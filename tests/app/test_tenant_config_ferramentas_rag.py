# -*- coding: utf-8 -*-
"""RAG religado nos modos baseados em agente (Fase 13, Task 17).

`buscar_documentos_internos`/`listar_documentos_disponiveis` estavam registradas em
`agente_ferramentas.py`, com schema, handler e testes próprios -- mas nenhum modo as declarava em
`"tools"`, então nunca eram de fato oferecidas ao modelo. Este teste trava que os modos que
passam por `_chat_via_agente` (ver api/main.py::chat) as recebem, e que os dois modos com
pipeline direto próprio (que nunca leem a chave "tools") continuam sem elas -- adicionar ali
não teria efeito nenhum, só sujaria a config.
"""

import unittest

from agente_ferramentas import listar_nomes
from tenant_config import TENANT_CONFIG

MODOS_VIA_AGENTE_COM_RAG = [
    "Consultor de Estilo",
    "Professor Técnico",
    "Engenharia Têxtil",
    "Tendências",
    "Assistente Geral",
]
MODOS_COM_PIPELINE_PROPRIO = ["Análise de Dados", "Base de Conhecimento"]


class TestFerramentasDeRagPorModo(unittest.TestCase):

    def setUp(self):
        self.modos = TENANT_CONFIG["senai_labfashion"]["modos"]

    def test_ferramentas_de_rag_estao_registradas_no_agente(self):
        nomes = listar_nomes()
        self.assertIn("buscar_documentos_internos", nomes)
        self.assertIn("listar_documentos_disponiveis", nomes)

    def test_modos_via_agente_declaram_as_ferramentas_de_rag(self):
        for nome_modo in MODOS_VIA_AGENTE_COM_RAG:
            with self.subTest(modo=nome_modo):
                tools = self.modos[nome_modo]["tools"] or []
                self.assertIn("buscar_documentos_internos", tools)
                self.assertIn("listar_documentos_disponiveis", tools)

    def test_modos_com_pipeline_direto_nao_precisam_da_ferramenta(self):
        # "tools" nunca é lido para estes dois modos (pipeline próprio em api/main.py::chat) --
        # continuam None por não ter efeito, não por esquecimento.
        for nome_modo in MODOS_COM_PIPELINE_PROPRIO:
            with self.subTest(modo=nome_modo):
                self.assertIsNone(self.modos[nome_modo]["tools"])

    def test_gerador_de_croqui_no_recebe_a_ferramenta_de_rag(self):
        # Fluxo de confirmação próprio, específico às tools de geração -- fora do escopo desta task.
        tools = self.modos["Gerador de Croqui"]["tools"]
        self.assertNotIn("buscar_documentos_internos", tools)


if __name__ == "__main__":
    unittest.main()
