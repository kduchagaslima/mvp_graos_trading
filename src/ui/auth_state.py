"""
Gerenciador de Estado de Autenticação, Sessão e Organizações na Interface (Ticket F13).
Garante retenção de tokens exclusivamente em memória (st.session_state),
seletor de empresa ativa e restrição visual de recursos conforme RBAC.
"""

import os
import streamlit as st
from typing import Optional, Dict, Any, List

# Configurações do Cognito / OIDC
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN", "")


def init_auth_state():
    """Inicializa as variáveis de sessão em memória do Streamlit."""
    if "is_authenticated" not in st.session_state:
        st.session_state.is_authenticated = False
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "current_user" not in st.session_state:
        st.session_state.current_user = None
    if "organizations" not in st.session_state:
        st.session_state.organizations = []
    if "active_org_id" not in st.session_state:
        st.session_state.active_org_id = None
    if "active_role" not in st.session_state:
        st.session_state.active_role = None


def login(token: str, user_data: Dict[str, Any], memberships: List[Dict[str, Any]]):
    """Efetua login registrando o token em memória e selecionando o tenant inicial."""
    st.session_state.is_authenticated = True
    st.session_state.auth_token = token
    st.session_state.current_user = user_data
    st.session_state.organizations = memberships
    if memberships:
        st.session_state.active_org_id = memberships[0]["organization_id"]
        st.session_state.active_role = memberships[0]["role"]
    else:
        st.session_state.active_org_id = None
        st.session_state.active_role = None


def logout():
    """Limpa todos os tokens e metadados de sessão em memória."""
    st.session_state.is_authenticated = False
    st.session_state.auth_token = None
    st.session_state.current_user = None
    st.session_state.organizations = []
    st.session_state.active_org_id = None
    st.session_state.active_role = None


def is_authenticated() -> bool:
    return st.session_state.get("is_authenticated", False)


def get_current_user() -> Optional[Dict[str, Any]]:
    return st.session_state.get("current_user")


def is_operator() -> bool:
    user = get_current_user()
    return bool(user and user.get("is_platform_operator", False))


def get_active_org_id() -> Optional[int]:
    return st.session_state.get("active_org_id")


def get_active_role() -> Optional[str]:
    return st.session_state.get("active_role")


def set_active_org(org_id: int):
    st.session_state.active_org_id = org_id
    for m in st.session_state.get("organizations", []):
        if m["organization_id"] == org_id:
            st.session_state.active_role = m["role"]
            break


def render_auth_header():
    """
    Renderiza o cabeçalho de autenticação e seletor de empresa na barra lateral.
    Permite alternar organizações ativas e efetuar logout.
    """
    init_auth_state()

    st.sidebar.markdown("### 🔐 Acesso & Organização")

    if not is_authenticated():
        # Formulário de Acesso para a Beta Privada
        with st.sidebar.expander("Entrar no AgriTrading", expanded=True):
            st.info("Plataforma em Beta Privada restrita a empresas convidadas.")
            
            # Opção 1: Seleção de perfil rápido para demonstração/piloto assistido
            demo_persona = st.selectbox(
                "Perfil de Acesso (Piloto):",
                [
                    "Cerrado Grãos Ltda (Dono / OWNER)",
                    "Sul Trading S/A (Analista / ANALYST)",
                    "Cooperativa Agro (Leitor / READER)",
                    "Operador da Plataforma (ADMIN)",
                ],
            )

            if st.button("Acessar Beta Privada", use_container_width=True):
                if "Cerrado" in demo_persona:
                    u = {"id": 1, "name": "Carlos Lima", "email": "carlos@cerradograos.com.br", "is_platform_operator": False}
                    m = [{"organization_id": 1, "organization_name": "Cerrado Grãos Ltda", "role": "OWNER"}]
                elif "Sul Trading" in demo_persona:
                    u = {"id": 2, "name": "Mariana Santos", "email": "mariana@sultrading.com.br", "is_platform_operator": False}
                    m = [{"organization_id": 2, "organization_name": "Sul Trading S/A", "role": "ANALYST"}]
                elif "Cooperativa" in demo_persona:
                    u = {"id": 3, "name": "João Pereira", "email": "joao@coopagro.com.br", "is_platform_operator": False}
                    m = [{"organization_id": 3, "organization_name": "Cooperativa Agro", "role": "READER"}]
                else:
                    u = {"id": 99, "name": "Operador AgriTrading", "email": "ops@agritrading.local", "is_platform_operator": True}
                    m = [{"organization_id": 1, "organization_name": "AgriTrading Master", "role": "OWNER"}]
                login("demo-jwt-in-memory-token", u, m)
                st.rerun()

            # Opção 2: Inserir token Bearer do Cognito se fornecido
            cognito_token = st.text_input("Ou cole seu Access Token Cognito:", type="password")
            if cognito_token:
                if st.button("Validar Token", use_container_width=True):
                    # Em integração real, chama GET /api/me
                    login(
                        cognito_token,
                        {"id": 10, "name": "Usuário Cognito", "email": "usuario@cognito.aws", "is_platform_operator": False},
                        [{"organization_id": 1, "organization_name": "Minha Empresa", "role": "ANALYST"}]
                    )
                    st.rerun()
    else:
        user = get_current_user()
        orgs = st.session_state.get("organizations", [])
        active_org = get_active_org_id()
        active_role = get_active_role()

        # Card do usuário logado
        op_tag = " 🛡️ OPERADOR" if user.get("is_platform_operator") else ""
        st.sidebar.markdown(
            f"""
            <div style="background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                <div style="font-weight: 700; color: #0f172a; font-size: 0.95rem;">👤 {user.get('name', 'Usuário')}</div>
                <div style="font-size: 0.8rem; color: #64748b;">{user.get('email', '')}{op_tag}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Seletor de Organização / Empresa
        if orgs:
            org_options = {o["organization_id"]: f"{o['organization_name']} ({o['role']})" for o in orgs}
            selected_org = st.sidebar.selectbox(
                "🏢 Empresa Ativa:",
                options=list(org_options.keys()),
                index=list(org_options.keys()).index(active_org) if active_org in org_options else 0,
                format_func=lambda x: org_options.get(x, str(x)),
            )
            if selected_org != active_org:
                set_active_org(selected_org)
                st.rerun()

            st.sidebar.caption(f"Seu papel na empresa: **{active_role}**")

        if st.sidebar.button("🚪 Sair da Conta (Logout)", use_container_width=True):
            logout()
            st.rerun()

    st.sidebar.markdown("---")
