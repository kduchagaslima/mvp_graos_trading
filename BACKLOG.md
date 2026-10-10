# Backlog do AgriTrading

## UX/UI
- **Melhoria da Tela de Login (Cognito Hosted UI):** A tela atual está feia. Redesenhar para um padrão mais profissional e moderno, injetando CSS customizado no Cognito e incluindo a logo oficial.
  - *Logo selecionada:* Salva em `docs/assets/agritrading_logo_oficial.jpg`

## Engenharia de Backend / Arquitetura de Dados (Transparência de Paridade)
- **Tabela Satélite W3C PROV:** Criar tabela `MARKET_QUOTES_LINEAGE` no banco de dados para registrar a derivação matemática (fórmula, versão, inputs) sem poluir a base principal de cotações.
- **Validação de Qualidade e Atualidade:** Implementar no motor de cálculo o bloqueio de dados `DEMO` e `UNVERIFIED` em ambiente produtivo.
- **Motor de TTL Dinâmico:** Implementar regras de expiração (STALE) por fonte (ex: 20 min para CBOT, boletim para PTAX, 24h para CEPEA).
