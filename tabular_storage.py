# -*- coding: utf-8 -*-
"""Módulo de Armazenamento e Gestão de Dados Estruturados Tabulares por Tenant.

Permite persistir, carregar, consultar e remover a representação estruturada completa
de arquivos tabulares (CSV, XLSX, XLS), garantindo isolamento estrito entre tenants,
rastreabilidade de abas/linhas e sincronização com o ciclo de vida do RAG.
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from logger_config import obter_logger


@dataclass
class TabularRow:
    """Representa uma linha individual estruturada em uma aba ou tabela."""
    linha: int
    dados: Dict[str, Any]
    metadados_derivados: Dict[str, Any] = field(default_factory=dict)
    propriedades_detectadas: List[str] = field(default_factory=list)
    marcadores_estruturados: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "linha": self.linha,
            "dados": self.dados,
            "metadados_derivados": self.metadados_derivados,
            "propriedades_detectadas": self.propriedades_detectadas,
            "marcadores_estruturados": self.marcadores_estruturados
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TabularRow":
        return cls(
            linha=int(d.get("linha", 1)),
            dados=dict(d.get("dados", {})),
            metadados_derivados=dict(d.get("metadados_derivados", {})),
            propriedades_detectadas=list(d.get("propriedades_detectadas", [])),
            marcadores_estruturados=list(d.get("marcadores_estruturados", []))
        )


@dataclass
class TabularSheet:
    """Representa uma aba ou tabela de dados com schema próprio."""
    nome_aba: str
    schema: List[str]
    linhas: List[TabularRow] = field(default_factory=list)
    eh_ficha_tecnica: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nome_aba": self.nome_aba,
            "schema": self.schema,
            "linhas": [r.to_dict() for r in self.linhas],
            "eh_ficha_tecnica": self.eh_ficha_tecnica
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TabularSheet":
        return cls(
            nome_aba=str(d.get("nome_aba", "Sheet1")),
            schema=list(d.get("schema", [])),
            linhas=[TabularRow.from_dict(r) for r in d.get("linhas", [])],
            eh_ficha_tecnica=bool(d.get("eh_ficha_tecnica", False))
        )


@dataclass
class TabularDocument:
    """Representa o documento tabular completo persistido para um tenant."""
    nome_arquivo: str
    tipo_arquivo: str
    tenant_id: str
    criado_em: str
    sheets: Dict[str, TabularSheet] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nome_arquivo": self.nome_arquivo,
            "tipo_arquivo": self.tipo_arquivo,
            "tenant_id": self.tenant_id,
            "criado_em": self.criado_em,
            "sheets": {nome: sheet.to_dict() for nome, sheet in self.sheets.items()}
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TabularDocument":
        sheets_dict = {}
        for nome, s_data in d.get("sheets", {}).items():
            sheets_dict[nome] = TabularSheet.from_dict(s_data)
        return cls(
            nome_arquivo=str(d.get("nome_arquivo", "")),
            tipo_arquivo=str(d.get("tipo_arquivo", "csv")),
            tenant_id=str(d.get("tenant_id", "default")),
            criado_em=str(d.get("criado_em", datetime.now().isoformat())),
            sheets=sheets_dict
        )

    def obter_todas_colunas(self) -> Set[str]:
        """Retorna o conjunto de todos os nomes de colunas presentes em todas as abas."""
        colunas = set()
        for sheet in self.sheets.values():
            for c in sheet.schema:
                colunas.add(c)
        return colunas


def _obter_diretorio_tabular(tenant_id: str) -> str:
    """Retorna o caminho físico do diretório de dados tabulares isolado por tenant."""
    tenant_seguro = "".join(c for c in tenant_id if c.isalnum() or c in ("_", "-")).strip() or "default"
    caminho = os.path.join("tenant_data", "tabular", tenant_seguro)
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _nome_arquivo_para_json(nome_arquivo: str) -> str:
    """Gera um nome de arquivo JSON seguro para armazenamento local."""
    nome_limpo = re.sub(r'[^a-zA-Z0-9._-]', '_', nome_arquivo)
    return f"{nome_limpo}.json"


def salvar_documento_tabular(
    tenant_id: str,
    nome_arquivo: str,
    tipo_arquivo: str,
    sheets: Dict[str, TabularSheet]
) -> TabularDocument:
    """Persiste ou substitui a representação tabular completa de um documento estruturado."""
    logger = obter_logger(tenant_id)
    doc_tabular = TabularDocument(
        nome_arquivo=nome_arquivo,
        tipo_arquivo=tipo_arquivo,
        tenant_id=tenant_id,
        criado_em=datetime.now().isoformat(),
        sheets=sheets
    )

    diretorio = _obter_diretorio_tabular(tenant_id)
    nome_json = _nome_arquivo_para_json(nome_arquivo)
    caminho_completo = os.path.join(diretorio, nome_json)

    try:
        with open(caminho_completo, "w", encoding="utf-8") as f:
            json.dump(doc_tabular.to_dict(), f, ensure_ascii=False, indent=2)
        total_linhas = sum(len(s.linhas) for s in sheets.values())
        logger.info(f"Documento tabular '{nome_arquivo}' salvo com sucesso para tenant '{tenant_id}': {len(sheets)} aba(s), {total_linhas} linha(s).")
        return doc_tabular
    except Exception as e:
        logger.error(f"Erro ao salvar documento tabular '{nome_arquivo}' no tenant '{tenant_id}': {e}", exc_info=True)
        raise


def carregar_documento_tabular(tenant_id: str, nome_arquivo: str) -> Optional[TabularDocument]:
    """Carrega o documento tabular correspondente de um tenant específico."""
    diretorio = _obter_diretorio_tabular(tenant_id)
    nome_json = _nome_arquivo_para_json(nome_arquivo)
    caminho_completo = os.path.join(diretorio, nome_json)

    if not os.path.exists(caminho_completo):
        return None

    try:
        with open(caminho_completo, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return TabularDocument.from_dict(dados)
    except Exception as e:
        logger = obter_logger(tenant_id)
        logger.error(f"Erro ao carregar documento tabular '{nome_arquivo}' do tenant '{tenant_id}': {e}", exc_info=True)
        return None


def carregar_documentos_tabulares(tenant_id: str) -> List[TabularDocument]:
    """Carrega todos os documentos tabulares pertencentes ao tenant."""
    diretorio = _obter_diretorio_tabular(tenant_id)
    if not os.path.exists(diretorio):
        return []

    documentos: List[TabularDocument] = []
    for arq in os.listdir(diretorio):
        if arq.endswith(".json"):
            caminho_completo = os.path.join(diretorio, arq)
            try:
                with open(caminho_completo, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                doc = TabularDocument.from_dict(dados)
                if doc.tenant_id == tenant_id:
                    documentos.append(doc)
            except Exception:
                continue

    return sorted(documentos, key=lambda d: d.nome_arquivo)


def remover_documento_tabular(tenant_id: str, nome_arquivo: str) -> bool:
    """Remove a persistência tabular de um documento quando ele for desindexado."""
    diretorio = _obter_diretorio_tabular(tenant_id)
    nome_json = _nome_arquivo_para_json(nome_arquivo)
    caminho_completo = os.path.join(diretorio, nome_json)

    if os.path.exists(caminho_completo):
        try:
            os.remove(caminho_completo)
            logger = obter_logger(tenant_id)
            logger.info(f"Documento tabular '{nome_arquivo}' removido com sucesso do tenant '{tenant_id}'.")
            return True
        except Exception as e:
            logger = obter_logger(tenant_id)
            logger.error(f"Erro ao remover documento tabular '{nome_arquivo}' do tenant '{tenant_id}': {e}", exc_info=True)
            return False
    return False


def remover_tenant_tabular(tenant_id: str) -> bool:
    """Remove completamente todos os dados tabulares do tenant (purga)."""
    import shutil
    diretorio = _obter_diretorio_tabular(tenant_id)
    if os.path.exists(diretorio):
        try:
            shutil.rmtree(diretorio)
            return True
        except Exception:
            return False
    return True
