# -*- coding: utf-8 -*-
"""Senha única de acesso ao app inteiro (Fase 14, Bloco S, Task 1).

Antes: qualquer rota do backend (chat, fichas, upload de planilha, geração de imagem) era
alcançável por qualquer um que soubesse o endereço -- sem cadastro de usuário final por design, a
única barreira real era não saber que o servidor existia. `POST /fichas/{id}/desenho` em
particular gastava dinheiro real (gpt-image-1) sem autenticação nenhuma.
"""

import os
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import _ACCESS_LOGIN_TENTATIVAS, _ACCESS_TOKENS, app

VAR_SENHA = "SENAI_LABFASHION_ACCESS_PASSWORD"


class TestGateDeAcessoDesligado(unittest.TestCase):
    """Sem a variável de ambiente definida, o comportamento é o de sempre -- nenhuma rota exige
    o novo header. Cobre o ambiente de desenvolvimento local, que não define essa variável."""

    def setUp(self):
        self.client = TestClient(app)
        self._valor_original = os.environ.pop(VAR_SENHA, None)

    def tearDown(self):
        if self._valor_original is not None:
            os.environ[VAR_SENHA] = self._valor_original

    def test_rota_qualquer_funciona_sem_nenhum_token(self):
        resposta = self.client.get("/config/tenant", params={"tenant_id": "senai_labfashion"})
        self.assertEqual(resposta.status_code, 200)

    def test_login_devolve_autorizado_mesmo_sem_senha_configurada(self):
        resposta = self.client.post("/acesso/login", json={"senha": "qualquer coisa"})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["autorizado"])


class TestGateDeAcessoLigado(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self._valor_original = os.environ.get(VAR_SENHA)
        os.environ[VAR_SENHA] = "senha-correta-123"
        self._tokens_originais = dict(_ACCESS_TOKENS)
        self._tentativas_originais = dict(_ACCESS_LOGIN_TENTATIVAS)
        _ACCESS_TOKENS.clear()
        _ACCESS_LOGIN_TENTATIVAS.clear()

    def tearDown(self):
        if self._valor_original is None:
            os.environ.pop(VAR_SENHA, None)
        else:
            os.environ[VAR_SENHA] = self._valor_original
        _ACCESS_TOKENS.clear()
        _ACCESS_TOKENS.update(self._tokens_originais)
        _ACCESS_LOGIN_TENTATIVAS.clear()
        _ACCESS_LOGIN_TENTATIVAS.update(self._tentativas_originais)

    def test_rota_protegida_sem_token_e_recusada(self):
        resposta = self.client.get("/config/tenant", params={"tenant_id": "senai_labfashion"})
        self.assertEqual(resposta.status_code, 401)

    def test_health_nunca_exige_token(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_login_com_senha_errada_nao_autoriza_e_nao_gera_token(self):
        resposta = self.client.post("/acesso/login", json={"senha": "errada"})
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertFalse(corpo["autorizado"])
        self.assertIsNone(corpo["token"])

    def test_login_com_senha_certa_autoriza_e_o_token_destranca_rota_protegida(self):
        login = self.client.post("/acesso/login", json={"senha": "senha-correta-123"})
        self.assertTrue(login.json()["autorizado"])
        token = login.json()["token"]

        resposta = self.client.get(
            "/config/tenant", params={"tenant_id": "senai_labfashion"},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(resposta.status_code, 200)

    def test_token_de_outra_sessao_nao_serve(self):
        resposta = self.client.get(
            "/config/tenant", params={"tenant_id": "senai_labfashion"},
            headers={"X-Access-Token": "token-inventado-qualquer"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_token_expirado_e_recusado(self):
        _ACCESS_TOKENS["token-velho"] = {"expira_em": time.time() - 1}
        resposta = self.client.get(
            "/config/tenant", params={"tenant_id": "senai_labfashion"},
            headers={"X-Access-Token": "token-velho"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_bloqueio_apos_tentativas_demais(self):
        for _ in range(5):
            self.client.post("/acesso/login", json={"senha": "errada"})
        resposta = self.client.post("/acesso/login", json={"senha": "errada"})
        self.assertEqual(resposta.status_code, 429)

    def test_bloqueio_e_por_ip_nao_por_tenant(self):
        # O bloqueio de admin (Task 2) é por tenant_id -- um erro que este gate não repete, já
        # que não existe tenant_id nenhum no corpo do login de acesso.
        for _ in range(5):
            self.client.post("/acesso/login", json={"senha": "errada"})
        self.assertIn("testclient", _ACCESS_LOGIN_TENTATIVAS)

    def test_rota_isenta_funciona_sem_token_mesmo_com_gate_ligado(self):
        # Rotas servidas direto por <img>/<a>/<iframe> não podem carregar header customizado --
        # ficam de fora do gate por necessidade técnica. O 400 vem da validação de UUID da rota
        # em si, não do gate (que devolveria 401).
        resposta = self.client.get(
            "/fichas/id-invalido/preview", params={"tenant_id": "senai_labfashion"}
        )
        self.assertNotEqual(resposta.status_code, 401)

    def test_login_isento_nao_exige_token_de_si_mesmo(self):
        resposta = self.client.post("/acesso/login", json={"senha": "senha-correta-123"})
        self.assertEqual(resposta.status_code, 200)


if __name__ == "__main__":
    unittest.main()
