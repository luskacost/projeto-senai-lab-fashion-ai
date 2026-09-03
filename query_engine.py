# -*- coding: utf-8 -*-
"""Motor de Query Understanding, Expansão, Decomposição e Normalização Leve para RAG.

Implementa:
1. Normalização leve de acentos e correção de typos técnicos frequentes.
2. Classificação determinística e heurística de perguntas (Direct, Conceptual, Comparative, Multi-Concept, Numeric).
3. Expansão semântica controlada.
4. Decomposição multi-hop e relacional em subconsultas atômicas para conexões causais, comparativas e multi-conceito.
"""

import re
import string
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set

from rag_config import RAG_CONFIG


class QueryCategory:
    DIRECT = "DIRECT"
    CONCEPTUAL = "CONCEPTUAL"
    COMPARATIVE = "COMPARATIVE"
    MULTI_CONCEPT = "MULTI_CONCEPT"
    NUMERIC = "NUMERIC"
    TABULAR = "TABULAR"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass
class QueryAnalysis:
    original_query: str
    categories: List[str] = field(default_factory=list)
    is_complex: bool = False
    entities: List[str] = field(default_factory=list)
    key_concepts: List[str] = field(default_factory=list)
    numeric_terms: List[str] = field(default_factory=list)
    expanded_queries: List[str] = field(default_factory=list)
    decomposed_queries: List[str] = field(default_factory=list)
    all_queries: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "categories": self.categories,
            "is_complex": self.is_complex,
            "entities": self.entities,
            "key_concepts": self.key_concepts,
            "numeric_terms": self.numeric_terms,
            "expanded_queries": self.expanded_queries,
            "decomposed_queries": self.decomposed_queries,
            "all_queries": self.all_queries
        }


# ==============================================================================
# NORMALIZAÇÃO LEVE DE TEXTO E CORREÇÃO DE TERMOS TÉCNICOS
# ==============================================================================
def normalizar_texto(texto: str) -> str:
    """Remove acentos e converte para minúsculas para correspondência lexical robusta."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# Dicionário leve de termos técnicos frequentes (sem dependência externa de spell-checker)
DICIONARIO_TERMOS_TECNICOS: Dict[str, str] = {
    "determistica": "determinística",
    "determisticas": "determinísticas",
    "deterministico": "determinístico",
    "deterministicos": "determinísticos",
    "determinstica": "determinística",
    "determinstico": "determinístico",
    "probabilistica": "probabilística",
    "probabilisticas": "probabilísticas",
    "probabilistico": "probabilístico",
    "probabilisticos": "probabilísticos",
    "overfiting": "overfitting",
    "over-fitting": "overfitting",
    "concep drift": "concept drift",
    "concept-drift": "concept drift",
    "data-leakage": "data leakage",
    "dataleakage": "data leakage",
    "cross validation": "cross-validation",
    "cross-validação": "cross-validation",
    "validação cruzada": "validação cruzada",
    "validacao cruzada": "validação cruzada",
    "desambiguacao": "desambiguação",
    "desambiguar": "desambiguação",
    "homonimo": "homônimo",
    "homonimos": "homônimos",
    "slms": "slm",
    "llms": "llm",
    "saida": "saída",
    "saidas": "saídas",
    "algodao": "algodão",
    "poliester": "poliéster",
    "madreperola": "madrepérola",
    "posicao": "posição",
}


def corrigir_termos_query(query: str) -> str:
    """Aplica normalização ortográfica leve para termos técnicos comuns do domínio."""
    # 1. Remove duplicações de palavras adjacentes acidentais (ex: "de de", "a a")
    q_mod = re.sub(r'\b(\w+)\s+\1\b', r'\1', query, flags=re.IGNORECASE)

    # 2. Corrige termos técnicos específicos do domínio
    for erro, correcao in DICIONARIO_TERMOS_TECNICOS.items():
        padrao = r'\b' + re.escape(erro) + r'\b'
        q_mod = re.sub(padrao, correcao, q_mod, flags=re.IGNORECASE)

    return q_mod.strip()


# Stopwords gerais para extração de conceitos
STOPWORDS_PT = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "sob", "sobre", "entre",
    "que", "e", "ou", "mas", "se", "como", "qual", "quais", "onde", "quando", "quem",
    "porque", "por que", "por quê", "quanto", "quantos", "quanta", "quantas", "é", "são",
    "foi", "foram", "ser", "estar", "ter", "haver", "este", "esta", "estes", "estas",
    "esse", "essa", "esses", "essas", "aquele", "aquela", "aqueles", "aquelas", "seu",
    "sua", "seus", "suas", "meu", "minha", "ele", "ela", "eles", "elas", "você", "vocês",
    "apenas", "muito", "mais", "menos", "segundo", "conforme", "deve", "devem", "poderia",
    "ajuda", "ajudar", "ajudam", "usar", "usado", "usada", "apresentado", "apresentada"
}


# ==============================================================================
# FASE 2: CLASSIFICAÇÃO DETERMINÍSTICA DA CONSULTA
# ==============================================================================
def classificar_query(query: str) -> List[str]:
    """Classifica a pergunta em uma ou mais categorias técnicas usando heurísticas leves."""
    q_lower = query.lower().strip()
    q_norm = normalizar_texto(query)
    categorias: Set[str] = set()

    # 1. NUMERIC
    padrao_numerico = (
        re.search(r'\d', q_lower) or
        re.search(r'\b(?:quantos?|quantas?|qual a gramatura|largura|comprimento|di[aâ]metro|pre[cç]o|custo|valor|n[uú]mero|taxa|limite|itera[cç][oõ]es|faixa|par[aâ]metros)\b', q_lower) or
        re.search(r'\b(?:g/m²|g/m2|oz|cm|mm|m|%|r\$|graus|pontos|polegada)\b', q_lower)
    )
    if padrao_numerico:
        categorias.add(QueryCategory.NUMERIC)

    # 2. COMPARATIVE
    padrao_comparativo = (
        re.search(r'\b(?:compare|comparar|compara[cç][aã]o|diferen[cç]as?|distin[cç][aã]o|versus|vs\.?|em rela[cç][aã]o a|ao contr[aá]rio de|enquanto)\b', q_lower) or
        re.search(r'\bqual\s+(?:a\s+)?diferen[cç]a\b', q_lower) or
        re.search(r'\b(?:llms?\s+(?:e|versus|vs)\s+slms?|slms?\s+(?:e|versus|vs)\s+llms?)\b', q_lower) or
        re.search(r'\b(?:m518\s+(?:e|versus|vs)\s+millie|millie\s+(?:e|versus|vs)\s+m518)\b', q_lower)
    )
    if padrao_comparativo:
        categorias.add(QueryCategory.COMPARATIVE)

    # 3. MULTI_CONCEPT (Multi-Hop / Relações causais, funcionais ou listas com múltiplos conceitos)
    padrao_multi_conceito = (
        re.search(r'([A-Za-z0-9\-_]{3,}(?: [A-Za-z0-9\-_]{3,})?),\s*([A-Za-z0-9\-_]{3,}(?: [A-Za-z0-9\-_]{3,})?)\s+(?:e|al[eé]m de|bem como)\s+([A-Za-z0-9\-_]{3,})', q_lower) or
        ("," in q_lower and (" e " in q_lower or " bem como " in q_lower or " alem de " in q_norm)) or
        ("parâmetros" in q_lower and "hardware" in q_lower and "casos de uso" in q_lower) or
        (q_lower.count(" e ") >= 2 and len(q_lower.split()) > 7) or
        # Relações funcionais / causais / multi-hop
        re.search(r'(?:como|de que forma|por que|qual a rela[cç][aã]o)\s+(?:o|a|os|as)?\s*.+?\s+(?:ajuda a|protege contra|mitiga|atua contra|impacta|influencia|relaciona-se com|se relaciona com|causa)\s+.+', q_lower)
    )
    if padrao_multi_conceito:
        categorias.add(QueryCategory.MULTI_CONCEPT)

    # 4. CONCEPTUAL
    padrao_conceitual = (
        re.search(r'^(?:por\s*que|por\s*qu[eê]|como|explique|qual\s+o\s+papel|qual\s+a\s+import[aâ]ncia|qual\s+o\s+conceito|o\s+que\s+[eé]|qual\s+a\s+rela[cç][aã]o|para\s+que\s+serve|descreva|qual\s+costuma\s+ser\s+a\s+sa[ií]da|qual\s+a\s+sa[ií]da)\b', q_lower) or
        re.search(r'\b(?:conceito|importante|interpretar|ambiguidade|desambigua[cç][aã]o|significado|funciona|funcionamento|proteger contra|prote[cç][aã]o|determinist|probabilist)\b', q_norm)
    )
    if padrao_conceitual:
        categorias.add(QueryCategory.CONCEPTUAL)

    # 5. TABULAR
    padrao_tabular = (
        re.search(r'\b(?:quantos?|quantas?|soma|somatorio|somatório|media|média|médio|medio|maior|menor|ranking|lidera|tabela|planilha|csv|vencedor|campeao|campeão|vice|premio|prêmio|premiacao|premiação|prize pool|pontos|classificacao|classificação|participantes|roster|jogadores)\b', q_norm)
    )
    if padrao_tabular:
        categorias.add(QueryCategory.TABULAR)

    # 6. DIRECT (Se não for puramente conceitual nem multi-conceito, ou se for uma busca factual simples)
    if not categorias or QueryCategory.NUMERIC in categorias or QueryCategory.TABULAR in categorias:
        if QueryCategory.MULTI_CONCEPT not in categorias and QueryCategory.COMPARATIVE not in categorias:
            categorias.add(QueryCategory.DIRECT)

    # Garante ao menos uma classificação
    if not categorias:
        categorias.add(QueryCategory.DIRECT)

    return sorted(list(categorias))


# ==============================================================================
# FASE 3: QUERY EXPANSION CONTROLADA
# ==============================================================================
def _extrair_termos_significativos(texto: str) -> List[str]:
    """Extrai palavras e termos significativos removendo stopwords e pontuação."""
    texto_limpo = re.sub(r'[^\w\s\-_/]', ' ', texto.lower())
    palavras = [p.strip() for p in texto_limpo.split() if len(p.strip()) > 2]
    return [p for p in palavras if p not in STOPWORDS_PT]


def expandir_query(query: str, categorias: List[str], config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Gera expansões controladas para consultas conceituais, comparativas ou multi-conceito.

    Preserva a query original e limita entre 2 e 4 variações de alta relevância.
    """
    cfg = config or RAG_CONFIG
    if not cfg.get("enable_query_expansion", True):
        return []

    q_lower = query.lower().strip()
    q_norm = normalizar_texto(query)
    termos = _extrair_termos_significativos(query)
    max_exp = cfg.get("max_expanded_queries", 3)
    expansoes: List[str] = []

    # Expansão para IA Determinística vs Probabilística
    if "determinist" in q_norm or "probabilist" in q_norm:
        if "saida" in q_norm or "entrada" in q_norm:
            expansoes.append("IA determinística mesma entrada mesma saída")
            expansoes.append("saída de uma IA determinística")
            expansoes.append("diferença entre IA determinística e probabilística")
        else:
            expansoes.append("IA determinística características e funcionamento")
            expansoes.append("modelo de IA determinístico vs probabilístico")

    # Expansão para Conceito de Contexto e Desambiguação
    elif "contexto" in q_norm and ("banco" in q_norm or "palavra" in q_norm or "ambiguidade" in q_norm or "interpretar" in q_norm):
        if "banco" in q_norm:
            expansoes.append("contexto significado da palavra banco")
            expansoes.append("palavra ambígua banco desambiguação pelo contexto")
            expansoes.append("interpretação contextual de termos homônimos")
        elif "ambiguidade" in q_norm or "reduzir" in q_norm:
            expansoes.append("contexto ambiguidade linguagem natural")
            expansoes.append("desambiguação de termos e significado contextual")
            expansoes.append("interpretação de palavras pelo contexto em IA")
        else:
            expansoes.append("importância do contexto na interpretação de palavras")
            expansoes.append("desambiguação contextual de significados")

    # Expansão para K-Fold e Machine Learning
    elif "k-fold" in q_norm or "cross-validation" in q_norm or "validacao cruzada" in q_norm:
        if "overfitting" in q_norm or "data leakage" in q_norm or "concept drift" in q_norm:
            expansoes.append("K-Fold Cross-Validation validação cruzada overfitting")
            expansoes.append("K-Fold proteção contra data leakage vazamento de dados")
            expansoes.append("K-Fold concept drift e generalização do modelo")
        else:
            expansoes.append("K-Fold Cross-Validation divisão em folds iterações")
            expansoes.append("validação cruzada particionamento treino validação")

    # Expansão para LLMs vs SLMs
    elif "llm" in q_norm or "slm" in q_norm:
        if "parametro" in q_norm or "hardware" in q_norm or "caso" in q_norm or "execucao" in q_norm:
            expansoes.append("LLM vs SLM parâmetros hardware execução")
            expansoes.append("Small Language Models SLMs requisitos de memória e casos de uso")
            expansoes.append("Large Language Models LLMs infraestrutura e custos computacionais")
        else:
            expansoes.append("comparação Large Language Models e Small Language Models")
            expansoes.append("diferenças entre modelos LLM e SLM")

    # Expansão Genérica baseada em palavras-chave relevantes
    if not expansoes and (QueryCategory.CONCEPTUAL in categorias or QueryCategory.MULTI_CONCEPT in categorias):
        if len(termos) >= 2:
            expansoes.append(" ".join(termos))
            # Variação com termos principais
            if len(termos) >= 3:
                expansoes.append(f"{termos[0]} {termos[1]} {termos[-1]}")

    # Deduplicação e limitação
    resultado: List[str] = []
    for exp in expansoes:
        exp_clean = exp.strip()
        if exp_clean and exp_clean.lower() != q_lower and exp_clean not in resultado:
            resultado.append(exp_clean)
        if len(resultado) >= max_exp:
            break

    return resultado


# ==============================================================================
# FASE 4: QUERY DECOMPOSITION MULTI-HOP (SUB-CONSULTAS)
# ==============================================================================
def decompor_query(query: str, categorias: List[str], config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Decompõe consultas complexas (multi-hop, relacionais, multi-conceito ou comparativas)

    em subconsultas atômicas para garantir resgate de evidências distribuídas.
    """
    cfg = config or RAG_CONFIG
    if not cfg.get("enable_query_decomposition", True):
        return []

    q_lower = query.lower().strip()
    q_norm = normalizar_texto(query)
    max_decomp = cfg.get("max_decomposed_queries", 6)
    subqueries: List[str] = []

    # 1. Decomposição Relacional Genérica (Multi-Hop Causal/Funcional)
    # Detecta: "Como X ajuda a proteger contra Y, Z e W", "De que forma X impacta Y", etc.
    padrao_relacional = re.search(
        r'(?:como|de que forma|por que|qual a rela[cç][aã]o(?:\s+entre)?)\s+(?:o|a|os|as)?\s*(.+?)\s+(?:ajuda a|protege contra|mitiga|atua contra|impacta|influencia|relaciona-se com|se relaciona com|causa|difere de)\s+(.+)',
        q_lower,
        re.IGNORECASE
    )

    if padrao_relacional:
        ancora = padrao_relacional.group(1).strip()
        alvos_str = padrao_relacional.group(2).strip()

        # Limpa artigos e conectores da âncora
        ancora = re.sub(r'^(?:o|a|os|as|um|uma)\s+', '', ancora, flags=re.IGNORECASE).strip(" ?.,;")

        # Divide os múltiplos alvos/conceitos
        partes = re.split(r'[,;]|\s+e\s+|\s+al[eé]m de\s+|\s+bem como\s+', alvos_str)
        alvos_limpos = []
        for p in partes:
            p_clean = p.strip(" ?.,;")
            # Remove verbos/preposições no início de cada alvo
            p_clean = re.sub(r'^(?:proteger contra|protegendo contra|mitigar|reduzir|contra|de|sobre|para|em)\s+', '', p_clean, flags=re.IGNORECASE).strip()
            if len(p_clean) > 2 and p_clean not in STOPWORDS_PT:
                alvos_limpos.append(p_clean)

        if ancora and alvos_limpos:
            # Subquery da entidade principal isolada
            subqueries.append(f"{ancora} conceito")
            # Subqueries de cada conceito alvo isolado
            for alvo in alvos_limpos:
                subqueries.append(alvo)
            # Subqueries de pares combinados
            for alvo in alvos_limpos:
                subqueries.append(f"{ancora} e {alvo}")

    # 2. Decomposição para Comparações Multi-Atributos (ex: LLMs vs SLMs)
    elif ("llm" in q_norm and "slm" in q_norm) or ("m518" in q_norm and "millie" in q_norm):
        if "llm" in q_norm and "slm" in q_norm:
            atributos = []
            if "parametro" in q_norm:
                atributos.append("parâmetros")
            if "hardware" in q_norm or "memoria" in q_norm:
                atributos.append("hardware")
            if "execucao" in q_norm:
                atributos.append("execução")
            if "caso" in q_norm or "uso" in q_norm:
                atributos.append("casos de uso")

            if atributos:
                for at in atributos:
                    subqueries.append(f"LLM {at}")
                    subqueries.append(f"SLM {at}")
            else:
                subqueries.append("LLM Large Language Models características")
                subqueries.append("SLM Small Language Models características")

        elif "m518" in q_norm and "millie" in q_norm:
            subqueries.append("Tecido M518 especificações técnicas gramatura composição")
            subqueries.append("Tecido Millie Denim Maskskin especificações técnicas gramatura composição")

    # 3. Decomposição Heurística para Listas de Conceitos Separados por Vírgula/Conjunção
    if not subqueries and QueryCategory.MULTI_CONCEPT in categorias:
        match_lista = re.search(r'(?:sobre|contra|de|entre)\s+(.+)$', q_lower)
        trecho_alvo = match_lista.group(1) if match_lista else q_lower

        # Divide por vírgula ou " e "
        partes = re.split(r'[,;]|\s+e\s+|\s+al[eé]m de\s+|\s+bem como\s+', trecho_alvo)
        partes_limpas = [p.strip() for p in partes if len(p.strip()) > 2 and p.strip() not in STOPWORDS_PT]

        if len(partes_limpas) >= 2:
            termo_ancora = ""
            for t in ["k-fold", "modelo", "tecido", "camisa", "sistema", "contexto", "logotipo", "ia"]:
                if t in q_norm:
                    termo_ancora = t
                    break

            for p in partes_limpas[:max_decomp]:
                if termo_ancora and termo_ancora not in normalizar_texto(p):
                    subqueries.append(f"{termo_ancora} {p}")
                else:
                    subqueries.append(p)

    # Limita e deduplica
    resultado: List[str] = []
    for sub in subqueries:
        sub_clean = sub.strip()
        if sub_clean and sub_clean.lower() != q_lower and sub_clean not in resultado:
            resultado.append(sub_clean)
        if len(resultado) >= max_decomp:
            break

    return resultado


# ==============================================================================
# FUNÇÃO PRINCIPAL DE ANÁLISE DE CONSULTA (QUERY UNDERSTANDING)
# ==============================================================================
def analisar_query_completa(query: str, config: Optional[Dict[str, Any]] = None) -> QueryAnalysis:
    """Executa a análise completa de Query Understanding:

    1. Correção ortográfica leve e normalização de termos técnicos.
    2. Classificação em categorias semânticas.
    3. Extração de entidades e termos numéricos.
    4. Expansão controlada e Decomposição multi-hop.
    """
    cfg = config or RAG_CONFIG
    
    # 1. Normalização e correção leve
    query_corrigida = corrigir_termos_query(query)
    
    # Usa a versão corrigida (ou original) para classificação e extração
    query_base = query_corrigida if query_corrigida != query else query
    categorias = classificar_query(query_base)
    is_complex = any(cat in (QueryCategory.CONCEPTUAL, QueryCategory.COMPARATIVE, QueryCategory.MULTI_CONCEPT) for cat in categorias)

    # Extrai termos numéricos
    termos_num = re.findall(r'\b\d+(?:[.,]\d+)?\s*(?:g/m²|g/m2|oz|cm|mm|m|%|r\$|itera[cç][oõ]es|par[aâ]metros)?\b', query_base, re.IGNORECASE)

    # Extrai conceitos chave
    termos_chave = _extrair_termos_significativos(query_base)

    # Executa expansão e decomposição se ativados e necessários
    expanded = []
    decomposed = []
    if is_complex:
        expanded = expandir_query(query_base, categorias, cfg)
        decomposed = decompor_query(query_base, categorias, cfg)

    # Compila lista total de queries a serem consultadas (Original SEMPRE primeira)
    todas_queries = [query]
    if query_corrigida != query and query_corrigida not in todas_queries:
        todas_queries.append(query_corrigida)

    for q_item in expanded + decomposed:
        if q_item not in todas_queries:
            todas_queries.append(q_item)

    return QueryAnalysis(
        original_query=query,
        categories=categorias,
        is_complex=is_complex,
        key_concepts=termos_chave,
        numeric_terms=[t.strip() for t in termos_num if t.strip()],
        expanded_queries=expanded,
        decomposed_queries=decomposed,
        all_queries=todas_queries
    )
