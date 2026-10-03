# ADR 002: Ciclo de Sessão, Tokens em Memória e Evolução para BFF

## Status
**Aceito** (Planejamento da Fase 1 - 03/10/2026)

## Contexto
O armazenamento de tokens de autenticação (especialmente Refresh Tokens) no navegador do cliente (SPA) é um vetor comum de ataque via XSS (Cross-Site Scripting) quando armazenado em `localStorage` ou `sessionStorage`. É necessário definir uma política de sessão rigorosa para a fase de piloto.

## Decisão
1. **Tokens em Memória na SPA:** Durante a fase de piloto assistido / beta privada, os Access Tokens e Refresh Tokens serão mantidos **exclusivamente em variáveis de memória JavaScript** dentro do cliente, nunca em `localStorage`.
2. **Dados Transitórios:** Parâmetros efêmeros necessários para completar o handshake PKCE (`code_verifier`, `state`, `nonce`) podem usar `sessionStorage` com remoção imediata após a troca do código.
3. **Tempo de Vida (TTL):** O Access Token terá TTL curto de **15 minutos**.
4. **Comportamento no Reload:** Ao recarregar a página (F5), o cliente tentará obter nova autorização silenciosa via sessão ativa do provedor OIDC; caso a sessão tenha expirado, solicitará novo login explícito ao usuário.
5. **Evolução Arquitetural Futura (BFF):** Se a persistência contínua de sessão entre abas ou reloads se tornar requisito de produto, a arquitetura deverá evoluir formalmente para um padrão **BFF (Backend-for-Frontend)** utilizando cookies `HttpOnly`, `Secure`, `SameSite=Strict` e proteção anti-CSRF, sem improvisar persistência vulnerável no JavaScript do navegador.

## Consequências
- **Positivas:** Risco zero de exfiltração persistente de tokens via `localStorage`; sessão limpa automaticamente ao fechar a aba.
- **Negativas:** Usuário precisará reautenticar caso feche o navegador ou recarregue a aba sem sessão ativa no provedor.
