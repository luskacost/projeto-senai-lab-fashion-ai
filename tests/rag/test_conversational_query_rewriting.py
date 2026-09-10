# -*- coding: utf-8 -*-
"""Suíte de Testes Automatizados para a Prioridade 4 (Query Rewriting e Memória Conversacional).

Valida resolução de pronomes, continuações curtas, anáforas, conjuntos tabulares anteriores,
não-invenção de fatos, expiração de entidades por idade, isolamento por tenant/conversation_id,
persistência no disco, integração com RAG vetorial e Tabular Engine, e testes de generalização sintética.
"""

import io
import os
import shutil
import unittest
from typing import Any, Dict, List

from .fixtures_prioridades_rag import indexar_fixtures_prioridades, remover_fixtures_prioridades
import conversational_query
from conversational_query import (
    ConversationEntity,
    ConversationMemory,
    ConversationTurn,
    analisar_dependencia_contextual,
    carregar_memoria_conversacao,
    extrair_entidades_fatuais_do_contexto,
    normalizar_texto_conversacional,
    reescrever_query_conversacional,
    registrar_turno_conversacional,
    resolver_entidades_contextual,
    salvar_memoria_conversacao
)
import document_extractors
import rag_manager
from rag_config import RAG_CONFIG
import tabular_query_engine


class TestConversationalQueryRewriting(unittest.TestCase):
    """Suíte Completa de Testes da Prioridade 4."""

    TENANT_A = "tenant_test_conv_a"
    TENANT_B = "tenant_test_conv_b"
    CONV_1 = "conv_suite_1"
    CONV_2 = "conv_suite_2"

    # Tenant de teste dedicado com fixtures sintéticas próprias (ver fixtures_prioridades_rag.py)
    # -- os testes N/O/S/T/U usavam antes o tenant real "senai_labfashion", assumindo conteúdo
    # pré-indexado localmente que nunca esteve sob controle de versão (quebrava numa máquina/CI
    # limpa). TENANT_A/TENANT_B continuam intactos para os demais testes desta classe.
    TENANT_RAG_FIXTURE = "teste_prioridades_conv"

    @classmethod
    def setUpClass(cls):
        caminho_chroma = os.path.join("tenant_data", "chroma", cls.TENANT_RAG_FIXTURE)
        if os.path.exists(caminho_chroma):
            shutil.rmtree(caminho_chroma, ignore_errors=True)
        cls.pdf_temp_path = "temp_manual_tecnico_conv_rewriting.pdf"
        indexar_fixtures_prioridades(cls.TENANT_RAG_FIXTURE, cls.pdf_temp_path)

    @classmethod
    def tearDownClass(cls):
        remover_fixtures_prioridades(cls.TENANT_RAG_FIXTURE)
        caminho_chroma = os.path.join("tenant_data", "chroma", cls.TENANT_RAG_FIXTURE)
        if os.path.exists(caminho_chroma):
            shutil.rmtree(caminho_chroma, ignore_errors=True)
        if os.path.exists(cls.pdf_temp_path):
            try:
                os.remove(cls.pdf_temp_path)
            except Exception:
                pass

    def setUp(self):
        # Limpeza inicial do tenant de teste
        rag_manager.remover_documento(self.TENANT_A, "empresas_teste.csv")
        rag_manager.remover_documento(self.TENANT_B, "empresas_teste.csv")
        dir_conv = conversational_query.DIRETORIO_MEMORIA_CONVERSAS
        if os.path.exists(dir_conv):
            for fname in os.listdir(dir_conv):
                if fname.startswith((self.TENANT_A, self.TENANT_B, self.TENANT_RAG_FIXTURE)):
                    try:
                        os.remove(os.path.join(dir_conv, fname))
                    except Exception:
                        pass

    def tearDown(self):
        self.setUp()

    def test_a_pronome_feminino(self):
        """TESTE A: Pronome feminino 'ela' resolvido para consultora factual (Morgana)."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem atende a empresa Cia Militar?",
            rewritten_query=None,
            assistant_answer="Morgana atende a Cia Militar.",
            sources=["empresas_consultores.xlsx"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana", "empresa": "Cia Militar"}]}
        )

        res = reescrever_query_conversacional("Quais outras empresas ela atende?", self.TENANT_A, self.CONV_1)
        self.assertTrue(res.context_resolved)
        self.assertEqual(res.dependency_type, "PRONOUN")
        self.assertIn("Morgana", res.rewritten_query)
        self.assertEqual(res.entities_used, ["Morgana"])

    def test_b_pronome_masculino(self):
        """TESTE B: Pronome masculino 'dele' resolvido para responsável factual (Bruno Costa)."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem é o responsável pelo lançamento de consultoria?",
            rewritten_query=None,
            assistant_answer="Bruno Costa é o responsável.",
            sources=["teste_pre_auditoria.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"responsavel": "Bruno Costa", "descricao": "Pagamento de consultoria"}]}
        )

        res = reescrever_query_conversacional("Qual é o telefone dele?", self.TENANT_A, self.CONV_1)
        self.assertTrue(res.context_resolved)
        self.assertEqual(res.dependency_type, "PRONOUN")
        self.assertIn("Bruno Costa", res.rewritten_query)

    def test_c_continucao_curta(self):
        """TESTE C: Continuação curta 'E a composição?' expandida com a entidade anterior (M518)."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Qual é a gramatura do tecido M518?",
            rewritten_query=None,
            assistant_answer="A gramatura do M518 é 128 g/m².",
            sources=["Manual Tecnico.pdf"],
            retrieved_chunks=[{"meta": {"material": "M518", "produto": "Camisa"}, "texto": "Gramatura do tecido M518 é 128 g/m²"}]
        )

        res = reescrever_query_conversacional("E a composição?", self.TENANT_A, self.CONV_1)
        self.assertTrue(res.context_resolved)
        self.assertEqual(res.dependency_type, "IMPLICIT_CONTINUATION")
        self.assertIn("M518", res.rewritten_query)

    def test_d_multiplas_continuacoes(self):
        """TESTE D: Múltiplas continuações consecutivas preservam a entidade principal."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Qual é a gramatura do M518?",
            rewritten_query=None,
            assistant_answer="128 g/m²",
            sources=["Manual.pdf"],
            retrieved_chunks=[{"meta": {"material": "M518"}, "texto": "M518"}]
        )

        res1 = reescrever_query_conversacional("E a composição?", self.TENANT_A, self.CONV_1)
        self.assertIn("M518", res1.rewritten_query)

        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="E a composição?",
            rewritten_query=res1.rewritten_query,
            assistant_answer="100% Algodão",
            sources=["Manual.pdf"],
            retrieved_chunks=[{"meta": {"material": "M518"}, "texto": "100% Algodão"}]
        )

        res2 = reescrever_query_conversacional("E qual é a largura?", self.TENANT_A, self.CONV_1)
        self.assertTrue(res2.context_resolved)
        self.assertIn("M518", res2.rewritten_query)

    def test_e_pergunta_independente(self):
        """TESTE E: Pergunta autocontida não é alterada desnecessariamente."""
        res = reescrever_query_conversacional("Qual é a gramatura do tecido M518?", self.TENANT_A, self.CONV_1)
        self.assertFalse(res.requires_context)
        self.assertTrue(res.context_resolved)
        self.assertEqual(res.rewritten_query, "Qual é a gramatura do tecido M518?")

    def test_f_prioridade_entidade_explicita(self):
        """TESTE F: Entidade explícita na pergunta atual tem prioridade total sobre a memória."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem atende Cia Militar?",
            rewritten_query=None,
            assistant_answer="Morgana.",
            sources=["dados.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana", "empresa": "Cia Militar"}]}
        )

        # Pergunta traz 'Isabella' explicitamente
        res = reescrever_query_conversacional("Quais empresas Isabella atende?", self.TENANT_A, self.CONV_1)
        self.assertEqual(res.rewritten_query, "Quais empresas Isabella atende?")
        self.assertEqual(res.dependency_type, "NONE")

    def test_g_referencia_conjunto_tabular(self):
        """TESTE G: Referência a conjunto tabular anterior ('qual delas') preserva os elementos."""
        registrar_turno_conversacional(
            self.TENANT_A, "conv_g",
            user_query="Quais empresas Morgana atende?",
            rewritten_query=None,
            assistant_answer="Empresa Alpha, Empresa Beta, Empresa Gamma.",
            sources=["dados.csv"],
            retrieved_chunks=[],
            tabular_result={
                "operation": "FILTER",
                "records": [
                    {"empresa": "Empresa Alpha", "consultor": "Morgana"},
                    {"empresa": "Empresa Beta", "consultor": "Morgana"},
                    {"empresa": "Empresa Gamma", "consultor": "Morgana"}
                ]
            }
        )

        res = reescrever_query_conversacional("Qual delas possui o maior faturamento?", self.TENANT_A, "conv_g")
        self.assertTrue(res.context_resolved, msg=f"Falha na resolução: fallback={res.fallback_reason}, debug={res.debug}")
        self.assertEqual(res.dependency_type, "SET_REFERENCE")
        self.assertIn("Empresa Alpha", res.rewritten_query)
        self.assertIn("Empresa Beta", res.rewritten_query)

    def test_h_resultado_tabular_nao_inventado(self):
        """TESTE H: Sem conjunto prévio na memória, 'qual delas' falha com segurança sem inventar."""
        res = reescrever_query_conversacional("Qual delas possui o maior faturamento?", self.TENANT_A, "conv_h_empty")
        self.assertFalse(res.context_resolved)
        self.assertEqual(res.fallback_reason, "no_conversation_history")

    def test_i_ambiguidade_nao_resolvida(self):
        """TESTE I: Ambiguidade com 2 pessoas do mesmo tipo no mesmo turno retorna context_resolved=False."""
        mem = ConversationMemory(tenant_id=self.TENANT_A, conversation_id=self.CONV_1)
        t = ConversationTurn(
            turn_index=1,
            user_query="Quem atende Alpha e Beta?",
            rewritten_query=None,
            assistant_answer="Morgana e Isabella.",
            entities=[
                ConversationEntity(text="Morgana", entity_type="person", source="tabular", turn_index=1),
                ConversationEntity(text="Isabella", entity_type="person", source="tabular", turn_index=1)
            ]
        )
        mem.turns.append(t)
        mem.entities.extend(t.entities)
        salvar_memoria_conversacao(mem)

        res = reescrever_query_conversacional("Qual outra empresa ela atende?", self.TENANT_A, self.CONV_1)
        self.assertFalse(res.context_resolved)
        self.assertEqual(res.fallback_reason, "ambiguous_entity_reference")

    def test_j_expiracao_entidade_antiga(self):
        """TESTE J: Entidade antiga (idade > conversation_entity_max_age_turns) não é utilizada."""
        cfg_custom = dict(RAG_CONFIG)
        cfg_custom["conversation_entity_max_age_turns"] = 2

        # Registra 4 turnos
        for i in range(1, 5):
            registrar_turno_conversacional(
                self.TENANT_A, self.CONV_1,
                user_query=f"Turno {i}",
                rewritten_query=None,
                assistant_answer=f"Resp {i}",
                sources=["doc.pdf"],
                retrieved_chunks=[{"meta": {"produto": f"Produto_{i}"}, "texto": f"Txt {i}"}],
                config=cfg_custom
            )

        # Pergunta no Turno 5 tenta acessar Produto_1 (idade = 5 - 1 = 4 > max_age 2)
        mem = carregar_memoria_conversacao(self.TENANT_A, self.CONV_1)
        res_ent, conf, fallback = resolver_entidades_contextual("E a composição?", mem, "IMPLICIT_CONTINUATION", {}, cfg_custom)
        # Deve pegar Produto_4 (mais recente, idade 1), e NUNCA Produto_1
        self.assertEqual(res_ent[0].text, "Produto_4")

    def test_k_isolamento_por_conversation_id(self):
        """TESTE K: Memórias de conversas diferentes no mesmo tenant são isoladas."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem atende Cia Militar?",
            rewritten_query=None,
            assistant_answer="Morgana",
            sources=["doc.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana"}]}
        )

        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_2,
            user_query="Quem atende YAZ FIT?",
            rewritten_query=None,
            assistant_answer="Isabella",
            sources=["doc.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Isabella"}]}
        )

        res1 = reescrever_query_conversacional("Quais outras empresas ela atende?", self.TENANT_A, self.CONV_1)
        res2 = reescrever_query_conversacional("Quais outras empresas ela atende?", self.TENANT_A, self.CONV_2)

        self.assertIn("Morgana", res1.rewritten_query)
        self.assertIn("Isabella", res2.rewritten_query)

    def test_l_isolamento_multi_tenant(self):
        """TESTE L: Memórias de tenants diferentes são estritamente isoladas no disco."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem atende Cia Militar?",
            rewritten_query=None,
            assistant_answer="Morgana",
            sources=["doc.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana"}]}
        )

        registrar_turno_conversacional(
            self.TENANT_B, self.CONV_1,
            user_query="Quem atende Empresa Beta?",
            rewritten_query=None,
            assistant_answer="Fernanda",
            sources=["doc.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Fernanda"}]}
        )

        res_a = reescrever_query_conversacional("Quais outras empresas ela atende?", self.TENANT_A, self.CONV_1)
        res_b = reescrever_query_conversacional("Quais outras empresas ela atende?", self.TENANT_B, self.CONV_1)

        self.assertIn("Morgana", res_a.rewritten_query)
        self.assertIn("Fernanda", res_b.rewritten_query)

    def test_m_persistencia_disco(self):
        """TESTE M: Memória conversacional é persistida no JSON e recarregada fielmente."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Qual a gramatura do M518?",
            rewritten_query=None,
            assistant_answer="128 g/m²",
            sources=["Manual.pdf"],
            retrieved_chunks=[{"meta": {"material": "M518"}, "texto": "M518"}]
        )

        # Recarrega do arquivo no disco
        mem_carregada = carregar_memoria_conversacao(self.TENANT_A, self.CONV_1)
        self.assertEqual(len(mem_carregada.turns), 1)
        self.assertEqual(mem_carregada.recent_subject, "M518")
        self.assertTrue(any(e.text == "M518" for e in mem_carregada.entities))

    def test_n_fallback_rag_vetorial(self):
        """TESTE N: Pergunta reescrita sem intenção tabular segue para a busca vetorial."""
        registrar_turno_conversacional(
            self.TENANT_RAG_FIXTURE, self.CONV_1,
            user_query="Qual é a gramatura do tecido M518?",
            rewritten_query=None,
            assistant_answer="128 g/m²",
            sources=["Manual.pdf"],
            retrieved_chunks=[{"meta": {"material": "M518"}, "texto": "M518"}]
        )

        res_chunks = rag_manager.buscar_contexto_relevante(
            self.TENANT_RAG_FIXTURE,
            "E a composição?",
            conversation_id=self.CONV_1,
            final_k=2
        )
        self.assertTrue(len(res_chunks) > 0)
        # Verifica se o relatório de debug registrou a reescrita conversacional
        dbg = rag_manager.obter_ultimo_rag_debug()
        conv_dbg = dbg.get("conversational_query_debug", {})
        self.assertTrue(conv_dbg.get("context_resolved"))
        self.assertIn("M518", conv_dbg.get("rewritten_query", ""))

    def test_o_query_reescrita_para_tabular_engine(self):
        """TESTE O: Query reescrita 'Quais outras empresas a consultora Morgana atende?' aciona o Tabular Engine."""
        registrar_turno_conversacional(
            self.TENANT_RAG_FIXTURE, self.CONV_1,
            user_query="Quem atende Cia Militar?",
            rewritten_query=None,
            assistant_answer="Morgana",
            sources=["empresas_consultores.xlsx"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana", "empresa": "Cia Militar"}]}
        )

        res_chunks = rag_manager.buscar_contexto_relevante(
            self.TENANT_RAG_FIXTURE,
            "Quais outras empresas ela atende?",
            conversation_id=self.CONV_1,
            final_k=2
        )
        self.assertTrue(len(res_chunks) > 0)
        self.assertEqual(res_chunks[0].get("tipo_arquivo"), "tabular")
        self.assertIn("Morgana", res_chunks[0].get("texto"))

    def test_p_nao_salvar_alucinacao_llm(self):
        """TESTE P: Afirmações não verificadas geradas pelo LLM não são gravadas na memória factual."""
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Qual é o preço do produto X?",
            rewritten_query=None,
            assistant_answer="O fornecedor Fabrica Ficticia vende por R$ 999.00.",  # Alucinação sem fontes
            sources=[],
            retrieved_chunks=[],
            tabular_result=None
        )

        mem = carregar_memoria_conversacao(self.TENANT_A, self.CONV_1)
        # Garante que 'Fabrica Ficticia' NUNCA entrou na memória factual de entidades
        self.assertFalse(any("Fabrica Ficticia" in e.text for e in mem.entities))

    def test_q_limite_de_turnos_memoria(self):
        """TESTE Q: Excesso de turnos é truncado para no máximo conversation_memory_max_turns (10)."""
        cfg_custom = dict(RAG_CONFIG)
        cfg_custom["conversation_memory_max_turns"] = 5

        for i in range(1, 10):
            registrar_turno_conversacional(
                self.TENANT_A, self.CONV_1,
                user_query=f"Turno {i}",
                rewritten_query=None,
                assistant_answer=f"Resp {i}",
                sources=[],
                retrieved_chunks=[],
                config=cfg_custom
            )

        mem = carregar_memoria_conversacao(self.TENANT_A, self.CONV_1)
        self.assertEqual(len(mem.turns), 5)
        self.assertEqual(mem.turns[0].user_query, "Turno 5")
        self.assertEqual(mem.turns[-1].user_query, "Turno 9")

    def test_r_pronomes_possessivos_e_plurais(self):
        """TESTE R: Resolução de pronomes possessivos (dele, dela, deles, delas)."""
        # Turno 1 com 2 consultores em um grupo
        registrar_turno_conversacional(
            self.TENANT_A, self.CONV_1,
            user_query="Quem são as consultoras responsável pela Cia Militar e Palatino?",
            rewritten_query=None,
            assistant_answer="Morgana e Mell.",
            sources=["doc.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": "Morgana"}, {"consultor": "Mell"}]}
        )

        res = reescrever_query_conversacional("Quais os telefones delas?", self.TENANT_A, self.CONV_1)
        self.assertTrue(res.context_resolved)

    def test_s_nao_regressao_prioridade_1(self):
        """TESTE S: Não-regressão da Prioridade 1 (Precision retrieval e Reranking)."""
        res = rag_manager.buscar_contexto_relevante(self.TENANT_RAG_FIXTURE, "Quem é responsável por atender a empresa Cia Militar?", final_k=3)
        self.assertTrue(len(res) > 0)
        self.assertTrue(any("Morgana" in c["texto"] for c in res))

    def test_t_nao_regressao_prioridade_2(self):
        """TESTE T: Não-regressão da Prioridade 2 (Semantic Enrichment [VALOR_NEGATIVO])."""
        res = rag_manager.buscar_contexto_relevante(self.TENANT_RAG_FIXTURE, "Existe algum lançamento com valor negativo?", final_k=3)
        self.assertTrue(len(res) > 0)
        textos = [c["texto"] for c in res]
        self.assertTrue(any("-150" in t or "[VALOR_NEGATIVO]" in t for t in textos))

    def test_u_nao_regressao_prioridade_3(self):
        """TESTE U: Não-regressão da Prioridade 3 (Tabular Query Engine determinístico)."""
        res = rag_manager.buscar_contexto_relevante(self.TENANT_RAG_FIXTURE, "Quantas empresas cada consultor atende?", final_k=3)
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0].get("tipo_arquivo"), "tabular")
        self.assertIn("GROUP_COUNT", res[0].get("rotulo_unidade"))

    def test_generalizacao_sintetica(self):
        """TESTE GENERALIZAÇÃO: Garante regras genéricas baseadas em tipos sem hardcode de nomes."""
        # Nomes completamente novos e sintéticos
        nome_sintetico_p = "Carlos Alberto"
        empresa_sintetica = "Indústria Química Alpha"
        conversa_sintetica = "conv_sintetica_001"

        registrar_turno_conversacional(
            self.TENANT_A, conversa_sintetica,
            user_query=f"Quem atende a {empresa_sintetica}?",
            rewritten_query=None,
            assistant_answer=f"{nome_sintetico_p} atende.",
            sources=["sintetico.csv"],
            retrieved_chunks=[],
            tabular_result={"records": [{"consultor": nome_sintetico_p, "empresa": empresa_sintetica}]}
        )

        res = reescrever_query_conversacional("Quais outras empresas ele atende?", self.TENANT_A, conversa_sintetica)
        self.assertTrue(res.context_resolved)
        self.assertIn(nome_sintetico_p, res.rewritten_query)
        self.assertNotIn("Morgana", res.rewritten_query)


if __name__ == "__main__":
    unittest.main()
