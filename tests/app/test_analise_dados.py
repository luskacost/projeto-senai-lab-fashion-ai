# -*- coding: utf-8 -*-
"""Testes automatizados para o módulo de Análise de Dados e configurações do Senai LabFashion IA."""

import io
import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from analise_dados import carregar_planilha, gerar_resumo_estatistico, responder_pergunta_sobre_dados
from tenant_config import TENANT_CONFIG, PERFIS_USUARIO


class TestAnaliseDados(unittest.TestCase):

    def setUp(self):
        # Cria DataFrame de teste com colunas numéricas, categóricas, datas e nulos
        self.df_teste = pd.DataFrame({
            "id_venda": [1, 2, 3, 4, 5, 6],
            "produto": ["Vestido Midi", "Camisa Linho", "Vestido Midi", "Calça Alfaiataria", "Vestido Midi", "Camisa Linho"],
            "categoria": ["Feminino", "Masculino", "Feminino", "Unissex", "Feminino", "Masculino"],
            "quantidade": [10, 5, 8, 12, 15, 7],
            "valor_unitario": [180.0, 150.0, 180.0, 220.0, 180.0, 150.0],
            "valor_total": [1800.0, 750.0, 1440.0, 2640.0, 2700.0, 1050.0],
            "data_venda": ["2026-01-10", "2026-01-15", "2026-01-20", "2026-02-01", "2026-02-10", "2026-02-15"],
            "observacao": ["OK", "Promoção", None, "OK", "OK", None]
        })

    def test_tenant_config_analise_dados(self):
        """Valida que o modo 'Análise de Dados' está devidamente configurado no tenant_config."""
        tenant = TENANT_CONFIG["senai_labfashion"]
        modos = tenant["modos"]
        
        self.assertIn("Análise de Dados", modos)
        modo_cfg = modos["Análise de Dados"]
        self.assertIsNone(modo_cfg["tools"])
        self.assertEqual(modo_cfg["validade_cache_horas"], 0)
        self.assertIn("resumo", modo_cfg["prompt"].lower())
        
        # Modo padrão para dono_responsavel
        self.assertEqual(tenant["modo_padrao_por_perfil"]["dono_responsavel"], "Análise de Dados")
        
        # Descrições
        self.assertIn("Análise de Dados", tenant["descricoes_modos"])
        self.assertIn("Análise de Dados", tenant["descricoes_detalhadas"])
        self.assertIn("Análise de Dados", tenant["perguntas_rapidas"])

    def test_carregar_planilha_csv(self):
        """Testa o carregamento de CSV em memória."""
        csv_buffer = io.BytesIO()
        self.df_teste.to_csv(csv_buffer, index=False, sep=";")
        csv_buffer.name = "vendas_teste.csv"
        csv_buffer.seek(0)

        df_carregado = carregar_planilha(csv_buffer)
        self.assertIsNotNone(df_carregado)
        self.assertEqual(len(df_carregado), 6)
        self.assertEqual(len(df_carregado.columns), 8)
        self.assertIn("produto", df_carregado.columns)

    def test_carregar_planilha_excel(self):
        """Testa o carregamento de arquivo Excel .xlsx em memória."""
        excel_buffer = io.BytesIO()
        self.df_teste.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_buffer.name = "estoque_teste.xlsx"
        excel_buffer.seek(0)

        df_carregado = carregar_planilha(excel_buffer)
        self.assertIsNotNone(df_carregado)
        self.assertEqual(len(df_carregado), 6)
        self.assertEqual(len(df_carregado.columns), 8)

    def test_carregar_planilha_corrompida_ou_invalida(self):
        """Testa comportamento resiliente com arquivo corrompido."""
        buffer_corrompido = io.BytesIO(b"conteudo_invalido_nao_csv_ou_excel\x00\x01\x02")
        buffer_corrompido.name = "corrompido.xlsx"
        
        df_carregado = carregar_planilha(buffer_corrompido)
        self.assertIsNone(df_carregado)

        # Arquivo None
        self.assertIsNone(carregar_planilha(None))

    def test_gerar_resumo_estatistico_com_agregacoes(self):
        """Testa se o resumo estatístico contém todas as chaves e agregações numéricas por grupo."""
        resumo = gerar_resumo_estatistico(self.df_teste)
        
        self.assertIn("metadados", resumo)
        self.assertEqual(resumo["metadados"]["total_linhas"], 6)
        self.assertEqual(resumo["metadados"]["total_colunas"], 8)
        
        # Colunas e tipos
        self.assertIn("colunas_e_tipos", resumo)
        self.assertIn("quantidade", resumo["colunas_e_tipos"])
        
        # Estatísticas numéricas
        self.assertIn("estatisticas_numericas", resumo)
        self.assertIn("quantidade", resumo["estatisticas_numericas"])
        stats_qtd = resumo["estatisticas_numericas"]["quantidade"]
        self.assertEqual(stats_qtd["count"], 6)
        self.assertEqual(stats_qtd["min"], 5.0)
        self.assertEqual(stats_qtd["max"], 15.0)
        
        # Totais de soma
        self.assertIn("totais_somas_numericas", resumo)
        self.assertEqual(resumo["totais_somas_numericas"]["quantidade"], 57.0)
        self.assertEqual(resumo["totais_somas_numericas"]["valor_total"], 10380.0)
        
        # Frequências categóricas
        self.assertIn("top_5_frequencias_categoricas", resumo)
        self.assertIn("produto", resumo["top_5_frequencias_categoricas"])
        self.assertEqual(resumo["top_5_frequencias_categoricas"]["produto"]["Vestido Midi"], 3)
        self.assertEqual(resumo["top_5_frequencias_categoricas"]["produto"]["Camisa Linho"], 2)
        
        # Agregações automáticas por grupo
        self.assertIn("agregacoes", resumo)
        agregacoes = resumo["agregacoes"]
        self.assertIn("produto", agregacoes)
        self.assertIn("quantidade", agregacoes["produto"])
        
        # Validação do Top 10 e Bottom 10 por quantidade
        top_qtd_produto = agregacoes["produto"]["quantidade"]["top_10"]
        # Vestido Midi: 10 + 8 + 15 = 33
        # Calça Alfaiataria: 12
        # Camisa Linho: 5 + 7 = 12
        self.assertEqual(top_qtd_produto["Vestido Midi"], 33.0)
        self.assertEqual(agregacoes["produto"]["quantidade"]["total_geral"], 57.0)

        # Validação de Faturamento / Valor Total por produto
        self.assertIn("valor_total", agregacoes["produto"])
        top_fat_produto = agregacoes["produto"]["valor_total"]["top_10"]
        # Vestido Midi: 1800 + 1440 + 2700 = 5940.0
        # Calça Alfaiataria: 2640.0
        # Camisa Linho: 750 + 1050 = 1800.0
        self.assertEqual(top_fat_produto["Vestido Midi"], 5940.0)
        self.assertEqual(top_fat_produto["Calça Alfaiataria"], 2640.0)
        self.assertEqual(top_fat_produto["Camisa Linho"], 1800.0)
        
        bottom_fat_produto = agregacoes["produto"]["valor_total"]["bottom_10"]
        self.assertEqual(list(bottom_fat_produto.keys())[0], "Camisa Linho")

        # Transparência da heurística de seleção (Fase 7, Task 5): as colunas usadas em
        # "agregacoes" devem ser expostas para o front-end mostrar o que foi analisado.
        self.assertIn("colunas_selecionadas_para_analise", resumo)
        self.assertIn("produto", resumo["colunas_selecionadas_para_analise"]["agrupamento"])
        self.assertIn("quantidade", resumo["colunas_selecionadas_para_analise"]["metricas"])
        self.assertIn("valor_total", resumo["colunas_selecionadas_para_analise"]["metricas"])

        # Datas
        self.assertIn("colunas_data", resumo)
        self.assertIn("data_venda", resumo["colunas_data"])
        self.assertEqual(resumo["colunas_data"]["data_venda"]["data_minima"], "2026-01-10")
        self.assertEqual(resumo["colunas_data"]["data_venda"]["data_maxima"], "2026-02-15")

        # Nulos
        self.assertIn("valores_ausentes", resumo)
        self.assertIn("observacao", resumo["valores_ausentes"])
        self.assertEqual(resumo["valores_ausentes"]["observacao"]["quantidade_nulos"], 2)

    def test_gerar_resumo_sem_colunas_agrupamento(self):
        """Testa DataFrame composto apenas por colunas únicas ou sem métricas."""
        df_sem_agrupamento = pd.DataFrame({
            "descricao": [f"Descricao {i}" for i in range(100)],
            "data": pd.date_range("2026-01-01", periods=100)
        })
        resumo = gerar_resumo_estatistico(df_sem_agrupamento)
        self.assertEqual(resumo["agregacoes"], {})

    def test_responder_pergunta_sobre_dados_mock(self):
        """Testa o fluxo da função responder_pergunta_sobre_dados com cliente mock da Groq."""
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Os produtos que mais venderam foram: 1º Vestido Midi (33 unidades, R$ 5.940,00), seguido por Calça Alfaiataria (12 unidades, R$ 2.640,00) e Camisa Linho (12 unidades, R$ 1.800,00)."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        resumo = gerar_resumo_estatistico(self.df_teste)
        pergunta = "Quais produtos venderam mais e quais geraram mais faturamento?"
        prompt_sistema = "Você é um assistente de moda focado em dados."

        resposta = responder_pergunta_sobre_dados(
            client=mock_client,
            pergunta=pergunta,
            resumo_estatistico=resumo,
            prompt_sistema=prompt_sistema
        )

        self.assertIn("Vestido Midi", resposta)
        mock_client.chat.completions.create.assert_called_once()
        
        # Verifica se o prompt do sistema instrui a usar o campo agregacoes
        call_args = mock_client.chat.completions.create.call_args[1]
        mensagens = call_args["messages"]
        system_msg = next(m["content"] for m in mensagens if m["role"] == "system")
        self.assertIn("agregacoes", system_msg)
        self.assertIn("NUNCA invente", system_msg)
        self.assertIn("5940", system_msg)


if __name__ == "__main__":
    unittest.main()
