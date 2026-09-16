# -*- coding: utf-8 -*-
"""Testes de integridade do golden set (Fase 13, Task 7).

## O que estes testes verificam -- e o que eles deliberadamente NÃO verificam

Eles verificam que cada caso é **bem-formado**: que um caso de resposta esperada é de fato
respondível pelo corpus, e que um caso de abstenção é de fato não-respondível. Isso é uma
propriedade do golden set, não do pipeline.

Eles NÃO verificam que o pipeline acerta os casos. Essa é a medição (Tasks 8 e 9), e ela tem que
poder dar um número ruim -- um golden set ajustado até tudo passar não mede nada. O corpus foi
desenhado justamente para ter casos que o pipeline erra hoje (o motor tabular, por exemplo,
devolve todas as linhas num filtro numérico, e resolve a coluna errada numa média).

A distinção entre os dois é o que mantém a medição honesta: se um caso falha na medição, estes
testes já garantiram que a culpa não é de um critério mal escrito.
"""

import os
import shutil
import unittest
from collections import Counter

import rag_eval
import rag_golden_set as gs
import rag_manager as rm

TENANT_TESTE = "teste_fase13_golden_set"


class TestEstruturaDosCasos(unittest.TestCase):
    """Validações puras, sem indexar nada."""

    def setUp(self):
        self.casos = gs.casos(TENANT_TESTE)

    def test_ids_sao_unicos(self):
        ids = [c.id for c in self.casos]
        duplicados = [i for i, n in Counter(ids).items() if n > 1]
        self.assertEqual(duplicados, [], f"Ids repetidos no golden set: {duplicados}")

    def test_cobertura_minima_por_categoria(self):
        # O golden set anterior tinha 8 casos soltos; o objetivo desta task é cobertura por
        # categoria de consulta, não volume.
        por_categoria = Counter(c.categoria for c in self.casos)
        self.assertGreaterEqual(len(por_categoria), 8, f"Poucas categorias: {dict(por_categoria)}")
        for categoria, quantidade in por_categoria.items():
            with self.subTest(categoria=categoria):
                self.assertGreaterEqual(
                    quantidade, 3,
                    f"Categoria '{categoria}' com só {quantidade} caso(s) -- cobertura fraca "
                    "demais para a métrica por categoria significar alguma coisa.",
                )

    def test_todo_caso_tem_tenant_aplicado(self):
        for caso in self.casos:
            self.assertEqual(caso.tenant_id, TENANT_TESTE)

    def test_categorias_de_abstencao_sao_coerentes(self):
        # Todo caso marcado deve_abster deveria estar numa das categorias de ausência, e
        # vice-versa -- um caso de abstenção perdido noutra categoria distorceria a métrica
        # daquela categoria sem ninguém perceber.
        categorias_de_ausencia = {"anti_alucinacao", "ausencia_parcial"}
        for caso in self.casos:
            with self.subTest(caso=caso.id):
                self.assertEqual(
                    caso.deve_abster, caso.categoria in categorias_de_ausencia,
                    f"Caso {caso.id}: deve_abster={caso.deve_abster} não bate com a categoria "
                    f"'{caso.categoria}'.",
                )


class TestIntegridadeContraOCorpus(unittest.TestCase):
    """Indexa o corpus de verdade e confere cada caso contra os chunks reais."""

    @classmethod
    def setUpClass(cls):
        cls._limpar()
        gs.indexar_corpus(TENANT_TESTE)
        colecao = rm._obter_colecao_tenant(TENANT_TESTE)
        dados = colecao.get(include=["documents", "metadatas"])
        cls.chunks = [
            {"texto": texto, "fonte": meta.get("fonte")}
            for texto, meta in zip(dados["documents"], dados["metadatas"])
        ]

    @classmethod
    def tearDownClass(cls):
        cls._limpar()

    @classmethod
    def _limpar(cls):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)

    def _chunks_que_satisfazem(self, caso):
        return [c for c in self.chunks if rag_eval._chunk_e_relevante(c, caso)]

    def test_corpus_tem_chunks_suficientes_para_o_ranking_importar(self):
        # Num corpus de 1 ou 2 chunks, recall@5 é sempre 1,0 e a métrica não diz nada.
        self.assertGreaterEqual(len(self.chunks), 15)

    def test_todo_caso_de_resposta_esperada_e_respondivel_pelo_corpus(self):
        # A checagem central de integridade: se nenhum chunk do corpus satisfaz o critério, o
        # caso está mal escrito (termo com grafia errada, valor que não existe na tabela) e
        # falharia na medição por motivo errado.
        for caso in gs.casos(TENANT_TESTE):
            if caso.deve_abster or caso.resposta_computada:
                continue
            with self.subTest(caso=caso.id):
                encontrados = self._chunks_que_satisfazem(caso)
                self.assertGreater(
                    len(encontrados), 0,
                    f"Caso {caso.id} ('{caso.query}') não tem nenhum chunk no corpus que satisfaça "
                    f"termos_relevantes={caso.termos_relevantes} -- caso mal escrito, não falha "
                    "de retrieval.",
                )

    def test_todo_caso_de_abstencao_e_de_fato_irrespondivel(self):
        # O espelho da checagem acima: se algum chunk satisfaz o critério, a pergunta TEM resposta
        # na base e o caso não é de abstenção -- marcá-lo como tal puniria o pipeline por acertar.
        for caso in gs.casos(TENANT_TESTE):
            if not caso.deve_abster:
                continue
            with self.subTest(caso=caso.id):
                encontrados = self._chunks_que_satisfazem(caso)
                self.assertEqual(
                    len(encontrados), 0,
                    f"Caso {caso.id} ('{caso.query}') está marcado deve_abster, mas "
                    f"{len(encontrados)} chunk(s) do corpus satisfazem o critério -- a pergunta "
                    "tem resposta na base.",
                )

    def test_caso_de_resposta_computada_nao_esta_no_corpus(self):
        # A razão de ser da flag: a resposta certa (soma, média, contagem distinta) não existe
        # literalmente em nenhum chunk. Se passasse a existir, a flag estaria errada e o caso
        # deixaria de medir o motor tabular.
        for caso in gs.casos(TENANT_TESTE):
            if not caso.resposta_computada:
                continue
            with self.subTest(caso=caso.id):
                self.assertEqual(
                    len(self._chunks_que_satisfazem(caso)), 0,
                    f"Caso {caso.id} está marcado resposta_computada, mas a resposta já existe "
                    "num chunk do corpus -- ele mede recuperação, não cálculo.",
                )

    def test_corpus_e_indexado_com_os_tres_documentos(self):
        fontes = {c["fonte"] for c in self.chunks}
        self.assertEqual(
            fontes, {gs.NOME_MANUAL, gs.NOME_CATALOGO, gs.NOME_NORMAS},
        )


if __name__ == "__main__":
    unittest.main()
