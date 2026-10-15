# Manual Operacional do Trader de Grãos — AgriTrading

**Versão:** 2.1 (Alinhada com Conformidade Regulatória ANTT Lei 13.703/2018, Contratos Privados de Frete, Boletas Formais Trade Ticket e W3C PROV)  
**Data:** 15/10/2026  
**Público-alvo:** Traders de Mesa, Analistas de Originação, Operadores Comerciais, Risco e Compliance  
**Classificação:** Uso Interno / Governança Operacional  

---

## 1. Visão Geral & Princípios de Negócio

O objetivo do AgriTrading é fornecer precisão matemática, velocidade analítica e governança institucional na formação de preços de compra no interior e exportação de commodities agrícolas (**Soja** e **Milho**).

### Princípio Fundamental de Rastreabilidade e Decisão
> *Nenhum valor usado ou exibido como decisão de mercado pode aparecer sem identificação de origem, atualidade, unidade, timestamp, fonte oficial e cadeia de derivação matemática.*

---

## 2. Fluxo Operacional da Mesa de Operações

```text
+-------------------------------------------------------------------------------------------------------------------------------------------------+
|                                                           FLUXO OPERACIONAL DA MESA                                                              |
|                                                                                                                                                 |
|  [1. Paridade FAS/FOB] -> [2. Corretagem] -> [3. Matriz Regional] -> [4. Piso ANTT & Fretes] -> [5. Comparador Bids]                             |
|        (Cálculo Base)       (Alocação)        (Decisão Compra)      (Conformidade Legal)       (Arbitragem Lote)                                |
|                                                                                                                                                 |
|  --------> [6. Carry Trade] -> [7. Transparência PROV] -> [8. Emissão da Boleta & Excel] -> [Checklist 7 Validações]                            |
|                 (Tempo)            (Auditoria)                   (Formalização)                   (Fechamento)                                  |
+-------------------------------------------------------------------------------------------------------------------------------------------------+
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
8. **(-) Fundo Tributário Estadual:** Retenção obrigatória (ex: FETHAB no MT: R$ 2,85/sc na soja; FUNDEINFRA em GO: R$ 1,65/sc; PRODEAGRO na BA: R$ 0,60/sc; Isento no PR e RS).
9. **(-) Quebra Técnica & Umidade:** Dedução de 0,20% a 0,30% sobre o valor após tributos.
10. **(-) Funrural:** Contribuição previdenciária de 1,5% retida na comercialização.
11. **(=) Paridade Líquida Balcão Interior (R$/sc):** **Preço Teto da Trading.**

> **Regra de Ouro do Trader:** A Paridade Líquida Balcão é o preço de indiferença da trading. Comprar acima desse teto significa exportar com prejuízo na margem da mesa.

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

### Passo 4: Conformidade com Piso Mínimo Regulatório ANTT & Contratos Privados de Frete

O frete rodoviário é a maior despesa logística na originação de grãos no Brasil e está sujeito a regulação federal estrita.

#### 4.1 Legislação e Piso Mínimo ANTT (Lei nº 13.703/2018 / Resolução nº 5.867/2020)
- A ANTT fixa semestralmente a **Política Nacional de Pisos Mínimos do Transporte Rodoviário de Cargas (PNPM-TRC)** para carga lotação de granel sólido.
- **Veículos Típicos:**
  - **Bitrem 7 Eixos (37 toneladas úteis):** Coeficiente de deslocamento $CCD = \text{R\$} 4,9232/\text{km}$ e carga/descarga $CC = \text{R\$} 382,15$.
  - **Rodotrem 9 Eixos (49 toneladas úteis):** Coeficiente de deslocamento $CCD = \text{R\$} 5,8410/\text{km}$ e carga/descarga $CC = \text{R\$} 435,50$.
- **Fórmula do Piso por Tonelada:**
  $$\text{Piso Mínimo (R\$/ton)} = \frac{(\text{Distância (km)} \times CCD) + CC}{\text{Capacidade Útil (ton)}}$$

> ⚠️ **ALERTA DE RISCO JURÍDICO (Art. 5º da Lei nº 13.703/2018):**  
> O contratante (embarcador/trading) que pagar frete inferior ao piso mínimo responderá pelo pagamento de **indenização equivalente ao dobro da diferença do valor que seria devido**.  
> O sistema exibe o status legal por corredor:  
> - `ABOVE_FLOOR`: Frete de mercado ou contrato acima do piso (**Conforme e autorizada contratação**).  
> - `BELOW_FLOOR`: Frete abaixo do piso legal (**Alerta crítico de passivo trabalhista/regulatório**).

#### 4.2 Contratos Privados de Frete da Trading
- Quando a trading possui contratos de longo prazo com transportadoras ou frotistas próprios, as tarifas contratadas podem ser cadastradas na aba **"Minha Empresa"** (individualmente ou via importação JSON em lote).
- **Regra de Precedência:** Havendo contrato ativo para a rota (ex: Sorriso ➔ Santos), a tarifa contratada **substitui automaticamente** a cotação pública de mercado nas calculadoras e matrizes da organização.

---

### Passo 5: Comparador de Propostas de Venda & Arbitragem de Bids

No dia a dia comercial, o originador recebe simultaneamente propostas de diferentes tradings/compradores e precisa decidir onde alocar o lote de grãos.

#### 5.1 Parâmetros do Lote
- O operador informa o **Volume do Lote** (ex: 10.000 sacas = 600 toneladas) e cadastra até 3 propostas simultâneas com comprador, porto de destino, CBOT, prêmio FOB, frete e tributos.

#### 5.2 Regra de Decisão do Comparador
$$\text{Receita Total do Lote (R\$)} = \text{Volume (sacas)} \times \text{Paridade Líquida Balcão da Proposta (R\$/sc)}$$
$$\text{Vantagem Financeira no Lote (R\$)} = \text{Receita Proposta Vencedora} - \text{Receita Segunda Colocada}$$

- O sistema elege a **Proposta Vencedora** (maior rentabilidade líquida na fazenda) e calcula o diferencial total em Reais.
- A partir do comparador, o trader pode emitir diretamente a **Boleta Formal de Compra** da proposta vencedora.

---

### Passo 6: Arbitragem Temporal e Custo de Carrego (Carry Trade)

#### 6.1 Equação do Carry Líquido
$$\text{Spread Bruto Forward} = \text{Preço Futuro} - \text{Preço Spot}$$
$$\text{Custo Total de Carrego} = \text{Custo de Capital (CDI)} + \text{Armazenagem} + \text{Quebra}$$
$$\text{Carry Líquido} = \text{Spread Bruto Forward} - \text{Custo Total de Carrego}$$

#### 6.2 Critérios de Ação da Mesa (3 Níveis de Decisão)
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

### Passo 7: Política de Transparência de Dados e Rastreabilidade (ADR-004 / W3C PROV)

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

### Passo 8: Formalização Operacional: Emissão da Boleta de Compra & Exportação Excel

Após validar os cálculos e chegar a um acordo comercial com o produtor ou corretor, o trader formaliza a operação.

#### 8.1 Emissão da Boleta Formal de Compra (Trade Ticket)
- **Acesso:** Clicar em **"Emitir Boleta"** na Calculadora de Paridade ou no Comparador de Propostas.
- **Campos Obrigatórios:** Nome/Razão Social do Vendedor, CPF/CNPJ, Fazenda de Origem, Volume em Sacas (auto-calcula toneladas), Preço Fechado R$/sc (auto-calcula Total em R$), Safra, Condições de Pagamento e Prazo de Entrega.
- **Padrão de Qualidade:** Padrão Exportação ANEC (Umidade máx 14%, Impureza máx 1%, Avariados máx 8%).
- **Numeração Auditável:** O sistema gera automaticamente um código único sequencial: `BOL-YYYYMMDD-XXXXXX`.
- **Amarração de Auditoria:** O documento grava o carimbo `DECISION_READY`, o identificador `parity_run_id` W3C PROV e as referências de CBOT, Câmbio PTAX e Frete travadas no momento exato do fechamento.
- **Ações Disponíveis:**
  - 🖨️ **Imprimir / Salvar PDF (A4):** Renderização formal com papel timbrado da trading e campos formais para assinatura.
  - 📱 **Copiar Boleta (WhatsApp):** Cópia rápida com formatação profissional pronta para envio ao produtor.
  - 💾 **Salvar no Histórico:** Armazena a boleta na base da empresa para consulta e auditoria na aba **"Minha Empresa"**.

#### 8.2 Exportação de Relatórios para Excel (.csv)
- Os botões **"Exportar Excel"** geram planilhas formatadas em UTF-8 com BOM e delimitador `;`, abrindo nativamente no Microsoft Excel ou Google Sheets sem distorção:
  - **Paridade:** Memória de cálculo completa (FOB, FAS, Frete, ANTT, Tributos e Margens).
  - **Comparador:** Quadro comparativo de todas as propostas analisadas com receitas totais do lote.
  - **Matriz de Sensibilidade:** Grade regional de praças com fretes e margens líquidas.

---

### 3. Checklist Obrigatório de Mesa: As 7 Validações Mandatórias

Antes de confirmar qualquer compra e emitir a boleta no balcão da trading, o operador deve validar rigorosamente os 7 itens abaixo:

```text
================================================================================
          CHECKLIST DE MESA: 7 VALIDAÇÕES MANDATÓRIAS ANTES DO FECHAMENTO
================================================================================
[ ] 1. STATUS DECISION_READY ATIVO
       A cotação possui origin_axis=OBSERVED e freshness_axis=CURRENT?
       (Proibido executar compras reais com dados em DEMO, UNVERIFIED ou STALE sem autorização).

[ ] 2. REGISTRO DE LINHAGEM E IDENTIFICADOR ÚNICO (W3C PROV)
       O parity_run_id foi gerado e registrado para comprovação formal de procedência e auditoria?

[ ] 3. TRAVA SIMULTÂNEA DE FUTUROS E CÂMBIO (HEDGE)
       A perna de commodity (CBOT ou B3) e o Câmbio Pronto / NDF foram travados imediatamente para eliminar risco de mercado?

[ ] 4. CONFORMIDADE COM PISO MÍNIMO ANTT (LEI Nº 13.703/2018)
       A tarifa de frete da rota foi verificada e apresenta status ABOVE_FLOOR?
       (Evitar risco de autuação e indenização em dobro por infração ao piso regulatório).

[ ] 5. JANELA PORTUÁRIA & FRETE RODOVIÁRIO CONFIRMADOS
       A transportadora confirmou o agendamento de caminhões e o prazo coincide com o line-up do navio no porto?

[ ] 6. FUNDOS TRIBUTÁRIOS ESTADUAIS & MARGEM DA TRADING
       Produtor está regular na SEFAZ, o fundo estadual (FETHAB/FUNDEINFRA/PRODEAGRO) e a margem mínima da empresa (mín. USD 2,00/t) foram garantidos?

[ ] 7. EMISSÃO E ARQUIVAMENTO DA BOLETA FORMAL (TRADE TICKET)
       A Boleta BOL-YYYYMMDD foi gerada com dados completos das partes, especificação ANEC, enviada ao vendedor e salva no histórico da empresa?
================================================================================
```
