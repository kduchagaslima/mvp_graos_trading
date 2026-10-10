# Política de Transparência de Dados — AgriTrading / Fluxo de Paridade

**Identificador:** GRAOS-007-PESQUISA  
**Revisão:** proposta revisada  
**Data:** 10/10/2026  
**Status:** pronta para decisão de produto e implementação; não validada contra o código, schema real ou dashboard Streamlit.

Esta política define como o AgriTrading deve apresentar a origem, a atualidade, a transformação e as limitações dos dados usados no cálculo de paridade. Ela combina:

- os dois eixos de rastreabilidade do ADR-004;
- a tabela `MARKET_QUOTES`;
- a proveniência do W3C PROV;
- os requisitos de transparência, qualidade, segurança e direitos da LGPD;
- as boas práticas voluntárias do Ag Data Transparent.

A política não constitui parecer jurídico, certificação Ag Data Transparent ou comprovação de conformidade da implementação.

## 1. Base factual e limites da revisão

### Fatos fornecidos pelo briefing arquitetural

O fluxo de cálculo informado é:

1. CBOT em cents/bu;
2. conversão para FOB Porto em USD/ton;
3. conversão para R$/saca por meio da PTAX;
4. dedução de custos portuários, chegando ao FAS;
5. dedução de frete, margem, fundos, quebra e Funrural;
6. resultado no Preço Balcão Interior.

O ADR-004 estabelece dois eixos independentes:

- **Eixo Origem:** `OBSERVED`, `MANUAL`, `ESTIMATED`, `DEMO`, `UNVERIFIED`;
- **Eixo Atualidade:** `CURRENT`, `STALE`, `UNKNOWN`.

A tabela `MARKET_QUOTES` deve registrar os inputs com timestamp UTC, fonte e unidade estrita. As fontes informadas são `BCB_PTAX`, `CME` e `CEPEA`. O usuário final consulta o resultado no Dashboard em Streamlit.

Esses fatos foram recebidos do orquestrador. Não houve acesso a arquivos locais, bridge, checkout, schema físico ou implementação do dashboard.

### Fatos normativos pesquisados

A LGPD define transparência como a garantia de informações claras, precisas e facilmente acessíveis sobre o tratamento e os agentes responsáveis. Também exige atenção a finalidade, adequação, necessidade, livre acesso, qualidade dos dados, segurança, prevenção, não discriminação e responsabilização. [1]

A LGPD exige que o titular receba informações sobre finalidade, forma e duração do tratamento, controlador, contato, compartilhamento, responsabilidades e direitos. Ela também prevê direitos de acesso, correção, anonimização, bloqueio, eliminação, portabilidade, informação sobre compartilhamentos e revogação de consentimento. [1]

O W3C PROV modela a proveniência por meio de **entidades**, **atividades** e **agentes**, além das relações de uso, geração, derivação, atribuição e associação. O modelo é adequado para registrar que um resultado foi derivado de determinadas cotações por uma atividade de cálculo executada por um sistema ou operador. [2] [3]

O PROV-O fornece classes e propriedades interoperáveis, como `prov:Entity`, `prov:Activity`, `prov:Agent`, `prov:used`, `prov:wasGeneratedBy`, `prov:wasDerivedFrom` e `prov:wasAssociatedWith`. [4]

O Ag Data Transparent é um conjunto voluntário de princípios voltado à transparência de contratos e práticas de provedores de tecnologia agrícola. A versão publicada informa que os princípios foram atualizados em 2024. O framework recomenda clareza sobre categorias coletadas, finalidade, escolhas do produtor, parceiros, portabilidade, retenção, exclusão, anonimização, segurança e uso em treinamento de modelos de IA. [5]

As 11 perguntas de certificação do Ag Data Transparent cobrem, entre outros pontos, identidade do provedor, categorias de dados, controle, opt-out de agregação, contratados, compartilhamento, venda, recuperação, exclusão, incidentes, mudanças contratuais e aquisição do provedor. [6]

## 2. Princípio central

> Nenhum valor usado ou exibido como decisão de mercado pode aparecer sem identificação de origem, atualidade, unidade, timestamp, fonte e cadeia de derivação.

Transparência, neste produto, não significa apenas disponibilizar uma política de privacidade. Significa permitir que o Trader ou Analista responda, para cada resultado:

1. **Que valor foi usado?**
2. **De onde ele veio?**
3. **Quando foi observado e quando foi ingerido?**
4. **Qual é a unidade?**
5. **Ele foi observado, digitado, estimado, demonstrativo ou não verificado?**
6. **Ele está atual, obsoleto ou sem atualidade conhecida?**
7. **Quais etapas transformaram o input no resultado?**
8. **Qual versão da fórmula e dos parâmetros foi utilizada?**
9. **Quem ou qual sistema foi responsável pelo registro ou cálculo?**
10. **O resultado está apto para decisão ou deve ser tratado apenas como referência?**

## 3. Escopo da política

A política se aplica a:

- cotações de CBOT;
- PTAX;
- valores de FOB Porto;
- custos portuários e FAS;
- frete;
- margem;
- FETHAB;
- FUNDEINFRA;
- quebra;
- Funrural;
- demais parâmetros, ajustes e inputs usados no cálculo;
- resultados intermediários e resultado final de paridade;
- registros de usuário, operador, revisão, correção e acesso que possam conter dados pessoais.

A tabela `MARKET_QUOTES` deve ser entendida como o repositório de evidência dos inputs. Se custos ou parâmetros não puderem ser armazenados nessa tabela sem comprometer sua semântica de “cotação”, deve existir uma tabela de inputs correlata. A política não permite que um input seja omitido da rastreabilidade apenas por não ser uma cotação de mercado.

## 4. Eixo Origem

O campo `origin_axis` é obrigatório para cada input, resultado intermediário e resultado final.

### `OBSERVED`

Use `OBSERVED` somente quando o valor foi obtido de uma fonte declarada, com evidência suficiente para identificar:

- fonte;
- instrumento ou parâmetro;
- unidade;
- timestamp de observação em UTC;
- referência do registro ou payload de origem;
- momento de ingestão no sistema.

`OBSERVED` descreve a forma de origem. Não significa, sozinho, que o valor esteja correto, atual ou adequado ao cálculo.

Uma cotação transcrita manualmente de um terminal ou documento não deve ser classificada como `OBSERVED` apenas porque originalmente veio de uma fonte oficial. Nesse caso, a origem operacional é `MANUAL`, e a fonte original deve ser registrada separadamente.

### `MANUAL`

Use `MANUAL` quando o valor foi inserido, corrigido ou confirmado por uma pessoa ou operador.

O registro manual deve conter:

- identificador pseudonimizado do operador;
- papel ou perfil autorizado;
- data e hora UTC;
- justificativa;
- referência documental, contratual ou operacional, quando existir;
- prazo de validade ou política de atualização;
- valor anterior, quando a ação for uma correção;
- indicação de que o registro substitui ou complementa outro.

O dashboard não deve apresentar um valor manual como se tivesse sido capturado automaticamente da BCB, CME ou CEPEA.

### `ESTIMATED`

Use `ESTIMATED` para:

- previsão;
- aproximação;
- interpolação;
- cenário;
- valor calculado a partir de premissa;
- parâmetro assumido;
- fallback autorizado que não representa uma observação direta.

Um resultado calculado por fórmula não deve ser marcado como `OBSERVED` apenas porque todos os seus inputs eram observados. O resultado é derivado. Quando houver estimativa em qualquer input necessário, o resultado deve conservar essa informação.

### `DEMO`

Use `DEMO` somente para dados sintéticos, fixtures, exemplos, testes ou simulações.

Dados `DEMO`:

- devem ser claramente marcados no armazenamento e na interface;
- não podem ser misturados silenciosamente com dados produtivos;
- não podem ser usados para formar um resultado apresentado como decisão real;
- devem fazer o resultado final herdar o status `DEMO`.

### `UNVERIFIED`

Use `UNVERIFIED` quando não for possível verificar a origem ou a integridade mínima do valor, incluindo:

- fonte ausente ou não reconhecida;
- unidade ausente ou inválida;
- timestamp ausente, ambíguo ou não convertido para UTC;
- referência de origem indisponível;
- payload inconsistente;
- valor recebido por mecanismo não auditado;
- registro cuja origem foi contestada.

`UNVERIFIED` não é sinônimo de “zero”, “não informado” ou “provavelmente correto”. É uma indicação explícita de que a evidência não é suficiente.

## 5. Eixo Atualidade

O campo `freshness_axis` também é obrigatório.

### `CURRENT`

Um valor pode ser classificado como `CURRENT` somente quando:

- existe timestamp de observação em UTC;
- existe uma política de atualidade aplicável à fonte e ao instrumento;
- o valor está dentro do prazo de validade definido por essa política;
- a avaliação foi executada em um momento conhecido;
O prazo de atualidade (`freshness_policy_id`) adotado para o AgriTrading é dinâmico, respeitando a natureza da fonte:
- **CBOT/CME:** 20 minutos durante o pregão. Após o fechamento, o último valor permanece válido até a próxima abertura.
- **PTAX:** Válido até o horário do próximo boletim do BCB.
- **CEPEA:** Válido por 24 horas úteis (ou até a consolidação do próximo dia).
- **Custos/Frete/Tributos:** Validação estendida (semanal, mensal ou anual, dependendo do parâmetro).

### `STALE`

Use `STALE` quando:

- existe timestamp válido;
- existe uma política de atualidade;
- o prazo de validade foi ultrapassado; ou
- a fonte indicou que o valor deixou de ser atual.

`STALE` não significa necessariamente que o valor esteja incorreto. Significa que ele não deve ser tratado como a observação mais recente disponível.

### `UNKNOWN`

Use `UNKNOWN` quando:

- o timestamp está ausente ou inválido;
- não existe política de atualidade;
- a fonte não permite avaliar a validade;
- houve falha na avaliação;
- o valor tem origem não verificada e não há evidência temporal confiável.

A aplicação não pode converter a ausência de informação temporal em `CURRENT`.

## 6. Separação obrigatória entre origem e atualidade

Os eixos não podem ser fundidos em um único campo ou em uma única cor.

Exemplos válidos:

- `OBSERVED + CURRENT`: valor observado e dentro da política de atualidade;
- `OBSERVED + STALE`: valor observado, mas antigo;
- `MANUAL + CURRENT`: valor digitado manualmente e ainda dentro da validade definida;
- `ESTIMATED + CURRENT`: estimativa calculada recentemente;
- `UNVERIFIED + UNKNOWN`: valor sem evidência suficiente e sem atualidade avaliável;
- `DEMO + CURRENT`: dado sintético gerado recentemente, ainda assim inadequado para decisão produtiva.

O dashboard deve exibir os dois eixos em texto. Cores podem complementar a informação, mas não podem ser o único mecanismo de comunicação, por razões de acessibilidade e precisão.

## 7. Contrato mínimo para `MARKET_QUOTES`

Cada registro deve possuir, no mínimo:

- `quote_id` imutável;
- identificador do instrumento, produto ou parâmetro;
- `value`;
- `unit`;
- `source`;
- `observed_at_utc`;
- `ingested_at_utc`;
- `origin_axis`;
- `freshness_axis`;
- `freshness_policy_id`;
- `freshness_evaluated_at_utc`;
- referência do registro de origem;
- status de validação;
- motivo de exceção, quando aplicável;
- identificador do registro que foi substituído, quando aplicável;
- versão do registro ou mecanismo de correção.

Recomenda-se também armazenar:

- hash ou referência do payload bruto;
- versão do conector ou adaptador;
- data de publicação da fonte, quando disponível;
- `source_access_mode`, para distinguir captura automática, transcrição manual e importação;
- identificador do agente responsável;
- indicador de que o registro contém ou não dados pessoais.

### Fonte e modo de captura

`source` deve identificar a fonte real. Para fontes de mercado, os valores canônicos informados são:

- `BCB_PTAX`;
- `CME`;
- `CEPEA`.

Um registro manual não deve usar `CME` ou `CEPEA` como se tivesse sido capturado automaticamente. Se o operador transcrever uma cotação da CME, o registro pode manter a referência à CME como fonte original, mas deve possuir um modo de captura explícito, como `MANUAL`, além de `origin_axis=MANUAL`.

Caso o schema atual só permita os nomes das fontes de mercado, recomenda-se adicionar `source_access_mode` em vez de inserir um valor artificial ou ocultar a natureza manual do registro.

### Unidades

A unidade deve ser validada antes de o valor entrar no cálculo. Exemplos do fluxo informado:

- CBOT: cents/bu;
- FOB Porto: USD/ton;
- PTAX: BRL/USD;
- preço final: R$/saca.

Conversões devem registrar:

- unidade de entrada;
- unidade de saída;
- fator ou fórmula;
- versão da regra;
- inputs utilizados;
- arredondamento, quando houver.

Não é permitido usar um valor numérico sem unidade ou inferir a unidade pela posição do campo.

## 8. Proveniência W3C PROV aplicada ao cálculo

A implementação deve representar, conceitualmente, o fluxo da seguinte maneira:

- cada cotação ou parâmetro é uma `prov:Entity`;
- cada resultado intermediário é uma nova `prov:Entity`;
- cada execução do cálculo é uma `prov:Activity`;
- BCB, CME, CEPEA, o sistema e operadores autorizados são `prov:Agent`;
- o cálculo `prov:used` os inputs;
- o cálculo `prov:generated` os resultados;
- o resultado `prov:wasDerivedFrom` os inputs e intermediários;
- o cálculo `prov:wasAssociatedWith` o sistema ou operador responsável;
- cada entidade pode registrar sua atribuição e seus timestamps.

A cadeia mínima deve permitir reconstruir:

```text
CBOT + PTAX
  -> FOB Porto
  -> R$/saca
  -> FAS
  -> deduções de frete, margem, fundos, quebra e Funrural
  -> Preço Balcão Interior
```

O modelo PROV não substitui a política de qualidade. Ele registra a proveniência. A classificação `CURRENT`, `STALE` ou `UNKNOWN` é uma regra específica do ADR-004 e do produto.

## 9. Propagação dos eixos para resultados derivados

A aplicação deve conservar todos os estados dos inputs, mas também produzir um estado resumido para cada resultado.

### Propagação do Eixo Origem

Para o `origin_axis` principal do resultado, aplicar a seguinte precedência:

```text
DEMO > UNVERIFIED > ESTIMATED > MANUAL > OBSERVED
```

A razão completa também deve ser armazenada. Assim:

- qualquer input `DEMO` torna o resultado `DEMO`;
- na ausência de `DEMO`, qualquer input `UNVERIFIED` torna o resultado `UNVERIFIED`;
- na ausência dos anteriores, qualquer `ESTIMATED` torna o resultado `ESTIMATED`;
- na ausência dos anteriores, qualquer `MANUAL` torna o resultado `MANUAL`;
- somente inputs observados permitem resultado com origem principal `OBSERVED`.

Essa precedência é uma decisão de produto para evitar que um resultado derivado pareça mais confiável que seu input menos rastreável. Ela não é uma regra do W3C PROV.

### Propagação do Eixo Atualidade

Para `freshness_axis`, aplicar:

```text
UNKNOWN > STALE > CURRENT
```

Assim:

- qualquer input necessário com atualidade `UNKNOWN` torna o resultado `UNKNOWN`;
- caso não haja `UNKNOWN`, qualquer input necessário `STALE` torna o resultado `STALE`;
- somente inputs necessários `CURRENT`, com cálculo avaliado dentro das regras aplicáveis, permitem resultado `CURRENT`.

O resultado nunca pode ser considerado mais atual que o input necessário mais antigo ou menos atual.

### Prontidão para decisão

Recomenda-se um indicador derivado separado, sem substituir os dois eixos:

```text
DECISION_READY = origin_axis == OBSERVED
                 e freshness_axis == CURRENT
                 e todas as validações técnicas aprovadas
```

`MANUAL`, `ESTIMATED`, `DEMO`, `UNVERIFIED`, `STALE` e `UNKNOWN` devem produzir `DECISION_READY=false`, salvo se uma política de negócio aprovada autorizar explicitamente determinado uso. Mesmo nesse caso, os eixos originais devem continuar visíveis.

## 10. Regras de cálculo e bloqueio

### Bloqueio obrigatório

O cálculo produtivo deve falhar de forma explícita quando um input necessário for:

- `DEMO`;
- `UNVERIFIED`;
- `UNKNOWN`;
- inválido quanto à unidade;
- sem timestamp exigido;
- sem referência de fonte;
- incompatível com a fórmula ou com a versão do instrumento.

A falha deve indicar qual input causou o bloqueio. Não deve haver substituição silenciosa por zero, valor aleatório, último valor desconhecido ou valor de demonstração.

### Dados obsoletos

Por padrão, dados `STALE` não devem gerar um novo resultado `DECISION_READY`.

Caso o produto permita cálculo com dados obsoletos, deve haver:

- ação explícita do usuário;
- aviso visível antes da execução;
- justificativa ou motivo;
- resultado marcado como `STALE`;
- registro de que o cálculo foi executado com exceção;
- indicação de todos os inputs obsoletos.

O uso de `STALE` não pode ser decidido somente pelo frontend. A validação deve ocorrer no serviço ou camada de domínio que executa o cálculo.

### Inputs manuais e estimados

`MANUAL` e `ESTIMATED` podem ser usados em cenários de simulação ou análise, desde que:

- o usuário veja a classificação antes de usar o resultado;
- o resultado herde a classificação;
- a fórmula e os parâmetros sejam identificados;
- o resultado não seja rotulado como cotação observada;
- o uso seja auditado.

## 11. Transparência no Dashboard Streamlit

Cada cartão, gráfico ou linha que apresentar um valor de paridade deve mostrar, em texto ou em uma expansão acessível:

- valor;
- unidade;
- fonte;
- timestamp de observação em UTC;
- timestamp de ingestão em UTC, quando relevante;
- `origin_axis`;
- `freshness_axis`;
- indicador `DECISION_READY`;
- fórmula ou versão do cálculo;
- identificador do cálculo;
- inputs utilizados;
- motivo de exceção, se houver.

O usuário deve conseguir abrir “Detalhes da origem” ou ação equivalente para percorrer a cadeia de cálculo. A interface não precisa expor credenciais, dados pessoais ou payloads sujeitos a restrição contratual, mas deve apresentar evidência suficiente para auditoria, como:

- nome da fonte;
- referência do registro;
- timestamp;
- hash ou identificador técnico;
- versão do conector;
- motivo de indisponibilidade do conteúdo bruto.

Exemplos de mensagens obrigatórias:

- **“OBSERVED — CURRENT. Fonte: CME. Observado em UTC: [timestamp].”**
- **“MANUAL — CURRENT. Valor informado por operador autorizado em [timestamp].”**
- **“STALE. A última observação ultrapassou a política de atualidade [policy_id].”**
- **“UNVERIFIED — não utilizado em cálculo produtivo. Motivo: unidade ausente.”**
- **“DEMO — resultado sintético. Não representa preço de mercado.”**

O sistema não deve exibir apenas “atualizado” sem informar o timestamp e a regra que determinou a atualidade.

## 12. Aplicação da LGPD

### Classificação

A LGPD protege dados relacionados a pessoa natural identificada ou identificável. Uma cotação de mercado isolada pode não ser dado pessoal. Porém, o sistema pode tratar dados pessoais quando associar informações a:

- usuário ou operador;
- produtor individual;
- atividade de uma pessoa natural;
- localização de propriedade identificável;
- dados financeiros ou gerenciais de uma pessoa natural;
- histórico de ações, correções e acessos;
- contratos ou documentos vinculados a uma pessoa.

A classificação deve ser realizada por um inventário de dados. Não se deve concluir que todo o conteúdo de `MARKET_QUOTES` está fora da LGPD apenas porque contém preços de mercado.

### Aviso de privacidade e transparência

O aviso de privacidade deve informar, em linguagem clara:

- quem é o controlador;
- quem atua como operador;
- finalidades do tratamento;
- categorias de dados tratados;
- fontes e formas de coleta;
- base legal aplicável;
- uso compartilhado;
- fornecedores ou parceiros com acesso;
- prazo ou critério de retenção;
- medidas de segurança;
- canal de contato;
- direitos do titular;
- procedimento para acesso, correção, oposição, eliminação ou portabilidade, quando aplicável.

**Definições Oficiais (Aprovadas pelo Produto):**
- **Controlador:** A empresa dona/gestora da plataforma AgriTrading.
- **Operador:** Parceiros de infraestrutura em nuvem e fornecedores de APIs de dados de mercado.
- **Base Legal (Auditoria/Proveniência):** Legítimo Interesse (Art. 7º, IX) para manter segurança e rastreabilidade contra fraudes.
- **Prazo de Retenção:** 5 anos para logs de proveniência contendo identificadores de operadores, sendo anonimizados após este período.

### Minimização

O sistema deve evitar armazenar nome, e-mail ou outros identificadores pessoais no registro público da cotação quando um identificador pseudonimizado de operador for suficiente.

A trilha técnica deve conservar a responsabilização necessária, mas o dashboard não deve exibir a identidade pessoal do operador para usuários que não tenham autorização.

### Correção e eliminação

Cotações e resultados não devem ser sobrescritos silenciosamente. A correção deve criar uma nova versão que:

- referencia o registro anterior;
- registra o motivo;
- identifica o agente responsável;
- preserva a cadeia de derivação;
- invalida ou substitui o resultado afetado.

A exclusão de dados pessoais deve ser tratada separadamente da preservação de uma trilha técnica não pessoal. A solução precisa definir quais registros devem ser eliminados, anonimizados ou retidos por obrigação legal, contratual ou de auditoria.

### Decisões automatizadas

O cálculo de paridade, isoladamente, é uma transformação determinística. Se o produto apenas apresenta o preço, isso não prova que exista uma decisão automatizada sujeita ao art. 20 da LGPD.

Se o sistema passar a classificar, aprovar, bloquear, ranquear ou recomendar uma ação que afete interesses de uma pessoa com base exclusivamente em tratamento automatizado, deverá informar critérios e procedimentos aplicáveis e oferecer o mecanismo de revisão previsto na LGPD. [1]

## 13. Integração com o Ag Data Transparent

O Ag Data Transparent deve ser usado como referência de desenho de transparência agrícola, não como substituto da LGPD brasileira.

A política deve incorporar os seguintes compromissos:

### Clareza

As explicações devem usar linguagem simples. A política de uso de dados, o aviso de privacidade e as informações de origem das cotações devem ser coerentes entre si.

### Finalidade

O sistema deve declarar que os dados são usados para:

- calcular e analisar paridade;
- apresentar indicadores de mercado;
- manter auditoria e qualidade;
- corrigir resultados;
- operar e proteger a plataforma.

Qualquer uso secundário precisa ser descrito separadamente.

### Escolhas do usuário

O produto deve explicar as consequências de:

- incluir ou não dados operacionais;
- permitir acesso a parceiros;
- participar de conjuntos agregados;
- interromper a coleta;
- encerrar o serviço.

Quando a escolha for tecnicamente possível, o usuário deve poder optar por uma finalidade sem ser obrigado a aceitar todas as demais.

### Parceiros

A política deve identificar as categorias de terceiros que podem acessar dados:

- parceiros de integração;
- fornecedores de infraestrutura;
- parceiros comerciais;
- afiliadas;
- consultores ou assessores autorizados.

Não é suficiente dizer “terceiros”. A categoria, finalidade e tipo de acesso precisam ser explicados.

### Agregação e anonimização

Se dados de produtores ou operações forem agregados para análises, a política deve explicar:

- quais categorias entram na agregação;
- se o usuário pode optar por não participar;
- se dados individuais são preservados;
- como se evita reidentificação;
- quais dados permanecem disponíveis para o próprio usuário.

Dados agregados não devem ser chamados de anônimos sem avaliação técnica de risco de reidentificação.

### IA e modelos

**Aviso sobre Modelos e Analytics (Aprovado pelo Produto):**
O AgriTrading agregará os dados de cotações locais da plataforma para fins futuros de treinamento de modelos de Machine Learning (IA) e Analytics.
- Todos os dados passarão por um processo rigoroso de anonimização antes da etapa de treinamento para impedir reidentificação.
- Os usuários (Traders/Analistas) serão devidamente notificados através da Política de Privacidade e dos Termos de Uso atualizados sobre essas finalidades.

### Retenção, exclusão e encerramento

A política deve informar:

- por quanto tempo os dados de mercado, resultados e trilhas são retidos;
- quais registros podem ser corrigidos;
- quais dados podem ser eliminados;
- o que acontece após encerramento do serviço;
- quais obrigações justificam retenção posterior;
- como o usuário recebe uma cópia utilizável de seus dados.

O prazo efetivo de retenção ainda não foi fornecido e precisa ser definido pelo responsável de produto, jurídico e segurança.

## 14. Decisões recomendadas

### D-01 — Manter dois eixos independentes

**Decisão:** origem e atualidade devem permanecer como campos independentes e sempre visíveis.

**Justificativa:** um valor pode ser observado, mas obsoleto; ou manual, mas ainda válido para uma simulação. Um único rótulo não representa essas diferenças.

### D-02 — Bloquear dados não verificados na produção

**Decisão:** `UNVERIFIED` e `DEMO` não entram em cálculo produtivo.

**Justificativa:** o ADR-004 proíbe dados aleatórios, e a classificação explícita não seria suficiente se o sistema ainda permitisse apresentar esses dados como preço operacional.

### D-03 — Propagar o pior estado para o resultado

**Decisão:** o resultado deve herdar a origem menos confiável e a atualidade menos favorável entre os inputs necessários.

**Justificativa:** o usuário deve perceber que um resultado derivado não pode ter aparência de maior qualidade que a evidência que o sustenta.

### D-04 — Usar PROV para explicar o cálculo

**Decisão:** registrar entidades, atividades e agentes, mesmo que a interface inicial apresente apenas uma visualização simplificada.

**Justificativa:** a rastreabilidade do resultado depende da relação entre os inputs, as etapas de transformação e a versão da fórmula. [2] [3] [4]

### D-05 — Tratar ADT como referência voluntária

**Decisão:** adotar os princípios de clareza, escolha, portabilidade, parceiros, retenção e segurança, sem afirmar certificação ou equivalência jurídica.

**Justificativa:** o Ag Data Transparent é uma iniciativa voluntária e orientada a provedores e contratos de dados agrícolas. [5] [6]

### D-06 — Não esconder dados manuais

**Decisão:** um valor manual pode ser aceito em simulações, mas jamais pode parecer captura automática de BCB, CME ou CEPEA.

**Justificativa:** esconder o modo de captura compromete a confiança e a capacidade de auditoria.

## 15. Critérios de aceite verificáveis

### CA-01 — Campos obrigatórios

**Dado** um input de mercado ou parâmetro necessário para o cálculo,  
**quando** ele for persistido,  
**então** deve possuir `value`, `unit`, `source`, `observed_at_utc`, `ingested_at_utc`, `origin_axis`, `freshness_axis` e identificador imutável.

### CA-02 — Validação de unidade

**Dado** um input sem unidade, com unidade desconhecida ou incompatível,  
**quando** o sistema tentar ingerir ou calcular,  
**então** o input deve ser rejeitado ou classificado como `UNVERIFIED` e não pode participar de cálculo produtivo.

### CA-03 — Ausência de timestamp

**Dado** um input sem timestamp UTC válido,  
**quando** a atualidade for avaliada,  
**então** seu `freshness_axis` deve ser `UNKNOWN`, nunca `CURRENT`.

### CA-04 — Captura manual

**Dado** um valor digitado por operador,  
**quando** ele for salvo,  
**então** deve possuir `origin_axis=MANUAL`, operador pseudonimizado, timestamp UTC, justificativa e referência de origem, se houver.

### CA-05 — Dado demonstrativo

**Dado** um input `DEMO`,  
**quando** o sistema executar um cálculo em ambiente produtivo,  
**então** o cálculo deve ser bloqueado ou explicitamente separado do fluxo produtivo; nunca deve ser apresentado como preço real.

### CA-06 — Dado não verificado

**Dado** um input `UNVERIFIED`,  
**quando** ele for requerido pelo cálculo,  
**então** a execução produtiva deve falhar com o motivo e listar o input que causou o bloqueio.

### CA-07 — Propagação de origem

**Dado** um cálculo com pelo menos um input `MANUAL`, sem inputs `DEMO`, `UNVERIFIED` ou `ESTIMATED`,  
**quando** o resultado for gerado,  
**então** o resultado deve possuir `origin_axis=MANUAL`.

### CA-08 — Propagação de atualidade

**Dado** um cálculo com pelo menos um input necessário `STALE` e nenhum `UNKNOWN`,  
**quando** o resultado for gerado,  
**então** o resultado deve possuir `freshness_axis=STALE` e não pode ser marcado como `DECISION_READY`.

### CA-09 — Proveniência completa

**Dado** um resultado final de paridade,  
**quando** o usuário abrir seus detalhes,  
**então** deve ser possível identificar todos os inputs, cada etapa de cálculo, a versão da fórmula, os parâmetros, o timestamp e o agente ou sistema associado.

### CA-10 — Unidade no dashboard

**Dado** qualquer valor exibido no dashboard,  
**quando** o usuário visualizar o cartão ou gráfico,  
**então** a unidade deve estar visível junto do valor, sem depender de tooltip ou memória do usuário.

### CA-11 — Exibição dos dois eixos

**Dado** um valor exibido no dashboard,  
**quando** a interface for renderizada,  
**então** `origin_axis` e `freshness_axis` devem aparecer em texto acessível, e não apenas por cor ou ícone.

### CA-12 — Correção sem sobrescrita

**Dado** um input já utilizado em um cálculo,  
**quando** ele for corrigido,  
**então** o sistema deve criar uma nova versão, preservar a referência ao registro anterior e permitir identificar quais resultados foram afetados.

### CA-13 — Reprodutibilidade

**Dado** um `parity_run_id`,  
**quando** um auditor ou usuário autorizado solicitar seus detalhes,  
**então** o sistema deve retornar os mesmos inputs, versão de fórmula e parâmetros utilizados naquela execução, observadas as regras de proteção de dados.

### CA-14 — Privacidade

**Dado** um registro de operador ou usuário associado a um input,  
**quando** um usuário sem permissão acessar o dashboard,  
**então** o sistema não deve expor nome, e-mail ou identificador pessoal desnecessário.

### CA-15 — Uso de dados obsoletos

**Dado** que uma política permita cálculo excepcional com input `STALE`,  
**quando** o usuário executar o cálculo,  
**então** deve haver ação explícita, aviso, registro da exceção e resultado marcado como `STALE`.

### CA-16 — Mudança de política

**Dado** que a política de atualização, compartilhamento, retenção ou uso de dados seja alterada,  
**quando** a alteração for publicada,  
**então** o usuário deve receber um resumo das mudanças e a data de vigência. Mudanças que alterem finalidade ou base de tratamento devem ser encaminhadas para a avaliação jurídica apropriada.

## 16. Recomendações para implementação

1. Criar um registro central de enumerações para `origin_axis`, `freshness_axis`, unidades, fontes e motivos de validação. O frontend não deve definir esses valores livremente.

2. Criar uma camada única de validação de qualidade antes do cálculo. Essa camada deve verificar timestamp, unidade, fonte, referência, duplicidade, política de atualidade e consistência do instrumento.

3. Separar o valor observado do estado calculado. O campo de origem do input não deve ser sobrescrito pelo status do resultado.

4. **Tabela Satélite de Lineage (Aprovado pelo Produto):** Implementar uma estrutura de lineage em uma tabela satélite dedicada (ex: `MARKET_QUOTES_LINEAGE`), preservando a `MARKET_QUOTES` principal sem sobrecarga. Esta tabela satélite relacionará `quote_id`, inputs de custo, resultados intermediários, `parity_run_id`, `formula_version` e `parameter_version`.

5. Implementar a avaliação de atualidade por política configurável por fonte e instrumento. Não usar um prazo único hardcoded para CBOT, PTAX, custos e tributos.

6. Implementar o bloqueio de produção no backend ou serviço de cálculo. Um filtro visual no Streamlit não é suficiente.

7. Criar testes automatizados para a matriz de propagação:

   - `OBSERVED + CURRENT`;
   - `OBSERVED + STALE`;
   - `MANUAL + CURRENT`;
   - `ESTIMATED + CURRENT`;
   - `UNVERIFIED + UNKNOWN`;
   - `DEMO + CURRENT`;
   - combinação com mais de um input em estados diferentes.

8. Criar uma visualização detalhada de proveniência no Streamlit. O resumo pode ser simples, mas deve existir uma forma de percorrer todos os inputs e etapas.

9. Manter os dados pessoais de operador em uma estrutura separada ou pseudonimizada. A trilha de auditoria deve preservar responsabilização sem expor identidade além do necessário.

10. Definir com jurídico, segurança e produto o controlador, as bases legais, os prazos de retenção, os canais de atendimento e as regras de exclusão antes de publicar a política externa.

## 17. Riscos e mitigação

### Falsa indicação de atualidade

Um TTL global pode marcar como atual um dado que tem ciclo diferente de atualização.

**Mitigação:** política por fonte, instrumento e parâmetro, com `freshness_policy_id` visível na evidência técnica.

### Confusão entre fonte e modo de captura

Uma transcrição manual pode ser confundida com integração automática da fonte original.

**Mitigação:** separar `source` de `source_access_mode` e tornar `MANUAL` obrigatório para digitação ou transcrição.

### Resultado com aparência mais confiável que os inputs

Um resultado numérico pode parecer preciso mesmo quando contém estimativa ou dado obsoleto.

**Mitigação:** propagação obrigatória dos eixos, indicador `DECISION_READY` e bloqueio de produção para `DEMO` e `UNVERIFIED`.

### Vazamento de dados pessoais na proveniência

A trilha pode registrar nomes, e-mails ou identificadores de operadores e produtores.

**Mitigação:** pseudonimização, controle de acesso, minimização e separação entre evidência pública e trilha restrita.

### Alteração da fórmula sem reprodutibilidade

Atualizar a fórmula sem versionar o cálculo pode tornar resultados históricos impossíveis de explicar.

**Mitigação:** `formula_version`, `parameter_version`, `parity_run_id` e preservação das relações de derivação.

### Dependência de fontes externas

CME, BCB e CEPEA podem ter restrições de acesso, licenciamento, latência ou formatos diferentes.

**Mitigação:** registrar referência e modo de captura, monitorar falhas, não fabricar fallback e definir previamente o comportamento para indisponibilidade.

### Reidentificação por agregação

Dados agrícolas agregados podem continuar permitindo inferir uma fazenda ou produtor em grupos pequenos.

**Mitigação:** avaliação de reidentificação, limiares mínimos de agregação, opt-out quando aplicável e revisão de qualquer alegação de anonimização.

### Interpretação excessiva do Ag Data Transparent

Adotar seus princípios não significa obter certificação, cumprir a LGPD ou resolver questões de titularidade contratual.

**Mitigação:** apresentar o framework como referência voluntária de desenho e manter análise jurídica brasileira separada.

## 18. Hipóteses e pendências que impedem declarar a implementação concluída
 
1. Não foi confirmado se todos os custos e parâmetros do cálculo estão registrados na mesma tabela ou em estruturas relacionadas.

2. Não foi confirmado o catálogo oficial de unidades nem o comportamento de arredondamento.

3. Não foi validado se o fluxo atual armazena payload bruto, referência de origem, hash, versão de conector ou somente o valor final.

4. Não foi confirmado se o dashboard já exibe origem, atualidade, timestamp, unidade e cadeia de cálculo.

5. Não foi realizado teste de integração, teste de aceitação, revisão de segurança ou validação jurídica.

## 19. Resultado da revisão

A política revisada recomenda que a transparência seja implementada como um contrato de dados verificável:

- `MARKET_QUOTES` fornece a evidência dos inputs;
- o ADR-004 classifica origem e atualidade;
- o W3C PROV registra entidades, atividades, agentes e derivações;
- a LGPD orienta finalidade, acesso, correção, segurança, minimização e direitos;
- o Ag Data Transparent orienta clareza, escolha, portabilidade, parceiros, retenção, agregação e comunicação de mudanças.

A principal mudança em relação a uma política genérica de transparência é tornar impossível que o usuário veja somente o número final. Cada resultado deve carregar sua origem, atualidade, unidade, versão, inputs e limitações. Sem esses elementos, o sistema não deve declarar o resultado como pronto para decisão.

## Referências

[1]: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm "Lei nº 13.709/2018 — Lei Geral de Proteção de Dados Pessoais (texto compilado)"

[2]: https://www.w3.org/TR/prov-overview/ "PROV-Overview — An Overview of the PROV Family of Documents"

[3]: https://www.w3.org/TR/prov-dm/ "PROV-DM: The PROV Data Model"

[4]: https://www.w3.org/TR/prov-o/ "PROV-O: The PROV Ontology"

[5]: https://www.agdatatransparent.com/principles "Ag Data Transparent — Core Principles"

[6]: https://www.agdatatransparent.com/11-questions "Ag Data Transparent — 11 Questions"
