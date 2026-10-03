# ADR 004: Qualidade de Dados, Dois Eixos de Rastreabilidade e Fim de Séries Artificiais

## Status
**Aceito** (Planejamento da Fase 1 - 03/10/2026)

## Contexto
O MVP utilizava geradores estatísticos e passeios aleatórios (`random.Random`) para fabricar séries históricas (como nos endpoints de candlestick e histórico de frete) e misturava no snapshot cotações reais do banco de dados com dicionários em memória (`DEFAULT_MARKET_SEEDS`). Em uma plataforma de trading e formação de preços, simular dados aleatórios como se fossem mercado real destrói a credibilidade da ferramenta.

## Decisão
1. **Fim dos Dados Fabricados:**
   - Remover geradores aleatórios (`random.Random`) de todas as rotas e serviços de mercado.
   - Quando não houver dados históricos suficientes para um determinado período ou ativo, a API deve retornar explicitamente apenas os pontos observados reais com a indicação de cobertura, ou um aviso transparente de ausência de dados, nunca uma curva artificial inventada.
2. **Modelagem em Dois Eixos Independentes:**
   - **Eixo 1 — Origem do Dado (`data_kind`):**
     - `OBSERVED`: Coletado diretamente da fonte oficial (BCB, B3, CEPEA, CME).
     - `MANUAL`: Inserido manualmente pelo operador ou usuário via override.
     - `ESTIMATED`: Calculado ou projetado por fórmula conhecida documentada.
     - `DEMO`: Dado demonstrativo mockado explicitamente sinalizado para testes.
     - `UNVERIFIED`: Dado legado cuja procedência não pode ser formalmente auditada.
   - **Eixo 2 — Atualidade (`freshness`):**
     - `CURRENT`: Dado atual dentro da janela de tolerância daquela frequência (ex: PTAX do dia útil).
     - `STALE`: Dado defasado que ultrapassou a janela esperada sem atualização.
     - `UNKNOWN`: Estado indeterminado de atualização.
3. **Precisão Numérica Financeira:**
   - Migrar campos financeiros críticos para `Decimal` / `NUMERIC` com regras explícitas de arredondamento, eliminando imprecisões de ponto flutuante IEEE 754 em cálculos de paridade e carrego.
4. **Timezone UTC Explícito:**
   - Todas as datas e horários persistidos (`observed_at`, `ingested_at`) devem utilizar timezone explícito UTC (`timezone.utc`), eliminando chamadas legadas de `datetime.utcnow()`.

## Consequências
- **Positivas:** Transparência e integridade total perante clientes institucionais; ausência de surpresas com dados fabricados; clareza na auditoria de cada valor apresentado na tela.
- **Negativas:** Gráficos podem apresentar lacunas visuais caso a ingestão histórica de um contrato recente tenha poucos pontos coletados.
