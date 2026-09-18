# -*- coding: utf-8 -*-
"""`_normalizar_fontes_de_tool` preenche o trecho de fontes-string via pareamento posicional
com "trechos" (Fase 13, Task 17).

Antes: o ramo de fonte-string (usado por buscar_documentos_internos, que devolve rótulos como
"manual.pdf (Página 3)" em vez de dicts com URL) sempre gravava `trecho=""`, porque a função só
lia `dados_extras["fontes"]` e nunca `dados_extras["trechos"]`. Toda vez que o agente citasse um
documento interno, o popover do front-end mostraria "Trecho não disponível para esta fonte" --
mesmo com o trecho certo disponível ao lado, em "trechos". Este é um bug diferente do de
`montar_prompt_final` (que causava fontes/trechos DESALINHADOS); aqui a informação simplesmente
nunca era lida, alinhada ou não.
"""

import unittest

from agente_openai import _normalizar_fontes_de_tool


class TestNormalizarFontesDeTool(unittest.TestCase):

    def test_fonte_string_preenche_trecho_pareado_por_posicao(self):
        dados_extras = {
            "fontes": ["manual.pdf (Página 3)", "catalogo.csv (Linha 5)"],
            "trechos": [
                {"fonte": "manual.pdf", "texto": "gramatura 180 g/m2"},
                {"fonte": "catalogo.csv", "texto": "TX-200, Oxford"},
            ],
        }
        resultado = _normalizar_fontes_de_tool(dados_extras)
        self.assertEqual(resultado[0]["trecho"], "gramatura 180 g/m2")
        self.assertEqual(resultado[1]["trecho"], "TX-200, Oxford")
        self.assertEqual(resultado[0]["titulo"], "manual.pdf (Página 3)")

    def test_fonte_dict_com_url_real_ignora_trechos(self):
        # Formato de uma tool futura com URL real (ex: um provedor de busca web) -- já vem com o
        # próprio trecho embutido no dict, não precisa (nem deve) consultar "trechos".
        dados_extras = {
            "fontes": [{"titulo": "Artigo X", "url": "https://exemplo.com", "trecho": "resumo do artigo"}],
        }
        resultado = _normalizar_fontes_de_tool(dados_extras)
        self.assertEqual(resultado, [{"titulo": "Artigo X", "url": "https://exemplo.com", "trecho": "resumo do artigo"}])

    def test_fontes_sem_trechos_correspondentes_nao_quebra(self):
        # "trechos" ausente ou mais curto que "fontes" -- não deve levantar IndexError.
        dados_extras = {"fontes": ["manual.pdf (Página 3)"]}
        resultado = _normalizar_fontes_de_tool(dados_extras)
        self.assertEqual(resultado[0]["trecho"], "")

    def test_sem_fontes_devolve_lista_vazia(self):
        self.assertEqual(_normalizar_fontes_de_tool({}), [])
        self.assertEqual(_normalizar_fontes_de_tool({"fontes": []}), [])


if __name__ == "__main__":
    unittest.main()
