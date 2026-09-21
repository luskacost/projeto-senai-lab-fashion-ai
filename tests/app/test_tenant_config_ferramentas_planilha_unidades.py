# -*- coding: utf-8 -*-
"""consultar_resumo_planilha e consultar_unidades_senai religadas (Fase 14, Bloco X, Task 11).

Igual ao caso do RAG na Fase 13, Task 17 (ver test_tenant_config_ferramentas_rag.py): as duas
ferramentas estavam registradas em agente_ferramentas.py com schema, handler e testes próprios,
mas nenhum modo as declarava em "tools" -- o README já as desenhava como ativas, mas na prática
nenhum modelo conseguia chamá-las.

`consultar_resumo_planilha` vai só em "Tendências" (a motivação documentada no registry --
agente_ferramentas.py:441-445 -- é cruzar a planilha da empresa com uma tendência de mercado
pesquisada na web, numa única resposta) e em "Assistente Geral" (único modo sem restrição de
escopo a moda). `consultar_unidades_senai` vai só em "Assistente Geral", pelo mesmo motivo de
escopo -- pedir o telefone de uma unidade SENAI não é uma pergunta de moda.
"""

import unittest

from agente_ferramentas import listar_nomes
from tenant_config import TENANT_CONFIG

MODOS_COM_RESUMO_PLANILHA = ["Tendências", "Assistente Geral"]
MODOS_COM_UNIDADES_SENAI = ["Assistente Geral"]
MODOS_SEM_NENHUMA_DAS_DUAS = ["Consultor de Estilo", "Professor Técnico", "Engenharia Têxtil", "Gerador de Croqui"]
MODOS_COM_PIPELINE_PROPRIO = ["Análise de Dados", "Base de Conhecimento"]


class TestFerramentasDePlanilhaEUnidadesPorModo(unittest.TestCase):

    def setUp(self):
        self.modos = TENANT_CONFIG["senai_labfashion"]["modos"]

    def test_ferramentas_estao_registradas_no_agente(self):
        nomes = listar_nomes()
        self.assertIn("consultar_resumo_planilha", nomes)
        self.assertIn("consultar_unidades_senai", nomes)

    def test_modos_esperados_declaram_consultar_resumo_planilha(self):
        for nome_modo in MODOS_COM_RESUMO_PLANILHA:
            with self.subTest(modo=nome_modo):
                self.assertIn("consultar_resumo_planilha", self.modos[nome_modo]["tools"] or [])

    def test_modos_esperados_declaram_consultar_unidades_senai(self):
        for nome_modo in MODOS_COM_UNIDADES_SENAI:
            with self.subTest(modo=nome_modo):
                self.assertIn("consultar_unidades_senai", self.modos[nome_modo]["tools"] or [])

    def test_modos_fora_de_escopo_nao_recebem_nenhuma_das_duas(self):
        for nome_modo in MODOS_SEM_NENHUMA_DAS_DUAS:
            with self.subTest(modo=nome_modo):
                tools = self.modos[nome_modo]["tools"] or []
                self.assertNotIn("consultar_resumo_planilha", tools)
                self.assertNotIn("consultar_unidades_senai", tools)

    def test_modos_com_pipeline_direto_continuam_sem_tools(self):
        for nome_modo in MODOS_COM_PIPELINE_PROPRIO:
            with self.subTest(modo=nome_modo):
                self.assertIsNone(self.modos[nome_modo]["tools"])


if __name__ == "__main__":
    unittest.main()
