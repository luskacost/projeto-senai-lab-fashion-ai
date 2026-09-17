# -*- coding: utf-8 -*-
"""Índice BM25 (Okapi) em memória por tenant, para a busca híbrida do RAG (Fase 13, Task 10).

Implementação própria em vez de `rank_bm25`: são ~40 linhas e evitam uma dependência nova.
O índice é reconstruído quando o conjunto de ids da coleção muda -- os ids são hash do conteúdo
(`rag_manager._gerar_id_chunk`), então "mesmos ids" implica "mesmo corpus".
"""

import hashlib
import math
import re
import threading
from collections import Counter
from typing import Dict, List, Sequence, Tuple

from query_engine import STOPWORDS_PT, normalizar_texto

_STOPWORDS_NORM = {normalizar_texto(p) for p in STOPWORDS_PT}
_PADRAO_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def tokenizar(texto: str) -> List[str]:
    tokens: List[str] = []
    for palavra in _PADRAO_TOKEN.findall(normalizar_texto(texto)):
        if len(palavra) < 2 or palavra in _STOPWORDS_NORM:
            continue
        tokens.append(palavra)
        # "tx-860" casa tanto a pergunta que cita o código inteiro quanto a que cita só "860".
        if "-" in palavra:
            tokens.extend(p for p in palavra.split("-") if len(p) >= 2)
    return tokens


class IndiceBM25:
    def __init__(self, documentos: Sequence[Tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        self.ids = [doc_id for doc_id, _ in documentos]
        self._freqs = [Counter(tokenizar(texto)) for _, texto in documentos]
        self._tamanhos = [sum(f.values()) for f in self._freqs]
        self._tamanho_medio = (sum(self._tamanhos) / len(self._tamanhos)) if self._tamanhos else 0.0
        self.k1 = k1
        self.b = b

        df: Counter = Counter()
        for f in self._freqs:
            df.update(f.keys())
        n = len(documentos)
        self._idf = {termo: math.log(1 + (n - q + 0.5) / (q + 0.5)) for termo, q in df.items()}

    def pontuar(self, consulta: str) -> Dict[str, float]:
        termos = tokenizar(consulta)
        resultado: Dict[str, float] = {}
        for doc_id, freqs, tamanho in zip(self.ids, self._freqs, self._tamanhos):
            score = 0.0
            for termo in termos:
                f = freqs.get(termo)
                if not f:
                    continue
                norm = 1 - self.b + self.b * (tamanho / self._tamanho_medio if self._tamanho_medio else 0.0)
                score += self._idf[termo] * f * (self.k1 + 1) / (f + self.k1 * norm)
            if score > 0:
                resultado[doc_id] = score
        return resultado


_CACHE: Dict[str, Tuple[str, IndiceBM25]] = {}
_LOCK = threading.Lock()


def obter_indice(tenant_id: str, collection) -> IndiceBM25:
    ids = collection.get(include=[])["ids"]
    assinatura = hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()
    with _LOCK:
        em_cache = _CACHE.get(tenant_id)
        if em_cache and em_cache[0] == assinatura:
            return em_cache[1]

    dados = collection.get(include=["documents"])
    indice = IndiceBM25(list(zip(dados["ids"], dados["documents"])))
    with _LOCK:
        _CACHE[tenant_id] = (assinatura, indice)
    return indice
