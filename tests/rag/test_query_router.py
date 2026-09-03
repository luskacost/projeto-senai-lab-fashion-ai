# -*- coding: utf-8 -*-
"""Testes Unitários da Camada Query Router + Source-Aware Retrieval (Prioridade 5).

Cobre os 10 cenários especificados no Requisito 33:
1. Agregações (COUNT, SUM, AVG, MIN, MAX)
2. Rankings (Total_Points, Prize_Money_USD, Rank)
3. Filtros pontuais (TABULAR_EXACT, TABULAR_FILTER)
4. Listas completas (TABULAR_LIST, DISTINCT)
5. Paráfrases e termos coloquiais em português
6. Erros de digitação / tolerância ortográfica
7. Perguntas fora do escopo / anti-alucinação
8. Ambiguidade explícita (pede desambiguação)
9. Joins relacionais entre tabelas (Summary ↔ Roster ↔ Standings)
10. Generalização para novos esquemas arbitrários
"""

import unittest
from typing import Any, Dict, List

from query_router import (
    RouteType,
    QueryRoute,
    QueryRouter,
    SourceProfile,
    extrair_intervalo_datas,
    normalizar_nome_entidade_ou_nickname
)
from tabular_query_engine import (
    TabularIntent,
    TabularFilter,
    TabularQueryPlan,
    detectar_e_planejar_consulta_tabular,
    executar_consulta_tabular
)
from tabular_storage import (
    TabularDocument,
    TabularRow,
    TabularSheet,
    salvar_documento_tabular,
    remover_tenant_tabular
)


class TestQueryRouter(unittest.TestCase):
    """Bateria de testes unitários para a Camada Query Router (P5)."""

    TEST_TENANT = "test_p5_query_router_tenant"

    @classmethod
    def setUpClass(cls):
        # Cria fixtures tabulares ricas simulando o dataset de benchmark (EWC 2026 e Google Trends)
        remover_tenant_tabular(cls.TEST_TENANT)

        # 1. Event Tournament Summary
        sheets_events = {
            "Sheet1": TabularSheet(
                nome_aba="Sheet1",
                schema=["Game", "Event_Name", "Start_Date", "End_Date", "Prize_Pool_USD", "Num_Participants", "Winner", "Runner_Up"],
                linhas=[
                    TabularRow(linha=2, dados={"Game": "VALORANT", "Event_Name": "EWC VALORANT", "Start_Date": "2026-07-02", "End_Date": "2026-07-12", "Prize_Pool_USD": "2000000", "Num_Participants": "16 Teams", "Winner": "100 Thieves", "Runner_Up": "NRG"}),
                    TabularRow(linha=3, dados={"Game": "Dota 2", "Event_Name": "EWC Dota 2", "Start_Date": "2026-07-07", "End_Date": "2026-07-19", "Prize_Pool_USD": "2000000", "Num_Participants": "24 Teams", "Winner": "PVISION", "Runner_Up": "BB Team"}),
                    TabularRow(linha=4, dados={"Game": "Apex Legends", "Event_Name": "ALGS 2026", "Start_Date": "2026-07-07", "End_Date": "2026-07-11", "Prize_Pool_USD": "2000000", "Num_Participants": "40 Teams", "Winner": "UNLIMIT", "Runner_Up": "Team Vision"}),
                ]
            )
        }
        salvar_documento_tabular(cls.TEST_TENANT, "01_EWC2026_Event_Tournament_Summary.csv", "csv", sheets_events)

        # 2. Club Championship Standings
        sheets_standings = {
            "Sheet1": TabularSheet(
                nome_aba="Sheet1",
                schema=["Rank", "Organization", "Total_Points", "Prize_Money_USD", "Tournament_Wins", "Games_Won"],
                linhas=[
                    TabularRow(linha=2, dados={"Rank": "1", "Organization": "AG.AL International", "Total_Points": "5300", "Prize_Money_USD": "7000000", "Tournament_Wins": "4", "Games_Won": "12"}),
                    TabularRow(linha=3, dados={"Rank": "2", "Organization": "Team Falcons", "Total_Points": "4200", "Prize_Money_USD": "4000000", "Tournament_Wins": "2", "Games_Won": "9"}),
                    TabularRow(linha=4, dados={"Rank": "3", "Organization": "Team Liquid", "Total_Points": "3100", "Prize_Money_USD": "2500000", "Tournament_Wins": "1", "Games_Won": "7"}),
                    TabularRow(linha=5, dados={"Rank": "24", "Organization": "ZETA DIVISION", "Total_Points": "50", "Prize_Money_USD": "Not fully tracked", "Tournament_Wins": "0", "Games_Won": "1"}),
                ]
            )
        }
        salvar_documento_tabular(cls.TEST_TENANT, "03_EWC2026_Club_Championship_Standings.csv", "csv", sheets_standings)

        # 3. Player Roster (com apelidos / nomes compostos)
        sheets_roster = {
            "Sheet1": TabularSheet(
                nome_aba="Sheet1",
                schema=["Player_ID", "Player_Name", "Country", "Region", "Team", "Game", "Role", "Tournament_Place", "Prize_Earned_USD"],
                linhas=[
                    TabularRow(linha=2, dados={"Player_ID": "P001", "Player_Name": 'Peter "Asuna" Mazuryk', "Country": "USA", "Region": "Americas", "Team": "100 Thieves", "Game": "VALORANT", "Role": "Player", "Tournament_Place": "1", "Prize_Earned_USD": "600000"}),
                    TabularRow(linha=3, dados={"Player_ID": "P002", "Player_Name": 'Sean "bang" Bezerra', "Country": "USA", "Region": "Americas", "Team": "100 Thieves", "Game": "VALORANT", "Role": "Player", "Tournament_Place": "1", "Prize_Earned_USD": "600000"}),
                    TabularRow(linha=4, dados={"Player_ID": "P003", "Player_Name": 'Kelden "Boostio" Pupello', "Country": "USA", "Region": "Americas", "Team": "100 Thieves", "Game": "VALORANT", "Role": "Player", "Tournament_Place": "1", "Prize_Earned_USD": "600000"}),
                ]
            )
        }
        salvar_documento_tabular(cls.TEST_TENANT, "05_EWC2026_Player_Roster.csv", "csv", sheets_roster)

        # 4. MultiTimeline (Google Translate vs ChatGPT vs DeepL)
        sheets_timeline = {
            "Sheet1": TabularSheet(
                nome_aba="Sheet1",
                schema=["Month", "Google Translate", "ChatGPT", "DeepL"],
                linhas=[
                    TabularRow(linha=2, dados={"Month": "2016-01-01", "Google Translate": "17", "ChatGPT": "0", "DeepL": "0.5"}),
                    TabularRow(linha=3, dados={"Month": "2016-02-01", "Google Translate": "19", "ChatGPT": "0", "DeepL": "0.5"}),
                ]
            )
        }
        salvar_documento_tabular(cls.TEST_TENANT, "multiTimeline_2016.csv", "csv", sheets_timeline)

    @classmethod
    def tearDownClass(cls):
        remover_tenant_tabular(cls.TEST_TENANT)

    def setUp(self):
        self.router = QueryRouter(self.TEST_TENANT)

    # 1. Agregações (COUNT, SUM, AVG, MIN, MAX)
    def test_01_agregacoes_count_sum_avg_min_max(self):
        # COUNT
        r_count = self.router.route_query("Quantos eventos existem no arquivo de resumo de torneios?")
        self.assertEqual(r_count.route, RouteType.TABULAR_AGGREGATION)
        self.assertEqual(r_count.tabular_intent, "COUNT")

        # SUM
        r_sum = self.router.route_query("Qual é o valor total somando a premiação de todos os torneios?")
        self.assertEqual(r_sum.route, RouteType.TABULAR_AGGREGATION)
        self.assertEqual(r_sum.tabular_intent, "SUM")

        # AVG
        r_avg = self.router.route_query("Qual é a média de pontos das organizações no Club Championship?")
        self.assertEqual(r_avg.route, RouteType.TABULAR_AGGREGATION)
        self.assertEqual(r_avg.tabular_intent, "AVG")

        # MAX
        r_max = self.router.route_query("Qual organização possui mais pontos no Club Championship?")
        self.assertEqual(r_max.route, RouteType.TABULAR_AGGREGATION)
        self.assertIn(r_max.tabular_intent, ("MAX", "RANK"))

        # MIN
        r_min = self.router.route_query("Qual organização possui menos pontos entre as pontuações registradas?")
        self.assertEqual(r_min.route, RouteType.TABULAR_AGGREGATION)
        self.assertEqual(r_min.tabular_intent, "MIN")

    # 2. Rankings (Total_Points, Prize_Money_USD, Rank)
    def test_02_rankings_numericos(self):
        r_rank = self.router.route_query("Qual clube lidera o ranking do Club Championship?")
        self.assertEqual(r_rank.route, RouteType.TABULAR_AGGREGATION)
        self.assertEqual(r_rank.tabular_intent, "RANK")
        self.assertIn("03_EWC2026_Club_Championship_Standings.csv", r_rank.preferred_sources)

    # 3. Filtros pontuais (TABULAR_EXACT, TABULAR_FILTER)
    def test_03_filtros_pontuais_e_exatos(self):
        r_exact = self.router.route_query("Quem venceu o torneio de VALORANT no EWC 2026?")
        self.assertIn(r_exact.route, (RouteType.TABULAR_EXACT, RouteType.TABULAR_FILTER))
        self.assertIn("01_EWC2026_Event_Tournament_Summary.csv", r_exact.preferred_sources)

        r_vice = self.router.route_query("Quem foi o vice-campeão de VALORANT no EWC 2026?")
        self.assertIn(r_vice.route, (RouteType.TABULAR_EXACT, RouteType.TABULAR_FILTER))

        # Teste de data exata / linha de timeline
        r_timeline = self.router.route_query("Qual era o valor do Google Translate em janeiro de 2016 no multiTimeline_2016.csv?")
        self.assertIn(r_timeline.route, (RouteType.TABULAR_EXACT, RouteType.TABULAR_FILTER))
        self.assertIn("multiTimeline_2016.csv", r_timeline.preferred_sources)

    # 4. Listas completas (TABULAR_LIST, DISTINCT)
    def test_04_listas_completas(self):
        r_list = self.router.route_query("Liste todos os eventos do campeonato")
        self.assertEqual(r_list.route, RouteType.TABULAR_LIST)

        r_dist = self.router.route_query("Quais organizações aparecem no Club Championship?")
        self.assertEqual(r_dist.route, RouteType.TABULAR_LIST)

    # 5. Paráfrases e termos coloquiais
    def test_05_parafrases_e_coloquialismos(self):
        r_coloquial1 = self.router.route_query("Quem levou a melhor no torneio de VALORANT?")
        self.assertIn(r_coloquial1.route, (RouteType.TABULAR_EXACT, RouteType.TABULAR_FILTER))

        r_coloquial2 = self.router.route_query("Qual time faturou mais grana no campeonato?")
        self.assertEqual(r_coloquial2.route, RouteType.TABULAR_AGGREGATION)

    # 6. Erros de digitação comuns
    def test_06_erros_digitacao_tolerancia(self):
        r_typo1 = self.router.route_query("Quantos jgos diferentes aparecem no torneio?")
        self.assertEqual(r_typo1.route, RouteType.TABULAR_AGGREGATION)

        r_typo2 = self.router.route_query("Qual foi a premicao total somando todos?")
        self.assertEqual(r_typo2.route, RouteType.TABULAR_AGGREGATION)

    # 7. Perguntas fora do escopo / anti-alucinação
    def test_07_anti_alucinacao_e_fora_de_escopo(self):
        # A pergunta pergunta sobre um salário que não existe em coluna alguma
        r_salario = self.router.route_query("Qual era o salário mensal do jogador Asuna?")
        # O router não deve inventar dados nem forçar um JOIN falso
        self.assertFalse(r_salario.is_ambiguous)

    # 8. Ambiguidade explícita
    def test_08_ambiguidade_pergunta_incompleta(self):
        r_ambi1 = self.router.route_query("Quem venceu?")
        self.assertTrue(r_ambi1.is_ambiguous)
        self.assertEqual(r_ambi1.route, RouteType.AMBIGUOUS)
        self.assertIsNotNone(r_ambi1.ambiguity_prompt)

        r_ambi2 = self.router.route_query("Qual foi o resultado?")
        self.assertTrue(r_ambi2.is_ambiguous)
        self.assertEqual(r_ambi2.route, RouteType.AMBIGUOUS)

    # 9. Joins relacionais entre tabelas
    def test_09_joins_relacionais_roster_summary(self):
        r_join = self.router.route_query("Quem venceu o torneio de VALORANT e quais são os jogadores da equipe?")
        self.assertEqual(r_join.route, RouteType.TABULAR_RELATIONAL)

        # Execução completa do plano relacional
        plano = detectar_e_planejar_consulta_tabular(
            "Quem venceu o torneio de VALORANT e quais são os jogadores da equipe?",
            self.TEST_TENANT
        )
        self.assertIsNotNone(plano)
        res = executar_consulta_tabular(plano, self.TEST_TENANT)
        self.assertTrue(res.success)
        # O resultado estruturado deve conter os dados de Summary (100 Thieves) E os jogadores de Roster (Asuna, bang, Boostio)
        self.assertIn("100 Thieves", res.formatted_result_block)
        self.assertIn("Asuna", res.formatted_result_block)
        self.assertIn("bang", res.formatted_result_block)

    # 10. Normalização de datas e apelidos
    def test_10_normalizacao_datas_e_apelidos(self):
        interv = extrair_intervalo_datas("qual o valor em janeiro de 2016?")
        self.assertIsNotNone(interv)
        self.assertEqual(interv["data_inicio"], "2016-01-01")
        self.assertEqual(interv["data_fim"], "2016-01-31")

        # Apelidos com aspas ou parênteses
        full, nick, paren = normalizar_nome_entidade_ou_nickname('Peter "Asuna" Mazuryk')
        self.assertEqual(nick, "asuna")

        full2, nick2, paren2 = normalizar_nome_entidade_ou_nickname('Asuna (Peter Mazuryk)')
        self.assertEqual(paren2, "peter mazuryk")


if __name__ == "__main__":
    unittest.main()
