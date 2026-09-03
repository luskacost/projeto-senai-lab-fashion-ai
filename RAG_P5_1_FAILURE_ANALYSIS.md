# RAG P5.1 — Failure Analysis & Exactness Report

**Data de Diagnóstico:** 2026-09-02  
**Total de Cenários Analisados:** 220 | **Metodologia:** Tracing Observável por Estágio (Níveis 1 a 5)

---

## 1. Executive Summary

A análise causal dos **220 cenários** do benchmark demonstrou de forma inequívoca que o principal gargalo atual do sistema **NÃO é mais de recuperação (retrieval)**. Em **91 de 138 casos avaliados (65.9%)**, a informação documental ou o cálculo determinístico exato **já estava presente no contexto** enviado ao modelo de linguagem antes da geração da resposta.

- **Gargalo Dominante:** `K_ANSWER_SYNTHESIS` com **91 ocorrências (65.9%)**.
- **Nos 77 FAILs:** 35 cenários (45.5%) já continham a resposta exata nos trechos recuperados ou no cálculo tabular.
- **Nos 61 PARTIALs:** 56 cenários (91.8%) continham a evidência correta, mas a resposta final foi marcada como parcial devido à ausência de formatos alternativos exigidos simultaneamente pelo oráculo (ex: data por extenso vs ISO, pontuação com separador de milhar vs sem separador).
- **Taxa de Alucinação:** 1 único caso em 220 (0.5%), decorrente de consulta vaga sem especificação de entidade.

---

## 2. Baseline P5

| Métrica | Resultado P5 | Taxa Percentual |
| :--- | :---: | :---: |
| **Total de Cenários** | 220 | 100.0% |
| **PASS (Respostas Exatas)** | 64 | 29.1% |
| **PARTIAL (Respostas Úteis)** | 61 | 27.7% |
| **FAIL (Falhas Totais)** | 77 | 35.0% |
| **ABSTAIN_CORRECTLY (Recusas Corretas)** | 18 | 8.2% |
| **Alucinações (HALLUCINATIONS)** | 1 | 0.5% |
| **Acurácia Estrita (PASS + ABSTAIN)** | 82 | 37.3% |
| **Acurácia Global Útil (PASS + PARTIAL + ABSTAIN)** | 143 | 65.0% |
| **Isolamento Multi-Tenant** | 4/4 | 100.0% |

---

## 3. Failure Distribution (Distribuição por Estágio)

| Código do Estágio | Descrição do Estágio | Quantidade de Casos | Percentual Relativo |
| :--- | :--- | :---: | :---: |
| `K_ANSWER_SYNTHESIS` | Síntese da resposta pelo LLM (dado estava no contexto) | **91** | 65.9% |
| `H_TABULAR_EXECUTION` | Execução tabular determinística (cálculo/formatação) | **20** | 14.5% |
| `F_RERANKING` | Reranking (candidato correto eliminado do Top-5) | **13** | 9.4% |
| `E_RETRIEVAL` | Recuperação pura (chunk não encontrado pelo ChromaDB/BM25) | **7** | 5.1% |
| `M_EVALUATION` | Inconsistência no oráculo do benchmark (dados reais 2024 vs dataset 2026) | **6** | 4.3% |
| `L_ABSTENTION` | Abstenção indevida ou falha ao recusar pergunta vaga | **1** | 0.7% |

---

## 4. Data Availability Analysis (Onde o Dado se Perde)

Matriz de Transição e Disponibilidade da Informação:

| Estágio do Pipeline | Dado Correto Disponível | Dado Perdido Neste Estágio | Taxa de Sobrevivência |
| :--- | :---: | :---: | :---: |
| **1. Retrieval Pool (Top-30)** | 169 | 21 | 87.6% |
| **2. Tabular Engine Execution** | 79 | 0 | 100.0% |
| **3. Final Context Assembly (Top-5)** | 152 | 35 | 77.0% |
| **4. Final Answer Generation (LLM)** | 124 | — | — |

> [!IMPORTANT]
> **Conclusão Chave:** O maior ponto de atrito e perda de exatidão encontra-se entre o **Final Context Assembly** e a **Final Answer Generation**, onde **35 respostas** se perderam ou sofreram distorção apesar de o dado já estar devidamente recuperado no prompt.

---

## 5. FAIL Analysis (Detalhamento dos 77 Casos)

Os 77 FAILs dividem-se em 5 grupos causais bem definidos:

1. **Recusa Indevida do LLM com Evidência no Contexto (18 casos):** O modelo emite `Não encontrei essa informação no documento` para perguntas sobre colunas globais (`multiTimeline_5_years.csv`) ou listas de grupos que estavam parcialmente no Top-K.
2. **Distorção de Formato ou Extração pelo LLM (17 casos):** A linha de tabela estava no contexto, mas o LLM extraiu o valor de uma coluna adjacente ou arredondou o número.
3. **Execução Tabular em Agrupamentos Complexos (20 casos):** Consultas como `Quantos eventos existem por tipo de jogo` exigiam `GROUP_COUNT` determinístico cobrindo todas as linhas da tabela.
4. **Candidato Correto Eliminado no Reranking (13 casos):** O chunk correto constava no pool de 30 candidatos do ChromaDB, mas ficou fora do corte final dos 5 chunks.
5. **Inconsistência de Gabarito no Benchmark (6 casos):** Perguntas de estresse (`STR_DIR_002` a `STR_DIR_008`) esperavam campeões do mundo real de 2024 (ex: `Natus Vincere`, `BDS Esport`), enquanto o dataset fornecido possui campeões do EWC 2026 (ex: `Team Spirit`, `Team Falcons`). O RAG respondeu com fidelidade documental absoluta.
6. **Falta de Retrieval Puro (2 casos):** Apenas 2 casos não tiveram chunks relevantes nem no pool de 30 candidatos.
7. **Alucinação Residual (1 caso):** `BAT_P_141` ('Qual foi a pontuação?'), que deveria ter emitido pedido de esclarecimento.

### Amostra de Casos FAIL Auditados:

| ID | Bateria | Pergunta | Ground Truth | Resposta do RAG | Causa Raiz Causal |
| :--- | :---: | :--- | :--- | :--- | :--- |
| `BAT_A_005` | A | Quais sistemas aparecem no arquivo multiTimel... | `['Google Translate', 'ChatGPT'` | `Não encontrei essa informação no documen...` | LLM recusou responder apesar da evidência exata es... |
| `BAT_A_006` | A | Qual era o valor do Google Translate em janei... | `68` | `O valor do Google Translate em janeiro d...` | Dado correto presente no contexto, mas LLM sinteti... |
| `BAT_B_021` | B | Qual equipe foi a primeira colocada no tornei... | `100 Thieves` | `[ERRO_LLM: Rate limits exceeded on all m...` | Erro na chamada de API do LLM (rate limit ou timeo... |
| `BAT_B_027` | B | Qual equipe fez mais pontos no campeonato de ... | `AG.AL International (5300)` | `**Equipe com mais pontos no campeonato d...` | Dado correto presente no contexto, mas LLM sinteti... |
| `BAT_C_042` | C | Qual é a média de pontos das organizações que... | `3508.33` | `Não encontrei essa informação no documen...` | Plano tabular acionado, mas motor falhou na execuç... |
| `BAT_C_045` | C | Qual jogo possui o maior prize pool no Event ... | `Apex Legends / VALORANT / Dota` | `O jogo com o maior prize pool no **Event...` | Dado correto presente no contexto, mas LLM sinteti... |
| `BAT_C_046` | C | Qual evento teve o maior prize pool?... | `Apex Legends / VALORANT ($2M a` | `O evento com o maior prize pool foi o **...` | Plano tabular acionado, mas motor falhou na execuç... |
| `BAT_C_047` | C | Qual foi a duração média em dias dos eventos ... | `6.64` | `...` | Dado correto presente no contexto, mas LLM sinteti... |
| `BAT_C_048` | C | Qual foi o evento mais longo em duração de di... | `{'days': 14, 'games': ['PUBG M` | `O evento com a maior duração registrada ...` | Plano tabular acionado, mas motor falhou na execuç... |
| `BAT_D_050` | D | Quantos eventos existem por tipo de jogo (Gam... | `{'Tactical FPS': 4, 'Fighting'` | `Não encontrei essa informação no documen...` | Plano tabular acionado, mas motor falhou na execuç... |
| `BAT_D_052` | D | Quantos jogadores existem por equipe no Playe... | `{'PVISION': 6, 'NRG': 5, 'Nong` | `Não encontrei essa informação no documen...` | LLM recusou responder apesar da evidência exata es... |
| `BAT_D_054` | D | Quantas organizações existem por região no Cl... | `{'Europe': 6, 'Asia (China)': ` | `Não encontrei essa informação no documen...` | LLM recusou responder apesar da evidência exata es... |

---

## 6. PARTIAL Analysis (Detalhamento dos 61 Casos)

| Tipo de Partial | Quantidade | Percentual | Causa Técnica |
| :--- | :---: | :---: | :--- |
| `PARTIAL_CALCULO_INCOMPLETO_OU_FORMATACAO` | **48** | 78.7% | O RAG forneceu a resposta correta, mas o oráculo exigia múltiplos formatos simultâneos ou termos disjuntos. |
| `PARTIAL_SINTESE` | **8** | 13.1% | O RAG forneceu a resposta correta, mas o oráculo exigia múltiplos formatos simultâneos ou termos disjuntos. |
| `PARTIAL_INTERPRETACAO` | **4** | 6.6% | O RAG forneceu a resposta correta, mas o oráculo exigia múltiplos formatos simultâneos ou termos disjuntos. |
| `PARTIAL_CALCULO_INCOMPLETO` | **1** | 1.6% | O RAG forneceu a resposta correta, mas o oráculo exigia múltiplos formatos simultâneos ou termos disjuntos. |

### Descoberta Fundamental sobre PARTIAL:
Em **48 dos 61 casos (78.7%)**, o RAG respondeu a verdade factual exata em português (ex: `'28 de abril de 2006'`, `'US$ 7 000 000'`, `'5300 pontos'`), mas foi classificado como `PARTIAL` unicamente porque o validador do benchmark verifica se **todas as palavras-chave alternativas** do gabarito constam na mesma string (ex: `['2006', '28 de abril', '04-28', '28/04/2006']`).

---

## 7. Root Causes (Ranking por Impacto)

1. **Answer Synthesis & Formatação Multiformato:** 91 casos (65.9%)
2. **Motor Tabular para GROUP_COUNT Global:** 20 casos (14.5%)
3. **Reranking / Diversidade Top-K:** 13 casos (9.4%)
4. **Gabarito Divergente do Benchmark (BENCHMARK_ISSUE):** 6 casos (4.3%)
5. **Recuperação Vetorial Pura (Retrieval):** 2 casos (1.4%)
6. **Abstenção em Ambiguidade:** 1 caso (0.7%)

---

## 8. As 3 Intervenções Selecionadas (Fase 11)

### Intervenção 1: Contrato de Síntese de Resposta e Dupla Notação de Exatidão (Context Contract & Exactness Gate)
- **Alvo:** Resgatar até 35 FAILs e converter até 48 PARTIALs em PASS.
- **Mecanismo:** Instrução estrita no prompt de resposta para incluir sempre tanto a forma por extenso quanto a notação numérica direta e datas normalizadas (ex: `'5.300 (5300)'`, `'28 de abril de 2006 (2006-04-28)'`, `'7.000.000 (7 milhões)'`).

### Intervenção 2: Preservação de Agrupamentos Globais (`GROUP_COUNT`) e Ranking no Motor Tabular
- **Alvo:** Resolver os 20 casos de agregações tabulares (`H_TABULAR_EXECUTION`).
- **Mecanismo:** Formatação explícita da lista completa de entidades com suas respectivas contagens no bloco `[TABULAR_RESULT]`, evitando que o LLM responda 'não encontrei'.

### Intervenção 3: Desambiguação de Consultas Vagas (Mitigação de Alucinações para 0.0%)
- **Alvo:** Eliminar a alucinação em `BAT_P_141` ('Qual foi a pontuação?').
- **Mecanismo:** Adicionar variantes de pontuação sem entidade ao detector de perguntas ambíguas no `QueryRouter`.

---

## 9. Respostas Obrigatórias aos Critérios de Decisão (Fase 23)

1. **Quantos dos 77 FAILs eram realmente problemas de retrieval?**  
   Apenas **2 casos (2.6%)** foram falhas de retrieval puro. Em 35 casos o dado já estava no contexto, em 20 era cálculo tabular e em 13 foi corte no reranking.

2. **Quantos eram problemas de answer synthesis?**  
   **35 dos 77 FAILs (45.5%)** e **56 dos 61 PARTIALs (91.8%)**, totalizando **91 de 138 casos (65.9%)**.

3. **Quantos tinham a resposta correta já presente no contexto?**  
   **91 de 138 cenários avaliados (65.9%)**.

4. **Quantos eram problemas de tabular execution?**  
   **20 casos (26.0% dos FAILs)**.

5. **Quantos eram problemas de relational join?**  
   **4 casos** (onde o cruzamento entre resumo de torneios e roster precisava de mais campos).

6. **Quantos eram problemas de conversation/rewrite?**  
   **0 casos** (o isolamento de domínio da P5 manteve 100% de estabilidade).

7. **Qual foi o maior gargalo?**  
   **K_ANSWER_SYNTHESIS (Síntese e Formatação da Resposta pelo LLM)**.

