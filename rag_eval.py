# -*- coding: utf-8 -*-
"""Harness de avaliação do pipeline de RAG (Fase 13, Task 6).

## Por que este módulo existe

Antes desta task, a única forma de medir a qualidade do retrieval era `scratch/benchmark_runner.py`
-- um script preso ao Groq (removido do projeto em 10/set) e a um diretório inteiramente
`.gitignore`d, ou seja, **irreproduzível fora da máquina em que foi rodado**. Os únicos números que
existiam eram de execuções manuais de setembro, anteriores a várias correções de RAG desde então
(Fase 13, Tasks 1-5) -- o estado atual de qualidade do retrieval era, rigorosamente, desconhecido.

Este harness resolve só a parte de **infraestrutura de medição**: como definir um caso de teste,
como executá-lo contra o pipeline real, e como julgar se cada chunk devolvido é relevante. Ele
propositalmente NÃO inclui:

- **O conjunto de casos de verdade** (Task 7 -- `RAG_GOLDEN_SET`, um corpus sintético versionado,
  nunca dados reais de cliente).
- **O cálculo de métricas agregadas** (Task 8 -- recall@k, precision@k, nDCG, MRR). O que este
  módulo produz é o material bruto que essas métricas vão consumir: uma lista de julgamentos de
  relevância binários, na ordem de rank devolvida pelo pipeline -- o formato de entrada padrão de
  qualquer métrica de IR.

## Custo

Zero chamada de API. `buscar_contexto_relevante` é retrieval puro (embeddings locais + reranking
heurístico) -- nenhuma etapa deste harness invoca um LLM. Medir a qualidade da busca não exige
gastar crédito nenhum; só a síntese da resposta final exigiria (fora do escopo deste módulo).
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from query_engine import normalizar_texto
from rag_manager import buscar_contexto_relevante


@dataclass
class CasoAvaliacao:
    """Um caso de teste do harness: uma pergunta contra um tenant, e o critério que decide se um
    chunk devolvido conta como relevante.

    O critério de relevância é por CONTEÚDO (termos que precisam aparecer no texto do chunk),
    não por id de chunk -- um id de chunk é uma implementação interna que muda se o chunking
    mudar (tamanho de chunk, versão do modelo de embeddings, etc.); o que realmente importa para
    o caso de teste continuar válido é "o dado certo apareceu", não "o chunk específico X".
    """

    id: str
    tenant_id: str
    query: str
    # Todos os termos precisam aparecer (normalizado, sem acento) no texto de um chunk para que
    # ele conte como relevante. Lista vazia + deve_abster=False não deveria acontecer (nenhum
    # chunk contaria como relevante nunca) -- ver validação em executar_caso.
    termos_relevantes: List[str] = field(default_factory=list)
    # Qualquer um destes termos no chunk o desqualifica, mesmo que todos os termos_relevantes
    # estejam presentes (Fase 13, Task 7). Existe por um motivo concreto: numa consulta do tipo
    # "quais tecidos têm gramatura acima de 300", um motor tabular com o filtro quebrado devolve
    # TODAS as linhas da tabela -- que naturalmente contêm também as duas linhas certas. Sem uma
    # forma de dizer "e não pode conter as linhas que deveriam ter sido filtradas", o julgamento
    # daria esse resultado como relevante e a métrica esconderia justamente o defeito.
    termos_proibidos: List[str] = field(default_factory=list)
    # Opcional: além dos termos, exige que o chunk venha de um destes arquivos (nome_arquivo/
    # metadata "fonte"). Lista vazia = qualquer fonte serve, desde que os termos batam.
    fontes_relevantes: List[str] = field(default_factory=list)
    # True quando a resposta certa NÃO existe literalmente em nenhum chunk do corpus e só pode
    # surgir de um cálculo (soma, média, contagem distinta). A distinção importa para dois
    # consumidores: a checagem de integridade do golden set (não faz sentido exigir que a resposta
    # já esteja no corpus) e as métricas de IR da Task 8 (não se calcula recall de um documento
    # que não existe -- esses casos medem o motor tabular, não a recuperação).
    resposta_computada: bool = False
    # Casos de anti-alucinação (Task 7 vai povoar vários): a pergunta não deveria ter resposta na
    # base, e o critério de sucesso é o INVERSO -- nenhum chunk relevante deveria ser recuperado.
    deve_abster: bool = False
    # Livre, para o relatório agrupar por tipo (Task 7/8): "conceptual", "numeric_direct",
    # "hallucination_test", etc. -- mesma nomenclatura do golden set anterior (test_cases.json),
    # para não inventar um vocabulário novo sem necessidade.
    categoria: str = "geral"

    def __post_init__(self):
        if not self.deve_abster and not self.termos_relevantes and not self.fontes_relevantes:
            raise ValueError(
                f"Caso '{self.id}': sem termos_relevantes/fontes_relevantes e deve_abster=False "
                "-- nenhum chunk jamais contaria como relevante. Defina ao menos um critério, ou "
                "marque deve_abster=True se a intenção é um caso de anti-alucinação."
            )


@dataclass
class ResultadoCaso:
    """Resultado bruto da execução de um caso -- os julgamentos de relevância na ordem de rank
    devolvida pelo pipeline, prontos para qualquer métrica de IR consumir (Task 8)."""

    caso_id: str
    categoria: str
    query: str
    tempo_ms: float
    chunks_recuperados: List[Dict[str, Any]]
    # relevancias[i] corresponde a chunks_recuperados[i] -- mesma ordem, mesmo tamanho.
    relevancias: List[bool]
    deve_abster: bool

    def abstencao_correta(self) -> bool:
        """Para casos deve_abster=True: sucesso é não recuperar NENHUM chunk relevante."""
        return not any(self.relevancias)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "caso_id": self.caso_id,
            "categoria": self.categoria,
            "query": self.query,
            "tempo_ms": round(self.tempo_ms, 1),
            "deve_abster": self.deve_abster,
            "quantidade_recuperada": len(self.chunks_recuperados),
            "relevancias": self.relevancias,
            "fontes_recuperadas": [c.get("fonte") for c in self.chunks_recuperados],
        }


def _chunk_e_relevante(chunk: Dict[str, Any], caso: CasoAvaliacao) -> bool:
    if caso.fontes_relevantes and chunk.get("fonte") not in caso.fontes_relevantes:
        return False

    texto_norm = normalizar_texto(chunk.get("texto", ""))

    # Um chunk não ganha crédito por repetir a pergunta (Fase 13, Task 7). O motor tabular
    # devolve um bloco [TABULAR_RESULT] que começa ecoando "Consulta: <pergunta do usuário>" --
    # sem esta linha, um caso de abstenção como "qual o prazo de entrega do tecido TX-200?" seria
    # julgado respondido porque o termo "prazo de entrega" aparece... no eco da própria pergunta.
    # Remover o eco antes de julgar é agnóstico ao motor: só afeta chunk que cita a pergunta
    # literalmente, coisa que nenhum trecho de documento real faz.
    texto_norm = texto_norm.replace(normalizar_texto(caso.query), " ")

    if any(normalizar_texto(termo) in texto_norm for termo in caso.termos_proibidos):
        return False

    if not caso.termos_relevantes:
        # Só fontes_relevantes foi declarado -- a fonte já bateu (linha acima não retornou), então
        # o chunk conta como relevante.
        return True
    return all(normalizar_texto(termo) in texto_norm for termo in caso.termos_relevantes)


def executar_caso(caso: CasoAvaliacao, k: int = 10) -> ResultadoCaso:
    """Roda um caso contra o pipeline de retrieval de verdade e julga cada chunk devolvido.

    `k` é repassado como `final_k` -- quantos chunks o pipeline devolve depois de reranking e
    seleção por diversidade/cobertura, o "@k" de qualquer métrica que for computada em cima disto.
    """
    inicio = time.monotonic()
    chunks = buscar_contexto_relevante(caso.tenant_id, caso.query, top_k=max(k, 10), final_k=k)
    tempo_ms = (time.monotonic() - inicio) * 1000

    relevancias = [_chunk_e_relevante(chunk, caso) for chunk in chunks]

    return ResultadoCaso(
        caso_id=caso.id,
        categoria=caso.categoria,
        query=caso.query,
        tempo_ms=tempo_ms,
        chunks_recuperados=chunks,
        relevancias=relevancias,
        deve_abster=caso.deve_abster,
    )


def executar_conjunto(casos: List[CasoAvaliacao], k: int = 10) -> List[ResultadoCaso]:
    """Roda todos os casos em sequência. Sequencial de propósito: `buscar_contexto_relevante` usa
    um modelo de embeddings compartilhado (cache global, `rag_manager.obter_modelo_embeddings`) --
    paralelizar aqui não traria ganho real e complicaria a leitura do relatório."""
    return [executar_caso(caso, k=k) for caso in casos]


def salvar_relatorio_json(resultados: List[ResultadoCaso], caminho: str) -> None:
    """Serializa os resultados brutos (sem métricas agregadas -- isso é Task 8) para inspeção ou
    para uma métrica externa consumir depois, sem precisar rodar o pipeline de novo."""
    dados = [r.to_dict() for r in resultados]
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def carregar_casos_de_json(caminho: str, tenant_id: Optional[str] = None) -> List[CasoAvaliacao]:
    """Carrega casos de um arquivo JSON (formato: lista de objetos com os mesmos campos de
    CasoAvaliacao). `tenant_id`, se informado, sobrescreve o tenant de todos os casos -- útil para
    rodar o mesmo conjunto de perguntas contra um tenant de teste isolado sem editar o arquivo.
    """
    with open(caminho, "r", encoding="utf-8") as f:
        bruto = json.load(f)

    casos = []
    for item in bruto:
        dados = dict(item)
        if tenant_id is not None:
            dados["tenant_id"] = tenant_id
        casos.append(CasoAvaliacao(**dados))
    return casos


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("casos_json", help="Caminho do arquivo JSON com os casos de avaliação.")
    parser.add_argument("--tenant", default=None, help="Sobrescreve o tenant_id de todos os casos.")
    parser.add_argument("--k", type=int, default=10, help="Quantidade de chunks avaliados por caso.")
    parser.add_argument("--saida", default=None, help="Caminho para salvar o relatório JSON bruto.")
    args = parser.parse_args()

    casos_carregados = carregar_casos_de_json(args.casos_json, tenant_id=args.tenant)
    resultados_execucao = executar_conjunto(casos_carregados, k=args.k)

    for resultado in resultados_execucao:
        situacao = "OK" if (resultado.abstencao_correta() if resultado.deve_abster else any(resultado.relevancias)) else "FALHOU"
        print(f"[{situacao}] {resultado.caso_id} ({resultado.categoria}) -- {resultado.tempo_ms:.0f}ms")

    if args.saida:
        salvar_relatorio_json(resultados_execucao, args.saida)
        print(f"\nRelatório salvo em: {args.saida}")
