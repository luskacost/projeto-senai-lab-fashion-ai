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
COLLECTION_VERSION: str = "v2"  # Versionamento para garantir integridade do novo schema
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
    """Retorna a coleção ChromaDB versionada específica do tenant."""
    client = obter_cliente_chroma(tenant_id)
    nome_colecao = f"docs_{COLLECTION_VERSION}_{tenant_id}"
    return client.get_or_create_collection(name=nome_colecao)


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
    """
    Inferência heurística de metadados enriquecidos para têxteis e confecção.
    Classifica Seção, Produto, Modelo (Feminino/Masculino), Variante (Jeans/M518/Tradicional) e Material.
    """
    meta: Dict[str, str] = {}
    texto_upper = texto.upper()

    # 1. Seção
    if "FICHA TÉCNICA" in texto_upper or "FICHA TECNICA" in texto_upper:
        meta["secao"] = "Ficha Técnica"
    elif "DESENHO TÉCNICO" in texto_upper or "DESENHO TECNICO" in texto_upper:
        meta["secao"] = "Desenho Técnico"
    elif "TABELA DE MEDIDAS" in texto_upper or "MEDIDAS BÁSICAS" in texto_upper or "MEDIDAS BASICAS" in texto_upper:
        meta["secao"] = "Tabela de Medidas"
    elif "ESTAMPA" in texto_upper or "ESTAMPARIA" in texto_upper:
        meta["secao"] = "Estamparia"
    elif "AVIAMENTO" in texto_upper:
        meta["secao"] = "Aviamentos"
    elif "ETIQUETA" in texto_upper:
        meta["secao"] = "Etiquetas"
    elif "DESCRIÇÃO TÉCNICA" in texto_upper or "DESCRICAO TECNICA" in texto_upper or "ESPECIFICAÇÕES" in texto_upper:
        meta["secao"] = "Especificações Técnicas"

    # 2. Produto
    if "CAMISA" in texto_upper or "CAMISETE" in texto_upper:
        meta["produto"] = "Camisa"
    elif "CALÇA" in texto_upper or "CALCA" in texto_upper:
        meta["produto"] = "Calça"

    # 3. Modelo / Gênero
    if re.search(r'\bFEMININ[AO]\b', texto_upper) or "CAMISETE" in texto_upper:
        meta["modelo"] = "Feminino"
    elif re.search(r'\bMASCULIN[AO]\b', texto_upper):
        meta["modelo"] = "Masculino"
    elif re.search(r'\bINFANTIL\b', texto_upper):
        meta["modelo"] = "Infantil"
    elif re.search(r'\bUNISSEX\b', texto_upper):
        meta["modelo"] = "Unissex"

    # 4. Variante e Material
    tem_millie = ("MILLIE DENIM" in texto_upper or "MASKSKIN" in texto_upper)
    tem_jeans = ("JEANS" in texto_upper or "LAVAGEM CLARA" in texto_upper)
    tem_m518 = ("M518" in texto_upper)
    tem_tradicional = ("TRADICIONAL" in texto_upper or "BRANCO, AZUL CLARO E AZUL MARINHO" in texto_upper)

    if (tem_millie or tem_jeans) and not tem_m518:
        meta["variante"] = "Jeans"
        meta["material"] = "Millie Denim Maskskin"
    elif tem_m518 and not tem_millie:
        meta["variante"] = "M518"
        meta["material"] = "M518"
    elif tem_tradicional and not tem_millie:
        meta["variante"] = "Tradicional"

    if "100% LIOCEL" in texto_upper or "LIOCEL" in texto_upper:
        meta["material"] = "100% Liocel"
    elif "100% ALGODÃO" in texto_upper or "100% ALGODAO" in texto_upper:
        meta["material"] = "100% Algodão"

    return meta


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

    linhas = [l.strip() for l in txt_pag_limpo.splitlines() if l.strip()]
    cabecalho_contexto = ""
    for l in linhas[:3]:
        if any(w in l.upper() for w in ["CAMISA", "CAMISETE", "CORPORATIVO", "DESENHO TÉCNICO", "AVIAMENTOS", "ESTAMPARIA"]):
            cabecalho_contexto = l
            break

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

        # Enriquece sub-blocos específicos com contexto explícito da variante têxtil
        if "MILLIE DENIM" in p.upper() or "LAVAGEM CLARA" in p.upper():
            if "JEANS" not in texto_chunk.upper():
                texto_chunk = f"PRODUTO: Camisa Jeans (Variante Jeans / Denim - Tecido Millie Denim Maskskin - Lavagem Clara)\n{texto_chunk}"
        elif "M518" in p.upper():
            if "TRADICIONAL" not in texto_chunk.upper() and "M518" in texto_chunk.upper():
                texto_chunk = f"PRODUTO: Camisa Tradicional (Cores: Branco, Azul Claro, Azul Marinho - Tecido M518)\n{texto_chunk}"

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


def dividir_em_chunks(texto: str, tamanho_chunk: int = 450, sobreposicao: int = 70) -> List[str]:
    """Função de compatibilidade com a assinatura original.

    Retorna lista de textos particionados.
    """
    if not texto or not texto.strip():
        return []

    padrao_pag = re.compile(r'---\s*\[PÁGINA\s*(\d+)\]\s*---', re.IGNORECASE)
    partes = padrao_pag.split(texto)

    chunks_str: List[str] = []
    if len(partes) > 1:
        for i in range(1, len(partes), 2):
            num_pag = int(partes[i])
            txt_pag = partes[i + 1] if i + 1 < len(partes) else ""
            chunks_pag = dividir_pagina_em_chunks(num_pag, txt_pag, tamanho_chunk, sobreposicao)
            for c in chunks_pag:
                chunks_str.append(c["texto"])
    else:
        chunks_pag = dividir_pagina_em_chunks(1, texto, tamanho_chunk, sobreposicao)
        for c in chunks_pag:
            chunks_str.append(c["texto"])

    return chunks_str


# ─────────────────────────────────────────────────────────────────────────────
# INDEXAÇÃO NO CHROMADB (COM METADADOS E NORMALIZAÇÃO)
# ─────────────────────────────────────────────────────────────────────────────
def indexar_documento(
    tenant_id: str,
    nome_arquivo: str,
    texto_ou_paginas: Union[str, List[Dict[str, Any]]],
    dados_tabulares: Optional[Dict[str, TabularSheet]] = None
) -> int:
    """Indexa um documento no ChromaDB com isolamento por tenant e metadados estruturados,

    e persiste a representação estruturada completa se for um arquivo tabular (CSV/XLSX/XLS).
    """
    logger = obter_logger(tenant_id)
    try:
        chunks_estruturados: List[Dict[str, Any]] = []

        if isinstance(texto_ou_paginas, list):
            for item in texto_ou_paginas:
                num_pag = item.get("pagina", 1)
                txt_pag = item.get("texto", "")
                meta_item = item.get("metadados", {})
                chunks_estruturados.extend(
                    dividir_pagina_em_chunks(num_pag, txt_pag, metadados_base=meta_item)
                )
        elif isinstance(texto_ou_paginas, str):
            padrao_pag = re.compile(r'---\s*\[PÁGINA\s*(\d+)\]\s*---', re.IGNORECASE)
            partes = padrao_pag.split(texto_ou_paginas)
            if len(partes) > 1:
                for i in range(1, len(partes), 2):
                    num_pag = int(partes[i])
                    txt_pag = partes[i + 1] if i + 1 < len(partes) else ""
                    chunks_estruturados.extend(dividir_pagina_em_chunks(num_pag, txt_pag))
            else:
                chunks_estruturados.extend(dividir_pagina_em_chunks(1, texto_ou_paginas))
        else:
            raise ValueError(f"Formato inválido de documento para indexação: {type(texto_ou_paginas)}")

        if not chunks_estruturados:
            logger.warning(f"Nenhum chunk gerado para indexação do arquivo '{nome_arquivo}' (tenant={tenant_id})")
            return 0

        # Remove versões anteriores do mesmo documento para evitar duplicidade (ChromaDB e Tabular Storage)
        remover_documento(tenant_id, nome_arquivo)

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

        textos = [c["texto"] for c in chunks_estruturados]
        embeddings = gerar_embeddings_normalizados(textos)

        collection = _obter_colecao_tenant(tenant_id)
        timestamp_iso = datetime.now().isoformat()
        hash_arquivo = hashlib.md5(nome_arquivo.encode("utf-8")).hexdigest()[:8]

        ids = [f"{hash_arquivo}_{i}_{int(datetime.now().timestamp())}" for i in range(len(chunks_estruturados))]
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

        collection.add(
            ids=ids,
            documents=textos,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(f"Documento '{nome_arquivo}' indexado com sucesso (tenant={tenant_id}): {len(chunks_estruturados)} chunks v2 gravados.")
        return len(chunks_estruturados)
    except Exception as e:
        logger.error(f"Erro ao indexar documento '{nome_arquivo}' para o tenant '{tenant_id}': {e}", exc_info=True)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO DE TERMOS E CONSULTAS COMPARATIVAS
# ─────────────────────────────────────────────────────────────────────────────
def _extrair_termos_chave(query: str) -> List[str]:
    """Extrai palavras-chave, códigos, números e unidades técnicas relevantes da pergunta."""
    codigos = re.findall(r'\b[A-Za-z]+[-_]?\d+[A-Za-z0-9]*\b|\b\d+[A-Za-z]+[0-9]*\b', query)
    medidas = re.findall(r'\b\d+(?:[.,]\d+)?\s*(?:g/m²|g/m2|oz|cm|mm|m|%)\b', query, re.IGNORECASE)
    palavras = re.findall(r'\b[A-Za-zÀ-ÿ]{3,}\b', query)

    stopwords = {
        "qual", "quais", "como", "onde", "quando", "quem", "porque", "para", "com", "sem",
        "que", "uma", "uns", "umas", "sobre", "entre", "este", "esta", "esse", "essa",
        "dele", "dela", "deles", "delas", "pelo", "pela", "pelos", "pelas", "está", "estao",
        "especificado", "utilizado", "utilizada", "usado", "usada", "informação", "documento",
        "segundo", "acordo", "dizer", "diz", "fornece", "preço", "custo", "saber", "indicado",
        "apresentado", "aparece", "aparecem"
    }
    termos_filtrados = [p.lower() for p in palavras if p.lower() not in stopwords]

    todos_termos = list(set([c.lower() for c in codigos] + [m.lower() for m in medidas] + termos_filtrados))
    return todos_termos


def _detectar_consulta_comparativa(query: str) -> Optional[Tuple[str, str]]:
    """Detecta se a consulta é uma comparação entre duas entidades e retorna (entidade_a, entidade_b)."""
    padroes = [
        r'(?:diferen[cç]as?|distin[cç][aã]o|compar(?:a[cç][aã]o|e|ar))\s+(?:entre\s+)?(?P<e1>.+?)\s+(?:e|com|versus|vs\.?)\s+(?P<e2>[^?.\n]+)',
        r'(?P<e1>[^?.\n]+?)\s+(?:versus|vs\.?)\s+(?P<e2>[^?.\n]+)',
        r'(?:qual\s+(?:a\s+)?diferen[cç]a\s+(?:entre\s+)?)(?P<e1>.+?)\s+e\s+(?P<e2>[^?.\n]+)'
    ]

    for p in padroes:
        m = re.search(p, query, re.IGNORECASE)
        if m:
            e1 = m.group("e1").strip()
            e2 = m.group("e2").strip()
            e1 = re.sub(r'^(?:o|a|os|as|do|da|dos|das|um|uma|entre)\s+', '', e1, flags=re.IGNORECASE).strip()
            e2 = re.sub(r'^(?:o|a|os|as|do|da|dos|das|um|uma)\s+', '', e2, flags=re.IGNORECASE).strip()
            e1 = e1.strip(" ?.,;")
            e2 = e2.strip(" ?.,;")
            if len(e1) >= 2 and len(e2) >= 2:
                return (e1, e2)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# SCORING HÍBRIDO E RERANKING
# ─────────────────────────────────────────────────────────────────────────────
def _calcular_score_hibrido(query: str, chunk_texto: str, metadata: Dict[str, Any], dist_chroma: float) -> Tuple[float, Dict[str, float]]:
    """Calcula um score combinado (0.0 a 1.0) unindo similaridade semântica, correspondência lexical exata,

    alinhamento de variantes, termos técnicos têxteis e modelo para evitar contaminação cruzada.
    """
    # 1. Similaridade semântica (Chroma L2 distance em vetores unitários: d^2 = 2 - 2*cos_sim => cos_sim = 1 - d^2 / 2)
    cos_sim = max(0.0, 1.0 - (dist_chroma ** 2) / 2.0)

    # 2. Correspondência Lexical e de Termos Exatos
    termos_query = _extrair_termos_chave(query)
    chunk_lower = chunk_texto.lower()
    query_lower = query.lower()

    matches_termos = 0
    bonus_codigos = 0.0

    palavras_chave_altas = {
        "millie", "maskskin", "liocel", "tafeta", "tafetá", "bandeirola", "chimango",
        "patte", "puídos", "maquinetado", "fieg", "dtf", "serigrafia", "tnt", "tex",
        "xgg", "pp", "gramatura", "largura", "punho", "gola", "barra", "botão", "botões",
        "etiqueta", "bordado", "pontos", "polegada", "tamanho", "tamanhos", "grade", "cor", "cores"
    }

    for termo in termos_query:
        # Match direto ou variação singular/plural simples em PT
        if termo in chunk_lower or (len(termo) > 3 and termo.rstrip('s') in chunk_lower) or (termo == "cores" and "cor" in chunk_lower):
            matches_termos += 1
            if re.search(r'\d', termo) or termo in palavras_chave_altas:
                bonus_codigos += 0.15

    razao_termos = (matches_termos / len(termos_query)) if termos_query else 0.0
    score_lexical = min(1.0, (razao_termos * 0.7) + bonus_codigos)

    # 3. Alinhamento de Variante e Prevenção de Contaminação
    ajuste_variante = 0.0
    pede_jeans = ("jeans" in query_lower or "millie" in query_lower or "denim" in query_lower)
    pede_m518 = ("m518" in query_lower)
    pede_masculina = ("masculin" in query_lower or "homem" in query_lower)
    pede_feminina = ("feminin" in query_lower or "camisete" in query_lower or "mulher" in query_lower)

    tem_jeans = ("jeans" in chunk_lower or "millie" in chunk_lower or metadata.get("variante") == "Jeans")
    tem_m518 = ("m518" in chunk_lower or metadata.get("variante") == "M518")

    if pede_jeans and pede_m518:
        if tem_jeans or tem_m518:
            ajuste_variante += 0.25
    elif pede_jeans:
        if tem_jeans:
            ajuste_variante += 0.25
        elif tem_m518:
            ajuste_variante -= 0.40
    elif pede_m518:
        if tem_m518:
            ajuste_variante += 0.25
        elif tem_jeans:
            ajuste_variante -= 0.40

    # 4. Alinhamento de Gênero / Modelo
    if pede_masculina and not pede_feminina:
        if metadata.get("modelo") == "Masculino":
            ajuste_variante += 0.20
        elif metadata.get("modelo") == "Feminino":
            ajuste_variante -= 0.20
    elif pede_feminina and not pede_masculina:
        if metadata.get("modelo") == "Feminino":
            ajuste_variante += 0.20
        elif metadata.get("modelo") == "Masculino":
            ajuste_variante -= 0.20

    # 5. Priorização de especificações de modelagem e construção vs referências espaciais
    if "tipo de gola" in query_lower or ("gola" in query_lower and "altura" not in query_lower and "logotipo" not in query_lower):
        if "pé de gola" in chunk_lower or "gola camisa" in chunk_lower:
            ajuste_variante += 0.30
        elif "abaixo da gola" in chunk_lower and "estamparia" in metadata.get("secao", "").lower():
            ajuste_variante -= 0.20

    # 6. Score Final Ponderado
    score_final = (0.50 * cos_sim) + (0.50 * score_lexical) + ajuste_variante
    score_final = max(0.0, min(1.0, score_final))

    detalhes = {
        "cos_sim": round(cos_sim, 4),
        "score_lex": round(score_lexical, 4),
        "ajuste_variante": round(ajuste_variante, 4),
        "score_final": round(score_final, 4)
    }

    return score_final, detalhes


# ─────────────────────────────────────────────────────────────────────────────
# BUSCA SEMÂNTICA, HÍBRIDA E RERANKING
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# BUSCA SEMÂNTICA, HÍBRIDA E RERANKING
# ─────────────────────────────────────────────────────────────────────────────
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

        return chunks_formatados
    except Exception as e:
        logger.error(f"Erro ao recuperar contexto relevante no ChromaDB para tenant '{tenant_id}': {e}", exc_info=True)
        return []


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
