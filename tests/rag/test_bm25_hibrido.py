# -*- coding: utf-8 -*-
"""Busca híbrida BM25 + fusão RRF (Fase 13, Task 10).

Caso que motivou: "Qual o preco por metro do tecido Linho misto?" -- a linha do catálogo tem o
maior casamento lexical, mas o embedding de uma linha de planilha é fraco (cos 0,20) e um trecho
de normas técnicas vencia a média ponderada. "linho" e "misto" são raros no corpus; "tecido"
aparece em quase tudo -- exatamente a distinção que o IDF do BM25 faz e o score lexical antigo não.
"""

import copy
import os
import shutil
import unittest

import bm25_index
import rag_golden_set as gs
import rag_manager as rm
from rag_config import RAG_CONFIG
from reranker import CandidateChunk, ordenar_por_rrf, selecionar_com_cobertura_e_diversidade
from query_engine import analisar_query_completa


class TestTokenizacao(unittest.TestCase):

    def test_remove_acento_caixa_e_stopwords(self):
        self.assertEqual(bm25_index.tokenizar("Qual o Preço do Tecido?"), ["preco", "tecido"])

    def test_codigo_com_hifen_gera_o_todo_e_as_partes(self):
        self.assertEqual(bm25_index.tokenizar("TX-860"), ["tx-860", "tx", "860"])


class TestIndiceBM25(unittest.TestCase):

    def setUp(self):
        self.indice = bm25_index.IndiceBM25([
            ("a", "tecido oxford para jaleco"),
            ("b", "tecido linho misto de verao"),
            ("c", "tecido brim resistente"),
            ("d", "ensaio de cor"),
        ])

    def test_termo_raro_pesa_mais_que_termo_comum(self):
        scores = self.indice.pontuar("tecido linho")
        self.assertEqual(max(scores, key=scores.get), "b")

    def test_documento_sem_termo_em_comum_nao_aparece(self):
        self.assertNotIn("d", self.indice.pontuar("tecido linho"))

    def test_consulta_sem_termo_util(self):
        self.assertEqual(self.indice.pontuar("qual o de"), {})


class _ColecaoFalsa:
    def __init__(self, docs):
        self.docs = docs
        self.construcoes = 0

    def get(self, include):
        if "documents" in include:
            self.construcoes += 1
            return {"ids": list(self.docs), "documents": list(self.docs.values())}
        return {"ids": list(self.docs)}


class TestCacheDoIndice(unittest.TestCase):

    def tearDown(self):
        bm25_index._CACHE.pop("tenant_cache_teste", None)

    def test_reaproveita_enquanto_os_ids_nao_mudam_e_reconstroi_quando_mudam(self):
        colecao = _ColecaoFalsa({"a": "linho"})
        primeiro = bm25_index.obter_indice("tenant_cache_teste", colecao)
        self.assertIs(bm25_index.obter_indice("tenant_cache_teste", colecao), primeiro)
        self.assertEqual(colecao.construcoes, 1)

        colecao.docs["b"] = "brim"
        novo = bm25_index.obter_indice("tenant_cache_teste", colecao)
        self.assertIsNot(novo, primeiro)
        self.assertIn("b", novo.pontuar("brim"))


def _cand(chunk_id, score):
    return CandidateChunk(chunk_id=chunk_id, texto=chunk_id, metadata={}, final_score=score)


class TestOrdenarPorRRF(unittest.TestCase):

    def test_bm25_sobe_um_candidato_quase_empatado(self):
        cands = [_cand("normas", 0.43), _cand("linho", 0.41), _cand("moletom", 0.39)]
        ordem = ordenar_por_rrf(cands, {"linho": 9.0, "normas": 1.0, "moletom": 2.0})
        self.assertEqual([c.chunk_id for c in ordem], ["linho", "normas", "moletom"])

    def test_nao_altera_o_score_heuristico(self):
        cands = [_cand("x", 0.43), _cand("y", 0.41)]
        ordenar_por_rrf(cands, {"y": 5.0})
        self.assertEqual([c.final_score for c in cands], [0.43, 0.41])

    def test_sem_termo_em_comum_nao_ganha_voto_do_bm25(self):
        # "z" é o último do BM25 com score 0 -- não pode ganhar 1/(k+rank) só por existir.
        cands = [_cand("x", 0.50), _cand("z", 0.49)]
        ordem = ordenar_por_rrf(cands, {"x": 1.0})
        self.assertEqual([c.chunk_id for c in ordem], ["x", "z"])
        self.assertNotIn("z", {c.chunk_id for c in ordem if c.score_breakdown["bm25"] > 0})

    def test_selecao_usa_o_melhor_score_mesmo_fora_da_primeira_posicao(self):
        # Ordem RRF com um candidato de score heurístico menor na frente: o threshold relativo
        # precisa partir do MAIOR score (0,80), senão o de 0,30 passaria o corte (0,55 * 0,30).
        ordem = [_cand("rrf_primeiro", 0.30), _cand("melhor", 0.80), _cand("fraco", 0.35)]
        selecionados = selecionar_com_cobertura_e_diversidade(
            ordem, analisar_query_completa("pergunta qualquer"), {"relative_score_threshold": 0.55, "min_rerank_score": 0.2}, final_k=5
        )
        self.assertEqual([c.chunk_id for c in selecionados], ["melhor"])


class TestPipelineHibrido(unittest.TestCase):
    TENANT = "teste_fase13_bm25_hibrido"
    PERGUNTA = "Qual o preco por metro do tecido Linho misto?"

    @classmethod
    def setUpClass(cls):
        cls._limpar()
        gs.indexar_corpus(cls.TENANT)

    @classmethod
    def tearDownClass(cls):
        gs.remover_corpus(cls.TENANT)
        cls._limpar()

    @classmethod
    def _limpar(cls):
        for sub in ("chroma", "tabular"):
            shutil.rmtree(os.path.join("tenant_data", sub, cls.TENANT), ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(cls.TENANT, None)
        bm25_index._CACHE.pop(cls.TENANT, None)

    def _buscar(self, **ajustes):
        cfg = copy.deepcopy(RAG_CONFIG)
        cfg["debug"] = False
        cfg.update(ajustes)
        return rm.buscar_contexto_relevante(self.TENANT, self.PERGUNTA, top_k=2, final_k=5, config=cfg)

    def _pool_pequeno(self, **ajustes):
        # Pool vetorial de 2 trechos num corpus de 19: a linha do Linho misto não é recuperada
        # pelo vetor -- só entra se o BM25 a trouxer.
        return self._buscar(retrieval_candidate_pool_size=2, per_query_top_k=2, **ajustes)

    def test_linha_exata_fica_em_primeiro(self):
        chunks = self._buscar()
        self.assertIn("TX-860", chunks[0]["texto"])

    def test_bm25_traz_para_o_pool_o_que_o_vetor_nao_achou(self):
        chunks = self._pool_pequeno()
        self.assertTrue(any("TX-860" in c["texto"] for c in chunks))
        self.assertGreater(rm.obter_ultimo_rag_debug()["bm25_debug"]["adicionados_ao_pool"], 0)

    def test_sem_bm25_o_pool_pequeno_perde_a_linha(self):
        chunks = self._pool_pequeno(enable_bm25_hybrid=False)
        self.assertFalse(any("TX-860" in c["texto"] for c in chunks))


if __name__ == "__main__":
    unittest.main()
