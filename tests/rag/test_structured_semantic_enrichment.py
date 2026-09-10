# -*- coding: utf-8 -*-
"""Suíte de Testes Automatizados de Enriquecimento Semântico de Dados Estruturados (Prioridade 2).
Valida detecção de números negativos, valores zero, campos ausentes/vazios, datas legíveis,
preservação de metadados, compatibilidade com múltiplos formatos e isolamento multi-tenant.
"""

import io
import os
import shutil
import unittest
from typing import Dict, Any, List

import document_extractors
import rag_manager
from rag_config import RAG_CONFIG
from semantic_enrichment import (
    enriquecer_registro_estruturado,
    normalizar_nome_coluna,
    _eh_valor_vazio,
    _eh_valor_zero,
    _formatar_data_legivel,
    _parse_numero_generico
)
from .fixtures_prioridades_rag import indexar_fixtures_prioridades, remover_fixtures_prioridades


class TestStructuredSemanticEnrichment(unittest.TestCase):
    """Testes Automatizados para a Prioridade 2 - Enriquecimento Semântico."""

    # Tenant de teste dedicado com fixtures sintéticas próprias (ver fixtures_prioridades_rag.py)
    # -- antes usava o tenant real "senai_labfashion", assumindo conteúdo pré-indexado localmente
    # que nunca esteve sob controle de versão, o que quebrava numa máquina/CI limpa.
    TENANT_TESTE = "teste_prioridades_enriquecimento"

    @classmethod
    def setUpClass(cls):
        caminho_chroma = os.path.join("tenant_data", "chroma", cls.TENANT_TESTE)
        if os.path.exists(caminho_chroma):
            shutil.rmtree(caminho_chroma, ignore_errors=True)
        cls.pdf_temp_path = "temp_manual_tecnico_enriquecimento.pdf"
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

    def test_a_valor_negativo(self):
        """TESTE A: valor: -150.00 gera [VALOR_NEGATIVO], preserva o dado e é recuperável."""
        registro = [
            ("id", "6"),
            ("descricao", "Compra de luvas descartaveis"),
            ("valor", "-150.00"),
            ("responsavel", "Bruno Costa")
        ]
        enriquecido = enriquecer_registro_estruturado(registro)
        
        # 1. Registro original preservado
        self.assertIn("valor: -150.00", enriquecido.texto_formatado)
        self.assertIn("Bruno Costa", enriquecido.texto_formatado)
        
        # 2. Marcadores e propriedades
        self.assertIn("[VALOR_NEGATIVO]", enriquecido.marcadores_estruturados)
        self.assertIn("[VALOR_ABAIXO_DE_ZERO]", enriquecido.marcadores_estruturados)
        self.assertTrue(enriquecido.metadados_derivados["tem_valor_negativo"])
        
        # 3. Recuperação via RAG
        resultados = rag_manager.buscar_contexto_relevante(
            self.TENANT_TESTE,
            "Existe algum lançamento com valor negativo?",
            final_k=5
        )
        textos = [r["texto"].lower() for r in resultados]
        self.assertTrue(any("-150" in t or "valor_negativo" in t for t in textos))

    def test_b_zero_nao_e_ausencia(self):
        """TESTE B: valor: 0.00 é reconhecido como zero e NÃO é classificado como ausente."""
        registro = [
            ("id", "2"),
            ("item", "Taxa administrativa"),
            ("valor", "0.00"),
            ("responsavel", "Carlos")
        ]
        enriquecido = enriquecer_registro_estruturado(registro)
        
        # Reconhecido como zero
        self.assertIn("[VALOR_ZERO]", enriquecido.marcadores_estruturados)
        self.assertTrue(enriquecido.metadados_derivados["tem_valor_zero"])
        
        # NÃO é classificado como ausente/vazio
        self.assertNotIn("[CAMPO_VAZIO:VALOR]", enriquecido.marcadores_estruturados)
        self.assertNotIn("[VALOR_AUSENTE]", enriquecido.marcadores_estruturados)
        self.assertFalse(enriquecido.metadados_derivados["tem_campo_ausente"])

    def test_c_campo_responsavel_vazio(self):
        """TESTE C: responsavel: '' é detectado como [RESPONSAVEL_AUSENTE] e [CAMPO_VAZIO:RESPONSAVEL]."""
        registro = [
            ("id", "10"),
            ("descricao", "Compra de papel"),
            ("valor", "45.30"),
            ("responsavel", "")
        ]
        enriquecido = enriquecer_registro_estruturado(registro)
        
        self.assertIn("[RESPONSAVEL_AUSENTE]", enriquecido.marcadores_estruturados)
        self.assertIn("[CAMPO_VAZIO:RESPONSAVEL]", enriquecido.marcadores_estruturados)
        self.assertTrue(enriquecido.metadados_derivados["tem_campo_ausente"])
        self.assertEqual(enriquecido.metadados_derivados["campos_ausentes"], "responsavel")
        self.assertIn("responsavel: não informado", enriquecido.texto_formatado)

    def test_d_campo_responsavel_inexistente(self):
        """TESTE D: Registro sem a chave 'responsavel' é marcado como inexistente quando comparado ao schema."""
        registro = [
            ("id", "1"),
            ("item", "Parafuso"),
            ("quantidade", "100")
        ]
        colunas_esperadas = ["id", "item", "quantidade", "responsavel"]
        enriquecido = enriquecer_registro_estruturado(registro, colunas_esperadas=colunas_esperadas)
        
        self.assertIn("[CAMPO_RESPONSAVEL_INEXISTENTE]", enriquecido.marcadores_estruturados)
        self.assertTrue(any("inexistente" in p for p in enriquecido.propriedades_detectadas))

    def test_e_data_legivel(self):
        """TESTE E: Data ISO (2026-06-10) preserva original e adiciona representação legível."""
        registro = [
            ("data", "2026-06-10"),
            ("evento", "Reunião de Alinhamento")
        ]
        enriquecido = enriquecer_registro_estruturado(registro)
        
        # Original preservado e forma por extenso adicionada
        self.assertIn("2026-06-10", enriquecido.texto_formatado)
        self.assertIn("10 de junho de 2026", enriquecido.texto_formatado)

    def test_f_numero_negativo_nao_financeiro(self):
        """TESTE F: temperatura: -5 gera [TEMPERATURA_NEGATIVA] e NÃO [VALOR_NEGATIVO]."""
        registro = [
            ("id", "55"),
            ("sensor", "Camara Fria"),
            ("temperatura", "-5")
        ]
        enriquecido = enriquecer_registro_estruturado(registro)
        
        self.assertIn("[TEMPERATURA_NEGATIVA]", enriquecido.marcadores_estruturados)
        self.assertIn("[NUMERO_NEGATIVO:TEMPERATURA]", enriquecido.marcadores_estruturados)
        self.assertNotIn("[VALOR_NEGATIVO]", enriquecido.marcadores_estruturados)
        self.assertNotIn("[VALOR_ABAIXO_DE_ZERO]", enriquecido.marcadores_estruturados)

    def test_g_preservacao_linha_xlsx(self):
        """TESTE G: Extração de XLSX tabular mantém aba, linha, rotulo_unidade e texto estruturado."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Dados_Auditoria"
        ws.append(["id", "descricao", "valor", "responsavel"])
        ws.append([1, "Item Teste", -50.0, ""])
        
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        
        unidades = document_extractors.extrair_documento(stream, "teste_planilha.xlsx")
        self.assertEqual(len(unidades), 1)
        u = unidades[0]
        
        self.assertEqual(u["metadados"]["aba"], "Dados_Auditoria")
        self.assertEqual(u["metadados"]["linha"], 2)
        self.assertIn("Aba: Dados_Auditoria", u["texto"])
        self.assertIn("[VALOR_NEGATIVO]", u["texto"])
        self.assertIn("[RESPONSAVEL_AUSENTE]", u["texto"])
        self.assertTrue(u["metadados"]["tem_valor_negativo"])
        self.assertTrue(u["metadados"]["tem_campo_ausente"])

    def test_h_csv_encoding_e_delimitadores(self):
        """TESTE H: CSV com ponto-e-vírgula e acentos é extraído e enriquecido corretamente."""
        csv_conteudo = (
            "Código;Descrição;Valor;Responsável\n"
            "101;Compra de reagentes;-250,50;João da Silva\n"
            "102;Serviço de limpeza;0,00;\n"
        )
        stream = io.BytesIO(csv_conteudo.encode("latin-1"))
        unidades = document_extractors.extrair_documento(stream, "teste_latin.csv")
        
        self.assertEqual(len(unidades), 2)
        u1 = unidades[0]
        u2 = unidades[1]
        
        # Linha 1: Valor negativo
        self.assertIn("[VALOR_NEGATIVO]", u1["texto"])
        self.assertTrue(u1["metadados"]["tem_valor_negativo"])
        
        # Linha 2: Valor zero e responsável ausente
        self.assertIn("[VALOR_ZERO]", u2["texto"])
        self.assertIn("[RESPONSAVEL_AUSENTE]", u2["texto"])
        self.assertTrue(u2["metadados"]["tem_valor_zero"])
        self.assertTrue(u2["metadados"]["tem_campo_ausente"])

    def test_i_xls_legado(self):
        """TESTE I: Planilha XLS legada é processada com enriquecimento semântico."""
        caminho_fixture = os.path.join("tests", "fixtures", "estoque_legado.xls")
        if not os.path.exists(caminho_fixture):
            self.skipTest(f"Fixture '{caminho_fixture}' não encontrada no repositório.")
        
        unidades = document_extractors.extrair_documento(caminho_fixture, nome_arquivo="estoque_legado.xls")
        self.assertTrue(len(unidades) > 0)
        self.assertEqual(unidades[0]["metadados"]["tipo_arquivo"], "xls")

    def test_j_regressao_pdf_inalterada(self):
        """TESTE J: Consulta técnica em PDF continua retornando o trecho exato sem poluição."""
        query = "Qual é a gramatura do tecido M518?"
        resultados = rag_manager.buscar_contexto_relevante(self.TENANT_TESTE, query, final_k=5)
        
        self.assertTrue(len(resultados) > 0)
        self.assertIn("Manual Tecnico - UNIFORMES CAMISA.pdf", [r["fonte"] for r in resultados])
        self.assertTrue(any("128" in r["texto"] for r in resultados))

    def test_k_multi_tenant_isolamento(self):
        """TESTE K: Registros enriquecidos em tenants distintos não vazam entre si."""
        t1 = "tenant_enrich_alpha"
        t2 = "tenant_enrich_beta"
        
        csv_t1 = "id,valor,responsavel\n1,-9999.00,Agente Alpha"
        csv_t2 = "id,valor,responsavel\n1,-8888.00,Agente Beta"
        
        u1 = document_extractors.extrair_documento(io.BytesIO(csv_t1.encode("utf-8")), "doc1.csv")
        u2 = document_extractors.extrair_documento(io.BytesIO(csv_t2.encode("utf-8")), "doc2.csv")
        
        rag_manager.indexar_documento(t1, "doc1.csv", u1)
        rag_manager.indexar_documento(t2, "doc2.csv", u2)
        
        res1 = rag_manager.buscar_contexto_relevante(t1, "Existe algum lançamento com valor negativo?", final_k=5)
        res2 = rag_manager.buscar_contexto_relevante(t2, "Existe algum lançamento com valor negativo?", final_k=5)
        
        # Limpeza
        rag_manager.remover_documento(t1, "doc1.csv")
        rag_manager.remover_documento(t2, "doc2.csv")
        
        self.assertTrue(any("-9999" in r["texto"] for r in res1))
        self.assertFalse(any("-8888" in r["texto"] for r in res1))
        self.assertTrue(any("-8888" in r["texto"] for r in res2))
        self.assertFalse(any("-9999" in r["texto"] for r in res2))


if __name__ == "__main__":
    unittest.main()
