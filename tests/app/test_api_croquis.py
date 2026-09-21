# -*- coding: utf-8 -*-
"""Testes das rotas HTTP /croquis (Fase 14, Bloco G, Task 13).

Espelha test_api_fichas.py: tenant fictício injetado em tenant_config.TENANT_CONFIG, limpeza de
tenant_data/croquis/{tenant}_* no tearDown. DELETE exige X-Admin-Token desde já (mesma decisão da
Fase 14, Bloco S, Task 2 para DELETE /fichas -- aplicada aqui desde a primeira versão da rota, não
como correção posterior).
"""

import glob
import os
import time
import unittest

from fastapi.testclient import TestClient

import croquis_repo as cr
import tenant_config
from api.main import _ADMIN_TOKENS, app

TENANT_TESTE = "teste_task13_api_croquis"
UUID_INEXISTENTE = "11111111-1111-1111-1111-111111111111"
PNG_FAKE = b"conteudo-png-fake-para-teste"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(cr.DIRETORIO_CROQUIS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestApiCroquisBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Task 13)"}
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()


class TestListarCroquisEndpoint(TestApiCroquisBase):

    def test_tenant_inexistente_404(self):
        r = self.client.get("/croquis", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_lista_vazia_para_tenant_sem_croquis(self):
        r = self.client.get("/croquis", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_lista_croqui_salvo(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE, resumo="Um vestido midi floral")
        r = self.client.get("/croquis", params={"tenant_id": TENANT_TESTE})
        self.assertEqual([e["id"] for e in r.json()], [entrada["id"]])


class TestObterImagemCroquiEndpoint(TestApiCroquisBase):

    def test_tenant_inexistente_404(self):
        r = self.client.get(f"/croquis/{UUID_INEXISTENTE}/imagem", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_croqui_inexistente_404(self):
        r = self.client.get(f"/croquis/{UUID_INEXISTENTE}/imagem", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.get("/croquis/nao-e-um-uuid/imagem", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_devolve_o_png(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        r = self.client.get(f"/croquis/{entrada['id']}/imagem", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, PNG_FAKE)
        self.assertEqual(r.headers["content-type"], "image/png")


class TestDeletarCroquiEndpoint(TestApiCroquisBase):

    def setUp(self):
        super().setUp()
        self.token_admin = "token-teste-deletar-croqui"
        _ADMIN_TOKENS[self.token_admin] = {"tenant_id": TENANT_TESTE, "expira_em": time.time() + 3600}

    def tearDown(self):
        super().tearDown()
        _ADMIN_TOKENS.pop(self.token_admin, None)

    def _headers(self):
        return {"X-Admin-Token": self.token_admin}

    def test_tenant_inexistente_404(self):
        r = self.client.delete(
            f"/croquis/{UUID_INEXISTENTE}", params={"tenant_id": "tenant_que_nao_existe"}, headers=self._headers()
        )
        self.assertEqual(r.status_code, 404)

    def test_croqui_inexistente_404(self):
        r = self.client.delete(f"/croquis/{UUID_INEXISTENTE}", params={"tenant_id": TENANT_TESTE}, headers=self._headers())
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.delete("/croquis/nao-e-um-uuid", params={"tenant_id": TENANT_TESTE}, headers=self._headers())
        self.assertEqual(r.status_code, 400)

    def test_deleta_e_depois_404(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        r = self.client.delete(f"/croquis/{entrada['id']}", params={"tenant_id": TENANT_TESTE}, headers=self._headers())
        self.assertEqual(r.status_code, 200)

        r2 = self.client.get(f"/croquis/{entrada['id']}/imagem", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r2.status_code, 404)

    def test_removido_da_listagem(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self.client.delete(f"/croquis/{entrada['id']}", params={"tenant_id": TENANT_TESTE}, headers=self._headers())
        r = self.client.get("/croquis", params={"tenant_id": TENANT_TESTE})
        self.assertNotIn(entrada["id"], [e["id"] for e in r.json()])

    def test_sem_token_e_recusado(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        r = self.client.delete(f"/croquis/{entrada['id']}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 422)  # header obrigatório ausente

    def test_token_de_outro_tenant_e_recusado(self):
        outro_token = "token-de-outro-tenant"
        _ADMIN_TOKENS[outro_token] = {"tenant_id": "outro_tenant_qualquer", "expira_em": time.time() + 3600}
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        try:
            r = self.client.delete(
                f"/croquis/{entrada['id']}", params={"tenant_id": TENANT_TESTE}, headers={"X-Admin-Token": outro_token}
            )
            self.assertEqual(r.status_code, 401)
        finally:
            _ADMIN_TOKENS.pop(outro_token, None)


if __name__ == "__main__":
    unittest.main()
