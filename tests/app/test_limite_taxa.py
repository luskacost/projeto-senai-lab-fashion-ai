# -*- coding: utf-8 -*-
"""Limite de taxa por IP nas rotas caras (Fase 16, Bloco D, D1).

Antes desta task, só o login (`_ACCESS_LOGIN_TENTATIVAS`/`_ADMIN_LOGIN_TENTATIVAS`) tinha algum
teto de tentativas -- `/chat`, `/documentos/upload` e `/planilha/upload` (cada uma disparando uma
chamada real à API da OpenAI ou parsing pesado) podiam ser chamadas sem limite nenhum. Testado
diretamente sobre a dependência `_limitar_taxa` (não via TestClient/rota real), porque simular uma
sessão de chat de verdade exigiria mockar o pipeline inteiro do agente -- o que importa aqui é só a
contagem por IP/janela, isolada do resto.
"""

import time
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from api.main import _LIMITE_TAXA_CONTADORES, _limitar_taxa


def _request_falso(ip: str) -> MagicMock:
    req = MagicMock()
    req.client.host = ip
    return req


class TestLimitarTaxa(unittest.TestCase):

    def setUp(self):
        self._contadores_originais = dict(_LIMITE_TAXA_CONTADORES)
        _LIMITE_TAXA_CONTADORES.clear()

    def tearDown(self):
        _LIMITE_TAXA_CONTADORES.clear()
        _LIMITE_TAXA_CONTADORES.update(self._contadores_originais)

    def test_permite_ate_o_limite(self):
        dependencia = _limitar_taxa("teste_rotulo_a", max_chamadas=3, janela_segundos=60)
        req = _request_falso("1.2.3.4")
        for _ in range(3):
            dependencia(req)  # não deve levantar

    def test_bloqueia_apos_exceder_o_limite(self):
        dependencia = _limitar_taxa("teste_rotulo_b", max_chamadas=3, janela_segundos=60)
        req = _request_falso("1.2.3.4")
        for _ in range(3):
            dependencia(req)
        with self.assertRaises(HTTPException) as ctx:
            dependencia(req)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_ips_diferentes_tem_contadores_independentes(self):
        dependencia = _limitar_taxa("teste_rotulo_c", max_chamadas=1, janela_segundos=60)
        dependencia(_request_falso("1.1.1.1"))  # consome o limite deste IP

        # Um IP diferente não é afetado pelo consumo do primeiro.
        dependencia(_request_falso("2.2.2.2"))  # não deve levantar

    def test_rotulos_diferentes_tem_contadores_independentes(self):
        # Duas rotas com limites próprios não compartilham o mesmo contador de IP.
        dep_chat = _limitar_taxa("teste_rotulo_d_chat", max_chamadas=1, janela_segundos=60)
        dep_upload = _limitar_taxa("teste_rotulo_d_upload", max_chamadas=1, janela_segundos=60)
        req = _request_falso("3.3.3.3")

        dep_chat(req)  # consome o limite de "chat" para este IP
        dep_upload(req)  # "upload" tem seu próprio contador -- não deve levantar

    def test_janela_expira_e_libera_novas_chamadas(self):
        dependencia = _limitar_taxa("teste_rotulo_e", max_chamadas=1, janela_segundos=60)
        req = _request_falso("4.4.4.4")
        dependencia(req)

        chave = ("teste_rotulo_e", "4.4.4.4")
        # Força a janela a já ter "passado" sem precisar de time.sleep de verdade no teste.
        _LIMITE_TAXA_CONTADORES[chave]["inicio_janela"] = time.time() - 61

        dependencia(req)  # nova janela -- não deve levantar


if __name__ == "__main__":
    unittest.main()
