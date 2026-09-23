# -*- coding: utf-8 -*-
"""Testes da rota HTTP POST /planilha/upload (Fase 15, Bloco V, V2).

Antes desta correção, `conversation_id` (query param, string livre) chegava cru em
`analise_dados.salvar_resumo_estatistico`, sem validação nenhuma na rota. Ver
tests/app/test_analise_dados.py para a prova em disco do path traversal.

Usa um tenant fictício, injetado em tenant_config.TENANT_CONFIG só durante esta suíte.
"""

import glob
import io
import os
import unittest
import uuid

from fastapi.testclient import TestClient

import tenant_config
from analise_dados import DIRETORIO_ANALISE_DADOS
from api.main import app

TENANT_TESTE = "teste_fase15_api_planilha_upload"
CONVERSA_VALIDA = str(uuid.uuid4())

CSV_MINIMO = b"produto,quantidade\nVestido,10\nCamisa,5\n"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(DIRETORIO_ANALISE_DADOS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestApiPlanilhaUpload(unittest.TestCase):

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

    def _upload(self, conversation_id: str):
        return self.client.post(
            "/planilha/upload",
            params={"tenant_id": TENANT_TESTE, "conversation_id": conversation_id},
            files={"arquivo": ("planilha.csv", io.BytesIO(CSV_MINIMO), "text/csv")},
        )

    def test_conversation_id_malformado_e_recusado_com_400(self):
        r = self._upload("../../../escrita_maliciosa")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(os.path.exists(os.path.join("tenant_data", "escrita_maliciosa.json")))

    def test_conversation_id_malformado_nao_gasta_o_parsing_da_planilha(self):
        # A validação roda antes do parsing (fail-fast): confirma que o CSV nem chega a ser lido
        # checando que nenhum arquivo de resumo foi criado para o tenant de teste.
        self._upload("<script>alert(1)</script>")
        self.assertEqual(glob.glob(os.path.join(DIRETORIO_ANALISE_DADOS, f"{TENANT_TESTE}_*")), [])

    def test_conversation_id_valido_continua_funcionando(self):
        r = self._upload(CONVERSA_VALIDA)
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo["nome_arquivo"], "planilha.csv")
        self.assertEqual(corpo["linhas"], 2)


if __name__ == "__main__":
    unittest.main()
