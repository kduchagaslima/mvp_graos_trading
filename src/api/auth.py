"""
Módulo de Autenticação e Autorização Multi-tenant do AgriTrading (Tickets F08, F09, F10).
Integração com Amazon Cognito (OIDC / PKCE / RS256 JWKS), validação estrita de Access Tokens,
provisionamento Just-In-Time (JIT), segregação multi-tenant e RBAC (OWNER, ANALYST, READER).
"""

import os
import logging
from typing import Dict, Any, Optional, List
from fastapi import Header, HTTPException, Depends, Path
from sqlalchemy.orm import Session
import jwt
from jwt import PyJWKClient

from src.db.connection import get_db
from src.db.models import User, Organization, Membership, MembershipRole

logger = logging.getLogger(__name__)

# Configurações de Ambiente para Amazon Cognito e OIDC
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")
COGNITO_JWKS_URL = os.getenv(
    "COGNITO_JWKS_URL",
    f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"
    if COGNITO_USER_POOL_ID else ""
)
COGNITO_ISSUER = os.getenv(
    "COGNITO_ISSUER",
    f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    if COGNITO_USER_POOL_ID else ""
)

# Chave pública RSA configurável para ambientes de teste determinísticos (sem dependência de rede)
_TEST_PUBLIC_KEY: Optional[str] = None
_jwks_client: Optional[PyJWKClient] = None


def set_test_public_key(pem_key: Optional[str]):
    """Configura chave pública RSA para execução de testes locais isolados."""
    global _TEST_PUBLIC_KEY
    _TEST_PUBLIC_KEY = pem_key


def get_jwks_client() -> Optional[PyJWKClient]:
    """Retorna cliente JWKS com cache de chaves para o User Pool do Cognito."""
    global _jwks_client
    if _jwks_client is None and COGNITO_JWKS_URL:
        _jwks_client = PyJWKClient(COGNITO_JWKS_URL, cache_keys=True, max_cached_keys=16)
    return _jwks_client


# Hierarquia de permissões RBAC
ROLE_LEVELS: Dict[str, int] = {
    MembershipRole.READER.value: 1,
    MembershipRole.ANALYST.value: 2,
    MembershipRole.OWNER.value: 3,
}


def decode_and_validate_jwt(token: str) -> Dict[str, Any]:
    """
    Valida e decodifica o JWT com verificação estrita:
    1. Assinatura RS256 e algoritmo permitido
    2. Validade temporal (exp)
    3. token_use == 'access' (ID token explicitamente rejeitado para acesso a APIs)
    4. client_id obrigatório e idêntico ao app client configurado (access token)
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT header: {str(e)}")

    alg = unverified_header.get("alg")
    if alg != "RS256":
        raise HTTPException(
            status_code=401,
            detail=f"Unsupported token algorithm '{alg}'. Only RS256 is permitted."
        )

    # 1. Obtenção da chave de verificação
    key = None
    if _TEST_PUBLIC_KEY:
        key = _TEST_PUBLIC_KEY
    else:
        client = get_jwks_client()
        if client:
            try:
                signing_key = client.get_signing_key_from_jwt(token)
                key = signing_key.key
            except Exception as e:
                logger.error(f"Failed to fetch JWKS signing key: {e}")
                raise HTTPException(status_code=401, detail="Signing key not found or unavailable in JWKS")
        else:
            # Fallback para ambiente local/desenvolvimento sem Cognito configurado
            # Rejeita em produção
            if os.getenv("ENVIRONMENT") == "production":
                raise HTTPException(status_code=500, detail="Authentication provider not configured in production")
            # Em dev sem chaves configuradas, rejeita tokens que exijam validação estrita
            raise HTTPException(status_code=401, detail="JWKS client not configured and no test key set")

    # 2. Decodificação do payload
    try:
        decode_kwargs: Dict[str, Any] = {
            "algorithms": ["RS256"],
            "options": {"verify_exp": True},
        }
        if COGNITO_ISSUER and not _TEST_PUBLIC_KEY:
            decode_kwargs["issuer"] = COGNITO_ISSUER

        payload = jwt.decode(token, key, **decode_kwargs)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

    # 3. Validação do uso do token: ID TOKEN NÃO É ACCESS TOKEN
    token_use = payload.get("token_use")
    if token_use != "access":
        if token_use == "id":
            raise HTTPException(
                status_code=401,
                detail="ID token is not allowed for API authentication; an access token is required."
            )
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token_use '{token_use}'. Access token required."
        )

    # 4. Validação de client_id (se configurado)
    if COGNITO_APP_CLIENT_ID:
        token_client_id = payload.get("client_id")
        if token_client_id != COGNITO_APP_CLIENT_ID:
            raise HTTPException(status_code=401, detail="Token client_id mismatch")

    return payload


def get_token_payload(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Extrai e valida o token Bearer do cabeçalho de autorização."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    token = parts[1]
    return decode_and_validate_jwt(token)


def get_current_user(
    payload: Dict[str, Any] = Depends(get_token_payload),
    db: Session = Depends(get_db),
) -> User:
    """
    Carrega o usuário ativo a partir do sub verificado do token Cognito.
    Aplica provisionamento JIT caso seja o primeiro acesso verificado do usuário.
    Garante que contas desativadas sejam bloqueadas imediatamente a cada requisição.
    """
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        raise HTTPException(status_code=401, detail="Token payload missing 'sub' subject claim")

    user = db.query(User).filter(User.cognito_sub == cognito_sub).first()
    if not user:
        # Provisionamento Just-In-Time (JIT) para usuário verificado
        email = payload.get("email") or payload.get("username") or f"{cognito_sub}@agritrading.local"
        name = payload.get("name") or payload.get("cognito:username") or email.split("@")[0]
        user = User(
            cognito_sub=cognito_sub,
            email=email,
            name=name,
            is_active=True,
            is_platform_operator=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Provisioned new user JIT: id={user.id}, email={user.email}, sub={cognito_sub}")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is deactivated or suspended")

    return user


def get_current_membership(
    org_id: int = Path(..., description="ID da organização solicitada"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Membership:
    """
    Verifica a filiação ativa do usuário na organização solicitada.
    organization_id é um seletor solicitado; a autorização é sempre verificada no banco.
    """
    membership = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.organization_id == org_id,
            Membership.is_active == True,
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: user does not have active membership in organization {org_id}"
        )

    if not membership.organization or not membership.organization.is_active:
        raise HTTPException(
            status_code=403,
            detail=f"Organization {org_id} is inactive or suspended"
        )

    return membership


def require_role(min_role: MembershipRole):
    """
    Fábrica de dependência para controle de acesso baseado em papel (RBAC).
    Hierarquia: OWNER (3) >= ANALYST (2) >= READER (1).
    """
    min_level = ROLE_LEVELS[min_role.value]

    def role_dependency(
        membership: Membership = Depends(get_current_membership),
    ) -> Membership:
        user_level = ROLE_LEVELS.get(membership.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions: role '{membership.role}' does not meet required '{min_role.value}'"
            )
        return membership

    return role_dependency


def require_platform_operator(
    user: User = Depends(get_current_user),
) -> User:
    """
    Garante que apenas operadores da plataforma tenham acesso a rotas administrativas.
    """
    if not user.is_platform_operator:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: requires platform operator privileges"
        )
    return user
