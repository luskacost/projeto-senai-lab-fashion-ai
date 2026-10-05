# -*- coding: utf-8 -*-
"""Modo produção (`AMBIENTE=producao`) -- travas que só fazem sentido com o app na internet.

Testa as duas funções isoladamente (sem recarregar `api.main` com outra variável de ambiente):
`_kwargs_documentacao` decide se `/docs`/`/openapi.json` existem, e
`_verificar_configuracao_de_producao` faz o backend se recusar a subir sem autenticação.
"""

import os
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import _kwargs_documentacao, _verificar_configuracao_de_producao

VAR_SENHA_DONO = "SENAI_LABFASHION_LOGIN_SENHA"


class TestDocumentacaoDesligadaEmProducao(unittest.TestCase):

    def test_em_producao_docs_e_openapi_nao_existem(self):
        cliente = TestClient(FastAPI(**_kwargs_documentacao(True)))
        self.assertEqual(cliente.get("/docs").status_code, 404)
        self.assertEqual(cliente.get("/redoc").status_code, 404)
        self.assertEqual(cliente.get("/openapi.json").status_code, 404)

    def test_fora_de_producao_docs_continuam_disponiveis(self):
        cliente = TestClient(FastAPI(**_kwargs_documentacao(False)))
        self.assertEqual(cliente.get("/openapi.json").status_code, 200)


class TestFalhaFechadoEmProducao(unittest.TestCase):

    def setUp(self):
        self._senha_original = os.environ.pop(VAR_SENHA_DONO, None)

    def tearDown(self):
        os.environ.pop(VAR_SENHA_DONO, None)
        if self._senha_original is not None:
            os.environ[VAR_SENHA_DONO] = self._senha_original

    def test_producao_sem_nenhum_login_configurado_recusa_subir(self):
        # `tests/app/__init__.py` já varre todo `*_LOGIN_SENHA` do ambiente -- este é o cenário
        # "esqueci de configurar as senhas no painel do Coolify".
        with self.assertRaises(RuntimeError):
            _verificar_configuracao_de_producao(True)

    def test_producao_com_login_de_tenant_configurado_sobe_normalmente(self):
        os.environ[VAR_SENHA_DONO] = "senha-forte-de-producao"
        _verificar_configuracao_de_producao(True)  # não deve levantar

    def test_fora_de_producao_sem_nada_configurado_continua_subindo(self):
        # Desenvolvimento local continua com o padrão aberto de sempre.
        _verificar_configuracao_de_producao(False)  # não deve levantar

    def test_senha_unica_legada_nao_basta_em_producao(self):
        # A senha única desliga o isolamento entre tenants (token sem tenant) -- em produção, só
        # login por tenant conta como autenticação configurada.
        anterior = os.environ.get("SENAI_LABFASHION_ACCESS_PASSWORD")
        os.environ["SENAI_LABFASHION_ACCESS_PASSWORD"] = "senha-unica-qualquer"
        try:
            with self.assertRaises(RuntimeError):
                _verificar_configuracao_de_producao(True)
        finally:
            if anterior is None:
                os.environ.pop("SENAI_LABFASHION_ACCESS_PASSWORD", None)
            else:
                os.environ["SENAI_LABFASHION_ACCESS_PASSWORD"] = anterior


if __name__ == "__main__":
    unittest.main()
