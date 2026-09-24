# -*- coding: utf-8 -*-
"""Testes de sugestoes_repo.py (Fase 16, Bloco S, S1).

Persistência simples por tenant, mesmo padrão de `conversas_manager.py` -- FileLock contra
escrita concorrente, tenant_id sanitizado por allowlist (não é UUID).
"""

import glob
import os
import unittest

import sugestoes_repo as sr

TENANT_TESTE = "teste_fase16_sugestoes"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(sr.DIRETORIO_SUGESTOES, f"{TENANT_TESTE}*")):
        os.remove(caminho)


class TestRegistrarSugestao(unittest.TestCase):

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()

    def test_carregar_sem_arquivo_devolve_lista_vazia(self):
        self.assertEqual(sr.carregar_sugestoes(TENANT_TESTE), [])

    def test_registrar_sugestao_persiste_e_pode_ser_recarregada(self):
        registro = sr.registrar_sugestao(TENANT_TESTE, "sugestao", "Seria bom ter um modo escuro.")
        self.assertEqual(registro["tipo"], "sugestao")
        self.assertEqual(registro["texto"], "Seria bom ter um modo escuro.")
        self.assertIn("id", registro)
        self.assertIn("criado_em", registro)

        recarregadas = sr.carregar_sugestoes(TENANT_TESTE)
        self.assertEqual(len(recarregadas), 1)
        self.assertEqual(recarregadas[0]["id"], registro["id"])

    def test_registrar_bug_com_tipo_valido(self):
        registro = sr.registrar_sugestao(TENANT_TESTE, "bug", "O botão de exportar não funciona.")
        self.assertEqual(registro["tipo"], "bug")

    def test_multiplos_registros_acumulam_na_mesma_lista(self):
        sr.registrar_sugestao(TENANT_TESTE, "sugestao", "Primeira.")
        sr.registrar_sugestao(TENANT_TESTE, "bug", "Segunda.")
        sugestoes = sr.carregar_sugestoes(TENANT_TESTE)
        self.assertEqual(len(sugestoes), 2)

    def test_tipo_invalido_levanta_value_error(self):
        with self.assertRaises(ValueError):
            sr.registrar_sugestao(TENANT_TESTE, "elogio", "Texto qualquer.")

    def test_texto_vazio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            sr.registrar_sugestao(TENANT_TESTE, "sugestao", "   ")

    def test_tenants_diferentes_nao_compartilham_arquivo(self):
        outro_tenant = f"{TENANT_TESTE}_outro"
        try:
            sr.registrar_sugestao(TENANT_TESTE, "sugestao", "Do tenant principal.")
            sr.registrar_sugestao(outro_tenant, "sugestao", "De outro tenant.")

            self.assertEqual(len(sr.carregar_sugestoes(TENANT_TESTE)), 1)
            self.assertEqual(len(sr.carregar_sugestoes(outro_tenant)), 1)
        finally:
            for caminho in glob.glob(os.path.join(sr.DIRETORIO_SUGESTOES, f"{outro_tenant}*")):
                os.remove(caminho)


if __name__ == "__main__":
    unittest.main()
