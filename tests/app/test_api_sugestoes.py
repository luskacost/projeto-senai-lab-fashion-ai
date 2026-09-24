# -*- coding: utf-8 -*-
"""Testes das rotas HTTP POST/GET /sugestoes (Fase 16, Bloco S, S2)."""

import glob
import os
import unittest

from fastapi.testclient import TestClient

from api.main import app
from sugestoes_repo import DIRETORIO_SUGESTOES
from tenant_config import TENANT_CONFIG

TENANT_TESTE = "senai_labfashion"  # tenant real já existente em TENANT_CONFIG


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(DIRETORIO_SUGESTOES, f"{TENANT_TESTE}*")):
        os.remove(caminho)


class TestCriarSugestao(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def test_cria_sugestao_com_sucesso(self):
        resposta = self.client.post(
            "/sugestoes",
            json={"tenant_id": TENANT_TESTE, "tipo": "sugestao", "texto": "Adicionar modo escuro."},
        )
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["tipo"], "sugestao")
        self.assertEqual(corpo["texto"], "Adicionar modo escuro.")
        self.assertIn("id", corpo)

    def test_tenant_inexistente_devolve_404(self):
        resposta = self.client.post(
            "/sugestoes",
            json={"tenant_id": "tenant_que_nao_existe_xyz", "tipo": "bug", "texto": "Algo quebrou."},
        )
        self.assertEqual(resposta.status_code, 404)

    def test_tipo_invalido_devolve_400(self):
        resposta = self.client.post(
            "/sugestoes",
            json={"tenant_id": TENANT_TESTE, "tipo": "elogio", "texto": "Texto qualquer."},
        )
        self.assertEqual(resposta.status_code, 400)

    def test_texto_vazio_devolve_400(self):
        resposta = self.client.post(
            "/sugestoes",
            json={"tenant_id": TENANT_TESTE, "tipo": "bug", "texto": "   "},
        )
        self.assertEqual(resposta.status_code, 400)


class TestListarSugestoes(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        _limpar_tenant_teste()
        self.senha_admin_original = os.environ.get(f"{TENANT_TESTE.upper()}_ADMIN_PASSWORD")

    def tearDown(self):
        _limpar_tenant_teste()

    def test_listar_sem_token_admin_correto_e_recusado(self):
        resposta = self.client.get(
            "/sugestoes", params={"tenant_id": TENANT_TESTE},
            headers={"X-Admin-Token": "token-invalido-qualquer"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_listar_com_token_admin_valido_devolve_as_sugestoes_criadas(self):
        os.environ[f"{TENANT_TESTE.upper()}_ADMIN_PASSWORD"] = "senha-admin-teste-fase16"
        try:
            login = self.client.post(
                "/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-admin-teste-fase16"}
            )
            token_admin = login.json()["token"]
            self.assertIsNotNone(token_admin)

            self.client.post(
                "/sugestoes",
                json={"tenant_id": TENANT_TESTE, "tipo": "bug", "texto": "Reporte de teste."},
            )

            resposta = self.client.get(
                "/sugestoes", params={"tenant_id": TENANT_TESTE},
                headers={"X-Admin-Token": token_admin},
            )
            self.assertEqual(resposta.status_code, 200)
            lista = resposta.json()
            self.assertTrue(any(s["texto"] == "Reporte de teste." for s in lista))
        finally:
            if self.senha_admin_original is None:
                os.environ.pop(f"{TENANT_TESTE.upper()}_ADMIN_PASSWORD", None)
            else:
                os.environ[f"{TENANT_TESTE.upper()}_ADMIN_PASSWORD"] = self.senha_admin_original


if __name__ == "__main__":
    unittest.main()
