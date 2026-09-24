# -*- coding: utf-8 -*-
"""Login por pessoa = login por tenant (Fase 16, Bloco L, L1/L2).

Cada colega/consultoria é o seu próprio tenant, então "usuário" no login É o `tenant_id` --
`POST /acesso/login` passa a aceitar `{tenant_id, senha}`, comparando com
`obter_secret_tenant(tenant_id, "LOGIN_SENHA")`. O token emitido passa a carregar o `tenant_id`, e
o gate (`verificar_acesso`) passa a exigir que esse tenant bata com o `tenant_id` que a rota
chamada está pedindo (query param ou corpo JSON) -- um token de uma consultoria não pode ler nem
escrever dado de outra.

Sem NENHUM tenant com `LOGIN_SENHA` configurada, o modo legado de senha única (Fase 14/15,
`SENAI_LABFASHION_ACCESS_PASSWORD`) continua funcionando -- é o que os testes de
`test_gate_de_acesso.py` já cobrem e continuam cobrindo sem alteração nenhuma.
"""

import os
import unittest

from fastapi.testclient import TestClient

from api.main import _ACCESS_LOGIN_TENTATIVAS, _ACCESS_TOKENS, _tenants_com_login_configurado, app
from tenant_config import TENANT_CONFIG

TENANT_TESTE = "consultoria_teste_fase16"
VAR_SENHA_TENANT_TESTE = "CONSULTORIA_TESTE_FASE16_LOGIN_SENHA"
OUTRO_TENANT_TESTE = "consultoria_teste_fase16_outra"
VAR_SENHA_OUTRO_TENANT = "CONSULTORIA_TESTE_FASE16_OUTRA_LOGIN_SENHA"


class TestLoginPorTenant(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        TENANT_CONFIG[TENANT_TESTE] = {"nome": "Consultoria Teste"}
        TENANT_CONFIG[OUTRO_TENANT_TESTE] = {"nome": "Consultoria Teste Outra"}
        os.environ[VAR_SENHA_TENANT_TESTE] = "senha-consultoria-123"
        self._tokens_originais = dict(_ACCESS_TOKENS)
        self._tentativas_originais = dict(_ACCESS_LOGIN_TENTATIVAS)
        _ACCESS_TOKENS.clear()
        _ACCESS_LOGIN_TENTATIVAS.clear()

    def tearDown(self):
        TENANT_CONFIG.pop(TENANT_TESTE, None)
        TENANT_CONFIG.pop(OUTRO_TENANT_TESTE, None)
        os.environ.pop(VAR_SENHA_TENANT_TESTE, None)
        os.environ.pop(VAR_SENHA_OUTRO_TENANT, None)
        _ACCESS_TOKENS.clear()
        _ACCESS_TOKENS.update(self._tokens_originais)
        _ACCESS_LOGIN_TENTATIVAS.clear()
        _ACCESS_LOGIN_TENTATIVAS.update(self._tentativas_originais)

    def test_login_com_tenant_e_senha_corretos_autoriza_e_devolve_tenant_id(self):
        resposta = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertTrue(corpo["autorizado"])
        self.assertIsNotNone(corpo["token"])
        self.assertEqual(corpo["tenant_id"], TENANT_TESTE)

    def test_login_com_senha_errada_nao_autoriza(self):
        resposta = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-errada"}
        )
        corpo = resposta.json()
        self.assertFalse(corpo["autorizado"])
        self.assertIsNone(corpo["token"])

    def test_login_com_tenant_inexistente_nao_autoriza(self):
        resposta = self.client.post(
            "/acesso/login", json={"tenant_id": "tenant_que_nao_existe", "senha": "qualquer"}
        )
        corpo = resposta.json()
        self.assertFalse(corpo["autorizado"])
        self.assertIsNone(corpo["token"])

    def test_login_sem_tenant_id_nao_autoriza_quando_ha_tenant_com_login_configurado(self):
        # Modo legado (só senha) deixa de valer assim que existe pelo menos um tenant com
        # LOGIN_SENHA configurada -- este teste roda com VAR_SENHA_TENANT_TESTE setada no setUp.
        resposta = self.client.post("/acesso/login", json={"senha": "senha-consultoria-123"})
        corpo = resposta.json()
        self.assertFalse(corpo["autorizado"])
        self.assertIsNone(corpo["token"])

    def test_token_de_um_tenant_acessa_rota_do_proprio_tenant(self):
        login = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        token = login.json()["token"]

        resposta = self.client.get(
            "/config/tenant", params={"tenant_id": TENANT_TESTE},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(resposta.status_code, 200)

    def test_token_de_um_tenant_nao_acessa_rota_de_outro_tenant_via_query_param(self):
        login = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        token = login.json()["token"]

        resposta = self.client.get(
            "/config/tenant", params={"tenant_id": OUTRO_TENANT_TESTE},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_token_de_um_tenant_nao_acessa_rota_de_outro_tenant_via_corpo_json(self):
        login = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        token = login.json()["token"]

        resposta = self.client.post(
            "/conversas",
            json={"tenant_id": OUTRO_TENANT_TESTE, "usuario_id": "11111111-1111-1111-1111-111111111111"},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(resposta.status_code, 403)

    def test_token_de_um_tenant_acessa_rota_do_proprio_tenant_via_corpo_json(self):
        # Confirma que ler o corpo JSON dentro da dependência (para comparar tenant_id) não
        # "consome" o corpo -- a rota ainda consegue parsear o mesmo corpo no Pydantic model.
        login = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        token = login.json()["token"]

        resposta = self.client.post(
            "/conversas",
            json={"tenant_id": TENANT_TESTE, "usuario_id": "11111111-1111-1111-1111-111111111111"},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(resposta.status_code, 200)

    def test_bloqueio_apos_tentativas_demais_no_login_por_tenant(self):
        for _ in range(5):
            self.client.post("/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "errada"})
        resposta = self.client.post(
            "/acesso/login", json={"tenant_id": TENANT_TESTE, "senha": "senha-consultoria-123"}
        )
        self.assertEqual(resposta.status_code, 429)


class TestIsolamentoDaSuiteContraLoginSenhaReal(unittest.TestCase):
    """Guarda contra a suíte inteira "vazar" para o modo por tenant/pessoa por causa de um
    `.env` real com `{TENANT}_LOGIN_SENHA` configurada (ex.: consultores de verdade cadastrados
    em produção/na máquina de quem roda os testes) -- sem isolamento, TODO teste que espera o
    modo legado (gate desligado ou senha única) quebra, porque `_tenants_com_login_configurado()`
    deixaria de devolver lista vazia. `tests/app/__init__.py` varre e remove essas variáveis do
    ambiente uma vez, antes de qualquer teste rodar -- este teste confirma que a varredura
    funcionou (não que ela existe: se `tests/app/__init__.py` for descuidadamente movido de volta
    para `tests/__init__.py`, por exemplo, ele nunca roda de verdade sob `python -m unittest
    discover -s tests`, e este teste pega isso)."""

    def test_nenhum_tenant_com_login_configurado_por_padrao(self):
        self.assertEqual(_tenants_com_login_configurado(), [])


if __name__ == "__main__":
    unittest.main()
