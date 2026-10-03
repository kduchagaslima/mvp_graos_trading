# Documento de Parâmetros e Casos Financeiros de Referência (Auditoria de 02/10/2026)

**Versão da Base:** Commit `693a541897c78c6e7d60638e1bbae1b5068079f8`  
**Escopo:** Referência determinística para garantir que nenhuma refatoração ou correção de bugs mascare distorções financeiras ou altere fórmulas sem justificativa formal.

---

## 1. Parâmetros de Mercado Congelados

| Indicador / Ativo | Valor Base | Valor Auditoria | Unidade | Finalidade no Motor |
| :--- | :--- | :--- | :--- | :--- |
| **Dólar PTAX (USD/BRL)** | `5.4850` | `5.2238` | R$/USD | Conversão de FOB USD para BRL e custos portuários (THC e Demurrage) |
| **CBOT Soja (Prompt)** | `1185.25` | `1185.25` | cents/bushel | Preço de referência da commodity em Chicago |
| **CBOT Milho (Prompt)** | `435.50` | `435.50` | cents/bushel | Preço de referência de milho em Chicago |
| **Prêmio Exportação Santos (STS)** | `+90.00` | `+90.00` | cents/bushel | Prêmio FOB sobre a CBOT para embarque em Santos |
| **Prêmio Exportação Barcarena (BCR)**| `+80.00` | `+80.00` | cents/bushel | Prêmio FOB sobre a CBOT no Arco Norte |
| **Prêmio Exportação Paranaguá (PNG)**| `+85.00` | `+85.00` | cents/bushel | Prêmio FOB sobre a CBOT no Sul |

---

## 2. Tarifas Portuárias e Riscos Operacionais

| Porto | THC Elevação (USD/t) | Despesas Acessórias (R$/t) | Provisão Demurrage (USD/t) | Fila Média (Dias) |
| :--- | :--- | :--- | :--- | :--- |
| **Santos (STS)** | US$ 8,00 | R$ 15,00 | US$ 2,50 | 28 dias |
| **Barcarena (BCR)** | US$ 8,50 | R$ 14,00 | US$ 0,80 | 10 dias |
| **Paranaguá (PNG)** | US$ 7,50 | R$ 12,00 | US$ 2,00 | 24 dias |
| **Itaqui (ITQ)** | US$ 8,00 | R$ 12,00 | US$ 1,20 | 14 dias |
| **Rio Grande (RG)** | US$ 7,00 | R$ 10,00 | US$ 1,00 | 12 dias |

---

## 3. Fundos Tributários Estaduais Oficiais

* **Mato Grosso (MT) — FETHAB:**
  * Soja: **R$ 2,85 / saca**
  * Milho: **R$ 1,45 / saca**
  * Base: Lei Estadual nº 7.263/2000. Retido pelo adquirente ou pago na originação.
* **Goiás (GO) — FUNDEINFRA:**
  * Soja: **R$ 1,65 / saca**
  * Milho: **R$ 0,90 / saca**
  * Base: Lei Estadual nº 21.670/2022.
* **Bahia (BA) — PRODEAGRO:**
  * Soja: **R$ 0,60 / saca**
  * Milho: **R$ 0,35 / saca**
  * Base: Lei Estadual nº 13.208/2014.
* **Paraná (PR) & Rio Grande do Sul (RS):**
  * **Isenção / Imunidade total (R$ 0,00 / saca)** via Lei Kandir (LC 87/1996).

---

## 4. Fatores de Conversão Físico-Financeiros Invariantes

* **Soja:** 60 lbs/bu $\rightarrow$ 27,2155 kg/bu $\rightarrow$ **36,7437 bu/tonelada métrica**.  
  Fator de conversão: $\text{cents/bu} \times 0.367437 = \text{USD/ton}$.
* **Milho:** 56 lbs/bu $\rightarrow$ 25,4012 kg/bu $\rightarrow$ **39,3683 bu/tonelada métrica**.  
  Fator de conversão: $\text{cents/bu} \times 0.393683 = \text{USD/ton}$.
* **Equivalência Saca / Tonelada:** 1 tonelada métrica = 1.000 kg = 16,6667 sacas de 60 kg ($\times 0.06$).

---

## 5. Casos de Teste Chave e Comportamentos Esperados

1. **Sensibilidade Cambial na Paridade FAS:**
   * A queda de PTAX de 5.4850 para 5.2238 não afeta o preço FOB em USD, mas reduz diretamente o FOB BRL e o FAS Interior em BRL/saca na mesma proporção.
2. **Arbitragem Sorriso ➔ Barcarena vs. Santos:**
   * Sorriso ➔ Santos: Frete R$ 420,00/t + THC/Porto/Demurrage.
   * Sorriso ➔ Barcarena: Frete R$ 360,00/t + THC/Porto/Demurrage (demurrage reduzido de US$ 0.80 vs US$ 2.50).
   * **Economia Logística:** Barcarena apresenta economia de $> \text{R\$} 60,00/\text{ton}$ ($> \text{R\$} 3,60/\text{saca}$) e é categorizada como `FAVORABLE` e `Melhor Rota`.
3. **Zona Neutra de Custo de Carrego:**
   * Com tolerância de R$ 0,75/sc, quando o spread líquido fica entre -R$ 0,75 e +R$ 0,75, o status deve ser rigorosamente `NEUTRO / INDIFERENTE` em todos os componentes.
