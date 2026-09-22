# -*- coding: utf-8 -*-
"""Repositório em disco da ficha técnica (Fase 11, Task 5).

Mesmo padrão de persistência de `conversas_manager.py`/`usage_tracker.py` -- arquivo JSON em
`tenant_data/`, sem banco de dados, com `filelock` no ciclo leitura-modificação-escrita. A
estrutura em disco:

    tenant_data/fichas/{tenant}_index.json          # histórico leve: id, ref, nome, status, datas
    tenant_data/fichas/{tenant}_{ficha_id}/
        ficha.json                                  # documento completo (fichas_modelo.ficha_vazia())
        desenho_v1.png, desenho_v2.png, ...          # versões do desenho técnico (Bloco C)
        ficha.docx, ficha.pdf                        # documentos gerados (Bloco B)

O índice existe separado do documento completo para que listar todas as fichas de um tenant não
precise abrir um arquivo por ficha -- mesmo raciocínio de custo/benefício por trás de qualquer
índice: uma tabela pequena e barata de ler no caminho comum (a tela de lista), redundante com o
dado completo que já está no documento principal.

`ficha_id` é sempre validado contra um formato UUID antes de virar caminho de arquivo -- ele nunca
é gerado a partir de entrada do usuário (só `uuid.uuid4()`, em `criar_ficha`/`duplicar_ficha`), mas
tratá-lo como não confiável na hora de montar caminhos custa uma função e evita que um ficha_id
malformado vindo de uma rota (Task 6) vire um path traversal.
"""

import copy
import json
import os
import re
import shutil
import uuid
from datetime import datetime
from typing import Any, List, Optional

from filelock import FileLock, Timeout

import fichas_modelo as fm
from logger_config import obter_logger

DIRETORIO_FICHAS = os.path.join("tenant_data", "fichas")

# Mesmo timeout curto dos outros módulos de tenant_data/ -- nenhuma operação aqui deveria
# realisticamente disputar o lock por mais que isso; se disputar, é melhor falhar rápido e visível
# do que travar a requisição indefinidamente.
TIMEOUT_LOCK_SEGUNDOS = 5

_REGEX_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class ConflitoDeVersaoError(Exception):
    """Levantado por `salvar_ficha` quando `atualizado_em_esperado` não bate com o valor salvo em
    disco -- indica que outra sessão (outra aba, outro usuário) modificou a ficha entre a leitura
    e a tentativa de escrita atual. A rota (Task 6) traduz isso para HTTP 412."""


def validar_id_uuid(valor: Any, rotulo: str = "id") -> str:
    """Confirma que `valor` tem formato UUID antes de virar caminho de arquivo -- pública (Fase
    14, Bloco G, Task 12) para `croquis_repo.py` reaproveitar em vez de duplicar a mesma regex e o
    mesmo risco de divergir dela com o tempo. `rotulo` só personaliza a mensagem de erro (ex:
    "ficha_id", "croqui_id")."""
    if not isinstance(valor, str) or not _REGEX_UUID.match(valor):
        raise ValueError(f"{rotulo} inválido: {valor!r}")
    return valor


def _validar_ficha_id(ficha_id: Any) -> str:
    return validar_id_uuid(ficha_id, rotulo="ficha_id")


def _dir_ficha(tenant_id: str, ficha_id: str) -> str:
    return os.path.join(DIRETORIO_FICHAS, f"{tenant_id}_{ficha_id}")


def _caminho_ficha_json(tenant_id: str, ficha_id: str) -> str:
    return os.path.join(_dir_ficha(tenant_id, ficha_id), "ficha.json")


def _caminho_lock_ficha(tenant_id: str, ficha_id: str) -> str:
    return os.path.join(_dir_ficha(tenant_id, ficha_id), "ficha.json.lock")


def caminho_arquivo_da_ficha(tenant_id: str, ficha_id: str, nome_arquivo: str) -> str:
    """Caminho de um artefato binário dentro da pasta da ficha (ficha.docx, ficha.pdf,
    desenho_v1.png...). Único ponto que monta esses caminhos, para render (Task 10), download
    (Task 12), PDF (Task 13) e desenhos (Bloco C) não divergirem sobre onde as coisas ficam."""
    _validar_ficha_id(ficha_id)
    if os.sep in nome_arquivo or "/" in nome_arquivo or ".." in nome_arquivo:
        raise ValueError(f"nome de arquivo inválido: {nome_arquivo!r}")
    return os.path.join(_dir_ficha(tenant_id, ficha_id), nome_arquivo)


def _caminho_indice(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_FICHAS, f"{tenant_id}_index.json")


def _caminho_lock_indice(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_FICHAS, f"{tenant_id}_index.json.lock")


def escrever_json_atomico(caminho: str, dados: Any) -> None:
    """Escreve num arquivo temporário e troca com `os.replace` -- um leitor concorrente nunca vê
    um arquivo pela metade (o replace é atômico no nível do sistema de arquivos), diferente de
    escrever direto no destino."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    caminho_tmp = caminho + ".tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(caminho_tmp, caminho)


def _resumo_indice(ficha: dict) -> dict:
    dados_ficha = (ficha.get("dados") or {}).get("ficha", {})
    aprovacao = ficha.get("aprovacao") or {}
    return {
        "id": ficha["id"],
        "ref": fm.valor_de(dados_ficha.get("ref")) or "",
        "nome": fm.valor_de(dados_ficha.get("nome")) or "",
        "status": ficha.get("status", fm.STATUS_RASCUNHO),
        "criado_em": ficha.get("criado_em", ""),
        "atualizado_em": ficha.get("atualizado_em", ""),
        # No índice (Fase 14, Bloco AP) para a lista de fichas mostrar quem aprovou sem precisar
        # abrir o JSON completo de cada uma -- mesma razão de ref/nome estarem aqui.
        "aprovada_por": aprovacao.get("aprovada_por", ""),
    }


def _indice_carregar(tenant_id: str) -> List[dict]:
    caminho = _caminho_indice(tenant_id)
    if not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, list) else []
    except Exception as e:
        obter_logger(tenant_id).error(f"Erro ao carregar índice de fichas: {e}", exc_info=True)
        return []


def _indice_upsert(tenant_id: str, entrada: dict) -> None:
    """Substitui (ou insere) a entrada de uma ficha no índice -- leitura-modificação-escrita
    completa dentro do lock, para duas fichas sendo salvas ao mesmo tempo não perderem a entrada
    uma da outra (o mesmo bug de escrita que motivou o lock em conversas_manager.salvar_conversas)."""
    os.makedirs(DIRETORIO_FICHAS, exist_ok=True)
    try:
        with FileLock(_caminho_lock_indice(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            indice = _indice_carregar(tenant_id)
            indice = [e for e in indice if e.get("id") != entrada["id"]]
            indice.append(entrada)
            escrever_json_atomico(_caminho_indice(tenant_id), indice)
    except Timeout:
        obter_logger(tenant_id).error(f"Timeout ao atualizar índice de fichas ({entrada.get('id')}).")


def _indice_remover(tenant_id: str, ficha_id: str) -> bool:
    try:
        with FileLock(_caminho_lock_indice(tenant_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
            indice = _indice_carregar(tenant_id)
            novo_indice = [e for e in indice if e.get("id") != ficha_id]
            removeu = len(novo_indice) != len(indice)
            if removeu:
                escrever_json_atomico(_caminho_indice(tenant_id), novo_indice)
            return removeu
    except Timeout:
        obter_logger(tenant_id).error(f"Timeout ao remover ficha {ficha_id} do índice.")
        return False


def _persistir(tenant_id: str, ficha: dict) -> None:
    """Grava ficha.json (com lock próprio da ficha) e atualiza o índice em seguida."""
    ficha_id = _validar_ficha_id(ficha["id"])
    with FileLock(_caminho_lock_ficha(tenant_id, ficha_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
        escrever_json_atomico(_caminho_ficha_json(tenant_id, ficha_id), ficha)
    _indice_upsert(tenant_id, _resumo_indice(ficha))


def criar_ficha(tenant_id: str, texto_origem: str = "", precificacao_padrao: Optional[dict] = None) -> dict:
    """Cria uma ficha nova (fichas_modelo.ficha_vazia() com id/timestamps preenchidos), persiste
    e a devolve. `texto_origem` é opcional -- o texto livre que originou a ficha, quando a
    extração (Task 3) já rodou; uma ficha pode nascer em branco também (revisão manual direta).

    `precificacao_padrao` (Fase 14, Bloco P, Task 19) semeia `ficha["precificacao"]` com os
    parâmetros configurados no tenant (`TENANT_CONFIG[...]["precificacao_padrao"]`) -- este módulo
    não conhece TENANT_CONFIG, então quem chama (a rota HTTP) decide o valor e só repassa aqui.
    Sem ele, a ficha nasce com os zeros de fichas_modelo.ficha_vazia()."""
    ficha = fm.ficha_vazia()
    ficha["id"] = str(uuid.uuid4())
    agora = datetime.now().isoformat()
    ficha["criado_em"] = agora
    ficha["atualizado_em"] = agora
    ficha["texto_origem"] = texto_origem or ""
    if precificacao_padrao:
        ficha["precificacao"] = {**ficha["precificacao"], **precificacao_padrao}
    _persistir(tenant_id, ficha)
    return ficha


def carregar_ficha(tenant_id: str, ficha_id: str) -> Optional[dict]:
    """Lê o documento completo de uma ficha. None se não existir ou estiver corrompido -- nunca
    lança por dado ausente, só por ficha_id malformado (isso sim é erro de programação do
    chamador, não estado normal de dado faltando)."""
    _validar_ficha_id(ficha_id)
    caminho = _caminho_ficha_json(tenant_id, ficha_id)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else None
    except Exception as e:
        obter_logger(tenant_id).error(f"Erro ao carregar ficha {ficha_id}: {e}", exc_info=True)
        return None


def listar_fichas(tenant_id: str) -> List[dict]:
    """Histórico leve (id/ref/nome/status/datas), mais recente primeiro -- mesma ordenação de
    ConversasHistorico.tsx para a lista de conversas."""
    indice = _indice_carregar(tenant_id)
    return sorted(indice, key=lambda e: e.get("atualizado_em", ""), reverse=True)


def salvar_ficha(tenant_id: str, ficha: dict, atualizado_em_esperado: Optional[str] = None) -> dict:
    """Persiste uma ficha existente, atualizando `atualizado_em` para agora.

    Se `atualizado_em_esperado` for informado (a rota HTTP, Task 6, envia o timestamp que o
    cliente tinha ao abrir a ficha), compara contra o valor salvo em disco *antes* de
    sobrescrever -- diferença significa que outra sessão editou a ficha nesse meio-tempo, e a
    escrita é recusada com ConflitoDeVersaoError em vez de apagar silenciosamente a mudança da
    outra sessão (last-write-wins).
    """
    ficha_id = _validar_ficha_id(ficha.get("id"))

    with FileLock(_caminho_lock_ficha(tenant_id, ficha_id), timeout=TIMEOUT_LOCK_SEGUNDOS):
        if atualizado_em_esperado is not None:
            atual = carregar_ficha(tenant_id, ficha_id)
            if atual is not None and atual.get("atualizado_em") != atualizado_em_esperado:
                raise ConflitoDeVersaoError(
                    f"A ficha {ficha_id} foi modificada em outra sessão desde a última leitura."
                )
        ficha["atualizado_em"] = datetime.now().isoformat()
        escrever_json_atomico(_caminho_ficha_json(tenant_id, ficha_id), ficha)

    _indice_upsert(tenant_id, _resumo_indice(ficha))
    return ficha


def duplicar_ficha(tenant_id: str, ficha_id: str) -> Optional[dict]:
    """Cria uma cópia dos dados de uma ficha existente com id/timestamps novos e status voltando
    a RASCUNHO. Desenho e documentos gerados (docx/pdf) NÃO são copiados -- são artefatos
    derivados desta ficha específica (a imagem aprovada, o Word/PDF já exportado), não fazem
    sentido herdados por uma cópia que ainda não passou pelo próprio fluxo de geração."""
    original = carregar_ficha(tenant_id, ficha_id)
    if original is None:
        return None

    copia = fm.ficha_vazia()
    copia["id"] = str(uuid.uuid4())
    agora = datetime.now().isoformat()
    copia["criado_em"] = agora
    copia["atualizado_em"] = agora
    copia["texto_origem"] = original.get("texto_origem", "")
    copia["dados"] = copy.deepcopy(original.get("dados") or fm.dados_vazios())
    # precificacao (Fase 14, Bloco P, Task 19) segue o mesmo tratamento de "dados", não o de
    # "desenho": são parâmetros que a pessoa configurou para esta peça, não um artefato derivado
    # de uma chamada de API específica desta ficha -- faz sentido herdar numa cópia usada como base.
    copia["precificacao"] = copy.deepcopy(original.get("precificacao") or copia["precificacao"])
    _persistir(tenant_id, copia)
    return copia


def deletar_ficha(tenant_id: str, ficha_id: str) -> bool:
    """Remove o diretório inteiro da ficha (documento + desenhos + documentos gerados) e sua
    entrada no índice. True se algo foi de fato removido."""
    _validar_ficha_id(ficha_id)
    diretorio = _dir_ficha(tenant_id, ficha_id)

    diretorio_existia = os.path.isdir(diretorio)
    if diretorio_existia:
        try:
            shutil.rmtree(diretorio)
        except Exception as e:
            obter_logger(tenant_id).error(f"Erro ao remover diretório da ficha {ficha_id}: {e}", exc_info=True)
            return False

    removeu_do_indice = _indice_remover(tenant_id, ficha_id)
    return diretorio_existia or removeu_do_indice
