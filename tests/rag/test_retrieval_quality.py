# -*- coding: utf-8 -*-
"""Testes Automatizados de Qualidade de Retrieval, Pool Amplo e Reranking.
Valida os critérios da Prioridade 1: eliminação de contaminação e preservação de chunks relevantes.
"""

import os
import shutil
import unittest
from typing import Dict, Any, List

from rag_config import RAG_CONFIG
import rag_manager
from query_engine import analisar_query_completa
from reranker import HeuristicReranker, CandidateChunk, selecionar_com_cobertura_e_diversidade
from .fixtures_prioridades_rag import indexar_fixtures_prioridades, remover_fixtures_prioridades


class TestRetrievalQualityAndTopK(unittest.TestCase):
    """Bateria de testes automatizados para validar a Prioridade 1 de Retrieval."""

    # Tenant de teste dedicado com fixtures sintéticas próprias (ver fixtures_prioridades_rag.py)
    # -- antes usava o tenant real "senai_labfashion", assumindo conteúdo pré-indexado localmente
    # que nunca esteve sob controle de versão, o que quebrava numa máquina/CI limpa.
    TENANT_TESTE = "teste_prioridades_retrieval"

    @classmethod
    def setUpClass(cls):
        caminho_chroma = os.path.join("tenant_data", "chroma", cls.TENANT_TESTE)
        if os.path.exists(caminho_chroma):
            shutil.rmtree(caminho_chroma, ignore_errors=True)
        cls.pdf_temp_path = "temp_manual_tecnico_retrieval_quality.pdf"
        indexar_fixtures_prioridades(cls.TENANT_TESTE, cls.pdf_temp_path)

    @classmethod
    def tearDownClass(cls):
        remover_fixtures_prioridades(cls.TENANT_TESTE)
        caminho_chroma = os.path.join("tenant_data", "chroma", cls.TENANT_TESTE)
        if os.path.exists(caminho_chroma):
            shutil.rmtree(caminho_chroma, ignore_errors=True)
        if os.path.exists(cls.pdf_temp_path):
            try:
                os.remove(cls.pdf_temp_path)
            except Exception:
                pass

    def test_a_pool_inicial_amplo_configurado(self):
        """TESTE A: Verifica que a busca inicial utiliza pool configurável maior que o final_k."""
        self.assertGreaterEqual(RAG_CONFIG.get("base_retrieval_top_k", 0), 20)
        self.assertGreaterEqual(RAG_CONFIG.get("per_query_top_k", 0), 10)
        self.assertGreaterEqual(RAG_CONFIG.get("retrieval_candidate_pool_size", 0), 20)
        self.assertEqual(RAG_CONFIG.get("final_context_top_k", 5), 5)

    def test_b_chunk_relevante_nao_perdido_por_corte_prematuro(self):
        """TESTE B: Verifica que um candidato na posição > 10 da busca bruta é capturado pelo pool e promovido."""
        query = "Quem atende a empresa Cia Militar?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=30, final_k=5)
        
        # O chunk da planilha com cia militar deve estar no resultado final
        textos = [r["texto"].lower() for r in resultados]
        fontes = [r["fonte"] for r in resultados]
        
        self.assertTrue(any("cia militar" in t for t in textos), "Chunk contendo 'cia militar' deve estar presente no top-k final.")
        self.assertIn("empresas_consultores.csv", fontes, "Planilha empresas_consultores.csv deve estar entre as fontes.")

    def test_c_remocao_de_resultado_irrelevante_por_threshold_relativo(self):
        """TESTE C: Verifica que chunks com score muito inferior ao melhor candidato são descartados."""
        qa = analisar_query_completa("Qual é a gramatura do tecido M518?", RAG_CONFIG)
        cands = [
            CandidateChunk(
                chunk_id="c1",
                texto="Tecido M518 com gramatura de 128 g/m2.",
                metadata={"fonte": "doc_relevante.pdf"},
                final_score=0.85
            ),
            CandidateChunk(
                chunk_id="c2",
                texto="Manual de sustentabilidade e processos gerais de TI.",
                metadata={"fonte": "doc_lixo.pdf"},
                final_score=0.22
            ),
            CandidateChunk(
                chunk_id="c3",
                texto="Introdução aos conceitos gerais da empresa.",
                metadata={"fonte": "doc_lixo2.pdf"},
                final_score=0.19
            )
        ]
        
        selecionados = selecionar_com_cobertura_e_diversidade(cands, qa, RAG_CONFIG, final_k=5)
        
        self.assertEqual(len(selecionados), 1, "Apenas o candidato com score alto deve sobreviver ao threshold relativo.")
        self.assertEqual(selecionados[0].chunk_id, "c1")

    def test_d_consulta_cia_militar(self):
        """TESTE D: Executa consulta Cia Militar e valida recuperação de Morgana."""
        query = "Quem atende a empresa Cia Militar?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, final_k=5)
        
        self.assertTrue(len(resultados) > 0)
        chunk_cia = [r for r in resultados if "cia militar" in r["texto"].lower()]
        self.assertTrue(len(chunk_cia) > 0, "Chunk de Cia Militar deve ser recuperado.")
        self.assertIn("Morgana", chunk_cia[0]["texto"])

    def test_e_consulta_yaz_fit_sem_regressao(self):
        """TESTE E: Executa consulta YAZ FIT e confirma presença de Isabella sem regressão."""
        query = "Qual consultor está associado à empresa YAZ FIT & CASUAL LTDA?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, final_k=5)
        
        self.assertTrue(len(resultados) > 0)
        self.assertIn("empresas_consultores.csv", [r["fonte"] for r in resultados])
        self.assertTrue(any("Isabella" in r["texto"] for r in resultados))

    def test_f_anti_alucinacao_preservada(self):
        """TESTE G: Pergunta inexistente não deve resgatar fontes inadequadas."""
        query = "Qual é o CNPJ da empresa YAZ FIT & CASUAL LTDA?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, final_k=5)
        
        # Os resultados retornados não devem conter menção inventada de CNPJ
        for r in resultados:
            self.assertNotIn("00.000.000/0001-00", r["texto"])

    def test_g_pdf_compatibilidade(self):
        """TESTE H: Consulta técnica em PDF funciona sem regressão."""
        query = "Qual é a gramatura do tecido M518?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, final_k=5)
        
        self.assertTrue(len(resultados) > 0)
        self.assertIn("Manual Tecnico - UNIFORMES CAMISA.pdf", [r["fonte"] for r in resultados])
        self.assertTrue(any("128" in r["texto"] or "m518" in r["texto"].lower() for r in resultados))

    def test_h_multi_tenant_isolamento(self):
        """TESTE I: Isolamento multi-tenant intacto."""
        t_a = "test_tenant_a_retrieval"
        t_b = "test_tenant_b_retrieval"
        
        rag_manager.indexar_documento(t_a, "doc_a.txt", "Segredo exclusivo do Tenant A: ALPHA-777")
        rag_manager.indexar_documento(t_b, "doc_b.txt", "Segredo exclusivo do Tenant B: BETA-888")
        
        res_a = rag_manager.buscar_contexto_relevante(t_a, "Qual é o segredo exclusivo?", final_k=5)
        res_b = rag_manager.buscar_contexto_relevante(t_b, "Qual é o segredo exclusivo?", final_k=5)
        
        # Limpeza
        rag_manager.remover_documento(t_a, "doc_a.txt")
        rag_manager.remover_documento(t_b, "doc_b.txt")
        
        self.assertTrue(any("ALPHA-777" in r["texto"] for r in res_a))
        self.assertFalse(any("BETA-888" in r["texto"] for r in res_a))
        self.assertTrue(any("BETA-888" in r["texto"] for r in res_b))
        self.assertFalse(any("ALPHA-777" in r["texto"] for r in res_b))


if __name__ == "__main__":
    unittest.main()
