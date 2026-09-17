# -*- coding: utf-8 -*-
"""Métricas de recuperação de informação (Fase 13, Task 8).

Funções puras sobre uma lista de julgamentos de relevância binários **na ordem de rank** --
exatamente o que `rag_eval.ResultadoCaso.relevancias` produz. Este módulo não importa nada do
pipeline de RAG de propósito: métrica errada corrompe silenciosamente toda decisão tomada em cima
dela, então ela precisa ser testável com valores calculados à mão, sem indexar documento nenhum.

## Por que `total_relevantes` é obrigatório em recall e nDCG

Recall precisa saber quantos documentos relevantes existem no corpus INTEIRO, não só quantos
foram devolvidos -- sem isso não dá para distinguir "achou os 2 que existiam" de "achou 2 dos 10".
nDCG precisa do mesmo número para montar o ranking ideal contra o qual normaliza.

Quando esse número é zero (caso de abstenção, ou resposta que só existe se for calculada), as duas
métricas são **indefinidas**, não zero. Devolver 0.0 ali seria pior que inútil: pareceria péssimo
desempenho quando na verdade a métrica não se aplica. Por isso as funções levantam ValueError --
a exclusão desses casos tem que ser uma decisão explícita de quem chama, e é (ver
`rag_eval.resumir_avaliacao`, que separa os três grupos de casos).
"""

import math
from typing import List


def precision_em_k(relevancias: List[bool], k: int) -> float:
    """Precisão@k clássica: relevantes entre os k primeiros, dividido por **k**.

    Atenção ao interpretar: quando o pipeline devolve menos de k chunks (o que é comum aqui --
    a seleção por diversidade/cobertura corta candidatos fracos de propósito), esta métrica fica
    mecanicamente limitada. Um sistema que devolve 1 chunk perfeito em vez de 1 bom e 4 ruins tem
    precision@5 = 0,20 e comportamento exemplar. Use junto com `precision_dos_recuperados`.
    """
    if k <= 0:
        return 0.0
    return sum(1 for rel in relevancias[:k] if rel) / k


def precision_dos_recuperados(relevancias: List[bool]) -> float:
    """Precisão sobre o que foi de fato devolvido, não sobre k.

    Responde "do que o sistema entregou, quanto presta?" -- a pergunta que importa para um RAG,
    onde cada chunk irrelevante no contexto é ruído que o LLM ainda vai ter que ignorar.
    """
    if not relevancias:
        return 0.0
    return sum(1 for rel in relevancias if rel) / len(relevancias)


def recall_em_k(relevancias: List[bool], k: int, total_relevantes: int) -> float:
    """Recall@k: dos relevantes que existem no corpus, quantos apareceram nos k primeiros."""
    if total_relevantes <= 0:
        raise ValueError(
            "recall_em_k exige total_relevantes > 0. Com zero relevantes no corpus (caso de "
            "abstenção ou de resposta calculada) a métrica é indefinida, não zero -- esses casos "
            "precisam ser medidos por taxa de acerto própria, não por recall."
        )
    if k <= 0:
        return 0.0
    return sum(1 for rel in relevancias[:k] if rel) / total_relevantes


def reciprocal_rank(relevancias: List[bool]) -> float:
    """1 / posição do primeiro relevante (1-based); 0.0 se nenhum foi recuperado.

    A média disto sobre os casos é o MRR -- mede se a resposta certa vem no topo, não só se está
    em algum lugar da lista. Para um RAG importa mais que o normal: o LLM lê os primeiros trechos
    com mais peso, e o contexto é cortado por tamanho.
    """
    for indice, relevante in enumerate(relevancias):
        if relevante:
            return 1.0 / (indice + 1)
    return 0.0


def ndcg_em_k(relevancias: List[bool], k: int, total_relevantes: int) -> float:
    """nDCG@k com relevância binária: quanto o ranking real se aproxima do ranking ideal.

    Diferente de recall@k (que só olha se o relevante entrou nos k), nDCG penaliza colocá-lo na
    posição 5 em vez da 1 -- é a métrica que distingue "recuperou" de "recuperou bem ranqueado".
    """
    if total_relevantes <= 0:
        raise ValueError(
            "ndcg_em_k exige total_relevantes > 0 para montar o ranking ideal (IDCG). Com zero "
            "relevantes no corpus a métrica é indefinida."
        )
    if k <= 0:
        return 0.0

    dcg = sum(
        1.0 / math.log2(indice + 2)
        for indice, relevante in enumerate(relevancias[:k])
        if relevante
    )
    # Ranking ideal: todos os relevantes que couberem nas k posições, do topo para baixo.
    idcg = sum(1.0 / math.log2(indice + 2) for indice in range(min(total_relevantes, k)))
    return dcg / idcg if idcg > 0 else 0.0


def media(valores: List[float]) -> float:
    """Média simples, 0.0 para lista vazia -- evita ZeroDivisionError em categoria sem casos."""
    return sum(valores) / len(valores) if valores else 0.0
