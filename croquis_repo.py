# -*- coding: utf-8 -*-
"""Repositório em disco da galeria de croquis (Fase 14, Bloco G, Task 12).

Antes desta task, um croqui gerado no chat só existia como data URI base64 dentro do histórico da
conversa -- perdido se a conversa fosse excluída, pesado no JSON persistido, e impossível de
reaproveitar em outro lugar (ex: como desenho técnico de uma ficha, Task 17) sem baixar e reenviar
manualmente a imagem. Este módulo persiste o PNG em disco, um arquivo por croqui, com um índice
leve para listar a galeria sem precisar abrir cada imagem.

Mesmo padrão de `fichas_repo.py` (JSON + `filelock` no ciclo leitura-modificação-escrita), mas mais
simples: cada croqui é um único arquivo binário, não uma pasta com vários artefatos. Reaproveita de
`fichas_repo.py` a escrita atômica (`escrever_json_atomico`) e a validação de UUID contra path
traversal (`validar_id_uuid`) -- duplicar essas duas funções aqui divergiria com o tempo do mesmo
código de segurança que a ficha técnica já testa.

Estrutura em disco:

    tenant_data/croquis/{tenant}_index.json           # id, estilo, resumo, criado_em
    tenant_data/croquis/{tenant}_{croqui_id}.png       # o PNG em si
"""

import json
import os
import uuid
from datetime import datetime
from typing import List, Optional

from filelock import FileLock, Timeout

import fichas_repo
from logger_config import obter_logger

DIRETORIO_CROQUIS = os.path.join("tenant_data", "croquis")

# Mesmo timeout curto dos outros módulos de tenant_data/ (ver fichas_repo.py/usage_tracker.py).
TIMEOUT_LOCK_SEGUNDOS = 5


def _caminho_png(tenant_id: str, croqui_id: str) -> str:
    return os.path.join(DIRETORIO_CROQUIS, f"{tenant_id}_{croqui_id}.png")


def _caminho_indice(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_CROQUIS, f"{tenant_id}_index.json")


def _caminho_lock_indice(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_CROQUIS, f"{tenant_id}_index.json.lock")


def _indice_carregar(tenant_id: str) -> List[dict]:
    caminho = _caminho_indice(tenant_id)
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, list) else []
    except Exception as e:
        obter_logger(tenant_id).error(f"Erro ao carregar índice de croquis: {e}", exc_info=True)
        return []


def _indice_upsert(tenant_id: str, entrada: dict) -> None:
    os.makedirs(DIRETORIO_CROQUIS, exist_ok=True)
    try:
        with FileLock(_caminho_lock_indice(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            indice = _indice_carregar(tenant_id)
            indice = [e for e in indice if e.get("id") != entrada["id"]]
            indice.append(entrada)
            fichas_repo.escrever_json_atomico(_caminho_indice(tenant_id), indice)
    except Timeout:
        obter_logger(tenant_id).error(f"Timeout ao atualizar índice de croquis ({entrada.get('id')}).")


def _indice_remover(tenant_id: str, croqui_id: str) -> bool:
    try:
        with FileLock(_caminho_lock_indice(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            indice = _indice_carregar(tenant_id)
            novo_indice = [e for e in indice if e.get("id") != croqui_id]
            removeu = len(novo_indice) != len(indice)
            if removeu:
                fichas_repo.escrever_json_atomico(_caminho_indice(tenant_id), novo_indice)
            return removeu
    except Timeout:
        obter_logger(tenant_id).error(f"Timeout ao remover croqui {croqui_id} do índice.")
        return False


def salvar_croqui(tenant_id: str, conteudo: bytes, estilo: str = "", resumo: str = "") -> dict:
    """Grava um PNG novo (id gerado aqui, nunca a partir de entrada do usuário) e o insere no
    índice. Devolve a entrada do índice recém-criada -- quem chama decide o que fazer com o `id`
    (ex: anexar à mensagem da conversa, Task 14).

    `estilo` ("Ilustração de Moda" / "Desenho Técnico") e `resumo` (a frase curta em português já
    usada como `resumo_confirmacao`) são só metadados de exibição na galeria -- nunca usados para
    montar caminho de arquivo.
    """
    croqui_id = str(uuid.uuid4())
    caminho = _caminho_png(tenant_id, croqui_id)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(conteudo)

    entrada = {
        "id": croqui_id,
        "estilo": estilo or "",
        "resumo": resumo or "",
        "criado_em": datetime.now().isoformat(),
    }
    _indice_upsert(tenant_id, entrada)
    return entrada


def listar_croquis(tenant_id: str) -> List[dict]:
    """Galeria completa, mais recente primeiro -- mesma ordenação de listar_fichas/ConversasHistorico."""
    indice = _indice_carregar(tenant_id)
    return sorted(indice, key=lambda e: e.get("criado_em", ""), reverse=True)


def caminho_croqui(tenant_id: str, croqui_id: str) -> Optional[str]:
    """Caminho do PNG de um croqui, ou None se não existir em disco. Levanta ValueError para
    croqui_id malformado (erro de programação do chamador, não estado normal de dado faltando --
    mesma convenção de fichas_repo.carregar_ficha)."""
    fichas_repo.validar_id_uuid(croqui_id, rotulo="croqui_id")
    caminho = _caminho_png(tenant_id, croqui_id)
    return caminho if os.path.exists(caminho) else None


def deletar_croqui(tenant_id: str, croqui_id: str) -> bool:
    """Remove o PNG e sua entrada no índice. True se algo foi de fato removido."""
    fichas_repo.validar_id_uuid(croqui_id, rotulo="croqui_id")
    caminho = _caminho_png(tenant_id, croqui_id)

    arquivo_existia = os.path.exists(caminho)
    if arquivo_existia:
        try:
            os.remove(caminho)
        except Exception as e:
            obter_logger(tenant_id).error(f"Erro ao remover PNG do croqui {croqui_id}: {e}", exc_info=True)
            return False

    removeu_do_indice = _indice_remover(tenant_id, croqui_id)
    return arquivo_existia or removeu_do_indice
