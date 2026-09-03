# -*- coding: utf-8 -*-
"""Módulo Centralizado de Enriquecimento Semântico de Dados Estruturados.

Transforma propriedades implícitas de dados tabulares (CSV, XLSX, XLS) em representações
textuais explícitas, legíveis e marcadores estruturados pesquisáveis para o RAG,
preservando integralmente os dados e metadados originais.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# Dicionário de meses em português para formatação de datas legíveis
MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
}

# Categorias conceituais de colunas para enriquecimento contextual seguro
COLUNAS_FINANCEIRAS = {
    "valor", "preco", "preço", "custo", "receita", "despesa", "saldo",
    "pagamento", "faturamento", "total", "orcamento", "orçamento",
    "taxa", "tarifa", "montante", "debito", "débito", "credito", "crédito",
    "reembolso", "honorarios", "honorários"
}

COLUNAS_QUANTIDADE = {
    "quantidade", "qtd", "quant", "volume", "estoque", "unidades", "unidade",
    "contagem", "itens", "saldo_itens"
}

COLUNAS_MEDIDA = {
    "temperatura", "peso", "gramatura", "largura", "altura", "comprimento",
    "espessura", "tamanho", "graus"
}

COLUNAS_RESPONSAVEL = {
    "responsavel", "responsável", "resp", "consultor", "consultora",
    "atendente", "analista", "operador", "autor", "aprovador", "criador",
    "usuario", "usuário", "solicitante", "funcionario", "funcionário",
    "colaborador", "colaboradora"
}

COLUNAS_DATA = {
    "data", "date", "dt", "data_lancamento", "data_lançamento",
    "data_pagamento", "data_emissao", "data_emissão", "data_registro",
    "criado_em", "atualizado_em"
}


@dataclass
class EnrichedRecord:
    """Estrutura enriquecida de um registro ou linha tabular."""
    texto_formatado: str
    propriedades_detectadas: List[str] = field(default_factory=list)
    marcadores_estruturados: List[str] = field(default_factory=list)
    metadados_derivados: Dict[str, Any] = field(default_factory=dict)
    dados_originais_pares: List[Tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "texto_formatado": self.texto_formatado,
            "propriedades_detectadas": self.propriedades_detectadas,
            "marcadores_estruturados": self.marcadores_estruturados,
            "metadados_derivados": self.metadados_derivados,
            "dados_originais_pares": self.dados_originais_pares
        }


def normalizar_nome_coluna(coluna: str) -> str:
    """Normaliza o nome da coluna para identificação de categoria semântica."""
    if not coluna:
        return ""
    texto = coluna.strip().lower()
    # Remove acentos para normalização conceitual
    substituicoes = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', '_': ' ', '-': ' '
    }
    for c_orig, c_sub in substituicoes.items():
        texto = texto.replace(c_orig, c_sub)
    texto = re.sub(r'[^a-z0-9 ]', '', texto)
    return "_".join(texto.split())


def _eh_valor_vazio(val: Any) -> bool:
    """Verifica com precisão se um valor é vazio/ausente (diferenciando de zero)."""
    if val is None:
        return True
    s = str(val).strip()
    if not s:
        return True
    s_low = s.lower()
    return s_low in {"none", "nan", "null", "n/a", "na", "-", "--", "não informado", "nao informado", "vazio"}


def _eh_valor_zero(val: Any) -> bool:
    """Verifica se um valor numérico ou textual representa exatamente zero."""
    if val is None:
        return False
    s = str(val).strip()
    if s in {"0", "0.0", "0.00", "0,00", "0,0", "-0", "+0", "-0.0", "-0.00", "-0,00"}:
        return True
    try:
        # Trata formato numérico com vírgula ou ponto
        s_clean = s.replace(".", "").replace(",", ".") if "," in s and "." in s else s.replace(",", ".")
        f = float(s_clean)
        return abs(f) < 1e-9
    except (ValueError, TypeError):
        return False


def _parse_numero_generico(val: Any) -> Optional[float]:
    """Tenta converter um valor para float suportando formatos brasileiros e internacionais."""
    if val is None or _eh_valor_vazio(val):
        return None
    s = str(val).strip()
    # Remove símbolos de moeda ou espaços
    s = re.sub(r'^[R$\s]+', '', s)
    s = re.sub(r'[\s]+', '', s)
    
    # Formato brasileiro: 1.234,56 ou -150,00
    if re.match(r'^-?\d{1,3}(?:\.\d{3})*,\d+$', s):
        try:
            return float(s.replace(".", "").replace(",", "."))
        except ValueError:
            pass
    elif re.match(r'^-?\d+,\d+$', s):
        try:
            return float(s.replace(",", "."))
        except ValueError:
            pass
    elif re.match(r'^-?\d+(?:\.\d+)?$', s):
        try:
            return float(s)
        except ValueError:
            pass
    elif re.match(r'^-?\d{1,3}(?:,\d{3})*\.\d+$', s):
        try:
            return float(s.replace(",", ""))
        except ValueError:
            pass
    return None


def _formatar_data_legivel(val: Any) -> Optional[str]:
    """Converte datas nos formatos ISO (YYYY-MM-DD) ou BR (DD/MM/YYYY) para data por extenso em português."""
    if not val:
        return None
    s = str(val).strip()
    
    # YYYY-MM-DD ou YYYY/MM/DD
    m_iso = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s].*)?$', s)
    if m_iso:
        ano, mes, dia = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1 <= mes <= 12 and 1 <= dia <= 31 and 1900 <= ano <= 2100:
            mes_nome = MESES_PT.get(mes, str(mes))
            return f"{dia} de {mes_nome} de {ano}"

    # DD/MM/YYYY ou DD-MM-YYYY
    m_br = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:[T\s].*)?$', s)
    if m_br:
        dia, mes, ano = int(m_br.group(1)), int(m_br.group(2)), int(m_br.group(3))
        if 1 <= mes <= 12 and 1 <= dia <= 31 and 1900 <= ano <= 2100:
            mes_nome = MESES_PT.get(mes, str(mes))
            return f"{dia} de {mes_nome} de {ano}"

    return None


def enriquecer_registro_estruturado(
    dados_registro: Union[Dict[str, Any], List[Tuple[str, Any]]],
    colunas_esperadas: Optional[List[str]] = None,
    contexto_origem: Optional[Dict[str, Any]] = None
) -> EnrichedRecord:
    """Enriquece semanticamente um registro tabular/estruturado.

    Recebe os pares chave-valor do registro (ex: linha de CSV ou Excel), analisa tipos de dados,
    ausências, zeros, datas e números negativos, e gera a representação textual legível,
    propriedades explícitas, marcadores estruturados e metadados derivados compatíveis com o ChromaDB.
    """
    if isinstance(dados_registro, dict):
        itens_registro = list(dados_registro.items())
    elif isinstance(dados_registro, list):
        itens_registro = dados_registro
    else:
        itens_registro = []

    propriedades: List[str] = []
    marcadores: List[str] = []
    pares_formatados: List[Tuple[str, str]] = []
    
    tem_valor_negativo = False
    tem_campo_ausente = False
    campos_ausentes_list: List[str] = []
    tem_valor_zero = False

    chaves_presentes_norm: Set[str] = set()

    for col_nome, val in itens_registro:
        col_norm = normalizar_nome_coluna(col_nome)
        chaves_presentes_norm.add(col_norm)

        # 1. Tratamento de Célula Vazia / Ausente
        if _eh_valor_vazio(val):
            tem_campo_ausente = True
            campos_ausentes_list.append(col_norm)
            pares_formatados.append((col_nome, "não informado"))
            propriedades.append(f"Campo {col_nome} não preenchido")
            marcadores.append(f"[CAMPO_VAZIO:{col_norm.upper()}]")
            
            # Marcadores específicos de domínio para campos ausentes comuns
            if col_norm in COLUNAS_RESPONSAVEL:
                propriedades.append("Responsável não informado")
                marcadores.extend(["[RESPONSAVEL_AUSENTE]", "[CAMPO_RESPONSAVEL_NAO_INFORMADO]", "[RESPONSAVEL_NAO_INFORMADO]"])
            elif col_norm in COLUNAS_FINANCEIRAS:
                propriedades.append(f"Valor financeiro no campo {col_nome} não informado")
                marcadores.extend([f"[{col_norm.upper()}_AUSENTE]", f"[CAMPO_{col_norm.upper()}_NAO_INFORMADO]"])
            continue

        val_str = str(val).strip()

        # 2. Tratamento de Valor Zero
        if _eh_valor_zero(val):
            tem_valor_zero = True
            pares_formatados.append((col_nome, val_str))
            propriedades.append(f"Valor igual a zero no campo {col_nome}")
            marcadores.extend(["[VALOR_ZERO]", "[VALOR_IGUAL_A_ZERO]", f"[VALOR_ZERO:{col_norm.upper()}]"])
            continue

        # 3. Tratamento de Datas
        data_legivel = _formatar_data_legivel(val_str)
        if data_legivel and (col_norm in COLUNAS_DATA or re.search(r'\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4}', val_str)):
            pares_formatados.append((col_nome, f"{val_str} ({data_legivel})"))
            propriedades.append(f"Data: {data_legivel}")
            marcadores.append(f"[DATA:{col_norm.upper()}]")
            continue

        # 4. Tratamento de Números (Positivos e Negativos)
        num_val = _parse_numero_generico(val_str)
        if num_val is not None:
            pares_formatados.append((col_nome, val_str))
            
            if num_val < 0:
                tem_valor_negativo = True
                
                # Diferenciação contextual: Campo financeiro vs Quantidade/Medida vs Outro
                if col_norm in COLUNAS_FINANCEIRAS:
                    propriedades.append(f"Valor negativo ({val_str}) no campo {col_nome}")
                    propriedades.append("Lançamento com valor abaixo de zero")
                    marcadores.extend([
                        "[VALOR_NEGATIVO]",
                        "[VALOR_ABAIXO_DE_ZERO]",
                        f"[NUMERO_NEGATIVO:{col_norm.upper()}]"
                    ])
                elif col_norm in COLUNAS_QUANTIDADE:
                    propriedades.append(f"Quantidade negativa ({val_str}) no campo {col_nome}")
                    propriedades.append(f"Número negativo no campo {col_nome}")
                    marcadores.extend([
                        "[QUANTIDADE_NEGATIVA]",
                        f"[NUMERO_NEGATIVO:{col_norm.upper()}]"
                    ])
                elif col_norm in COLUNAS_MEDIDA:
                    propriedades.append(f"{col_nome.capitalize()} negativa ({val_str})")
                    propriedades.append(f"Número negativo no campo {col_nome}")
                    marcadores.extend([
                        f"[{col_norm.upper()}_NEGATIVA]",
                        f"[NUMERO_NEGATIVO:{col_norm.upper()}]"
                    ])
                else:
                    propriedades.append(f"Número negativo ({val_str}) no campo {col_nome}")
                    marcadores.append(f"[NUMERO_NEGATIVO:{col_norm.upper()}]")
            continue

        # 5. Valor Textual Padrão
        pares_formatados.append((col_nome, val_str))

    # 6. Tratamento de Colunas Inexistentes no Registro (quando verificado contra schema esperado)
    if colunas_esperadas:
        for col_esp in colunas_esperadas:
            esp_norm = normalizar_nome_coluna(col_esp)
            if esp_norm and esp_norm not in chaves_presentes_norm:
                propriedades.append(f"Campo {col_esp} inexistente neste registro")
                marcadores.append(f"[CAMPO_{esp_norm.upper()}_INEXISTENTE]")
                if esp_norm in COLUNAS_RESPONSAVEL:
                    marcadores.append("[CAMPO_RESPONSAVEL_INEXISTENTE]")

    # 7. Montagem do Texto Estruturado e Legível
    linhas_texto: List[str] = []
    for k, v in pares_formatados:
        linhas_texto.append(f"{k}: {v}")

    # Deduplicação preservando ordem de propriedades e marcadores
    propriedades_dedup = list(dict.fromkeys(propriedades))
    marcadores_dedup = list(dict.fromkeys(marcadores))

    if propriedades_dedup:
        linhas_texto.append("\nPropriedades detectadas:")
        for p in propriedades_dedup:
            linhas_texto.append(f"- {p}")

    if marcadores_dedup:
        linhas_texto.append("\nMarcadores estruturados:")
        linhas_texto.append(" ".join(marcadores_dedup))

    texto_final = "\n".join(linhas_texto).strip()

    # 8. Metadados Derivados Primitivos (ChromaDB Safe)
    metadados_derivados = {
        "tem_valor_negativo": bool(tem_valor_negativo),
        "tem_campo_ausente": bool(tem_campo_ausente),
        "campos_ausentes": ",".join(sorted(list(set(campos_ausentes_list)))) if campos_ausentes_list else "",
        "tem_valor_zero": bool(tem_valor_zero)
    }

    return EnrichedRecord(
        texto_formatado=texto_final,
        propriedades_detectadas=propriedades_dedup,
        marcadores_estruturados=marcadores_dedup,
        metadados_derivados=metadados_derivados,
        dados_originais_pares=pares_formatados
    )
