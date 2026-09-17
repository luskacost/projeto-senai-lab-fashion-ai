# -*- coding: utf-8 -*-
"""Guarda de regressão contra a baseline oficial (Fase 13, Task 9).

`rag_baseline_fase13.json` é o número medido e documentado em `RAG_BASELINE_FASE13.md` -- a régua
contra a qual toda mudança do Bloco F3 (Tasks 10-14) precisa se provar melhor, nunca pior. Este
teste roda o MESMO golden set agora e falha se algum número piorou, sem depender de ninguém lembrar
de rodar `scripts/medir_baseline_rag.py` manualmente antes de revisar uma mudança de reranking.

Não usa `assertGreaterEqual` cru: uma flutuação de ponto flutuante de 1e-9 não é regressão.
`TOLERANCIA` absorve ruído sem esconder uma piora de verdade.
"""

import json
import os
import shutil
import unittest

import rag_eval
import rag_golden_set as gs
import rag_manager as rm

CAMINHO_BASELINE = os.path.join(os.path.dirname(__file__), "..", "..", "rag_baseline_fase13.json")
TENANT_TESTE = "teste_fase13_baseline_regressao"
TOLERANCIA = 1e-6


class TestNaoRegrideContraABaseline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(CAMINHO_BASELINE, encoding="utf-8") as f:
            cls.baseline = json.load(f)

        cls._limpar()
        gs.indexar_corpus(TENANT_TESTE)
        casos = gs.casos(TENANT_TESTE)
        resultados = rag_eval.executar_conjunto(casos, k=cls.baseline["k"])
        chunks = rag_eval.carregar_chunks_do_tenant(TENANT_TESTE)
        cls.atual = rag_eval.resumir_avaliacao(casos, resultados, chunks, k=cls.baseline["k"])

    @classmethod
    def tearDownClass(cls):
        cls._limpar()

    @classmethod
    def _limpar(cls):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)

    def test_baseline_e_o_mesmo_k_desta_execucao(self):
        self.assertEqual(self.atual["k"], self.baseline["k"])

    def test_recall_nao_regrediu(self):
        self.assertGreaterEqual(
            self.atual["recuperaveis"]["recall_medio"],
            self.baseline["recuperaveis"]["recall_medio"] - TOLERANCIA,
        )

    def test_ndcg_nao_regrediu(self):
        self.assertGreaterEqual(
            self.atual["recuperaveis"]["ndcg_medio"],
            self.baseline["recuperaveis"]["ndcg_medio"] - TOLERANCIA,
        )

    def test_mrr_nao_regrediu(self):
        self.assertGreaterEqual(
            self.atual["recuperaveis"]["mrr"],
            self.baseline["recuperaveis"]["mrr"] - TOLERANCIA,
        )

    def test_taxa_de_abstencao_correta_nao_regrediu(self):
        # A garantia mais importante do sistema: nunca alucinar quando a base não tem resposta.
        # Qualquer queda aqui é crítica, não só uma regressão de qualidade.
        self.assertGreaterEqual(
            self.atual["abstencao"]["taxa"], self.baseline["abstencao"]["taxa"] - TOLERANCIA,
        )

    def test_taxa_de_acerto_computado_nao_regrediu(self):
        self.assertGreaterEqual(
            self.atual["computados"]["taxa"], self.baseline["computados"]["taxa"] - TOLERANCIA,
        )

    def test_nenhuma_categoria_regrediu(self):
        # O agregado esconde trocas: uma melhora grande numa categoria pode mascarar a piora de
        # outra (aconteceu no desenvolvimento do salto por entidade, com tabular_filtro).
        metricas = {
            "recuperaveis": ("recall_medio", "ndcg_medio", "mrr"),
            "abstencao": ("taxa",),
            "computados": ("taxa",),
        }
        for categoria, grupos in self.baseline["por_categoria"].items():
            for grupo, registro in grupos.items():
                if grupo not in metricas:
                    continue
                for metrica in metricas[grupo]:
                    with self.subTest(categoria=categoria, grupo=grupo, metrica=metrica):
                        self.assertGreaterEqual(
                            self.atual["por_categoria"][categoria][grupo][metrica],
                            registro[metrica] - TOLERANCIA,
                        )

    def test_quantidade_de_casos_por_grupo_nao_mudou(self):
        # Se este número mudar, o golden set foi editado -- a comparação deixou de ser
        # "mesmo teste, pipeline diferente" e passou a ser "teste diferente", que invalida
        # qualquer conclusão dos testes acima.
        for grupo in ("recuperaveis", "abstencao", "computados"):
            with self.subTest(grupo=grupo):
                self.assertEqual(self.atual[grupo]["n"], self.baseline[grupo]["n"])


if __name__ == "__main__":
    unittest.main()
