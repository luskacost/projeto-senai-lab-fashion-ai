# -*- coding: utf-8 -*-
"""Testes automatizados de Retrieval, Query Understanding, Expansão e Reranking."""

import json
import os
import shutil
import unittest

from rag_manager import (
    indexar_documento,
    buscar_contexto_relevante,
    listar_documentos_indexados,
    remover_documento
)
from query_engine import analisar_query_completa, QueryCategory
from reranker import HeuristicReranker


DOC_CONCEITUAL_PAG_1 = """PROCESSAMENTO DE LINGUAGEM NATURAL E DESAMBIGUAÇÃO:
O contexto é fundamental para interpretar palavras polissêmicas ou ambíguas como 'banco', que pode significar tanto uma instituição financeira quanto um assento físico.
Sistemas de Inteligência Artificial utilizam a análise do contexto textual ao redor das palavras para realizar a correta desambiguação semântica, reduzindo ambiguidades e determinando o significado preciso na frase."""

DOC_CONCEITUAL_PAG_2 = """VALIDAÇÃO CRUZADA E MACHINE LEARNING:
O método K-Fold Cross-Validation divide o conjunto de dados em K partições iterativas para treinar e validar o modelo.
Essa técnica é essencial para proteger contra overfitting (sobreajuste), pois testa o modelo em folds não vistos;
mitiga riscos de data leakage (vazamento de dados) ao isolar transformações dentro de cada fold;
e auxilia na identificação de concept drift (deriva de conceito) ao avaliar a estabilidade do modelo através das partições."""

DOC_CONCEITUAL_PAG_3 = """COMPARAÇÃO ENTRE ARQUITETURAS DE LINGUAGEM:
Large Language Models (LLMs) operam com dezenas a centenas de bilhões de parâmetros, demandando hardware corporativo com clusters de GPUs e infraestrutura em nuvem, sendo indicados para raciocínio generalista complexo.
Por outro lado, Small Language Models (SLMs) possuem faixa de 1 a 7 bilhões de parâmetros, possibilitam execução local em edge devices e hardware modesto, com baixíssimo consumo de memória e foco em tarefas especializadas."""

DOC_CONCEITUAL_PAG_4 = """FICHA TÉCNICA TÊXTIL E ESPECIFICAÇÕES DE MATERIAIS:
Modelo Base Tradicional: Tecido M518, gramatura 128 g/m², largura 145 cm, composição 100% Algodão.
Variante Camisa Jeans: Tecido Millie Denim Maskskin, gramatura 4,5 oz, largura 172 cm, composição 100% Liocel, lavagem clara."""


class TestRAGRetrieval(unittest.TestCase):
    TENANT_TESTE = "test_eval_retrieval"

    @classmethod
    def setUpClass(cls):
        caminho = os.path.join("tenant_data", "chroma", cls.TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)

        paginas = [
            {"pagina": 1, "texto": DOC_CONCEITUAL_PAG_1},
            {"pagina": 2, "texto": DOC_CONCEITUAL_PAG_2},
            {"pagina": 3, "texto": DOC_CONCEITUAL_PAG_3},
            {"pagina": 4, "texto": DOC_CONCEITUAL_PAG_4}
        ]
        indexar_documento(cls.TENANT_TESTE, "manual_conceitual_e_tecnico.pdf", paginas)

    @classmethod
    def tearDownClass(cls):
        caminho = os.path.join("tenant_data", "chroma", cls.TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)

    def test_01_query_classification_and_expansion(self):
        """Valida que a classificação de queries identifica categorias e gera expansões pertinentes."""
        q1 = "Por que o contexto é importante para interpretar uma palavra como banco?"
        a1 = analisar_query_completa(q1)
        self.assertIn(QueryCategory.CONCEPTUAL, a1.categories)
        self.assertTrue(len(a1.expanded_queries) >= 1)

        q2 = "Como o K-Fold Cross-Validation ajuda a proteger contra overfitting, concept drift e data leakage?"
        a2 = analisar_query_completa(q2)
        self.assertIn(QueryCategory.MULTI_CONCEPT, a2.categories)
        self.assertTrue(len(a2.decomposed_queries) >= 2)

        q3 = "Compare LLMs e SLMs em relação a parâmetros e hardware."
        a3 = analisar_query_completa(q3)
        self.assertIn(QueryCategory.COMPARATIVE, a3.categories)

    def test_02_retrieval_conceptual_contexto_banco(self):
        """Valida recuperação bem-sucedida para a pergunta conceitual sobre contexto e a palavra banco."""
        query = "Por que o contexto é importante para interpretar uma palavra como banco?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)
        
        texto_unido = " ".join(r["texto"].lower() for r in resultados)
        self.assertIn("contexto", texto_unido)
        self.assertIn("banco", texto_unido)
        self.assertIn("ambígua", texto_unido)

    def test_03_retrieval_multi_concept_kfold(self):
        """Valida que a consulta multi-conceito de K-Fold recupera trechos contendo overfitting, concept drift e data leakage."""
        query = "Como o K-Fold Cross-Validation ajuda a proteger contra overfitting, concept drift e data leakage?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)

        texto_unido = " ".join(r["texto"].lower() for r in resultados)
        self.assertIn("k-fold", texto_unido)
        self.assertIn("overfitting", texto_unido)
        self.assertIn("data leakage", texto_unido)
        self.assertIn("concept drift", texto_unido)

    def test_04_retrieval_comparative_llm_vs_slm(self):
        """Valida que a consulta comparativa LLM vs SLM recupera informações sobre ambas as entidades."""
        query = "Compare LLMs e SLMs em relação a parâmetros, hardware, execução e casos de uso."
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        self.assertGreater(len(resultados), 0)

        texto_unido = " ".join(r["texto"].lower() for r in resultados)
        self.assertIn("large language models", texto_unido)
        self.assertIn("small language models", texto_unido)
        self.assertIn("parâmetros", texto_unido)
        self.assertIn("hardware", texto_unido)

    def test_05_retrieval_unknown_info(self):
        """Valida que para pergunta sem evidência no documento, não há retorno indevido de chunks com alto score."""
        query = "Qual é a chave de API secreta do servidor de produção?"
        resultados = buscar_contexto_relevante(self.TENANT_TESTE, query, top_k=5)
        for r in resultados:
            self.assertNotIn("chave de API", r["texto"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
