# -*- coding: utf-8 -*-
"""Higiene de sessão (Fase 15, V6).

Antes: `_ACCESS_TOKENS`/`_ADMIN_TOKENS` nunca eram purgados -- um token expirado ficava para
sempre no dicionário em memória, só deixando de validar (o dicionário só cresce, nunca encolhe,
em qualquer servidor de longa duração). E não havia como um usuário encerrar a própria sessão de
propósito: a única saída era esperar o token expirar (30 dias de acesso, 4 horas de admin) ou
reiniciar o processo Uvicorn inteiro."""

import os
import time
import unittest

from fastapi.testclient import TestClient

from api.main import (
    _ACCESS_LOGIN_TENTATIVAS,
    _ACCESS_TOKENS,
    _ADMIN_LOGIN_TENTATIVAS,
    _ADMIN_TOKENS,
    _purgar_tokens_expirados,
    app,
)

VAR_SENHA = "SENAI_LABFASHION_ACCESS_PASSWORD"


class TestPurgaDeTokensExpirados(unittest.TestCase):
    """Testa `_purgar_tokens_expirados` isoladamente -- não depende do gate estar ligado."""

    def test_remove_so_os_expirados(self):
        agora = time.time()
        tokens = {
            "expirado-1": {"expira_em": agora - 10},
            "expirado-2": {"expira_em": agora - 1},
            "valido": {"expira_em": agora + 1000},
        }
        _purgar_tokens_expirados(tokens)
        self.assertEqual(set(tokens.keys()), {"valido"})

    def test_dicionario_vazio_nao_quebra(self):
        tokens = {}
        _purgar_tokens_expirados(tokens)
        self.assertEqual(tokens, {})

    def test_nenhum_expirado_nao_remove_nada(self):
        agora = time.time()
        tokens = {"a": {"expira_em": agora + 100}, "b": {"expira_em": agora + 200}}
        _purgar_tokens_expirados(tokens)
        self.assertEqual(len(tokens), 2)


class TestPurgaAcontecePorEmissaoDeToken(unittest.TestCase):
    """Um login novo purga os tokens de acesso expirados que sobraram no dicionário --
    é o único ponto de escrita de `_ACCESS_TOKENS`, então basta ele."""

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

    def test_login_novo_purga_token_de_acesso_expirado_que_sobrou(self):
        _ACCESS_TOKENS["token-velho-esquecido"] = {"expira_em": time.time() - 100}

        resposta = self.client.post("/acesso/login", json={"senha": "senha-correta-123"})
        self.assertTrue(resposta.json()["autorizado"])

        self.assertNotIn("token-velho-esquecido", _ACCESS_TOKENS)


class TestLogoutDeAcesso(unittest.TestCase):

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

    def test_logout_invalida_o_token_imediatamente(self):
        login = self.client.post("/acesso/login", json={"senha": "senha-correta-123"})
        token = login.json()["token"]

        resposta = self.client.post("/acesso/logout", headers={"X-Access-Token": token})
        self.assertEqual(resposta.status_code, 200)

        # O mesmo token não abre mais rota nenhuma protegida.
        seguinte = self.client.get(
            "/config/tenant", params={"tenant_id": "senai_labfashion"},
            headers={"X-Access-Token": token},
        )
        self.assertEqual(seguinte.status_code, 401)

    def test_logout_de_token_inexistente_nao_quebra(self):
        resposta = self.client.post("/acesso/logout", headers={"X-Access-Token": "nunca-existiu"})
        self.assertEqual(resposta.status_code, 200)


class TestLogoutDeAdmin(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self._admin_tokens_originais = dict(_ADMIN_TOKENS)
        self._admin_tentativas_originais = dict(_ADMIN_LOGIN_TENTATIVAS)
        _ADMIN_TOKENS.clear()
        _ADMIN_LOGIN_TENTATIVAS.clear()

    def tearDown(self):
        _ADMIN_TOKENS.clear()
        _ADMIN_TOKENS.update(self._admin_tokens_originais)
        _ADMIN_LOGIN_TENTATIVAS.clear()
        _ADMIN_LOGIN_TENTATIVAS.update(self._admin_tentativas_originais)

    def test_logout_invalida_o_token_de_admin_imediatamente(self):
        token = "token-admin-de-teste"
        _ADMIN_TOKENS[token] = {"tenant_id": "senai_labfashion", "expira_em": time.time() + 1000}

        resposta = self.client.post("/admin/logout", headers={"X-Admin-Token": token})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(token, _ADMIN_TOKENS)

    def test_logout_de_token_admin_inexistente_nao_quebra(self):
        resposta = self.client.post("/admin/logout", headers={"X-Admin-Token": "nunca-existiu"})
        self.assertEqual(resposta.status_code, 200)


if __name__ == "__main__":
    unittest.main()
