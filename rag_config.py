# -*- coding: utf-8 -*-
"""Configuração centralizada do pipeline RAG para o Senai LabFashion IA.

Centraliza hiperparâmetros de ingestão, busca vetorial, expansão, decomposição,
reranking, diversidade e observabilidade.
"""

import os
from typing import Dict, Any

# Modelo OpenAI usado em todas as chamadas de texto (chat, moderação, tool-calling de
# croqui/tendências, síntese do RAG) -- ver geracao_imagem.py/moderacao.py. Centralizado aqui
# para evitar divergência entre os pontos de chamada. Substituiu o Groq de vez na Fase 9/Bloco A
# (Task 17) -- validado manualmente contra a API real em todos os modos antes da remoção.
OPENAI_TEXT_MODEL = os.environ.get("OPENAI_TEXT_MODEL", "gpt-4o")


def validar_chunking_config(chunk_size_raw: Any, chunk_overlap_raw: Any) -> tuple[int, int]:
    """Valida e normaliza chunk_size e chunk_overlap garantindo:

    - chunk_size > 0
    - chunk_overlap >= 0
    - chunk_overlap < chunk_size
    """
    try:
        cs = int(chunk_size_raw)
    except (ValueError, TypeError):
        cs = 600
    if cs <= 0:
        cs = 600

    try:
        co = int(chunk_overlap_raw)
    except (ValueError, TypeError):
        co = 100
    if co < 0:
        co = 0
    if co >= cs:
        co = max(0, cs - 1)

    return cs, co


# Inicializa e valida parâmetros de chunking a partir do ambiente
_INIT_CHUNK_SIZE, _INIT_CHUNK_OVERLAP = validar_chunking_config(
    os.environ.get("RAG_CHUNK_SIZE", "600"),
    os.environ.get("RAG_CHUNK_OVERLAP", "100")
)

# ==============================================================================
# DICIONÁRIO DE CONFIGURAÇÃO CENTRALIZADA (RAG_CONFIG)
# ==============================================================================
RAG_CONFIG: Dict[str, Any] = {
    # Ingestão e Chunking
    "chunk_size": _INIT_CHUNK_SIZE,
    "chunk_overlap": _INIT_CHUNK_OVERLAP,
    "min_chunk_len": 40,
    "supported_extensions": ["pdf", "docx", "txt", "md", "csv", "xlsx", "xls", "pptx"],
    "max_csv_rows": int(os.environ.get("RAG_MAX_CSV_ROWS", "5000")),
    "max_excel_rows_per_sheet": int(os.environ.get("RAG_MAX_EXCEL_ROWS", "5000")),
    "max_excel_sheets": int(os.environ.get("RAG_MAX_EXCEL_SHEETS", "30")),
    "max_pptx_slides": int(os.environ.get("RAG_MAX_PPTX_SLIDES", "200")),
    "max_file_size_mb": int(os.environ.get("RAG_MAX_FILE_SIZE_MB", "50")),

    # Modelo de Embeddings
    "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",

    # Hiperparâmetros de Busca e Multi-Query
    "base_retrieval_top_k": int(os.environ.get("RAG_BASE_TOP_K", "30")),
    "per_query_top_k": int(os.environ.get("RAG_PER_QUERY_TOP_K", "15")),
    "max_expanded_queries": int(os.environ.get("RAG_MAX_EXPANDED_QUERIES", "3")),
    "max_decomposed_queries": int(os.environ.get("RAG_MAX_DECOMPOSED_QUERIES", "6")),
    "candidate_pool_size": int(os.environ.get("RAG_CANDIDATE_POOL_SIZE", "30")),
    "retrieval_candidate_pool_size": int(os.environ.get("RAG_RETRIEVAL_CANDIDATE_POOL_SIZE", os.environ.get("RAG_CANDIDATE_POOL_SIZE", "30"))),
    "final_context_top_k": int(os.environ.get("RAG_FINAL_TOP_K", "5")),

    # Thresholds de Relevância e Filtragem de Qualidade
    "similarity_threshold": float(os.environ.get("RAG_SIMILARITY_THRESHOLD", "0.20")),
    "min_rerank_score": float(os.environ.get("RAG_MIN_RERANK_SCORE", "0.20")),
    "relative_score_threshold": float(os.environ.get("RAG_RELATIVE_SCORE_THRESHOLD", "0.55")),
    "relevance_validation_min_score": float(os.environ.get("RAG_MIN_VALIDATION_SCORE", "0.18")),

    # Feature Flags Modulares
    "enable_conversational_query_rewriting": os.environ.get("RAG_ENABLE_CONVERSATIONAL_REWRITING", "True").lower() in ("true", "1", "yes"),
    "conversation_memory_max_turns": int(os.environ.get("RAG_CONVERSATION_MAX_TURNS", "10")),
    "conversation_entity_max_age_turns": int(os.environ.get("RAG_CONVERSATION_ENTITY_MAX_AGE", "5")),
    "conversation_min_resolution_confidence": float(os.environ.get("RAG_CONVERSATION_MIN_CONFIDENCE", "0.75")),
    "conversation_allow_ambiguous_resolution": os.environ.get("RAG_CONVERSATION_ALLOW_AMBIGUOUS", "False").lower() in ("true", "1", "yes"),
    "conversation_max_entities_per_turn": int(os.environ.get("RAG_CONVERSATION_MAX_ENTITIES", "20")),
    "conversation_max_set_entities": int(os.environ.get("RAG_CONVERSATION_MAX_SET_ENTITIES", "100")),
    "enable_tabular_query_engine": os.environ.get("RAG_ENABLE_TABULAR_QUERY_ENGINE", "True").lower() in ("true", "1", "yes"),
    "enable_bm25_hybrid": os.environ.get("RAG_ENABLE_BM25_HYBRID", "True").lower() in ("true", "1", "yes"),
    "bm25_candidate_pool": int(os.environ.get("RAG_BM25_CANDIDATE_POOL", "20")),
    "rrf_k": int(os.environ.get("RAG_RRF_K", "60")),
    "enable_entity_hop": os.environ.get("RAG_ENABLE_ENTITY_HOP", "True").lower() in ("true", "1", "yes"),
    "entity_hop_max_chunks": int(os.environ.get("RAG_ENTITY_HOP_MAX_CHUNKS", "2")),
    "max_tabular_rows_per_query": int(os.environ.get("RAG_MAX_TABULAR_ROWS", "10000")),
    "max_tabular_result_rows": int(os.environ.get("RAG_MAX_TABULAR_RESULT_ROWS", "50")),
    "enable_query_router": os.environ.get("RAG_ENABLE_QUERY_ROUTER", "True").lower() in ("true", "1", "yes"),
    "query_router_min_confidence": float(os.environ.get("RAG_QUERY_ROUTER_MIN_CONFIDENCE", "0.60")),
    "enable_source_aware_retrieval": os.environ.get("RAG_ENABLE_SOURCE_AWARE_RETRIEVAL", "True").lower() in ("true", "1", "yes"),
    "enable_tabular_first_routing": os.environ.get("RAG_ENABLE_TABULAR_FIRST_ROUTING", "True").lower() in ("true", "1", "yes"),
    "enable_markdown_anti_saturation": os.environ.get("RAG_ENABLE_MARKDOWN_ANTI_SATURATION", "True").lower() in ("true", "1", "yes"),
    "markdown_max_chunks_for_tabular_query": int(os.environ.get("RAG_MARKDOWN_MAX_CHUNKS_FOR_TABULAR", "1")),
    "enable_relational_join": os.environ.get("RAG_ENABLE_RELATIONAL_JOIN", "True").lower() in ("true", "1", "yes"),
    "enable_domain_aware_conversation": os.environ.get("RAG_ENABLE_DOMAIN_AWARE_CONVERSATION", "True").lower() in ("true", "1", "yes"),
    "enable_semantic_enrichment": os.environ.get("RAG_ENABLE_SEMANTIC_ENRICHMENT", "True").lower() in ("true", "1", "yes"),
    "enable_query_understanding": os.environ.get("RAG_ENABLE_UNDERSTANDING", "True").lower() in ("true", "1", "yes"),
    "enable_query_expansion": os.environ.get("RAG_ENABLE_EXPANSION", "True").lower() in ("true", "1", "yes"),
    "enable_query_decomposition": os.environ.get("RAG_ENABLE_DECOMPOSITION", "True").lower() in ("true", "1", "yes"),
    "enable_lexical_boost": os.environ.get("RAG_ENABLE_LEXICAL_BOOST", "True").lower() in ("true", "1", "yes"),
    "enable_reranking": os.environ.get("RAG_ENABLE_RERANKING", "True").lower() in ("true", "1", "yes"),
    "enable_diversity": os.environ.get("RAG_ENABLE_DIVERSITY", "True").lower() in ("true", "1", "yes"),
    "enable_llm_query_expansion": os.environ.get("RAG_ENABLE_LLM_EXPANSION", "False").lower() in ("true", "1", "yes"),

    # Classificação de metadados por palavra-chave, configurável por tenant (Fase 13, Task 3).
    # Generaliza o que antes era uma lista fixa de vocabulário têxtil hardcoded em
    # rag_manager._inferir_metadados_trecho (seção/produto/modelo/variante/material de UM
    # documento específico que não está mais na base). Formato:
    #   {"<campo_de_metadado>": {"<rótulo>": ["<termo>", ...], ...}, ...}
    # Cada campo é conferido contra o texto do chunk (case-insensitive); dentro de um campo, os
    # rótulos são testados na ordem declarada e o primeiro que casar vence. Default vazio: nenhum
    # tenant classifica metadado nenhum até configurar as próprias regras.
    "metadata_keyword_rules": {},

    # Injeção de texto sintético num chunk quando um campo de metadado (já classificado pelas
    # regras acima) bate com um rótulo configurado -- generaliza o que antes era a injeção fixa de
    # "PRODUTO: Camisa Jeans (...)" no chunker. Cada item:
    #   {"quando_metadado": {"campo": "variante", "rotulo": "Jeans"}, "texto_injetado": "...",
    #    "somente_se_ausente_termos": ["jeans"]}
    # Só injeta se NENHUM termo de "somente_se_ausente_termos" já aparecer no chunk (evita
    # duplicar informação que o texto já tem). Default vazio.
    "chunk_text_injection_rules": [],

    # Bônus/penalidade de alinhamento de variante no reranker (Fase 13, Task 3) -- generaliza o
    # que antes eram as regras hardcoded de contaminação cruzada jeans/M518 e masculino/feminino.
    # Cada regra define um "eixo" de variação mutuamente exclusiva do produto (tecido/lavagem,
    # gênero, etc.); quando a query menciona palavras-chave de exatamente 1 grupo do eixo, um
    # chunk alinhado com esse grupo ganha `bonus`, e um chunk alinhado com OUTRO grupo do mesmo
    # eixo perde `penalidade` (evita a contaminação cruzada entre variantes do mesmo produto).
    # Quando a query menciona 2+ grupos (comparação explícita), qualquer chunk alinhado com um dos
    # grupos mencionados ganha `bonus`, sem penalidade. Formato:
    #   [{"campo_metadado": "variante", "grupos": {"jeans": ["jeans","millie"], "m518": ["m518"]},
    #     "bonus": 0.25, "penalidade": 0.40}, ...]
    # Default vazio: nenhum tenant tem esse ajuste até configurar.
    "variant_alignment_rules": [],

    # Modo Debug e Observabilidade
    "debug": os.environ.get("RAG_DEBUG", "True").lower() in ("true", "1", "yes"),

    # Pesos Ponderados do Reranker Heurístico (Soma normalizada para ~1.0)
    "weights": {
        "vector": 0.40,      # Similaridade vetorial de cosseno
        "lexical": 0.35,     # Correspondência exata, n-grams, códigos técnicos e medidas
        "frequency": 0.15,   # Bônus para chunks resgatados por múltiplas formulações de query
        "metadata": 0.10,    # Alinhamento de variante/produto/seção
    },

    # Pesos específicos de bônus lexical
    "lexical_weights": {
        "technical_code": 0.20,      # Códigos como M518, CF-2026, etc.
        "number_unit": 0.15,         # Números com unidades (128 g/m², 4.5 oz, 172 cm)
        "domain_keyword": 0.12,      # Palavras do domínio têxtil/vestuário/IA
        "exact_phrase": 0.25,        # Casamento exato da frase da query
        "ngram_overlap": 0.15,       # Sobreposição de bi-grams e tri-grams
    },

    # Parâmetros de Diversidade (MMR / Penalidade de Redundância)
    "diversity": {
        "max_similarity_between_chunks": 0.85,  # Similaridade máxima de Jaccard permitida entre chunks
        "entity_balance_weight": 0.30,          # Força a inclusão de entidades secundárias em comparações
        "concept_coverage_weight": 0.25,        # Garante representatividade de sub-conceitos
    }
}


def obter_rag_config() -> Dict[str, Any]:
    """Retorna uma cópia do dicionário de configurações ativas do RAG."""
    return dict(RAG_CONFIG)


def atualizar_rag_config(novos_valores: Dict[str, Any]) -> None:
    """Atualiza dinamicamente parâmetros da configuração centralizada do RAG com validação."""
    dados_validados = dict(novos_valores)
    if "chunk_size" in dados_validados or "chunk_overlap" in dados_validados:
        cs = dados_validados.get("chunk_size", RAG_CONFIG.get("chunk_size", 600))
        co = dados_validados.get("chunk_overlap", RAG_CONFIG.get("chunk_overlap", 100))
        cs_val, co_val = validar_chunking_config(cs, co)
        dados_validados["chunk_size"] = cs_val
        dados_validados["chunk_overlap"] = co_val

    RAG_CONFIG.update(dados_validados)
