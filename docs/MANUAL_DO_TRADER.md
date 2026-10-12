# Manual Operacional do Trader de Grãos — AgriTrading

**Versão:** 2.0 (Alinhada com a Política de Transparência de Dados ADR-004 e W3C PROV)  
**Data:** 12/10/2026  
**Público-alvo:** Traders de Mesa, Analistas de Originação, Operadores Comerciais e Compliance  
**Classificação:** Uso Interno / Governança Operacional  

---

## 1. Visão Geral & Princípios de Negócio

O objetivo do AgriTrading é fornecer precisão matemática, velocidade e governança na formação de preços de compra no interior e exportação de commodities agrícolas (**Soja** e **Milho**).

### Princípio Fundamental de Rastreabilidade
> *Nenhum valor usado ou exibido como decisão de mercado pode aparecer sem identificação de origem, atualidade, unidade, timestamp, fonte e cadeia de derivação.*

---

## 2. Passo a Passo Operacional do Trader

```
+---------------------------------------------------------------------------------------------------+
|                                 FLUXO OPERACIONAL DA MESA                                         |
|                                                                                                   |
|  [1. Paridade FAS/FOB] -> [2. Corretagem] -> [3. Matriz Regional] -> [4. Carry] -> [5. Checklist] |
|        (Cálculo Base)       (Alocação)        (Decisão Compra)      (Tempo)       (Validação Final)|
+---------------------------------------------------------------------------------------------------+
```

---

### Passo 1: Formação do Preço FOB Porto e Paridade FAS Líquida

O preço internacional de referência no Brasil é determinado pela cotação do contrato futuro correspondente na **Bolsa de Chicago (CME/CBOT)**, somado ou subtraído do **Prêmio de Exportação (Port Premium)** praticado no porto de escoamento (Santos, Paranaguá, Barcarena, Itaqui ou Rio Grande).

#### 1.1 Fórmula do Preço FOB Porto
$$\text{Preço FOB (¢/bu)} = \text{CBOT (¢/bu)} + \text{Prêmio (¢/bu)}$$
$$\text{Preço FOB (USD/t)} = \text{Preço FOB (¢/bu)} \times \text{Fator de Conversão}$$
$$\text{Preço FOB (R\$/saca)} = \text{Preço FOB (USD/t)} \times \text{Câmbio PTAX (USD/BRL)} \times 0,06$$

*Fatores Oficiais de Conversão:*
- **Soja:** `0,3674371` (36,7437 bushels por tonelada métrica).
- **Milho:** `0,3936825` (39,3682 bushels por tonelada métrica).
- **Saca de 60kg:** $1\text{ tonelada} = 16,6667\text{ sacas}$ (fator $0,06\text{ t/sc}$).

#### 1.2 Waterfall de Custos: Do Porto ao Interior
Para encontrar o preço teto que a trading pode pagar no balcão da fazenda ou armazém (*Paridade Líquida Balcão Interior*), desconta-se:

1. **Preço FOB Porto (100%):** Base de venda na exportação.
2. **(-) Elevação Portuária (THC):** Tarifa do terminal portuário (USD 7,00 a 8,50/t + despesas acessórias de R$ 10 a 15/t).
3. **(-) Provisão de Demurrage:** Risco de sobreestadia do navio no line-up (USD 0,80 a 2,50/t dependendo da fila de espera).
4. **(=) Preço FAS Entregue no Porto:** Free Alongside Ship.
5. **(-) Frete Rodoviário Origem-Porto:** Custo de frete por tonelada até o porto de destino.
6. **(-) Margem da Trading:** Margem comercial mínima requerida pela empresa (padrão de mercado: USD 2,00 a 3,00/t).
7. **(-) Despesa de Corretagem:** Conforme modelo acordado com o intermediador (R$ 0,25 a R$ 0,70/sc).
8. **(-) Fundo Tributário Estadual:** Retenção obrigatória (ex: FETHAB no MT: R$ 2,85/sc na soja; FUNDEINFRA em GO: R$ 1,65/sc).
9. **(-) Quebra Técnica & Umidade:** Dedução de 0,20% a 0,30% sobre o valor após tributos.
10. **(-) Funrural:** Contribuição previdenciária de 1,5% retida na comercialização.
11. **(=) Paridade Líquida Balcão Interior (R$/sc):** **Preço Teto da Trading.**

> **Regra de Ouro:** A Paridade Líquida Balcão é o preço de indiferença da trading. Comprar acima desse teto significa exportar com prejuízo na margem da mesa.

---

### Passo 2: Tratamento de Despesa com Corretor de Grãos (Brokerage)

A plataforma suporta três modelos de negócio para intermediação de grãos:

#### Modelo 1: Trading Paga a Corretagem (Dedução da Paridade)
- **Operação:** A trading contrata o corretor e assume o encargo. O valor é abatido diretamente da oferta ao produtor.
- **Fórmula:** $\text{Preço Ofertado ao Produtor} = \text{Paridade FAS} - \text{Corretagem}$
- **Exemplo:** Paridade R$ 125,00/sc - Corretagem R$ 0,50/sc = **R$ 124,50/sc pago ao produtor**.
- **Resultado:** Margem comercial líquida da mesa permanece 100% protegida.

#### Modelo 2: Produtor Paga a Corretagem (Retenção Contratual na Fonte)
- **Operação:** O produtor assume a comissão. A trading formaliza o contrato pelo preço cheio de balcão e retém a comissão na liquidação financeira.
- **Exemplo:** Contrato Compra: R$ 125,00/sc | Retenção: R$ 0,50/sc | **Líquido ao Produtor: R$ 124,50/sc** | Repasse ao Corretor: R$ 0,50/sc (mediante NF de Serviços).
- **Vantagem:** Custo financeiro zero para a trading. A trading atua apenas como fonte retentora.

#### Modelo 3: Originação Direta (Sem Corretor)
- **Operação:** Compra direta com o produtor rural ou cooperativa sem intermediação.
- **Opção A:** Reter os R$ 0,50/sc como margem adicional da trading.
- **Opção B:** Repassar R$ 0,20 a R$ 0,30/sc na oferta para ganhar o lote da concorrência na praça.

---

### Passo 3: Decisão na Matriz Regional de Praças & Arbitragem Logística

#### 3.1 Interpretação do Spread da Mesa
$$\text{Spread da Mesa (R\$/sc)} = \text{Paridade Líquida Balcão} - \text{Preço Físico Praticado no Interior}$$

- **Spread Positivo (COMPRAR):** A paridade que a trading pode pagar é superior à pedida do balcão local. A mesa fecha a compra e realiza a exportação capturando o spread como lucro.
- **Spread Negativo (AGUARDAR / PASSAR):** A cotação local está inflacionada pela demanda doméstica (esmagadoras, usinas de etanol de milho ou fábricas de ração). Exportar o lote traria prejuízo.

#### 3.2 Otimização do Corredor de Escoamento
- **Mato Grosso Centro-Norte (Sorriso, Sinop, Lucas do Rio Verde):** Priorizar escoamento pelo **Arco Norte (Barcarena - BCR ou Itaqui - ITQ)** via BR-163. A economia de frete de R$ 60 a R$ 80/t frequentemente supera deságios pontuais de prêmio portuário.
- **Goiás e Triângulo Mineiro:** Rota rodoferroviária preferencial para **Santos (STS)**.
- **Paraná e Rio Grande do Sul:** Isenção de fundos estaduais (FETHAB zero), com escoamento rápido por **Paranaguá (PNG)** ou **Rio Grande (RG)**.

---

### Passo 4: Arbitragem Temporal e Custo de Carrego (Carry Trade)

#### 4.1 Equação do Carry Líquido
$$\text{Spread Bruto Forward} = \text{Preço Futuro} - \text{Preço Spot}$$
$$\text{Custo Total de Carrego} = \text{Custo de Capital (CDI)} + \text{Armazenagem} + \text{Quebra}$$
$$\text{Carry Líquido} = \text{Spread Bruto Forward} - \text{Custo Total de Carrego}$$

#### 4.2 Critérios de Ação da Mesa (3 Níveis)
1. **Carry Líquido > +R$ 0,75/sc: CARREGAR A POSIÇÃO**  
   O prêmio da curva futura cobre juros e armazenagem com margem atrativa.  
   *Ação:* Comprar no spot, travar a venda futura na B3/Exportação e estocar em armazém credenciado.
2. **-R$ 0,75/sc ≤ Carry Líquido ≤ +R$ 0,75/sc: NEUTRO / INDIFERENTE**  
   Spread empata rigorosamente com os custos financeiros e operacionais.  
   *Ação:* Priorizar giro de estoque e capacidade estática.
3. **Carry Líquido < -R$ 0,75/sc: VENDER SPOT IMEDIATAMENTE**  
   Mercado em inversão (*backwardation*) ou com prêmio forward inferior ao custo de capital.  
   *Ação:* Liquidar o grão à vista no balcão físico.

---

### Passo 5: Política de Transparência de Dados e Rastreabilidade (ADR-004 / W3C PROV)

Todo cálculo gerado pela plataforma possui rastreabilidade em dois eixos independentes:

#### Eixo 1: Origem dos Dados (`origin_axis`)
- `OBSERVED`: Capturado diretamente de fonte oficial (BACEN PTAX, CME/CBOT, B3, CEPEA). Apto para decisão operacional.
- `MANUAL`: Inserido ou corrigido por operador autorizado com justificativa registrada.
- `ESTIMATED`: Calculado ou projetado matematicamente com premissas declaradas.
- `DEMO`: Dado sintético de demonstração. **PROIBIDO PARA COMPRAS REAIS.**
- `UNVERIFIED`: Dado cuja integridade ou procedência não pôde ser auditada. **PROIBIDO PARA COMPRAS REAIS.**

#### Eixo 2: Frescor Temporal (`freshness_axis`)
- `CURRENT`: Cotação dentro da política dinâmica de tolerância:
  - **CBOT/CME:** 20 minutos durante pregão ativo (ou até próxima abertura após o fechamento).
  - **PTAX:** Válido até o próximo boletim oficial do BACEN.
  - **CEPEA:** Válido por 24 horas úteis.
  - **Fretes:** Válido por 72 horas úteis.
- `STALE`: Cotação que ultrapassou a janela temporal. Requer flag `allow_stale=True` e **não recebe selo `DECISION_READY`**.
- `UNKNOWN`: Timestamp ausente ou corrompido. **Cálculo bloqueado.**

---

### Passo 6: Checklist Obrigatório Antes de Bater o Martelo

```text
================================================================================
          CHECKLIST DE MESA: 6 VALIDAÇÕES MANDATÓRIAS ANTES DO FECHAMENTO
================================================================================
[ ] 1. STATUS DECISION_READY ATIVO
       A cotação possui origin_axis=OBSERVED e freshness_axis=CURRENT?
       (Proibido executar compras reais com dados em DEMO, UNVERIFIED ou STALE sem autorização).

[ ] 2. REGISTRO DE LINHAGEM E IDENTIFICADOR ÚNICO
       O parity_run_id foi gerado e registrado no terminal para auditoria de proveniência (W3C PROV)?

[ ] 3. TRAVA SIMULTÂNEA DE FUTUROS E CÂMBIO (HEDGE)
       A perna CBOT/B3 e o Câmbio Pronto / NDF foram travados imediatamente para eliminar risco de mercado?

[ ] 4. JANELA PORTUÁRIA & FRETE RODOVIÁRIO CONFIRMADOS
       A tarifa de frete está formalizada com a transportadora e a janela de entrega bate com o line-up do navio?

[ ] 5. CONFORMIDADE FISCAL E FUNDOS ESTADUAIS
       Produtor está regular na SEFAZ e os recolhimentos de FETHAB, FUNDEINFRA ou Funrural estão calculados?

[ ] 6. MARGEM MÍNIMA DA TRADING PRESERVADA
       A margem comercial da empresa (mínimo USD 2,00/t no perfil padrão) e o modelo de corretagem estão resguardados?
================================================================================
```
