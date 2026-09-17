# -*- coding: utf-8 -*-
"""Módulo avançado de ingestão, indexação e recuperação semântica e híbrida (RAG)

para o Senai LabFashion IA.

Principais capacidades:
- Extração estruturada por página com pypdf.
- Chunking semântico respeitando unidades lógicas de fichas técnicas, tabelas e especificações.
- Metadados ricos por chunk: fonte, página, seção, produto, modelo, variante, material.
- Embeddings normalizados com 'paraphrase-multilingual-MiniLM-L12-v2' via sentence-transformers.
- Armazenamento embutido e isolado por tenant no ChromaDB (PersistentClient).
- Busca híbrida (vetorial + lexical boosting de códigos/números/unidades).
- Suporte a consultas comparativas (multi-query por entidades com fusão e deduplicação).
- Prevenção de contaminação cruzada de especificações entre variantes de produto.
- Reranking inteligente e threshold configurável.
- Observabilidade e log de debug detalhado.
"""

import os
import io
import re
import math
import hashlib
import shutil
import sqlite3
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Union, Tuple, Set

import chromadb
from pypdf import PdfReader
from logger_config import obter_logger
import conversational_query

# Fallback gracioso para st.cache_resource caso o Streamlit esteja ativo
try:
    import streamlit as st
    cache_resource_decorator = st.cache_resource
except Exception:
    def cache_resource_decorator(func):
        cache = {}
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]
        return wrapper

__all__ = [
    "extrair_documento",
    "EXTENSOES_SUPORTADAS",
    "SUPPORTED_EXTENSIONS",
    "extrair_paginas_pdf",
    "extrair_texto_pdf",
    "dividir_pagina_em_chunks",
    "indexar_documento",
    "buscar_contexto_relevante",
    "listar_documentos_indexados",
    "remover_documento",
    "obter_modelo_embeddings",
    "gerar_embeddings_normalizados",
    "obter_cliente_chroma",
    "formatar_bloco_debug_rag",
    "obter_ultimo_rag_debug",
    "RAG_DEBUG",
    "RAG_SIMILARITY_THRESHOLD",
]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES CENTRAIS DO PIPELINE RAG
# ─────────────────────────────────────────────────────────────────────────────
from rag_config import RAG_CONFIG, obter_rag_config, atualizar_rag_config
from document_extractors import (
    extrair_documento,
    extrair_documento_com_dados_tabulares,
    EXTENSOES_SUPORTADAS,
    SUPPORTED_EXTENSIONS,
    extrair_documento_pdf,
    obter_extensao_normalizada
)
from tabular_storage import (
    TabularDocument,
    TabularSheet,
    TabularRow,
    salvar_documento_tabular,
    carregar_documento_tabular,
    carregar_documentos_tabulares,
    remover_documento_tabular,
    remover_tenant_tabular
)
from tabular_query_engine import (
    TabularIntent,
    TabularQueryPlan,
    TabularQueryResult,
    detectar_e_planejar_consulta_tabular,
    executar_consulta_tabular
)
from query_router import (
    QueryRouter,
    RouteType,
    QueryRoute
)
from query_engine import (
    QueryCategory,
    QueryAnalysis,
    analisar_query_completa,
    classificar_query,
    expandir_query,
    decompor_query,
    normalizar_texto
)
from reranker import (
    CandidateChunk,
    fundir_e_deduplicar_candidatos,
    calcular_score_lexical,
    BaseReranker,
    HeuristicReranker,
    selecionar_com_cobertura_e_diversidade
)

RAG_DEBUG: bool = RAG_CONFIG.get("debug", True)
RAG_SIMILARITY_THRESHOLD: float = RAG_CONFIG.get("similarity_threshold", 0.20)
COLLECTION_VERSION: str = "v3"  # v3 (Fase 13, Task 1): bump forçado pela troca de hnsw:space l2 -> cosine
DEFAULT_INITIAL_TOP_K: int = RAG_CONFIG.get("base_retrieval_top_k", 10)
FINAL_RERANK_K: int = RAG_CONFIG.get("final_context_top_k", 5)

# Instância padrão do reranker heurístico desacoplado
_DEFAULT_RERANKER: BaseReranker = HeuristicReranker()

# Armazena o último relatório de debug gerado para inspeção
_ULTIMO_RAG_DEBUG: Dict[str, Any] = {}

def obter_ultimo_rag_debug() -> Dict[str, Any]:
    """Retorna o relatório estruturado de debug do último retrieval executado."""
    return dict(_ULTIMO_RAG_DEBUG)


def formatar_bloco_debug_rag(debug_info: Optional[Dict[str, Any]] = None) -> str:
    """Formata o relatório de debug RAG em formato textual padronizado para logs ou UI."""
    info = debug_info or _ULTIMO_RAG_DEBUG
    if not info:
        return "Nenhum dado de debug RAG disponível."

    linhas = [
        "================================================",
        "RAG DEBUG - OBSERVABILIDADE",
        "================================================",
        "==============================",
        "QUERY ORIGINAL",
        "==============================",
        f"{info.get('question', '')}\n",
        f"CATEGORIAS INFERIDAS: {' / '.join(info.get('query_type', []))}\n",
        "==============================",
        "BUSCA INICIAL (MULTI-QUERY / CANDIDATE POOL)",
        "=============================="
    ]
    
    ret_res = info.get("retrieval_results", {})
    total_solicitados = info.get("candidatos_solicitados", 0)
    total_encontrados = info.get("candidatos_encontrados_inicial", 0)
    linhas.append(f"Candidatos solicitados por query: {total_solicitados}")
    linhas.append(f"Total de candidatos encontrados no pool inicial: {total_encontrados}")
    
    for query, cands in ret_res.items():
        linhas.append(f"\nQuery Sub-busca:\n'{query}' ({len(cands)} candidatos)")
        for idx, c in enumerate(cands[:4], 1):
            txt_prev = (c.get('texto') or '').replace('\n', ' ')[:90]
            linhas.append(
                f"  [{idx}] {c.get('fonte')} ({c.get('rotulo_unidade', 'Pág ' + str(c.get('pagina', 1)))}) | "
                f"tipo={c.get('tipo_arquivo', 'pdf')} | dist={c.get('distancia', 0):.4f} | "
                f"cos_sim={c.get('score', 0):.4f}\n"
                f"       Preview: {txt_prev}..."
            )

    linhas.append("\n==============================")
    linhas.append("ANTES DO RERANKING")
    linhas.append("==============================")
    linhas.append(f"Quantidade de candidatos únicos no pool: {info.get('pool_antes_rerank_count', 0)}")

    linhas.append("\n==============================")
    linhas.append("APÓS RERANKING & AVALIAÇÃO DE QUALIDADE")
    linhas.append("==============================")
    for idx, c in enumerate(info.get("all_ranked_candidates", []), 1):
        det = c.get("detalhes_score", {})
        relevante_str = "SIM" if c.get("is_relevant", True) else "NÃO"
        motivo_str = f" | Motivo: {c.get('discard_reason')}" if c.get("discard_reason") else ""
        txt_prev = (c.get('texto') or '').replace('\n', ' ')[:80]
        linhas.append(
            f"  [{idx}] {c.get('fonte')} ({c.get('rotulo_unidade', 'Pág ' + str(c.get('pagina', 1)))})\n"
            f"       Rerank Score: {c.get('score', 0):.4f} (vec={det.get('vector', 0):.4f}, lex={det.get('lexical', 0):.4f}, freq={det.get('frequency', 0):.4f})\n"
            f"       Relevante: {relevante_str}{motivo_str}\n"
            f"       Preview: {txt_prev}..."
        )

    linhas.append("\n==============================")
    linhas.append("SELEÇÃO FINAL DE CONTEXTO")
    linhas.append("==============================")
    fc = info.get("final_context", {})
    linhas.append(f"Final context chunks: {fc.get('quantidade_chunks', 0)}")
    for idx, c in enumerate(info.get("final_reranking", []), 1):
        txt_prev = (c.get('texto') or '').replace('\n', ' ')[:90]
        linhas.append(
            f"  [{idx}] SCORE={c.get('score', 0):.4f} | {c.get('fonte')} ({c.get('rotulo_unidade', 'Pág ' + str(c.get('pagina', 1)))})\n"
            f"       Preview: {txt_prev}..."
        )

    if info.get("tabular_query_debug"):
        tab_dbg = info["tabular_query_debug"]
        plano = tab_dbg.get("plano", {})
        res = tab_dbg.get("resultado", {})
        linhas.append("\n==============================")
        linhas.append("TABULAR QUERY DEBUG (PRIORIDADE 3)")
        linhas.append("==============================")
        linhas.append(f"Intent: {plano.get('intent')}")
        linhas.append(f"Confiança: {plano.get('confidence', 0.0):.2f}")
        linhas.append(f"Documento Selecionado: {plano.get('target_document')}")
        linhas.append(f"Aba Selecionada: {plano.get('target_sheet')}")
        linhas.append(f"Razão da Seleção: {plano.get('selection_reason', '')}")
        linhas.append(f"Linhas Escaneadas: {res.get('rows_scanned', 0)} | Linhas Casadas: {res.get('rows_matched', 0)}")
        linhas.append(f"Colunas Utilizadas: {', '.join(res.get('columns_used', []))}")
        linhas.append(f"Fallback Vetorial: {'SIM' if tab_dbg.get('fallback_vetorial') else 'NÃO'}")

    if info.get("conversational_query_debug"):
        conv_dbg = info["conversational_query_debug"]
        linhas.append("\n==============================")
        linhas.append("CONVERSATIONAL QUERY DEBUG (PRIORIDADE 4)")
        linhas.append("==============================")
        linhas.append(f"Query Original: {conv_dbg.get('original_query')}")
        linhas.append(f"Query Reescrita: {conv_dbg.get('rewritten_query')}")
        linhas.append(f"Dependência Detectada: {'SIM' if conv_dbg.get('requires_context') else 'NÃO'}")
        linhas.append(f"Tipo de Dependência: {conv_dbg.get('dependency_type')}")
        linhas.append(f"Contexto Resolvido: {'SIM' if conv_dbg.get('context_resolved') else 'NÃO'}")
        linhas.append(f"Entidades Utilizadas: {', '.join(conv_dbg.get('entities_used', []))}")
        linhas.append(f"Confiança da Reescrita: {conv_dbg.get('rewrite_confidence', 0.0):.2f}")
        if conv_dbg.get("fallback_reason"):
            linhas.append(f"Razão de Fallback: {conv_dbg.get('fallback_reason')}")

    linhas.append("\n==============================")
    linhas.append("CONTEXTO ENVIADO AO LLM (RESUMO SEGURO)")
    linhas.append("==============================")
    linhas.append(f"Total de caracteres: {fc.get('caracteres', 0)}")
    linhas.append(f"Fontes utilizadas: {', '.join(fc.get('fontes', []))}")
    linhas.append("================================================")
    return "\n".join(linhas)

# Cache global de clientes ChromaDB por tenant
_CHROMA_CLIENTS: Dict[str, chromadb.PersistentClient] = {}


# ─────────────────────────────────────────────────────────────────────────────
# GESTÃO DE CLIENTES E COLEÇÕES CHROMADB
# ─────────────────────────────────────────────────────────────────────────────
def _obter_caminho_chroma(tenant_id: str) -> str:
    """Retorna o caminho físico do diretório ChromaDB para o tenant especificado."""
    tenant_seguro = "".join(c for c in tenant_id if c.isalnum() or c in ("_", "-")).strip() or "default"
    return os.path.join("tenant_data", "chroma", tenant_seguro)


def obter_cliente_chroma(tenant_id: str) -> chromadb.PersistentClient:
    """Inicializa ou reutiliza um cliente ChromaDB persistente com armazenamento isolado por tenant."""
    caminho_tenant = _obter_caminho_chroma(tenant_id)
    if tenant_id not in _CHROMA_CLIENTS:
        try:
            os.makedirs(caminho_tenant, exist_ok=True)
            client = chromadb.PersistentClient(path=caminho_tenant)
            _CHROMA_CLIENTS[tenant_id] = client
        except Exception as e:
            logger = obter_logger(tenant_id)
            logger.error(f"Erro ao inicializar cliente ChromaDB para tenant '{tenant_id}' em '{caminho_tenant}': {e}", exc_info=True)
            raise
    return _CHROMA_CLIENTS[tenant_id]


def _obter_colecao_tenant(tenant_id: str):
    """Retorna a coleção ChromaDB versionada específica do tenant.

    `hnsw:space="cosine"` é declarado explicitamente na criação -- sem isso, o Chroma usa `l2`
    por padrão silencioso, que devolve distância euclidiana ao quadrado (`d² = 2 - 2·cos`), não
    diretamente utilizável como similaridade. Com cosine, `distancia_chroma = 1 - cos_sim`: a
    conversão em `reranker.fundir_e_deduplicar_candidatos` fica `cos_sim = 1 - dist`, sem
    elevar nada ao quadrado (Fase 13, Task 1).

    O Chroma não permite mudar o `space` de uma coleção já criada -- por isso o bump de
    `COLLECTION_VERSION` para "v3": garante que nenhum tenant reutilize, sem querer, uma coleção
    antiga criada sob `l2`, o que faria as distâncias devolvidas parecerem certas mas estarem na
    escala errada, silenciosamente.
    """
    client = obter_cliente_chroma(tenant_id)
    nome_colecao = f"docs_{COLLECTION_VERSION}_{tenant_id}"
    return client.get_or_create_collection(name=nome_colecao, metadata={"hnsw:space": "cosine"})


def limpar_indices_orfaos(tenant_id: str) -> Dict[str, Any]:
    """Remove collections não-canônicas e pastas de segmento órfãs do armazenamento do tenant.

    A única collection considerada válida para o tenant é `docs_{COLLECTION_VERSION}_{tenant_id}`.
    Qualquer outra collection registrada no mesmo armazenamento físico (ex.: leftovers de
    scripts de benchmark que reutilizaram o cliente ChromaDB do tenant para criar collections
    com nomes arbitrários) é removida via `client.delete_collection()`. Em seguida, pastas de
    segmento no disco sem nenhuma linha correspondente em `segments` (resíduo de reindexações
    ou collections antigas já deletadas) são removidas diretamente.

    Não é chamada automaticamente em nenhum fluxo do app — deve ser executada manualmente,
    sob supervisão, para higienizar o armazenamento de um tenant específico.
    """
    logger = obter_logger(tenant_id)
    client = obter_cliente_chroma(tenant_id)
    caminho_tenant = _obter_caminho_chroma(tenant_id)
    nome_canonico = f"docs_{COLLECTION_VERSION}_{tenant_id}"

    colecoes_removidas: List[str] = []
    for colecao in client.list_collections():
        nome = getattr(colecao, "name", colecao)
        if nome != nome_canonico:
            client.delete_collection(name=nome)
            colecoes_removidas.append(nome)
            logger.info(f"Collection não-canônica removida do tenant '{tenant_id}': {nome}")

    ids_segmentos_ativos: Set[str] = set()
    caminho_sqlite = os.path.join(caminho_tenant, "chroma.sqlite3")
    if os.path.exists(caminho_sqlite):
        conexao = sqlite3.connect(caminho_sqlite)
        try:
            ids_segmentos_ativos = {row[0] for row in conexao.execute("SELECT id FROM segments").fetchall()}
        finally:
            conexao.close()

    pastas_removidas: List[str] = []
    if os.path.isdir(caminho_tenant):
        for nome_pasta in os.listdir(caminho_tenant):
            caminho_pasta = os.path.join(caminho_tenant, nome_pasta)
            if os.path.isdir(caminho_pasta) and nome_pasta not in ids_segmentos_ativos:
                shutil.rmtree(caminho_pasta, ignore_errors=True)
                pastas_removidas.append(nome_pasta)
                logger.info(f"Pasta de índice órfã removida do tenant '{tenant_id}': {nome_pasta}")

    return {"colecoes_removidas": colecoes_removidas, "pastas_removidas": pastas_removidas}


# ─────────────────────────────────────────────────────────────────────────────
# MODELO DE EMBEDDINGS LOCAL (NORMALIZADO)
# ─────────────────────────────────────────────────────────────────────────────
@cache_resource_decorator
def _carregar_modelo_sentence_transformer():
    """Carrega o modelo de embeddings multilíngue local com cache de longa duração."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


def obter_modelo_embeddings():
    """Retorna a instância do modelo de embeddings paraphrase-multilingual-MiniLM-L12-v2."""
    try:
        return _carregar_modelo_sentence_transformer()
    except Exception as e:
        logger = obter_logger()
        logger.error(f"Erro ao carregar modelo de embeddings local: {e}", exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# GARANTIA DE JANELA DE TOKENS DO MODELO DE EMBEDDINGS (Fase 13, Task 2)
#
# `chunk_size` (rag_config.py) é um orçamento em CARACTERES -- útil para decidir onde quebrar um
# bloco de texto, mas não é uma garantia de que o resultado cabe na janela de TOKENS do modelo de
# embeddings (128 tokens para o MiniLM atual). Português técnico roda ~3,3-4,3 caracteres por
# token dependendo do texto -- qualquer limite fixo de caracteres é uma aposta calibrada, não uma
# garantia. O sentence-transformers trunca silenciosamente o que exceder `max_seq_length` no
# forward (sem erro, sem aviso): a cauda de um chunk cheio simplesmente nunca é embeddada, embora
# apareça inteira no texto enviado ao LLM -- uma discrepância entre "o que foi buscado" e "o que
# foi mostrado" que não aparece em nenhum log.
#
# A correção aqui mede o tamanho real via o tokenizer do próprio modelo (não estima por
# caracteres) e, só quando um chunk de fato excede a janela, o bisseca recursivamente até caber --
# preservando os metadados originais em cada metade. Roda uma vez por documento indexado, depois
# que a reconstrução do storage tabular (que precisa dos chunks originais e inteiros) já rodou.
# ─────────────────────────────────────────────────────────────────────────────
def _limite_de_tokens_do_modelo(modelo) -> int:
    return int(getattr(modelo, "max_seq_length", None) or 128)


def _contar_tokens_em_lote(modelo, textos: List[str]) -> List[int]:
    if not textos:
        return []
    codificado = modelo.tokenizer(list(textos), add_special_tokens=True)
    return [len(ids) for ids in codificado["input_ids"]]


def _bissectar_chunk_por_tokens(chunk: Dict[str, Any], modelo, limite: int) -> List[Dict[str, Any]]:
    """Divide um chunk ao meio (por caracteres, no espaço mais próximo do centro) até que cada
    metade caiba na janela de tokens do modelo -- recursivo, preserva todo metadado original em
    cada metade (só `texto` muda)."""
    texto = chunk.get("texto", "")
    n_tokens = _contar_tokens_em_lote(modelo, [texto])[0]
    if n_tokens <= limite:
        return [chunk]

    meio = len(texto) // 2
    ponto_quebra = texto.rfind(" ", 0, meio)
    if ponto_quebra <= 0:
        ponto_quebra = meio  # sem espaço antes do meio (palavra/token gigante) -- corta bruto

    metade_a = texto[:ponto_quebra].strip()
    metade_b = texto[ponto_quebra:].strip()
    if not metade_a or not metade_b:
        metade_a, metade_b = texto[:meio].strip(), texto[meio:].strip()
    if not metade_a or not metade_b:
        # Texto vazio ou só espaços de um lado -- não há como bissectar mais; devolve como está
        # em vez de entrar em recursão infinita sobre uma string que não encolhe.
        return [chunk]

    partes: List[Dict[str, Any]] = []
    for metade in (metade_a, metade_b):
        partes.extend(_bissectar_chunk_por_tokens({**chunk, "texto": metade}, modelo, limite))
    return partes


def _garantir_limite_de_tokens(chunks_estruturados: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Verifica todos os chunks contra a janela real de tokens do modelo ativo e bisseca só os
    que excedem. A maioria dos chunks (curtos) passa pela checagem em lote sem custo extra."""
    if not chunks_estruturados:
        return chunks_estruturados

    modelo = obter_modelo_embeddings()
    limite = _limite_de_tokens_do_modelo(modelo)
    contagens = _contar_tokens_em_lote(modelo, [c.get("texto", "") for c in chunks_estruturados])

    resultado: List[Dict[str, Any]] = []
    excedentes = 0
    for chunk, n_tokens in zip(chunks_estruturados, contagens):
        if n_tokens <= limite:
            resultado.append(chunk)
        else:
            excedentes += 1
            resultado.extend(_bissectar_chunk_por_tokens(chunk, modelo, limite))

    if excedentes:
        obter_logger().warning(
            f"{excedentes} chunk(s) excediam a janela de {limite} tokens do modelo de embeddings "
            f"e foram divididos antes da indexação."
        )
    return resultado


def gerar_embeddings_normalizados(textos: List[str]) -> List[List[float]]:
    """Gera embeddings normalizados (L2 normalized) para textos garantindo equivalência de cosseno."""
    if not textos:
        return []
    modelo = obter_modelo_embeddings()
    embeddings = modelo.encode(textos, normalize_embeddings=True)
    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return [list(emb) for emb in embeddings]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE PDF POR PÁGINA
# ─────────────────────────────────────────────────────────────────────────────
def extrair_paginas_pdf(arquivo: Union[io.BytesIO, bytes, str, Any]) -> List[Dict[str, Any]]:
    """Extrai o conteúdo de um PDF mantendo estritamente a separação e numeração por página.

    Retorna: List[Dict[str, Any]] onde cada item contém:
    {"pagina": int, "texto": str}
    """
    logger = obter_logger()
    try:
        if isinstance(arquivo, bytes):
            stream = io.BytesIO(arquivo)
            reader = PdfReader(stream)
        elif isinstance(arquivo, str):
            reader = PdfReader(arquivo)
        elif hasattr(arquivo, "read"):
            if hasattr(arquivo, "seek"):
                arquivo.seek(0)
            reader = PdfReader(arquivo)
        else:
            raise ValueError(f"Tipo de arquivo não suportado para extração de PDF: {type(arquivo)}")

        paginas_extraidas: List[Dict[str, Any]] = []
        for i, pagina in enumerate(reader.pages, start=1):
            try:
                texto_pag = pagina.extract_text() or ""
                # Normaliza espaços mantendo quebras de linha estruturais
                linhas_limpas = [l.rstrip() for l in texto_pag.splitlines()]
                texto_limpo = "\n".join(linhas_limpas).strip()
                if texto_limpo:
                    paginas_extraidas.append({
                        "pagina": i,
                        "texto": texto_limpo
                    })
            except Exception as pag_err:
                logger.warning(f"Aviso ao extrair página {i} do PDF: {pag_err}")

        return paginas_extraidas
    except Exception as e:
        logger.error(f"Falha na extração de páginas do arquivo PDF: {e}", exc_info=True)
        raise


def extrair_texto_pdf(arquivo: Union[io.BytesIO, bytes, str, Any]) -> str:
    """Função pública de extração compatível com a interface original.

    Preserva a estrutura de páginas através de marcadores explícitos:
    '--- [PÁGINA X] ---'
    """
    paginas = extrair_paginas_pdf(arquivo)
    blocos = []
    for p in paginas:
        blocos.append(f"--- [PÁGINA {p['pagina']}] ---\n{p['texto']}")
    return "\n\n".join(blocos).strip()


# ─────────────────────────────────────────────────────────────────────────────
# INFERÊNCIA DE METADADOS TÉCNICOS
# ─────────────────────────────────────────────────────────────────────────────
def _inferir_metadados_trecho(texto: str) -> Dict[str, str]:
    """Classifica metadados do chunk (seção/produto/modelo/variante/material/...) por
    palavras-chave configuráveis por tenant (`RAG_CONFIG["metadata_keyword_rules"]`, Fase 13,
    Task 3).

    Generaliza o que antes era uma lista fixa de vocabulário têxtil hardcoded aqui (seção,
    produto, modelo, variante Jeans/M518/Tradicional de um documento específico que não está mais
    na base) -- sem configuração (default), nenhuma classificação acontece: um chunk sem metadado
    nenhum não é um bug, é o estado esperado até um tenant configurar suas próprias regras.

    Para cada campo, os rótulos são testados na ordem declarada no dict de configuração (que
    preserva ordem de inserção) e o primeiro que casar vence -- equivalente ao encadeamento
    if/elif que existia aqui antes, só que dirigido por dado em vez de código.
    """
    meta: Dict[str, str] = {}
    texto_upper = texto.upper()
    regras = RAG_CONFIG.get("metadata_keyword_rules") or {}

    for campo, grupos in regras.items():
        for rotulo, termos in grupos.items():
            if any(termo.upper() in texto_upper for termo in termos):
                meta[campo] = rotulo
                break

    return meta


def _aplicar_injecoes_de_texto(texto_chunk: str, meta: Dict[str, str]) -> str:
    """Prepende texto sintético a um chunk quando um metadado já classificado bate com uma regra
    configurada (`RAG_CONFIG["chunk_text_injection_rules"]`, Fase 13, Task 3).

    Generaliza o que antes era a injeção fixa de "PRODUTO: Camisa Jeans (...)" no chunker: útil
    quando o texto de um sub-bloco menciona uma variante (ex: um material de tecido específico)
    sem literalmente conter o termo pelo qual os usuários costumam buscá-la (ex: "jeans") -- sem
    isso, uma busca por esse termo nunca encontraria o sub-bloco. Default vazio: nenhuma injeção
    até um tenant configurar.
    """
    regras = RAG_CONFIG.get("chunk_text_injection_rules") or []
    texto_upper = texto_chunk.upper()

    for regra in regras:
        condicao = regra.get("quando_metadado") or {}
        campo, rotulo = condicao.get("campo"), condicao.get("rotulo")
        if not campo or meta.get(campo) != rotulo:
            continue

        termos_ausentes = regra.get("somente_se_ausente_termos") or []
        if any(termo.upper() in texto_upper for termo in termos_ausentes):
            continue  # o chunk já menciona o termo -- nada a esclarecer

        texto_injetado = regra.get("texto_injetado", "")
        if texto_injetado:
            texto_chunk = f"{texto_injetado}\n{texto_chunk}"
            texto_upper = texto_chunk.upper()

    return texto_chunk


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CHUNKING SEMÂNTICO E ESTRUTURAL
# ─────────────────────────────────────────────────────────────────────────────
def _dividir_texto_longo_recursivo(
    texto: str,
    tamanho_max: int = 500,
    sobreposicao: int = 80
) -> List[str]:
    """Divide textos longos respeitando hierarquia semântica e limites estritos de tamanho.

    Garante que nenhum chunk exceda tamanho_max (mesmo após sobreposição) e evita loops infinitos.
    Tenta divisões em:
    1. Parágrafos duplos (\n\n)
    2. Linhas simples (\n)
    3. Finais de frase (pontuação seguida de espaço)
    4. Pontuações intermediárias (, ;)
    5. Espaços entre palavras
    6. Fatiamento por caracteres caso indivisível.
    """
    if not texto or not texto.strip():
        return []

    # Sanitização e validação estrita de limites
    tamanho_max = max(1, int(tamanho_max))
    sobreposicao = max(0, min(int(sobreposicao), max(0, tamanho_max - 1)))

    txt_limpo = texto.strip()
    if len(txt_limpo) <= tamanho_max:
        return [txt_limpo]

    separadores = [
        "\n\n",
        "\n",
        r'(?<=[.!?])\s+',
        r'(?<=[,;])\s+',
        r'\s+'
    ]

    def _split_passo(txt: str, sep_idx: int) -> List[str]:
        txt_s = txt.strip()
        if not txt_s:
            return []
        if len(txt_s) <= tamanho_max:
            return [txt_s]

        if sep_idx >= len(separadores):
            # Último recurso: fatiamento rígido por caracteres/espaços garantindo avanço
            blocos = []
            inicio = 0
            passo_minimo = max(1, tamanho_max - sobreposicao)
            while inicio < len(txt_s):
                fim = min(len(txt_s), inicio + tamanho_max)
                if fim < len(txt_s):
                    pos_espaco = txt_s.rfind(" ", inicio, fim)
                    if pos_espaco > inicio + (tamanho_max // 3):
                        fim = pos_espaco
                bloco = txt_s[inicio:fim].strip()
                if bloco:
                    blocos.append(bloco)
                if fim >= len(txt_s):
                    break
                novo_inicio = max(inicio + 1, fim - sobreposicao)
                if novo_inicio <= inicio:
                    novo_inicio = inicio + passo_minimo
                inicio = novo_inicio
            return [b for b in blocos if b and len(b) <= tamanho_max]

        sep = separadores[sep_idx]
        if sep.startswith(r'(?<='):
            partes = re.split(sep, txt_s)
        else:
            partes = txt_s.split(sep)

        if len(partes) <= 1:
            return _split_passo(txt_s, sep_idx + 1)

        resultado: List[str] = []
        buffer_atual: List[str] = []
        tamanho_buffer = 0
        delimitador_join = "\n" if sep in ("\n", "\n\n") else " "

        for p in partes:
            p_limpo = p.strip()
            if not p_limpo:
                continue

            if len(p_limpo) > tamanho_max:
                if buffer_atual:
                    bloco_montado = delimitador_join.join(buffer_atual).strip()
                    if bloco_montado:
                        resultado.append(bloco_montado)
                    buffer_atual = []
                    tamanho_buffer = 0
                sub_pedacos = _split_passo(p_limpo, sep_idx + 1)
                resultado.extend(sub_pedacos)
                continue

            comp_adicional = len(p_limpo) + (len(delimitador_join) if buffer_atual else 0)
            if tamanho_buffer + comp_adicional <= tamanho_max:
                buffer_atual.append(p_limpo)
                tamanho_buffer += comp_adicional
            else:
                if buffer_atual:
                    bloco_montado = delimitador_join.join(buffer_atual).strip()
                    if bloco_montado:
                        resultado.append(bloco_montado)

                    # Calcula overlap sem estourar tamanho_max com o próximo item
                    if sobreposicao > 0:
                        buffer_overlap: List[str] = []
                        tam_overlap = 0
                        for item_rec in reversed(buffer_atual):
                            tam_item = len(item_rec) + (len(delimitador_join) if buffer_overlap else 0)
                            if tam_overlap + tam_item <= sobreposicao:
                                buffer_overlap.insert(0, item_rec)
                                tam_overlap += tam_item
                            else:
                                break
                        # Verifica se cabe com o novo p_limpo
                        if tam_overlap + len(delimitador_join) + len(p_limpo) <= tamanho_max:
                            buffer_atual = buffer_overlap
                            tamanho_buffer = sum(len(x) for x in buffer_atual) + (len(delimitador_join) * max(0, len(buffer_atual) - 1))
                        else:
                            buffer_atual = []
                            tamanho_buffer = 0
                    else:
                        buffer_atual = []
                        tamanho_buffer = 0

                buffer_atual.append(p_limpo)
                tamanho_buffer += len(p_limpo) + (len(delimitador_join) if len(buffer_atual) > 1 else 0)

        if buffer_atual:
            bloco_montado = delimitador_join.join(buffer_atual).strip()
            if bloco_montado:
                resultado.append(bloco_montado)

        return resultado

    chunks_brutos = _split_passo(txt_limpo, 0)
    return [c for c in chunks_brutos if c.strip()]


def dividir_pagina_em_chunks(
    pagina_num: int,
    texto_pagina: str,
    tamanho_chunk: int = 450,
    sobreposicao: int = 70,
    metadados_base: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Divide o texto de uma única unidade/página em chunks semânticos.

    Preserva a integridade de blocos técnicos (têxteis/vestuário), tabelas e fichas técnicas.
    Aplica fallback recursivo para textos longos garantindo que nenhum bloco exceda o tamanho limite.
    """
    if not texto_pagina or not texto_pagina.strip():
        return []

    tamanho_chunk = max(1, int(tamanho_chunk))
    sobreposicao = max(0, min(int(sobreposicao), max(0, tamanho_chunk - 1)))
    base_meta = dict(metadados_base or {})
    txt_pag_limpo = texto_pagina.strip()

    # Páginas/unidades curtas e coesas mantêm-se inteiras respeitando tamanho_chunk
    cont_desc = len(re.findall(r'DESCRI[ÇC][ÕO]ES\s+T[ÉE]CNICAS', txt_pag_limpo, re.IGNORECASE))
    if cont_desc <= 1 and len(txt_pag_limpo) <= tamanho_chunk:
        meta = _inferir_metadados_trecho(txt_pag_limpo)
        chunk_dict = {
            "texto": txt_pag_limpo,
            "pagina": pagina_num,
            **base_meta,
            **meta
        }
        return [chunk_dict]

    # Cabeçalho de contexto: repete a primeira linha da página nos sub-blocos que não a
    # carregam, para um bloco no meio da página não ficar sem o título que o identifica (Fase 13,
    # Task 3 -- antes disparava só para uma lista fixa de palavras-chave de um documento
    # específico; título é heurística de forma, não de vocabulário, então funciona para qualquer
    # documento: curto o bastante para parecer um título, sem terminar em pontuação de frase).
    linhas = [l.strip() for l in txt_pag_limpo.splitlines() if l.strip()]
    cabecalho_contexto = ""
    if linhas and 0 < len(linhas[0]) <= 80 and not linhas[0].endswith((".", ";", ",")):
        cabecalho_contexto = linhas[0]

    # Padrão para separar blocos técnicos independentes na mesma página
    padrao_quebra = re.compile(
        r'(?=(?:DESCRIÇÕES\s+TÉCNICAS:|Tabela\s+\d+:|GRADE\s+DE\s+TAMANHOS|ETIQUETA\s+DE\s+COMPOSIÇÃO))',
        re.IGNORECASE
    )

    partes = [p.strip() for p in padrao_quebra.split(txt_pag_limpo) if p.strip()]
    if not partes:
        partes = [txt_pag_limpo]

    chunks: List[Dict[str, Any]] = []
    meta_pag = _inferir_metadados_trecho(txt_pag_limpo)

    for p in partes:
        texto_chunk = p

        # Enriquece sub-blocos com texto sintético configurado por tenant (Fase 13, Task 3),
        # baseado no metadado já classificado pelas regras de RAG_CONFIG -- generaliza a injeção
        # fixa que existia aqui antes; default vazio não altera o texto.
        meta_bloco = _inferir_metadados_trecho(texto_chunk)
        texto_chunk = _aplicar_injecoes_de_texto(texto_chunk, meta_bloco)

        if cabecalho_contexto and cabecalho_contexto.upper() not in texto_chunk.upper() and len(texto_chunk) > 30:
            texto_chunk = f"[{cabecalho_contexto}]\n{texto_chunk}"

        # Se o bloco exceder o tamanho máximo de chunk, aplica fallback semântico recursivo
        if len(texto_chunk) > tamanho_chunk:
            sub_textos = _dividir_texto_longo_recursivo(texto_chunk, tamanho_max=tamanho_chunk, sobreposicao=sobreposicao)
        else:
            sub_textos = [texto_chunk]

        for stxt in sub_textos:
            meta = _inferir_metadados_trecho(stxt)
            meta_completo = {**base_meta, **meta_pag, **meta}
            chunks.append({
                "texto": stxt,
                "pagina": pagina_num,
                **meta_completo
            })

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# INDEXAÇÃO NO CHROMADB (COM METADADOS E NORMALIZAÇÃO)
# ─────────────────────────────────────────────────────────────────────────────
def _gerar_id_chunk(nome_arquivo: str, indice: int, texto: str) -> str:
    """Id determinístico de um chunk (Fase 13, Task 5): a mesma combinação de arquivo, posição e
    conteúdo sempre produz o mesmo id.

    Antes, o id incluía `int(datetime.now().timestamp())` -- reindexar o mesmo documento sem
    mudança nenhuma produzia um id DIFERENTE a cada vez, e a única forma de evitar duplicação era
    apagar a coleção inteira do arquivo antes de reinserir (`remover_documento` no início de
    `indexar_documento`). Com o id dependendo só do conteúdo, reindexar sem mudanças produz
    exatamente os mesmos ids -- o que permite trocar `collection.add()` por `collection.upsert()`
    (sobrescreve em vez de duplicar) e reconciliar por diferença em vez de destruir e reconstruir
    tudo a cada chamada.

    `indice` entra no hash para não colidir quando duas linhas de uma tabela têm texto idêntico
    (célula vazia repetida, por exemplo) -- sem ele, ambas gerariam o mesmo id e uma sobrescreveria
    a outra silenciosamente no upsert.
    """
    hash_arquivo = hashlib.md5(nome_arquivo.encode("utf-8")).hexdigest()[:8]
    hash_conteudo = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
    return f"{hash_arquivo}_{indice}_{hash_conteudo}"


def indexar_documento(
    tenant_id: str,
    nome_arquivo: str,
    texto_ou_paginas: Union[str, List[Dict[str, Any]]],
    dados_tabulares: Optional[Dict[str, TabularSheet]] = None
) -> int:
    """Indexa um documento no ChromaDB com isolamento por tenant e metadados estruturados,

    e persiste a representação estruturada completa se for um arquivo tabular (CSV/XLSX/XLS).

    A reindexação é incremental (Fase 13, Task 5): usa `collection.upsert()` com ids
    determinísticos (`_gerar_id_chunk`) em vez de apagar e reconstruir a coleção inteira do
    arquivo a cada chamada -- chunks cujo conteúdo não mudou desde a última indexação recebem o
    mesmo id de antes e são simplesmente sobrescritos com o mesmo valor (upsert idempotente);
    só os chunks que sobraram de uma versão anterior e não existem mais no conjunto atual (linha
    removida, documento encolheu) são de fato apagados, ao final, por diferença de id.
    """
    logger = obter_logger(tenant_id)
    try:
        chunks_estruturados: List[Dict[str, Any]] = []

        tamanho_chunk = RAG_CONFIG.get("chunk_size", 600)
        sobreposicao = RAG_CONFIG.get("chunk_overlap", 100)

        if isinstance(texto_ou_paginas, list):
            for item in texto_ou_paginas:
                num_pag = item.get("pagina", 1)
                txt_pag = item.get("texto", "")
                meta_item = item.get("metadados", {})
                chunks_estruturados.extend(
                    dividir_pagina_em_chunks(
                        num_pag, txt_pag,
                        tamanho_chunk=tamanho_chunk, sobreposicao=sobreposicao,
                        metadados_base=meta_item
                    )
                )
        elif isinstance(texto_ou_paginas, str):
            padrao_pag = re.compile(r'---\s*\[PÁGINA\s*(\d+)\]\s*---', re.IGNORECASE)
            partes = padrao_pag.split(texto_ou_paginas)
            if len(partes) > 1:
                for i in range(1, len(partes), 2):
                    num_pag = int(partes[i])
                    txt_pag = partes[i + 1] if i + 1 < len(partes) else ""
                    chunks_estruturados.extend(
                        dividir_pagina_em_chunks(
                            num_pag, txt_pag,
                            tamanho_chunk=tamanho_chunk, sobreposicao=sobreposicao
                        )
                    )
            else:
                chunks_estruturados.extend(
                    dividir_pagina_em_chunks(
                        1, texto_ou_paginas,
                        tamanho_chunk=tamanho_chunk, sobreposicao=sobreposicao
                    )
                )
        else:
            raise ValueError(f"Formato inválido de documento para indexação: {type(texto_ou_paginas)}")

        if not chunks_estruturados:
            logger.warning(f"Nenhum chunk gerado para indexação do arquivo '{nome_arquivo}' (tenant={tenant_id})")
            return 0

        # Storage tabular é sempre substituído por completo logo abaixo (salvar_documento_tabular
        # grava um JSON novo, nunca mescla) -- remover antes só importa se este arquivo ERA
        # tabular numa indexação anterior e deixou de ser (extensão trocada, ou a reconstrução
        # não gerar nenhuma aba desta vez). O lado do ChromaDB não precisa mais de remoção
        # antecipada (Fase 13, Task 5): ids determinísticos + upsert cuidam disso por diferença,
        # ao final desta função.
        remover_documento_tabular(tenant_id, nome_arquivo)

        # Gestão de Persistência Tabular Estruturada (Prioridade 3)
        ext = nome_arquivo.lower().split(".")[-1] if "." in nome_arquivo else ""
        if ext in ("csv", "xlsx", "xls"):
            if dados_tabulares:
                salvar_documento_tabular(tenant_id, nome_arquivo, ext, dados_tabulares)
            else:
                # Reconstrói a representação estruturada a partir dos chunks enriquecidos
                sheets_reconstruidos: Dict[str, TabularSheet] = {}
                for c in chunks_estruturados:
                    aba_nome = c.get("aba", "Tabela")
                    linha_idx = int(c.get("linha", 1))
                    if aba_nome not in sheets_reconstruidos:
                        sheets_reconstruidos[aba_nome] = TabularSheet(nome_aba=aba_nome, schema=[], linhas=[])

                    txt_chunk = c.get("texto", "")
                    dados_linha: Dict[str, Any] = {}
                    for l in txt_chunk.split("\n"):
                        l = l.strip()
                        if not l or l.startswith("Aba: ") or l.startswith("Propriedades") or l.startswith("Marcadores") or l.startswith("[") or l.startswith("- "):
                            continue
                        if ":" in l:
                            k, v = l.split(":", 1)
                            k = k.strip()
                            v = v.strip()
                            v_limpo = re.sub(r'\s*\([^)]*\)$', '', v)
                            dados_linha[k] = v_limpo
                            if k not in sheets_reconstruidos[aba_nome].schema:
                                sheets_reconstruidos[aba_nome].schema.append(k)

                    if dados_linha:
                        sheets_reconstruidos[aba_nome].linhas.append(TabularRow(
                            linha=linha_idx,
                            dados=dados_linha,
                            metadados_derivados={
                                "tem_valor_negativo": c.get("tem_valor_negativo", False),
                                "tem_campo_ausente": c.get("tem_campo_ausente", False),
                                "campos_ausentes": c.get("campos_ausentes", ""),
                                "tem_valor_zero": c.get("tem_valor_zero", False)
                            }
                        ))

                if sheets_reconstruidos:
                    salvar_documento_tabular(tenant_id, nome_arquivo, ext, sheets_reconstruidos)

        # Garantia de janela de tokens (Fase 13, Task 2): roda DEPOIS da reconstrução tabular
        # acima, que precisa dos chunks originais e inteiros (ela lê pares "chave: valor" linha a
        # linha; bissectar antes correria o risco de partir uma linha ao meio). O que a indexação
        # vetorial recebe daqui pra frente é a versão garantidamente dentro da janela do modelo.
        chunks_estruturados = _garantir_limite_de_tokens(chunks_estruturados)

        textos = [c["texto"] for c in chunks_estruturados]
        embeddings = gerar_embeddings_normalizados(textos)

        collection = _obter_colecao_tenant(tenant_id)
        timestamp_iso = datetime.now().isoformat()

        ids = [_gerar_id_chunk(nome_arquivo, i, c["texto"]) for i, c in enumerate(chunks_estruturados)]
        metadatas = []
        for i, c in enumerate(chunks_estruturados):
            meta = {
                "fonte": str(nome_arquivo),
                "pagina": int(c.get("pagina", 1)),
                "chunk_index": int(i),
                "tenant_id": str(tenant_id),
                "indexado_em": timestamp_iso,
            }
            campos_permitidos = [
                "secao", "produto", "modelo", "variante", "material",
                "tipo_arquivo", "rotulo_unidade", "aba", "linha", "slide", "secao_origem",
                "tem_valor_negativo", "tem_campo_ausente", "campos_ausentes", "tem_valor_zero"
            ]
            for campo in campos_permitidos:
                if campo in c and c[campo] is not None:
                    val = c[campo]
                    if isinstance(val, (str, int, float, bool)):
                        meta[campo] = val
                    else:
                        meta[campo] = str(val)

            metadatas.append(meta)

        collection.upsert(
            ids=ids,
            documents=textos,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Reconciliação: remove só os chunks que pertenciam a uma versão anterior deste arquivo
        # e não existem no conjunto atual (linha/parágrafo removido, documento encolheu) -- os
        # que continuam iguais já foram sobrescritos pelo upsert acima com o mesmo id de sempre,
        # e nunca chegam a ser tocados por este delete.
        existentes = collection.get(where={"fonte": str(nome_arquivo)}, include=[])
        ids_orfaos = [i for i in existentes["ids"] if i not in set(ids)]
        if ids_orfaos:
            collection.delete(ids=ids_orfaos)

        logger.info(f"Documento '{nome_arquivo}' indexado com sucesso (tenant={tenant_id}): {len(chunks_estruturados)} chunks v2 gravados.")
        return len(chunks_estruturados)
    except Exception as e:
        logger.error(f"Erro ao indexar documento '{nome_arquivo}' para o tenant '{tenant_id}': {e}", exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# BUSCA SEMÂNTICA, HÍBRIDA E RERANKING
# ─────────────────────────────────────────────────────────────────────────────
def _log_resumo_busca(logger, tenant_id: str, debug_info: Dict[str, Any], tempo_inicio: float) -> None:
    """Registra uma linha de log estruturada e enxuta com o resultado de uma busca RAG.

    Complementa o bloco de debug verboso (gated por RAG_DEBUG) com uma linha sempre ativa,
    de baixo custo, para observabilidade mínima em produção: tenant, rota escolhida pelo
    QueryRouter, se o motor tabular foi acionado, quantidade de chunks retornados ao LLM e
    tempo total de resposta da busca.
    """
    tempo_ms = (time.time() - tempo_inicio) * 1000
    logger.info(
        f"rag_query_summary tenant={tenant_id} route={debug_info.get('route', '?')} "
        f"tabular_attempted={debug_info.get('tabular_engine_attempted', False)} "
        f"chunks={debug_info.get('final_context', {}).get('quantidade_chunks', 0)} "
        f"tempo_ms={tempo_ms:.1f}"
    )


_PADRAO_CODIGO_ENTIDADE = re.compile(r"\b[A-Za-z]{1,6}-?\d{2,}[A-Za-z0-9]*\b")


def _codigos_de_entidade(texto: str) -> List[str]:
    vistos: List[str] = []
    for codigo in _PADRAO_CODIGO_ENTIDADE.findall(texto or ""):
        if codigo.upper() not in (c.upper() for c in vistos):
            vistos.append(codigo)
    return vistos


def _expandir_por_entidade(
    collection,
    selecionados: List[CandidateChunk],
    pergunta: str,
    cfg: Dict[str, Any],
    final_k: int,
) -> Tuple[List[CandidateChunk], Dict[str, Any]]:
    """Segundo salto: segue os códigos citados no trecho-âncora até outros documentos.

    Resolve perguntas cuja resposta está dividida entre documentos ("preço do tecido do jaleco
    JL-100": o manual liga a peça ao código TX-200, o catálogo liga TX-200 ao preço). A busca
    vetorial acha a peça mas nunca a linha do catálogo, que não compartilha vocabulário com a
    pergunta.
    """
    debug: Dict[str, Any] = {"ancora": None, "codigos": [], "adicionados": []}
    max_chunks = int(cfg.get("entity_hop_max_chunks", 2))
    if not selecionados or max_chunks <= 0:
        return selecionados, debug

    # Âncora pelo casamento lexical com a pergunta, não pelo score final: o 1º colocado pode ser
    # um trecho de outro documento que só se parece com a pergunta.
    ancora = max(selecionados, key=lambda c: c.lexical_score)
    pergunta_upper = pergunta.upper()
    codigos = [
        c for c in _codigos_de_entidade(ancora.texto)
        if not re.search(rf"\b{re.escape(c.upper())}\b", pergunta_upper)
    ]
    debug["ancora"] = ancora.chunk_id
    debug["codigos"] = codigos
    if not codigos:
        return selecionados, debug

    por_id = {c.chunk_id: c for c in selecionados}
    vistos: Set[str] = {ancora.chunk_id}
    novos: List[CandidateChunk] = []
    for codigo in codigos:
        if len(novos) >= max_chunks:
            break
        res = collection.get(
            where_document={"$contains": codigo},
            include=["documents", "metadatas"],
        )
        padrao = re.compile(rf"\b{re.escape(codigo)}\b")
        for c_id, doc, meta in zip(res.get("ids", []), res.get("documents", []), res.get("metadatas", [])):
            meta = meta or {}
            if len(novos) >= max_chunks:
                break
            if c_id in vistos or meta.get("fonte") == ancora.fonte or not padrao.search(doc or ""):
                continue
            vistos.add(c_id)
            debug["adicionados"].append({"chunk_id": c_id, "codigo": codigo, "ja_selecionado": c_id in por_id})
            if c_id in por_id:
                novos.append(por_id[c_id])
                continue
            novos.append(CandidateChunk(
                chunk_id=c_id,
                texto=doc,
                metadata=meta,
                pagina=meta.get("pagina", 1),
                fonte=meta.get("fonte", "Documento"),
                final_score=ancora.final_score,
                score_breakdown={"entity_hop": 1.0},
                matched_concepts={codigo},
            ))

    if not novos:
        return selecionados, debug

    restantes = [c for c in selecionados if c not in novos]
    posicao = restantes.index(ancora) + 1
    expandidos = restantes[:posicao] + novos + restantes[posicao:]
    return expandidos[:max(final_k, posicao + len(novos))], debug


def buscar_contexto_relevante(
    tenant_id: str,
    pergunta: str,
    top_k: int = DEFAULT_INITIAL_TOP_K,
    threshold: float = RAG_SIMILARITY_THRESHOLD,
    final_k: int = FINAL_RERANK_K,
    reranker: Optional[BaseReranker] = None,
    config: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Executa a busca híbrida avançada (Query Understanding + Multi-Query Retrieval +

    Fusão/Deduplicação + Reranking Desacoplado + Seleção com Cobertura/Diversidade).
    Preserva 100% de compatibilidade com a interface pública original.
    """
    global _ULTIMO_RAG_DEBUG
    logger = obter_logger(tenant_id)
    cfg = config or RAG_CONFIG
    _inicio_busca = time.time()

    try:
        collection = _obter_colecao_tenant(tenant_id)
        total_docs = collection.count()

        # -1. Conversational Query Rewriting & Anaphora Resolution (Prioridade 4)
        conv_rewrite_res = None
        pergunta_busca = pergunta
        if cfg.get("enable_conversational_query_rewriting", True) and conversation_id:
            conv_rewrite_res = conversational_query.reescrever_query_conversacional(
                query=pergunta,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                config=cfg
            )
            if conv_rewrite_res and conv_rewrite_res.context_resolved and conv_rewrite_res.rewritten_query:
                pergunta_busca = conv_rewrite_res.rewritten_query

        # -0.5. Query Routing Inteligente e Detecção de Ambiguidade (Prioridade 5)
        query_route = None
        if cfg.get("enable_query_router", True):
            router_obj = QueryRouter(tenant_id, cfg)
            query_route = router_obj.route_query(
                pergunta_busca,
                conversation_context_active=bool(conversation_id and conv_rewrite_res and conv_rewrite_res.context_resolved)
            )

            # Se for AMBIGUOUS sem contexto conversacional desambiguador: emite clarification chunk imediato
            if query_route.is_ambiguous and not (conversation_id and conv_rewrite_res and conv_rewrite_res.context_resolved):
                ambiguity_chunk = {
                    "id": "ambiguity_clarification_p5",
                    "texto": query_route.ambiguity_prompt or "A pergunta é ambígua porque existem múltiplos eventos e registros no dataset. Por favor, especifique a qual jogo, modalidade ou evento você se refere.",
                    "fonte": "Sistema (Desambiguação)",
                    "pagina": 1,
                    "rotulo_unidade": "Desambiguação Necessária",
                    "tipo_arquivo": "sistema",
                    "score": 1.0,
                    "detalhes_score": {"ambiguity": 1.0},
                    "retrieval_count": 1,
                    "matched_concepts": ["ambiguidade"],
                    "is_relevant": True,
                    "discard_reason": ""
                }
                _ULTIMO_RAG_DEBUG = {
                    "question": pergunta,
                    "rewritten_question": pergunta_busca if pergunta_busca != pergunta else None,
                    "route": query_route.route.value,
                    "route_confidence": query_route.confidence,
                    "route_reasons": query_route.reasons,
                    "tabular_intent": None,
                    "selected_sources": [],
                    "fallback_sources": [],
                    "tabular_engine_attempted": False,
                    "tabular_engine_success": False,
                    "vector_retrieval_used": False,
                    "retrieval_pool_size": 0,
                    "structured_results_count": 0,
                    "narrative_results_count": 0,
                    "final_context_count": 1,
                    "ambiguous": True,
                    "context_switch_detected": bool(conv_rewrite_res and conv_rewrite_res.debug.get("domain_switch_detected")),
                    "query_type": ["AMBIGUOUS"],
                    "generated_queries": [pergunta_busca],
                    "retrieval_results": {},
                    "final_reranking": [ambiguity_chunk],
                    "coverage": {},
                    "tabular_query_debug": None,
                    "conversational_query_debug": conv_rewrite_res.to_dict() if conv_rewrite_res else None,
                    "final_context": {"quantidade_chunks": 1, "caracteres": len(ambiguity_chunk["texto"]), "fontes": [ambiguity_chunk["fonte"]]}
                }
                _log_resumo_busca(logger, tenant_id, _ULTIMO_RAG_DEBUG, _inicio_busca)
                return [ambiguity_chunk]

        # 0. Verificação e Execução do Tabular Query Engine (Prioridades 3 e 5)
        tabular_chunk_dict = None
        tabular_debug_info = None
        plano_tab = None
        if cfg.get("enable_tabular_query_engine", True):
            plano_tab = detectar_e_planejar_consulta_tabular(pergunta_busca, tenant_id, cfg)
            if plano_tab and plano_tab.confidence >= 0.20:
                res_tab = executar_consulta_tabular(plano_tab, tenant_id, cfg)
                if res_tab.success:
                    tabular_debug_info = {
                        "plano": {
                            "intent": plano_tab.intent.value,
                            "target_document": plano_tab.target_document,
                            "target_sheet": plano_tab.target_sheet,
                            "selection_reason": plano_tab.selection_reason,
                            "confidence": plano_tab.confidence
                        },
                        "resultado": res_tab.to_dict(),
                        "fallback_vetorial": False
                    }
                    tabular_chunk_dict = {
                        "id": f"tabular_{plano_tab.target_document}_{plano_tab.intent.value}",
                        "texto": res_tab.formatted_result_block,
                        "fonte": plano_tab.target_document,
                        "pagina": 1,
                        "rotulo_unidade": f"Aba {plano_tab.target_sheet} (Agregação Tabular: {plano_tab.intent.value})",
                        "tipo_arquivo": "tabular",
                        "score": 1.0,
                        "detalhes_score": {"tabular": 1.0, "vector": 1.0, "lexical": 1.0},
                        "retrieval_count": 1,
                        "matched_concepts": list(plano_tab.target_columns or plano_tab.group_by_columns or []),
                        "is_relevant": True,
                        "discard_reason": ""
                    }

        if total_docs == 0:
            if tabular_chunk_dict:
                _ULTIMO_RAG_DEBUG = {
                    "question": pergunta,
                    "rewritten_question": pergunta_busca if pergunta_busca != pergunta else None,
                    "route": query_route.route.value if query_route else "TABULAR_ONLY",
                    "route_confidence": query_route.confidence if query_route else 1.0,
                    "route_reasons": query_route.reasons if query_route else [],
                    "tabular_intent": plano_tab.intent.value if plano_tab else None,
                    "selected_sources": [plano_tab.target_document] if plano_tab else [],
                    "fallback_sources": [],
                    "tabular_engine_attempted": bool(plano_tab),
                    "tabular_engine_success": True,
                    "vector_retrieval_used": False,
                    "retrieval_pool_size": 0,
                    "structured_results_count": 1,
                    "narrative_results_count": 0,
                    "final_context_count": 1,
                    "ambiguous": False,
                    "context_switch_detected": bool(conv_rewrite_res and conv_rewrite_res.debug.get("domain_switch_detected")),
                    "query_type": ["TABULAR_ONLY"],
                    "generated_queries": [pergunta_busca],
                    "retrieval_results": {},
                    "final_reranking": [tabular_chunk_dict],
                    "coverage": {},
                    "tabular_query_debug": tabular_debug_info,
                    "conversational_query_debug": conv_rewrite_res.to_dict() if conv_rewrite_res else None,
                    "final_context": {"quantidade_chunks": 1, "caracteres": len(tabular_chunk_dict["texto"]), "fontes": [tabular_chunk_dict["fonte"]]}
                }
                _log_resumo_busca(logger, tenant_id, _ULTIMO_RAG_DEBUG, _inicio_busca)
                return [tabular_chunk_dict]

            if RAG_DEBUG:
                logger.info(f"[RAG DEBUG] Coleção vazia para tenant '{tenant_id}'.")
            _ULTIMO_RAG_DEBUG = {
                "question": pergunta,
                "rewritten_question": pergunta_busca if pergunta_busca != pergunta else None,
                "route": "EMPTY_COLLECTION",
                "route_confidence": 0.0,
                "route_reasons": [],
                "tabular_intent": None,
                "selected_sources": [],
                "fallback_sources": [],
                "tabular_engine_attempted": bool(plano_tab),
                "tabular_engine_success": False,
                "vector_retrieval_used": False,
                "retrieval_pool_size": 0,
                "structured_results_count": 0,
                "narrative_results_count": 0,
                "final_context_count": 0,
                "ambiguous": False,
                "context_switch_detected": False,
                "query_type": ["EMPTY_COLLECTION"],
                "generated_queries": [pergunta_busca],
                "retrieval_results": {},
                "final_reranking": [],
                "coverage": {},
                "tabular_query_debug": tabular_debug_info,
                "conversational_query_debug": conv_rewrite_res.to_dict() if conv_rewrite_res else None,
                "final_context": {"quantidade_chunks": 0, "caracteres": 0, "fontes": []}
            }
            _log_resumo_busca(logger, tenant_id, _ULTIMO_RAG_DEBUG, _inicio_busca)
            return []

        # 1. Query Understanding, Classificação e Expansão/Decomposição
        query_analysis = analisar_query_completa(pergunta_busca, cfg)
        queries_para_busca = query_analysis.all_queries

        # 2. Multi-Query Retrieval no ChromaDB com Pool Inicial Amplo
        modelo = obter_modelo_embeddings()
        candidate_pool_k = cfg.get("retrieval_candidate_pool_size", cfg.get("base_retrieval_top_k", 30))
        per_q_k = max(cfg.get("per_query_top_k", 20), candidate_pool_k, top_k)

        resultados_por_query: Dict[str, List[Dict[str, Any]]] = {}

        for q_sub in queries_para_busca:
            q_emb = modelo.encode([q_sub], normalize_embeddings=True).tolist()
            k_busca = min(per_q_k, total_docs)
            res = collection.query(
                query_embeddings=q_emb,
                n_results=k_busca,
                include=["documents", "metadatas", "distances"],
            )

            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            dists = res.get("distances", [[]])[0] if "distances" in res else [1.0] * len(docs)
            ids = res.get("ids", [[]])[0] if "ids" in res else [f"cand_{i}" for i in range(len(docs))]

            lista_q = []
            for c_id, doc, meta, dist in zip(ids, docs, metas, dists):
                lista_q.append({
                    "id": c_id,
                    "texto": doc,
                    "meta": meta or {},
                    "dist": dist
                })
            resultados_por_query[q_sub] = lista_q

        # 3. Fusão e Deduplicação dos Candidatos
        candidatos_pool = fundir_e_deduplicar_candidatos(resultados_por_query)

        # 4. Reranking Desacoplado (HeuristicReranker por padrão)
        reranker_ativo = reranker or _DEFAULT_RERANKER
        candidatos_ranqueados = reranker_ativo.rerank(query_analysis, candidatos_pool, cfg)

        # 5. Seleção Final com Diversidade, Threshold Relativo e Cobertura Conceitual
        candidatos_selecionados = selecionar_com_cobertura_e_diversidade(
            candidatos_ranqueados,
            query_analysis,
            cfg,
            final_k=final_k
        )

        entity_hop_debug = None
        # Resposta tabular calculada = pergunta de agregação/filtro, sem entidade-âncora: o salto
        # só escolheria uma linha qualquer e empurraria as relevantes para fora do contexto.
        if cfg.get("enable_entity_hop", True) and not tabular_chunk_dict:
            candidatos_selecionados, entity_hop_debug = _expandir_por_entidade(
                collection, candidatos_selecionados, pergunta_busca, cfg, final_k
            )

        # 6. Validação de Cobertura para Observabilidade
        coverage_map: Dict[str, bool] = {}
        for conceito in query_analysis.key_concepts:
            c_norm = normalizar_texto(conceito)
            encontrado = any(c_norm in normalizar_texto(cand.texto) for cand in candidatos_selecionados)
            coverage_map[conceito] = encontrado

        # Formatação do contexto final
        chunks_formatados = [c.to_dict() for c in candidatos_selecionados]
        if tabular_chunk_dict:
            chunks_formatados.insert(0, tabular_chunk_dict)

        all_ranked_dicts = [c.to_dict() for c in candidatos_ranqueados]
        total_chars = sum(len(c["texto"]) for c in chunks_formatados)
        fontes_unicas = sorted(list(set(
            f"{c['fonte']} ({c.get('rotulo_unidade', 'Página ' + str(c.get('pagina', 1)))})"
            for c in chunks_formatados
        )))

        # 7. Gravação Estruturada do Relatório de Debug (Fase 12 / Prioridade 5)
        total_encontrados_inicial = sum(len(l) for l in resultados_por_query.values())
        struct_count = sum(1 for c in chunks_formatados if c.get("tipo_arquivo") in ("tabular", "csv", "xlsx", "xls") or str(c.get("fonte", "")).lower().endswith((".csv", ".xlsx", ".xls")))
        narr_count = sum(1 for c in chunks_formatados if c.get("tipo_arquivo") in ("md", "markdown", "pdf", "txt", "text") or str(c.get("fonte", "")).lower().endswith((".md", ".pdf", ".txt")))

        _ULTIMO_RAG_DEBUG = {
            "question": pergunta,
            "rewritten_question": pergunta_busca if pergunta_busca != pergunta else None,
            "route": query_route.route.value if query_route else "VECTOR_SEMANTIC",
            "route_confidence": query_route.confidence if query_route else 0.50,
            "route_reasons": query_route.reasons if query_route else [],
            "tabular_intent": (query_route.tabular_intent if query_route else None) or (plano_tab.intent.value if plano_tab else None),
            "selected_sources": (query_route.preferred_sources if query_route else []) or ([plano_tab.target_document] if plano_tab else []),
            "fallback_sources": query_route.fallback_sources if query_route else [],
            "tabular_engine_attempted": bool(plano_tab),
            "tabular_engine_success": bool(tabular_chunk_dict),
            "vector_retrieval_used": bool(candidatos_selecionados),
            "retrieval_pool_size": len(candidatos_pool),
            "structured_results_count": struct_count,
            "narrative_results_count": narr_count,
            "final_context_count": len(chunks_formatados),
            "ambiguous": bool(query_route and query_route.is_ambiguous),
            "context_switch_detected": bool(conv_rewrite_res and conv_rewrite_res.debug.get("domain_switch_detected")),
            "query_type": query_analysis.categories,
            "generated_queries": queries_para_busca,
            "candidatos_solicitados": per_q_k,
            "candidatos_encontrados_inicial": total_encontrados_inicial,
            "pool_antes_rerank_count": len(candidatos_pool),
            "tabular_query_debug": tabular_debug_info,
            "entity_hop_debug": entity_hop_debug,
            "conversational_query_debug": conv_rewrite_res.to_dict() if conv_rewrite_res else None,
            "retrieval_results": {
                q: [
                    {
                        "chunk_id": c["id"],
                        "score": round(max(0.0, 1.0 - (c["dist"] ** 2) / 2.0), 4),
                        "distancia": round(c["dist"], 4),
                        "lexical_score": round(calcular_score_lexical(query_analysis, c["texto"], cfg)[0], 4),
                        "retrieval_count": 1,
                        "fonte": c["meta"].get("fonte", "Doc"),
                        "pagina": c["meta"].get("pagina", 1),
                        "rotulo_unidade": c["meta"].get("rotulo_unidade", f"Página {c['meta'].get('pagina', 1)}"),
                        "texto": c["texto"]
                    } for c in c_list
                ] for q, c_list in resultados_por_query.items()
            },
            "all_ranked_candidates": all_ranked_dicts,
            "final_reranking": chunks_formatados,
            "coverage": coverage_map,
            "final_context": {
                "quantidade_chunks": len(chunks_formatados),
                "caracteres": total_chars,
                "fontes": fontes_unicas
            }
        }

        # Emissão de Log de Debug
        if RAG_DEBUG:
            logger.info(f"\n{formatar_bloco_debug_rag(_ULTIMO_RAG_DEBUG)}")

        _log_resumo_busca(logger, tenant_id, _ULTIMO_RAG_DEBUG, _inicio_busca)
        return chunks_formatados
    except Exception as e:
        logger.error(f"Erro ao recuperar contexto relevante no ChromaDB para tenant '{tenant_id}': {e}", exc_info=True)
        tempo_ms = (time.time() - _inicio_busca) * 1000
        logger.info(f"rag_query_summary tenant={tenant_id} route=ERROR tabular_attempted=False chunks=0 tempo_ms={tempo_ms:.1f}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MONTAGEM DO PROMPT FINAL PARA O LLM
# ─────────────────────────────────────────────────────────────────────────────
def montar_prompt_final(chunks_relevantes: List[Dict[str, Any]], pergunta: str) -> Tuple[str, Set[str]]:
    """Monta o prompt final enviado ao LLM a partir dos chunks recuperados pelo RAG.

    Formata cada chunk em um bloco "--- TRECHO N ---" com metadados de origem (documento,
    localização, seção/produto/variante), acrescenta a instrução de resposta exclusiva ao
    contexto fornecido e o contrato de dupla notação (numérica + por extenso), e retorna
    também o conjunto de fontes citadas para exibição na UI ("Fontes consultadas").
    """
    trechos_formatados: List[str] = []
    fontes_consultadas: Set[str] = set()

    for i, chk in enumerate(chunks_relevantes, 1):
        fonte = chk.get("fonte", "Documento desconhecido")
        rotulo = chk.get("rotulo_unidade")
        if not rotulo:
            pag = chk.get("pagina", 1)
            rotulo = f"Página {pag}"
        fontes_consultadas.add(f"{fonte} ({rotulo})")

        meta_info = []
        if chk.get("secao") or chk.get("secao_origem"):
            sec_val = chk.get("secao") or chk.get("secao_origem")
            meta_info.append(f"SEÇÃO: {sec_val}")
        if chk.get("produto") or chk.get("variante"):
            prod_var = f"{chk.get('produto', '')} {chk.get('variante', '')}".strip()
            meta_info.append(f"PRODUTO/VARIANTE: {prod_var}")
        if chk.get("aba"):
            meta_info.append(f"ABA: {chk['aba']}")
        meta_header = " | ".join(meta_info) if meta_info else "Especificação Técnica"

        trechos_formatados.append(
            f"--- TRECHO {i} ---\n"
            f"DOCUMENTO: {fonte}\n"
            f"LOCALIZAÇÃO: {rotulo}\n"
            f"CONTEXTO: {meta_header}\n"
            f"CONTEÚDO:\n{chk.get('texto', '')}\n"
        )

    contexto_rag = "\n".join(trechos_formatados)
    prompt_com_contexto = (
        "INSTRUÇÃO IMPORTANTE: Responda à pergunta a seguir utilizando EXCLUSIVAMENTE os seguintes trechos de documentos fornecidos. "
        "Siga rigorosamente as regras de preservação de números, medidas, códigos e isolamento de variantes.\n\n"
        "CONTRATO DE EXATIDÃO: sempre que a resposta envolver um número, data, valor monetário ou medida, "
        "inclua tanto a notação direta quanto a forma normalizada/por extenso na mesma frase "
        "(ex.: '5.300 (5300)', '28 de abril de 2006 (2006-04-28)', 'US$ 7.000.000 (7 milhões)'). "
        "Nunca escolha apenas um formato quando o dado permitir ambos.\n\n"
        f"--- TRECHOS DOS DOCUMENTOS DISPONÍVEIS ---\n{contexto_rag}\n--- FIM DOS TRECHOS ---\n\n"
        f"PERGUNTA DO USUÁRIO:\n{pergunta}"
    )
    return prompt_com_contexto, fontes_consultadas


# ─────────────────────────────────────────────────────────────────────────────
# GESTÃO DE DOCUMENTOS INDEXADOS
# ─────────────────────────────────────────────────────────────────────────────
def listar_documentos_indexados(tenant_id: str) -> List[str]:
    """Retorna a lista de nomes únicos de arquivos já indexados na coleção versionada do tenant."""
    logger = obter_logger(tenant_id)
    try:
        collection = _obter_colecao_tenant(tenant_id)
        if collection.count() == 0:
            return []

        registros = collection.get(include=["metadatas"])
        metadatas = registros.get("metadatas", [])

        documentos_unicos: Set[str] = set()
        for meta in metadatas:
            if meta and "fonte" in meta:
                documentos_unicos.add(meta["fonte"])

        return sorted(list(documentos_unicos))
    except Exception as e:
        logger.error(f"Erro ao listar documentos indexados do tenant '{tenant_id}': {e}", exc_info=True)
        return []


def remover_documento(tenant_id: str, nome_arquivo: str) -> bool:
    """Remove todos os chunks associados ao arquivo especificado da coleção do tenant e do storage tabular."""
    logger = obter_logger(tenant_id)
    try:
        remover_documento_tabular(tenant_id, nome_arquivo)
        collection = _obter_colecao_tenant(tenant_id)
        if collection.count() == 0:
            return True

        collection.delete(where={"fonte": str(nome_arquivo)})
        logger.info(f"Documento '{nome_arquivo}' removido com sucesso do tenant '{tenant_id}'.")
        return True
    except Exception as e:
        logger.error(f"Erro ao remover documento '{nome_arquivo}' do tenant '{tenant_id}': {e}", exc_info=True)
        return False
