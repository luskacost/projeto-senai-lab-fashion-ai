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


class TestResolverColunasDeAgrupamento(unittest.TestCase):
    """Função pura -- decide qual das duas colunas citadas na pergunta é o grupo e qual é o
    valor listado dentro de cada grupo, pela cardinalidade (menos valores distintos = grupo)."""

    def setUp(self):
        self.sheet = _sheet(
            ["Fabricante", "Referencia", "Peso unitario"],
            [
                {"Fabricante": "Casa", "Referencia": "AV-01", "Peso unitario": "2.5"},
                {"Fabricante": "Casa", "Referencia": "AV-03", "Peso unitario": "1.2"},
                {"Fabricante": "Zip", "Referencia": "AV-02", "Peso unitario": "8.0"},
            ],
        )

    def test_coluna_de_menor_cardinalidade_vira_o_grupo(self):
        # Fabricante tem 2 valores distintos, Referencia tem 3 -- Fabricante agrupa.
        colunas = tqe._resolver_colunas_de_agrupamento("cada fabricante e suas referencias", self.sheet)
        self.assertEqual(colunas, ("Fabricante", "Referencia"))

    def test_ordem_das_palavras_na_pergunta_nao_importa(self):
        colunas = tqe._resolver_colunas_de_agrupamento("cada referencia do respectivo fabricante", self.sheet)
        self.assertEqual(colunas, ("Fabricante", "Referencia"))

    def test_uma_coluna_so_citada_nao_resolve(self):
        colunas = tqe._resolver_colunas_de_agrupamento("cada fabricante do estoque", self.sheet)
        self.assertIsNone(colunas)

    def test_coluna_numerica_nao_participa(self):
        # "Peso unitario" é citada, mas não pode virar coluna de listagem agrupada (numérica).
        colunas = tqe._resolver_colunas_de_agrupamento("cada fabricante e seu peso unitario", self.sheet)
        self.assertIsNone(colunas)

    def test_mencao_parcial_nao_conta(self):
        # "fabricante" sozinho, sem citar "referencia" pelo nome inteiro.
        colunas = tqe._resolver_colunas_de_agrupamento("cada fabricante e seus produtos", self.sheet)
        self.assertIsNone(colunas)


class _ComPlanilhaIndexada(unittest.TestCase):

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


class TestPlanosComPlanilhaReal(_ComPlanilhaIndexada):

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


class TestFiltrosPorValor(unittest.TestCase):
    """Função pura: a condição de uma listagem vem de valores que existem nas células."""

    def setUp(self):
        self.sheet = _sheet(
            ["Fornecedor", "Descricao", "Peso"],
            [
                {"Fornecedor": "Fornecedor Alfa", "Descricao": "peca azul lisa", "Peso": "1"},
                {"Fornecedor": "Loja Beta", "Descricao": "peca verde listrada", "Peso": "2"},
                {"Fornecedor": "Loja Beta", "Descricao": "peca azul listrada", "Peso": "3"},
            ],
        )

    def _filtros(self, pergunta):
        return [(f.column, f.value) for f in tqe._resolver_filtros_por_valor(pergunta, self.sheet)]

    def test_valor_inteiro_da_celula_citado_na_pergunta(self):
        self.assertEqual(self._filtros("quais pecas da Loja Beta?"), [("Fornecedor", "Loja Beta")])

    def test_palavra_presente_em_parte_das_celulas(self):
        self.assertEqual(self._filtros("quais pecas sao verde?"), [("Descricao", "verde")])

    def test_palavra_presente_em_todas_as_celulas_nao_filtra(self):
        # "peca" está nas três descrições: é vocabulário da tabela, não condição.
        self.assertEqual(self._filtros("quais peca existem?"), [])

    def test_nome_de_coluna_nao_vira_valor(self):
        # "fornecedor" aparece dentro de "Fornecedor Alfa", mas aqui nomeia a coluna.
        self.assertEqual(self._filtros("quais pecas tem fornecedor?"), [])

    def test_coluna_numerica_ignorada(self):
        self.assertEqual(self._filtros("quais pecas pesam 2?"), [])


class TestListagens(_ComPlanilhaIndexada):
    """Antes: "liste X com condição Y" virava DISTINCT de uma coluna da tabela inteira, rotulado
    como resultado calculado -- a condição era simplesmente ignorada."""

    def test_listagem_por_valor_inteiro(self):
        plano, res = self._executar("Liste os aviamentos do fabricante Zipers Brasil")
        self.assertEqual(plano.intent, tqe.TabularIntent.FILTER)
        self.assertEqual(sorted(r["Referencia"] for r in res.records), ["AV-02", "AV-05"])

    def test_listagem_por_palavra_que_o_roteador_manda_para_o_vetor(self):
        plano, res = self._executar("Quais aviamentos sao de cobre?")
        self.assertEqual(plano.intent, tqe.TabularIntent.FILTER)
        self.assertEqual([r["Referencia"] for r in res.records], ["AV-04"])

    def test_listagem_da_coluna_citada(self):
        plano, res = self._executar("Quais os fabricantes do estoque?")
        self.assertEqual(plano.intent, tqe.TabularIntent.DISTINCT)
        self.assertEqual(sorted(res.value), ["Casa dos Botoes", "Metais Sul", "Zipers Brasil"])

    def test_coluna_citada_com_condicao_nao_resolvida_nao_lista_a_coluna_inteira(self):
        # "fabricantes" resolve a coluna, mas "certificacao" é uma condição que a planilha não
        # tem -- listar os 3 fabricantes afirmaria que todos são certificados.
        plano = tqe.detectar_e_planejar_consulta_tabular(
            "Quais os fabricantes com certificacao ambiental?", TENANT_TESTE
        )
        self.assertIsNone(plano)

    def test_condicao_inexistente_nao_lista_a_tabela(self):
        plano = tqe.detectar_e_planejar_consulta_tabular(
            "Liste os aviamentos com garantia vitalicia", TENANT_TESTE
        )
        self.assertIsNone(plano)


class TestListagemAgrupada(_ComPlanilhaIndexada):
    """"Liste cada fabricante e suas respectivas referências" -- achado em produção (não no
    golden set original): a pergunta cita DUAS colunas reais junto de um marcador de grupo
    ("cada", "respectivas"). Antes desta correção, o plano de listagem tentava resolver 1 coluna
    só, sobrava a outra como "condição sem resolução" e a pergunta inteira caía na busca vetorial
    -- que devolve uma amostra arbitrária de poucas linhas (não todos os grupos) apresentada como
    se fosse a lista completa. No caso real que motivou isto (produção, tenant
    `senai_labfashion`), "liste cada consultor e suas respectivas empresas" respondia só 2 dos 6
    consultores, com listas de empresas incompletas e inconsistentes entre uma pergunta e outra
    na mesma conversa.
    """

    def test_marcador_cada_agrupa_pela_coluna_de_menor_cardinalidade(self):
        plano, res = self._executar("Liste cada fabricante e suas respectivas referencias")
        self.assertEqual(plano.intent, tqe.TabularIntent.GROUP_LIST)
        self.assertEqual(plano.group_by_columns, ["Fabricante"])
        self.assertEqual(plano.target_columns, ["Referencia"])
        grupos = {g["grupo"]: g["itens"] for g in res.value}
        self.assertEqual(grupos["Casa dos Botoes"], ["AV-01", "AV-03"])
        self.assertEqual(grupos["Zipers Brasil"], ["AV-02", "AV-05"])
        self.assertEqual(grupos["Metais Sul"], ["AV-04"])

    def test_marcador_respectivas_sem_a_palavra_cada(self):
        plano, res = self._executar("Mostre os fabricantes e suas respectivas referencias")
        self.assertEqual(plano.intent, tqe.TabularIntent.GROUP_LIST)
        self.assertEqual(len(res.value), 3)  # os 3 fabricantes, nenhum de fora

    def test_todos_os_grupos_aparecem_nao_so_uma_amostra(self):
        # O defeito original: a busca vetorial via só 2-3 grupos de 6 (top_k pequeno). Aqui é
        # cálculo determinístico sobre a planilha inteira -- todo grupo com pelo menos uma linha
        # tem que aparecer.
        _plano, res = self._executar("Liste cada fabricante e suas respectivas referencias")
        self.assertEqual({g["grupo"] for g in res.value}, {"Casa dos Botoes", "Zipers Brasil", "Metais Sul"})

    def test_sem_marcador_de_grupo_nao_vira_group_list(self):
        # As duas colunas aparecem juntas, mas sem "cada"/"respectivas" -- continua sendo o
        # comportamento antigo (aqui, filtro por valor, não listagem agrupada).
        plano, _res = self._executar("Liste os aviamentos do fabricante Zipers Brasil")
        self.assertNotEqual(plano.intent, tqe.TabularIntent.GROUP_LIST)

    def test_uma_coluna_so_citada_nao_vira_group_list(self):
        # "cada" presente, mas só uma coluna resolvida (fabricante) -- sem uma segunda coluna
        # citada pelo nome inteiro, não há como saber o que listar dentro de cada grupo. "cada"
        # em si não é uma condição reconhecida, então o plano é descartado (nunca chuta).
        plano = tqe.detectar_e_planejar_consulta_tabular("Liste cada fabricante do estoque", TENANT_TESTE)
        self.assertTrue(plano is None or plano.intent != tqe.TabularIntent.GROUP_LIST)


class TestExecutorRecusaOperacaoNumericaSemColuna(unittest.TestCase):
    """Defesa em profundidade: mesmo um plano montado à mão com coluna errada não pode produzir
    um número inventado com success=True."""

    @classmethod
    def setUpClass(cls):
        _ComPlanilhaIndexada.setUpClass()

    @classmethod
    def tearDownClass(cls):
        _ComPlanilhaIndexada.tearDownClass()

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
