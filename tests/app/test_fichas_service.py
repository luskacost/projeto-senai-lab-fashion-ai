# -*- coding: utf-8 -*-
"""Testes de fichas_service.py (Fase 12).

Client sempre mockado -- nenhum destes testes gasta crédito de API real. `extrair_dados` e
`verificar_proveniencia` são mockados no nível do módulo (não reimplementam a extração real, que
já tem sua própria suíte em test_fichas_extracao.py/test_fichas_verificacao.py); o alvo aqui é só o
pipeline de orquestração (extrai -> verifica -> persiste -> incrementa uso), que POST /fichas e o
atalho gerar_ficha_tecnica do chat compartilham desde a Fase 12.
"""

import glob
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

import fichas_modelo as fm
import fichas_repo as fr
import fichas_service as fs

TENANT_TESTE = "teste_fase12_fichas_service"


class TestCriarFichaAPartirDeTexto(unittest.TestCase):

    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        for caminho in glob.glob(os.path.join(fr.DIRETORIO_FICHAS, f"{TENANT_TESTE}_*")):
            if os.path.isdir(caminho):
                shutil.rmtree(caminho, ignore_errors=True)
            else:
                os.remove(caminho)
        for caminho in glob.glob(os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json*")):
            os.remove(caminho)

    def test_persiste_a_ficha_com_os_dados_verificados(self):
        dados_extraidos = fm.dados_vazios()
        dados_verificados = fm.dados_vazios()
        dados_verificados["ficha"]["nome"] = {"valor": "Camisa Social Branca", "origem": "FORNECIDO", "trecho": "camisa social branca"}

        with patch("fichas_service.extrair_dados", return_value=dados_extraidos) as mock_extrair, \
             patch("fichas_service.verificar_proveniencia", return_value=(dados_verificados, [])) as mock_verificar:
            ficha, alertas = fs.criar_ficha_a_partir_de_texto(TENANT_TESTE, "camisa social branca", MagicMock())

        mock_extrair.assert_called_once()
        mock_verificar.assert_called_once_with(dados_extraidos, "camisa social branca")
        self.assertEqual(alertas, [])
        self.assertEqual(ficha["dados"]["ficha"]["nome"]["valor"], "Camisa Social Branca")

        recarregada = fr.carregar_ficha(TENANT_TESTE, ficha["id"])
        self.assertEqual(recarregada["dados"]["ficha"]["nome"]["valor"], "Camisa Social Branca")

    def test_marca_status_em_revisao(self):
        with patch("fichas_service.extrair_dados", return_value=fm.dados_vazios()), \
             patch("fichas_service.verificar_proveniencia", return_value=(fm.dados_vazios(), [])):
            ficha, _ = fs.criar_ficha_a_partir_de_texto(TENANT_TESTE, "algo", MagicMock())
        self.assertEqual(ficha["status"], fm.STATUS_EM_REVISAO)

    def test_grava_texto_origem(self):
        with patch("fichas_service.extrair_dados", return_value=fm.dados_vazios()), \
             patch("fichas_service.verificar_proveniencia", return_value=(fm.dados_vazios(), [])):
            ficha, _ = fs.criar_ficha_a_partir_de_texto(TENANT_TESTE, "vestido midi floral", MagicMock())
        self.assertEqual(ficha["texto_origem"], "vestido midi floral")

    def test_devolve_os_alertas_de_proveniencia(self):
        alertas_fake = [{"codigo": "X", "severidade": "aviso", "campo": "y", "mensagem": "z"}]
        with patch("fichas_service.extrair_dados", return_value=fm.dados_vazios()), \
             patch("fichas_service.verificar_proveniencia", return_value=(fm.dados_vazios(), alertas_fake)):
            _, alertas = fs.criar_ficha_a_partir_de_texto(TENANT_TESTE, "algo", MagicMock())
        self.assertEqual(alertas, alertas_fake)

    def test_incrementa_o_uso_de_fichas(self):
        with patch("fichas_service.extrair_dados", return_value=fm.dados_vazios()), \
             patch("fichas_service.verificar_proveniencia", return_value=(fm.dados_vazios(), [])):
            fs.criar_ficha_a_partir_de_texto(TENANT_TESTE, "algo", MagicMock())

        from usage_tracker import carregar_uso_do_dia
        self.assertEqual(carregar_uso_do_dia(TENANT_TESTE)["fichas"], 1)

    def test_nao_verifica_cota_diaria(self):
        # Responsabilidade do chamador (POST /fichas, POST /chat/croqui/confirmar) -- este módulo
        # não importa nem chama usage_tracker.verificar_limite; só incrementa o uso, depois que o
        # chamador já decidiu que a chamada é permitida.
        self.assertFalse(hasattr(fs, "verificar_limite"))


if __name__ == "__main__":
    unittest.main()
