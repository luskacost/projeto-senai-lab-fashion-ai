# -*- coding: utf-8 -*-
"""GET /uso -- uso visível (Fase 14, Bloco U, Task 9).

Antes desta task, o único jeito de descobrir que o limite diário tinha sido atingido era receber
o erro na hora de enviar uma mensagem. Esta rota devolve usado/limite/restante por categoria para
o front-end mostrar um indicador discreto antes disso virar surpresa.

Usa um tenant_id fictício e próprio para não colidir com tenant_data/senai_labfashion_usage.json;
remove o arquivo de uso no tearDown para não deixar debris em tenant_data/.
"""

import os
import unittest

from fastapi.testclient import TestClient

import tenant_config
from api.main import app
from usage_tracker import incrementar_uso

TENANT_TESTE = "teste_fase14_uso"


def _caminho_uso() -> str:
    return os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json")


class TestObterUso(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {
            "nome": "Tenant de Teste (Fase 14)",
            "limite_mensagens_dia": 200,
            "limite_imagens_dia": 30,
            "limite_buscas_web_dia": 50,
            "limite_fichas_dia": 30,
        }
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)

    def tearDown(self):
        if os.path.exists(_caminho_uso()):
            os.remove(_caminho_uso())

    def test_tenant_inexistente_devolve_404(self):
        resposta = self.client.get("/uso", params={"tenant_id": "tenant-que-nao-existe"})
        self.assertEqual(resposta.status_code, 404)

    def test_sem_nenhum_uso_ainda_devolve_zerado_e_restante_igual_ao_limite(self):
        resposta = self.client.get("/uso", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["categorias"]["mensagens"], {"usado": 0, "limite": 200, "restante": 200})
        self.assertEqual(corpo["categorias"]["buscas_web"], {"usado": 0, "limite": 50, "restante": 50})

    def test_uso_incrementado_reflete_no_usado_e_no_restante(self):
        incrementar_uso(TENANT_TESTE, "mensagens", 5)
        incrementar_uso(TENANT_TESTE, "buscas_web", 2)

        resposta = self.client.get("/uso", params={"tenant_id": TENANT_TESTE})
        corpo = resposta.json()
        self.assertEqual(corpo["categorias"]["mensagens"]["usado"], 5)
        self.assertEqual(corpo["categorias"]["mensagens"]["restante"], 195)
        self.assertEqual(corpo["categorias"]["buscas_web"]["usado"], 2)
        self.assertEqual(corpo["categorias"]["buscas_web"]["restante"], 48)

    def test_restante_nunca_fica_negativo_mesmo_acima_do_limite(self):
        incrementar_uso(TENANT_TESTE, "imagens", 999)

        resposta = self.client.get("/uso", params={"tenant_id": TENANT_TESTE})
        corpo = resposta.json()
        self.assertEqual(corpo["categorias"]["imagens"]["usado"], 999)
        self.assertEqual(corpo["categorias"]["imagens"]["restante"], 0)


if __name__ == "__main__":
    unittest.main()
