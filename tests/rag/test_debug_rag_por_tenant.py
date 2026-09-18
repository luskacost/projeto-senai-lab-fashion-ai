# -*- coding: utf-8 -*-
"""`obter_ultimo_rag_debug` segmentado por tenant (Fase 13, Task 16).

Antes: `_ULTIMO_RAG_DEBUG` era uma única variável de módulo, reescrita a cada busca de QUALQUER
tenant. `obter_ultimo_rag_debug()` sem argumento devolvia sempre a mais recente -- se o tenant A
buscasse "qual o CNPJ do cliente X" e o tenant B chamasse a rota logo depois, via a pergunta e os
chunks inteiros da busca de A. Este teste substitui `_ULTIMO_RAG_DEBUG_POR_TENANT` diretamente
(não roda `buscar_contexto_relevante` de verdade) para isolar só o comportamento da segmentação.
"""

import unittest

import rag_manager as rm


class TestSegmentacaoPorTenant(unittest.TestCase):

    def setUp(self):
        self._original = dict(rm._ULTIMO_RAG_DEBUG_POR_TENANT)
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.clear()

    def tearDown(self):
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.clear()
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.update(self._original)

    def test_tenant_recebe_so_o_proprio_debug(self):
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"] = {"question": "pergunta sensivel de A"}
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_b"] = {"question": "pergunta de B"}

        self.assertEqual(rm.obter_ultimo_rag_debug("tenant_a")["question"], "pergunta sensivel de A")
        self.assertEqual(rm.obter_ultimo_rag_debug("tenant_b")["question"], "pergunta de B")

    def test_busca_mais_recente_de_outro_tenant_nao_vaza(self):
        # A busca de A aconteceu primeiro; B buscou por último. Pedir o debug de A não pode
        # devolver o de B só porque foi o mais recente do processo.
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"] = {"question": "pergunta de A"}
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_b"] = {"question": "pergunta de B, mais recente"}

        self.assertEqual(rm.obter_ultimo_rag_debug("tenant_a")["question"], "pergunta de A")

    def test_tenant_sem_busca_ainda_recebe_vazio(self):
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"] = {"question": "pergunta de A"}
        self.assertEqual(rm.obter_ultimo_rag_debug("tenant_nunca_buscou"), {})

    def test_sem_tenant_id_devolve_o_mais_recente_de_qualquer_um(self):
        # Compatibilidade com os usos internos (testes de baixo nível, log verboso) que chamam
        # sem argumento sabendo que só um tenant rodou busca neste processo até agora.
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"] = {"question": "primeira"}
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_b"] = {"question": "mais recente"}
        self.assertEqual(rm.obter_ultimo_rag_debug()["question"], "mais recente")

    def test_sem_nenhuma_busca_ainda_devolve_vazio(self):
        self.assertEqual(rm.obter_ultimo_rag_debug(), {})

    def test_devolve_copia_nao_a_referencia_interna(self):
        rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"] = {"question": "original"}
        copia = rm.obter_ultimo_rag_debug("tenant_a")
        copia["question"] = "adulterado"
        self.assertEqual(rm._ULTIMO_RAG_DEBUG_POR_TENANT["tenant_a"]["question"], "original")


if __name__ == "__main__":
    unittest.main()
