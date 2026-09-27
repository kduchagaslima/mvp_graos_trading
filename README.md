# 🌾 MVP de Market Data e Trading de Grãos (Soja e Milho)

Sistema containerizado em Docker para comercialização de grãos e inteligência de trading. Permite calcular a **Paridade de Exportação (FAS / FOB / Balcão Interior)**, simular **Curva Forward e Custo de Carrego (*Carry Trade*)** e realizar **Testes de Estresse de Cenários** em tempo real.

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

4. **Market Data & Integrações**:
   - Ingestão da taxa **PTAX oficial ao vivo** do Banco Central do Brasil (API pública Olinda).
   - Base de dados pré-configurada para praças formadoras de MT, GO, PR, RS e BA, e portos de Santos, Paranaguá, Rio Grande, Barcarena e Itaqui.

5. **API REST FastAPI & Swagger**:
   - Endpoints padronizados para integrar com sistemas de ERP, planilhas Excel (via Power Query) ou outros frontends.

---

## 🚀 Como Executar em Ambiente Containerizado (Docker)

O projeto foi estruturado com `Docker` e `Docker Compose` para inicialização imediata e isolamento completo.

### Pré-requisitos
* [Docker](https://docs.docker.com/get-docker/) instalado
* [Docker Compose](https://docs.docker.com/compose/install/) instalado

### 1. Inicializar os Serviços

No diretório do projeto, execute:

```bash
make up
```

Ou usando o comando docker direto:

```bash
docker compose up -d
```

### 2. Acessar as Interfaces

* **Dashboard do Trader (Streamlit)**: Acesse [http://localhost:8501](http://localhost:8501)
* **API REST & Swagger Docs**: Acesse [http://localhost:8000/docs](http://localhost:8000/docs)
* **Healthcheck da API**: Acesse [http://localhost:8000/health](http://localhost:8000/health)

### 3. Executar os Testes Unitários

Para rodar os testes de integridade matemática e lógica de paridade dentro do container:

```bash
make test
```

Ou:

```bash
docker compose run --rm api pytest -v
```

### 4. Encerrar os Containers

```bash
make down
```

---

## 📁 Estrutura do Repositório

```
mvp_graos_trading/
├── docker-compose.yml       # Orquestração dos containers (Dashboard + API)
├── Dockerfile               # Build da imagem Python 3.11-slim
├── Makefile                 # Atalhos operacionais (make up, make test, etc.)
├── requirements.txt         # Dependências do projeto
├── README.md                # Guia de uso e visão geral
├── ARCHITECTURE.md          # Especificação matemática e formulação de paridade
├── src/
│   ├── domain/
│   │   ├── commodities.py   # Especificações de grãos e fatores bushel/ton
│   │   ├── locations.py     # Praças de originação, portos e fretes
│   │   └── models.py        # Schemas Pydantic de entrada e saída
│   ├── engines/
│   │   ├── export_parity.py # Motor de formação de preço FOB/FAS/Balcão
│   │   ├── carry_cost.py    # Motor de análise de curva forward e carrego
│   │   └── stress_tester.py # Motor de simulação de choques e sensibilidade
│   ├── services/
│   │   └── market_data.py   # Provedor de cotações, PTAX BCB e cache
│   ├── api/
│   │   └── main.py          # Backend REST FastAPI
│   └── ui/
│       └── app.py           # Dashboard analítico Streamlit
└── tests/
    ├── test_conversions.py  # Testes de bushel, kg, saca e tonelada
    ├── test_export_parity.py# Testes da fórmula de paridade
    └── test_carry_cost.py   # Testes de carrego e regras de decisão
```

---

## 📐 Fórmulas e Regras de Negócio

Para detalhes aprofundados sobre a matemática da formação de preço, fatores de bushel de soja (60 lbs) vs milho (56 lbs), e desoneração fiscal (Lei Kandir / Funrural / Fundos Estaduais), consulte o documento [ARCHITECTURE.md](ARCHITECTURE.md).
