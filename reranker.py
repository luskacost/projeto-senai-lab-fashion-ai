# -*- coding: utf-8 -*-
"""Módulo de Reranking Desacoplado, Scoring Híbrido e Seleção com Diversidade/Cobertura.

Define a interface abstrata BaseReranker, o HeuristicReranker ponderado,
fusão e deduplicação de multi-queries, e seleção com cobertura conceitual e diversidade.
"""

import abc
import math
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple

from rag_config import RAG_CONFIG
from query_engine import QueryAnalysis, QueryCategory, normalizar_texto


@dataclass
class CandidateChunk:
    chunk_id: str
    texto: str
    metadata: Dict[str, Any]
    pagina: int = 1
    fonte: str = "Documento"
    vector_distance: float = 1.0
    vector_score: float = 0.0
    retrieval_queries: List[str] = field(default_factory=list)
    retrieval_count: int = 1
    lexical_score: float = 0.0
    frequency_score: float = 0.0
    metadata_score: float = 0.0
    final_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    matched_concepts: Set[str] = field(default_factory=set)
    is_relevant: bool = True
    discard_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "chunk_id": self.chunk_id,
            "texto": self.texto,
            "metadata": self.metadata,
            "pagina": self.pagina,
            "fonte": self.fonte,
            "rotulo_unidade": self.metadata.get("rotulo_unidade", f"Página {self.pagina}"),
            "tipo_arquivo": self.metadata.get("tipo_arquivo", "pdf"),
            "secao": self.metadata.get("secao", ""),
            "produto": self.metadata.get("produto", ""),
            "modelo": self.metadata.get("modelo", ""),
            "variante": self.metadata.get("variante", ""),
            "material": self.metadata.get("material", ""),
            "distancia": self.vector_distance,
            "vector_score": round(self.vector_score, 4),
            "lexical_score": round(self.lexical_score, 4),
            "frequency_score": round(self.frequency_score, 4),
            "metadata_score": round(self.metadata_score, 4),
            "score": round(self.final_score, 4),
            "detalhes_score": self.score_breakdown,
            "retrieval_queries": self.retrieval_queries,
            "retrieval_count": self.retrieval_count,
            "matched_concepts": list(self.matched_concepts),
            "is_relevant": self.is_relevant,
            "discard_reason": self.discard_reason
        }
        for campo in ["aba", "linha", "slide", "secao_origem"]:
            if campo in self.metadata:
                d[campo] = self.metadata[campo]
        return d


# ==============================================================================
# FASE 6: FUSÃO E DEDUPLICAÇÃO DE CANDIDATOS
# ==============================================================================
def fundir_e_deduplicar_candidatos(
    resultados_por_query: Dict[str, List[Dict[str, Any]]]
) -> List[CandidateChunk]:
    """Funde resultados de múltiplas queries e deduplica por chunk_id e similaridade de texto.

    Registra a contagem de vezes que o chunk foi resgatado (retrieval_count).
    """
    candidatos_map: Dict[str, CandidateChunk] = {}

    for query, lista_cands in resultados_por_query.items():
        for cand in lista_cands:
            c_id = str(cand.get("id") or cand.get("chunk_id") or "")
            texto = cand.get("texto") or cand.get("document") or ""
            meta = cand.get("meta") or cand.get("metadata") or {}
            dist = float(cand.get("dist") if cand.get("dist") is not None else cand.get("distance", 1.0))

            # Similaridade de cosseno a partir da distância euclidiana normalizada do ChromaDB
            cos_sim = max(0.0, 1.0 - (dist ** 2) / 2.0)

            # Chave de unicidade (chunk_id ou hash do texto)
            chave = c_id if c_id else f"h_{hash(texto)}"

            if chave in candidatos_map:
                existente = candidatos_map[chave]
                existente.retrieval_count += 1
                if query not in existente.retrieval_queries:
                    existente.retrieval_queries.append(query)
                # Mantém a melhor similaridade vetorial observada
                if cos_sim > existente.vector_score:
                    existente.vector_score = cos_sim
                    existente.vector_distance = dist
            else:
                candidatos_map[chave] = CandidateChunk(
                    chunk_id=chave,
                    texto=texto,
                    metadata=meta,
                    pagina=int(meta.get("pagina", 1)),
                    fonte=str(meta.get("fonte", "Documento")),
                    vector_distance=dist,
                    vector_score=cos_sim,
                    retrieval_queries=[query],
                    retrieval_count=1
                )

    return list(candidatos_map.values())


# ==============================================================================
# FASE 7: HYBRID & LEXICAL BOOSTING (COM SUPORTE A NORMALIZAÇÃO DE ACENTOS)
# ==============================================================================
def calcular_score_lexical(
    query_analysis: QueryAnalysis,
    chunk_texto: str,
    config: Optional[Dict[str, Any]] = None
) -> Tuple[float, Set[str]]:
    """Calcula o score de correspondência lexical exata, n-grams, códigos e medidas técnicas.

    Utiliza correspondência tanto com acentos originais quanto normalizada (sem acentos).
    """
    cfg = config or RAG_CONFIG
    lex_weights = cfg.get("lexical_weights", {})
    chunk_lower = chunk_texto.lower()
    chunk_norm = normalizar_texto(chunk_texto)
    q_original_lower = query_analysis.original_query.lower()
    q_original_norm = normalizar_texto(query_analysis.original_query)

    score = 0.0
    matched_concepts: Set[str] = set()

    # 1. Correspondência de Frase Exata (com ou sem acento)
    if len(q_original_lower) > 8 and (q_original_lower in chunk_lower or q_original_norm in chunk_norm):
        score += lex_weights.get("exact_phrase", 0.25)

    # 2. Correspondência de Conceitos Chave e Termos Significativos
    total_conceitos = len(query_analysis.key_concepts)
    if total_conceitos > 0:
        matches = 0
        for conceito in query_analysis.key_concepts:
            c_low = conceito.lower()
            c_norm = normalizar_texto(conceito)
            # Match exato, normalizado ou stem plural
            if (c_low in chunk_lower or c_norm in chunk_norm or
                (len(c_norm) > 3 and c_norm.rstrip('s') in chunk_norm)):
                matches += 1
                matched_concepts.add(conceito)

        taxa_cobertura = matches / total_conceitos
        score += (taxa_cobertura * 0.40)

    # 3. Bônus para Códigos Técnicos Alfanuméricos (ex: M518, CF-2026, etc.)
    codigos_query = re.findall(r'\b[A-Za-z]+[-_]?\d+[A-Za-z0-9]*\b|\b\d+[A-Za-z]+[0-9]*\b', query_analysis.original_query)
    for cod in codigos_query:
        if cod.lower() in chunk_lower:
            score += lex_weights.get("technical_code", 0.20)
            matched_concepts.add(cod)

    # 4. Bônus para Números e Medidas Específicas
    for num_termo in query_analysis.numeric_terms:
        if num_termo.lower() in chunk_lower or normalizar_texto(num_termo) in chunk_norm:
            score += lex_weights.get("number_unit", 0.15)
            matched_concepts.add(num_termo)

    # 5. Palavras-Chave de Alta Relevância do Domínio (Têxtil / IA / Cibersegurança / ML)
    palavras_chave_altas = {
        "millie", "maskskin", "liocel", "tafeta", "tafetá", "bandeirola", "chimango",
        "patte", "puídos", "maquinetado", "fieg", "dtf", "serigrafia", "tnt", "tex",
        "xgg", "pp", "gramatura", "largura", "punho", "gola", "barra", "botão", "botões",
        "etiqueta", "bordado", "pontos", "polegada", "tamanho", "tamanhos", "grade", "cor", "cores",
        "k-fold", "overfitting", "concept drift", "data leakage", "vazamento de dados",
        "desambiguação", "homônimo", "slm", "llm", "parâmetros", "hardware", "inferência",
        "determinística", "probabilística", "deterministica", "probabilistica", "transformer",
        "transformers", "atenção", "fine-tuning", "alinhamento", "prompt"
    }

    for kw in palavras_chave_altas:
        kw_norm = normalizar_texto(kw)
        if (kw in q_original_lower or kw_norm in q_original_norm) and (kw in chunk_lower or kw_norm in chunk_norm):
            score += lex_weights.get("domain_keyword", 0.12)
            matched_concepts.add(kw)

    # 6. Sobreposição de N-grams Significativos (Bi-grams e Tri-grams de entidades/termos)
    stopwords_ng = {"qual", "quem", "como", "onde", "para", "com", "por", "que", "uma", "uns", "das", "dos", "da", "do", "de", "a", "o", "e"}
    palavras_limpas = [re.sub(r'[^a-zA-Z0-9áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]', '', w.lower()) for w in q_original_lower.split()]
    termos_significativos = [normalizar_texto(w) for w in palavras_limpas if len(w) >= 2 and normalizar_texto(w) not in stopwords_ng]
    if len(termos_significativos) >= 2:
        encontrou_ngram = False
        for n in (3, 2):
            if encontrou_ngram:
                break
            for i in range(len(termos_significativos) - n + 1):
                ngram = " ".join(termos_significativos[i:i+n])
                if len(ngram) >= 4 and ngram in chunk_norm:
                    w_ng = lex_weights.get("ngram_overlap", 0.20)
                    score += w_ng
                    matched_concepts.add(ngram)
                    encontrou_ngram = True
                    break

    return min(1.0, score), matched_concepts


# ==============================================================================
# FASE 8: INTERFACE DE RERANKING DESACOPLADA
# ==============================================================================
class BaseReranker(abc.ABC):
    """Interface abstrata base para rerankers do pipeline RAG."""

    @abc.abstractmethod
    def rerank(
        self,
        query_analysis: QueryAnalysis,
        candidates: List[CandidateChunk],
        config: Optional[Dict[str, Any]] = None
    ) -> List[CandidateChunk]:
        pass


class HeuristicReranker(BaseReranker):
    """Reranker Heurístico de Alta Performance combinando vetorial, léxico, frequência e metadados."""

    def rerank(
        self,
        query_analysis: QueryAnalysis,
        candidates: List[CandidateChunk],
        config: Optional[Dict[str, Any]] = None
    ) -> List[CandidateChunk]:
        cfg = config or RAG_CONFIG
        weights = cfg.get("weights", {
            "vector": 0.40,
            "lexical": 0.35,
            "frequency": 0.15,
            "metadata": 0.10
        })

        q_lower = query_analysis.original_query.lower()
        q_norm = normalizar_texto(query_analysis.original_query)
        num_queries_total = max(1, len(query_analysis.all_queries))

        for cand in candidates:
            # 1. Score Lexical (com normalização de acentos)
            lex_score, matched_c = calcular_score_lexical(query_analysis, cand.texto, cfg)
            cand.lexical_score = lex_score
            cand.matched_concepts = matched_c

            # 2. Score de Frequência de Recuperação Multi-Query
            cand.frequency_score = min(1.0, (cand.retrieval_count / num_queries_total) * 1.5)

            # 3. Score de Metadados e Isolamento de Variantes
            meta_score = 0.0
            meta = cand.metadata
            chunk_low = cand.texto.lower()

            pede_jeans = ("jeans" in q_norm or "millie" in q_norm or "denim" in q_norm)
            pede_m518 = ("m518" in q_norm)
            pede_masculina = ("masculin" in q_norm or "homem" in q_norm)
            pede_feminina = ("feminin" in q_norm or "camisete" in q_norm or "mulher" in q_norm)

            tem_jeans = ("jeans" in chunk_low or "millie" in chunk_low or meta.get("variante") == "Jeans")
            tem_m518 = ("m518" in chunk_low or meta.get("variante") == "M518")

            if pede_jeans and pede_m518:
                if tem_jeans or tem_m518:
                    meta_score += 0.25
            elif pede_jeans:
                if tem_jeans:
                    meta_score += 0.25
                elif tem_m518:
                    meta_score -= 0.40
            elif pede_m518:
                if tem_m518:
                    meta_score += 0.25
                elif tem_jeans:
                    meta_score -= 0.40

            if pede_masculina and not pede_feminina:
                if meta.get("modelo") == "Masculino":
                    meta_score += 0.20
                elif meta.get("modelo") == "Feminino":
                    meta_score -= 0.20
            elif pede_feminina and not pede_masculina:
                if meta.get("modelo") == "Feminino":
                    meta_score += 0.20
                elif meta.get("modelo") == "Masculino":
                    meta_score -= 0.20

            # Priorização de especificações de modelagem vs referências espaciais
            if "tipo de gola" in q_norm or ("gola" in q_norm and "altura" not in q_norm and "logotipo" not in q_norm):
                if "pe de gola" in normalizar_texto(chunk_low) or "gola camisa" in normalizar_texto(chunk_low):
                    meta_score += 0.30
                elif "abaixo da gola" in normalizar_texto(chunk_low) and "estamparia" in normalizar_texto(meta.get("secao", "")):
                    meta_score -= 0.20

            # 3.1 Bônus de Fonte Estruturada para Queries Tabulares (Requisitos 15, 16)
            is_tab_query = (
                QueryCategory.TABULAR in query_analysis.categories or
                QueryCategory.NUMERIC in query_analysis.categories or
                any(t in q_norm for t in ["quantos", "soma", "media", "maior", "menor", "ranking", "premio", "pontos", "vencedor", "tabela", "planilha"])
            )
            tipo_arq = str(meta.get("tipo_arquivo", "")).lower()
            fonte_low = cand.fonte.lower()
            is_structured = tipo_arq in ("csv", "xlsx", "xls", "tabular") or fonte_low.endswith((".csv", ".xlsx", ".xls"))
            if is_tab_query and is_structured:
                meta_score += 0.15

            cand.metadata_score = meta_score

            # 4. Cálculo Ponderado Final
            w_vec = weights.get("vector", 0.40)
            w_lex = weights.get("lexical", 0.35)
            w_freq = weights.get("frequency", 0.15)
            w_meta = weights.get("metadata", 0.10)

            score_bruto = (
                (w_vec * cand.vector_score) +
                (w_lex * cand.lexical_score) +
                (w_freq * cand.frequency_score) +
                (w_meta * cand.metadata_score)
            )

            cand.final_score = max(0.0, min(1.0, score_bruto))
            cand.score_breakdown = {
                "vector": round(cand.vector_score, 4),
                "lexical": round(cand.lexical_score, 4),
                "frequency": round(cand.frequency_score, 4),
                "metadata": round(cand.metadata_score, 4),
                "final": round(cand.final_score, 4)
            }

        # Ordena candidatos por score final decrescente
        candidates.sort(key=lambda x: x.final_score, reverse=True)
        return candidates


# ==============================================================================
# FASE 9: DIVERSIDADE E COBERTURA CONCEITUAL
# ==============================================================================
def _calcular_similaridade_jaccard(texto1: str, texto2: str) -> float:
    """Calcula similaridade de Jaccard baseada em conjunto de palavras."""
    palavras1 = set(texto1.lower().split())
    palavras2 = set(texto2.lower().split())
    if not palavras1 or not palavras2:
        return 0.0
    intersecao = len(palavras1.intersection(palavras2))
    uniao = len(palavras1.union(palavras2))
    return intersecao / uniao if uniao > 0 else 0.0


def selecionar_com_cobertura_e_diversidade(
    ranked_candidates: List[CandidateChunk],
    query_analysis: QueryAnalysis,
    config: Optional[Dict[str, Any]] = None,
    final_k: int = 5
) -> List[CandidateChunk]:
    """Seleciona o conjunto final de chunks aplicando:
    1. Threshold absoluto mínimo (min_rerank_score / similarity_threshold).
    2. Threshold relativo de qualidade proporcional ao melhor score (relative_score_threshold).
    3. Cobertura de entidades/conceitos para queries comparativas e multi-conceito.
    4. Deduplicação e diversidade balanceada (Jaccard similarity).
    5. Anti-saturação de Markdown/README para consultas tabulares (Requisito 13, 14).
    6. Rastreabilidade de motivos de descarte em cada candidato para observabilidade.
    """
    cfg = config or RAG_CONFIG
    min_score_abs = float(cfg.get("min_rerank_score", cfg.get("similarity_threshold", 0.20)))
    rel_thresh = float(cfg.get("relative_score_threshold", 0.55))
    diversity_cfg = cfg.get("diversity", {})
    max_sim = float(diversity_cfg.get("max_similarity_between_chunks", 0.85))

    if not ranked_candidates:
        return []

    best_score = ranked_candidates[0].final_score

    # Se o melhor score geral for muito fraco, descarta todos (evita alucinação)
    if best_score < min_score_abs:
        for c in ranked_candidates:
            c.is_relevant = False
            c.discard_reason = f"Abaixo do score mínimo absoluto ({c.final_score:.4f} < {min_score_abs:.4f})"
        return []

    # Threshold dinâmico relativo ao melhor candidato
    cutoff_score = max(min_score_abs, best_score * rel_thresh)

    candidatos_validos: List[CandidateChunk] = []
    for c in ranked_candidates:
        if c.final_score >= cutoff_score:
            c.is_relevant = True
            c.discard_reason = ""
            candidatos_validos.append(c)
        else:
            c.is_relevant = False
            c.discard_reason = f"Score ({c.final_score:.4f}) abaixo do threshold relativo ({cutoff_score:.4f} = {rel_thresh:.2f} * {best_score:.4f})"

    if not candidatos_validos:
        return []

    if not cfg.get("enable_diversity", True):
        return candidatos_validos[:final_k]

    selecionados: List[CandidateChunk] = []
    conceitos_cobertos: Set[str] = set()

    # Configuração de Anti-Saturação de Markdown / README
    enable_anti_sat = cfg.get("enable_markdown_anti_saturation", True)
    markdown_cap = int(cfg.get("markdown_max_chunks_for_tabular_query", 1))
    is_tab_query = (
        QueryCategory.TABULAR in query_analysis.categories or
        QueryCategory.NUMERIC in query_analysis.categories or
        any(t in normalizar_texto(query_analysis.original_query) for t in ["quantos", "soma", "media", "maior", "menor", "ranking", "premio", "pontos", "vencedor", "tabela", "planilha"])
    )

    def _eh_markdown(c: CandidateChunk) -> bool:
        return c.fonte.lower().endswith((".md", ".markdown")) or str(c.metadata.get("tipo_arquivo", "")).lower() in ("md", "markdown")

    # 1. Trata Consultas Comparativas: Garante representação de ambas as entidades
    if QueryCategory.COMPARATIVE in query_analysis.categories:
        q_norm = normalizar_texto(query_analysis.original_query)
        entidades: List[str] = []
        if "llm" in q_norm and "slm" in q_norm:
            entidades = ["llm", "slm"]
        elif "m518" in q_norm and "millie" in q_norm:
            entidades = ["m518", "millie"]

        if entidades:
            for ent in entidades:
                for cand in candidatos_validos:
                    if cand not in selecionados and ent in normalizar_texto(cand.texto):
                        selecionados.append(cand)
                        conceitos_cobertos.add(ent)
                        break

    # 2. Trata Consultas Multi-Conceito e Multi-Hop: Garante representação dos conceitos individuais
    if QueryCategory.MULTI_CONCEPT in query_analysis.categories:
        q_norm = normalizar_texto(query_analysis.original_query)

        conceitos_alvo = [
            "k-fold", "overfitting", "concept drift", "data leakage", "vazamento de dados",
            "validação cruzada", "desambiguação", "parâmetros", "hardware", "execução",
            "casos de uso", "data augmentation", "data balancing", "fine-tuning", "transformers", "banco"
        ]
        sub_conceitos = [c for c in conceitos_alvo if normalizar_texto(c) in q_norm]

        if not sub_conceitos:
            sub_conceitos = [c for c in query_analysis.key_concepts if len(c) > 3]

        for sc in sub_conceitos:
            sc_norm = normalizar_texto(sc)
            if sc_norm not in conceitos_cobertos:
                for cand in candidatos_validos:
                    if cand not in selecionados and sc_norm in normalizar_texto(cand.texto):
                        selecionados.append(cand)
                        conceitos_cobertos.add(sc_norm)
                        break

    # 3. Preenche as vagas restantes selecionando os melhores scores com controle de anti-saturação
    for cand in candidatos_validos:
        if len(selecionados) >= final_k:
            break
        if cand in selecionados:
            continue

        # Aplica regra de Anti-Saturação para Markdown quando a query é tabular
        if enable_anti_sat and is_tab_query and _eh_markdown(cand):
            md_selecionados_count = sum(1 for s in selecionados if _eh_markdown(s))
            tem_candidato_estruturado_restante = any(
                c not in selecionados and not _eh_markdown(c) and c.final_score >= cutoff_score
                for c in candidatos_validos
            )
            if md_selecionados_count >= markdown_cap and tem_candidato_estruturado_restante:
                cand.discard_reason = f"Anti-saturação: limite de {markdown_cap} chunk(s) de Markdown atingido para query tabular."
                continue

        eh_redundante = False
        for sel in selecionados:
            sim = _calcular_similaridade_jaccard(cand.texto, sel.texto)
            if sim > max_sim:
                eh_redundante = True
                cand.discard_reason = f"Descartado por redundância com chunk selecionado (Jaccard {sim:.2f} > {max_sim:.2f})"
                break

        if not eh_redundante:
            selecionados.append(cand)
            conceitos_cobertos.update(cand.matched_concepts)

    return selecionados
