# -*- coding: utf-8 -*-
"""Testes de conversas_manager.py -- path traversal em usuario_id (Fase 15, Bloco V, V2).

Antes desta correção, `usuario_id` (que vem do `localStorage` do navegador -- controle total do
cliente) entrava cru em `f"{tenant_id}_{usuario_id}.json"`, sem validação nenhuma. Um valor como
"../../../etc/passwd" virava parte literal do caminho de arquivo.

Usa um tenant_id fictício e próprio, limpando tenant_data/conversas/{TENANT_TESTE}_* no tearDown.
"""

import glob
import os
import unittest
import uuid

import conversas_manager as cm

TENANT_TESTE = "teste_fase15_conversas_manager"
USUARIO_VALIDO = str(uuid.uuid4())


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(cm.DIRETORIO_CONVERSAS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestCaminhoConversas(unittest.TestCase):

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def test_usuario_id_valido_gera_caminho_esperado(self):
        caminho = cm._caminho_conversas(TENANT_TESTE, USUARIO_VALIDO)
        self.assertTrue(caminho.endswith(f"{TENANT_TESTE}_{USUARIO_VALIDO}.json"))

    def test_usuario_id_com_traversal_levanta_value_error(self):
        for malicioso in ("../../../etc/passwd", "..\\..\\windows", "a/b", "a\\b", ""):
            with self.subTest(usuario_id=malicioso):
                with self.assertRaises(ValueError):
                    cm._caminho_conversas(TENANT_TESTE, malicioso)

    def test_usuario_id_nao_string_levanta_value_error(self):
        with self.assertRaises(ValueError):
            cm._caminho_conversas(TENANT_TESTE, 12345)

    def test_tenant_id_e_sanitizado_por_allowlist_nao_por_uuid(self):
        # tenant_id não é UUID (é um slug de config) -- caractere fora da allowlist é removido,
        # não rejeitado, mesmo padrão de rag_manager._obter_caminho_chroma.
        caminho = cm._caminho_conversas("tenant/../malicioso", USUARIO_VALIDO)
        nome_arquivo = os.path.basename(caminho)
        self.assertNotIn("..", nome_arquivo)
        self.assertNotIn("/", nome_arquivo)
        self.assertNotIn("\\", nome_arquivo)


class TestCarregarESalvarConversas(unittest.TestCase):

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def test_carregar_com_usuario_id_malicioso_levanta_value_error(self):
        with self.assertRaises(ValueError):
            cm.carregar_conversas(TENANT_TESTE, "../../../etc/passwd")

    def test_salvar_com_usuario_id_malicioso_levanta_value_error_e_nao_escreve_nada(self):
        with self.assertRaises(ValueError):
            cm.salvar_conversas(TENANT_TESTE, "../../../escrita_maliciosa", [{"id": "x"}])
        self.assertFalse(os.path.exists(os.path.join("tenant_data", "escrita_maliciosa.json")))

    def test_fluxo_normal_continua_funcionando_com_usuario_id_valido(self):
        cm.salvar_conversas(TENANT_TESTE, USUARIO_VALIDO, [{"id": "c1", "titulo": "Teste"}])
        conversas = cm.carregar_conversas(TENANT_TESTE, USUARIO_VALIDO)
        self.assertEqual(len(conversas), 1)
        self.assertEqual(conversas[0]["titulo"], "Teste")

    def test_dois_usuarios_nao_compartilham_arquivo(self):
        outro_usuario = str(uuid.uuid4())
        cm.salvar_conversas(TENANT_TESTE, USUARIO_VALIDO, [{"id": "c1"}])
        cm.salvar_conversas(TENANT_TESTE, outro_usuario, [{"id": "c2"}])
        self.assertEqual([c["id"] for c in cm.carregar_conversas(TENANT_TESTE, USUARIO_VALIDO)], ["c1"])
        self.assertEqual([c["id"] for c in cm.carregar_conversas(TENANT_TESTE, outro_usuario)], ["c2"])


if __name__ == "__main__":
    unittest.main()
