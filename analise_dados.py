# -*- coding: utf-8 -*-
"""Módulo de Análise de Dados para o Senai LabFashion IA.

Processa planilhas (CSV, XLSX, XLS) localmente com pandas, gera resumos
estatísticos estruturados e agregações numéricas (rankings top/bottom, totais)
e utiliza o LLM apenas para interpretação didática, garantindo que nenhum dado
bruto vaze e que os números sejam calculados deterministicamente.
"""

import io
import json
import os
import unicodedata
from typing import Optional, Any, List
import numpy as np
import pandas as pd

from logger_config import obter_logger


PALAVRAS_CHAVE_AGRUPAMENTO = [
    "produto", "item", "categoria", "departamento", "vendedor", "cliente",
    "regiao", "cidade", "estado", "loja", "filial", "tipo", "modelo",
    "marca", "linha", "canal", "segmento", "colecao", "grupo", "setor",
    "tecido", "material", "cor", "tamanho"
]

PALAVRAS_CHAVE_METRICAS = [
    "quantidade", "qtd", "faturamento", "valor", "preco", "total",
    "receita", "lucro", "venda", "estoque", "custo", "saldo", "volume",
    "peso", "desconto", "pecas", "unidades"
]


def _normalizar_texto(texto: str) -> str:
    """Remove acentos, espaços extras e converte para minúsculas."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()


def carregar_planilha(arquivo: Any, tenant_id: str = "senai_labfashion") -> Optional[pd.DataFrame]:
    """Carrega uma planilha (.csv, .xlsx, .xls) a partir de um objeto de upload (st.file_uploader),
    objeto em memória (bytes/BytesIO) ou caminho de arquivo.

    Retorna:
        pandas.DataFrame se o arquivo for lido com sucesso;
        None em caso de falha ou arquivo corrompido.
    """
    logger = obter_logger(tenant_id)
    if arquivo is None:
        return None

    nome_arquivo = getattr(arquivo, "name", "") or (str(arquivo) if isinstance(arquivo, str) else "arquivo_desconhecido")
    extensao = os.path.splitext(nome_arquivo)[1].lower()

    try:
        if extensao == ".csv":
            # Tenta carregar com utf-8 e separador automático; se falhar, tenta latin1
            try:
                if hasattr(arquivo, "seek"):
                    arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=None, engine="python", encoding="utf-8")
            except Exception:
                if hasattr(arquivo, "seek"):
                    arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=None, engine="python", encoding="latin1")

        elif extensao in [".xlsx", ".xls"]:
            if hasattr(arquivo, "seek"):
                arquivo.seek(0)
            df = pd.read_excel(arquivo)
        else:
            # Tenta inferir pelo conteúdo se a extensão não for explícita
            try:
                if hasattr(arquivo, "seek"):
                    arquivo.seek(0)
                df = pd.read_excel(arquivo)
            except Exception:
                if hasattr(arquivo, "seek"):
                    arquivo.seek(0)
                df = pd.read_csv(arquivo, sep=None, engine="python", encoding="utf-8")

        if df is None or df.empty:
            logger.warning(f"Planilha carregada está vazia: {nome_arquivo}")
            return None

        # Converte nomes de colunas para string limpa
        df.columns = [str(col).strip() for col in df.columns]
        logger.info(f"Planilha '{nome_arquivo}' lida com sucesso: {len(df)} linhas, {len(df.columns)} colunas.")
        return df

    except Exception as e:
        logger.error(
            f"Erro ao carregar planilha '{nome_arquivo}' (ext: {extensao}): {e}",
            exc_info=True
        )
        return None


def _limpar_valor_json(val: Any) -> Any:
    """Converte tipos do numpy/pandas para tipos nativos do Python compatíveis com JSON."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if np.isnan(val) or np.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    return str(val)


def _selecionar_colunas_agrupamento(df: pd.DataFrame, colunas_data: set) -> List[str]:
    """Identifica e seleciona as colunas categóricas mais relevantes para agrupamento (máximo 3)."""
    total_linhas = len(df)
    candidatas = []

    for col in df.columns:
        if col in colunas_data:
            continue

        serie = df[col]
        # Considera colunas de texto/categoria ou mesmo numéricas discretas com poucos valores
        is_cat_type = pd.api.types.is_object_dtype(serie) or isinstance(serie.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(serie)

        n_unique = serie.nunique(dropna=True)
        if n_unique <= 1:
            continue

        # Baixa cardinalidade: até 50 únicos OU até 30% do total de linhas
        eh_baixa_cardinalidade = (n_unique <= 50) or (total_linhas > 0 and (n_unique / total_linhas) <= 0.3)

        if is_cat_type or (eh_baixa_cardinalidade and not pd.api.types.is_float_dtype(serie)):
            nome_norm = _normalizar_texto(str(col))
            
            # Score de prioridade baseado em palavras-chave
            score = 0
            for idx, kw in enumerate(PALAVRAS_CHAVE_AGRUPAMENTO):
                if kw in nome_norm:
                    score = 1000 - idx * 10
                    break

            # Se não bateu com palavra-chave, dá score básico se for texto de baixa cardinalidade
            if score == 0 and is_cat_type and eh_baixa_cardinalidade:
                score = 100

            if score > 0:
                candidatas.append((score, -n_unique, str(col)))

    # Ordena por score decrescente e seleciona no máximo 3
    candidatas.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [col_nome for _, _, col_nome in candidatas[:3]]


def _selecionar_colunas_metricas(df: pd.DataFrame) -> List[str]:
    """Identifica e seleciona as colunas numéricas mais relevantes para métricas (máximo 3)."""
    cols_numericas = df.select_dtypes(include=[np.number]).columns.tolist()
    total_linhas = len(df)
    candidatas = []

    for col in cols_numericas:
        nome_norm = _normalizar_texto(str(col))
        
        # Ignora colunas que parecem IDs puros ou índices
        if (nome_norm.startswith("id_") or nome_norm.startswith("cod_") or nome_norm == "id" or nome_norm == "codigo" or nome_norm == "index"):
            continue

        serie = df[col].dropna()
        if serie.empty or serie.nunique() <= 1:
            continue

        # Se for inteiros perfeitamente sequenciais 1..N, provavelmente é um ID/índice
        if total_linhas > 10 and serie.nunique() == total_linhas and serie.min() == 1 and serie.max() == total_linhas:
            continue

        score = 0
        for idx, kw in enumerate(PALAVRAS_CHAVE_METRICAS):
            if kw in nome_norm:
                score = 1000 - idx * 10
                break

        if score == 0:
            score = 100

        candidatas.append((score, str(col)))

    candidatas.sort(key=lambda x: x[0], reverse=True)
    return [col_nome for _, col_nome in candidatas[:3]]


def gerar_resumo_estatistico(df: pd.DataFrame) -> dict:
    """Gera um resumo estatístico estruturado e compacto a partir de um DataFrame do pandas,
    incluindo agregações pré-calculadas (soma, média, top 10 e bottom 10) por dimensões relevantes.
    """
    if df is None or df.empty:
        return {}

    total_linhas = int(len(df))
    total_colunas = int(len(df.columns))

    colunas_e_tipos = {str(col): str(dtype) for col, dtype in df.dtypes.items()}

    # Identificação de valores ausentes por coluna
    valores_ausentes = {}
    for col in df.columns:
        nulos = int(df[col].isna().sum())
        if nulos > 0:
            valores_ausentes[str(col)] = {
                "quantidade_nulos": nulos,
                "percentual_nulos": round((nulos / total_linhas) * 100, 2)
            }

    # Estatísticas descritivas para colunas numéricas
    cols_numericas = df.select_dtypes(include=[np.number]).columns.tolist()
    estatisticas_numericas = {}
    totais_somas = {}

    if cols_numericas:
        describe_dict = df[cols_numericas].describe().to_dict()
        for col, stats in describe_dict.items():
            estatisticas_numericas[str(col)] = {
                stat: _limpar_valor_json(val) for stat, val in stats.items()
            }
            try:
                soma_col = df[col].sum()
                totais_somas[str(col)] = _limpar_valor_json(soma_col)
            except Exception:
                pass

    # Top 5 valores mais frequentes para colunas categóricas / texto
    cols_categoricas = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()
    top_5_categoricas = {}
    for col in cols_categoricas:
        try:
            serie_limpa = df[col].dropna().astype(str).str.strip()
            if not serie_limpa.empty:
                contagens = serie_limpa.value_counts().head(5).to_dict()
                top_5_categoricas[str(col)] = {
                    str(k): int(v) for k, v in contagens.items()
                }
        except Exception:
            continue

    # Detecção e resumo de colunas de data
    colunas_data = {}
    nomes_colunas_data = set()
    for col in df.columns:
        is_datetime = pd.api.types.is_datetime64_any_dtype(df[col])
        if not is_datetime and ("data" in str(col).lower() or "date" in str(col).lower() or "periodo" in str(col).lower()):
            try:
                dt_series = pd.to_datetime(df[col], errors="coerce")
                if dt_series.notna().sum() > (0.5 * total_linhas):
                    is_datetime = True
                else:
                    dt_series = None
            except Exception:
                dt_series = None
        else:
            dt_series = df[col] if is_datetime else None

        if is_datetime and dt_series is not None:
            nomes_colunas_data.add(col)
            dt_validos = dt_series.dropna()
            if not dt_validos.empty:
                colunas_data[str(col)] = {
                    "data_minima": dt_validos.min().strftime("%Y-%m-%d") if hasattr(dt_validos.min(), "strftime") else str(dt_validos.min()),
                    "data_maxima": dt_validos.max().strftime("%Y-%m-%d") if hasattr(dt_validos.max(), "strftime") else str(dt_validos.max()),
                    "total_registros_validos": int(len(dt_validos))
                }

    # Agregações automáticas por combinações relevantes (máx 3x3)
    cols_agrupamento = _selecionar_colunas_agrupamento(df, nomes_colunas_data)
    cols_metricas = _selecionar_colunas_metricas(df)

    agregacoes = {}
    if cols_agrupamento and cols_metricas:
        for cat_col in cols_agrupamento:
            agregacoes[str(cat_col)] = {}
            for num_col in cols_metricas:
                try:
                    # Agrupamento com soma
                    serie_agrupada = df.groupby(cat_col)[num_col].sum().dropna()
                    if serie_agrupada.empty:
                        continue

                    # Top 10 maiores (descendente)
                    top_10 = serie_agrupada.sort_values(ascending=False).head(10)
                    top_10_dict = {str(k): _limpar_valor_json(v) for k, v in top_10.items()}

                    # Bottom 10 menores (ascendente)
                    bottom_10 = serie_agrupada.sort_values(ascending=True).head(10)
                    bottom_10_dict = {str(k): _limpar_valor_json(v) for k, v in bottom_10.items()}

                    total_geral = _limpar_valor_json(df[num_col].sum())
                    media_por_grupo = _limpar_valor_json(serie_agrupada.mean())

                    agregacoes[str(cat_col)][str(num_col)] = {
                        "top_10": top_10_dict,
                        "bottom_10": bottom_10_dict,
                        "total_geral": total_geral,
                        "media_por_grupo": media_por_grupo
                    }
                except Exception:
                    continue

    resumo = {
        "metadados": {
            "total_linhas": total_linhas,
            "total_colunas": total_colunas,
            "colunas": list(df.columns)
        },
        "colunas_e_tipos": colunas_e_tipos,
        "valores_ausentes": valores_ausentes,
        "estatisticas_numericas": estatisticas_numericas,
        "totais_somas_numericas": totais_somas,
        "top_5_frequencias_categoricas": top_5_categoricas,
        "colunas_data": colunas_data,
        "agregacoes": agregacoes
    }

    return resumo


def responder_pergunta_sobre_dados(
    client: Any,
    pergunta: str,
    resumo_estatistico: dict,
    prompt_sistema: str,
    modelo: str = "openai/gpt-oss-20b",
    tenant_id: str = "senai_labfashion"
) -> str:
    """Monta a mensagem para a API da Groq contendo o resumo_estatistico serializado
    em JSON como contexto seguro, mais a pergunta do usuário, e retorna a resposta interpretada.
    """
    logger = obter_logger(tenant_id)
    if not client:
        raise ValueError("Cliente da API Groq não fornecido ou inválido.")

    if not resumo_estatistico:
        return "Nenhum resumo de dados foi fornecido para análise. Por favor, faça o upload de uma planilha válida primeiro."

    try:
        resumo_json = json.dumps(resumo_estatistico, ensure_ascii=False, indent=2)

        instrucao_seguranca = (
            f"{prompt_sistema}\n\n"
            "--- RESUMO ESTATÍSTICO ESTRUTURADO DA PLANILHA (CALCULADO EM PYTHON) ---\n"
            f"```json\n{resumo_json}\n```\n\n"
            "DIRETRIZES DE RESPOSTA:\n"
            "1. O campo `agregacoes` no resumo JSON acima contém totais somados e rankings (`top_10` e `bottom_10`) pré-calculados por categoria (ex: soma de quantidade ou faturamento por produto/categoria). Utilize esses dados diretamente para responder a perguntas como 'quais produtos venderam mais', 'quais venderam menos', 'maior faturamento', etc., em vez de recorrer apenas às contagens de frequência de linhas.\n"
            "2. Baseie TODAS as suas afirmações e números ESTRITAMENTE no resumo estatístico JSON acima.\n"
            "3. NUNCA invente, deduza ou adivinhe valores numéricos que não estejam expressamente no resumo.\n"
            "4. Se o campo `agregacoes` estiver vazio ({}) e a pergunta exigir agregações/rankings que não puderam ser calculados, ou se o usuário fizer uma pergunta que exija um dado específico não presente no resumo, informe com clareza e gentileza que a planilha não parece ter colunas adequadas para esse tipo de análise agrupada e sugira que o usuário renomeie ou organize as colunas com nomes mais claros (como 'Produto', 'Quantidade' e 'Faturamento').\n"
            "5. Responda em português simples, direto, didático e profissional, evitando jargões técnicos excessivos."
        )

        mensagens = [
            {"role": "system", "content": instrucao_seguranca},
            {"role": "user", "content": pergunta}
        ]

        resposta = client.chat.completions.create(
            messages=mensagens,
            model=modelo,
            temperature=0.3,
            max_tokens=2048,
        )

        texto_resposta = resposta.choices[0].message.content or ""
        return texto_resposta

    except Exception as e:
        logger.error(f"Erro ao consultar LLM sobre resumo de dados: {e}", exc_info=True)
        raise
