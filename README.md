# 🌾 MVP de Market Data e Trading de Grãos (Soja e Milho)

Sistema containerizado em Docker para comercialização de grãos e inteligência de trading. Permite calcular a **Paridade de Exportação (FAS / FOB / Balcão Interior)**, simular **Curva Forward e Custo de Carrego (*Carry Trade*)**, realizar **Testes de Estresse de Cenários** e persistir cotações em uma **Base de Dados Relacional Otimizada** para séries temporais.

---

## 🎯 Funcionalidades Principais

1. **Calculadora de Paridade de Exportação (FAS / FOB)**:
   - Conversão de unidades internacionais: *Cents/Bushel* ➔ *USD/Ton* ➔ *R\$/Ton* ➔ *R\$/Saca de 60kg*.
   - Decomposição transparente dos custos de elevação portuária (THC), outras despesas portuárias, frete rodoviário, fundos fiscais estaduais (FETHAB MT, FUNDEINFRA GO, etc.), Funrural, quebra técnica e margem comercial da trading.
   - Cálculo automático do **Spread de Originação (*Basis*)** contra os preços físicos praticados no interior.
   - Gráfico interativo *Waterfall* (cascata) demonstrando a formação do preço centavo a centavo.

2. **Projeção de Curva Forward & Custo de Carrego (*Cost of Carry*)**:
   - Comparação analítica entre venda *Spot* (na colheita) e venda futura (*Forward*).
   - Cálculo do custo total de armazenagem física, custo financeiro de oportunidade do capital (CDI) e quebra técnica no armazém.
   - Recomendação automatizada com racional quantitativo: **"CARREGAR PARA VENDA FUTURA"** vs **"VENDER SPOT IMEDIATAMENTE"**.

3. **Simulador de Cenários & Testes de Estresse**:
   - Choques simultâneos de Câmbio (USD/BRL), Chicago (CBOT), Prêmios nos Portos e Fretes Rodoviários.
   - Matriz de calor (*Heatmap*) bidimensional de sensibilidade entre Dólar e CBOT para mapeamento de risco.

4. **Pipeline ETL de Extração & Persistência de Market Data**:
   - Função `extract_and_persist_market_data()` que coleta:
     - Taxa **PTAX oficial ao vivo** do Banco Central do Brasil (API pública Olinda com fallback de dias úteis).
     - Futuros da **CBOT (Soja e Milho)** via CME / provedores de mercado.
     - **Prêmios FOB** nos portos de Santos, Paranaguá, Rio Grande, Barcarena e Itaqui.
     - **Preços Físicos de Balcão** no interior (MT, GO, PR, RS, BA).
     - **Fretes Rodoviários** interior ➔ portos.
   - Gravação transacional com **Upsert idempotente** e registro de logs de auditoria (`extraction_logs`).

5. **Modelagem de Banco de Dados Otimizada para Consumo**:
   - Tabela `market_quotes` com chave natural única `(quote_date, category, symbol, contract_code, location_id)`.
   - Índices compostos de alta performance para consultas em \(O(1)\):
     - `idx_quotes_latest`: Recuperação imediata da cotação ativa mais recente.
     - `idx_quotes_lookup`: Consulta ultrarrápida de curvas a termo e séries temporais.
   - Suporte a SQLite com modo **WAL (Write-Ahead Logging)** e PostgreSQL via `DATABASE_URL`.

6. **API REST FastAPI & Swagger Docs**:
   - Endpoints para paridade, carry, estresse, extração sob demanda (`POST /api/market-data/extract`) e histórico (`GET /api/market-data/history/{symbol}`).

---

## 🚀 Como Executar em Ambiente Containerizado (Docker)

### Pré-requisitos
* [Docker](https://docs.docker.com/get-docker/) instalado
* [Docker Compose](https://docs.docker.com/compose/install/) instalado

### 1. Inicializar os Serviços

No diretório do projeto, execute:

```bash
make up
```

Ou diretamente pelo docker compose:

```bash
docker compose up -d
```

### 2. Acessar as Interfaces

* **Dashboard do Trader (Streamlit)**: Acesse [http://localhost:8501](http://localhost:8501)
* **API REST & Swagger Docs**: Acesse [http://localhost:8000/docs](http://localhost:8000/docs)
* **Healthcheck da API**: Acesse [http://localhost:8000/health](http://localhost:8000/health)

### 3. Executar o Pipeline de Extração e Persistência (ETL)

Você pode disparar a extração de dados de três maneiras:

1. **Pelo Dashboard**: Clicando no botão `⚡ Extrair & Persistir Market Data` na barra lateral do Streamlit.
2. **Pela Linha de Comando**:
   ```bash
   make extract
   ```
3. **Pela API REST**:
   ```bash
   curl -X POST http://localhost:8000/api/market-data/extract
   ```

### 4. Executar os Testes Unitários

Para rodar a suíte completa de testes (conversões, paridade, carrego, banco e extrator):

```bash
make test
```

### 5. Encerrar os Containers

```bash
make down
```

---

## 📁 Estrutura do Repositório

```
mvp_graos_trading/
├── docker-compose.yml          # Orquestração dos containers (Dashboard + API)
├── Dockerfile                  # Build da imagem Python 3.11-slim
├── Makefile                    # Atalhos operacionais (make up, make extract, make test)
├── requirements.txt            # Dependências do projeto
├── README.md                   # Guia de uso e visão geral
├── ARCHITECTURE.md             # Especificação matemática e modelagem relacional
├── data/                       # Volume persistente do banco de dados (market_data.db)
├── src/
│   ├── db/
│   │   ├── connection.py       # Engine SQLAlchemy com WAL mode e pooling
│   │   ├── models.py           # Modelos ORM (MarketQuote, ParitySnapshot, ExtractionLog)
│   │   └── repository.py       # DAO com queries indexadas e upserts atômicos
│   ├── domain/
│   │   ├── commodities.py      # Conversões bushel/ton/saca (Soja e Milho)
│   │   ├── locations.py        # Praças de originação, portos e fretes
│   │   └── models.py           # Schemas Pydantic validados
│   ├── engines/
│   │   ├── export_parity.py    # Motor de paridade FOB/FAS/Balcão
│   │   ├── carry_cost.py       # Motor de análise de curva forward e carrego
│   │   └── stress_tester.py    # Motor de simulação de choques e sensibilidade
│   ├── services/
│   │   ├── market_data.py      # Provedor de cotações com prioridade para o banco
│   │   └── extractor.py        # Pipeline ETL de extração e persistência
│   ├── scripts/
│   │   └── run_extraction.py   # Script CLI para agendamento / crontab
│   ├── api/
│   │   └── main.py             # Backend REST FastAPI
│   └── ui/
│       └── app.py              # Dashboard analítico Streamlit (5 abas completas)
└── tests/
    ├── test_conversions.py     # Testes de bushel, kg, saca e tonelada
    ├── test_export_parity.py   # Testes da fórmula de paridade
    ├── test_carry_cost.py      # Testes de carrego e regras de decisão
    ├── test_database.py        # Testes de banco, índices e upsert idempotente
    └── test_extractor.py       # Testes da função de extração e governança
```

---

## 📐 Fórmulas e Modelagem

Para detalhes aprofundados sobre a matemática da formação de preço, fatores de bushel de soja (60 lbs) vs milho (56 lbs), deduções fiscais e o diagrama ER do banco de dados, consulte o documento [ARCHITECTURE.md](ARCHITECTURE.md).
