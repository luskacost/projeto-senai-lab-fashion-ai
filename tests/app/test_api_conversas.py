# -*- coding: utf-8 -*-
"""Testes das rotas HTTP /conversas (Fase 15, Bloco V, V2).

Antes desta correção, só GET .../export validava `tenant_id`, e `usuario_id` (que vem do
`localStorage` do navegador -- controle total do cliente) nunca era validado em rota nenhuma,
indo cru para `conversas_manager` e virando parte de um nome de arquivo. Ver
tests/app/test_conversas_manager.py para a prova em disco do path traversal.

Usa um tenant fictício, injetado em tenant_config.TENANT_CONFIG só durante esta suíte. Limpa
tenant_data/conversas/{tenant}_* no tearDown.
"""

import glob
import os
import unittest
import uuid

from fastapi.testclient import TestClient

import conversas_manager as cm
import tenant_config
from api.main import app

TENANT_TESTE = "teste_fase15_api_conversas"
USUARIO_VALIDO = str(uuid.uuid4())


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(cm.DIRETORIO_CONVERSAS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestApiConversasBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Fase 15)"}
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()


class TestTenantEUsuarioInvalidos(TestApiConversasBase):
    """Cobre as 5 rotas -- todas precisam recusar tenant inexistente e usuario_id malformado
    antes de tocar em disco, não só a de export (a única que já validava)."""

    def test_get_tenant_inexistente_404(self):
        r = self.client.get("/conversas", params={"tenant_id": "nao_existe", "usuario_id": USUARIO_VALIDO})
        self.assertEqual(r.status_code, 404)

    def test_get_usuario_id_malformado_400(self):
        r = self.client.get("/conversas", params={"tenant_id": TENANT_TESTE, "usuario_id": "../../etc/passwd"})
        self.assertEqual(r.status_code, 400)

    def test_post_tenant_inexistente_404(self):
        r = self.client.post("/conversas", json={"tenant_id": "nao_existe", "usuario_id": USUARIO_VALIDO})
        self.assertEqual(r.status_code, 404)

    def test_post_usuario_id_malformado_400(self):
        r = self.client.post("/conversas", json={"tenant_id": TENANT_TESTE, "usuario_id": "../../etc/passwd"})
        self.assertEqual(r.status_code, 400)

    def test_patch_usuario_id_malformado_400(self):
        r = self.client.patch(
            "/conversas/qualquer-id",
            json={"tenant_id": TENANT_TESTE, "usuario_id": "../x", "novo_titulo": "Y"},
        )
        self.assertEqual(r.status_code, 400)

    def test_delete_usuario_id_malformado_400(self):
        r = self.client.delete(
            "/conversas/qualquer-id",
            params={"tenant_id": TENANT_TESTE, "usuario_id": "../x"},
        )
        self.assertEqual(r.status_code, 400)

    def test_export_usuario_id_malformado_400(self):
        r = self.client.get(
            "/conversas/qualquer-id/export",
            params={"tenant_id": TENANT_TESTE, "usuario_id": "../x"},
        )
        self.assertEqual(r.status_code, 400)

    def test_usuario_id_malformado_nao_cria_arquivo_nenhum(self):
        self.client.post("/conversas", json={"tenant_id": TENANT_TESTE, "usuario_id": "../../fora"})
        # Nada deveria ter sido escrito em tenant_data/conversas/ nem fora dela.
        self.assertEqual(glob.glob(os.path.join(cm.DIRETORIO_CONVERSAS, "*fora*")), [])
        self.assertFalse(os.path.exists(os.path.join("tenant_data", "fora.json")))


class TestFluxoNormalContinuaFuncionando(TestApiConversasBase):
    """A correção não pode ter quebrado o caminho feliz."""

    def test_criar_listar_atualizar_e_deletar(self):
        criada = self.client.post(
            "/conversas", json={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO}
        ).json()
        self.assertTrue(criada["id"])

        listagem = self.client.get(
            "/conversas", params={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO}
        ).json()
        self.assertEqual([c["id"] for c in listagem], [criada["id"]])

        atualizada = self.client.patch(
            f"/conversas/{criada['id']}",
            json={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO, "novo_titulo": "Renomeada"},
        ).json()
        self.assertEqual(atualizada["titulo"], "Renomeada")

        r = self.client.delete(
            f"/conversas/{criada['id']}",
            params={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO},
        )
        self.assertEqual(r.status_code, 200)

    def test_export_continua_funcionando(self):
        criada = self.client.post(
            "/conversas", json={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO}
        ).json()
        r = self.client.get(
            f"/conversas/{criada['id']}/export",
            params={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO, "formato": "txt"},
        )
        self.assertEqual(r.status_code, 200)

    def test_dois_usuarios_do_mesmo_tenant_nao_veem_a_conversa_um_do_outro(self):
        outro_usuario = str(uuid.uuid4())
        self.client.post("/conversas", json={"tenant_id": TENANT_TESTE, "usuario_id": USUARIO_VALIDO})

        listagem_outro = self.client.get(
            "/conversas", params={"tenant_id": TENANT_TESTE, "usuario_id": outro_usuario}
        ).json()
        self.assertEqual(listagem_outro, [])


if __name__ == "__main__":
    unittest.main()
