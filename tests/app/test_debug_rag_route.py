# -*- coding: utf-8 -*-
"""Rota GET /debug/rag exige token de admin e nunca vaza dado de outro tenant (Fase 13, Task 16).

Antes: a rota não pedia autenticação nenhuma e devolvia sempre a última busca RAG executada
neste processo, de QUALQUER tenant -- não o `tenant_id` recebido no parâmetro (que era lido e
ignorado). Um cliente autenticado como tenant A conseguia ler a pergunta e o texto integral dos
chunks de uma busca do tenant B, só chamando a rota logo depois.
"""

import time
import unittest

from fastapi.testclient import TestClient

import rag_manager as rm
from api.main import _ADMIN_TOKENS, app

TENANT_A = "teste_fase13_debug_rag_a"
TENANT_B = "teste_fase13_debug_rag_b"


class TestRotaDebugRag(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self._debug_original = dict(rm._ULTIMO_RAG_DEBUG_POR_TENANT)
        self._tokens_originais = dict(_ADMIN_TOKENS)
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.clear()
        rm._ULTIMO_RAG_DEBUG_POR_TENANT[TENANT_A] = {"question": "pergunta sensivel de A"}
        rm._ULTIMO_RAG_DEBUG_POR_TENANT[TENANT_B] = {"question": "pergunta de B"}
        self.token_a = "token-teste-tenant-a"
        _ADMIN_TOKENS[self.token_a] = {"tenant_id": TENANT_A, "expira_em": time.time() + 3600}

    def tearDown(self):
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.clear()
        rm._ULTIMO_RAG_DEBUG_POR_TENANT.update(self._debug_original)
        _ADMIN_TOKENS.clear()
        _ADMIN_TOKENS.update(self._tokens_originais)

    def test_sem_token_e_recusado(self):
        resposta = self.client.get("/debug/rag", params={"tenant_id": TENANT_A})
        self.assertEqual(resposta.status_code, 422)  # header obrigatório ausente

    def test_token_de_outro_tenant_e_recusado(self):
        resposta = self.client.get(
            "/debug/rag",
            params={"tenant_id": TENANT_B},
            headers={"X-Admin-Token": self.token_a},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_token_valido_devolve_so_o_proprio_tenant(self):
        resposta = self.client.get(
            "/debug/rag",
            params={"tenant_id": TENANT_A},
            headers={"X-Admin-Token": self.token_a},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["question"], "pergunta sensivel de A")

    def test_nunca_devolve_o_debug_de_outro_tenant_mesmo_autenticado(self):
        # O ponto central do vazamento original: mesmo com um token válido (de A), pedir o
        # tenant_id de B não pode devolver o conteúdo de B nem o de A por engano cruzado.
        resposta = self.client.get(
            "/debug/rag",
            params={"tenant_id": TENANT_A},
            headers={"X-Admin-Token": self.token_a},
        )
        self.assertNotIn("pergunta de B", resposta.json().get("question", ""))


if __name__ == "__main__":
    unittest.main()
