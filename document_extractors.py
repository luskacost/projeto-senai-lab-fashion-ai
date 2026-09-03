# -*- coding: utf-8 -*-
"""Módulo de Extração Centralizada e Normalizada de Documentos para o RAG.

Suporta extração estruturada de múltiplos formatos de arquivo:
- PDF (.pdf) via pypdf
- Word (.docx) via python-docx (parágrafos, cabeçalhos e tabelas)
- Texto (.txt) com suporte a múltiplos encodings
- Markdown (.md) preservando hierarquia de seções e tabelas
- CSV (.csv) com detecção automática de delimitadores e mapeamento chave-valor
- Excel (.xlsx e .xls) via openpyxl e xlrd, preservando abas, linhas e cabeçalhos
- PowerPoint (.pptx) via python-pptx, preservando slides, caixas de texto e tabelas

Todos os extratores produzem uma lista de unidades normalizadas com metadados estruturados:
[
    {
        "pagina": int,
        "texto": str,
        "metadados": {
            "tipo_arquivo": str,
            "rotulo_unidade": str,
            ...
        }
    }
]
"""

import os
import io
import csv
import re
from typing import List, Dict, Any, Optional, Tuple, Union

from logger_config import obter_logger
from rag_config import RAG_CONFIG
from semantic_enrichment import enriquecer_registro_estruturado
from tabular_storage import TabularRow, TabularSheet

def obter_extensoes_suportadas() -> List[str]:
    """Retorna a lista única de extensões suportadas sincronizada diretamente com o RAG_CONFIG."""
    exts = RAG_CONFIG.get("supported_extensions", ["pdf", "docx", "txt", "md", "csv", "xlsx", "xls", "pptx"])
    return [ext.lower().lstrip(".") for ext in exts]

# Fonte única derivada diretamente de RAG_CONFIG
EXTENSOES_SUPORTADAS: List[str] = obter_extensoes_suportadas()
SUPPORTED_EXTENSIONS: List[str] = EXTENSOES_SUPORTADAS


def obter_extensao_normalizada(nome_arquivo_ou_caminho: str) -> str:
    """Extrai e normaliza a extensão do arquivo em minúsculas e sem ponto inicial."""
    if not nome_arquivo_ou_caminho:
        return ""
    _, ext = os.path.splitext(nome_arquivo_ou_caminho)
    return ext.lower().lstrip(".")


def _obter_info_arquivo(
    arquivo: Union[io.BytesIO, bytes, str, Any],
    nome_arquivo: Optional[str] = None
) -> Tuple[io.BytesIO, str, str]:
    """Obtém um stream BytesIO, o nome do arquivo e a extensão normalizada.

    Valida limites de tamanho de arquivo contra RAG_CONFIG.
    """
    logger = obter_logger()
    max_mb = RAG_CONFIG.get("max_file_size_mb", 50)
    max_bytes = max_mb * 1024 * 1024

    nome = nome_arquivo or getattr(arquivo, "name", None)

    if isinstance(arquivo, str):
        if not nome:
            nome = os.path.basename(arquivo)
        if not os.path.exists(arquivo):
            raise FileNotFoundError(f"Arquivo não encontrado: {arquivo}")
        tam = os.path.getsize(arquivo)
        if tam > max_bytes:
            raise ValueError(f"O arquivo '{nome}' excede o tamanho máximo permitido de {max_mb} MB (tamanho: {tam / 1024 / 1024:.2f} MB).")
        with open(arquivo, "rb") as f:
            bytes_data = f.read()
        stream = io.BytesIO(bytes_data)

    elif isinstance(arquivo, bytes):
        if not nome:
            nome = "documento"
        if len(arquivo) > max_bytes:
            raise ValueError(f"O arquivo '{nome}' excede o tamanho máximo permitido de {max_mb} MB.")
        stream = io.BytesIO(arquivo)

    elif hasattr(arquivo, "read"):
        if not nome:
            nome = "documento"
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        bytes_data = arquivo.read()
        if hasattr(arquivo, "seek"):
            arquivo.seek(0)
        if isinstance(bytes_data, str):
            bytes_data = bytes_data.encode("utf-8")
        if len(bytes_data) > max_bytes:
            raise ValueError(f"O arquivo '{nome}' excede o tamanho máximo permitido de {max_mb} MB.")
        stream = io.BytesIO(bytes_data)

    else:
        raise ValueError(f"Tipo de objeto de arquivo não suportado: {type(arquivo)}")

    extensao = obter_extensao_normalizada(nome)
    return stream, nome, extensao


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: PDF (.pdf)
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_pdf(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai conteúdo de um arquivo PDF mantendo a numeração e separação por página."""
    from pypdf import PdfReader
    logger = obter_logger()
    stream.seek(0)
    reader = PdfReader(stream)

    if len(reader.pages) == 0:
        return []

    unidades: List[Dict[str, Any]] = []
    for i, pagina in enumerate(reader.pages, start=1):
        try:
            texto_pag = pagina.extract_text() or ""
            linhas_limpas = [l.rstrip() for l in texto_pag.splitlines()]
            texto_limpo = "\n".join(linhas_limpas).strip()
            if texto_limpo:
                unidades.append({
                    "pagina": i,
                    "texto": texto_limpo,
                    "metadados": {
                        "tipo_arquivo": "pdf",
                        "rotulo_unidade": f"Página {i}",
                    }
                })
        except Exception as pag_err:
            logger.warning(f"Aviso ao extrair página {i} do PDF '{nome_arquivo}': {pag_err}")

    return unidades


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: WORD (.docx)
# ─────────────────────────────────────────────────────────────────────────────
def _formatar_tabela_docx(tabela) -> str:
    """Converte uma tabela do python-docx em representação textual estruturada."""
    linhas_tabela = []
    for row in tabela.rows:
        celulas = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        # Remove células duplicadas por merge consecutivo
        celulas_dedup = []
        for c in celulas:
            if not celulas_dedup or c != celulas_dedup[-1]:
                celulas_dedup.append(c)
        if any(celulas_dedup):
            linhas_tabela.append(celulas_dedup)

    if not linhas_tabela:
        return ""

    if len(linhas_tabela) == 1:
        return " | ".join(linhas_tabela[0])

    cabecalho = linhas_tabela[0]
    dados = linhas_tabela[1:]

    linhas_str = ["[TABELA]"]
    linhas_str.append("Colunas: " + " | ".join(cabecalho))
    linhas_str.append("Dados:")
    for d in dados:
        linhas_str.append(" | ".join(d))

    return "\n".join(linhas_str)


def extrair_documento_docx(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai conteúdo de um arquivo DOCX mantendo títulos, parágrafos e tabelas em ordem."""
    import docx
    from docx.text.paragraph import Paragraph
    from docx.table import Table

    stream.seek(0)
    doc = docx.Document(stream)

    blocos: List[str] = []
    secao_atual: Optional[str] = None
    unidades: List[Dict[str, Any]] = []

    for elemento in doc.element.body:
        tag = elemento.tag.split("}")[-1] if "}" in elemento.tag else elemento.tag

        if tag == "p":
            p = Paragraph(elemento, doc)
            txt = p.text.strip()
            if not txt:
                continue

            style_name = p.style.name if p.style else ""
            if any(h in style_name.lower() for h in ["heading", "title", "título", "subtítulo", "subtitle", "header"]):
                if txt:
                    secao_atual = txt
                    blocos.append(f"\n### {txt}\n")
            elif "list" in style_name.lower() or "bullet" in style_name.lower():
                blocos.append(f"- {txt}")
            else:
                blocos.append(txt)

        elif tag == "tbl":
            t = Table(elemento, doc)
            txt_tabela = _formatar_tabela_docx(t)
            if txt_tabela:
                blocos.append(txt_tabela)

    texto_completo = "\n\n".join(b for b in blocos if b.strip()).strip()
    if not texto_completo:
        return []

    # Divide por seções principais se houver marcadores de cabeçalho explícitos
    padrao_secao = re.compile(r'(?=\n###\s+)', re.IGNORECASE)
    secoes = [s.strip() for s in padrao_secao.split(texto_completo) if s.strip()]

    if len(secoes) > 1:
        for idx, sec in enumerate(secoes, start=1):
            primeira_linha = sec.splitlines()[0].replace("###", "").strip() if sec else ""
            rotulo = f"Seção: {primeira_linha}" if primeira_linha else f"Seção {idx}"
            unidades.append({
                "pagina": idx,
                "texto": sec,
                "metadados": {
                    "tipo_arquivo": "docx",
                    "rotulo_unidade": rotulo,
                    "secao_origem": primeira_linha or rotulo
                }
            })
    else:
        unidades.append({
            "pagina": 1,
            "texto": texto_completo,
            "metadados": {
                "tipo_arquivo": "docx",
                "rotulo_unidade": "Documento",
            }
        })

    return unidades


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: TXT (.txt)
# ─────────────────────────────────────────────────────────────────────────────
def _decodificar_bytes_texto(raw_bytes: bytes) -> str:
    """Tenta decodificar bytes em string utilizando uma cadeia de encodings com fallback."""
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]
    for enc in encodings:
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue

    # Fallback com substituição de caracteres não reconhecidos
    return raw_bytes.decode("utf-8", errors="replace")


def extrair_documento_txt(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai conteúdo de arquivo de texto puro com tratamento robusto de encoding."""
    stream.seek(0)
    raw = stream.read()
    if not raw:
        return []

    texto = _decodificar_bytes_texto(raw)
    linhas = [l.rstrip() for l in texto.splitlines()]
    texto_limpo = "\n".join(linhas).strip()

    if not texto_limpo:
        return []

    return [{
        "pagina": 1,
        "texto": texto_limpo,
        "metadados": {
            "tipo_arquivo": "txt",
            "rotulo_unidade": "Documento de Texto"
        }
    }]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: MARKDOWN (.md)
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_md(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai conteúdo de arquivos Markdown preservando a hierarquia de títulos e tabelas."""
    stream.seek(0)
    raw = stream.read()
    if not raw:
        return []

    texto = _decodificar_bytes_texto(raw)
    texto_limpo = texto.strip()
    if not texto_limpo:
        return []

    # Divide por títulos principais (# ou ##) preservando unidades de conteúdo
    padrao_h = re.compile(r'(?=(?:^|\n)#{1,2}\s+)', re.MULTILINE)
    secoes = [s.strip() for s in padrao_h.split(texto_limpo) if s.strip()]

    if len(secoes) > 1:
        unidades: List[Dict[str, Any]] = []
        for idx, sec in enumerate(secoes, start=1):
            primeira_linha = sec.splitlines()[0].lstrip("#").strip() if sec else ""
            rotulo = f"Seção: {primeira_linha}" if primeira_linha else f"Seção {idx}"
            unidades.append({
                "pagina": idx,
                "texto": sec,
                "metadados": {
                    "tipo_arquivo": "md",
                    "rotulo_unidade": rotulo,
                    "secao_origem": primeira_linha or rotulo
                }
            })
        return unidades

    return [{
        "pagina": 1,
        "texto": texto_limpo,
        "metadados": {
            "tipo_arquivo": "md",
            "rotulo_unidade": "Documento Markdown"
        }
    }]


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: CSV (.csv)
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_csv(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai dados de CSV preservando o mapeamento estruturado chave-valor por linha."""
    stream.seek(0)
    raw = stream.read()
    if not raw:
        return []

    texto = _decodificar_bytes_texto(raw)
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        return []

    # Detecta delimitador (, ; ou \t)
    primeira_linha = linhas[0]
    delimitador = ","
    try:
        sniffer = csv.Sniffer()
        amostra = "\n".join(linhas[:5])
        dialect = sniffer.sniff(amostra, delimiters=",;\t|")
        delimitador = dialect.delimiter
    except Exception:
        cont_virgula = primeira_linha.count(",")
        cont_ponto_virgula = primeira_linha.count(";")
        cont_tab = primeira_linha.count("\t")
        if cont_ponto_virgula > cont_virgula and cont_ponto_virgula > cont_tab:
            delimitador = ";"
        elif cont_tab > cont_virgula and cont_tab > cont_ponto_virgula:
            delimitador = "\t"

    leitor = csv.reader(linhas, delimiter=delimitador)
    linhas_parsed = [r for r in leitor if any(c.strip() for c in r)]
    if not linhas_parsed:
        return []

    cabecalho = [c.strip() for c in linhas_parsed[0]]
    dados = linhas_parsed[1:]

    max_rows = RAG_CONFIG.get("max_csv_rows", 5000)
    unidades: List[Dict[str, Any]] = []
    linhas_tabulares: List[TabularRow] = []

    for idx, row in enumerate(dados[:max_rows], start=2):
        pares_linha = []
        dados_linha_dict: Dict[str, Any] = {}
        for i in range(len(cabecalho)):
            col_nome = cabecalho[i] if cabecalho[i] else f"Coluna_{i + 1}"
            val = row[i] if i < len(row) else ""
            pares_linha.append((col_nome, val))
            dados_linha_dict[col_nome] = val

        if len(row) > len(cabecalho):
            for j in range(len(cabecalho), len(row)):
                col_extra = f"Coluna_{j + 1}"
                pares_linha.append((col_extra, row[j]))
                dados_linha_dict[col_extra] = row[j]

        if any(str(v).strip() for _, v in pares_linha):
            registro_enr = enriquecer_registro_estruturado(
                pares_linha,
                colunas_esperadas=cabecalho,
                contexto_origem={"tipo_arquivo": "csv", "linha": idx, "documento": nome_arquivo}
            )
            meta_unidade = {
                "tipo_arquivo": "csv",
                "linha": idx,
                "rotulo_unidade": f"Linha {idx}"
            }
            meta_unidade.update(registro_enr.metadados_derivados)
            unidades.append({
                "pagina": idx,
                "texto": registro_enr.texto_formatado,
                "metadados": meta_unidade
            })
            linhas_tabulares.append(TabularRow(
                linha=idx,
                dados=dados_linha_dict,
                metadados_derivados=registro_enr.metadados_derivados,
                propriedades_detectadas=registro_enr.propriedades_detectadas,
                marcadores_estruturados=registro_enr.marcadores_estruturados
            ))

    return unidades, {"Tabela": TabularSheet(nome_aba="Tabela", schema=cabecalho, linhas=linhas_tabulares)}


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: EXCEL (.xlsx e .xls)
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_excel(
    stream: io.BytesIO,
    nome_arquivo: str,
    extensao: str
) -> List[Dict[str, Any]]:
    """Extrai dados de planilhas Excel (.xlsx ou .xls) por aba e linha estruturada."""
    logger = obter_logger()
    stream.seek(0)

def _processar_linhas_planilha_estruturada(
    linhas_com_indice: List[Tuple[int, List[str]]],
    sheet_name: str,
    extensao: str,
    pagina_inicio: int = 1
) -> Tuple[List[Dict[str, Any]], int, TabularSheet]:
    """Processa linhas de uma aba detectando automaticamente se é tabular ou ficha técnica/chave-valor.

    Preserva contextos de fichas técnicas e pares chave-valor sem assumir cegamente que a primeira
    linha é um cabeçalho tabular.
    """
    if not linhas_com_indice:
        sheet_vazia = TabularSheet(nome_aba=sheet_name, schema=[], linhas=[])
        return [], pagina_inicio, sheet_vazia

    linhas_validas: List[Tuple[int, List[str]]] = []
    for r_idx, row in linhas_com_indice:
        celulas = [str(c).strip() if c is not None else "" for c in row]
        # Remove valores None convertidos em string
        celulas = ["" if c.lower() == "none" else c for c in celulas]
        # Remove sufixo .0 em inteiros vindos de XLS
        celulas = [re.sub(r'\.0$', '', c) if re.match(r'^-?\d+\.0$', c) else c for c in celulas]
        while celulas and not celulas[-1]:
            celulas.pop()
        if any(celulas):
            linhas_validas.append((r_idx, celulas))

    if not linhas_validas:
        sheet_vazia = TabularSheet(nome_aba=sheet_name, schema=[], linhas=[])
        return [], pagina_inicio, sheet_vazia

    qtd_linhas = len(linhas_validas)
    linhas_com_rotulo_dois_pontos = sum(1 for _, c in linhas_validas if len(c) >= 1 and c[0].strip().endswith(":"))

    # Detecta se a aba é ficha técnica / pares chave-valor:
    eh_chave_valor = (qtd_linhas > 1 and (linhas_com_rotulo_dois_pontos / qtd_linhas) >= 0.40)

    unidades: List[Dict[str, Any]] = []
    linhas_tabulares: List[TabularRow] = []
    pagina_atual = pagina_inicio

    if eh_chave_valor:
        pares_chave_valor = []
        schema_ft: List[str] = []
        dados_ft: Dict[str, Any] = {}
        for r_idx, celulas in linhas_validas:
            celulas_preenchidas = [c for c in celulas if c]
            if len(celulas_preenchidas) == 1:
                pares_chave_valor.append(f"\n[{celulas_preenchidas[0]}]")
                linhas_tabulares.append(TabularRow(linha=r_idx, dados={"secao": celulas_preenchidas[0]}))
            elif len(celulas_preenchidas) == 2:
                k = celulas_preenchidas[0].rstrip(":")
                v = celulas_preenchidas[1]
                pares_chave_valor.append(f"{k}: {v}")
                dados_ft[k] = v
                if k not in schema_ft:
                    schema_ft.append(k)
                linhas_tabulares.append(TabularRow(linha=r_idx, dados={k: v}))
            elif len(celulas_preenchidas) > 2:
                k = celulas_preenchidas[0].rstrip(":")
                v = celulas_preenchidas[1]
                extras = ", ".join(celulas_preenchidas[2:])
                pares_chave_valor.append(f"{k}: {v} ({extras})")
                dados_ft[k] = f"{v} ({extras})"
                if k not in schema_ft:
                    schema_ft.append(k)
                linhas_tabulares.append(TabularRow(linha=r_idx, dados={k: v, "extras": extras}))

        if pares_chave_valor:
            bloco_txt = f"Aba: {sheet_name}\n" + "\n".join(pares_chave_valor).strip()
            unidades.append({
                "pagina": pagina_atual,
                "texto": bloco_txt,
                "metadados": {
                    "tipo_arquivo": extensao,
                    "aba": sheet_name,
                    "rotulo_unidade": f"Aba {sheet_name} (Ficha Técnica)"
                }
            })
            pagina_atual += 1

        sheet_obj = TabularSheet(
            nome_aba=sheet_name,
            schema=schema_ft,
            linhas=linhas_tabulares,
            eh_ficha_tecnica=True
        )
        return unidades, pagina_atual, sheet_obj

    # Caso padrão tabular: Localiza a linha de cabeçalho
    header_idx = 0
    for i, (r_idx, cels) in enumerate(linhas_validas):
        if len(cels) >= 2 and all(len(x) > 0 for x in cels[:2]):
            header_idx = i
            break

    cabecalho = linhas_validas[header_idx][1]
    dados = linhas_validas[header_idx + 1:]

    if not dados:
        bloco = f"Aba: {sheet_name}\n" + " | ".join(cabecalho)
        unidades.append({
            "pagina": pagina_atual,
            "texto": bloco,
            "metadados": {
                "tipo_arquivo": extensao,
                "aba": sheet_name,
                "linha": linhas_validas[0][0],
                "rotulo_unidade": f"Aba {sheet_name} - Linha {linhas_validas[0][0]}"
            }
        })
        pagina_atual += 1
        sheet_obj = TabularSheet(nome_aba=sheet_name, schema=cabecalho, linhas=[], eh_ficha_tecnica=False)
        return unidades, pagina_atual, sheet_obj

    for r_idx, celulas in dados:
        pares_linha = []
        dados_linha_dict: Dict[str, Any] = {}
        for i in range(len(cabecalho)):
            col_nome = cabecalho[i] if cabecalho[i] else f"Coluna_{i + 1}"
            val = celulas[i] if i < len(celulas) else ""
            pares_linha.append((col_nome, val))
            dados_linha_dict[col_nome] = val

        if len(celulas) > len(cabecalho):
            for j in range(len(cabecalho), len(celulas)):
                col_extra = f"Coluna_{j + 1}"
                pares_linha.append((col_extra, celulas[j]))
                dados_linha_dict[col_extra] = celulas[j]

        if any(str(v).strip() for _, v in pares_linha):
            registro_enr = enriquecer_registro_estruturado(
                pares_linha,
                colunas_esperadas=cabecalho,
                contexto_origem={"tipo_arquivo": extensao, "aba": sheet_name, "linha": r_idx}
            )
            bloco = f"Aba: {sheet_name}\n" + registro_enr.texto_formatado
            meta_unidade = {
                "tipo_arquivo": extensao,
                "aba": sheet_name,
                "linha": r_idx,
                "rotulo_unidade": f"Aba {sheet_name} - Linha {r_idx}"
            }
            meta_unidade.update(registro_enr.metadados_derivados)
            unidades.append({
                "pagina": pagina_atual,
                "texto": bloco,
                "metadados": meta_unidade
            })
            linhas_tabulares.append(TabularRow(
                linha=r_idx,
                dados=dados_linha_dict,
                metadados_derivados=registro_enr.metadados_derivados,
                propriedades_detectadas=registro_enr.propriedades_detectadas,
                marcadores_estruturados=registro_enr.marcadores_estruturados
            ))
            pagina_atual += 1

    sheet_obj = TabularSheet(
        nome_aba=sheet_name,
        schema=cabecalho,
        linhas=linhas_tabulares,
        eh_ficha_tecnica=False
    )
    return unidades, pagina_atual, sheet_obj


def extrair_documento_excel(
    stream: io.BytesIO,
    nome_arquivo: str,
    extensao: str
) -> Tuple[List[Dict[str, Any]], Dict[str, TabularSheet]]:
    """Extrai dados de planilhas Excel (.xlsx ou .xls) por aba e linha estruturada."""
    logger = obter_logger()
    stream.seek(0)

    max_sheets = RAG_CONFIG.get("max_excel_sheets", 30)
    max_rows_per_sheet = RAG_CONFIG.get("max_excel_rows_per_sheet", 5000)

    unidades: List[Dict[str, Any]] = []
    sheets_dict: Dict[str, TabularSheet] = {}
    pagina_counter = 1

    if extensao == "xlsx":
        import openpyxl
        try:
            wb = openpyxl.load_workbook(stream, data_only=True, read_only=True)
        except Exception as e:
            logger.error(f"Erro ao abrir arquivo XLSX '{nome_arquivo}': {e}", exc_info=True)
            raise ValueError(f"Não foi possível abrir o arquivo Excel '{nome_arquivo}': formato inválido ou corrompido.")

        sheet_names = wb.sheetnames[:max_sheets]
        for sheet_name in sheet_names:
            ws = wb[sheet_name]
            rows_com_idx = []
            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if row_idx > max_rows_per_sheet:
                    break
                rows_com_idx.append((row_idx, list(row)))

            unidades_aba, pagina_counter, sheet_obj = _processar_linhas_planilha_estruturada(
                rows_com_idx, sheet_name, extensao, pagina_counter
            )
            unidades.extend(unidades_aba)
            sheets_dict[sheet_name] = sheet_obj

        wb.close()

    elif extensao == "xls":
        import xlrd
        try:
            stream.seek(0)
            wb = xlrd.open_workbook(file_contents=stream.read())
        except Exception as e:
            logger.error(f"Erro ao abrir arquivo XLS legado '{nome_arquivo}': {e}", exc_info=True)
            raise ValueError(f"Não foi possível abrir o arquivo Excel XLS legado '{nome_arquivo}': formato inválido ou corrompido.")

        for s_idx in range(min(wb.nsheets, max_sheets)):
            sheet = wb.sheet_by_index(s_idx)
            sheet_name = sheet.name

            if sheet.nrows == 0:
                continue

            rows_com_idx = []
            for row_idx in range(min(sheet.nrows, max_rows_per_sheet)):
                rows_com_idx.append((row_idx + 1, sheet.row_values(row_idx)))

            unidades_aba, pagina_counter, sheet_obj = _processar_linhas_planilha_estruturada(
                rows_com_idx, sheet_name, extensao, pagina_counter
            )
            unidades.extend(unidades_aba)
            sheets_dict[sheet_name] = sheet_obj

    return unidades, sheets_dict


# ─────────────────────────────────────────────────────────────────────────────
# EXTRATOR: POWERPOINT (.pptx)
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_pptx(stream: io.BytesIO, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Extrai conteúdo de apresentações PowerPoint preservando slides, títulos, formas e tabelas."""
    import pptx
    logger = obter_logger()
    stream.seek(0)

    try:
        prs = pptx.Presentation(stream)
    except Exception as e:
        logger.error(f"Erro ao abrir apresentação PPTX '{nome_arquivo}': {e}", exc_info=True)
        raise ValueError(f"Não foi possível abrir o arquivo PowerPoint '{nome_arquivo}': formato inválido ou corrompido.")

    max_slides = RAG_CONFIG.get("max_pptx_slides", 200)
    unidades: List[Dict[str, Any]] = []

    for slide_idx, slide in enumerate(prs.slides, start=1):
        if slide_idx > max_slides:
            break
        linhas_slide: List[str] = []

        titulo_slide = ""
        if slide.shapes.title and slide.shapes.title.has_text_frame:
            titulo_slide = slide.shapes.title.text_frame.text.strip()
            if titulo_slide:
                linhas_slide.append(f"Título: {titulo_slide}")

        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue

            if shape.has_text_frame:
                for p in shape.text_frame.paragraphs:
                    txt_p = p.text.strip()
                    if txt_p and txt_p != titulo_slide:
                        linhas_slide.append(txt_p)

            elif shape.has_table:
                tbl = shape.table
                linhas_tbl = []
                for row in tbl.rows:
                    celulas = [c.text.strip().replace("\n", " ") for c in row.cells]
                    if any(celulas):
                        linhas_tbl.append(" | ".join(celulas))
                if linhas_tbl:
                    linhas_slide.append("[TABELA NO SLIDE]")
                    linhas_slide.extend(linhas_tbl)

        texto_slide = "\n".join(linhas_slide).strip()
        if texto_slide:
            unidades.append({
                "pagina": slide_idx,
                "texto": texto_slide,
                "metadados": {
                    "tipo_arquivo": "pptx",
                    "slide": slide_idx,
                    "rotulo_unidade": f"Slide {slide_idx}",
                    "secao_origem": titulo_slide or f"Slide {slide_idx}"
                }
            })

    return unidades


# ─────────────────────────────────────────────────────────────────────────────
# DESPACHANTE CENTRAL: extrair_documento
# ─────────────────────────────────────────────────────────────────────────────
def extrair_documento_com_dados_tabulares(
    arquivo: Union[io.BytesIO, bytes, str, Any],
    nome_arquivo: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, TabularSheet]]]:
    """Extrai unidades de texto para o RAG e, quando aplicável (CSV/XLSX/XLS), a estrutura tabular completa."""
    logger = obter_logger()
    stream, nome, extensao = _obter_info_arquivo(arquivo, nome_arquivo)

    if not extensao:
        raise ValueError(f"Não foi possível identificar a extensão do arquivo '{nome}'. Formatos aceitos: {', '.join(EXTENSOES_SUPORTADAS)}.")

    if extensao not in EXTENSOES_SUPORTADAS:
        raise ValueError(
            f"Extensão de arquivo '.{extensao}' não é suportada. "
            f"Formatos aceitos atualmente: {', '.join(EXTENSOES_SUPORTADAS)}."
        )

    try:
        sheets_tabulares: Optional[Dict[str, TabularSheet]] = None
        if extensao == "pdf":
            unidades = extrair_documento_pdf(stream, nome)
        elif extensao == "docx":
            unidades = extrair_documento_docx(stream, nome)
        elif extensao == "txt":
            unidades = extrair_documento_txt(stream, nome)
        elif extensao == "md":
            unidades = extrair_documento_md(stream, nome)
        elif extensao == "csv":
            unidades, sheets_tabulares = extrair_documento_csv(stream, nome)
        elif extensao in ("xlsx", "xls"):
            unidades, sheets_tabulares = extrair_documento_excel(stream, nome, extensao)
        elif extensao == "pptx":
            unidades = extrair_documento_pptx(stream, nome)
        else:
            raise ValueError(f"Extrator para extensão '.{extensao}' não está configurado.")

        unidades_validas = [u for u in unidades if u.get("texto", "").strip()]
        if not unidades_validas:
            logger.warning(f"Arquivo '{nome}' não gerou nenhuma unidade com texto legível.")
            return [], sheets_tabulares

        logger.info(f"Extração concluída para '{nome}' ({extensao}): {len(unidades_validas)} unidades geradas.")
        return unidades_validas, sheets_tabulares

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Falha ao extrair conteúdo do arquivo '{nome}' ({extensao}): {e}", exc_info=True)
        raise ValueError(f"Falha ao processar o arquivo '{nome}': {e}")


def extrair_documento(
    arquivo: Union[io.BytesIO, bytes, str, Any],
    nome_arquivo: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Função pública central de ingestão de documentos.

    Detecta automaticamente o formato pela extensão do arquivo, despacha para o
    extrator apropriado e retorna a estrutura normalizada de unidades para o ChromaDB.
    """
    unidades, _ = extrair_documento_com_dados_tabulares(arquivo, nome_arquivo)
    return unidades
