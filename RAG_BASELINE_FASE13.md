# RAG — Baseline Oficial (Fase 13, Task 9)

**Data de medição:** 2026-09-17
**Corpus:** `rag_golden_set.py` — 3 documentos sintéticos, 19 chunks, nunca dado real de cliente
**Casos:** `rag_golden_set.casos()` — 36 casos, 9 categorias
**Metodologia:** `rag_eval.py` + `rag_metrics.py` (Fase 13, Tasks 6-8) — retrieval puro, custo zero de API
**k:** 5 (mesmo valor de `RAG_CONFIG["final_context_top_k"]`, produção)
**Como reproduzir:** `python scripts/medir_baseline_rag.py --k 5 --rotulo "..." --forcar` (o resultado
bruto da medição vigente está versionado em `rag_baseline_fase13.json`)

---

## 0. Histórico de medições

`rag_baseline_fase13.json` guarda sempre a medição **vigente** — é contra ela que
`tests/rag/test_baseline_regressao.py` barra regressões. Cada melhoria aceita no Bloco F3 sobe a
régua, para uma task futura não conseguir desfazer um ganho sem que o teste perceba.

| Medição | Data | Recall@5 | nDCG@5 | MRR | Abstenção | Calculados |
|---|---|---|---|---|---|---|
| v1 — pós F1 (Tasks 1-5) | 2026-09-17 | 0,7826 | 0,6850 | 0,6587 | 8/8 | 1/5 |
| **v2 — pós correção do motor tabular (F3)** | 2026-09-17 | **0,8261** | **0,7566** | **0,7783** | 8/8 | **5/5** |

**v1 → v2:** o motor tabular passou a resolver a coluna pelo schema real da planilha (ver seção 6).
As seções 2 a 5 abaixo são a análise original da **v1**, preservada como registro do ponto de
partida.
Resolve 6 das 9 falhas da v1; as 3 restantes são todas `multi_documento`.

**Mudança de métrica entre v1 e v2 (sem efeito na v1):** o denominador de recall/nDCG passou a
incluir os chunks relevantes *gerados* pelo pipeline (pooling — ver
`rag_eval.contar_relevantes_gerados`). Sem isso, um bloco `[TABULAR_RESULT]` relevante somado à
linha do catálogo dava recall 2/1 = 2,0. A v1 foi **remedida com a métrica nova sobre o código
antigo** e os números não mudaram (o motor antigo nunca produzia chunk tabular relevante nos casos
de recuperação) — a comparação v1 × v2 é, portanto, de mesma régua.

---

## 1. Por que este número existe

Os únicos números de qualidade de RAG que o projeto tinha antes desta task eram de **02/09/2026**
(`RAG_P5_1_FAILURE_ANALYSIS.md`), medidos **antes** dos 4 fixes de qualidade daquela mesma semana
e **antes** de toda a Fase 13 (Tasks 1-5: correção da métrica de distância do Chroma, garantia de
janela de tokens, remoção de vocabulário hardcoded, ids determinísticos). O harness daquela época
(`scratch/benchmark_runner.py`) está preso ao Groq, removido do projeto em 10/09, e vive num
diretório inteiramente `.gitignore`d — irreproduzível fora da máquina em que rodou.

Em resumo: entre 02/09 e 17/09 o pipeline mudou de forma significativa e **ninguém tinha medido
o efeito**. Este é o primeiro número honesto do estado atual — a baseline contra a qual toda
mudança do Bloco F3 (Tasks 10-14) precisa se provar melhor, não pior.

## 2. Resultado (v1)

Os 36 casos são separados em três grupos que **não podem ser somados numa média só** (ver a
justificativa completa em `rag_eval.resumir_avaliacao`) — foi exatamente uma média única que, em
setembro, escondeu categorias inteiras em 0% atrás de "65% de acurácia útil".

### 2.1 Recuperação (23 casos — a resposta existe em algum chunk do corpus)

| Métrica | Valor |
|---|---|
| Recall@5 | **0,7826** |
| nDCG@5 | **0,6850** |
| MRR | **0,6587** |
| Precision@5 | 0,1739 |
| Precision sobre o devolvido | 0,2123 |
| Relevantes por caso (média) | 1,09 |

O teto estrutural de Precision@5 aqui é **~0,22** (1,09 relevante / 5 posições) — o número baixo
não indica busca ruim, é uma propriedade do corpus (poucos chunks relevantes por pergunta). Ler
Precision@k sempre junto do "relevantes/caso" nos próximos relatórios.

### 2.2 Abstenção (8 casos — a pergunta não tem resposta na base)

**8/8 = 100%.** O pipeline nunca alucinou uma resposta para as perguntas do golden set desenhadas
para não ter resposta (anti-alucinação + ausência parcial de atributo).

### 2.3 Resposta computada (5 casos — soma, média, contagem distinta, filtro multi-linha)

**1/5 = 20%.**

## 3. Por categoria

| Categoria | Tipo | Resultado |
|---|---|---|
| `lookup_direto` | recuperação | recall 1,000 · nDCG 1,000 · MRR 1,000 |
| `numerico_exato` | recuperação | recall 1,000 · nDCG 0,908 · MRR 0,875 |
| `desambiguacao` | recuperação | recall 1,000 · nDCG 1,000 · MRR 1,000 |
| `conceitual` | recuperação | recall 1,000 · nDCG 0,827 · MRR 0,800 |
| `anti_alucinacao` | abstenção | 4/4 |
| `ausencia_parcial` | abstenção | 4/4 |
| `multi_documento` | recuperação | recall **0,250** · nDCG **0,097** · MRR **0,050** |
| `tabular_agregacao` | computado | 1/4 |
| `tabular_filtro` | recuperação (3) + computado (1) | recall 0,333 · nDCG 0,144 · MRR 0,083 \| 0/1 |

## 4. Leitura honesta do número

**A recuperação direta está sólida.** Lookup direto, número exato, desambiguação entre entidades
quase idênticas e busca conceitual (sem o termo literal da pergunta no documento) — as quatro
categorias que testam "o pipeline acha o trecho certo quando ele existe isolado" — saem em
recall 1,000. O trabalho da Fase 7-10 nessas frentes está de fato funcionando.

**Zero alucinação nos 8 casos de abstenção.** Nenhuma resposta inventada quando a base não tem o
dado — a garantia mais importante de um sistema de RAG em produção, intacta.

**Duas frentes concentram toda a falha, e nenhuma delas é a busca vetorial em si:**

- **`multi_documento` (recall 0,250, MRR 0,050):** quando a resposta exige ligar uma peça do
  manual ao atributo dela no catálogo (ex: "qual o preço do tecido usado no jaleco JL-100?"), o
  pipeline quase sempre falha. Não é falta de embedding — é ausência de um passo de
  *join semântico* entre documentos. Nenhuma task da Fase 13 tentou resolver isso ainda.
- **Motor tabular (`tabular_agregacao` 1/4, `tabular_filtro` computado 0/1):** confirma
  exatamente o que a inspeção manual já tinha achado antes da Task 7 — `AVG` resolve a coluna
  errada e devolve `0.00`, `FILTER` numérico devolve a tabela inteira como se estivesse
  filtrada, e `DISTINCT` vira `COUNT`. Isso não é uma amostra pequena mostrando ruído; é o motor
  tabular quebrado de forma sistemática nessas operações, sobre um catálogo de 12 linhas onde
  não deveria haver ambiguidade nenhuma.

## 5. O que isto significa para o Bloco F3

- **Não é prioridade mexer em BM25/fusão híbrida ou em pesos do reranker primeiro** — a
  recuperação vetorial pura já está no teto (recall 1,0) em tudo que não depende de motor
  tabular ou de múltiplos documentos. Ajustar pesos de reranking não move nenhuma das duas
  frentes que de fato falham.
- **O motor tabular (`tabular_query_engine.py`) precisa de correção antes de qualquer
  recalibração de threshold** — não é um problema que `final_context_top_k` adaptativo (Task 11)
  resolveria.
- **Join multi-documento é uma capacidade que não existe ainda**, não um bug — decidir se entra
  no escopo do Bloco F3 ou fica para uma fase futura é uma decisão de produto, não só técnica.

## 6. Atualização após a correção do motor tabular (v2)

A seção 5 recomendava corrigir o motor tabular antes de qualquer outra coisa do Bloco F3 — e a
decisão foi tomada nessa ordem (em vez de BM25/fusão híbrida, a Task 10 original do plano).

**Causa raiz única:** resolução de coluna. O `QueryRouter` propunha o termo de coluna a partir de
um vocabulário fixo, herdado do benchmark de e-sports de setembro (`pontos`, `premiacao`), ou —
num filtro numérico — da palavra logo após o número (`reais` em "menos de 15 reais por metro").
Quando o termo não casava com nenhuma coluna real, o plano seguia sem coluna e o executor:

- calculava média/soma sobre a coluna inexistente `valor` e devolvia `0,00`;
- descartava o filtro e devolvia a tabela inteira como se estivesse filtrada;
- respondia "quantos fornecedores diferentes" com o total de linhas.

Tudo com `success=True` e rotulado para o LLM como **"Resultado Calculado Deterministicamente"**,
com a instrução de usar o número sem recalcular. Era uma fonte de afirmação falsa com cara de fato,
não só uma resposta errada.

**O que mudou (`tabular_query_engine.py`, `query_router.py`):**

1. A coluna passa a ser resolvida a partir dos nomes que **existem** no schema e são citados na
   pergunta (com casamento de plural por prefixo e um conceito genérico de dinheiro para
   "caro/barato/custa/preço"), em vez do vocabulário fixo do roteador.
2. **Nunca fabricar:** sem coluna resolvível, a operação numérica ou o filtro numérico não geram
   plano — a pergunta cai na busca vetorial. O executor também recusa (`success=False`) operação
   numérica sobre coluna inexistente, de texto, ou média de conjunto vazio.
3. "Quantos X diferentes/distintos" vira `DISTINCT` na coluna citada.
4. Superlativos que o roteador não reconhecia ("mais caro", "mais barato") viram `MAX`/`MIN`;
   "maior/menor" só quando a pergunta cita a coluna pelo nome inteiro, para não sequestrar
   perguntas conceituais.
5. O roteador passou a reconhecer média pelo adjetivo masculino ("preço **médio**").

**Nuance registrada, não corrigida:** em `tabular_filtro`, recall 0,667 convive com MRR 1,000 — a
resposta calculada vem no topo, mas nem sempre a linha crua do catálogo aparece junto, e o pooling
conta isso como recall parcial. É ausência de redundância, não erro; ajustar a métrica para
esconder isso seria pior do que explicar.

**O que continua aberto:** `multi_documento` (recall 0,250). É uma capacidade que não existe —
ligar peça (manual) → tecido → atributo (catálogo) — e não um bug.

## 7. Limitações desta medição

- **Corpus de 19 chunks.** Suficiente para o ranking ter o que errar (ver o desenho do corpus em
  `rag_golden_set.py`), mas pequeno demais para expor problemas de escala (ex: `final_context_top_k`
  fixo em 5 contra uma tabela de centenas de linhas — o defeito #2 do benchmark de setembro, que
  este corpus não teria como reproduzir).
- **36 casos** cobrem 9 categorias com 3-4 casos cada — cobertura por categoria, não volume. Um
  caso isolado que falhe por acidente de fraseado pesa 25% da categoria inteira.
- **Sem medição de síntese final.** Este baseline mede só retrieval (custo zero de API,
  decisão consciente da Fase 13). Não diz se o LLM, tendo o contexto certo em mãos, de fato
  produz a resposta certa — essa é uma medição diferente, que exigiria autorização explícita do
  usuário antes de gastar chamadas reais.
