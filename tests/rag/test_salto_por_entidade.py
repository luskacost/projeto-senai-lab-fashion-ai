# -*- coding: utf-8 -*-
"""Segundo salto por código de entidade entre documentos (Fase 13, Bloco F3).

A pergunta "qual o fornecedor do tecido da calça operacional?" tem a resposta dividida: o manual
liga a peça ao código TX-520, o catálogo liga TX-520 ao fornecedor. Antes do salto, a busca achava
a peça e nunca a linha do catálogo (recall 0,25 em multi_documento no golden set).
"""

import unittest

import rag_manager as rm
from reranker import CandidateChunk


class _ColecaoFalsa:
    """Imita `collection.get(where_document={"$contains": ...})` do Chroma (substring, sem
    fronteira de palavra -- por isso o código testado precisa checar a fronteira sozinho)."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.consultas = []

    def get(self, where_document, include):
        termo = where_document["$contains"]
        self.consultas.append(termo)
        achados = [c for c in self.chunks if termo in c["texto"]]
        return {
            "ids": [c["id"] for c in achados],
            "documents": [c["texto"] for c in achados],
            "metadatas": [{"fonte": c["fonte"]} for c in achados],
        }


def _cand(chunk_id, texto, fonte, lexical=0.0, score=0.5):
    return CandidateChunk(
        chunk_id=chunk_id, texto=texto, metadata={"fonte": fonte}, fonte=fonte,
        lexical_score=lexical, final_score=score,
    )


CFG = {"entity_hop_max_chunks": 2}


class TestSaltoPorEntidade(unittest.TestCase):

    def setUp(self):
        self.linha_tx520 = {"id": "cat_520", "texto": "Codigo: TX-520 / Fornecedor: Tecelagem Bandeira", "fonte": "catalogo.csv"}
        self.linha_tx5200 = {"id": "cat_5200", "texto": "Codigo: TX-5200 / Fornecedor: Outro", "fonte": "catalogo.csv"}
        self.peca = _cand("man_4", "CALCA OPERACIONAL REF CL-440 / Tecido: Sarja TX-520", "manual.txt", lexical=0.6)
        self.ruido = [_cand(f"r{i}", f"texto qualquer {i}", "normas.txt", lexical=0.1) for i in range(4)]

    def _expandir(self, selecionados, pergunta, chunks, final_k=5, cfg=CFG):
        colecao = _ColecaoFalsa(chunks)
        resultado, debug = rm._expandir_por_entidade(colecao, selecionados, pergunta, cfg, final_k)
        return resultado, debug, colecao

    def test_segue_o_codigo_ate_outro_documento_logo_apos_a_ancora(self):
        resultado, _, _ = self._expandir(
            [self.peca] + self.ruido, "fornecedor do tecido da calca operacional?", [self.linha_tx520],
        )
        self.assertEqual([c.chunk_id for c in resultado], ["man_4", "cat_520", "r0", "r1", "r2"])

    def test_ancora_e_o_melhor_casamento_lexical_nao_o_primeiro_colocado(self):
        distrator = _cand("cat_200", "Codigo: TX-200 / Fornecedor: Fiacao Aurora", "catalogo.csv", lexical=0.2, score=0.9)
        resultado, debug, _ = self._expandir(
            [distrator, self.peca], "fornecedor do tecido da calca operacional?", [self.linha_tx520],
        )
        self.assertEqual(debug["ancora"], "man_4")
        self.assertEqual([c.chunk_id for c in resultado], ["cat_200", "man_4", "cat_520"])

    def test_ignora_chunks_do_mesmo_documento_da_ancora(self):
        mesmo_doc = {"id": "man_9", "texto": "Revisao: tecido TX-520 substituido", "fonte": "manual.txt"}
        resultado, debug, _ = self._expandir([self.peca], "tecido da calca?", [mesmo_doc])
        self.assertEqual([c.chunk_id for c in resultado], ["man_4"])
        self.assertEqual(debug["adicionados"], [])

    def test_codigo_ja_citado_na_pergunta_nao_e_seguido(self):
        _, debug, colecao = self._expandir([self.peca], "qual o tecido da CL-440?", [self.linha_tx520])
        self.assertNotIn("CL-440", debug["codigos"])
        self.assertNotIn("CL-440", colecao.consultas)

    def test_casamento_respeita_fronteira_de_palavra(self):
        # "$contains": "TX-520" também acha "TX-5200" -- esse não pode entrar.
        resultado, _, _ = self._expandir([self.peca], "tecido da calca?", [self.linha_tx5200])
        self.assertEqual([c.chunk_id for c in resultado], ["man_4"])

    def test_chunk_ja_selecionado_e_promovido_nao_duplicado(self):
        ja_la = _cand("cat_520", self.linha_tx520["texto"], "catalogo.csv", lexical=0.1)
        resultado, _, _ = self._expandir(
            [self.peca] + self.ruido[:3] + [ja_la], "tecido da calca?", [self.linha_tx520],
        )
        ids = [c.chunk_id for c in resultado]
        self.assertEqual(ids, ["man_4", "cat_520", "r0", "r1", "r2"])

    def test_limite_de_chunks_adicionados(self):
        ancora = _cand("man_x", "Tecidos: TX-1 TX-11 TX-12 TX-13", "manual.txt", lexical=0.9)
        linhas = [{"id": f"cat_{c}", "texto": f"Codigo: {c}", "fonte": "catalogo.csv"} for c in ("TX-11", "TX-12", "TX-13")]
        resultado, _, _ = self._expandir([ancora], "tecidos?", linhas, cfg={"entity_hop_max_chunks": 2})
        self.assertEqual([c.chunk_id for c in resultado], ["man_x", "cat_TX-11", "cat_TX-12"])

    def test_ancora_sem_codigo_nao_muda_nada(self):
        selecionados = [_cand("a", "texto sem identificador", "manual.txt", lexical=0.5)]
        resultado, debug, colecao = self._expandir(selecionados, "pergunta", [self.linha_tx520])
        self.assertEqual(resultado, selecionados)
        self.assertEqual(colecao.consultas, [])

    def test_lista_vazia(self):
        resultado, _, _ = self._expandir([], "pergunta", [self.linha_tx520])
        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()
