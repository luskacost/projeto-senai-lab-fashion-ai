# -*- coding: utf-8 -*-
"""Fixtures sintéticas compartilhadas por test_retrieval_quality.py e
test_conversational_query_rewriting.py (Fase 9, Bloco F).

Antes, os testes de não-regressão de Prioridades 1/2/3 (test_retrieval_quality.py, e os
métodos test_n/o/s/t/u de test_conversational_query_rewriting.py) assumiam conteúdo já
pré-indexado no tenant real "senai_labfashion", sem nenhum setup próprio -- o que não é
reproduzível numa máquina/CI limpa, já que `tenant_data/` é inteiramente gitignored. Este
módulo reconstrói só os documentos sintéticos necessários (nunca os dados reais de clientes
da empresa, que continuam fora do controle de versão):

- Manual técnico M518/Millie Denim Maskskin: mesmo conteúdo fictício já usado (e já versionado)
  em test_rag.py -- não é dado real.
- empresas_consultores.csv: tabela sintética reaproveitando só os identificadores que já
  apareciam nos próprios testes já versionados (Cia Militar/Morgana, Palatino/Mell, YAZ FIT &
  CASUAL LTDA/Isabella) -- não a lista real de ~60 clientes da empresa.
- teste_pre_auditoria.csv: registros de compra inteiramente fictícios (nomes genéricos, valores
  de exemplo) usados para validar o marcador [VALOR_NEGATIVO].
"""

import io

from fpdf import FPDF

import document_extractors
import rag_manager
from rag_config import RAG_CONFIG

# Config de teste para o manual técnico M518/Millie Denim (Fase 13, Task 3): reproduz, via
# RAG_CONFIG (default vazio em produção), o mesmo comportamento de classificação de metadado e
# alinhamento de variante que antes era hardcoded em rag_manager._inferir_metadados_trecho e
# reranker.HeuristicReranker.rerank. Sem isso, os testes que dependem de distinguir a variante
# Jeans/M518 (ex: "composição da camisa jeans" não deve trazer o algodão do M518) deixariam de
# funcionar -- não porque o mecanismo quebrou, mas porque ele virou opt-in e nenhum tenant de
# teste estava configurando as próprias regras.
CONFIG_HEURISTICAS_TEXTEIS_DE_TESTE = {
    "metadata_keyword_rules": {
        "secao": {
            "Ficha Técnica": ["FICHA TÉCNICA", "FICHA TECNICA"],
            "Desenho Técnico": ["DESENHO TÉCNICO", "DESENHO TECNICO"],
            "Tabela de Medidas": ["TABELA DE MEDIDAS", "MEDIDAS BÁSICAS", "MEDIDAS BASICAS"],
            "Estamparia": ["ESTAMPA", "ESTAMPARIA"],
            "Aviamentos": ["AVIAMENTO"],
            "Etiquetas": ["ETIQUETA"],
            "Especificações Técnicas": ["DESCRIÇÃO TÉCNICA", "DESCRICAO TECNICA", "ESPECIFICAÇÕES"],
        },
        "produto": {
            "Camisa": ["CAMISA", "CAMISETE"],
            "Calça": ["CALÇA", "CALCA"],
        },
        "modelo": {
            "Feminino": ["FEMININA", "FEMININO", "CAMISETE"],
            "Masculino": ["MASCULINA", "MASCULINO"],
            "Infantil": ["INFANTIL"],
            "Unissex": ["UNISSEX"],
        },
        "variante": {
            "Jeans": ["MILLIE DENIM", "MASKSKIN", "JEANS", "LAVAGEM CLARA"],
            "M518": ["M518"],
            "Tradicional": ["TRADICIONAL", "BRANCO, AZUL CLARO E AZUL MARINHO"],
        },
        # Ordem importa: composição (Liocel/Algodão) checada antes do nome de variante, para
        # reproduzir a prioridade que existia no código antigo (a composição, quando presente,
        # sempre prevalecia sobre o material inferido só pelo nome da variante).
        "material": {
            "100% Liocel": ["100% LIOCEL", "LIOCEL"],
            "100% Algodão": ["100% ALGODÃO", "100% ALGODAO"],
            "Millie Denim Maskskin": ["MILLIE DENIM", "MASKSKIN"],
            "M518": ["M518"],
        },
    },
    "variant_alignment_rules": [
        {
            "campo_metadado": "variante",
            "grupos": {"jeans": ["jeans", "millie", "denim"], "m518": ["m518"]},
            "bonus": 0.25,
            "penalidade": 0.40,
        },
        {
            "campo_metadado": "modelo",
            "grupos": {
                "masculino": ["masculin", "homem"],
                "feminino": ["feminin", "camisete", "mulher"],
            },
            "bonus": 0.20,
            "penalidade": 0.20,
        },
    ],
}

_config_original: dict = {}
_contagem_ativacoes = 0


def _ativar_config_de_teste() -> None:
    """Ativa a config acima em RAG_CONFIG, salvando o valor original só na primeira ativação --
    suporta chamadas aninhadas de diferentes suítes sem perder o valor a restaurar depois."""
    global _config_original, _contagem_ativacoes
    if _contagem_ativacoes == 0:
        _config_original = {chave: RAG_CONFIG.get(chave) for chave in CONFIG_HEURISTICAS_TEXTEIS_DE_TESTE}
    _contagem_ativacoes += 1
    RAG_CONFIG.update(CONFIG_HEURISTICAS_TEXTEIS_DE_TESTE)


def _restaurar_config_de_teste() -> None:
    global _contagem_ativacoes
    _contagem_ativacoes = max(0, _contagem_ativacoes - 1)
    if _contagem_ativacoes == 0:
        RAG_CONFIG.update(_config_original)

NOME_MANUAL_TECNICO = "Manual Tecnico - UNIFORMES CAMISA.pdf"
NOME_EMPRESAS_CONSULTORES = "empresas_consultores.csv"
NOME_PRE_AUDITORIA = "teste_pre_auditoria.csv"

_PAGINA_1 = """SENAI LABFASHION - FICHA TÉCNICA DE PRODUTO
PRODUTO: Camisa Feminina Manga Longa
REFERÊNCIA GERAL: CF-2026

1. ESPECIFICAÇÕES DO MODELO BASE (VARIANTE TRADICIONAL):
Tecido: M518
Composição: 100% ALGODÃO
Gramatura: 128 g/m²
Largura: 145 cm
Acabamento: Toque suave, pré-encolhido."""

_PAGINA_2 = """2. ESPECIFICAÇÕES DA VARIANTE JEANS:
PRODUTO: Camisa Feminina Manga Longa
VARIANTE: Jeans / Denim
Tecido: Millie Denim Maskskin
Composição: 100% LIOCEL
Gramatura: 4,5 oz
Largura: 172 cm
Lavagem: Clara com puídos leves."""

_PAGINA_3 = """3. ESPECIFICAÇÕES DE AVIAMENTOS E ETIQUETAS:
Botões: Madrepérola 18mm (6 unidades frontais + 2 punhos).
Etiqueta lateral de composição:
Fio: 50% poliéster e 50% algodão
Linha de costura principal: 100% poliéster 120."""

_CSV_EMPRESAS_CONSULTORES = (
    "Empresa,Consultor\n"
    "Cia Militar,Morgana\n"
    "Palatino Confeccoes,Mell\n"
    "YAZ FIT & CASUAL LTDA,Isabella\n"
    "Confeccao Exemplo Dois,Morgana\n"
)

_CSV_PRE_AUDITORIA = (
    "id,data,descricao,categoria,valor,responsavel\n"
    "1,2026-06-02,Compra de reagentes de laboratorio,Material de consumo,850.00,Ana Souza\n"
    "2,2026-06-03,Manutencao de equipamento,Servico,1200.50,Carlos Lima\n"
    "3,2026-06-05,Reembolso de viagem congresso,Viagem,430.75,Ana Souza\n"
    "4,2026-06-07,Compra de vidraria,Material de consumo,275.00,Bruno Costa\n"
    "5,2026-06-10,Assinatura de software cientifico,Servico,99.90,Carlos Lima\n"
    "6,2026-06-12,Compra de luvas descartaveis,Material de consumo,-150.00,Bruno Costa\n"
    "7,2026-06-15,Reembolso de hospedagem,Viagem,,Ana Souza\n"
    "8,2026-12-20,Compra de equipamento de protecao,Material de consumo,600.00,Carlos Lima\n"
    "9,2026-06-18,Pagamento de consultoria,Servico,15000.00,Bruno Costa\n"
    "10,2026-06-19,Compra de papel e material de escritorio,Material de consumo,45.30,\n"
)


def _construir_pdf_manual_tecnico(caminho: str) -> None:
    pdf = FPDF()
    for conteudo in (_PAGINA_1, _PAGINA_2, _PAGINA_3):
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for linha in conteudo.split("\n"):
            pdf.cell(0, 7, linha.encode("latin-1", "replace").decode("latin-1"), new_x="LMARGIN", new_y="NEXT")
    pdf.output(caminho)


def indexar_fixtures_prioridades(tenant_id: str, caminho_pdf_temp: str) -> None:
    """Indexa os 3 documentos sintéticos no tenant informado. Chamar em setUpClass;
    remover_fixtures_prioridades() correspondente deve rodar em tearDownClass."""
    _ativar_config_de_teste()
    _construir_pdf_manual_tecnico(caminho_pdf_temp)
    paginas = rag_manager.extrair_paginas_pdf(caminho_pdf_temp)
    rag_manager.indexar_documento(tenant_id, NOME_MANUAL_TECNICO, paginas)

    unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(
        io.BytesIO(_CSV_EMPRESAS_CONSULTORES.encode("utf-8")), NOME_EMPRESAS_CONSULTORES
    )
    rag_manager.indexar_documento(tenant_id, NOME_EMPRESAS_CONSULTORES, unidades, dados_tabulares=sheets)

    unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(
        io.BytesIO(_CSV_PRE_AUDITORIA.encode("utf-8")), NOME_PRE_AUDITORIA
    )
    rag_manager.indexar_documento(tenant_id, NOME_PRE_AUDITORIA, unidades, dados_tabulares=sheets)


def remover_fixtures_prioridades(tenant_id: str) -> None:
    rag_manager.remover_documento(tenant_id, NOME_MANUAL_TECNICO)
    rag_manager.remover_documento(tenant_id, NOME_EMPRESAS_CONSULTORES)
    rag_manager.remover_documento(tenant_id, NOME_PRE_AUDITORIA)
    _restaurar_config_de_teste()
