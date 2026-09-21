# -*- coding: utf-8 -*-
"""POST /admin/login bloqueia por IP, não por tenant (Fase 14, Bloco S, Task 2).

Antes, o bloqueio de 15min após 5 tentativas incorretas era chaveado por `tenant_id` -- uma
string pública, não um segredo. Como este projeto é single-tenant, qualquer um que soubesse o
`tenant_id` conseguia negar o acesso do administrador legítimo por 15 minutos só errando a senha
5 vezes de propósito (DoS trivial). O `TestClient` do FastAPI usa sempre o mesmo IP de origem
("testclient"), então os testes de bloqueio aqui verificam a CHAVE usada internamente
(`_ADMIN_LOGIN_TENTATIVAS`), não dois IPs de fato diferentes.
"""

import os
import unittest

from fastapi.testclient import TestClient

import tenant_config
from api.main import _ADMIN_LOGIN_TENTATIVAS, app

TENANT_TESTE = "teste_fase14_admin_login"
ENV_SENHA = f"{TENANT_TESTE}_ADMIN_PASSWORD".upper()


class TestAdminLoginBloqueioPorIp(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Fase 14)"}
        os.environ[ENV_SENHA] = "senha-correta"
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)
        os.environ.pop(ENV_SENHA, None)

    def setUp(self):
        self._tentativas_originais = dict(_ADMIN_LOGIN_TENTATIVAS)
        _ADMIN_LOGIN_TENTATIVAS.clear()

    def tearDown(self):
        _ADMIN_LOGIN_TENTATIVAS.clear()
        _ADMIN_LOGIN_TENTATIVAS.update(self._tentativas_originais)

    def test_login_correto_funciona(self):
        r = self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-correta"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["autorizado"])
        self.assertIsNotNone(r.json()["token"])

    def test_bloqueio_e_registrado_por_ip_nao_por_tenant(self):
        for _ in range(5):
            self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "errada"})
        # A chave de bloqueio não pode ser o tenant_id -- é o IP do cliente.
        self.assertNotIn(TENANT_TESTE, _ADMIN_LOGIN_TENTATIVAS)
        self.assertTrue(any(dados["falhas"] == 0 and dados["bloqueado_ate"] > 0 for dados in _ADMIN_LOGIN_TENTATIVAS.values()))

    def test_bloqueio_apos_tentativas_demais(self):
        for _ in range(5):
            self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "errada"})
        r = self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-correta"})
        self.assertEqual(r.status_code, 429)

    def test_login_correto_reseta_as_tentativas(self):
        for _ in range(4):
            self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "errada"})
        r_ok = self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-correta"})
        self.assertEqual(r_ok.status_code, 200)

        # Depois de um login certo, as 4 falhas anteriores não contam mais para o bloqueio.
        for _ in range(4):
            self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "errada"})
        r = self.client.post("/admin/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-correta"})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
