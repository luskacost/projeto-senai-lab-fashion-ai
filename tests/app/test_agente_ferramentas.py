# -*- coding: utf-8 -*-
"""Testes do registry de ferramentas do agente (agente_ferramentas.py, Fase 10, Bloco A)."""

import unittest
from unittest.mock import MagicMock, patch

from agente_ferramentas import (
    ContextoExecucao,
    ErroValidacaoFerramenta,
    Ferramenta,
    LIMITE_CONTEUDO_FERRAMENTA_CHARS,
    ResultadoFerramenta,
    executar_ferramenta,
    exige_confirmacao,
    listar_nomes,
    obter_ferramenta,
    resumir_para_log,
    schemas_para,
    truncar_conteudo,
    validar_argumentos,
)

FAKE_B64 = "ZmFrZS1wbmctYnl0ZXM="
FAKE_DATA_URI = "data:image/png;base64," + FAKE_B64


def _ferramenta_de_teste(handler=None) -> Ferramenta:
    return Ferramenta(
        nome="ferramenta_ficticia",
        descricao="Só para teste.",
        propriedades={
            "texto": {"type": "string", "description": "um texto"},
            "quantidade": {"type": "integer", "description": "um número"},
        },
        obrigatorios=["texto"],
        handler=handler or (lambda args, ctx: ResultadoFerramenta(conteudo="ok")),
    )


class TestSchemaResponsesApi(unittest.TestCase):
    """A Responses API usa o formato *flat* -- o formato aninhado da Chat Completions
    (`{"type":"function","function":{...}}`) é rejeitado com 400 lá."""

    def test_schema_e_flat_e_nao_aninhado(self):
        schema = _ferramenta_de_teste().para_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["name"], "ferramenta_ficticia")
        self.assertIn("parameters", schema)
        self.assertNotIn("function", schema)

    def test_schema_marca_additional_properties_false(self):
        schema = _ferramenta_de_teste().para_schema()
        self.assertFalse(schema["parameters"]["additionalProperties"])
        self.assertEqual(schema["parameters"]["required"], ["texto"])

    def test_schemas_para_ignora_nome_desconhecido_sem_quebrar(self):
        schemas = schemas_para(["gerar_imagem_croqui", "ferramenta_que_nao_existe"])
        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["name"], "gerar_imagem_croqui")

    def test_schemas_para_sem_nomes_retorna_vazio(self):
        self.assertEqual(schemas_para(None), [])
        self.assertEqual(schemas_para([]), [])


class TestInvarianteDeSeguranca(unittest.TestCase):
    """A invariante que sustenta o isolamento multi-tenant do agente inteiro."""

    def test_nenhuma_ferramenta_aceita_tenant_id_ou_credencial_do_modelo(self):
        # Se algum dia alguém declarar uma ferramenta com tenant_id nos parâmetros, o modelo
        # passa a poder escolher em qual tenant operar -- e uma página web com prompt injection
        # também. O isolamento deixaria de ser estrutural e viraria "torcer pelo bom
        # comportamento do modelo". Este teste falha antes que isso chegue em produção.
        proibidos = {"tenant_id", "conversation_id", "usuario_id", "api_key", "token", "senha"}
        for nome in listar_nomes():
            parametros = set(obter_ferramenta(nome).propriedades)
            vazamento = parametros & proibidos
            self.assertEqual(
                vazamento, set(),
                f"Ferramenta '{nome}' expõe parâmetro sensível ao modelo: {vazamento}"
            )


class TestValidacaoDeArgumentos(unittest.TestCase):

    def test_obrigatorio_ausente_levanta_erro(self):
        with self.assertRaises(ErroValidacaoFerramenta):
            validar_argumentos(_ferramenta_de_teste(), {"quantidade": 3})

    def test_obrigatorio_vazio_levanta_erro(self):
        with self.assertRaises(ErroValidacaoFerramenta):
            validar_argumentos(_ferramenta_de_teste(), {"texto": ""})

    def test_tipo_errado_levanta_erro(self):
        with self.assertRaises(ErroValidacaoFerramenta):
            validar_argumentos(_ferramenta_de_teste(), {"texto": "ok", "quantidade": "não é número"})

    def test_booleano_nao_passa_como_numero(self):
        # bool é subclasse de int em Python: sem tratamento explícito, True passaria por "integer".
        with self.assertRaises(ErroValidacaoFerramenta):
            validar_argumentos(_ferramenta_de_teste(), {"texto": "ok", "quantidade": True})

    def test_argumento_nao_declarado_e_descartado(self):
        limpos = validar_argumentos(
            _ferramenta_de_teste(), {"texto": "ok", "parametro_inventado": "valor perigoso"}
        )
        self.assertEqual(limpos, {"texto": "ok"})
        self.assertNotIn("parametro_inventado", limpos)

    def test_argumentos_nao_dict_levanta_erro(self):
        with self.assertRaises(ErroValidacaoFerramenta):
            validar_argumentos(_ferramenta_de_teste(), "não é um objeto")


class TestExecucaoTolerante(unittest.TestCase):
    """executar_ferramenta nunca propaga exceção -- uma tool quebrada vira texto que o modelo lê."""

    def setUp(self):
        self.ctx = ContextoExecucao(tenant_id="senai_labfashion")

    def test_ferramenta_desconhecida_retorna_erro_sem_excecao(self):
        resultado = executar_ferramenta("nao_existe", {}, self.ctx)
        self.assertTrue(resultado.erro)
        self.assertIn("não existe", resultado.conteudo)

    def test_argumentos_invalidos_retornam_erro_legivel(self):
        resultado = executar_ferramenta("gerar_imagem_croqui", {"prompt_visual": "só isso"}, self.ctx)
        self.assertTrue(resultado.erro)
        self.assertIn("resumo_confirmacao", resultado.conteudo)

    def test_handler_que_levanta_excecao_vira_resultado_de_erro(self):
        def _handler_quebrado(args, ctx):
            raise RuntimeError("banco fora do ar")

        with patch.dict(
            "agente_ferramentas._REGISTRO",
            {"ferramenta_quebrada": _ferramenta_de_teste(handler=_handler_quebrado)},
        ):
            resultado = executar_ferramenta("ferramenta_quebrada", {"texto": "oi"}, self.ctx)

        self.assertTrue(resultado.erro)
        self.assertIn("falhou ao executar", resultado.conteudo)
        # A mensagem técnica original não vaza para o modelo/usuário.
        self.assertNotIn("banco fora do ar", resultado.conteudo)

    def test_resultado_muito_grande_e_truncado_com_aviso(self):
        def _handler_verboso(args, ctx):
            return ResultadoFerramenta(conteudo="x" * (LIMITE_CONTEUDO_FERRAMENTA_CHARS + 5000))

        with patch.dict(
            "agente_ferramentas._REGISTRO",
            {"ferramenta_verbosa": _ferramenta_de_teste(handler=_handler_verboso)},
        ):
            resultado = executar_ferramenta("ferramenta_verbosa", {"texto": "oi"}, self.ctx)

        self.assertLess(len(resultado.conteudo), LIMITE_CONTEUDO_FERRAMENTA_CHARS + 500)
        self.assertIn("truncado", resultado.conteudo)


class TestHandlersDeImagem(unittest.TestCase):
    """Regra crítica: a data URI da imagem (megabytes de base64) nunca pode voltar ao modelo."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.images.generate.return_value = MagicMock(data=[MagicMock(b64_json=FAKE_B64)])
        self.ctx = ContextoExecucao(tenant_id="senai_labfashion", client=self.mock_client)

    def test_croqui_devolve_imagem_em_dados_extras_e_nao_no_conteudo(self):
        resultado = executar_ferramenta(
            "gerar_imagem_croqui",
            {"prompt_visual": "floral midi dress", "resumo_confirmacao": "Um vestido midi floral"},
            self.ctx,
        )
        self.assertFalse(resultado.erro)
        self.assertEqual(resultado.dados_extras["imagem_url"], FAKE_DATA_URI)
        self.assertNotIn("base64", resultado.conteudo)
        self.assertEqual(resultado.conteudo, "Imagem gerada com sucesso.")

    def test_estilo_tecnico_acrescenta_sufixo_ao_prompt(self):
        from geracao_imagem import ESTILO_TECNICO

        ctx_tecnico = ContextoExecucao(
            tenant_id="senai_labfashion", client=self.mock_client, estilo_croqui=ESTILO_TECNICO
        )
        executar_ferramenta(
            "gerar_imagem_croqui",
            {"prompt_visual": "denim jacket", "resumo_confirmacao": "Jaqueta jeans"},
            ctx_tecnico,
        )
        prompt_enviado = self.mock_client.images.generate.call_args.kwargs["prompt"]
        self.assertIn("technical flat sketch", prompt_enviado)
        self.assertIn("front view and back view", prompt_enviado)

    def test_falha_na_geracao_retorna_erro_sem_dados_extras(self):
        self.mock_client.images.generate.side_effect = Exception("content_policy_violation")
        resultado = executar_ferramenta(
            "gerar_imagem_croqui",
            {"prompt_visual": "algo", "resumo_confirmacao": "algo"},
            self.ctx,
        )
        self.assertTrue(resultado.erro)
        self.assertEqual(resultado.dados_extras, {})

    def test_ficha_tecnica_pede_tabela_ao_modelo(self):
        resultado = executar_ferramenta(
            "gerar_ficha_tecnica",
            {"prompt_visual": "denim jacket", "resumo_confirmacao": "Ficha técnica de jaqueta jeans"},
            self.ctx,
        )
        self.assertEqual(resultado.dados_extras["imagem_url"], FAKE_DATA_URI)
        self.assertIn("tabela markdown", resultado.conteudo)


class TestConfirmacaoObrigatoria(unittest.TestCase):
    """Ferramentas caras não podem rodar por decisão isolada do modelo (Etapa 6)."""

    def test_ferramentas_de_imagem_exigem_confirmacao(self):
        self.assertTrue(exige_confirmacao("gerar_imagem_croqui"))
        self.assertTrue(exige_confirmacao("gerar_ficha_tecnica"))

    def test_consulta_interna_nao_exige_confirmacao(self):
        self.assertFalse(exige_confirmacao("consultar_unidades_senai"))
        self.assertFalse(exige_confirmacao("buscar_documentos_internos"))

    def test_ferramenta_inexistente_nao_exige_confirmacao(self):
        self.assertFalse(exige_confirmacao("nao_existe"))


class TestResumoParaLog(unittest.TestCase):

    def test_valor_longo_e_cortado_com_indicacao_de_tamanho(self):
        resumo = resumir_para_log("a" * 500)
        self.assertLess(len(resumo), 300)
        self.assertIn("+300 chars", resumo)

    def test_dict_vira_json_de_uma_linha(self):
        resumo = resumir_para_log({"query": "cores 2027"})
        self.assertIn("cores 2027", resumo)
        self.assertNotIn("\n", resumo)

    def test_conteudo_curto_passa_intacto(self):
        self.assertEqual(truncar_conteudo("resultado pequeno"), "resultado pequeno")


if __name__ == "__main__":
    unittest.main()
