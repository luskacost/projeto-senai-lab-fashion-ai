# -*- coding: utf-8 -*-
"""POST /fichas/{id}/desenho/importar-croqui (Fase 14, Bloco G, Task 17).

Reaproveita um croqui já salvo na galeria como versão do desenho técnico da ficha -- sem
moderação, sem checagem de cota, sem chamada de API nenhuma (a imagem já foi moderada e cobrada
quando foi gerada no chat). `api.main.OpenAI` nunca é mockado aqui de propósito: se a rota
tentasse chamar a API de geração de imagem, o teste devia falhar por não ter mock nenhum
configurado -- é a prova de que este caminho realmente não gasta uma chamada nova.

Tenant fictício próprio, limpando fichas_repo.DIRETORIO_FICHAS e croquis_repo.DIRETORIO_CROQUIS
no tearDown.
"""

import glob
import os
import shutil
import unittest

from fastapi.testclient import TestClient

import croquis_repo as cr
import fichas_modelo as fm
import fichas_repo as fr
import tenant_config
from api.main import app

TENANT_TESTE = "teste_fase14_importar_croqui_desenho"
UUID_INEXISTENTE = "11111111-1111-1111-1111-111111111111"
PNG_FAKE = b"\x89PNG\r\n\x1a\n" + b"conteudo minimo do croqui"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(fr.DIRETORIO_FICHAS, f"{TENANT_TESTE}_*")):
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            os.remove(caminho)
    for caminho in glob.glob(os.path.join(cr.DIRETORIO_CROQUIS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestImportarCroquiComoDesenho(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Fase 14)"}
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def _importar(self, ficha_id, croqui_id):
        return self.client.post(
            f"/fichas/{ficha_id}/desenho/importar-croqui",
            json={"tenant_id": TENANT_TESTE, "croqui_id": croqui_id},
        )

    def test_tenant_inexistente_404(self):
        r = self.client.post(
            f"/fichas/{UUID_INEXISTENTE}/desenho/importar-croqui",
            json={"tenant_id": "tenant_que_nao_existe", "croqui_id": UUID_INEXISTENTE},
        )
        self.assertEqual(r.status_code, 404)

    def test_ficha_inexistente_404(self):
        r = self._importar(UUID_INEXISTENTE, UUID_INEXISTENTE)
        self.assertEqual(r.status_code, 404)

    def test_croqui_inexistente_404(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self._importar(criada["id"], UUID_INEXISTENTE)
        self.assertEqual(r.status_code, 404)

    def test_croqui_id_malformado_400(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self._importar(criada["id"], "nao-e-um-uuid")
        self.assertEqual(r.status_code, 400)

    def test_importa_com_sucesso_sem_chamar_nenhuma_api(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        croqui = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE, estilo="🎨 Ilustração de Moda", resumo="Um vestido midi floral")

        r = self._importar(criada["id"], croqui["id"])

        self.assertEqual(r.status_code, 200)
        corpo = r.json()["ficha"]
        self.assertEqual(len(corpo["desenho"]["versoes"]), 1)
        self.assertEqual(corpo["desenho"]["versoes"][0]["versao"], 1)
        self.assertEqual(corpo["desenho"]["versoes"][0]["status"], fm.DESENHO_AGUARDANDO_APROVACAO)
        self.assertEqual(corpo["status"], fm.STATUS_DESENHO_GERADO)

    def test_conteudo_importado_bate_com_o_png_do_croqui(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        croqui = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self._importar(criada["id"], croqui["id"])

        r = self.client.get(f"/fichas/{criada['id']}/desenho/1", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, PNG_FAKE)

    def test_nao_incrementa_cota_de_imagens(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        croqui = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self._importar(criada["id"], croqui["id"])

        from usage_tracker import carregar_uso_do_dia
        uso = carregar_uso_do_dia(TENANT_TESTE)
        self.assertEqual(uso.get("imagens", 0), 0)

    def test_importar_uma_segunda_vez_gera_versao_2_sem_substituir_a_1(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        croqui_a = cr.salvar_croqui(TENANT_TESTE, b"png-a")
        croqui_b = cr.salvar_croqui(TENANT_TESTE, b"png-b")

        self._importar(criada["id"], croqui_a["id"])
        r = self._importar(criada["id"], croqui_b["id"])

        corpo = r.json()["ficha"]
        self.assertEqual(len(corpo["desenho"]["versoes"]), 2)

        r1 = self.client.get(f"/fichas/{criada['id']}/desenho/1", params={"tenant_id": TENANT_TESTE})
        r2 = self.client.get(f"/fichas/{criada['id']}/desenho/2", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r1.content, b"png-a")
        self.assertEqual(r2.content, b"png-b")


if __name__ == "__main__":
    unittest.main()
