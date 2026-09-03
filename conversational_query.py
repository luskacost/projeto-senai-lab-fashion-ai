# -*- coding: utf-8 -*-
"""Módulo de Query Rewriting Conversacional, Resolução de Anáforas e Memória de Entidades Fatuais.

Implementa uma camada de Query Understanding Conversacional antes da classificação tabular
e do retrieval vetorial no RAG, permitindo resolver pronomes, continuações curtas, anáforas e
referências a conjuntos de resultados anteriores.
"""

import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from logger_config import obter_logger
from rag_config import RAG_CONFIG


# ─────────────────────────────────────────────────────────────────────────────
# ESTRUTURAS DE DADOS CONVERSACIONAIS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConversationEntity:
    """Representa uma entidade factual extraída do contexto documental ou tabular."""
    text: str
    entity_type: str  # 'person', 'company', 'product', 'fabric', 'metric', 'general'
    source: str       # 'tabular', 'vector', 'metadata'
    turn_index: int
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "source": self.source,
            "turn_index": self.turn_index,
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationEntity":
        return cls(
            text=data.get("text", ""),
            entity_type=data.get("entity_type", "general"),
            source=data.get("source", "vector"),
            turn_index=data.get("turn_index", 0),
            confidence=float(data.get("confidence", 1.0)),
            metadata=data.get("metadata", {})
        )


@dataclass
class ConversationTurn:
    """Representa um turno de conversa armazenado na memória estruturada."""
    turn_index: int
    user_query: str
    rewritten_query: Optional[str]
    assistant_answer: str
    entities: List[ConversationEntity] = field(default_factory=list)
    tabular_result: Optional[Dict[str, Any]] = None
    sources: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "user_query": self.user_query,
            "rewritten_query": self.rewritten_query,
            "assistant_answer": self.assistant_answer,
            "entities": [e.to_dict() for e in self.entities],
            "tabular_result": self.tabular_result,
            "sources": self.sources,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationTurn":
        entities = [ConversationEntity.from_dict(e) for e in data.get("entities", [])]
        return cls(
            turn_index=data.get("turn_index", 0),
            user_query=data.get("user_query", ""),
            rewritten_query=data.get("rewritten_query"),
            assistant_answer=data.get("assistant_answer", ""),
            entities=entities,
            tabular_result=data.get("tabular_result"),
            sources=data.get("sources", []),
            timestamp=data.get("timestamp", "")
        )


@dataclass
class QueryRewriteResult:
    """Resultado do processo de resolução e reescrita conversacional."""
    original_query: str
    rewritten_query: str
    requires_context: bool
    context_resolved: bool
    dependency_type: str  # 'PRONOUN', 'IMPLICIT_CONTINUATION', 'SET_REFERENCE', 'NONE'
    entities_used: List[str] = field(default_factory=list)
    rewrite_confidence: float = 1.0
    fallback_reason: Optional[str] = None
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "requires_context": self.requires_context,
            "context_resolved": self.context_resolved,
            "dependency_type": self.dependency_type,
            "entities_used": self.entities_used,
            "rewrite_confidence": self.rewrite_confidence,
            "fallback_reason": self.fallback_reason,
            "debug": self.debug
        }


@dataclass
class ConversationMemory:
    """Memória estruturada por tenant e conversa."""
    tenant_id: str
    conversation_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    entities: List[ConversationEntity] = field(default_factory=list)
    recent_subject: str = ""
    last_tabular_result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "conversation_id": self.conversation_id,
            "turns": [t.to_dict() for t in self.turns],
            "entities": [e.to_dict() for e in self.entities],
            "recent_subject": self.recent_subject,
            "last_tabular_result": self.last_tabular_result
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMemory":
        turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        entities = [ConversationEntity.from_dict(e) for e in data.get("entities", [])]
        return cls(
            tenant_id=data.get("tenant_id", "default"),
            conversation_id=data.get("conversation_id", "default"),
            turns=turns,
            entities=entities,
            recent_subject=data.get("recent_subject", ""),
            last_tabular_result=data.get("last_tabular_result")
        )


# ─────────────────────────────────────────────────────────────────────────────
# PERSISTÊNCIA E CARREGAMENTO DA MEMÓRIA ESTRUTURADA
# ─────────────────────────────────────────────────────────────────────────────

DIRETORIO_MEMORIA_CONVERSAS = os.path.join("tenant_data", "conversas")


def _obter_caminho_memoria(tenant_id: str, conversation_id: str) -> str:
    os.makedirs(DIRETORIO_MEMORIA_CONVERSAS, exist_ok=True)
    nome_seguro = f"{tenant_id}_{conversation_id}_memory.json"
    return os.path.join(DIRETORIO_MEMORIA_CONVERSAS, nome_seguro)


def carregar_memoria_conversacao(tenant_id: str, conversation_id: str) -> ConversationMemory:
    """Carrega a memória conversacional estruturada do arquivo JSON no disco."""
    logger = obter_logger(tenant_id)
    if not conversation_id:
        return ConversationMemory(tenant_id=tenant_id, conversation_id="default")

    caminho = _obter_caminho_memoria(tenant_id, conversation_id)
    if os.path.exists(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return ConversationMemory.from_dict(dados)
        except Exception as e:
            logger.error(f"Erro ao carregar memória conversacional '{caminho}': {e}")

    return ConversationMemory(tenant_id=tenant_id, conversation_id=conversation_id)


def salvar_memoria_conversacao(memoria: ConversationMemory) -> bool:
    """Salva a memória conversacional estruturada no disco."""
    logger = obter_logger(memoria.tenant_id)
    if not memoria.conversation_id:
        return False

    caminho = _obter_caminho_memoria(memoria.tenant_id, memoria.conversation_id)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(memoria.to_dict(), f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar memória conversacional '{caminho}': {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES DE NORMALIZAÇÃO E EXTRAÇÃO DE ENTIDADES FATUAIS
# ─────────────────────────────────────────────────────────────────────────────

def normalizar_texto_conversacional(texto: str) -> str:
    """Normaliza texto para minúsculas sem acentos com espaços simples."""
    if not texto:
        return ""
    txt = unicodedata.normalize("NFKD", str(texto))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r'[^a-zA-Z0-9\s]', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt).strip().lower()
    return txt


def extrair_entidades_fatuais_do_contexto(
    turn_index: int,
    sources: List[str],
    chunks: List[Dict[str, Any]],
    tabular_result: Optional[Dict[str, Any]] = None
) -> Tuple[List[ConversationEntity], Optional[Dict[str, Any]], str]:
    """Extrai estritamente entidades confirmadas a partir das fontes recuperadas ou resultados tabulares.

    NUNCA armazena afirmações não verificadas geradas pelo LLM.
    """
    entidades: List[ConversationEntity] = []
    recent_subject = ""
    seen_texts: Set[str] = set()

    # 1. Extração de Resultados Tabulares Determinísticos
    tab_info = None
    if tabular_result and isinstance(tabular_result, dict):
        tab_info = tabular_result
        records = tabular_result.get("records", [])
        for r in records:
            if not isinstance(r, dict):
                continue
            # Entidades do tipo consultor / responsável / pessoa
            for k in ["consultor", "responsavel", "atendente", "autor"]:
                if k in r and r[k] and str(r[k]).strip():
                    val = str(r[k]).strip()
                    v_norm = normalizar_texto_conversacional(val)
                    if v_norm not in seen_texts:
                        seen_texts.add(v_norm)
                        entidades.append(ConversationEntity(
                            text=val,
                            entity_type="person",
                            source="tabular",
                            turn_index=turn_index,
                            confidence=1.0,
                            metadata={"column": k}
                        ))

            # Entidades do tipo empresa / cliente
            for k in ["empresa", "cliente", "confeccao", "organizacao"]:
                if k in r and r[k] and str(r[k]).strip():
                    val = str(r[k]).strip()
                    v_norm = normalizar_texto_conversacional(val)
                    if v_norm not in seen_texts:
                        seen_texts.add(v_norm)
                        entidades.append(ConversationEntity(
                            text=val,
                            entity_type="company",
                            source="tabular",
                            turn_index=turn_index,
                            confidence=1.0,
                            metadata={"column": k}
                        ))

        # Valores únicos em 'value' (ex: DISTINCT)
        val = tabular_result.get("value")
        if isinstance(val, list):
            for item in val:
                if item and isinstance(item, str):
                    v_norm = normalizar_texto_conversacional(item)
                    if v_norm not in seen_texts:
                        seen_texts.add(v_norm)
                        entidades.append(ConversationEntity(
                            text=item,
                            entity_type="general",
                            source="tabular",
                            turn_index=turn_index,
                            confidence=1.0
                        ))

    # 2. Extração de Chunks Vetoriais do ChromaDB
    for c in chunks:
        meta = c.get("meta", {}) or c
        texto = c.get("texto", "")

        # Produtos e materiais nos metadados
        for k_type in [("produto", "product"), ("material", "fabric"), ("variante", "product"), ("secao", "general")]:
            val = meta.get(k_type[0])
            if val and isinstance(val, str) and len(val.strip()) > 1:
                val_str = val.strip()
                v_norm = normalizar_texto_conversacional(val_str)
                if v_norm not in seen_texts:
                    seen_texts.add(v_norm)
                    entidades.append(ConversationEntity(
                        text=val_str,
                        entity_type=k_type[1],
                        source="vector",
                        turn_index=turn_index,
                        confidence=0.95
                    ))
                    if not recent_subject and k_type[1] in ["product", "fabric"]:
                        recent_subject = val_str

        # Padrões conhecidos de códigos no texto (ex: M518, REF-990, Millie Denim)
        codigos = re.findall(r'\b[A-Z][0-9]{3,4}\b|\b[A-Z]{2,4}-[0-9]{3,4}\b|Millie Denim|Maskskin', texto)
        for cod in codigos:
            v_norm = normalizar_texto_conversacional(cod)
            if v_norm not in seen_texts:
                seen_texts.add(v_norm)
                entidades.append(ConversationEntity(
                    text=cod,
                    entity_type="fabric",
                    source="vector",
                    turn_index=turn_index,
                    confidence=0.95
                ))
                if not recent_subject:
                    recent_subject = f"tecido {cod}"

    return entidades, tab_info, recent_subject


# ─────────────────────────────────────────────────────────────────────────────
# DETECÇÃO DE DEPENDÊNCIA CONTEXTUAL E ANÁLISE DE ANÁFORAS
# ─────────────────────────────────────────────────────────────────────────────

PRONOMES_FEMININOS = {"ela", "dela", "nela", "aquela", "daquela", "naquela", "essa", "dessa", "nessa", "esta", "desta", "nesta"}
PRONOMES_MASCULINOS = {"ele", "dele", "nele", "aquele", "daquele", "naquele", "esse", "desse", "nesse", "este", "deste", "neste"}
PRONOMES_PLURAIS = {"elas", "delas", "nelas", "aquela", "daquelas", "naquelas", "essas", "dessas", "nessas", "eles", "deles", "neles", "aqueles", "daqueles", "naqueles", "esses", "desses", "nesses"}
PRONOMES_NEUTROS = {"isso", "isto", "aquilo", "o mesmo", "a mesma", "os mesmos", "as mesmas"}
TODOS_PRONOMES = PRONOMES_FEMININOS | PRONOMES_MASCULINOS | PRONOMES_PLURAIS | PRONOMES_NEUTROS

PALAVRAS_PROPRIEDADES = {
    "composicao", "composição", "largura", "gramatura", "valor", "preco", "preço",
    "telefone", "modelo", "responsavel", "responsável", "fabricante", "categoria",
    "descricao", "descrição", "faturamento", "gasto", "custo", "consultor", "consultora"
}


def inferir_dominio_texto(texto: str) -> str:
    """Infere o domínio temático de um texto para prevenção de contaminação cruzada (Requisito 20)."""
    if not texto:
        return "GERAL"
    t_norm = normalizar_texto_conversacional(texto)

    # 1. Google Trends / Tradução / IA de Linguagem
    if any(k in t_norm for k in ["google translate", "chatgpt", "deepl", "timeline", "traducao", "tradução", "gnmt", "pageviews"]):
        return "GOOGLE_TRENDS"

    # 2. EWC / Esports / Jogos
    if any(k in t_norm for k in ["ewc", "valorant", "dota", "esports", "club championship", "roster", "tekken", "apex legends", "free fire", "pubg", "fortnite", "rocket league", "100 thieves", "ag.al", "team falcons"]):
        return "EWC_ESPORTS"

    # 3. Têxtil / Confecção / SENAI
    if any(k in t_norm for k in ["m518", "millie", "camisa", "camisete", "jeans", "denim", "tecido", "consultor", "confeccao", "confecção", "auditoria"]):
        return "SENAI_FASHION"

    return "GERAL"


def analisar_dependencia_contextual(
    query: str,
    memoria: Optional[ConversationMemory] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """Identifica se a consulta atual depende do contexto anterior da conversa.

    Retorna: (requires_context, dependency_type, details)
    """
    if not query:
        return False, "NONE", {}

    q_norm = normalizar_texto_conversacional(query)
    tokens = q_norm.split()

    details: Dict[str, Any] = {}

    # 0. Detecção de Mudança Forte de Domínio (Context Switch - Requisito 20)
    if memoria and memoria.turns:
        dom_atual = inferir_dominio_texto(query)
        ultimo_turno = memoria.turns[-1]
        dom_anterior = inferir_dominio_texto(ultimo_turno.user_query + " " + ultimo_turno.assistant_answer)

        if dom_atual != "GERAL" and dom_anterior != "GERAL" and dom_atual != dom_anterior:
            # Houve troca de domínio! Evita herança de contexto anterior
            details["domain_switch_detected"] = True
            details["previous_domain"] = dom_anterior
            details["current_domain"] = dom_atual
            return False, "NONE", details

    # 1. Verificação de Referências a Conjuntos (ex: "qual delas", "qual deles", "qual possui o maior faturamento")
    padroes_conjunto = [
        r'\bqual (delas|deles|dos quais|das quais)\b',
        r'\bdentre (elas|eles)\b',
        r'\bentre (elas|eles)\b',
        r'\bqual (possui|tem|apresenta) o (maior|menor)\b',
        r'\bqual o (maior|menor) (faturamento|valor|gasto)\b',
        r'\bqual a (maior|menor) (empresa|categoria)\b'
    ]
    for pat in padroes_conjunto:
        if re.search(pat, q_norm):
            details["pattern"] = pat
            return True, "SET_REFERENCE", details

    # 2. Verificação de Pronomes Explícitos
    for tok in tokens:
        if tok in TODOS_PRONOMES:
            details["pronoun"] = tok
            if tok in PRONOMES_FEMININOS:
                details["gender"] = "female"
            elif tok in PRONOMES_MASCULINOS:
                details["gender"] = "male"
            elif tok in PRONOMES_PLURAIS:
                details["gender"] = "plural"
            else:
                details["gender"] = "neutral"
            return True, "PRONOUN", details

    # 3. Verificação de Continuações Curtas ou Perguntas Incompletas
    # Ex: "E a composição?", "E a largura?", "E o valor?", "Qual o telefone?"
    eh_continual_curta = False
    if q_norm.startswith(("e a ", "e o ", "e qual ", "e quanto ", "e sobre ", "e depois ")) or len(tokens) <= 4:
        # Se contiver uma palavra de propriedade e não contiver entidade própria
        if any(prop in q_norm for prop in PALAVRAS_PROPRIEDADES):
            eh_continual_curta = True

    if eh_continual_curta:
        details["short_continuation"] = True
        return True, "IMPLICIT_CONTINUATION", details

    return False, "NONE", {}


# ─────────────────────────────────────────────────────────────────────────────
# RESOLUÇÃO DE ENTIDADES E REESCRITA DE QUERY
# ─────────────────────────────────────────────────────────────────────────────

def resolver_entidades_contextual(
    query: str,
    memoria: Optional[ConversationMemory],
    dep_type: str,
    dep_details: Dict[str, Any],
    config: Dict[str, Any]
) -> Tuple[List[ConversationEntity], float, Optional[str]]:
    """Resolve a entidade ou conjunto de entidades mais compatíveis da memória factual.

    Aplica as 5 Camadas de Resolução com limites de idade e tratamento estrito de ambiguidade.
    """
    if not memoria or not memoria.turns:
        return [], 0.0, "no_conversation_history"

    max_age = config.get("conversation_entity_max_age_turns", 5)
    current_turn = len(memoria.turns) + 1
    allow_ambiguous = config.get("conversation_allow_ambiguous_resolution", False)

    # Filtra entidades com idade <= max_age
    entidades_validas = [
        e for e in memoria.entities
        if (current_turn - e.turn_index) <= max_age
    ]

    # ── CAMADA 1: Entidade explícita presente na própria pergunta atual ──
    q_norm = normalizar_texto_conversacional(query)
    for e in entidades_validas:
        if normalizar_texto_conversacional(e.text) in q_norm:
            return [e], 1.0, None

    # ── CAMADA 4: Referência a Conjunto Tabular Anterior ──
    if dep_type == "SET_REFERENCE":
        # Procura o último resultado tabular no histórico recente
        for turn in reversed(memoria.turns):
            if turn.tabular_result and isinstance(turn.tabular_result, dict):
                records = turn.tabular_result.get("records", [])
                value = turn.tabular_result.get("value")

                entidades_conjunto = []
                if records:
                    for r in records:
                        if isinstance(r, dict):
                            # Tenta pegar coluna principal (empresa, consultor, descricao)
                            val_col = r.get("empresa") or r.get("consultor") or r.get("descricao") or r.get("categoria")
                            if val_col and str(val_col).strip():
                                entidades_conjunto.append(str(val_col).strip())
                elif isinstance(value, list):
                    entidades_conjunto = [str(x) for x in value if str(x).strip()]

                if entidades_conjunto:
                    # Limita tamanho do conjunto conforme configuração
                    max_set = config.get("conversation_max_set_entities", 100)
                    entidades_conjunto = entidades_conjunto[:max_set]
                    obj_ent = ConversationEntity(
                        text=", ".join(entidades_conjunto),
                        entity_type="set",
                        source="tabular",
                        turn_index=turn.turn_index,
                        confidence=0.95,
                        metadata={"elements": entidades_conjunto}
                    )
                    return [obj_ent], 0.95, None

        return [], 0.0, "missing_tabular_set_context"

    # ── CAMADA 2: Pronomes (ele, ela, dele, dela, etc.) ──
    if dep_type == "PRONOUN":
        gender = dep_details.get("gender", "neutral")

        if gender == "plural":
            candidatos_p = [e for e in entidades_validas if e.entity_type in ["person", "company", "product", "set"]]
            if candidatos_p:
                max_turn = max(e.turn_index for e in candidatos_p)
                recentes = [e for e in candidatos_p if e.turn_index == max_turn]
                nomes = list(dict.fromkeys(e.text for e in recentes))
                ent_plural = ConversationEntity(
                    text=" e ".join(nomes),
                    entity_type="plural",
                    source="context",
                    turn_index=max_turn,
                    confidence=0.95,
                    metadata={"elements": nomes}
                )
                return [ent_plural], 0.95, None

        # Priorização por especificidade do tipo semântico para singular:
        candidatos: List[ConversationEntity] = []
        if gender in ["female", "male"]:
            pessoas = [e for e in entidades_validas if e.entity_type == "person"]
            if pessoas:
                candidatos = pessoas
            else:
                candidatos = [e for e in entidades_validas if e.entity_type in ["company", "fabric", "product"]]
        else:
            candidatos = list(entidades_validas)

        if not candidatos:
            candidatos = list(entidades_validas)

        if not candidatos:
            return [], 0.0, "no_compatible_entity_found"

        # Ordena por recência (turn_index descendente)
        candidatos.sort(key=lambda x: x.turn_index, reverse=True)

        # Checagem de Ambiguidade: Múltiplas entidades do MESMO tipo no MESMO turno mais recente
        max_turn = candidatos[0].turn_index
        candidatos_mais_recentes = [c for c in candidatos if c.turn_index == max_turn]

        if len(candidatos_mais_recentes) > 1 and not allow_ambiguous:
            textos_unicos = set(normalizar_texto_conversacional(c.text) for c in candidatos_mais_recentes)
            if len(textos_unicos) > 1:
                return [], 0.0, "ambiguous_entity_reference"

        return [candidatos[0]], 0.95, None

    # ── CAMADA 3: Continuação Implícita (ex: "E a composição?") ──
    if dep_type == "IMPLICIT_CONTINUATION":
        # Prioriza tecidos/produtos específicos (ex: M518) sobre termos genéricos
        tecidos = [e for e in entidades_validas if e.entity_type in ["fabric", "product"]]
        if tecidos:
            tecidos.sort(key=lambda x: (x.turn_index, 1 if x.entity_type == "fabric" else 0), reverse=True)
            return [tecidos[0]], 0.92, None

        candidatos = [e for e in entidades_validas if e.entity_type in ["person", "company"]]
        if candidatos:
            candidatos.sort(key=lambda x: x.turn_index, reverse=True)
            return [candidatos[0]], 0.88, None

        if memoria.recent_subject:
            ent_subj = ConversationEntity(
                text=memoria.recent_subject,
                entity_type="general",
                source="context",
                turn_index=current_turn - 1,
                confidence=0.85
            )
            return [ent_subj], 0.85, None

    return [], 0.0, "unresolved_context"


def reescrever_query_conversacional(
    query: str,
    tenant_id: str,
    conversation_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> QueryRewriteResult:
    """Executa a análise, resolução de entidades e reescrita determinística da pergunta.

    Retorna um objeto `QueryRewriteResult` contendo a `rewritten_query` autocontida.
    Preserva 100% a pergunta original para a interface de usuário.
    """
    logger = obter_logger(tenant_id)
    cfg = config or RAG_CONFIG

    if not cfg.get("enable_conversational_query_rewriting", True) or not conversation_id:
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            requires_context=False,
            context_resolved=True,
            dependency_type="NONE",
            entities_used=[],
            rewrite_confidence=1.0,
            fallback_reason="rewriting_disabled_or_no_conversation_id"
        )

    memoria = carregar_memoria_conversacao(tenant_id, conversation_id)
    requires_ctx, dep_type, dep_details = analisar_dependencia_contextual(query, memoria)

    if not requires_ctx:
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            requires_context=False,
            context_resolved=True,
            dependency_type="NONE",
            entities_used=[],
            rewrite_confidence=1.0,
            fallback_reason=None,
            debug={"dep_type": "NONE", "turns_count": len(memoria.turns)}
        )

    if not memoria.turns:
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            requires_context=True,
            context_resolved=False,
            dependency_type=dep_type,
            entities_used=[],
            rewrite_confidence=0.0,
            fallback_reason="no_conversation_history",
            debug={"dep_type": dep_type, "turns_count": 0}
        )

    # Tenta resolver entidades na memória factual
    entidades_res, conf, fallback = resolver_entidades_contextual(query, memoria, dep_type, dep_details, cfg)

    min_conf = cfg.get("conversation_min_resolution_confidence", 0.75)
    if not entidades_res or conf < min_conf or fallback:
        logger.info(f"[CONVERSATIONAL DEBUG] Resolução de contexto falhou para '{query}': {fallback}")
        return QueryRewriteResult(
            original_query=query,
            rewritten_query=query,
            requires_context=True,
            context_resolved=False,
            dependency_type=dep_type,
            entities_used=[],
            rewrite_confidence=conf,
            fallback_reason=fallback or "low_confidence",
            debug={"dep_type": dep_type, "dep_details": dep_details, "fallback": fallback}
        )

    entidade_primaria = entidades_res[0]
    texto_entidade = entidade_primaria.text
    query_reescrita = query

    # ── CONSTRUÇÃO DA QUERY REESCRITA AUTOCONTIDA ──
    if dep_type == "PRONOUN":
        pronome = dep_details.get("pronoun", "").lower()
        if pronome:
            if pronome in ["dela", "daquela", "dessa", "desta"]:
                if entidade_primaria.entity_type == "person":
                    subst = f"da consultora {texto_entidade}"
                elif entidade_primaria.entity_type == "company":
                    subst = f"da empresa {texto_entidade}"
                else:
                    subst = f"de {texto_entidade}"
            elif pronome in ["dele", "daquele", "desse", "deste"]:
                if entidade_primaria.entity_type == "person":
                    subst = f"do responsável {texto_entidade}"
                elif entidade_primaria.entity_type in ["fabric", "product"]:
                    subst = f"do produto {texto_entidade}"
                else:
                    subst = f"de {texto_entidade}"
            elif pronome in ["delas", "daquelas", "dessas"]:
                subst = f"das empresas {texto_entidade}" if entidade_primaria.entity_type == "company" else f"de {texto_entidade}"
            elif pronome in ["deles", "daqueles", "desses"]:
                subst = f"dos consultores {texto_entidade}" if entidade_primaria.entity_type == "person" else f"de {texto_entidade}"
            else:
                if entidade_primaria.entity_type == "person":
                    subst = f"a consultora {texto_entidade}" if dep_details.get("gender") == "female" else f"o responsável {texto_entidade}"
                elif entidade_primaria.entity_type == "company":
                    subst = f"a empresa {texto_entidade}"
                elif entidade_primaria.entity_type in ["fabric", "product"]:
                    subst = f"o produto {texto_entidade}"
                else:
                    subst = texto_entidade

            query_reescrita = re.sub(rf'\b{re.escape(pronome)}\b', subst, query, flags=re.IGNORECASE)

    elif dep_type == "IMPLICIT_CONTINUATION":
        # Se for uma pergunta curta como "E a composição?", expande para "Qual é a composição de [Entidade]?"
        q_clean = query.strip()
        if q_clean.lower().startswith("e "):
            q_clean = q_clean[2:].strip()
            q_clean = q_clean[0].upper() + q_clean[1:] if q_clean else q_clean

        if not re.search(rf'\b{re.escape(texto_entidade)}\b', q_clean, re.IGNORECASE):
            if q_clean.endswith("?"):
                q_clean = q_clean[:-1].strip()
            
            if entidade_primaria.entity_type in ["fabric", "product"]:
                query_reescrita = f"{q_clean} do {texto_entidade}?"
            elif entidade_primaria.entity_type in ["person", "company"]:
                query_reescrita = f"{q_clean} de {texto_entidade}?"
            else:
                query_reescrita = f"{q_clean} sobre {texto_entidade}?"

    elif dep_type == "SET_REFERENCE":
        # Conjunto de elementos retornados na consulta tabular anterior
        elementos = entidade_primaria.metadata.get("elements", [])
        if elementos:
            lista_str = ", ".join(elementos[:10])
            query_reescrita = f"Entre as empresas {lista_str}, qual possui o maior faturamento?" if "faturamento" in query.lower() else f"Entre {lista_str}, {query.lower()}"

    debug_info = {
        "dep_type": dep_type,
        "dep_details": dep_details,
        "entity_selected": texto_entidade,
        "entity_type": entidade_primaria.entity_type,
        "confidence": conf
    }

    return QueryRewriteResult(
        original_query=query,
        rewritten_query=query_reescrita,
        requires_context=True,
        context_resolved=True,
        dependency_type=dep_type,
        entities_used=[e.text for e in entidades_res],
        rewrite_confidence=conf,
        fallback_reason=None,
        debug=debug_info
    )


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO DE TURNO E ATUALIZAÇÃO DE MEMÓRIA FACTUAL
# ─────────────────────────────────────────────────────────────────────────────

def registrar_turno_conversacional(
    tenant_id: str,
    conversation_id: str,
    user_query: str,
    rewritten_query: Optional[str],
    assistant_answer: str,
    sources: List[str],
    retrieved_chunks: List[Dict[str, Any]],
    tabular_result: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None
) -> ConversationMemory:
    """Registra o turno encerrado e atualiza a memória factual do tenant/conversa.

    Persiste no disco apenas entidades confirmadas por fontes documentais ou tabulares.
    """
    cfg = config or RAG_CONFIG
    memoria = carregar_memoria_conversacao(tenant_id, conversation_id)
    turn_index = len(memoria.turns) + 1

    # Extração estrita de entidades fatuais
    entidades_fatuais, tab_info, recent_subj = extrair_entidades_fatuais_do_contexto(
        turn_index, sources, retrieved_chunks, tabular_result
    )

    turno = ConversationTurn(
        turn_index=turn_index,
        user_query=user_query,
        rewritten_query=rewritten_query,
        assistant_answer=assistant_answer,
        entities=entidades_fatuais,
        tabular_result=tab_info,
        sources=sources
    )

    memoria.turns.append(turno)

    # Atualiza lista global de entidades fatuais na memória
    for ent in entidades_fatuais:
        # Substitui duplicatas ou adiciona nova
        memoria.entities = [e for e in memoria.entities if normalizar_texto_conversacional(e.text) != normalizar_texto_conversacional(ent.text)]
        memoria.entities.append(ent)

    if recent_subj:
        memoria.recent_subject = recent_subj
    if tab_info:
        memoria.last_tabular_result = tab_info

    # Trunca memória de turnos para no máximo conversation_memory_max_turns
    max_turns = cfg.get("conversation_memory_max_turns", 10)
    if len(memoria.turns) > max_turns:
        memoria.turns = memoria.turns[-max_turns:]

    salvar_memoria_conversacao(memoria)
    return memoria
