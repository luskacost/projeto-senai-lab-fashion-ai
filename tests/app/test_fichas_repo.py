# -*- coding: utf-8 -*-
"""Testes de fichas_repo.py (Fase 11, Task 5).

Usa um tenant_id fictício e próprio (não compartilhado com nenhum tenant real) e limpa todo
tenant_data/fichas/{TENANT_TESTE}* no tearDown -- mesmo cuidado de test_usage_tracker.py, pra não
deixar debris em tenant_data/ nem colidir com dado real de outro teste.
"""

import glob
import os
import shutil
import time
import unittest

import fichas_modelo as fm
import fichas_repo as fr

TENANT_TESTE = "teste_task5_fichas_repo"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(fr.DIRETORIO_FICHAS, f"{TENANT_TESTE}_*")):
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            os.remove(caminho)


class TestRepoFichasBase(unittest.TestCase):
    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()


class TestCriarFicha(TestRepoFichasBase):

    def test_cria_com_id_e_timestamps(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        self.assertTrue(ficha["id"])
        self.assertTrue(ficha["criado_em"])
        self.assertEqual(ficha["criado_em"], ficha["atualizado_em"])
        self.assertEqual(ficha["status"], fm.STATUS_RASCUNHO)

    def test_cria_com_texto_origem(self):
        ficha = fr.criar_ficha(TENANT_TESTE, texto_origem="camisa preta de algodão")
        self.assertEqual(ficha["texto_origem"], "camisa preta de algodão")

    def test_cria_sem_texto_origem_fica_vazio(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        self.assertEqual(ficha["texto_origem"], "")

    def test_sem_precificacao_padrao_nasce_zerada(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        self.assertEqual(ficha["precificacao"], {
            "imposto_percentual": 0.0, "comissao_percentual": 0.0, "margem_lucro_percentual": 0.0,
        })

    def test_com_precificacao_padrao_semeia_os_parametros(self):
        ficha = fr.criar_ficha(TENANT_TESTE, precificacao_padrao={"margem_lucro_percentual": 30.0})
        self.assertEqual(ficha["precificacao"]["margem_lucro_percentual"], 30.0)
        # Chaves não informadas no padrão continuam zeradas -- merge parcial, não substituição.
        self.assertEqual(ficha["precificacao"]["imposto_percentual"], 0.0)

    def test_persiste_em_disco_e_e_recarregavel(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        recarregada = fr.carregar_ficha(TENANT_TESTE, ficha["id"])
        self.assertEqual(recarregada, ficha)

    def test_aparece_no_indice(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        indice = fr.listar_fichas(TENANT_TESTE)
        self.assertIn(ficha["id"], [e["id"] for e in indice])

    def test_ids_diferentes_a_cada_chamada(self):
        f1 = fr.criar_ficha(TENANT_TESTE)
        f2 = fr.criar_ficha(TENANT_TESTE)
        self.assertNotEqual(f1["id"], f2["id"])


class TestCarregarFicha(TestRepoFichasBase):

    def test_inexistente_devolve_none(self):
        self.assertIsNone(fr.carregar_ficha(TENANT_TESTE, "11111111-1111-1111-1111-111111111111"))

    def test_ficha_id_malformado_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fr.carregar_ficha(TENANT_TESTE, "../../etc/passwd")

    def test_ficha_id_com_barra_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fr.carregar_ficha(TENANT_TESTE, "algum/id")

    def test_ficha_id_vazio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fr.carregar_ficha(TENANT_TESTE, "")

    def test_path_traversal_nao_cria_nada_fora_do_diretorio_esperado(self):
        base_antes = set(os.listdir(fr.DIRETORIO_FICHAS)) if os.path.isdir(fr.DIRETORIO_FICHAS) else set()
        with self.assertRaises(ValueError):
            fr.carregar_ficha(TENANT_TESTE, "../evil")
        base_depois = set(os.listdir(fr.DIRETORIO_FICHAS)) if os.path.isdir(fr.DIRETORIO_FICHAS) else set()
        self.assertEqual(base_antes, base_depois)


class TestListarFichas(TestRepoFichasBase):

    def test_vazio_quando_nao_ha_fichas(self):
        self.assertEqual(fr.listar_fichas(TENANT_TESTE), [])

    def test_ordenado_por_atualizado_em_desc(self):
        f1 = fr.criar_ficha(TENANT_TESTE)
        time.sleep(0.01)
        f2 = fr.criar_ficha(TENANT_TESTE)
        indice = fr.listar_fichas(TENANT_TESTE)
        ids = [e["id"] for e in indice]
        self.assertEqual(ids.index(f2["id"]), 0)
        self.assertLess(ids.index(f2["id"]), ids.index(f1["id"]))

    def test_entrada_tem_campos_esperados(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        entrada = next(e for e in fr.listar_fichas(TENANT_TESTE) if e["id"] == ficha["id"])
        # "aprovada_por" entrou na Fase 14, Bloco AP: a lista de fichas mostra quem aprovou sem
        # precisar abrir o JSON completo de cada uma -- mesma razão de ref/nome estarem no índice.
        self.assertEqual(
            set(entrada.keys()),
            {"id", "ref", "nome", "status", "criado_em", "atualizado_em", "aprovada_por"},
        )

    def test_entrada_traz_quem_aprovou(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        ficha["aprovacao"]["aprovada_por"] = "Ana Paula"
        fr.salvar_ficha(TENANT_TESTE, ficha)

        entrada = next(e for e in fr.listar_fichas(TENANT_TESTE) if e["id"] == ficha["id"])
        self.assertEqual(entrada["aprovada_por"], "Ana Paula")

    def test_entrada_de_ficha_antiga_sem_aprovacao_nao_quebra(self):
        # Ficha salva antes da Fase 14 não tem a chave "aprovacao" nenhuma.
        ficha = fr.criar_ficha(TENANT_TESTE)
        del ficha["aprovacao"]
        fr.salvar_ficha(TENANT_TESTE, ficha)

        entrada = next(e for e in fr.listar_fichas(TENANT_TESTE) if e["id"] == ficha["id"])
        self.assertEqual(entrada["aprovada_por"], "")

    def test_entrada_reflete_ref_e_nome_da_ficha(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        ficha["dados"]["ficha"]["ref"] = {"valor": "CM-001", "origem": fm.ORIGEM_FORNECIDO, "trecho": "CM-001"}
        ficha["dados"]["ficha"]["nome"] = {"valor": "Camisa Social", "origem": fm.ORIGEM_FORNECIDO, "trecho": "camisa social"}
        fr.salvar_ficha(TENANT_TESTE, ficha)

        entrada = next(e for e in fr.listar_fichas(TENANT_TESTE) if e["id"] == ficha["id"])
        self.assertEqual(entrada["ref"], "CM-001")
        self.assertEqual(entrada["nome"], "Camisa Social")


class TestSalvarFicha(TestRepoFichasBase):

    def test_atualiza_atualizado_em(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        criado_em_original = ficha["criado_em"]
        time.sleep(0.01)

        salva = fr.salvar_ficha(TENANT_TESTE, ficha)
        self.assertNotEqual(salva["atualizado_em"], criado_em_original)
        self.assertEqual(salva["criado_em"], criado_em_original)

    def test_mudancas_persistem(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        ficha["status"] = fm.STATUS_EM_REVISAO
        fr.salvar_ficha(TENANT_TESTE, ficha)

        recarregada = fr.carregar_ficha(TENANT_TESTE, ficha["id"])
        self.assertEqual(recarregada["status"], fm.STATUS_EM_REVISAO)

    def test_sem_atualizado_em_esperado_nao_verifica_conflito(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        fr.salvar_ficha(TENANT_TESTE, {**ficha, "status": fm.STATUS_APROVADA})  # não deveria lançar

    def test_atualizado_em_esperado_correto_permite_salvar(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        fr.salvar_ficha(TENANT_TESTE, ficha, atualizado_em_esperado=ficha["atualizado_em"])  # não lança

    def test_atualizado_em_esperado_divergente_levanta_conflito(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        # Simula outra sessão salvando entre a leitura e a tentativa de escrita desta sessão.
        fr.salvar_ficha(TENANT_TESTE, {**ficha})
        with self.assertRaises(fr.ConflitoDeVersaoError):
            fr.salvar_ficha(TENANT_TESTE, ficha, atualizado_em_esperado=ficha["atualizado_em"])

    def test_ficha_id_malformado_levanta_value_error(self):
        ficha = fm.ficha_vazia()
        ficha["id"] = "not-a-uuid"
        with self.assertRaises(ValueError):
            fr.salvar_ficha(TENANT_TESTE, ficha)


class TestDuplicarFicha(TestRepoFichasBase):

    def test_copia_tem_id_novo(self):
        original = fr.criar_ficha(TENANT_TESTE, texto_origem="camisa azul")
        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        self.assertNotEqual(copia["id"], original["id"])

    def test_copia_reseta_status_para_rascunho(self):
        original = fr.criar_ficha(TENANT_TESTE)
        original["status"] = fm.STATUS_APROVADA
        fr.salvar_ficha(TENANT_TESTE, original)

        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        self.assertEqual(copia["status"], fm.STATUS_RASCUNHO)

    def test_copia_preserva_dados_e_texto_origem(self):
        original = fr.criar_ficha(TENANT_TESTE, texto_origem="camisa azul")
        original["dados"]["ficha"]["nome"] = {"valor": "Camisa Azul", "origem": fm.ORIGEM_FORNECIDO, "trecho": "camisa azul"}
        fr.salvar_ficha(TENANT_TESTE, original)

        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        self.assertEqual(copia["dados"]["ficha"]["nome"]["valor"], "Camisa Azul")
        self.assertEqual(copia["texto_origem"], "camisa azul")

    def test_copia_preserva_precificacao(self):
        # Fase 14, Bloco P, Task 19: precificacao segue o tratamento de "dados" (copiado), não o
        # de "desenho" (derivado, não copiado) -- são parâmetros configurados pela pessoa.
        original = fr.criar_ficha(TENANT_TESTE, precificacao_padrao={"margem_lucro_percentual": 40.0})
        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        self.assertEqual(copia["precificacao"]["margem_lucro_percentual"], 40.0)

    def test_copia_nao_herda_desenho_nem_documentos(self):
        original = fr.criar_ficha(TENANT_TESTE)
        original["desenho"]["solicitado"] = True
        original["desenho"]["versoes"] = [{"v": 1, "arquivo": "desenho_v1.png", "status": "aprovado"}]
        original["documentos"]["docx"] = "ficha.docx"
        fr.salvar_ficha(TENANT_TESTE, original)

        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        self.assertFalse(copia["desenho"]["solicitado"])
        self.assertEqual(copia["desenho"]["versoes"], [])
        self.assertEqual(copia["documentos"]["docx"], "")

    def test_editar_copia_nao_afeta_original(self):
        original = fr.criar_ficha(TENANT_TESTE)
        copia = fr.duplicar_ficha(TENANT_TESTE, original["id"])
        copia["dados"]["ficha"]["nome"] = {"valor": "Mudou só na cópia", "origem": fm.ORIGEM_FORNECIDO, "trecho": "x"}
        fr.salvar_ficha(TENANT_TESTE, copia)

        original_recarregado = fr.carregar_ficha(TENANT_TESTE, original["id"])
        self.assertEqual(original_recarregado["dados"]["ficha"]["nome"]["valor"], "")

    def test_original_inexistente_devolve_none(self):
        self.assertIsNone(fr.duplicar_ficha(TENANT_TESTE, "11111111-1111-1111-1111-111111111111"))


class TestDeletarFicha(TestRepoFichasBase):

    def test_remove_do_disco(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        self.assertTrue(fr.deletar_ficha(TENANT_TESTE, ficha["id"]))
        self.assertIsNone(fr.carregar_ficha(TENANT_TESTE, ficha["id"]))
        self.assertFalse(os.path.isdir(fr._dir_ficha(TENANT_TESTE, ficha["id"])))

    def test_remove_do_indice(self):
        ficha = fr.criar_ficha(TENANT_TESTE)
        fr.deletar_ficha(TENANT_TESTE, ficha["id"])
        self.assertNotIn(ficha["id"], [e["id"] for e in fr.listar_fichas(TENANT_TESTE)])

    def test_inexistente_devolve_false(self):
        self.assertFalse(fr.deletar_ficha(TENANT_TESTE, "11111111-1111-1111-1111-111111111111"))

    def test_nao_afeta_outras_fichas(self):
        f1 = fr.criar_ficha(TENANT_TESTE)
        f2 = fr.criar_ficha(TENANT_TESTE)
        fr.deletar_ficha(TENANT_TESTE, f1["id"])
        self.assertIsNotNone(fr.carregar_ficha(TENANT_TESTE, f2["id"]))
        self.assertIn(f2["id"], [e["id"] for e in fr.listar_fichas(TENANT_TESTE)])


if __name__ == "__main__":
    unittest.main()
