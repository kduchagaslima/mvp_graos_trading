# Backlog do AgriTrading

## UX/UI & Transparência
- [x] **Melhoria da Tela de Login (Cognito Hosted UI):** Redesenhar para padrão profissional, CSS customizado no Cognito e logo oficial otimizada (26KB).
- [x] **Revisão do Manual do Trader:** Publicado em `docs/MANUAL_DO_TRADER.md` e integrado à Tab 6 com checklist `DECISION_READY` e impressão/PDF.
- [x] **Exibição do Selo DECISION_READY e Linhagem W3C PROV na Calculadora:** Exibição do badge visual `DECISION_READY` / `REVISÃO NECESSÁRIA`, eixos de transparência e modal interativo de linhagem W3C PROV (`parity_run_id`, `prov:used`, `prov:generated`, JSON completo).
- [x] **Modal de Termos de Uso e Política de Privacidade (LGPD / Ag Data Transparent):** Apresentação no rodapé e modal dedicado com prazo de retenção de 5 anos, direitos dos titulares (LGPD Art. 18) e aviso sobre dados agregados para treinamento de IA.

## Engenharia de Backend & Auditoria de Dados
- [x] **Tabela Satélite W3C PROV:** Criar tabela `MARKET_QUOTES_LINEAGE` no DDL e ORM para registrar derivação sem sobrecarregar cotações principais.
- [x] **Validação de Qualidade e Atualidade:** Bloqueio obrigatório de dados `DEMO`, `UNVERIFIED`, `UNKNOWN` e `STALE` (sem autorização).
- [x] **Motor de TTL Dinâmico:** Regras de expiração por fonte (CBOT 20min pregão, PTAX boletim, CEPEA 24h, Frete 72h).
- [x] **Migração Versionada 006 (`006_market_quotes_lineage.sql`):** Adicionado script SQL em `src/db/migrations/` e validada idempotência no `run_migrations()`.
- [x] **Endpoint de Auditoria de Linhagem (`GET /api/parity/lineage/{parity_run_id}`):** Persistência automática das execuções de paridade e rota de consulta de linhagem W3C PROV.
- [x] **Conectores Oficiais Gratuitos (BACEN, CBOT, B3 MDS, CEPEA/ESALQ):** Ingestão de cotações reais das fontes oficiais com classificação `OBSERVED`, preservando resiliência offline e sementes como fallback.
- [x] **Tabela de Piso Mínimo Regulatório ANTT (Lei nº 13.703/2018 / Resolução nº 5.867/2020):** Cálculo oficial dos custos mínimos para granel sólido (Bitrem 7 eixos 37t e Rodotrem 9 eixos 49t), matriz de conformidade regulatória por corredor (`ABOVE_FLOOR` vs `BELOW_FLOOR`), endpoint `GET /api/freight/antt-floor`, KPI e modal explicativo no frontend.
- [x] **Contratos Privados de Frete Rodoviário da Trading (Multi-tenant):** Tabela e migração versionada `007_company_freight_contracts.sql`, endpoints CRUD e batch em `/api/organizations/{org_id}/freight-contracts`, precedência da tabela privada sobre cotações públicas da mesa e UI completa em "Minha Empresa" (cadastro individual e importação em lote).

## Próximos Passos (Fase 3 - Futuro)
- **Conectores Proprietários Pagos / Streaming Intraday:** Ingestão de dados de alta frequência via Webhook/WebSocket comercial (ex: Cedro, Barchart, CME FIX).
- **Alarmes e Observabilidade:** Alertas no CloudWatch se cotações críticas ficarem STALE em horário comercial.
