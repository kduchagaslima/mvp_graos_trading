# ADR 003: Multi-tenancy, Autorização no Banco e RBAC

## Status
**Aceito** (Planejamento da Fase 1 - 03/10/2026)

## Contexto
O AgriTrading foi concebido como um MVP monousuário, onde todas as cotações e premissas residem em um único contexto. Para viabilizar múltiplos clientes empresariais (tradings, cooperativas, consultorias), é necessário segregar dados privados com isolamento rigoroso, impedindo qualquer acesso cruzado (BOLA / IDOR).

## Decisão
1. **A API valida Identidade; o Banco autoriza a Empresa:**
   - O FastAPI valida a assinatura criptográfica do JWT emitido pelo Cognito e extrai o identificador imutável do usuário (`sub`).
   - O backend consulta no banco de dados (Neon Postgres) os registros de `User` e `Membership` para determinar a quais empresas (`Organization`) o usuário pertence e quais permissões possui.
2. **Desconfiança em Seletores do Cliente:**
   - `organization_id` enviado em rotas ou cabeçalhos é tratado estritamente como um **seletor solicitado**, nunca como prova de autoridade. O backend verifica obrigatoriamente se o usuário autenticado possui `Membership` ativa naquela organização antes de executar a query.
3. **Papéis Mínimos (RBAC):**
   - `OWNER` (Dono da Empresa): Pode convidar membros, alterar papéis, configurar perfil de custos privado e operar motores. Não possui privilégios de operador da plataforma.
   - `ANALYST` (Analista): Pode calcular paridades, alterar custos operacionais e criar simulações, mas não gerencia membros da organização.
   - `READER` (Leitor): Acesso somente-leitura aos dados de mercado e cálculos da empresa, sem permissão de gravação.
4. **Isolamento de Recursos Privados:**
   - Toda entidade privada (como `CostProfile`) deve possuir a chave estrangeira obrigatória `organization_id`. Consultas devem sempre filtrar pelo `organization_id` validado da sessão.
   - Recursos inexistentes ou pertencentes a outras empresas devem retornar HTTP `404 Not Found` (para não confirmar a existência do recurso) ou `403 Forbidden` quando o acesso ao recurso conhecido for negado.

## Consequências
- **Positivas:** Prevenção completa contra ataques BOLA/IDOR; possibilidade de um usuário pertencer a mais de uma empresa via múltiplas `Membership`; bloqueio instantâneo de usuários ao desativar a membership no banco, sem depender da expiração do JWT.
- **Negativas:** Requer consulta ao banco relacional a cada requisição autenticada de recurso privado.
