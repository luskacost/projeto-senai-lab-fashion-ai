# -*- coding: utf-8 -*-
"""Testes das rotas HTTP POST/GET /sugestoes (Fase 16, Bloco S, S2) e do resumo agregado
(GET /sugestoes/resumo-geral, adicionado depois a pedido do usuário -- ele precisava ficar
sabendo de sugestões/reportes de qualquer consultor sem logar em cada tenant separado)."""

import glob
import os
import unittest

from fastapi.testclient import TestClient

from api.main import TENANT_DONO, app
from sugestoes_repo import DIRETORIO_SUGESTOES
from tenant_config import TENANT_CONFIG

TENANT_TESTE = "senai_labfashion"  # tenant real já existente em TENANT_CONFIG


def _limpar_tenant_teste(tenant_id=TENANT_TESTE):
    for caminho in glob.glob(os.path.join(DIRETORIO_SUGESTOES, f"{tenant_id}*")):
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


OUTRO_TENANT_TESTE = "consultoria_teste_fase16_resumo"
VAR_SENHA_OUTRO_TENANT = "CONSULTORIA_TESTE_FASE16_RESUMO_LOGIN_SENHA"
VAR_SENHA_TENANT_DONO = "SENAI_LABFASHION_LOGIN_SENHA"


class TestResumoGeralSugestoesComLoginPorTenant(unittest.TestCase):
    """Com login por tenant ativo (pelo menos um tenant com LOGIN_SENHA): só um token do
    próprio `TENANT_DONO` vê o resumo agregado."""

    def setUp(self):
        self.client = TestClient(app)
        _limpar_tenant_teste(TENANT_TESTE)
        _limpar_tenant_teste(OUTRO_TENANT_TESTE)
        TENANT_CONFIG[OUTRO_TENANT_TESTE] = {"nome": "Consultoria Teste Resumo"}
        self._senha_dono_original = os.environ.get(VAR_SENHA_TENANT_DONO)
        os.environ[VAR_SENHA_OUTRO_TENANT] = "senha-outro-tenant-123"
        os.environ[VAR_SENHA_TENANT_DONO] = "senha-dono-teste-123"

    def tearDown(self):
        _limpar_tenant_teste(TENANT_TESTE)
        _limpar_tenant_teste(OUTRO_TENANT_TESTE)
        TENANT_CONFIG.pop(OUTRO_TENANT_TESTE, None)
        os.environ.pop(VAR_SENHA_OUTRO_TENANT, None)
        if self._senha_dono_original is None:
            os.environ.pop(VAR_SENHA_TENANT_DONO, None)
        else:
            os.environ[VAR_SENHA_TENANT_DONO] = self._senha_dono_original

    def _token(self, tenant_id: str, senha: str) -> str:
        login = self.client.post("/acesso/login", json={"tenant_id": tenant_id, "senha": senha})
        return login.json()["token"]

    def test_token_de_outro_tenant_nao_ve_o_resumo_geral(self):
        token = self._token(OUTRO_TENANT_TESTE, "senha-outro-tenant-123")
        resposta = self.client.get("/sugestoes/resumo-geral", headers={"X-Access-Token": token})
        self.assertEqual(resposta.status_code, 403)

    def test_token_do_tenant_dono_ve_o_resumo_agregado_de_todos(self):
        token_dono = self._token(TENANT_TESTE, "senha-dono-teste-123")
        token_outro = self._token(OUTRO_TENANT_TESTE, "senha-outro-tenant-123")

        self.client.post(
            "/sugestoes", json={"tenant_id": TENANT_TESTE, "tipo": "sugestao", "texto": "Do dono."},
            headers={"X-Access-Token": token_dono},
        )
        self.client.post(
            "/sugestoes", json={"tenant_id": OUTRO_TENANT_TESTE, "tipo": "bug", "texto": "De outro tenant, 1."},
            headers={"X-Access-Token": token_outro},
        )
        self.client.post(
            "/sugestoes", json={"tenant_id": OUTRO_TENANT_TESTE, "tipo": "bug", "texto": "De outro tenant, 2."},
            headers={"X-Access-Token": token_outro},
        )

        resposta = self.client.get("/sugestoes/resumo-geral", headers={"X-Access-Token": token_dono})
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["por_tenant"].get(OUTRO_TENANT_TESTE), 2)
        self.assertEqual(corpo["por_tenant"].get(TENANT_TESTE), 1)
        self.assertGreaterEqual(corpo["total"], 3)


class TestResumoGeralSugestoesModoLegado(unittest.TestCase):
    """Sem NENHUM tenant com LOGIN_SENHA, o app inteiro está no modo legado -- inclusive esta
    rota, que trata "token sem tenant" como o dono único do app (comportamento pré-Fase 16)."""

    def setUp(self):
        self.client = TestClient(app)

    def test_token_legado_sem_tenant_ve_o_resumo(self):
        login = self.client.post("/acesso/login", json={"senha": "qualquer"})
        token = login.json()["token"]

        resposta = self.client.get("/sugestoes/resumo-geral", headers={"X-Access-Token": token})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("total", resposta.json())


if __name__ == "__main__":
    unittest.main()
