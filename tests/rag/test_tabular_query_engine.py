# -*- coding: utf-8 -*-
"""Suíte Completa de Testes Automatizados para o Tabular Query Engine (Prioridade 3).

Valida operações matemáticas determinísticas (SUM, AVG, MIN, MAX, COUNT, GROUP_COUNT, RANK, DISTINCT),
filtros de campos ausentes e valores negativos, diferenciação de zero, seleção de documento e abas,
isolamento multi-tenant, ciclo de vida (reindexação e remoção) e não-regressão de PDFs e Prioridades 1 e 2.
"""

import io
import os
import unittest
from typing import Any, Dict, List

import document_extractors
import rag_manager
from rag_config import RAG_CONFIG
import tabular_query_engine
from tabular_query_engine import (
    TabularIntent,
    TabularQueryPlan,
    TabularQueryResult,
    detectar_e_planejar_consulta_tabular,
    executar_consulta_tabular,
    normalizar_query_texto,
    resolver_coluna
)
from tabular_storage import (
    TabularDocument,
    TabularRow,
    TabularSheet,
    carregar_documentos_tabulares,
    carregar_documento_tabular,
    remover_documento_tabular,
    salvar_documento_tabular
)


class TestTabularQueryEngine(unittest.TestCase):
    """Testes Unitários e de Integração do Motor de Consultas Tabulares."""

    TENANT_TESTE = "tenant_test_tabular"

    def setUp(self):
        # Garante limpeza inicial do tenant de teste
        rag_manager.remover_documento(self.TENANT_TESTE, "auditoria_teste.csv")
        rag_manager.remover_documento(self.TENANT_TESTE, "equipe_consultoria.csv")
        rag_manager.remover_documento(self.TENANT_TESTE, "multi_abas.xlsx")

    def tearDown(self):
        # Limpeza final
        rag_manager.remover_documento(self.TENANT_TESTE, "auditoria_teste.csv")
        rag_manager.remover_documento(self.TENANT_TESTE, "equipe_consultoria.csv")
        rag_manager.remover_documento(self.TENANT_TESTE, "multi_abas.xlsx")

    def test_a_count_global(self):
        """TESTE A: COUNT global - 10 registros na planilha retornam count == 10."""
        linhas_csv = "id,descricao,valor\n" + "\n".join(f"{i},Item {i},{i * 10}" for i in range(1, 11))
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quantos lançamentos existem?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.COUNT)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(res.value, 10)
        self.assertEqual(res.rows_scanned, 10)
        self.assertEqual(res.rows_matched, 10)
        self.assertIn("Total de registros encontrados: 10", res.formatted_result_block)

    def test_b_distinct(self):
        """TESTE B: DISTINCT - Valores repetidos de consultores são desduplicados determinísticamente."""
        linhas_csv = (
            "empresa,consultor\n"
            "Empresa A,Morgana\n"
            "Empresa B,Morgana\n"
            "Empresa C,Isabella\n"
            "Empresa D,Ana\n"
            "Empresa E,Isabella\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "equipe_consultoria.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "equipe_consultoria.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quais consultores existem?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.DISTINCT)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(set(res.value), {"Morgana", "Isabella", "Ana"})
        self.assertEqual(len(res.value), 3)

    def test_c_group_count(self):
        """TESTE C: GROUP COUNT - Quantidade de empresas atendidas por cada consultor."""
        linhas_csv = (
            "empresa,consultor\n"
            "Empresa A,Morgana\n"
            "Empresa B,Morgana\n"
            "Empresa C,Morgana\n"
            "Empresa D,Isabella\n"
            "Empresa E,Isabella\n"
            "Empresa F,Ana\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "equipe_consultoria.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "equipe_consultoria.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quantas empresas cada consultor atende?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.GROUP_COUNT)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        mapa = {g["grupo"]: g["contagem"] for g in res.groups}
        self.assertEqual(mapa["Morgana"], 3)
        self.assertEqual(mapa["Isabella"], 2)
        self.assertEqual(mapa["Ana"], 1)

    def test_d_rank(self):
        """TESTE D: RANK - Identifica o consultor que atende mais empresas."""
        linhas_csv = (
            "empresa,consultor\n"
            "Empresa A,Morgana\n"
            "Empresa B,Morgana\n"
            "Empresa C,Morgana\n"
            "Empresa D,Isabella\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "equipe_consultoria.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "equipe_consultoria.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Qual consultor atende mais empresas?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.RANK)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(len(res.groups), 1)
        self.assertEqual(res.groups[0]["grupo"], "Morgana")
        self.assertEqual(res.groups[0]["contagem"], 3)

    def test_e_sum(self):
        """TESTE E: SUM - Soma determinística de valores positivos e negativos."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,Reagentes,100.00\n"
            "2,Manutencao,200.00\n"
            "3,Estorno,-50.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Qual é a soma de todos os valores?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.SUM)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(res.value, 250.00)

    def test_f_avg(self):
        """TESTE F: AVG - Média aritmética determinística."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,A,10.00\n"
            "2,B,20.00\n"
            "3,C,30.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Qual é a média dos valores?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.intent, TabularIntent.AVG)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(res.value, 20.00)

    def test_g_min_max(self):
        """TESTE G: MIN e MAX com identificação correta de valores extremos."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,Item A,100.00\n"
            "2,Item B,20.00\n"
            "3,Item C,300.00\n"
            "4,Item D,-50.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        # MAX
        plano_max = detectar_e_planejar_consulta_tabular("Qual é o maior lançamento financeiro da planilha?", self.TENANT_TESTE)
        res_max = executar_consulta_tabular(plano_max, self.TENANT_TESTE)
        self.assertEqual(res_max.value["valor_extremo"], 300.00)
        self.assertEqual(res_max.value["registro"]["descricao"], "Item C")

        # MIN
        plano_min = detectar_e_planejar_consulta_tabular("Qual é o menor lançamento?", self.TENANT_TESTE)
        res_min = executar_consulta_tabular(plano_min, self.TENANT_TESTE)
        self.assertEqual(res_min.value["valor_extremo"], -50.00)
        self.assertEqual(res_min.value["registro"]["descricao"], "Item D")

    def test_h_filtro_negativo(self):
        """TESTE H: Filtro de valores negativos retorna apenas registros abaixo de zero."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,Compra,100.00\n"
            "2,Devolucao,-35.50\n"
            "3,Ajuste,-120.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quais lançamentos possuem valor negativo?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)

        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertEqual(res.rows_matched, 2)
        self.assertTrue(all(float(r["valor"]) < 0 for r in res.records))

    def test_i_contagem_negativos(self):
        """TESTE I: Contagem de lançamentos negativos."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,Compra,100.00\n"
            "2,Devolucao,-35.50\n"
            "3,Ajuste,-120.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quantos lançamentos possuem valor negativo?", self.TENANT_TESTE)
        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertEqual(res.value, 2)

    def test_j_campo_ausente(self):
        """TESTE J: Detecção de registros com campo responsável não preenchido."""
        linhas_csv = (
            "id,descricao,responsavel\n"
            "1,Item 1,Ana\n"
            "2,Item 2,\n"
            "3,Item 3,Bruno\n"
            "4,Item 4,\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quais registros estão sem responsável?", self.TENANT_TESTE)
        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertEqual(res.rows_matched, 2)
        ids_encontrados = [r["id"] for r in res.records]
        self.assertEqual(ids_encontrados, ["2", "4"])

    def test_k_zero_nao_e_ausencia(self):
        """TESTE K: Zero numérico (0.00) NÃO é classificado como ausente."""
        linhas_csv = (
            "id,descricao,valor\n"
            "1,Taxa Isenta,0.00\n"
            "2,Pendente,\n"
            "3,Compra,100.00\n"
        )
        stream = io.BytesIO(linhas_csv.encode("utf-8"))
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", unidades, dados_tabulares=sheets)

        # Ausentes: deve ser apenas 1 (linha 2)
        plano_aus = detectar_e_planejar_consulta_tabular("Quantos valores estão ausentes?", self.TENANT_TESTE)
        res_aus = executar_consulta_tabular(plano_aus, self.TENANT_TESTE)
        self.assertEqual(res_aus.value, 1)

        # Iguais a zero: deve ser 1 (linha 1)
        plano_zero = detectar_e_planejar_consulta_tabular("Quantos valores são iguais a zero?", self.TENANT_TESTE)
        res_zero = executar_consulta_tabular(plano_zero, self.TENANT_TESTE)
        self.assertEqual(res_zero.value, 1)

    def test_l_xlsx_multiplas_abas(self):
        """TESTE L: Planilha com múltiplas abas seleciona a aba correta com base nas colunas."""
        import openpyxl
        wb = openpyxl.Workbook()
        
        # Aba 1: Vendas
        ws1 = wb.active
        ws1.title = "Vendas"
        ws1.append(["id", "mes", "faturamento"])
        ws1.append([1, "Janeiro", 50000.0])

        # Aba 2: Consultores
        ws2 = wb.create_sheet(title="Consultores")
        ws2.append(["empresa", "consultor"])
        ws2.append(["Empresa Alpha", "Morgana"])
        ws2.append(["Empresa Beta", "Isabella"])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(stream, "multi_abas.xlsx")
        rag_manager.indexar_documento(self.TENANT_TESTE, "multi_abas.xlsx", unidades, dados_tabulares=sheets)

        plano = detectar_e_planejar_consulta_tabular("Quantas empresas cada consultor atende?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.target_sheet, "Consultores")
        self.assertEqual(plano.target_document, "multi_abas.xlsx")

    def test_m_selecao_documento(self):
        """TESTE M: Seleciona o documento estruturado correto entre múltiplos disponíveis."""
        csv1 = "id,data,descricao,valor\n1,2026-06-01,Despesa,500.00"
        csv2 = "empresa,consultor\nEmpresa A,Morgana"

        u1, s1 = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv1.encode("utf-8")), "auditoria_teste.csv")
        u2, s2 = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv2.encode("utf-8")), "equipe_consultoria.csv")

        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", u1, dados_tabulares=s1)
        rag_manager.indexar_documento(self.TENANT_TESTE, "equipe_consultoria.csv", u2, dados_tabulares=s2)

        plano = detectar_e_planejar_consulta_tabular("Qual consultor atende mais empresas?", self.TENANT_TESTE)
        self.assertIsNotNone(plano)
        self.assertEqual(plano.target_document, "equipe_consultoria.csv")

    def test_n_isolamento_multi_tenant(self):
        """TESTE N: Isolamento estrito - dados do Tenant A não afetam consultas do Tenant B."""
        t_a = "tenant_a_strict"
        t_b = "tenant_b_strict"

        csv_a = "id,valor\n" + "\n".join(f"{i},10.00" for i in range(1, 11))   # 10 linhas
        csv_b = "id,valor\n" + "\n".join(f"{i},10.00" for i in range(1, 51))   # 50 linhas

        u_a, s_a = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv_a.encode("utf-8")), "dados.csv")
        u_b, s_b = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv_b.encode("utf-8")), "dados.csv")

        rag_manager.indexar_documento(t_a, "dados.csv", u_a, dados_tabulares=s_a)
        rag_manager.indexar_documento(t_b, "dados.csv", u_b, dados_tabulares=s_b)

        plano_a = detectar_e_planejar_consulta_tabular("Quantos lançamentos existem?", t_a)
        res_a = executar_consulta_tabular(plano_a, t_a)

        plano_b = detectar_e_planejar_consulta_tabular("Quantos lançamentos existem?", t_b)
        res_b = executar_consulta_tabular(plano_b, t_b)

        # Limpeza
        rag_manager.remover_documento(t_a, "dados.csv")
        rag_manager.remover_documento(t_b, "dados.csv")

        self.assertEqual(res_a.value, 10)
        self.assertEqual(res_b.value, 50)

    def test_o_reindexacao_sem_duplicacao(self):
        """TESTE O: Reindexação substitui atomicamente os dados sem duplicar linhas."""
        csv_v1 = "id,valor\n" + "\n".join(f"{i},100.00" for i in range(1, 11))  # 10 linhas
        csv_v2 = "id,valor\n" + "\n".join(f"{i},100.00" for i in range(1, 6))   # 5 linhas

        u1, s1 = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv_v1.encode("utf-8")), "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", u1, dados_tabulares=s1)

        # Reindexação com v2
        u2, s2 = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv_v2.encode("utf-8")), "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", u2, dados_tabulares=s2)

        plano = detectar_e_planejar_consulta_tabular("Quantos lançamentos existem?", self.TENANT_TESTE)
        res = executar_consulta_tabular(plano, self.TENANT_TESTE)
        self.assertEqual(res.value, 5)

    def test_p_remocao_de_documento(self):
        """TESTE P: Remoção de documento apaga os dados estruturados do storage tabular."""
        csv = "id,valor\n1,50.00"
        u, s = document_extractors.extrair_documento_com_dados_tabulares(io.BytesIO(csv.encode("utf-8")), "auditoria_teste.csv")
        rag_manager.indexar_documento(self.TENANT_TESTE, "auditoria_teste.csv", u, dados_tabulares=s)

        doc_antes = carregar_documento_tabular(self.TENANT_TESTE, "auditoria_teste.csv")
        self.assertIsNotNone(doc_antes)

        rag_manager.remover_documento(self.TENANT_TESTE, "auditoria_teste.csv")
        doc_depois = carregar_documento_tabular(self.TENANT_TESTE, "auditoria_teste.csv")
        self.assertIsNone(doc_depois)

    def test_q_fallback_rag_pergunta_conceitual(self):
        """TESTE Q: Pergunta conceitual em PDF faz fallback para o RAG vetorial sem acionar motor tabular."""
        plano = detectar_e_planejar_consulta_tabular("Qual é a gramatura do tecido M518?", "senai_labfashion")
        self.assertIsNone(plano)

    def test_r_retrocompatibilidade_pdf(self):
        """TESTE R: Consultas em PDF continuam recuperando evidências exatas."""
        res = rag_manager.buscar_contexto_relevante("senai_labfashion", "Qual é a largura do tecido da camisa jeans?", final_k=3)
        self.assertTrue(len(res) > 0)
        self.assertTrue(any("172" in c["texto"] for c in res))

    def test_s_nao_regressao_prioridade_1(self):
        """TESTE S: Não-regressão da Prioridade 1 (Reranker, N-grams, Cia Militar)."""
        res = rag_manager.buscar_contexto_relevante("senai_labfashion", "Quem é responsável por atender a empresa Cia Militar?", final_k=3)
        self.assertTrue(len(res) > 0)
        self.assertTrue(any("Morgana" in c["texto"] for c in res))

    def test_t_nao_regressao_prioridade_2(self):
        """TESTE T: Não-regressão da Prioridade 2 (Semantic Enrichment [VALOR_NEGATIVO])."""
        res = rag_manager.buscar_contexto_relevante("senai_labfashion", "Existe algum lançamento com valor negativo?", final_k=3)
        self.assertTrue(len(res) > 0)
        textos = [c["texto"] for c in res]
        self.assertTrue(any("-150" in t or "[VALOR_NEGATIVO]" in t for t in textos))


if __name__ == "__main__":
    unittest.main()
