# -*- coding: utf-8 -*-
"""Testes da resolução de coluna pelo schema real no motor tabular (Fase 13, Bloco F3).

## O defeito que estes testes existem para pegar

O roteador propunha o termo de coluna a partir de um vocabulário fixo de um benchmark antigo
("pontos", "premiacao") ou, num filtro numérico, da palavra logo após o número ("reais" em "menos
de 15 reais por metro"). Quando o termo não casava com nenhuma coluna real, o plano seguia sem
coluna e o executor devolvia, com success=True e rotulado como "Resultado Calculado
Deterministicamente":

- média 0,00 "baseado em 0 registros" (coluna inexistente "valor");
- a tabela inteira como resultado de um filtro (o filtro não resolvido era simplesmente
  descartado);
- contagem de linhas como resposta a "quantos fornecedores diferentes".

Fixture própria, com nomes de coluna diferentes do golden set, para os testes não passarem só
por coincidência com aquele corpus.
"""

import io
import os
import shutil
import unittest

import document_extractors
import rag_manager as rm
import tabular_query_engine as tqe
from tabular_storage import TabularRow, TabularSheet

TENANT_TESTE = "teste_fase13_tabular_resolucao"
NOME_PLANILHA = "estoque_aviamentos.csv"

_CSV = (
    "Referencia,Descricao,Fabricante,Peso unitario,Custo unitario,Quantidade em estoque\n"
    "AV-01,Botao de madreperola,Casa dos Botoes,2.5,0.80,1200\n"
    "AV-02,Ziper metalico,Zipers Brasil,8.0,3.40,300\n"
    "AV-03,Elastico chato,Casa dos Botoes,1.2,0.35,5000\n"
    "AV-04,Rebite de cobre,Metais Sul,3.1,0.95,800\n"
    "AV-05,Velcro adesivo,Zipers Brasil,4.0,2.10,450\n"
)


def _sheet(schema, linhas):
    return TabularSheet(
        nome_aba="Tabela", schema=schema,
        linhas=[TabularRow(linha=i + 2, dados=d) for i, d in enumerate(linhas)],
    )


class TestResolverColunaPelaPergunta(unittest.TestCase):
    """Função pura -- sem indexar nada."""

    def setUp(self):
        self.sheet = _sheet(
            ["Referencia", "Fabricante", "Peso unitario", "Custo unitario"],
            [
                {"Referencia": "AV-01", "Fabricante": "Casa", "Peso unitario": "2.5", "Custo unitario": "0.80"},
                {"Referencia": "AV-02", "Fabricante": "Zip", "Peso unitario": "8.0", "Custo unitario": "3.40"},
            ],
        )

    def test_coluna_citada_pelo_nome(self):
        coluna, score = tqe._resolver_coluna_pela_pergunta("qual o peso unitario medio?", self.sheet)
        self.assertEqual(coluna, "Peso unitario")
        self.assertGreaterEqual(score, 1.0)

    def test_plural_casa_por_prefixo(self):
        coluna, _ = tqe._resolver_coluna_pela_pergunta("quantos fabricantes existem?", self.sheet)
        self.assertEqual(coluna, "Fabricante")

    def test_conceito_monetario_resolve_coluna_de_custo(self):
        # A pergunta não cita "custo unitario" -- só "mais caro". O conceito genérico de dinheiro
        # é que liga as duas.
        coluna, _ = tqe._resolver_coluna_pela_pergunta("qual o aviamento mais caro?", self.sheet, somente_numericas=True)
        self.assertEqual(coluna, "Custo unitario")

    def test_mencao_explicita_vence_o_conceito_monetario(self):
        coluna, _ = tqe._resolver_coluna_pela_pergunta("qual o valor do peso unitario?", self.sheet, somente_numericas=True)
        self.assertEqual(coluna, "Peso unitario")

    def test_somente_numericas_ignora_colunas_de_texto(self):
        coluna, _ = tqe._resolver_coluna_pela_pergunta("qual o maior fabricante?", self.sheet, somente_numericas=True)
        self.assertIsNone(coluna)

    def test_pergunta_sem_relacao_com_o_schema(self):
        coluna, score = tqe._resolver_coluna_pela_pergunta("como costurar seda?", self.sheet)
        self.assertIsNone(coluna)
        self.assertEqual(score, 0.0)

    def test_token_curto_nao_casa_por_prefixo(self):
        # "cor" (3 letras) não pode casar com "corte" -- abaixo do tamanho mínimo, só exato.
        self.assertFalse(tqe._tokens_casam("corte", "cor"))
        self.assertTrue(tqe._tokens_casam("cor", "cor"))


class TestPlanosComPlanilhaReal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._limpar()
        unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(
            io.BytesIO(_CSV.encode("utf-8")), NOME_PLANILHA
        )
        rm.indexar_documento(TENANT_TESTE, NOME_PLANILHA, unidades, dados_tabulares=sheets)

    @classmethod
    def tearDownClass(cls):
        rm.remover_documento(TENANT_TESTE, NOME_PLANILHA)
        cls._limpar()

    @classmethod
    def _limpar(cls):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)

    def _executar(self, pergunta):
        plano = tqe.detectar_e_planejar_consulta_tabular(pergunta, TENANT_TESTE)
        self.assertIsNotNone(plano, f"Nenhum plano para: {pergunta}")
        return plano, tqe.executar_consulta_tabular(plano, TENANT_TESTE)

    def test_media_usa_a_coluna_citada(self):
        plano, res = self._executar("Qual o peso unitario medio dos aviamentos?")
        self.assertEqual(plano.intent, tqe.TabularIntent.AVG)
        self.assertEqual(plano.target_columns, ["Peso unitario"])
        # (2.5 + 8.0 + 1.2 + 3.1 + 4.0) / 5 = 3.76
        self.assertTrue(res.success)
        self.assertAlmostEqual(res.value, 3.76)

    def test_soma_pelo_padrao_legado_com_coluna_da_pergunta(self):
        # "qual a soma" casa com um padrão legado que assume a coluna "valor" -- inexistente aqui.
        plano, res = self._executar("Qual a soma do custo unitario de todos os aviamentos?")
        self.assertEqual(plano.intent, tqe.TabularIntent.SUM)
        self.assertEqual(plano.target_columns, ["Custo unitario"])
        # 0.80 + 3.40 + 0.35 + 0.95 + 2.10 = 7.60
        self.assertAlmostEqual(res.value, 7.60)
        # A confiança precisa passar o limiar de execução do rag_manager (0,20).
        self.assertGreaterEqual(plano.confidence, 0.20)

    def test_filtro_com_coluna_antes_do_comparador(self):
        plano, res = self._executar("Quais aviamentos tem peso unitario acima de 3?")
        self.assertEqual([(f.column, f.operator) for f in plano.filters], [("Peso unitario", ">")])
        self.assertEqual(res.rows_matched, 3)  # AV-02 (8.0), AV-04 (3.1), AV-05 (4.0)

    def test_filtro_com_unidade_depois_do_numero(self):
        # O termo logo após o número é "reais" -- não é coluna nenhuma.
        plano, res = self._executar("Quais aviamentos custam menos de 1 real por unidade?")
        self.assertEqual([f.column for f in plano.filters], ["Custo unitario"])
        self.assertEqual(res.rows_matched, 3)  # AV-01 (0.80), AV-03 (0.35), AV-04 (0.95)

    def test_filtro_irresolvivel_nao_devolve_a_tabela_inteira(self):
        # Nenhuma coluna numérica é citada nem monetária -- o filtro não tem onde ser aplicado.
        # Antes: plano FILTER sem filtros, 5 de 5 linhas "encontradas".
        plano = tqe.detectar_e_planejar_consulta_tabular(
            "Quais aviamentos tem mais de 3 anos de garantia?", TENANT_TESTE
        )
        if plano is not None:
            res = tqe.executar_consulta_tabular(plano, TENANT_TESTE)
            self.assertFalse(
                plano.intent == tqe.TabularIntent.FILTER and not plano.filters,
                "Plano FILTER sem nenhum filtro -- devolveria a tabela inteira como filtrada.",
            )
            self.assertLess(res.rows_matched, 5)

    def test_quantos_diferentes_vira_distinct(self):
        plano, res = self._executar("Quantos fabricantes diferentes existem no estoque?")
        self.assertEqual(plano.intent, tqe.TabularIntent.DISTINCT)
        self.assertEqual(plano.target_columns, ["Fabricante"])
        self.assertEqual(sorted(res.value), ["Casa dos Botoes", "Metais Sul", "Zipers Brasil"])

    def test_superlativo_monetario_vira_max(self):
        plano, res = self._executar("Qual o aviamento mais caro do estoque?")
        self.assertEqual(plano.intent, tqe.TabularIntent.MAX)
        self.assertEqual(res.value["registro"]["Referencia"], "AV-02")

    def test_superlativo_monetario_vira_min(self):
        plano, res = self._executar("Qual o aviamento mais barato do estoque?")
        self.assertEqual(plano.intent, tqe.TabularIntent.MIN)
        self.assertEqual(res.value["registro"]["Referencia"], "AV-03")

    def test_superlativo_sem_coluna_citada_nao_sequestra_a_pergunta(self):
        # "maior" sem nenhuma coluna citada pelo nome não pode virar MAX sobre qualquer coluna.
        plano = tqe.detectar_e_planejar_consulta_tabular(
            "Qual a maior dificuldade ao pregar botoes em tecido fino?", TENANT_TESTE
        )
        self.assertIsNone(plano)


class TestExecutorRecusaOperacaoNumericaSemColuna(unittest.TestCase):
    """Defesa em profundidade: mesmo um plano montado à mão com coluna errada não pode produzir
    um número inventado com success=True."""

    @classmethod
    def setUpClass(cls):
        TestPlanosComPlanilhaReal.setUpClass()

    @classmethod
    def tearDownClass(cls):
        TestPlanosComPlanilhaReal.tearDownClass()

    def _plano(self, intent, colunas):
        return tqe.TabularQueryPlan(
            intent=intent, target_document=NOME_PLANILHA, target_sheet="Tabela",
            target_columns=colunas, original_query="pergunta",
        )

    def test_coluna_inexistente_falha(self):
        for intent in (tqe.TabularIntent.SUM, tqe.TabularIntent.AVG, tqe.TabularIntent.MAX, tqe.TabularIntent.MIN):
            with self.subTest(intent=intent):
                res = tqe.executar_consulta_tabular(self._plano(intent, ["coluna_que_nao_existe"]), TENANT_TESTE)
                self.assertFalse(res.success)
                self.assertEqual(res.formatted_result_block, "")

    def test_sem_coluna_e_sem_valor_no_schema_falha(self):
        # O fallback antigo usava a coluna "valor" -- que esta planilha não tem.
        res = tqe.executar_consulta_tabular(self._plano(tqe.TabularIntent.AVG, []), TENANT_TESTE)
        self.assertFalse(res.success)

    def test_coluna_de_texto_falha(self):
        res = tqe.executar_consulta_tabular(self._plano(tqe.TabularIntent.SUM, ["Fabricante"]), TENANT_TESTE)
        self.assertFalse(res.success)

    def test_coluna_numerica_valida_continua_funcionando(self):
        res = tqe.executar_consulta_tabular(self._plano(tqe.TabularIntent.MAX, ["Quantidade em estoque"]), TENANT_TESTE)
        self.assertTrue(res.success)
        self.assertEqual(res.value["registro"]["Referencia"], "AV-03")


if __name__ == "__main__":
    unittest.main()
