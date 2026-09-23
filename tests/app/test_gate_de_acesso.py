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

    def test_imagem_de_croqui_isenta_do_gate_mesmo_ligado(self):
        # Mesmo motivo da desenho da ficha acima: <img src> não carrega header customizado
        # (Fase 14, Bloco G, Task 13). O 404 vem da validação da rota (croqui inexistente), não
        # do gate (que devolveria 401).
        resposta = self.client.get(
            "/croquis/11111111-1111-1111-1111-111111111111/imagem",
            params={"tenant_id": "senai_labfashion"},
        )
        self.assertNotEqual(resposta.status_code, 401)

    def test_importar_croqui_como_desenho_exige_token_mesmo_no_caminho_de_desenho(self):
        # Fase 15, V1: a isenção `^/fichas/[^/]+/desenho/[^/]+$` (criada para o GET da imagem, Fase
        # 14 Task 9) também casava com POST /fichas/{id}/desenho/importar-croqui (rota que ESCREVE,
        # nascida depois na Fase 14 Task 17) -- o gate testava só o caminho, nunca o método. Sem
        # token, essa rota anexava uma versão de desenho e mudava o status da ficha em silêncio.
        # Prova o fechamento: sem token, cai em 401 antes de a rota rodar (nunca 404 de ficha
        # inexistente, que seria o corpo da rota respondendo).
        resposta = self.client.post(
            "/fichas/11111111-1111-1111-1111-111111111111/desenho/importar-croqui",
            json={
                "tenant_id": "senai_labfashion",
                "croqui_id": "22222222-2222-2222-2222-222222222222",
            },
        )
        self.assertEqual(resposta.status_code, 401)

    def test_get_da_imagem_do_desenho_continua_isento_so_com_numero_de_versao(self):
        # A regex apertou de [^/]+ para \d+ -- confirma que o caso legítimo (GET .../desenho/1)
        # continua isento. O 404 vem da rota (ficha inexistente), não do gate.
        resposta = self.client.get(
            "/fichas/11111111-1111-1111-1111-111111111111/desenho/1",
            params={"tenant_id": "senai_labfashion"},
        )
        self.assertNotEqual(resposta.status_code, 401)

    def test_baixar_docx_exige_token(self):
        # Fase 15, V3: /docx saiu da lista de isenções -- a justificativa (<a href> sem header)
        # nunca foi verdadeira aqui, o frontend já busca via fetch(). Sem token, 401 -- não chega
        # a gerar o documento nem a tocar no status da ficha.
        resposta = self.client.get(
            "/fichas/11111111-1111-1111-1111-111111111111/docx",
            params={"tenant_id": "senai_labfashion"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_baixar_pdf_exige_token(self):
        resposta = self.client.get(
            "/fichas/11111111-1111-1111-1111-111111111111/pdf",
            params={"tenant_id": "senai_labfashion"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_exportar_conversa_exige_token(self):
        # Antes, esta rota devolvia o histórico completo da conversa sem credencial nenhuma.
        resposta = self.client.get(
            "/conversas/qualquer-id/export",
            params={"tenant_id": "senai_labfashion", "usuario_id": "qualquer-usuario"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_preview_continua_isenta_por_ser_consumida_por_iframe(self):
        # Diferente de /docx e /pdf: /preview é de fato consumida por <iframe src>
        # (urlPreviewFicha), que não manda header customizado -- isenção legítima, não mexida.
        resposta = self.client.get(
            "/fichas/11111111-1111-1111-1111-111111111111/preview",
            params={"tenant_id": "senai_labfashion"},
        )
        self.assertNotEqual(resposta.status_code, 401)


if __name__ == "__main__":
    unittest.main()
