# TODO — Qualidade do RAG (priorizado a partir dos relatórios de benchmark)

Checklist operacional extraído de `RAG_P5_1_FAILURE_ANALYSIS.md` (220 cenários, baseline mais recente,
2026-09-02) e `RAG_EXTERNAL_DATASET_BENCHMARK.md`. Cada item vira 1 sessão de trabalho (Passo 12,
ciclo de melhoria pontual): reproduzir com `tests/rag/test_retrieval_quality.py`/`test_cases.json` ou
um caso equivalente, ajustar 1 hiperparâmetro/regra, revalidar. Não recriar a análise — só executar.

Status desta lista: itens 1 e 2 tratados. Itens 3-4 seguem pendentes. A ordem reflete o ranking de
impacto do próprio relatório (Seção 7 do failure analysis).

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

## 3. Desambiguação de consultas vagas sem entidade (elimina a última alucinação, 1 caso)

- **Causa raiz:** perguntas como `"Qual foi a pontuação?"` sem especificar a entidade não são
  capturadas pelo detector de ambiguidade do `QueryRouter`, podendo levar a uma resposta inventada.
- **Onde mexer:** `query_router.py` (já tem lógica de detecção de ambiguidade — grep por "pontuação"
  mostra que o termo já aparece no arquivo; **verificar se a variante sem entidade explícita está
  coberta** ou se falta adicionar esse padrão específico ao detector).
- **Como validar:** reproduzir o caso `BAT_P_141` (ou equivalente) e confirmar que o sistema pede
  esclarecimento em vez de responder.

## 4. Reranking corta candidato correto do Top-5 (~13 casos, 9.4%)

- **Causa raiz:** o chunk correto está no pool de 30 candidatos do ChromaDB, mas é eliminado antes do
  corte final de 5 pelo reranker (`reranker.py` — `HeuristicReranker` / `selecionar_com_cobertura_e_diversidade`).
- **Onde mexer:** `reranker.py` e pesos em `RAG_CONFIG["weights"]`/`RAG_CONFIG["diversity"]`
  (`rag_config.py`). Candidato a ajuste: aumentar `final_context_top_k` experimentalmente ou revisar
  peso de diversidade vs. relevância pura para esses casos específicos.
- **Como validar:** `tests/rag/test_retrieval_quality.py` (já cobre corte prematuro de Top-K — ver
  `test_b_chunk_relevante_nao_perdido_por_corte_prematuro`).

## Fora de escopo desta lista (não ignorar, mas não é prioridade imediata)

- 6 casos de "gabarito divergente do benchmark" (dados reais 2024 vs dataset de teste 2026) — não é
  bug do sistema, é inconsistência do dataset de benchmark em si.
- 2 casos de falha de retrieval puro — volume baixo (1.4%), monitorar mas não priorizar agora.
