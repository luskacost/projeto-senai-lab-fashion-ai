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

import rag_metrics
from query_engine import normalizar_texto
from rag_manager import buscar_contexto_relevante

# Tamanho mínimo (em caracteres normalizados) para uma pergunta ser descontada do texto do chunk
# como eco. Ver a justificativa em `_chunk_e_relevante`.
TAMANHO_MINIMO_ECO = 20


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
    # sem descontar isso, um caso de abstenção como "qual o prazo de entrega do tecido TX-200?"
    # seria julgado respondido porque o termo "prazo de entrega" aparece... no eco da própria
    # pergunta.
    #
    # O desconto só vale para pergunta longa o bastante (TAMANHO_MINIMO_ECO). Uma string de 20+
    # caracteres aparecendo literalmente num chunk é eco da pergunta, não coincidência do
    # documento; já uma query curta costuma ser um termo isolado ("tricoline") que legitimamente
    # aparece no conteúdo -- descontá-la apagaria justamente a evidência que se quer medir.
    query_norm = normalizar_texto(caso.query)
    if len(query_norm) >= TAMANHO_MINIMO_ECO:
        texto_norm = texto_norm.replace(query_norm, " ")

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


def carregar_chunks_do_tenant(tenant_id: str) -> List[Dict[str, Any]]:
    """Todos os chunks indexados do tenant, no formato mínimo que o julgamento de relevância usa.

    Necessário para recall e nDCG: as duas precisam saber quantos chunks relevantes existem no
    corpus INTEIRO, não só entre os recuperados.
    """
    import rag_manager

    colecao = rag_manager._obter_colecao_tenant(tenant_id)
    dados = colecao.get(include=["documents", "metadatas"])
    return [
        {"texto": texto, "fonte": (meta or {}).get("fonte")}
        for texto, meta in zip(dados["documents"], dados["metadatas"])
    ]


def contar_relevantes_no_corpus(caso: CasoAvaliacao, chunks_do_corpus: List[Dict[str, Any]]) -> int:
    return sum(1 for chunk in chunks_do_corpus if _chunk_e_relevante(chunk, caso))


def contar_relevantes_gerados(resultado: ResultadoCaso, textos_do_corpus: set) -> int:
    """Chunks relevantes que o pipeline devolveu mas que não existem no corpus.

    O motor tabular sintetiza um bloco [TABULAR_RESULT] na hora da consulta -- ele não está
    indexado, então não entra em `contar_relevantes_no_corpus`. Quando esse bloco E a linha do
    catálogo são ambos relevantes, contar só o corpus no denominador dava recall 2/1 = 2,0.

    A solução é o "pooling" usado em avaliação de IR: o conjunto de relevantes de um caso é a
    união dos relevantes conhecidos (corpus) com os relevantes que o sistema efetivamente
    produziu. Recall fica limitado a 1,0 e o nDCG passa a comparar com um ranking ideal que também
    inclui a resposta sintetizada.
    """
    return sum(
        1 for chunk, relevante in zip(resultado.chunks_recuperados, resultado.relevancias)
        if relevante and chunk.get("texto", "") not in textos_do_corpus
    )


def _metricas_de_um_caso(
    resultado: ResultadoCaso, total_relevantes: int, k: int
) -> Dict[str, float]:
    return {
        "recall": rag_metrics.recall_em_k(resultado.relevancias, k, total_relevantes),
        "precision_em_k": rag_metrics.precision_em_k(resultado.relevancias, k),
        "precision_dos_recuperados": rag_metrics.precision_dos_recuperados(resultado.relevancias),
        "reciprocal_rank": rag_metrics.reciprocal_rank(resultado.relevancias),
        "ndcg": rag_metrics.ndcg_em_k(resultado.relevancias, k, total_relevantes),
    }


def resumir_avaliacao(
    casos: List[CasoAvaliacao],
    resultados: List[ResultadoCaso],
    chunks_do_corpus: List[Dict[str, Any]],
    k: int,
    rotulo: str = "",
) -> Dict[str, Any]:
    """Agrega os resultados num relatório comparável entre execuções.

    Os casos são separados em **três grupos que não podem ser somados numa média só**:

    - `recuperaveis`: a resposta existe em algum chunk do corpus. Só aqui recall/precision/nDCG/
      MRR fazem sentido, e é aqui que se mede qualidade de recuperação.
    - `abstencao`: a resposta não existe -- sucesso é não devolver nada relevante. Recall seria
      divisão por zero; a métrica certa é a taxa de abstenção correta.
    - `computados`: a resposta só existe se o motor tabular calcular (soma, média, contagem
      distinta). Não se mede recall de um documento que não existe; mede-se acerto do cálculo.

    Misturar os três numa "acurácia geral" é exatamente o tipo de média que esconde qual metade
    está quebrada -- foi o que aconteceu com os números de setembro, em que 65% de "acurácia útil"
    convivia com categorias inteiras em 0%.
    """
    por_id = {r.caso_id: r for r in resultados}
    textos_do_corpus = {chunk.get("texto", "") for chunk in chunks_do_corpus}
    grupos: Dict[str, List[Dict[str, Any]]] = {"recuperaveis": [], "abstencao": [], "computados": []}
    # categoria -> grupo -> registros. Uma categoria PODE abranger mais de um grupo: em
    # "tabular_filtro", um filtro de resultado multi-linha só existe calculado, enquanto os de
    # resultado de uma linha são satisfeitos recuperando aquela linha. Forçar uma categoria a ter
    # um grupo só obrigaria a classificar um caso errado para caber no formato do relatório.
    por_categoria: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for caso in casos:
        resultado = por_id.get(caso.id)
        if resultado is None:
            continue

        if caso.deve_abster:
            grupo, registro = "abstencao", {"caso_id": caso.id, "acertou": resultado.abstencao_correta()}
        elif caso.resposta_computada:
            grupo, registro = "computados", {"caso_id": caso.id, "acertou": any(resultado.relevancias)}
        else:
            no_corpus = contar_relevantes_no_corpus(caso, chunks_do_corpus)
            gerados = contar_relevantes_gerados(resultado, textos_do_corpus)
            grupo = "recuperaveis"
            registro = {
                "caso_id": caso.id,
                "total_relevantes_no_corpus": no_corpus,
                "relevantes_gerados": gerados,
                **_metricas_de_um_caso(resultado, no_corpus + gerados, k),
            }

        grupos[grupo].append(registro)
        por_categoria.setdefault(caso.categoria, {}).setdefault(grupo, []).append(registro)

    def _agregar(tipo: str, registros: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not registros:
            return {"n": 0}
        if tipo == "recuperaveis":
            return {
                "n": len(registros),
                # Média de quantos chunks relevantes existem no corpus por caso. Sem esse número,
                # a precision é facilmente mal lida: se existe 1 único chunk relevante, precision@5
                # não passa de 0,20 por construção, por melhor que o sistema seja.
                "relevantes_no_corpus_medio": round(
                    rag_metrics.media([float(r["total_relevantes_no_corpus"]) for r in registros]), 2
                ),
                "recall_medio": round(rag_metrics.media([r["recall"] for r in registros]), 4),
                "precision_em_k_media": round(rag_metrics.media([r["precision_em_k"] for r in registros]), 4),
                "precision_dos_recuperados_media": round(
                    rag_metrics.media([r["precision_dos_recuperados"] for r in registros]), 4
                ),
                "mrr": round(rag_metrics.media([r["reciprocal_rank"] for r in registros]), 4),
                "ndcg_medio": round(rag_metrics.media([r["ndcg"] for r in registros]), 4),
            }
        acertos = sum(1 for r in registros if r["acertou"])
        return {"n": len(registros), "acertos": acertos, "taxa": round(acertos / len(registros), 4)}

    return {
        "rotulo": rotulo,
        "k": k,
        "total_casos": len(casos),
        "recuperaveis": _agregar("recuperaveis", grupos["recuperaveis"]),
        "abstencao": _agregar("abstencao", grupos["abstencao"]),
        "computados": _agregar("computados", grupos["computados"]),
        "por_categoria": {
            categoria: {
                "n": sum(len(registros) for registros in por_grupo.values()),
                **{grupo: _agregar(grupo, registros) for grupo, registros in sorted(por_grupo.items())},
            }
            for categoria, por_grupo in sorted(por_categoria.items())
        },
    }


def comparar_resumos(antes: Dict[str, Any], depois: Dict[str, Any]) -> Dict[str, Any]:
    """Delta entre dois relatórios, para uma mudança de pipeline só entrar se o número melhorar.

    Compara apenas as chaves numéricas que existem nos dois lados -- se o `k` mudou entre as
    execuções, a comparação é sinalizada como não confiável em vez de produzir um delta que
    parece significativo e não é.
    """
    deltas: Dict[str, Any] = {
        "k_comparavel": antes.get("k") == depois.get("k"),
        "de": antes.get("rotulo", ""),
        "para": depois.get("rotulo", ""),
    }

    for grupo in ("recuperaveis", "abstencao", "computados"):
        bloco_antes, bloco_depois = antes.get(grupo, {}), depois.get(grupo, {})
        deltas[grupo] = {
            chave: round(valor - bloco_antes[chave], 4)
            for chave, valor in bloco_depois.items()
            if isinstance(valor, (int, float)) and isinstance(bloco_antes.get(chave), (int, float))
        }

    return deltas


def formatar_resumo(resumo: Dict[str, Any]) -> str:
    """Relatório legível no terminal, com os três grupos separados e a quebra por categoria."""
    linhas = [
        f"RELATÓRIO DE AVALIAÇÃO DO RAG{(' -- ' + resumo['rotulo']) if resumo.get('rotulo') else ''}",
        f"k={resumo['k']} | {resumo['total_casos']} casos",
        "",
    ]

    recup = resumo.get("recuperaveis", {})
    if recup.get("n"):
        linhas += [
            f"RECUPERAÇÃO ({recup['n']} casos -- a resposta existe em algum chunk do corpus)",
            f"  recall@{resumo['k']}           {recup['recall_medio']:.4f}",
            f"  nDCG@{resumo['k']}             {recup['ndcg_medio']:.4f}",
            f"  MRR                  {recup['mrr']:.4f}",
            f"  precision@{resumo['k']}        {recup['precision_em_k_media']:.4f}   (dividido por k)",
            f"  precision devolvida  {recup['precision_dos_recuperados_media']:.4f}   (sobre o que foi entregue)",
            f"  relevantes/caso      {recup['relevantes_no_corpus_medio']:.2f}     "
            f"(teto de precision@{resumo['k']} ~ {min(1.0, recup['relevantes_no_corpus_medio'] / resumo['k']):.2f})",
            "",
        ]

    for grupo, titulo in (("abstencao", "ABSTENÇÃO"), ("computados", "RESPOSTA CALCULADA")):
        bloco = resumo.get(grupo, {})
        if bloco.get("n"):
            linhas += [f"{titulo} ({bloco['n']} casos): {bloco['acertos']}/{bloco['n']} = {bloco['taxa']:.4f}", ""]

    linhas.append("POR CATEGORIA")
    for categoria, bloco in resumo.get("por_categoria", {}).items():
        linhas.append(f"  {categoria} (n={bloco['n']})")
        for grupo in ("recuperaveis", "abstencao", "computados"):
            sub = bloco.get(grupo)
            if not sub or not sub.get("n"):
                continue
            if grupo == "recuperaveis":
                detalhe = (
                    f"recall={sub['recall_medio']:.3f}  nDCG={sub['ndcg_medio']:.3f}  "
                    f"MRR={sub['mrr']:.3f}"
                )
            else:
                detalhe = f"acertos={sub['acertos']}/{sub['n']}"
            linhas.append(f"      {grupo:13s} n={sub['n']:2d}  {detalhe}")

    return "\n".join(linhas)


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
    parser.add_argument("--rotulo", default="", help="Rótulo da execução, para comparar relatórios.")
    args = parser.parse_args()

    casos_carregados = carregar_casos_de_json(args.casos_json, tenant_id=args.tenant)
    resultados_execucao = executar_conjunto(casos_carregados, k=args.k)

    for resultado in resultados_execucao:
        situacao = "OK" if (resultado.abstencao_correta() if resultado.deve_abster else any(resultado.relevancias)) else "FALHOU"
        print(f"[{situacao}] {resultado.caso_id} ({resultado.categoria}) -- {resultado.tempo_ms:.0f}ms")

    tenant_dos_casos = casos_carregados[0].tenant_id if casos_carregados else ""
    resumo_execucao = resumir_avaliacao(
        casos_carregados, resultados_execucao,
        carregar_chunks_do_tenant(tenant_dos_casos), k=args.k, rotulo=args.rotulo,
    )
    print("\n" + formatar_resumo(resumo_execucao))

    if args.saida:
        salvar_relatorio_json(resultados_execucao, args.saida)
        print(f"\nRelatório salvo em: {args.saida}")
