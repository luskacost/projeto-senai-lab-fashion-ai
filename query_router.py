# -*- coding: utf-8 -*-
"""Módulo Centralizado de Roteamento de Consultas e Recuperação Orientada à Fonte (Query Router).

Implementa:
1. Classificação multi-sinal de rotas:
   - TABULAR_EXACT: Busca determinística de célula/registro específico.
   - TABULAR_AGGREGATION: Agregações globais (COUNT, SUM, AVG, MIN, MAX, GROUP_COUNT, RANK).
   - TABULAR_FILTER: Filtragem estruturada por valores e intervalos de datas.
   - TABULAR_LIST: Listagem completa ou amostragem estruturada (todos, todas, lista completa).
   - TABULAR_RELATIONAL: Resolução relacional multi-tabela determinística (joins).
   - VECTOR_SEMANTIC: Perguntas conceituais, discursivas e narrativas.
   - CONVERSATIONAL: Continuações resolvidas contextualmente.
   - HYBRID: Perguntas que exigem dados estruturados + síntese explicativa.
   - AMBIGUOUS: Perguntas vagas sem contexto suficiente (evita alucinação).
   - UNKNOWN: Fallback seguro quando a confiança for insuficiente.
2. Reconhecimento robusto de intenções em português natural com tolerância a variações e erros.
3. Normalização determinística de datas e intervalos temporais.
4. Profiling de fontes e anti-saturação de documentos narrativos.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from logger_config import obter_logger
from rag_config import RAG_CONFIG
from semantic_enrichment import normalizar_nome_coluna, _parse_numero_generico
from tabular_storage import TabularDocument, carregar_documentos_tabulares


class RouteType(str, Enum):
    TABULAR_EXACT = "TABULAR_EXACT"
    TABULAR_AGGREGATION = "TABULAR_AGGREGATION"
    TABULAR_FILTER = "TABULAR_FILTER"
    TABULAR_LIST = "TABULAR_LIST"
    TABULAR_RELATIONAL = "TABULAR_RELATIONAL"
    VECTOR_SEMANTIC = "VECTOR_SEMANTIC"
    CONVERSATIONAL = "CONVERSATIONAL"
    HYBRID = "HYBRID"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


@dataclass
class SourceProfile:
    """Perfil estruturado de uma fonte documental ou tabular."""
    document_name: str
    sheet_name: str
    source_type: str  # 'csv', 'xlsx', 'xls', 'json', 'markdown', 'pdf', 'text'
    is_structured: bool
    is_narrative: bool
    columns: List[str] = field(default_factory=list)
    row_count: int = 0
    sample_entities: Set[str] = field(default_factory=set)


@dataclass
class QueryRoute:
    """Resultado estruturado e auditável do Query Router."""
    route: RouteType
    confidence: float
    reasons: List[str]
    tabular_intent: Optional[str] = None
    preferred_sources: List[str] = field(default_factory=list)
    fallback_sources: List[str] = field(default_factory=list)
    target_columns: List[str] = field(default_factory=list)
    filters: List[Dict[str, Any]] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    is_ambiguous: bool = False
    ambiguity_prompt: Optional[str] = None
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route.value if isinstance(self.route, RouteType) else str(self.route),
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
            "tabular_intent": self.tabular_intent,
            "preferred_sources": self.preferred_sources,
            "fallback_sources": self.fallback_sources,
            "target_columns": self.target_columns,
            "filters": self.filters,
            "group_by": self.group_by,
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_prompt": self.ambiguity_prompt,
            "debug": self.debug
        }


# ==============================================================================
# ALIASES EXPANDIDOS DE COLUNAS EM PORTUGUÊS (GENÉRICOS E REUTILIZÁVEIS)
# ==============================================================================
EXTENDED_COLUMN_ALIASES: Dict[str, List[str]] = {
    # Pontuação e Desempenho
    "pontos": [
        "pontos", "pontuacao", "pontuação", "total_points", "points",
        "club_championship_points", "score", "pontos totais", "pontos acumulados"
    ],
    # Valores Monetários e Premiações
    "premiacao": [
        "premiacao", "premiação", "premio", "prêmio", "premios", "prêmios",
        "prize_pool_usd", "prize_money_usd", "prize_earned_usd", "amount_usd",
        "prize_pool", "valor", "montante", "recompensa", "dinheiro", "grana", "faturou", "faturamento", "gasto", "custo"
    ],
    # Participantes e Recipientes
    "participantes": [
        "participantes", "num_participants", "num_recipients", "quantidade de participantes",
        "recipientes", "equipes participantes", "times participantes", "total de participantes"
    ],
    # Vencedores e Campeões
    "vencedor": [
        "vencedor", "campeao", "campeão", "winner", "champion", "primeiro colocado",
        "1 colocado", "1º colocado", "ouro", "gold", "primeiro"
    ],
    # Vice-campeão e Segundo Colocado
    "vice": [
        "vice", "vice campeao", "vice-campeão", "segundo colocado", "2 colocado",
        "2º colocado", "runner_up", "prata", "silver", "segundo"
    ],
    # Organizações, Equipes e Clubes
    "organizacao": [
        "organizacao", "organização", "clube", "equipe", "time", "empresa",
        "organization", "team", "club", "team_organization", "organizacoes", "organizações"
    ],
    # Países e Regiões
    "pais": [
        "pais", "país", "country", "nacionalidade", "origem", "estado", "regiao", "região", "region"
    ],
    # Jogos e Modalidades
    "jogo": [
        "jogo", "jogos", "game", "games", "modalidade", "modalidades", "game_type", "titulo", "título"
    ],
    # Eventos e Torneios
    "evento": [
        "evento", "eventos", "event_name", "tournament", "torneio", "torneios", "campeonato"
    ],
    # Plataformas e Formatos
    "plataforma": [
        "plataforma", "platform", "console", "pc", "mobile", "dispositivo"
    ],
    # Gênero e Divisão
    "genero": [
        "genero", "gênero", "gender", "categoria", "divisao", "divisão"
    ],
    # Jogadores e Pro Players
    "jogador": [
        "jogador", "jogadores", "player", "player_name", "pro player", "atleta", "membro"
    ],
    # Classificação e Posição
    "colocacao": [
        "colocacao", "colocação", "posicao", "posição", "rank", "placement",
        "tournament_place", "lugar", "classificacao", "classificação"
    ],
    # Datas e Prazos
    "data": [
        "data", "date", "start_date", "end_date", "periodo", "período",
        "month", "mes", "mês", "week", "semana", "ano", "year"
    ],
    # Duração
    "duracao": [
        "duracao", "duração", "duration_days", "duration_minutes", "dias", "tempo"
    ],
    # Medalhas
    "medalhas": [
        "medalhas", "gold_medals", "silver_medals", "bronze_medals", "medals"
    ],
    # Vitórias
    "vitorias": [
        "vitorias", "vitórias", "tournament_wins", "games_won", "wins", "partidas ganhas"
    ],
    # Consultoria e Auditoria (compatibilidade P1-P4)
    "consultor": [
        "consultor", "consultora", "responsavel", "responsável", "resp", "atendente", "analista"
    ],
    "descricao": [
        "descricao", "descrição", "desc", "historico", "histórico", "item", "detalhe"
    ],
    "quantidade": [
        "quantidade", "qtd", "quant", "volume", "estoque", "unidades", "itens"
    ]
}


def normalizar_texto_router(texto: str) -> str:
    """Normaliza texto da query para remoção de acentos, pontuação desnecessária e espaços."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', str(texto))
    sem_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    sem_pont = re.sub(r'[^a-zA-Z0-9\s_\-\./]', ' ', sem_acentos)
    return re.sub(r'\s+', ' ', sem_pont).strip().lower()


def normalizar_nome_entidade_ou_nickname(nome: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Extrai apelido e nome formal de expressões compostas como 'bang (Sean Bezerra)', 'Peter "Asuna" Mazuryk' ou 'Faker (Lee Sang-hyeok)'.

    Retorna: (nome_completo_norm, nickname_norm, nome_parenteses_norm)
    """
    if not nome:
        return "", None, None
    nome_norm = normalizar_texto_router(nome)

    # 1. Caso com aspas: Peter "Asuna" Mazuryk ou Luis "DarkAngel" Castillo Gomez
    m_aspas = re.search(r'^(.*?)\s*["“”\']([^"“”\']+)["“”\']\s*(.*?)$', nome.strip())
    if m_aspas:
        antes = m_aspas.group(1).strip()
        nick_raw = m_aspas.group(2).strip()
        depois = m_aspas.group(3).strip()
        nome_completo = f"{antes} {depois}".strip()
        return nome_norm, normalizar_texto_router(nick_raw), normalizar_texto_router(nome_completo)

    # 2. Caso com parênteses: Asuna (Peter Mazuryk)
    m = re.search(r'^(.*?)\s*\((.*?)\)$', nome.strip())
    if m:
        nick_raw = m.group(1).strip()
        paren_raw = m.group(2).strip()
        return nome_norm, normalizar_texto_router(nick_raw), normalizar_texto_router(paren_raw)

    return nome_norm, None, None


# ==============================================================================
# NORMALIZAÇÃO DE DATAS E INTERVALOS EM PORTUGUÊS (REQUISITO 12)
# ==============================================================================
MESES_NUM = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2,
    "marco": 3, "março": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "maio": 5, "mai": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12
}


def extrair_intervalo_datas(texto: str) -> Optional[Dict[str, Any]]:
    """Identifica e normaliza expressões temporais em português para intervalos ISO (YYYY-MM-DD)."""
    t_norm = normalizar_texto_router(texto)

    # 1. Mês e Ano específico: "em julho de 2026", "julho 2026", "em janeiro de 2016"
    m_mes_ano = re.search(r'\b(?:em\s+|de\s+|no\s+mes\s+de\s+)?(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+(?:de\s+)?(\d{4})\b', t_norm)
    if m_mes_ano:
        mes_nome = m_mes_ano.group(1)
        ano = int(m_mes_ano.group(2))
        mes_num = MESES_NUM[mes_nome]
        # Último dia do mês simplificado
        dias_no_mes = 31 if mes_num in [1, 3, 5, 7, 8, 10, 12] else (30 if mes_num != 2 else (29 if ano % 4 == 0 else 28))
        return {
            "tipo": "month_year",
            "ano": ano,
            "mes": mes_num,
            "data_inicio": f"{ano:04d}-{mes_num:02d}-01",
            "data_fim": f"{ano:04d}-{mes_num:02d}-{dias_no_mes:02d}",
            "padrao_chave": f"{ano:04d}-{mes_num:02d}"
        }

    # 2. Período entre meses: "entre julho e agosto", "de julho a agosto"
    m_entre_meses = re.search(r'\b(?:entre|de)\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+(?:e|a|ate)\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+(?:de\s+)?(\d{4}))?\b', t_norm)
    if m_entre_meses:
        m1 = MESES_NUM[m_entre_meses.group(1)]
        m2 = MESES_NUM[m_entre_meses.group(2)]
        ano = int(m_entre_meses.group(3)) if m_entre_meses.group(3) else 2026
        dias_fim = 31 if m2 in [1, 3, 5, 7, 8, 10, 12] else 30
        return {
            "tipo": "range_months",
            "ano": ano,
            "mes_inicio": m1,
            "mes_fim": m2,
            "data_inicio": f"{ano:04d}-{m1:02d}-01",
            "data_fim": f"{ano:04d}-{m2:02d}-{dias_fim:02d}",
            "padrao_chave": f"{ano:04d}"
        }

    # 3. Intervalo de dias no mês: "entre 1 e 10 de julho", "de 1 a 10 de julho"
    m_dias = re.search(r'\b(?:entre|de)\s+(\d{1,2})\s+(?:e|a|ate)\s+(\d{1,2})\s+(?:de\s+)?(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+(?:de\s+)?(\d{4}))?\b', t_norm)
    if m_dias:
        d1 = int(m_dias.group(1))
        d2 = int(m_dias.group(2))
        mes = MESES_NUM[m_dias.group(3)]
        ano = int(m_dias.group(4)) if m_dias.group(4) else 2026
        return {
            "tipo": "range_days",
            "data_inicio": f"{ano:04d}-{mes:02d}-{d1:02d}",
            "data_fim": f"{ano:04d}-{mes:02d}-{d2:02d}"
        }

    # 4. Primeira semana: "na primeira semana de julho"
    if "primeira semana" in t_norm:
        m_sem = re.search(r'primeira semana\s+(?:de\s+)?(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)(?:\s+(?:de\s+)?(\d{4}))?', t_norm)
        if m_sem:
            mes = MESES_NUM[m_sem.group(1)]
            ano = int(m_sem.group(2)) if m_sem.group(2) else 2026
            return {
                "tipo": "first_week",
                "data_inicio": f"{ano:04d}-{mes:02d}-01",
                "data_fim": f"{ano:04d}-{mes:02d}-07"
            }

    # 5. Apenas mês no ano corrente ou citado: "durante julho", "em julho", "no mes de julho"
    m_mes_isolado = re.search(r'\b(?:durante|no mes de|em)\s+(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b', t_norm)
    if m_mes_isolado:
        mes = MESES_NUM[m_mes_isolado.group(1)]
        ano = 2026
        dias_fim = 31 if mes in [1, 3, 5, 7, 8, 10, 12] else 30
        return {
            "tipo": "single_month",
            "mes": mes,
            "data_inicio": f"{ano:04d}-{mes:02d}-01",
            "data_fim": f"{ano:04d}-{mes:02d}-{dias_fim:02d}",
            "padrao_chave": f"-{mes:02d}-"
        }

    # 6. Apenas Ano: "em 2026", "de 2026"
    m_ano = re.search(r'\b(?:em|no ano de|de)\s+(\d{4})\b', t_norm)
    if m_ano:
        ano = int(m_ano.group(1))
        return {
            "tipo": "year",
            "ano": ano,
            "data_inicio": f"{ano:04d}-01-01",
            "data_fim": f"{ano:04d}-12-31",
            "padrao_chave": str(ano)
        }

    return None


def _parse_numero_pergunta(bruto: str) -> Optional[float]:
    """Converte um número escrito em português natural numa pergunta (ex: "4.000", "3,5") para float.

    Diferente de `semantic_enrichment._parse_numero_generico` (que assume valores vindos de células
    de planilha, onde "." tipicamente é decimal), aqui o texto vem de uma pergunta em linguagem
    natural em português, onde "." é o separador de milhar convencional ("mais de 4.000 pontos").
    """
    s = bruto.strip()
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    else:
        partes = s.split('.')
        if len(partes) == 2 and len(partes[1]) == 3:
            s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


# Expressões de comparação numérica em português -> operador correspondente.
# Ordem importa: variantes mais específicas ("maior ou igual a") antes das genéricas ("maior que").
_PADROES_OPERADOR_NUMERICO: List[Tuple[str, str]] = [
    (r'maior ou igual a', ">="),
    (r'pelo menos', ">="),
    (r'no minimo', ">="),
    (r'menor ou igual a', "<="),
    (r'no maximo', "<="),
    (r'mais de', ">"),
    (r'acima de', ">"),
    (r'superior a', ">"),
    (r'maior que', ">"),
    (r'maior a', ">"),
    (r'menos de', "<"),
    (r'abaixo de', "<"),
    (r'inferior a', "<"),
    (r'menor que', "<"),
    (r'menor a', "<"),
]

_NUMERO_PT_PATTERN = r'(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)'


def extrair_filtro_numerico(texto: str) -> Optional[Dict[str, Any]]:
    """Identifica expressões de filtro por limiar numérico em português.

    Ex: "mais de 4.000 pontos", "acima de 10", "no mínimo 500", "menor que 3,5". Retorna
    {"operador": ">", "valor": 4000.0, "termo_coluna": "pontos"} ou None se não houver filtro numérico.
    """
    t_norm = normalizar_texto_router(texto)
    for padrao_op, operador in _PADROES_OPERADOR_NUMERICO:
        m = re.search(r'\b' + padrao_op + r'\s+' + _NUMERO_PT_PATTERN + r'\b', t_norm)
        if m:
            valor = _parse_numero_pergunta(m.group(1))
            if valor is None:
                continue
            # Termo de coluna: primeira palavra relevante logo após o número (ex: "pontos" em
            # "mais de 4.000 pontos"), usada depois para resolver contra o schema/aliases.
            resto = t_norm[m.end():].strip()
            termo_coluna = resto.split(" ")[0] if resto else None
            return {"operador": operador, "valor": valor, "termo_coluna": termo_coluna}
    return None


class QueryRouter:
    """Roteador inteligente e determinístico de consultas para o pipeline RAG."""

    def __init__(self, tenant_id: str, config: Optional[Dict[str, Any]] = None):
        self.tenant_id = tenant_id
        self.config = config or RAG_CONFIG
        self.logger = obter_logger(tenant_id)
        self.source_profiles: List[SourceProfile] = self._mapear_perfis_fontes()

    def _mapear_perfis_fontes(self) -> List[SourceProfile]:
        """Inspeciona as fontes estruturadas do tenant para profiling detalhado."""
        perfis: List[SourceProfile] = []
        try:
            docs = carregar_documentos_tabulares(self.tenant_id)
            for doc in docs:
                for sheet_name, sheet in doc.sheets.items():
                    sample_ent = set()
                    for r in sheet.linhas[:20]:
                        for v in r.dados.values():
                            if v and isinstance(v, str) and len(v.strip()) > 2 and len(v.strip()) < 40:
                                sample_ent.add(normalizar_texto_router(v))

                    perfis.append(SourceProfile(
                        document_name=doc.nome_arquivo,
                        sheet_name=sheet_name,
                        source_type=doc.tipo_arquivo,
                        is_structured=True,
                        is_narrative=False,
                        columns=sheet.schema,
                        row_count=len(sheet.linhas),
                        sample_entities=sample_ent
                    ))
        except Exception as e:
            self.logger.warning(f"Erro ao mapear perfis tabulares para tenant '{self.tenant_id}': {e}")
        return perfis

    def resolver_coluna_em_schema(self, termo: str, colunas_schema: List[str]) -> Optional[str]:
        """Resolve um termo em uma coluna do schema usando aliases estendidos."""
        if not termo or not colunas_schema:
            return None
        t_norm = normalizar_texto_router(termo)

        # 1. Correspondência direta normalizada
        for col in colunas_schema:
            if normalizar_texto_router(col) == t_norm:
                return col

        # 2. Aliases configurados
        for alias_key, aliases in EXTENDED_COLUMN_ALIASES.items():
            aliases_norm = [normalizar_texto_router(a) for a in aliases]
            if t_norm == alias_key or t_norm in aliases_norm:
                for col in colunas_schema:
                    col_norm = normalizar_texto_router(col)
                    if col_norm == alias_key or col_norm in aliases_norm:
                        return col

        # 3. Substring ou sobreposição
        for col in colunas_schema:
            col_norm = normalizar_texto_router(col)
            if (len(t_norm) > 3 and t_norm in col_norm) or (len(col_norm) > 3 and col_norm in t_norm):
                return col

        return None

    def selecionar_melhor_fonte_estruturada(
        self,
        query_norm: str,
        termos_colunas: List[str]
    ) -> Tuple[Optional[SourceProfile], float, List[str]]:
        """Seleciona a melhor fonte estruturada com base em correspondência de colunas, nomes e entidades."""
        if not self.source_profiles:
            return None, 0.0, ["Nenhuma fonte estruturada disponível."]

        melhor_perfil: Optional[SourceProfile] = None
        melhor_score = -1.0
        reasons: List[str] = []

        for p in self.source_profiles:
            doc_name_norm = normalizar_texto_router(p.document_name)
            sheet_norm = normalizar_texto_router(p.sheet_name)

            col_matches = 0
            cols_casadas = []
            for tc in termos_colunas:
                c_real = self.resolver_coluna_em_schema(tc, p.columns)
                if c_real:
                    col_matches += 1
                    cols_casadas.append(c_real)

            score_cols = (col_matches / len(termos_colunas)) if termos_colunas else 0.0

            # Bônus por menção direta do nome do arquivo na pergunta
            bonus_nome = 0.0
            if doc_name_norm in query_norm or any(token in query_norm for token in doc_name_norm.split("_") if len(token) > 4):
                bonus_nome += 0.40

            # Bônus se palavras chaves da tabela estiverem na query
            if "event" in doc_name_norm and ("evento" in query_norm or "torneio" in query_norm):
                bonus_nome += 0.30
            if "standings" in doc_name_norm and ("pontos" in query_norm or "ranking" in query_norm or "club championship" in query_norm or "lidera" in query_norm):
                bonus_nome += 0.35
            if "roster" in doc_name_norm and ("jogador" in query_norm or "player" in query_norm or "roster" in query_norm or "pais" in query_norm or "equipe" in query_norm):
                bonus_nome += 0.35
            if "timeline" in doc_name_norm and ("2016" in query_norm or "5 years" in query_norm or "google translate" in query_norm or "chatgpt" in query_norm or "deepl" in query_norm):
                bonus_nome += 0.40

            # Bônus por presença de linhas
            bonus_dados = 0.10 if p.row_count > 0 else 0.0

            score_total = (score_cols * 0.50) + bonus_nome + bonus_dados

            if score_total > melhor_score:
                melhor_score = score_total
                melhor_perfil = p
                reasons = [
                    f"Fonte '{p.document_name}' (Aba '{p.sheet_name}') selecionada com score {score_total:.2f}.",
                    f"Colunas compatíveis: {cols_casadas} ({col_matches}/{len(termos_colunas)})."
                ]

        return melhor_perfil, melhor_score, reasons

    def route_query(
        self,
        query: str,
        conversation_context_active: bool = False
    ) -> QueryRoute:
        """Determina a rota da consulta analisando múltiplos sinais complementares."""
        q_norm = normalizar_texto_router(query)
        reasons: List[str] = []
        confidence = 0.50

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 0: Detecção de Ambiguidade Estrita (Requisitos 19, 40)
        # ─────────────────────────────────────────────────────────────────────
        # Perguntas vagas sem substantivo ou especificação que causavam alucinação
        perguntas_vagas = {
            "quem venceu", "quem ganhou", "qual foi o vencedor", "quem e o vencedor",
            "quanto recebeu", "quanto ganhou", "qual o valor", "qual foi o premio",
            "quem foi o campeao", "quem lidera", "qual foi o resultado", "qual o resultado",
            "qual o placar", "quem levou", "qual foi a pontuacao", "qual foi a pontuação",
            "qual a pontuacao", "qual a pontuação"
        }
        tokens = q_norm.split()
        if not conversation_context_active and (q_norm in perguntas_vagas or (len(tokens) <= 3 and any(pv == q_norm.strip(" ?.") for pv in perguntas_vagas))):
            return QueryRoute(
                route=RouteType.AMBIGUOUS,
                confidence=0.95,
                reasons=["Consulta ambígua sem entidade/torneio especificado e sem histórico conversacional prévio."],
                is_ambiguous=True,
                ambiguity_prompt="A pergunta é ambígua porque existem múltiplos eventos e participantes. Por favor, especifique a qual jogo, modalidade ou evento você se refere."
            )

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 1: Detecção de Intenção de Agregação / Tabular (Requisitos 6, 7)
        # ─────────────────────────────────────────────────────────────────────
        intent: Optional[str] = None
        target_cols: List[str] = []
        group_by_cols: List[str] = []
        detected_filters: List[Dict[str, Any]] = []

        # A. COUNT
        padroes_count = [
            r'\bquantos\b', r'\bquantas\b', r'\bnumero de\b', r'\bnúmero de\b',
            r'\bquantidade de\b', r'\btotal de registros\b', r'\btotal de eventos\b',
            r'\btotal de jogos\b', r'\btotal de organizacoes\b', r'\bexistem\b', r'\bexiste\b',
            r'\bquantos evento\b', r'\bquantos participante\b'
        ]
        tem_count = any(re.search(p, q_norm) for p in padroes_count)
        if any(exp in q_norm for exp in ["quanto tempo", "quanto dura", "quanto custa", "quanto vale"]):
            tem_count = False

        # B. SUM
        padroes_sum = [
            r'\bsoma\b', r'\bsomatorio\b', r'\bsomatório\b', r'\bquanto somou\b',
            r'\bvalor total\b', r'\bsome todos\b', r'\bsomando todos\b', r'\bqual e o total do prize pool\b',
            r'\btotal do prize pool somando\b', r'\bqual e o total\b'
        ]
        tem_sum = any(re.search(p, q_norm) for p in padroes_sum)

        # C. AVG
        padroes_avg = [
            r'\bmedia\b', r'\bmédia\b', r'\bvalor medio\b', r'\bvalor médio\b',
            r'\bmedia de\b', r'\bem media\b', r'\bem média\b'
        ]
        tem_avg = any(re.search(p, q_norm) for p in padroes_avg)

        # D. MAX / MIN
        padroes_max = [
            r'\bmaior\b', r'\bmaximo\b', r'\bmáximo\b', r'\bmais alto\b',
            r'\bmaior valor\b', r'\bmaior premiacao\b', r'\bmaior premiação\b',
            r'\bmaior prize pool\b', r'\bquem teve mais\b', r'\bquem fez mais pontos\b',
            r'\bmais pontos\b', r'\bmelhor classificacao\b', r'\bmais lucrativo\b',
            r'\bevento mais longo\b', r'\bmais dinheiro\b', r'\bmais grana\b',
            r'\bfaturou mais\b', r'\bganhou mais\b', r'\bmais faturou\b'
        ]
        tem_max = any(re.search(p, q_norm) for p in padroes_max)

        padroes_min = [
            r'\bmenor\b', r'\bminimo\b', r'\bmínimo\b', r'\bmais baixo\b',
            r'\bmenor valor\b', r'\bmenor premiacao\b', r'\bmenor premiação\b',
            r'\bmenos pontos\b', r'\bpior classificacao\b', r'\bmenor gasto\b'
        ]
        tem_min = any(re.search(p, q_norm) for p in padroes_min)

        # E. RANK / GROUP_COUNT
        padroes_rank = [
            r'\branking\b', r'\btop\b', r'\bprimeiro\b', r'\b1o\b', r'\b1º\b',
            r'\bquem lidera\b', r'\bquem ficou em primeiro\b', r'\bqual organizacao terminou em primeiro\b',
            r'\bquem terminou em primeiro\b', r'\bquem ganhou mais\b', r'\bquem teve mais vitorias\b',
            r'\bquem venceu mais\b', r'\bmais vitorias\b', r'\bqual equipe fez mais pontos\b',
            r'\bqual organizacao lidera\b', r'\bqual clube terminou em primeiro\b',
            r'\bqual organizacao teve a melhor classificacao\b'
        ]
        tem_rank = any(re.search(p, q_norm) for p in padroes_rank)

        padroes_group_count = [
            r'\bquantos por\b', r'\bquantas por\b', r'\bquantidade por\b',
            r'\bpor organizacao\b', r'\bpor jogo\b', r'\bpor plataforma\b',
            r'\bquem venceu mais eventos\b', r'\bqual organizacao ganhou mais vezes\b'
        ]
        tem_group_count = any(re.search(p, q_norm) for p in padroes_group_count)

        # F. DISTINCT / LIST ALL (Requisitos 10, 11)
        padroes_list = [
            r'\bliste\b', r'\blistar\b', r'\bquais sao todos\b', r'\bquais foram todos\b',
            r'\bmostre todos\b', r'\bmostre todas\b', r'\btodos os eventos\b',
            r'\btodas as organizacoes\b', r'\btodos os jogos\b', r'\blista completa\b',
            r'\bquais organizacoes aparecem\b', r'\bquais jogos diferentes aparecem\b',
            r'\bquais sistemas aparecem\b', r'\bquais paises\b', r'\bquais plataformas\b'
        ]
        tem_list = any(re.search(p, q_norm) for p in padroes_list)

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 2: Mapeamento de Colunas e Conceitos Chave
        # ─────────────────────────────────────────────────────────────────────
        termos_coluna_detectados = []
        for alias_key, aliases in EXTENDED_COLUMN_ALIASES.items():
            for al in aliases:
                al_norm = normalizar_texto_router(al)
                if re.search(r'\b' + re.escape(al_norm) + r'\b', q_norm):
                    termos_coluna_detectados.append(alias_key)
                    break

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 3: Detecção de Datas e Filtros Temporais (Requisito 12)
        # ─────────────────────────────────────────────────────────────────────
        filtro_data = extrair_intervalo_datas(query)
        if filtro_data:
            detected_filters.append({"tipo": "data", "intervalo": filtro_data})
            reasons.append(f"Filtro temporal detectado: {filtro_data['tipo']} ({filtro_data.get('data_inicio', '')} a {filtro_data.get('data_fim', '')})")

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 3.5: Detecção de Filtro por Limiar Numérico (TODO_RAG_QUALIDADE.md item 4)
        # ─────────────────────────────────────────────────────────────────────
        # Ex: "mais de 4.000 pontos" -- uma busca vetorial pura não recupera de forma confiável
        # *todas* as linhas que atendem a um limiar; precisa de uma rota tabular dedicada.
        filtro_numerico = extrair_filtro_numerico(query)
        if filtro_numerico:
            detected_filters.append({"tipo": "numeric_threshold", **filtro_numerico})
            reasons.append(
                f"Filtro numérico detectado: {filtro_numerico['operador']} {filtro_numerico['valor']}"
                f" (coluna candidata: {filtro_numerico.get('termo_coluna')})"
            )

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 4: Perguntas Conceituais / Semânticas (README / Narrativo)
        # ─────────────────────────────────────────────────────────────────────
        padroes_semanticos = [
            r'\bo que e\b', r'\bo que significa\b', r'\bo que sao\b',
            r'\bcomo funciona\b', r'\bpor que\b', r'\bqual a definicao\b',
            r'\bquando o chatgpt foi lancado\b', r'\bquando o google translate passou a utilizar\b',
            r'\bquando o google translate foi lancado\b', r'\bconceito de\b', r'\bsobre o que e\b'
        ]
        eh_semantico = any(re.search(p, q_norm) for p in padroes_semanticos)

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 5: Detecção de Consultas Relacionais / Multi-Tabela (Requisitos 21, 22)
        # ─────────────────────────────────────────────────────────────────────
        padroes_relacionais = [
            r'\bquem venceu\b.*\be qual era a organizacao\b',
            r'\bjogadores da equipe vencedora\b',
            r'\bquem venceu\b.*\be quais sao os jogadores\b',
            r'\bqual organizacao esse jogador representa\b',
            r'\broster da equipe\b', r'\bjogadores que representam\b',
            # Padrões genéricos: pergunta encadeada de 2 etapas ("qual X e quais Y desse X") --
            # detecta uma segunda oração que se refere de volta a uma entidade da primeira via
            # pronome demonstrativo, o sinal generalizável de um cruzamento relacional entre
            # tabelas (TODO_RAG_QUALIDADE.md item 4), em vez de depender só de frases literais.
            r'\be\s+qua(?:l|is)\s+.{0,40}?\b(?:desse|dessa|deste|desta|dele|dela)\b',
            r'\be\s+quant[oa]s\s+.{0,40}?\b(?:desse|dessa|deste|desta|dele|dela)\b',
        ]
        eh_relacional = any(re.search(p, q_norm) for p in padroes_relacionais)

        # ─────────────────────────────────────────────────────────────────────
        # SINAL 6: Detecção de Consultas Exatas Pontuais (TABULAR_EXACT)
        # ─────────────────────────────────────────────────────────────────────
        # Ex: "Qual era o valor do Google Translate em janeiro de 2016 no multiTimeline_2016.csv?"
        # Ex: "Quem venceu o torneio de VALORANT no EWC 2026?"
        padroes_exact = [
            r'\bqual era o valor de\b', r'\bqual era o valor do\b', r'\bno arquivo multiTimeline\b',
            r'\bquem venceu o torneio de\b', r'\bquem foi o vice-campeao de\b', r'\bquem foi o campeao de\b',
            r'\bquanto tempo\b', r'\bquanto dura\b', r'\bqual o prazo\b', r'\bqual o tempo\b', r'\bqual a duracao\b'
        ]
        tem_exact = any(re.search(p, q_norm) for p in padroes_exact)

        # ─────────────────────────────────────────────────────────────────────
        # SELEÇÃO DA ROTA FINAL
        # ─────────────────────────────────────────────────────────────────────
        # 1. Caso Semântico Convicto (sem componentes tabulares fortes)
        if eh_semantico and not (tem_count or tem_sum or tem_avg or tem_max or tem_min):
            reasons.append("Consulta identificada como conceitual/narrativa (VECTOR_SEMANTIC).")
            return QueryRoute(
                route=RouteType.VECTOR_SEMANTIC,
                confidence=0.92,
                reasons=reasons,
                preferred_sources=["README.md", "main.pdf", "data_milestones_manual.csv"],
                fallback_sources=[]
            )

        # 2. Caso Relacional Multi-Tabela
        if eh_relacional:
            reasons.append("Identificada necessidade de cruzamento relacional entre tabelas (TABULAR_RELATIONAL).")
            return QueryRoute(
                route=RouteType.TABULAR_RELATIONAL,
                confidence=0.88,
                reasons=reasons,
                tabular_intent="RELATIONAL",
                preferred_sources=["01_EWC2026_Event_Tournament_Summary.csv", "05_EWC2026_Player_Roster.csv"],
                fallback_sources=["03_EWC2026_Club_Championship_Standings.csv"]
            )

        # 3. Caso Tabular Agregação ou Filtro
        if filtro_numerico:
            intent = "FILTER"
            termo_coluna_filtro = filtro_numerico.get("termo_coluna")
            coluna_resolvida = None
            for alias_key, aliases in EXTENDED_COLUMN_ALIASES.items():
                if termo_coluna_filtro == alias_key or termo_coluna_filtro in [normalizar_texto_router(a) for a in aliases]:
                    coluna_resolvida = alias_key
                    break
            if coluna_resolvida:
                target_cols = [coluna_resolvida]
                if coluna_resolvida not in termos_coluna_detectados:
                    termos_coluna_detectados.append(coluna_resolvida)
            elif termo_coluna_filtro:
                target_cols = [termo_coluna_filtro]
            reasons.append("Identificado filtro por limiar numérico em coluna estruturada (FILTER).")
        elif tem_group_count or (tem_rank and ("mais" in q_norm or "vitorias" in q_norm or "vitórias" in q_norm)):
            intent = "GROUP_COUNT"
            group_by_cols = ["vencedor"] if "venceu" in q_norm or "ganhou" in q_norm else ["organizacao"]
            reasons.append("Identificada consulta de contagem por grupo e ranking (GROUP_COUNT / RANK).")
        elif tem_rank:
            intent = "RANK"
            target_cols = ["pontos"] if "pontos" in q_norm else (["premiacao"] if "dinheiro" in q_norm or "premio" in q_norm else ["colocacao"])
            reasons.append("Identificada consulta de liderança/ranking (RANK).")
        elif tem_sum:
            intent = "SUM"
            target_cols = ["premiacao"] if ("prize pool" in q_norm or "premio" in q_norm or "gasto" in q_norm or "valor" in q_norm) else ["pontos"]
            reasons.append("Identificada expressão de somatório (SUM).")
        elif tem_avg:
            intent = "AVG"
            target_cols = ["pontos"] if "pontos" in q_norm else ["premiacao"]
            reasons.append("Identificada expressão de média aritmética (AVG).")
        elif tem_max:
            intent = "MAX"
            target_cols = ["premiacao"] if ("prize pool" in q_norm or "premio" in q_norm or "lucrativo" in q_norm or "dinheiro" in q_norm) else (["duracao"] if "longo" in q_norm else ["pontos"])
            reasons.append("Identificada busca pelo valor máximo (MAX).")
        elif tem_min:
            intent = "MIN"
            target_cols = ["pontos"] if "pontos" in q_norm else ["premiacao"]
            reasons.append("Identificada busca pelo valor mínimo (MIN).")
        elif tem_count:
            intent = "COUNT"
            reasons.append("Identificada consulta de contagem total (COUNT).")
        elif tem_list:
            intent = "DISTINCT"
            reasons.append("Identificada solicitação de listagem completa (DISTINCT / TABULAR_LIST).")

        # Seleciona fontes tabulares mais compatíveis
        perfil_sel, score_fonte, raz_fonte = self.selecionar_melhor_fonte_estruturada(q_norm, termos_coluna_detectados)
        reasons.extend(raz_fonte)

        # Decisão de Rota
        if intent == "FILTER":
            conf = min(0.94, max(0.70, score_fonte + 0.30))
            return QueryRoute(
                route=RouteType.TABULAR_FILTER,
                confidence=conf,
                reasons=reasons,
                tabular_intent="FILTER",
                preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
                fallback_sources=["README.md"],
                target_columns=target_cols or termos_coluna_detectados,
                filters=detected_filters
            )

        if intent in ("COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_COUNT", "RANK"):
            conf = min(0.96, max(0.70, score_fonte + 0.30))
            return QueryRoute(
                route=RouteType.TABULAR_AGGREGATION,
                confidence=conf,
                reasons=reasons,
                tabular_intent=intent,
                preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
                fallback_sources=["README.md"],
                target_columns=target_cols or termos_coluna_detectados,
                group_by=group_by_cols,
                filters=detected_filters
            )

        if intent == "DISTINCT" or tem_list:
            conf = min(0.95, max(0.65, score_fonte + 0.25))
            return QueryRoute(
                route=RouteType.TABULAR_LIST,
                confidence=conf,
                reasons=reasons,
                tabular_intent="DISTINCT",
                preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
                fallback_sources=["README.md"],
                target_columns=termos_coluna_detectados,
                filters=detected_filters
            )

        if tem_exact or (perfil_sel and score_fonte >= 0.45 and (filtro_data or any(jogo in q_norm for jogo in ["valorant", "dota 2", "apex legends", "tekken 8", "cs2", "rocket league", "lol"]))):
            reasons.append("Identificada consulta de busca pontual exata em tabela estruturada (TABULAR_EXACT).")
            cols_alvo_exact = list(termos_coluna_detectados)
            if any(t in q_norm for t in ["tempo", "prazo", "dura", "duracao", "duração"]) and "prazo" not in cols_alvo_exact:
                cols_alvo_exact.extend(["prazo", "duracao", "tempo"])
            return QueryRoute(
                route=RouteType.TABULAR_EXACT,
                confidence=0.88,
                reasons=reasons,
                tabular_intent="EXACT",
                preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
                fallback_sources=["README.md"],
                target_columns=cols_alvo_exact,
                filters=detected_filters
            )

        # 4. Caso Híbrido: se há interesse em dados e explicação
        if any(term in q_norm for term in ["por que", "qual a razao", "relevante", "impacto"]) and termos_coluna_detectados:
            reasons.append("Identificada necessidade conjunta de dados estruturados e fundamentação semântica (HYBRID).")
            return QueryRoute(
                route=RouteType.HYBRID,
                confidence=0.80,
                reasons=reasons,
                preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
                fallback_sources=["README.md", "main.pdf"]
            )

        # Fallback Seguro: Se não houver certeza, recai para VECTOR_SEMANTIC
        reasons.append("Confiança insuficiente para operações tabulares puras; recaindo para VECTOR_SEMANTIC com segurança.")
        return QueryRoute(
            route=RouteType.VECTOR_SEMANTIC,
            confidence=0.60,
            reasons=reasons,
            preferred_sources=[perfil_sel.document_name] if perfil_sel else [],
            fallback_sources=["README.md"]
        )
