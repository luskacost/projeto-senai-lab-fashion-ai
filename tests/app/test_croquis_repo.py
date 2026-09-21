# -*- coding: utf-8 -*-
"""Testes de croquis_repo.py (Fase 14, Bloco G, Task 12).

Usa um tenant_id fictício e próprio, limpo no setUp/tearDown -- mesmo cuidado de
test_fichas_repo.py, pra não deixar debris em tenant_data/ nem colidir com dado real.
"""

import glob
import os
import unittest

import croquis_repo as cr

TENANT_TESTE = "teste_task12_croquis_repo"
PNG_FAKE = b"conteudo-png-fake-para-teste"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(cr.DIRETORIO_CROQUIS, f"{TENANT_TESTE}_*")):
        os.remove(caminho)


class TestRepoCroquisBase(unittest.TestCase):
    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()


class TestSalvarCroqui(TestRepoCroquisBase):

    def test_gera_id_e_grava_o_png_em_disco(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self.assertTrue(entrada["id"])
        caminho = cr.caminho_croqui(TENANT_TESTE, entrada["id"])
        self.assertIsNotNone(caminho)
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), PNG_FAKE)

    def test_guarda_estilo_e_resumo_como_metadados(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE, estilo="Ilustração de Moda", resumo="Um vestido midi floral")
        self.assertEqual(entrada["estilo"], "Ilustração de Moda")
        self.assertEqual(entrada["resumo"], "Um vestido midi floral")

    def test_sem_estilo_e_resumo_ficam_vazios(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self.assertEqual(entrada["estilo"], "")
        self.assertEqual(entrada["resumo"], "")

    def test_tem_timestamp_de_criacao(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self.assertTrue(entrada["criado_em"])

    def test_aparece_na_listagem(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        listagem = cr.listar_croquis(TENANT_TESTE)
        self.assertEqual([e["id"] for e in listagem], [entrada["id"]])

    def test_dois_croquis_tem_ids_diferentes_e_nao_se_sobrescrevem(self):
        a = cr.salvar_croqui(TENANT_TESTE, b"png-a")
        b = cr.salvar_croqui(TENANT_TESTE, b"png-b")
        self.assertNotEqual(a["id"], b["id"])

        with open(cr.caminho_croqui(TENANT_TESTE, a["id"]), "rb") as f:
            self.assertEqual(f.read(), b"png-a")
        with open(cr.caminho_croqui(TENANT_TESTE, b["id"]), "rb") as f:
            self.assertEqual(f.read(), b"png-b")


class TestListarCroquis(TestRepoCroquisBase):

    def test_lista_vazia_para_tenant_sem_nenhum_croqui(self):
        self.assertEqual(cr.listar_croquis(TENANT_TESTE), [])

    def test_mais_recente_primeiro(self):
        primeiro = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE, resumo="primeiro")
        segundo = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE, resumo="segundo")
        listagem = cr.listar_croquis(TENANT_TESTE)
        self.assertEqual(listagem[0]["id"], segundo["id"])
        self.assertEqual(listagem[1]["id"], primeiro["id"])


class TestCaminhoCroqui(TestRepoCroquisBase):

    def test_none_para_croqui_inexistente_com_id_valido(self):
        self.assertIsNone(cr.caminho_croqui(TENANT_TESTE, "0d95d17e-ca9c-442f-9db3-dcbf3a6ec7b5"))

    def test_levanta_value_error_para_id_malformado(self):
        with self.assertRaises(ValueError):
            cr.caminho_croqui(TENANT_TESTE, "../../etc/passwd")

    def test_levanta_value_error_para_id_nao_string(self):
        with self.assertRaises(ValueError):
            cr.caminho_croqui(TENANT_TESTE, 12345)


class TestDeletarCroqui(TestRepoCroquisBase):

    def test_remove_arquivo_e_indice(self):
        entrada = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        self.assertTrue(cr.deletar_croqui(TENANT_TESTE, entrada["id"]))
        self.assertIsNone(cr.caminho_croqui(TENANT_TESTE, entrada["id"]))
        self.assertEqual(cr.listar_croquis(TENANT_TESTE), [])

    def test_devolve_false_para_croqui_inexistente(self):
        self.assertFalse(cr.deletar_croqui(TENANT_TESTE, "0d95d17e-ca9c-442f-9db3-dcbf3a6ec7b5"))

    def test_levanta_value_error_para_id_malformado(self):
        with self.assertRaises(ValueError):
            cr.deletar_croqui(TENANT_TESTE, "../../etc/passwd")

    def test_nao_afeta_outro_croqui_do_mesmo_tenant(self):
        a = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        b = cr.salvar_croqui(TENANT_TESTE, PNG_FAKE)
        cr.deletar_croqui(TENANT_TESTE, a["id"])
        self.assertIsNotNone(cr.caminho_croqui(TENANT_TESTE, b["id"]))
        self.assertEqual([e["id"] for e in cr.listar_croquis(TENANT_TESTE)], [b["id"]])


if __name__ == "__main__":
    unittest.main()
