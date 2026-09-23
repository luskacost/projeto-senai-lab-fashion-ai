# -*- coding: utf-8 -*-
"""Mensagem de erro do parsing de documento não vaza detalhe interno (Fase 15, V5).

`extrair_documento_com_dados_tabulares` tinha um fallback (`except Exception as e`) que embutia
a exceção original, sem filtro nenhum, na mensagem da `ValueError` que se propaga -- e
`POST /documentos/upload` (api/main.py) repassa essa mensagem direto como `detail` da resposta
HTTP. Uma exceção de biblioteca de parsing pode carregar caminho de arquivo, traço de pilha
resumido ou mensagem interna do parser; nada disso deveria chegar a quem fez o upload.
"""

import unittest
from unittest.mock import patch

from document_extractors import extrair_documento_com_dados_tabulares

# Texto que, se vazasse pra fora, seria um sinal claro do bug -- não algo que apareceria por
# acaso numa mensagem de erro genérica escrita por nós.
DETALHE_SENSIVEL = "C:\\Segredos\\chave_interna.pem linha 42 do parser XML"


class TestMensagemDeErroNaoVazaDetalheInterno(unittest.TestCase):

    @patch("document_extractors.extrair_documento_txt")
    def test_excecao_generica_na_extracao_nao_aparece_na_mensagem(self, mock_extrair):
        mock_extrair.side_effect = RuntimeError(DETALHE_SENSIVEL)

        with self.assertRaises(ValueError) as ctx:
            extrair_documento_com_dados_tabulares(b"conteudo qualquer", nome_arquivo="relatorio.txt")

        mensagem = str(ctx.exception)
        self.assertNotIn(DETALHE_SENSIVEL, mensagem)
        self.assertNotIn("chave_interna", mensagem)

    @patch("document_extractors.extrair_documento_txt")
    def test_mensagem_devolvida_e_generica_mas_util(self, mock_extrair):
        mock_extrair.side_effect = RuntimeError(DETALHE_SENSIVEL)

        with self.assertRaises(ValueError) as ctx:
            extrair_documento_com_dados_tabulares(b"x", nome_arquivo="relatorio.txt")

        mensagem = str(ctx.exception)
        self.assertIn("relatorio.txt", mensagem)  # ainda diz qual arquivo falhou
        self.assertIn("corrompido", mensagem.lower())

    @patch("document_extractors.obter_logger")
    @patch("document_extractors.extrair_documento_txt")
    def test_detalhe_completo_continua_indo_pro_log(self, mock_extrair, mock_obter_logger):
        # O detalhe não desaparece -- só sai da resposta HTTP. Quem precisa dele (quem administra
        # o servidor) continua tendo acesso via log, com stack trace.
        mock_extrair.side_effect = RuntimeError(DETALHE_SENSIVEL)
        logger_falso = mock_obter_logger.return_value

        with self.assertRaises(ValueError):
            extrair_documento_com_dados_tabulares(b"x", nome_arquivo="relatorio.txt")

        mensagem_logada = logger_falso.error.call_args.args[0]
        self.assertIn(DETALHE_SENSIVEL, mensagem_logada)
        # exc_info=True é o que garante o stack trace completo no arquivo de log.
        self.assertTrue(logger_falso.error.call_args.kwargs.get("exc_info"))


if __name__ == "__main__":
    unittest.main()
