# TODO — Qualidade do RAG (priorizado a partir dos relatórios de benchmark)

Checklist operacional extraído de `RAG_P5_1_FAILURE_ANALYSIS.md` (220 cenários, baseline mais recente,
2026-09-02) e `RAG_EXTERNAL_DATASET_BENCHMARK.md`. Cada item vira 1 sessão de trabalho (Passo 12,
ciclo de melhoria pontual): reproduzir com `tests/rag/test_retrieval_quality.py`/`test_cases.json` ou
um caso equivalente, ajustar 1 hiperparâmetro/regra, revalidar. Não recriar a análise — só executar.

Status desta lista: itens 1, 2, 3 e 4 tratados. A ordem reflete o ranking de impacto do próprio
relatório (Seção 7 do failure analysis).

## 1. [CONCLUÍDO] Contrato de síntese de resposta / dupla notação (maior impacto: ~91 de 138 casos, 65.9%)

- **Causa raiz:** o dado correto já está no contexto enviado ao LLM em 65.9% dos casos avaliados, mas
  a resposta final é marcada como FAIL/PARTIAL porque falta uma segunda forma de notação exigida pelo
  gabarito (ex.: `"5.300 (5300)"`, `"28 de abril de 2006 (2006-04-28)"`, `"7.000.000 (7 milhões)"`) —
  não é um problema de retrieval, é de formatação da resposta final.
- **Onde mexer:** o prompt de instrução enviado ao LLM no modo "Base de Conhecimento" (montagem em
  `app.py`, hoje ainda inline — ver Passo 14 desta fase, que extrai isso para `rag_manager.py`).
  Adicionar instrução explícita para sempre incluir forma numérica direta E por extenso/normalizada
  quando aplicável.
- **Como validar:** casos de `tests/rag/test_cases.json` com datas/valores numéricos; comparar
  resposta antes/depois da instrução.

## 2. [CONCLUÍDO] Preservação de agrupamentos globais (`GROUP_COUNT`) no motor tabular (~20 casos, 14.5%)

- **Causa raiz real (confirmada por reprodução empírica, diferente da hipótese original):** a
  formatação da saída do `GROUP_COUNT` já estava correta e completa (não truncava). O bug real tinha
  2 partes em `tabular_query_engine.py`: (1) quando o termo de agrupamento da pergunta (em português,
  sem alias configurado) não resolvia para nenhuma coluna real, o score de seleção de documento caía
  abaixo do limiar e o intent `GROUP_COUNT` corretamente identificado era descartado, caindo para uma
  classificação genérica do `QueryRouter` que ignorava o agrupamento; (2) quando a execução chegava a
  rodar sem coluna de agrupamento resolvida, usava cegamente `sheet.schema[0]` (tipicamente um
  identificador único) em vez de uma coluna categórica.
- **Corrigido:** limiar de score dispensado quando há um único documento tabular no tenant (sem
  ambiguidade de seleção); adicionada `_escolher_coluna_categoria_provavel()` como fallback por
  cardinalidade. Teste de regressão permanente:
  `tests/rag/test_tabular_query_engine.py::test_u_group_count_sem_correspondencia_de_coluna`.

## 3. [CONCLUÍDO] Desambiguação de consultas vagas sem entidade (elimina a última alucinação, 1 caso)

- **Descoberta:** já estava implementado em `query_router.py` (linhas 475-476, conjunto
  `perguntas_vagas` inclui `"qual foi a pontuacao"`/`"qual foi a pontuação"`) — não era um gap real,
  só faltava cobertura de teste. Confirmado por reprodução direta: `route_query("Qual foi a
  pontuação?")` retorna `AMBIGUOUS`; a mesma pergunta com entidades explícitas
  (`"...entre Team Spirit e Team Falcons?"`) corretamente NÃO é tratada como ambígua.
- **Feito:** estendido `tests/rag/test_query_router.py::test_08_ambiguidade_pergunta_incompleta` com
  o caso exato do benchmark (`BAT_P_141`) e o contraste com entidades explícitas.

## 4. [CONCLUÍDO] "Reranking corta candidato correto do Top-5" (~13 casos, 9.4%)

- **Diagnóstico original do relatório (impreciso):** sugeria ajustar pesos/threshold do reranker em
  `reranker.py`/`RAG_CONFIG`.
- **Investigação feita nesta sessão:** os dados brutos ainda existem em
  `scratch/benchmark_p5_1_diagnostics.json` (`fails_analise_77`, filtrando por
  `failure_stage == "F_RERANKING"`). Inspecionados os 13 casos: **100% têm
  `tabular_engine_attempted: False`** — nenhum chegou a acionar o motor tabular. Todas são perguntas
  de filtro/limiar numérico (`"Quais organizações possuem mais de 4.000 pontos?"`) ou relacionais
  encadeadas (`"Qual país possui mais medalhas... e quais jogadores confirmados no roster são desse
  país?"`) que foram roteadas como `VECTOR_SEMANTIC` puro pelo `QueryRouter`. Também testei a
  hipótese de redundância por similaridade de Jaccard entre linhas de uma mesma planilha
  (`_calcular_similaridade_jaccard`) — descartada, a similaridade medida (~0.38) fica bem abaixo do
  limiar de descarte (0.85), não é a causa.
- **Causa raiz real:** gap de **roteamento**, não de reranking. `query_router.py` não tem padrões de
  detecção para (a) filtros com limiar numérico em linguagem natural ("mais de X pontos/reais/USD")
  e (b) perguntas relacionais encadeadas de duas partes ("qual X e quais Y desse X"). Uma busca
  vetorial pura estruturalmente não consegue recuperar de forma confiável *todas* as linhas de uma
  tabela que satisfazem um filtro — não há ajuste de reranker que resolva isso.
- **Corrigido (Fase 7 — aprimoramento dos modos):** `query_router.py` ganhou `extrair_filtro_numerico()`
  (reconhece "mais de/acima de/pelo menos/menor que/etc + número" e resolve a coluna via
  `EXTENDED_COLUMN_ALIASES`) e 2 padrões genéricos em `padroes_relacionais` que detectam uma segunda
  oração referenciando de volta uma entidade da primeira via pronome demonstrativo
  (desse/dessa/deste/desta/dele/dela), generalizando a detecção relacional além dos 5 padrões
  literais hardcoded. `tabular_query_engine.py` ganhou a tradução do filtro `numeric_threshold` do
  `QueryRouter` para um `TabularFilter` executável (sem isso, `TabularIntent.FILTER` executaria com
  `filters=[]` e devolveria todas as linhas como se estivessem filtradas). Teste de regressão
  permanente com execução completa do plano (não só a classificação):
  `tests/rag/test_query_router.py::test_11_filtro_por_limiar_numerico`,
  `::test_12_relacional_encadeado_generico`.

## Fora de escopo desta lista (não ignorar, mas não é prioridade imediata)

- 6 casos de "gabarito divergente do benchmark" (dados reais 2024 vs dataset de teste 2026) — não é
  bug do sistema, é inconsistência do dataset de benchmark em si.
- 2 casos de falha de retrieval puro — volume baixo (1.4%), monitorar mas não priorizar agora.
