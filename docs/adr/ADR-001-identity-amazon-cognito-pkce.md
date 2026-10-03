# ADR 001: Gestão de Identidade com Amazon Cognito User Pool e PKCE

## Status
**Aceito** (Planejamento da Fase 1 - 03/10/2026)

## Contexto
O MVP do AgriTrading não possui autenticação e expõe todos os endpoints REST de forma aberta. Para viabilizar uma beta privada e transformar a aplicação em um Micro-SaaS B2B seguro, é necessário autenticar os usuários corporativos sem desenvolver autenticação artesanal ou armazenar hashes de senhas no banco relacional da aplicação.

## Decisão
1. Adotar **Amazon Cognito User Pool** com **Managed Login** utilizando o fluxo padrão **Authorization Code Grant com PKCE (Proof Key for Code Exchange)** com desafio criptográfico `S256`.
2. O frontend é configurado estritamente como **cliente público** (sem `client_secret` exposto no código JavaScript).
3. Desabilitar implicit grant em todos os clientes de app.
4. Definir redirect URIs e logout URIs exatas por ambiente (`staging`, `prod`), rejeitando qualquer URL curinga.
5. Utilizar parâmetros de transação `state` e `nonce` para proteção contra ataques CSRF e replay durante a troca de código OIDC.
6. A administração de contas (cadastro, redefinição de senha, confirmação de e-mail e políticas de complexidade) é delegada ao Cognito.

## Consequências
- **Positivas:** Sem risco de vazamento de senhas no PostgreSQL; conformidade com OWASP e melhores práticas AWS; infraestrutura serverless gerenciada sem custo operacional fixo adicional.
- **Negativas:** Dependência do serviço Cognito na AWS; necessidade de validar JWTs com JWKS localmente no backend FastAPI.
