# -*- coding: utf-8 -*-
"""Testes do harness de avaliação de RAG (Fase 13, Task 6).

Usa um tenant sintético próprio, indexado e removido no setUp/tearDown -- nunca dados reais de
cliente (mesma disciplina de tests/rag/fixtures_prioridades_rag.py). Nenhum destes testes faz
chamada de API: `buscar_contexto_relevante` é retrieval puro (embeddings locais).
"""

import os
import shutil
import unittest

import rag_eval as re_
import rag_manager as rm

TENANT_TESTE = "teste_fase13_rag_eval"

_DOCUMENTO = (
    "A camisa social branca tem gola italiana e manga longa, tecido tricoline 100% algodão.\n\n"
    "A calça jeans azul tem corte reto e cinco bolsos, tecido denim pesado.\n\n"
    "O vestido midi floral tem manga curta e cinto na cintura, tecido viscose leve."
)


class TestCasoAvaliacaoValidacao(unittest.TestCase):
    """CasoAvaliacao é uma estrutura pura -- sem tocar em rede/disco."""

    def test_caso_sem_nenhum_criterio_e_sem_deve_abster_levanta_erro(self):
        # Um caso assim nunca teria nenhum chunk contando como relevante -- provavelmente um erro
        # de quem escreveu o golden set (Task 7), não uma configuração válida.
        with self.assertRaises(ValueError):
            re_.CasoAvaliacao(id="x", tenant_id="t", query="qualquer coisa")

    def test_caso_deve_abster_sem_termos_e_valido(self):
        # Casos de anti-alucinação legitimamente não precisam de termos_relevantes -- o próprio
        # sucesso é não encontrar nada.
        caso = re_.CasoAvaliacao(id="x", tenant_id="t", query="pergunta sem resposta", deve_abster=True)
        self.assertEqual(caso.termos_relevantes, [])

    def test_caso_so_com_fontes_relevantes_e_valido(self):
        caso = re_.CasoAvaliacao(id="x", tenant_id="t", query="q", fontes_relevantes=["doc.pdf"])
        self.assertEqual(caso.fontes_relevantes, ["doc.pdf"])


class TestExecutarCasoBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._limpar()
        rm.indexar_documento(TENANT_TESTE, "catalogo.txt", _DOCUMENTO)

    @classmethod
    def tearDownClass(cls):
        cls._limpar()

    @classmethod
    def _limpar(cls):
        caminho = os.path.join("tenant_data", "chroma", TENANT_TESTE)
        if os.path.exists(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        rm._CHROMA_CLIENTS.pop(TENANT_TESTE, None)


class TestExecutarCaso(TestExecutarCasoBase):

    def test_caso_com_termo_presente_e_julgado_relevante(self):
        caso = re_.CasoAvaliacao(
            id="c1", tenant_id=TENANT_TESTE, query="qual o tecido da camisa social",
            termos_relevantes=["tricoline"],
        )
        resultado = re_.executar_caso(caso, k=5)
        self.assertGreater(len(resultado.chunks_recuperados), 0)
        self.assertTrue(any(resultado.relevancias), "Nenhum chunk foi julgado relevante, mas o termo existe na base.")

    def test_relevancias_tem_mesmo_tamanho_que_chunks_recuperados(self):
        caso = re_.CasoAvaliacao(
            id="c2", tenant_id=TENANT_TESTE, query="calça jeans", termos_relevantes=["denim"],
        )
        resultado = re_.executar_caso(caso, k=5)
        self.assertEqual(len(resultado.relevancias), len(resultado.chunks_recuperados))

    def test_termo_ausente_da_base_nao_e_julgado_relevante_em_nenhum_chunk(self):
        caso = re_.CasoAvaliacao(
            id="c3", tenant_id=TENANT_TESTE, query="qual o preço da camisa",
            termos_relevantes=["um termo que definitivamente não existe na base xyzabc"],
        )
        resultado = re_.executar_caso(caso, k=5)
        self.assertFalse(any(resultado.relevancias))

    def test_fontes_relevantes_restringe_por_metadado_fonte(self):
        caso = re_.CasoAvaliacao(
            id="c4", tenant_id=TENANT_TESTE, query="camisa social gola",
            fontes_relevantes=["arquivo_que_nao_existe.txt"],
        )
        resultado = re_.executar_caso(caso, k=5)
        # A busca pode até recuperar chunks relevantes por conteúdo, mas nenhum vem da fonte
        # exigida -- o critério de fonte tem que vencer.
        self.assertFalse(any(resultado.relevancias))

    def test_deve_abster_correto_quando_nada_relevante_e_recuperado(self):
        caso = re_.CasoAvaliacao(
            id="c5", tenant_id=TENANT_TESTE, query="qual o CNPJ da empresa fabricante",
            termos_relevantes=["cnpj"], deve_abster=True,
        )
        resultado = re_.executar_caso(caso, k=5)
        self.assertTrue(resultado.abstencao_correta())

    def test_normalizacao_de_acento_e_case_no_julgamento(self):
        caso = re_.CasoAvaliacao(
            id="c6", tenant_id=TENANT_TESTE, query="vestido floral",
            termos_relevantes=["VESTIDO MIDI"],  # maiúsculas, o texto tem "vestido midi"
        )
        resultado = re_.executar_caso(caso, k=5)
        self.assertTrue(any(resultado.relevancias))


class TestExecutarConjuntoESerializacao(TestExecutarCasoBase):

    def test_executar_conjunto_preserva_ordem_e_roda_todos(self):
        casos = [
            re_.CasoAvaliacao(id="a", tenant_id=TENANT_TESTE, query="camisa", termos_relevantes=["tricoline"]),
            re_.CasoAvaliacao(id="b", tenant_id=TENANT_TESTE, query="calça", termos_relevantes=["denim"]),
        ]
        resultados = re_.executar_conjunto(casos, k=3)
        self.assertEqual([r.caso_id for r in resultados], ["a", "b"])

    def test_to_dict_e_serializavel_em_json(self):
        import json
        caso = re_.CasoAvaliacao(id="a", tenant_id=TENANT_TESTE, query="camisa", termos_relevantes=["tricoline"])
        resultado = re_.executar_caso(caso, k=3)
        # Não deve levantar -- prova que to_dict() não vaza nenhum tipo não serializável
        # (ex: um objeto CandidateChunk cru, um set).
        serializado = json.dumps(resultado.to_dict(), ensure_ascii=False)
        self.assertIn("a", serializado)

    def test_salvar_relatorio_json_grava_arquivo_valido(self):
        import json
        import tempfile

        caso = re_.CasoAvaliacao(id="a", tenant_id=TENANT_TESTE, query="camisa", termos_relevantes=["tricoline"])
        resultados = re_.executar_conjunto([caso], k=3)

        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "relatorio.json")
            re_.salvar_relatorio_json(resultados, caminho)
            with open(caminho, encoding="utf-8") as f:
                conteudo = json.load(f)
            self.assertEqual(len(conteudo), 1)
            self.assertEqual(conteudo[0]["caso_id"], "a")


class TestTermosProibidos(TestExecutarCasoBase):
    """Fase 13, Task 7: um chunk que contém um termo proibido não conta como relevante, mesmo
    tendo todos os termos esperados -- o caso de uso real é um filtro tabular quebrado que
    devolve a tabela inteira (e portanto também as linhas certas)."""

    def test_termo_proibido_desqualifica_chunk_que_tem_os_termos_esperados(self):
        caso_sem_proibicao = re_.CasoAvaliacao(
            id="p1", tenant_id=TENANT_TESTE, query="camisa social",
            termos_relevantes=["tricoline"],
        )
        caso_com_proibicao = re_.CasoAvaliacao(
            id="p2", tenant_id=TENANT_TESTE, query="camisa social",
            termos_relevantes=["tricoline"],
            termos_proibidos=["denim"],  # o chunk único do fixture tem as três peças juntas
        )
        self.assertTrue(any(re_.executar_caso(caso_sem_proibicao, k=5).relevancias))
        self.assertFalse(any(re_.executar_caso(caso_com_proibicao, k=5).relevancias))


class TestEcoDaPerguntaNaoContaComoEvidencia(unittest.TestCase):
    """Fase 13, Task 7: o motor tabular devolve um bloco que começa ecoando a pergunta do
    usuário. Sem descontar esse eco, um caso de abstenção seria julgado respondido porque o termo
    proibido aparece... na própria pergunta repetida."""

    def test_chunk_que_so_repete_a_pergunta_nao_e_relevante(self):
        caso = re_.CasoAvaliacao(
            id="e1", tenant_id="irrelevante", query="Qual o prazo de entrega do tecido TX-200?",
            termos_relevantes=["prazo de entrega"], deve_abster=True,
        )
        chunk_que_ecoa = {
            "texto": "[TABULAR_RESULT]\nConsulta: Qual o prazo de entrega do tecido TX-200?\n"
                     "Resultado: Codigo: TX-200, Nome: Oxford",
            "fonte": "catalogo.csv",
        }
        self.assertFalse(re_._chunk_e_relevante(chunk_que_ecoa, caso))

    def test_chunk_com_o_termo_fora_do_eco_continua_relevante(self):
        # A regra não pode ser tão agressiva a ponto de descartar evidência de verdade: se o termo
        # aparece ALÉM do eco da pergunta, o chunk continua contando.
        caso = re_.CasoAvaliacao(
            id="e2", tenant_id="irrelevante", query="Qual o prazo de entrega do tecido TX-200?",
            termos_relevantes=["prazo de entrega"],
        )
        chunk_com_conteudo = {
            "texto": "[TABULAR_RESULT]\nConsulta: Qual o prazo de entrega do tecido TX-200?\n"
                     "Resultado: prazo de entrega contratual de 15 dias uteis.",
            "fonte": "catalogo.csv",
        }
        self.assertTrue(re_._chunk_e_relevante(chunk_com_conteudo, caso))


class TestCarregarCasosDeJson(unittest.TestCase):

    def test_carrega_casos_e_permite_sobrescrever_tenant(self):
        import json
        import tempfile

        bruto = [{
            "id": "x1", "tenant_id": "tenant_original", "query": "pergunta",
            "termos_relevantes": ["termo"], "categoria": "conceptual",
        }]
        with tempfile.TemporaryDirectory() as tmp:
            caminho = os.path.join(tmp, "casos.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(bruto, f)

            casos_sem_override = re_.carregar_casos_de_json(caminho)
            self.assertEqual(casos_sem_override[0].tenant_id, "tenant_original")

            casos_com_override = re_.carregar_casos_de_json(caminho, tenant_id="outro_tenant")
            self.assertEqual(casos_com_override[0].tenant_id, "outro_tenant")
            self.assertEqual(casos_com_override[0].categoria, "conceptual")


if __name__ == "__main__":
    unittest.main()
