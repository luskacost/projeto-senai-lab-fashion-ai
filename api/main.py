# -*- coding: utf-8 -*-
"""Scaffold da API do SenaiLabFashionAssistant (Fase 3, Passo 16).

Casca HTTP em FastAPI para expor a lógica de negócio já existente (rag_manager.py,
conversas_manager.py, analise_dados.py, tenant_config.py) sem depender do Streamlit.
Estrutura de rotas conforme `API_CONTRATO.md`; endpoints marcados como stub ainda não
têm lógica implementada (ver roadmap: cada um é implementado em uma sessão futura).

Rodar localmente: uvicorn api.main:app --reload
"""

import asyncio
import base64
import hmac
import io
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from tenant_config import (
    TENANT_CONFIG,
    PERFIS_USUARIO,
    carregar_config_tenant,
    salvar_config_tenant,
    obter_secret_tenant
)
from rag_manager import (
    buscar_contexto_relevante,
    montar_prompt_final,
    listar_documentos_indexados,
    indexar_documento,
    remover_documento,
    obter_ultimo_rag_debug
)
from document_extractors import extrair_documento
from rag_config import OPENAI_TEXT_MODEL
from conversas_manager import (
    carregar_conversas,
    salvar_conversas,
    criar_nova_conversa,
    renomear_conversa,
    gerar_titulo_conversa,
    formatar_conversa_txt,
    gerar_conversa_pdf
)
from analise_dados import (
    carregar_planilha,
    gerar_resumo_estatistico,
    responder_pergunta_sobre_dados,
    salvar_resumo_estatistico,
    carregar_resumo_estatistico
)
from moderacao import validar_prompt_imagem
from usage_tracker import carregar_uso_do_dia, incrementar_uso, verificar_limite
from logger_config import obter_logger
from geracao_imagem import ESTILO_ILUSTRACAO, ESTILO_TECNICO, SUFIXO_TECNICO, PREFIXO_IMAGEM_GERADA, eh_imagem_gerada
from agente_ferramentas import ContextoExecucao, executar_ferramenta
from agente_openai import chamar_agente, montar_input_historico, retomar_apos_confirmacao
from fichas_modelo import STATUS_DESENHO_GERADO, STATUS_DOCUMENTO_GERADO, valor_de
import fichas_desenho
import fichas_docx
import fichas_logo
import fichas_pdf
from fichas_service import criar_ficha_a_partir_de_texto
from fichas_validacao import validar_ficha
from fichas_repo import (
    ConflitoDeVersaoError,
    criar_ficha,
    carregar_ficha,
    listar_fichas,
    salvar_ficha,
    duplicar_ficha,
    deletar_ficha,
)
from croquis_repo import (
    caminho_croqui,
    deletar_croqui,
    listar_croquis,
    salvar_croqui,
)

try:
    # pyrefly: ignore [missing-import]
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(
    title="SenaiLabFashionAssistant API",
    description="API do assistente de IA com RAG do SENAI LabFashion.",
    version="0.1.0"
)

# CORS configurável por variável de ambiente (Fase 9/Bloco C) -- antes era hardcoded pra
# http://localhost:3000, exigindo mudar código+redeploy pra apontar pra um domínio real de
# produção. CORS_ALLOWED_ORIGINS aceita uma lista separada por vírgula (ex:
# "https://labfashion.senaigoias.com.br,https://outro-dominio.com"); sem a variável definida,
# mantém o comportamento de sempre (só localhost:3000, uso em desenvolvimento local).
_origens_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
ORIGENS_PERMITIDAS = [origem.strip() for origem in _origens_cors.split(",") if origem.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENS_PERMITIDAS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Sem isto, o JavaScript do front não consegue LER o Content-Disposition das respostas de
    # download, mesmo elas chegando corretamente: o navegador só expõe um punhado de headers
    # "seguros" para requisições cross-origin, e Content-Disposition não é um deles. O efeito era
    # silencioso -- o download funcionava, mas com o nome genérico do fallback em vez do nome
    # montado pelo backend (ficha_CM-001_Camisa_Social.docx).
    expose_headers=["Content-Disposition"],
)


# ─────────────────────────────────────────────────────────────────────────────
# SENHA ÚNICA DE ACESSO (Fase 14, Bloco S)
#
# Antes disto, qualquer rota do backend (chat, fichas, upload de planilha, geração de imagem) era
# alcançável por qualquer um que soubesse o endereço -- sem cadastro de usuário final por design
# (decisão da Fase 9), a única barreira real era não saber que o servidor existia. Uma senha única
# para o app inteiro fecha essa porta sem reabrir a decisão de não ter login por pessoa: é "quem
# sabe a senha entra", não "quem sou eu" -- não isola um colega do outro dentro da mesma
# organização, só impede acesso de quem está de fora.
#
# Mesmo padrão do token de admin abaixo (token opaco em memória, bloqueio por tentativas), mas sem
# tenant_id (a senha é do app, não por tenant -- este projeto é single-tenant por decisão de
# produto) e com duração bem mais longa (uso diário contínuo, não uma ação administrativa pontual).
#
# Implementado como dependência global (app.router.dependencies, logo abaixo) em vez de decorar
# rota por rota -- assim nenhuma rota nova esquece de exigi-la. Rotas que servem um arquivo para
# consumo DIRETO do navegador (<img src>, <a href>, <iframe src>) ficam de fora por necessidade
# técnica, nunca por descuido: o navegador não anexa headers customizados nesses casos. São sempre
# rotas de leitura de um recurso cujo identificador (UUID de ficha, id de croqui) já não é
# adivinhável -- a exceção reduz a proteção só ali, não abre a porta inteira de novo.
# ─────────────────────────────────────────────────────────────────────────────
_ACCESS_TOKENS: Dict[str, Dict[str, Any]] = {}  # token -> {"expira_em": timestamp}
_ACCESS_LOGIN_TENTATIVAS: Dict[str, Dict[str, Any]] = {}  # ip -> {"falhas": int, "bloqueado_ate": timestamp}

DURACAO_TOKEN_ACESSO_SEGUNDOS = 30 * 24 * 60 * 60  # 30 dias -- uso diário, não pontual como o admin
MAX_TENTATIVAS_LOGIN_ACESSO = 5
DURACAO_BLOQUEIO_LOGIN_ACESSO_SEGUNDOS = 15 * 60  # 15 minutos

_PADROES_SEM_GATE_DE_ACESSO = [
    re.compile(r"^/health$"),
    re.compile(r"^/acesso/login$"),
    re.compile(r"^/branding/logo$"),  # logo pública, exibida inclusive na própria tela de login
    re.compile(r"^/fichas/[^/]+/preview$"),
    re.compile(r"^/fichas/[^/]+/docx$"),
    re.compile(r"^/fichas/[^/]+/pdf$"),
    re.compile(r"^/fichas/[^/]+/desenho/[^/]+$"),
    re.compile(r"^/conversas/[^/]+/export$"),
    re.compile(r"^/croquis/[^/]+/imagem$"),
]


def _rota_isenta_do_gate_de_acesso(caminho: str) -> bool:
    return any(padrao.match(caminho) for padrao in _PADROES_SEM_GATE_DE_ACESSO)


def _gerar_token_acesso() -> str:
    token = secrets.token_urlsafe(32)
    _ACCESS_TOKENS[token] = {"expira_em": time.time() + DURACAO_TOKEN_ACESSO_SEGUNDOS}
    return token


def verificar_acesso(request: Request, x_access_token: Optional[str] = Header(None, alias="X-Access-Token")) -> None:
    """Dependência global -- aplicada a toda rota via app.router.dependencies. Sem
    SENAI_LABFASHION_ACCESS_PASSWORD configurada, o gate fica desligado (ambiente de
    desenvolvimento local, comportamento de sempre)."""
    senha_de_acesso = os.environ.get("SENAI_LABFASHION_ACCESS_PASSWORD", "")
    if not senha_de_acesso:
        return
    if request.method == "OPTIONS" or _rota_isenta_do_gate_de_acesso(request.url.path):
        return
    dados = _ACCESS_TOKENS.get(x_access_token or "")
    if not dados or dados["expira_em"] < time.time():
        # Header próprio (não confundir com o 401 de token de admin expirado, que é uma rota
        # específica falhando, não o app inteiro) -- o frontend usa isto para saber que precisa
        # voltar à tela de senha de acesso, em vez de tentar interpretar o texto da mensagem.
        raise HTTPException(
            status_code=401,
            detail="Acesso não autorizado. Informe a senha de acesso.",
            headers={"X-Auth-Gate": "acesso"},
        )


class AccessLoginRequest(BaseModel):
    senha: str


@app.post("/acesso/login")
def acesso_login(payload: AccessLoginRequest, request: Request) -> Dict[str, Any]:
    senha_de_acesso = os.environ.get("SENAI_LABFASHION_ACCESS_PASSWORD", "")
    if not senha_de_acesso:
        # Gate desligado: não há o que comparar -- só ocorre em ambiente sem a variável definida.
        return {"autorizado": True, "token": _gerar_token_acesso()}

    ip_cliente = request.client.host if request.client else "desconhecido"
    agora = time.time()
    estado = _ACCESS_LOGIN_TENTATIVAS.get(ip_cliente, {"falhas": 0, "bloqueado_ate": 0.0})
    if estado["bloqueado_ate"] > agora:
        minutos_restantes = int((estado["bloqueado_ate"] - agora) / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas incorretas. Tente novamente em {minutos_restantes} minuto(s)."
        )

    autorizado = hmac.compare_digest(payload.senha, senha_de_acesso)
    if not autorizado:
        estado["falhas"] += 1
        if estado["falhas"] >= MAX_TENTATIVAS_LOGIN_ACESSO:
            estado["bloqueado_ate"] = agora + DURACAO_BLOQUEIO_LOGIN_ACESSO_SEGUNDOS
            estado["falhas"] = 0
        _ACCESS_LOGIN_TENTATIVAS[ip_cliente] = estado
        return {"autorizado": False, "token": None}

    _ACCESS_LOGIN_TENTATIVAS.pop(ip_cliente, None)
    return {"autorizado": True, "token": _gerar_token_acesso()}


app.router.dependencies.append(Depends(verificar_acesso))


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DO TENANT (implementado — lógica trivial, sem dependências pendentes)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/config/tenant")
def obter_config_tenant(tenant_id: str) -> Dict[str, Any]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    return carregar_config_tenant(tenant_id, TENANT_CONFIG[tenant_id])


@app.get("/uso")
def obter_uso(tenant_id: str) -> Dict[str, Any]:
    """Uso visível (Fase 14, Bloco U, Task 9): antes o limite diário só aparecia quando já tinha
    sido excedido (mensagem de erro na hora de enviar). Devolve usado/limite/restante por
    categoria para o frontend mostrar um indicador discreto antes disso virar surpresa."""
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    config = carregar_config_tenant(tenant_id, TENANT_CONFIG[tenant_id])
    uso = carregar_uso_do_dia(tenant_id)

    categorias = {
        "mensagens": config.get("limite_mensagens_dia", 200),
        "imagens": config.get("limite_imagens_dia", 30),
        "buscas_web": config.get("limite_buscas_web_dia", 50),
        "fichas": config.get("limite_fichas_dia", 30),
    }
    return {
        "data": uso.get("data"),
        "categorias": {
            tipo: {
                "usado": uso.get(tipo, 0),
                "limite": limite,
                "restante": max(0, limite - uso.get(tipo, 0)),
            }
            for tipo, limite in categorias.items()
        },
    }


class ConfigTenantUpdate(BaseModel):
    tenant_id: str
    dados_custom: Dict[str, Any]


@app.put("/config/tenant")
def atualizar_config_tenant(payload: ConfigTenantUpdate, x_admin_token: str = Header(..., alias="X-Admin-Token")) -> Dict[str, str]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")
    verificar_token_admin(payload.tenant_id, x_admin_token)
    salvar_config_tenant(payload.tenant_id, payload.dados_custom)
    return {"status": "salvo"}


# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICAÇÃO/ADMIN (Fase 9, Bloco B)
#
# Antes disto, /admin/login comparava a senha com "==" (não é constant-time), sem limite de
# tentativas, e sequer emitia um token -- o front-end só guardava um "1" no sessionStorage após
# o login, e as rotas administrativas de verdade (upload/remoção de documentos, config do tenant)
# não checavam autorização nenhuma no backend. Qualquer um que soubesse o tenant_id (uma string
# pública) podia chamá-las direto via curl, sem nunca passar pelo login.
#
# Sessão de admin implementada como um token opaco em memória (processo único, sem banco de
# dados -- compatível com a arquitetura atual de um único servidor Uvicorn; ver Fase 9/Bloco D
# para os outros pontos de estado em memória/arquivo local). Reinicia ao reiniciar o processo,
# o que é aceitável: exige só um novo login.
# ─────────────────────────────────────────────────────────────────────────────
_ADMIN_TOKENS: Dict[str, Dict[str, Any]] = {}  # token -> {"tenant_id": ..., "expira_em": timestamp}
_ADMIN_LOGIN_TENTATIVAS: Dict[str, Dict[str, Any]] = {}  # ip -> {"falhas": int, "bloqueado_ate": timestamp}

DURACAO_TOKEN_ADMIN_SEGUNDOS = 4 * 60 * 60  # 4 horas
MAX_TENTATIVAS_LOGIN_ADMIN = 5
DURACAO_BLOQUEIO_LOGIN_SEGUNDOS = 15 * 60  # 15 minutos


def _gerar_token_admin(tenant_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _ADMIN_TOKENS[token] = {"tenant_id": tenant_id, "expira_em": time.time() + DURACAO_TOKEN_ADMIN_SEGUNDOS}
    return token


def verificar_token_admin(tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")) -> None:
    """Dependência de rota: exige um token de admin válido (emitido por POST /admin/login) para o
    tenant informado. Levanta 401 se ausente, de outro tenant, ou expirado."""
    dados = _ADMIN_TOKENS.get(x_admin_token)
    if not dados or dados["tenant_id"] != tenant_id or dados["expira_em"] < time.time():
        raise HTTPException(status_code=401, detail="Token de admin ausente, inválido ou expirado. Faça login novamente.")


class AdminLoginRequest(BaseModel):
    tenant_id: str
    senha: str


@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest, request: Request) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    # Bloqueio por IP (Fase 14, Bloco S, Task 2) -- antes era por tenant_id, e como este projeto é
    # single-tenant, qualquer um conseguia negar o acesso do admin legítimo por 15 minutos só
    # errando a senha 5 vezes (DoS trivial, sem precisar saber nada além do tenant_id público).
    ip_cliente = request.client.host if request.client else "desconhecido"
    agora = time.time()
    estado = _ADMIN_LOGIN_TENTATIVAS.get(ip_cliente, {"falhas": 0, "bloqueado_ate": 0.0})
    if estado["bloqueado_ate"] > agora:
        minutos_restantes = int((estado["bloqueado_ate"] - agora) / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas de login incorretas. Tente novamente em {minutos_restantes} minuto(s)."
        )

    senha_correta = obter_secret_tenant(payload.tenant_id, "ADMIN_PASSWORD")
    # hmac.compare_digest evita timing attack -- "==" vaza quantos caracteres iniciais bateram
    # através do tempo de resposta.
    autorizado = bool(senha_correta) and hmac.compare_digest(payload.senha, senha_correta)

    if not autorizado:
        estado["falhas"] += 1
        if estado["falhas"] >= MAX_TENTATIVAS_LOGIN_ADMIN:
            estado["bloqueado_ate"] = agora + DURACAO_BLOQUEIO_LOGIN_SEGUNDOS
            estado["falhas"] = 0
        _ADMIN_LOGIN_TENTATIVAS[ip_cliente] = estado
        return {"autorizado": False, "token": None}

    _ADMIN_LOGIN_TENTATIVAS.pop(ip_cliente, None)
    return {"autorizado": True, "token": _gerar_token_admin(payload.tenant_id)}


# ─────────────────────────────────────────────────────────────────────────────
# CHAT (implementados: "Base de Conhecimento", "Análise de Dados" e "Gerador de
# Croqui". Modos custom adicionais ficam para uma sessão futura.)
# ─────────────────────────────────────────────────────────────────────────────
class MensagemHistorico(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    tenant_id: str
    conversation_id: Optional[str] = None
    modo: str
    perfil_usuario: Optional[str] = None
    mensagem: str
    historico: Optional[List[MensagemHistorico]] = None
    estilo_croqui: Optional[str] = None


def _montar_custom_prompt(
    config: Dict[str, Any],
    modo_selecionado: str,
    perfil_usuario: Optional[str],
    estilo_croqui: Optional[str] = None
) -> str:
    """Monta o prompt de sistema (regras de base + prompt do modo + contexto de perfil).

    As regras de base vêm de duas partes independentes (Fase 7, Bloco E): prompt_seguranca
    (sempre aplicado, todo modo) e prompt_escopo_moda (só aplicado quando o modo tiver
    escopo_moda=True, o padrão -- o modo "Assistente Geral" define escopo_moda=False para não
    herdar a restrição "responda só sobre moda").

    Para o modo "Gerador de Croqui", seleciona prompt_tecnico ou prompt_ilustracao
    conforme estilo_croqui, espelhando app.py.
    """
    modo_cfg = config["modos"][modo_selecionado]
    prompt_modo = modo_cfg["prompt"]

    if modo_selecionado == "Gerador de Croqui":
        estilo = estilo_croqui or ESTILO_ILUSTRACAO
        if estilo == ESTILO_TECNICO:
            prompt_modo = modo_cfg.get("prompt_tecnico", prompt_modo)
        else:
            prompt_modo = modo_cfg.get("prompt_ilustracao", prompt_modo)

    partes_base = [config["prompt_seguranca"]]
    if modo_cfg.get("escopo_moda", True):
        partes_base.append(config["prompt_escopo_moda"])
    prompt_base = "\n\n".join(partes_base)

    contexto_perfil = ""
    if perfil_usuario:
        perfil_info = PERFIS_USUARIO.get(perfil_usuario, {})
        rotulo = perfil_info.get("rotulo_prompt", perfil_usuario)
        contexto_perfil = f"\n\nO usuário se identificou como {rotulo}. Adapte a profundidade técnica e o tom da resposta para esse perfil."

    return f"{prompt_base}\n\n{prompt_modo}{contexto_perfil}"


def _chat_analise_dados(payload: "ChatRequest", config: Dict[str, Any]) -> Dict[str, Any]:
    """Modo "Análise de Dados": interpreta o resumo estatístico persistido para a conversa.

    Requer que POST /planilha/upload já tenha sido chamado antes para o mesmo
    tenant_id + conversation_id, persistindo o resumo via
    analise_dados.salvar_resumo_estatistico (substitui st.session_state.resumo_estatistico_atual).
    """
    if not payload.conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id é obrigatório para o modo 'Análise de Dados'.")

    resumo_estatistico = carregar_resumo_estatistico(payload.tenant_id, payload.conversation_id)
    if not resumo_estatistico:
        return {
            "resposta": "Nenhum resumo de dados foi encontrado para esta conversa. Faça o upload de uma planilha primeiro via POST /planilha/upload.",
            "fontes_consultadas": [],
            "trechos_consultados": []
        }

    custom_prompt = _montar_custom_prompt(config, payload.modo, payload.perfil_usuario)

    api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")

    client = OpenAI(api_key=api_key)
    resposta = responder_pergunta_sobre_dados(
        client=client,
        pergunta=payload.mensagem,
        resumo_estatistico=resumo_estatistico,
        prompt_sistema=custom_prompt,
        modelo=OPENAI_TEXT_MODEL,
        tenant_id=payload.tenant_id
    )
    return {"resposta": resposta, "fontes_consultadas": [], "trechos_consultados": []}


def _chat_via_agente(payload: "ChatRequest", config: Dict[str, Any]) -> Dict[str, Any]:
    """Modos baseados em agente com tool calling (Responses API, Fase 10): Gerador de Croqui,
    Consultor de Estilo, Professor Técnico, Engenharia Têxtil, Tendências e Assistente Geral.

    A função é agnóstica ao modo -- só repassa a lista de nomes de ferramentas configurada para
    o modo (config["modos"][payload.modo]["tools"], nomes do registry em agente_ferramentas.py;
    None para modos sem tool) e a flag usar_web_search (habilitada por modo na Fase 10, Bloco C).
    Só o Gerador de Croqui de fato aciona o fluxo de confirmação abaixo (pendente_confirmacao),
    pois gerar_imagem_croqui/gerar_ficha_tecnica são as únicas ferramentas marcadas
    exige_confirmacao=True no registry.

    Quando o modelo decide chamar uma dessas ferramentas, a execução (custo real de geração de
    imagem) NÃO ocorre aqui -- retorna pendente_confirmacao para o front-end exibir a confirmação
    ("Entendi que você quer: ...") antes de gastar a chamada. A confirmação/cancelamento é feita
    em POST /chat/croqui/confirmar.
    """
    estilo = payload.estilo_croqui or ESTILO_ILUSTRACAO
    instructions = _montar_custom_prompt(config, payload.modo, payload.perfil_usuario, estilo)
    input_items = montar_input_historico(payload.mensagem, payload.historico)

    api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
    client = OpenAI(api_key=api_key)

    modo_cfg = config["modos"][payload.modo]
    contexto = ContextoExecucao(
        tenant_id=payload.tenant_id,
        conversation_id=payload.conversation_id,
        perfil_usuario=payload.perfil_usuario,
        estilo_croqui=estilo,
        client=client,
        mensagem_usuario=payload.mensagem,
    )

    # Fase 10, Task 8: limite_buscas_web_dia -- diferente do limite de imagens (que bloqueia a
    # rota com 429, porque a geração de imagem É o pedido do usuário), aqui a busca web é só uma
    # ferramenta a mais que o modo pode usar. Bloquear a rota inteira deixaria o modo Tendências
    # inutilizável pelo resto do dia assim que a cota estourasse -- em vez disso, quando a cota
    # já foi atingida, a chamada segue sem a ferramenta (o modelo responde com conhecimento
    # próprio) em vez de falhar. Só desliga a busca se o modo de fato a usaria.
    usar_web_search = modo_cfg.get("usar_web_search", False)
    # Sinalizado pro frontend (Fase 14, Bloco U, Task 9) -- antes a degradação era só um log de
    # servidor: o usuário recebia uma resposta de qualidade inferior (sem pesquisa) achando que
    # era normal, sem nenhum aviso de que o limite diário do modo tinha sido atingido.
    busca_web_desligada_por_cota = False
    if usar_web_search:
        limite_buscas = config.get("limite_buscas_web_dia", 50)
        if not verificar_limite(payload.tenant_id, "buscas_web", limite_buscas, quantidade_necessaria=1):
            obter_logger(payload.tenant_id).warning(
                f"Limite diário de buscas web atingido para o modo '{payload.modo}' -- respondendo sem web_search nesta chamada."
            )
            usar_web_search = False
            busca_web_desligada_por_cota = True

    resultado = chamar_agente(
        client,
        instructions,
        modo_cfg.get("tools"),
        input_items,
        contexto,
        usar_web_search=usar_web_search,
    )

    if resultado.usou_web_search:
        incrementar_uso(payload.tenant_id, "buscas_web")

    if resultado.pendente_confirmacao:
        pendente = dict(resultado.pendente_confirmacao)
        pendente["modo"] = payload.modo
        return {
            "resposta": None,
            "imagem_url": None,
            "pendente_confirmacao": pendente,
            "fontes_consultadas": [],
            "trechos_consultados": [],
            "usou_busca_web": resultado.usou_web_search,
            "busca_web_desligada_por_cota": busca_web_desligada_por_cota,
        }

    # fontes_consultadas/trechos_consultados unificam citações do web_search nativo (título +
    # URL) e de tools que devolvem "fontes" em dados_extras (ex: buscar_documentos_internos) --
    # mesmo contrato que o modo "Base de Conhecimento" já usa, então o front-end exibe as duas
    # igualmente sem precisar saber a origem. "url" vai como campo próprio (Fase 10, Task 10) em
    # vez de embutido no texto do trecho -- o front-end usa isso pra tornar a fonte um link
    # clicável de verdade; documentos internos não têm URL real, então o campo fica None/ausente.
    return {
        "resposta": resultado.texto,
        "imagem_url": resultado.imagem_url,
        "pendente_confirmacao": None,
        "fontes_consultadas": [f["titulo"] for f in resultado.fontes if f.get("titulo")],
        "trechos_consultados": [
            {"fonte": f["titulo"], "texto": f["trecho"], "url": f.get("url") or None}
            for f in resultado.fontes
        ],
        "usou_busca_web": resultado.usou_web_search,
        "busca_web_desligada_por_cota": busca_web_desligada_por_cota,
    }


@app.post("/chat")
def chat(payload: ChatRequest) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])

    if payload.modo not in config["modos"]:
        raise HTTPException(status_code=400, detail=f"Modo '{payload.modo}' inválido para o tenant '{payload.tenant_id}'.")

    # Fase 10, Task 8: limite_mensagens_dia estava configurado em TENANT_CONFIG desde sempre mas
    # nunca era de fato verificado -- qualquer volume de chat passava sem checagem de custo. Um
    # único ponto de checagem/incremento aqui cobre os 3 caminhos abaixo (Análise de Dados,
    # agente, Base de Conhecimento) sem duplicar a lógica em cada um. Se a chamada abaixo levantar
    # uma exceção (ex: 500 da OpenAI), o incremento no fim da função não é alcançado -- mesmo
    # comportamento do limite de imagens (só conta uso que de fato completou).
    limite_msgs = config.get("limite_mensagens_dia", 200)
    if not verificar_limite(payload.tenant_id, "mensagens", limite_msgs, quantidade_necessaria=1):
        raise HTTPException(status_code=429, detail="Limite diário de mensagens atingido. Novas mensagens estarão disponíveis amanhã.")

    if payload.modo == "Análise de Dados":
        resultado = _chat_analise_dados(payload, config)
    elif payload.modo != "Base de Conhecimento":
        resultado = _chat_via_agente(payload, config)
    else:
        chunks_relevantes = buscar_contexto_relevante(
            payload.tenant_id,
            payload.mensagem,
            top_k=10,
            conversation_id=payload.conversation_id
        )

        if not chunks_relevantes:
            docs_cadastrados = listar_documentos_indexados(payload.tenant_id)
            if docs_cadastrados:
                resposta = "Não encontrei essa informação no documento."
            else:
                resposta = "📚 Nenhum documento foi carregado ainda para este assistente na Base de Conhecimento. Peça ao administrador para adicionar materiais na aba Configurações."
            resultado = {"resposta": resposta, "fontes_consultadas": [], "trechos_consultados": []}
        else:
            prompt_com_contexto, fontes_consultadas = montar_prompt_final(chunks_relevantes, payload.mensagem)
            custom_prompt = _montar_custom_prompt(config, payload.modo, payload.perfil_usuario)

            api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
            if not api_key:
                raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")

            client = OpenAI(api_key=api_key)
            resposta_obj = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": custom_prompt},
                    {"role": "user", "content": prompt_com_contexto}
                ],
                model=OPENAI_TEXT_MODEL,
                temperature=0.1,
                max_tokens=2048
            )
            resposta = resposta_obj.choices[0].message.content

            resultado = {
                "resposta": resposta,
                # Mesma ordem/tamanho de chunks_relevantes (Fase 13, Task 17) -- nunca
                # deduplicar/reordenar aqui, ou o pareamento por índice no front-end quebra.
                "fontes_consultadas": fontes_consultadas,
                "trechos_consultados": chunks_relevantes
            }

    incrementar_uso(payload.tenant_id, "mensagens")
    return resultado


class ConfirmarCroquiRequest(BaseModel):
    tenant_id: str
    confirmado: bool
    pendente: Dict[str, Any]


def _confirmar_criacao_de_ficha(payload: "ConfirmarCroquiRequest", client: OpenAI) -> Dict[str, Any]:
    """Ramo do gerar_ficha_tecnica (Fase 12): cria a ficha de verdade em /fichas, em vez de gerar
    uma imagem. Chamada real de API (extração estruturada) -- por isso a cota diária ("fichas",
    mesma de POST /fichas) é checada aqui antes de gastar qualquer coisa, no mesmo padrão que a
    cota de imagens é checada abaixo antes de gerar_imagem_croqui.
    """
    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])
    limite_fichas = config.get("limite_fichas_dia", 30)
    if not verificar_limite(payload.tenant_id, "fichas", limite_fichas, quantidade_necessaria=1):
        raise HTTPException(status_code=429, detail="Limite diário de fichas técnicas atingido. Novas extrações estarão disponíveis amanhã.")

    contexto = ContextoExecucao(
        tenant_id=payload.tenant_id,
        client=client,
        mensagem_usuario=payload.pendente.get("mensagem_usuario", ""),
    )
    resultado_ferramenta = executar_ferramenta(
        "gerar_ficha_tecnica", payload.pendente.get("argumentos", {}), contexto
    )

    instructions = payload.pendente.get("instructions", "")
    texto_final = retomar_apos_confirmacao(
        client, instructions, payload.pendente, resultado_ferramenta.conteudo, tenant_id=payload.tenant_id
    )

    return {
        "resposta": texto_final,
        "imagem_url": None,
        "ficha_id": resultado_ferramenta.dados_extras.get("ficha_id"),
        "redirecionar_para": resultado_ferramenta.dados_extras.get("redirecionar_para"),
    }


def _persistir_croqui_best_effort(tenant_id: str, imagem_url: str, estilo: str, resumo: str) -> Optional[str]:
    """Decodifica a data URI do croqui recém-gerado e salva na galeria (Fase 14, Bloco G, Task 14).

    Best-effort de propósito: a imagem já foi gerada e cobrada (incrementar_uso já rodou antes
    desta chamada) -- uma falha ao gravar em disco não pode virar erro 500 pro usuário nem
    descartar a resposta que ele já pagou por ela, só significa que este croqui em particular não
    aparecerá na galeria depois. `None` sinaliza "não foi possível persistir" sem quebrar o fluxo.
    """
    try:
        if not eh_imagem_gerada(imagem_url):
            raise ValueError("imagem_url não é uma data URI PNG reconhecida.")
        conteudo = base64.b64decode(imagem_url[len(PREFIXO_IMAGEM_GERADA):])
        entrada = salvar_croqui(tenant_id, conteudo, estilo=estilo, resumo=resumo)
        return entrada["id"]
    except Exception as e:
        obter_logger(tenant_id).error(f"Falha ao persistir croqui na galeria: {e}", exc_info=True)
        return None


@app.post("/chat/croqui/confirmar")
def confirmar_croqui(payload: ConfirmarCroquiRequest) -> Dict[str, Any]:
    """Segundo passo dos modos com ferramenta cara: confirma ou cancela a execução.

    `payload.pendente` é o mesmo dict retornado em `pendente_confirmacao` por POST /chat --
    o front-end o mantém em memória e o devolve aqui inalterado, evitando qualquer estado
    guardado no servidor entre as duas chamadas. `nome_ferramenta` decide o caminho:
    gerar_imagem_croqui gera uma imagem (fluxo original, Fase 8); gerar_ficha_tecnica virou, na
    Fase 12, um atalho que cria uma ficha real em /fichas em vez de imagem + tabela solta no chat
    -- ver `_confirmar_criacao_de_ficha`.
    """
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    if not payload.confirmado:
        return {
            "resposta": "Entendido! Por favor, reescreva seu pedido com mais detalhes sobre como você gostaria que fosse o croqui.",
            "imagem_url": None
        }

    api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
    client = OpenAI(api_key=api_key)

    nome_ferramenta = payload.pendente.get("nome_ferramenta", "gerar_imagem_croqui")
    if nome_ferramenta == "gerar_ficha_tecnica":
        return _confirmar_criacao_de_ficha(payload, client)

    prompt_vis = payload.pendente.get("prompt_visual", "")
    estilo = payload.pendente.get("estilo_croqui", ESTILO_ILUSTRACAO)

    resultado_mod = validar_prompt_imagem(client, prompt_vis, payload.tenant_id)
    if not resultado_mod.get("aprovado", False):
        raise HTTPException(
            status_code=422,
            detail=resultado_mod.get("motivo", "O pedido contém elementos fora do escopo de moda e vestuário.")
        )

    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])
    limite_img = config.get("limite_imagens_dia", 30)
    if not verificar_limite(payload.tenant_id, "imagens", limite_img, quantidade_necessaria=1):
        raise HTTPException(status_code=429, detail="Limite diário de geração de imagens atingido. Novas gerações estarão disponíveis amanhã.")

    # Segunda moderação sobre o prompt JÁ com o sufixo técnico (SUFIXO_TECNICO): a que roda acima
    # (resultado_mod) só avalia o texto que o modelo produziu; esta cobre também o texto fixo que
    # o próprio sistema acrescenta antes de gerar (mesmo texto que o handler da ferramenta, mais
    # abaixo, vai reconstruir por conta própria para a chamada real de geração -- duplicar essa
    # concatenação aqui é o preço de manter a checagem de moderação exatamente sobre o prompt
    # final, sem precisar que o registry exponha um hook só para isso).
    if estilo == ESTILO_TECNICO:
        prompt_final = f"{prompt_vis}{SUFIXO_TECNICO}"
        resultado_mod_final = validar_prompt_imagem(client, prompt_final, payload.tenant_id)
        if not resultado_mod_final.get("aprovado", False):
            raise HTTPException(
                status_code=422,
                detail=resultado_mod_final.get("motivo", "O pedido contém elementos fora do escopo de moda e vestuário.")
            )

    contexto = ContextoExecucao(tenant_id=payload.tenant_id, estilo_croqui=estilo, client=client)
    resultado_ferramenta = executar_ferramenta(nome_ferramenta, payload.pendente.get("argumentos", {}), contexto)

    imagem_url_gerada = resultado_ferramenta.dados_extras.get("imagem_url")
    croqui_id = None
    if imagem_url_gerada:
        incrementar_uso(payload.tenant_id, "imagens")
        croqui_id = _persistir_croqui_best_effort(
            payload.tenant_id, imagem_url_gerada, estilo, payload.pendente.get("resumo_confirmacao", "")
        )

    instructions = payload.pendente.get("instructions", "")
    texto_final = retomar_apos_confirmacao(
        client, instructions, payload.pendente, resultado_ferramenta.conteudo, tenant_id=payload.tenant_id
    )

    return {
        "resposta": texto_final,
        "imagem_url": imagem_url_gerada,
        "croqui_id": croqui_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSAS
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/conversas")
def listar_conversas(tenant_id: str, usuario_id: str) -> List[Dict[str, Any]]:
    return carregar_conversas(tenant_id, usuario_id)


class NovaConversaRequest(BaseModel):
    tenant_id: str
    usuario_id: str


@app.post("/conversas")
def criar_conversa(payload: NovaConversaRequest) -> Dict[str, Any]:
    conversas = carregar_conversas(payload.tenant_id, payload.usuario_id)
    nova_conv = criar_nova_conversa()
    conversas.append(nova_conv)
    salvar_conversas(payload.tenant_id, payload.usuario_id, conversas)
    return nova_conv


class AtualizarConversaRequest(BaseModel):
    tenant_id: str
    usuario_id: str
    novo_titulo: Optional[str] = None
    mensagens: Optional[List[Dict[str, Any]]] = None


@app.patch("/conversas/{conversa_id}")
def atualizar_conversa_endpoint(conversa_id: str, payload: AtualizarConversaRequest) -> Dict[str, Any]:
    """Atualiza título e/ou mensagens de uma conversa.

    Substitui a lacuna do contrato original (que só previa renomear): o front-end
    precisa de uma forma de persistir o histórico de mensagens à medida que a
    conversa avança, equivalente a persistir_mensagem_atualizada() em app.py.
    """
    if payload.novo_titulo is None and payload.mensagens is None:
        raise HTTPException(status_code=400, detail="Informe ao menos 'novo_titulo' ou 'mensagens' para atualizar.")

    conversas = carregar_conversas(payload.tenant_id, payload.usuario_id)
    conversa = next((c for c in conversas if c.get("id") == conversa_id), None)
    if conversa is None:
        raise HTTPException(status_code=404, detail=f"Conversa '{conversa_id}' não encontrada.")

    if payload.novo_titulo is not None:
        sucesso = renomear_conversa(conversas, conversa_id, payload.novo_titulo)
        if not sucesso:
            raise HTTPException(status_code=400, detail="Título vazio não é permitido.")

    if payload.mensagens is not None:
        conversa["mensagens"] = payload.mensagens
        conversa["atualizado_em"] = datetime.now().isoformat()
        if conversa.get("titulo") == "Nova conversa":
            primeira_user_msg = next((m.get("content", "") for m in payload.mensagens if m.get("role") == "user"), "")
            if primeira_user_msg:
                conversa["titulo"] = gerar_titulo_conversa(primeira_user_msg)

    salvar_conversas(payload.tenant_id, payload.usuario_id, conversas)
    return conversa


@app.delete("/conversas/{conversa_id}")
def deletar_conversa(conversa_id: str, tenant_id: str, usuario_id: str) -> Dict[str, str]:
    conversas = carregar_conversas(tenant_id, usuario_id)
    conversas_restantes = [c for c in conversas if c.get("id") != conversa_id]
    if len(conversas_restantes) == len(conversas):
        raise HTTPException(status_code=404, detail=f"Conversa '{conversa_id}' não encontrada.")
    salvar_conversas(tenant_id, usuario_id, conversas_restantes)
    return {"status": "removida"}


@app.get("/conversas/{conversa_id}/export")
def exportar_conversa(conversa_id: str, tenant_id: str, usuario_id: str, formato: str = "txt") -> Response:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    if formato not in ("txt", "pdf"):
        raise HTTPException(status_code=400, detail=f"Formato '{formato}' inválido — use 'txt' ou 'pdf'.")

    conversas = carregar_conversas(tenant_id, usuario_id)
    conversa = next((c for c in conversas if c.get("id") == conversa_id), None)
    if conversa is None:
        raise HTTPException(status_code=404, detail=f"Conversa '{conversa_id}' não encontrada.")

    config = carregar_config_tenant(tenant_id, TENANT_CONFIG[tenant_id])
    messages = conversa.get("mensagens", [])
    titulo = conversa.get("titulo", "Conversa")

    if formato == "txt":
        conteudo = formatar_conversa_txt(messages, config, tenant_id=tenant_id, conversa_titulo=titulo)
        return Response(
            content=conteudo,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="conversa_{tenant_id}.txt"'}
        )

    pdf_bytes = gerar_conversa_pdf(messages, config, tenant_id=tenant_id, conversa_titulo=titulo)
    if pdf_bytes is None:
        raise HTTPException(status_code=500, detail="Biblioteca fpdf2 não disponível no servidor.")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="conversa_{tenant_id}.pdf"'}
    )


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENTOS (Base de Conhecimento)
# ─────────────────────────────────────────────────────────────────────────────
# Antes, /documentos/upload e /planilha/upload aceitavam arquivo de qualquer tamanho -- um
# upload muito grande (acidental ou não) podia gastar memória/disco/tempo de indexação
# desproporcionais. 20MB cobre com folga documentos técnicos e planilhas reais de uso normal.
LIMITE_UPLOAD_BYTES = 20 * 1024 * 1024


@app.get("/documentos")
def listar_documentos(tenant_id: str) -> List[str]:
    return listar_documentos_indexados(tenant_id)


@app.post("/documentos/upload")
async def upload_documento(
    tenant_id: str,
    arquivo: UploadFile = File(...),
    x_admin_token: str = Header(..., alias="X-Admin-Token")
) -> Dict[str, Any]:
    verificar_token_admin(tenant_id, x_admin_token)
    conteudo = await arquivo.read()
    if len(conteudo) > LIMITE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo '{arquivo.filename}' excede o limite de {LIMITE_UPLOAD_BYTES // (1024 * 1024)}MB por upload."
        )
    try:
        # Extração (parsing de PDF/DOCX/planilha) e indexação (embeddings via
        # sentence-transformers) são CPU-bound e síncronas -- rodar direto aqui bloquearia o
        # event loop inteiro, inclusive o chat de outros tenants, pela duração da indexação.
        unidades_extraidas = await asyncio.to_thread(extrair_documento, conteudo, nome_arquivo=arquivo.filename)
    except ValueError as err_val:
        raise HTTPException(status_code=400, detail=str(err_val))

    if not unidades_extraidas:
        raise HTTPException(status_code=422, detail=f"O arquivo '{arquivo.filename}' não contém texto legível, registros ou está vazio.")

    qtd_chunks = await asyncio.to_thread(indexar_documento, tenant_id, arquivo.filename, unidades_extraidas)
    if qtd_chunks == 0:
        raise HTTPException(status_code=422, detail=f"Nenhum chunk pôde ser gerado para o arquivo '{arquivo.filename}'.")

    return {"nome_arquivo": arquivo.filename, "chunks_indexados": qtd_chunks}


@app.delete("/documentos/{nome_arquivo}")
def deletar_documento(nome_arquivo: str, tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")) -> Dict[str, str]:
    verificar_token_admin(tenant_id, x_admin_token)
    removido = remover_documento(tenant_id, nome_arquivo)
    if not removido:
        raise HTTPException(status_code=404, detail=f"Documento '{nome_arquivo}' não encontrado para o tenant '{tenant_id}'.")
    return {"status": "removido"}


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISE DE DADOS (upload de planilha)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/planilha/upload")
async def upload_planilha(tenant_id: str, conversation_id: str, arquivo: UploadFile = File(...)) -> Dict[str, Any]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")

    conteudo = await arquivo.read()
    if len(conteudo) > LIMITE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo '{arquivo.filename}' excede o limite de {LIMITE_UPLOAD_BYTES // (1024 * 1024)}MB por upload."
        )
    stream = io.BytesIO(conteudo)
    stream.name = arquivo.filename

    # Mesmo motivo do /documentos/upload acima: parsing com pandas e o resumo estatístico são
    # síncronos e podem ser pesados o bastante para travar o event loop numa planilha grande.
    df = await asyncio.to_thread(carregar_planilha, stream, tenant_id)
    if df is None:
        raise HTTPException(status_code=422, detail=f"Não foi possível ler a planilha '{arquivo.filename}' (formato inválido, corrompida ou vazia).")

    resumo = await asyncio.to_thread(gerar_resumo_estatistico, df)
    salvar_resumo_estatistico(tenant_id, conversation_id, resumo)

    return {
        "nome_arquivo": arquivo.filename,
        "linhas": len(df),
        "colunas": list(df.columns),
        "resumo_estatistico": resumo
    }


# ─────────────────────────────────────────────────────────────────────────────
# FICHAS TÉCNICAS DE MODA (Fase 11, Task 6)
#
# Diferente de /conversas (por usuario_id, privado por navegador), fichas são compartilhadas por
# todo o tenant -- mesmo modelo de /documentos (recurso institucional do laboratório, não dado
# pessoal de quem está conversando). Decisão da Fase 11: uma empresa só (SENAI), sem cadastro
# multiempresa nem autenticação de usuário final -- por isso nenhuma rota abaixo pede usuario_id
# nem token de admin.
#
# O envelope de resposta {"ficha": ..., "alertas": [...]} recalcula os alertas de
# fichas_validacao.validar_ficha() a cada leitura/escrita -- os alertas refletem o estado atual
# dos dados, nunca um snapshot congelado de quando a ficha foi criada.
# ─────────────────────────────────────────────────────────────────────────────
def _nome_arquivo_ficha(ficha: Dict[str, Any], extensao: str) -> str:
    """Nome de download legível, a partir da referência e do nome da peça.

    "ficha_CM-001_Camisa_Social.docx" diz muito mais na pasta de downloads do usuário do que o
    uuid da ficha. Reduzido a ASCII e a caracteres seguros porque o nome viaja num header HTTP
    (Content-Disposition) -- acento e espaço ali causam comportamento inconsistente entre
    navegadores.
    """
    identificacao = (ficha.get("dados") or {}).get("ficha") or {}
    partes = [valor_de(identificacao.get("ref")) or "", valor_de(identificacao.get("nome")) or ""]
    rotulo = "_".join(parte for parte in partes if parte) or "ficha"

    rotulo = unicodedata.normalize("NFKD", rotulo).encode("ascii", "ignore").decode("ascii")
    rotulo = re.sub(r"[^A-Za-z0-9_-]+", "_", rotulo).strip("_")[:60]
    return f"ficha_{rotulo or 'sem_nome'}.{extensao}"


def _ficha_com_alertas(ficha: Dict[str, Any], alertas_extra: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    alertas = list(alertas_extra or [])
    alertas.extend(validar_ficha(ficha.get("dados", {})))
    return {"ficha": ficha, "alertas": alertas}


class CriarFichaRequest(BaseModel):
    tenant_id: str
    texto_origem: Optional[str] = None


class AtualizarFichaRequest(BaseModel):
    tenant_id: str
    ficha: Dict[str, Any]
    atualizado_em_esperado: Optional[str] = None


class DuplicarFichaRequest(BaseModel):
    tenant_id: str


@app.post("/fichas")
def criar_ficha_endpoint(payload: CriarFichaRequest) -> Dict[str, Any]:
    """Cria uma ficha nova. Se `texto_origem` for informado, extrai os dados estruturados
    (fichas_extracao, Structured Outputs -- chamada real de API) e audita a proveniência
    (fichas_verificacao) antes de persistir; sem texto, nasce em branco para revisão manual.
    """
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    alertas_proveniencia: List[Dict[str, Any]] = []

    if payload.texto_origem:
        config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])
        limite_fichas = config.get("limite_fichas_dia", 30)
        if not verificar_limite(payload.tenant_id, "fichas", limite_fichas, quantidade_necessaria=1):
            raise HTTPException(status_code=429, detail="Limite diário de fichas técnicas atingido. Novas extrações estarão disponíveis amanhã.")

        api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
        client = OpenAI(api_key=api_key)

        ficha, alertas_proveniencia = criar_ficha_a_partir_de_texto(payload.tenant_id, payload.texto_origem, client)
    else:
        ficha = criar_ficha(payload.tenant_id, texto_origem="")

    return _ficha_com_alertas(ficha, alertas_proveniencia)


@app.get("/fichas")
def listar_fichas_endpoint(tenant_id: str) -> List[Dict[str, Any]]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    return listar_fichas(tenant_id)


@app.get("/fichas/{ficha_id}")
def obter_ficha_endpoint(ficha_id: str, tenant_id: str) -> Dict[str, Any]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")

    try:
        ficha = carregar_ficha(tenant_id, ficha_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de ficha inválido: '{ficha_id}'.")
    if ficha is None:
        raise HTTPException(status_code=404, detail=f"Ficha '{ficha_id}' não encontrada.")
    return _ficha_com_alertas(ficha)


@app.put("/fichas/{ficha_id}")
def atualizar_ficha_endpoint(ficha_id: str, payload: AtualizarFichaRequest) -> Dict[str, Any]:
    """Salva os dados revisados de uma ficha existente.

    `atualizado_em_esperado`, quando informado, é o timestamp que o cliente tinha ao abrir a
    ficha para edição -- divergência do valor salvo em disco indica edição concorrente em outra
    sessão (ConflitoDeVersaoError, traduzido para HTTP 412 aqui).
    """
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    try:
        existente = carregar_ficha(payload.tenant_id, ficha_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de ficha inválido: '{ficha_id}'.")
    if existente is None:
        raise HTTPException(status_code=404, detail=f"Ficha '{ficha_id}' não encontrada.")

    ficha = dict(payload.ficha)
    ficha["id"] = ficha_id  # o path é a fonte de verdade do id, não o corpo da requisição

    try:
        ficha_salva = salvar_ficha(payload.tenant_id, ficha, atualizado_em_esperado=payload.atualizado_em_esperado)
    except ConflitoDeVersaoError as err_conflito:
        raise HTTPException(status_code=412, detail=str(err_conflito))

    return _ficha_com_alertas(ficha_salva)


@app.post("/fichas/{ficha_id}/duplicar")
def duplicar_ficha_endpoint(ficha_id: str, payload: DuplicarFichaRequest) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    try:
        copia = duplicar_ficha(payload.tenant_id, ficha_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de ficha inválido: '{ficha_id}'.")
    if copia is None:
        raise HTTPException(status_code=404, detail=f"Ficha '{ficha_id}' não encontrada.")
    return _ficha_com_alertas(copia)


def _carregar_ficha_ou_404(tenant_id: str, ficha_id: str) -> Dict[str, Any]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")

    try:
        ficha = carregar_ficha(tenant_id, ficha_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de ficha inválido: '{ficha_id}'.")
    if ficha is None:
        raise HTTPException(status_code=404, detail=f"Ficha '{ficha_id}' não encontrada.")
    return ficha


def _gerar_docx_e_marcar(tenant_id: str, ficha: Dict[str, Any], marcar: bool = True) -> str:
    """Renderiza o .docx da ficha e, opcionalmente, registra a geração no documento persistido.

    Gera na hora, a cada chamada, em vez de servir um arquivo guardado: a ficha pode ter sido
    editada depois da última geração, e entregar um documento desatualizado sem avisar seria pior
    do que o custo de renderizar de novo (que é local e rápido -- nenhuma chamada de API).

    `marcar=False` é usado pela pré-visualização: olhar a ficha não é o mesmo que emitir o
    documento final, então o status não pode virar DOCUMENTO_GERADO só por abrir a prévia.
    """
    try:
        caminho = fichas_docx.gerar_docx_da_ficha(tenant_id, ficha)
    except Exception:
        # gerar_docx_da_ficha já logou o erro com stack trace.
        raise HTTPException(status_code=500, detail="Falha ao gerar o documento da ficha técnica.")

    if marcar:
        ficha["documentos"]["docx"] = fichas_docx.NOME_ARQUIVO_DOCX
        ficha["documentos"]["gerado_em"] = datetime.now().isoformat()
        ficha["status"] = STATUS_DOCUMENTO_GERADO
        salvar_ficha(tenant_id, ficha)
    return caminho


@app.get("/fichas/{ficha_id}/docx")
def baixar_ficha_docx(ficha_id: str, tenant_id: str) -> Response:
    """Gera o documento Word da ficha e devolve o arquivo para download."""
    ficha = _carregar_ficha_ou_404(tenant_id, ficha_id)
    caminho = _gerar_docx_e_marcar(tenant_id, ficha)

    with open(caminho, "rb") as f:
        conteudo = f.read()

    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{_nome_arquivo_ficha(ficha, "docx")}"'},
    )


@app.get("/fichas/{ficha_id}/preview")
def previsualizar_ficha(ficha_id: str, tenant_id: str) -> Response:
    """PDF da ficha para exibição na tela, sem marcar a ficha como emitida.

    Rota separada do download (em vez de um parâmetro) porque a diferença não é de formato, é de
    intenção: pré-visualizar é conferir; baixar é emitir o documento. Só o segundo muda o status
    da ficha para DOCUMENTO_GERADO -- caso contrário, abrir a prévia para revisar marcaria a
    ficha como pronta, que é justamente o que o usuário ainda está decidindo.

    `Content-Disposition: inline` para o navegador exibir no lugar de baixar.
    """
    ficha = _carregar_ficha_ou_404(tenant_id, ficha_id)
    caminho_docx = _gerar_docx_e_marcar(tenant_id, ficha, marcar=False)

    try:
        caminho_pdf = fichas_pdf.gerar_pdf_da_ficha(tenant_id, ficha_id, caminho_docx)
    except fichas_pdf.LibreOfficeIndisponivelError as err:
        raise HTTPException(status_code=501, detail=str(err))
    except fichas_pdf.ConversaoPdfError as err:
        raise HTTPException(status_code=500, detail=str(err))

    with open(caminho_pdf, "rb") as f:
        conteudo = f.read()

    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="previa.pdf"'},
    )


@app.get("/fichas/{ficha_id}/pdf")
def baixar_ficha_pdf(ficha_id: str, tenant_id: str) -> Response:
    """Gera o PDF da ficha (Word renderizado pelo LibreOffice) e devolve para download.

    O PDF vem sempre do mesmo .docx que o usuário baixaria -- não é um segundo layout gerado em
    paralelo. É o que garante que os dois arquivos sejam visualmente idênticos.
    """
    ficha = _carregar_ficha_ou_404(tenant_id, ficha_id)
    caminho_docx = _gerar_docx_e_marcar(tenant_id, ficha)

    try:
        caminho_pdf = fichas_pdf.gerar_pdf_da_ficha(tenant_id, ficha_id, caminho_docx)
    except fichas_pdf.LibreOfficeIndisponivelError as err:
        # 501 (não implementado neste ambiente) em vez de 500: não é um defeito do código, é uma
        # dependência de sistema ausente -- e a mensagem diz exatamente o que instalar.
        raise HTTPException(status_code=501, detail=str(err))
    except fichas_pdf.ConversaoPdfError as err:
        raise HTTPException(status_code=500, detail=str(err))

    ficha["documentos"]["pdf"] = fichas_pdf.NOME_ARQUIVO_PDF
    salvar_ficha(tenant_id, ficha)

    with open(caminho_pdf, "rb") as f:
        conteudo = f.read()

    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_nome_arquivo_ficha(ficha, "pdf")}"'},
    )


class GerarDesenhoRequest(BaseModel):
    tenant_id: str
    instrucao_adicional: Optional[str] = None


@app.post("/fichas/{ficha_id}/desenho")
def gerar_desenho_endpoint(ficha_id: str, payload: GerarDesenhoRequest) -> Dict[str, Any]:
    """Gera uma nova versão do desenho técnico -- chamada real de API (moderação de texto +
    gpt-image-1), protegida pelo mesmo limite diário de imagens do Gerador de Croqui.

    `instrucao_adicional` é o pedido de ajuste da regeneração (ex: "a manga é 3/4, não curta") --
    vazio na primeira geração de cada ficha.
    """
    ficha = _carregar_ficha_ou_404(payload.tenant_id, ficha_id)

    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])
    limite_imagens = config.get("limite_imagens_dia", 30)

    api_key = obter_secret_tenant(payload.tenant_id, "OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"OPENAI_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
    client = OpenAI(api_key=api_key)

    try:
        ficha = fichas_desenho.gerar_nova_versao(
            client, payload.tenant_id, ficha, limite_imagens, instrucao_adicional=payload.instrucao_adicional or ""
        )
    except fichas_desenho.PromptReprovadoError as err:
        raise HTTPException(status_code=422, detail=err.motivo)
    except fichas_desenho.LimiteDeImagensExcedidoError as err:
        raise HTTPException(status_code=429, detail=str(err))
    except RuntimeError as err:
        raise HTTPException(status_code=500, detail=str(err))

    ficha["status"] = STATUS_DESENHO_GERADO
    ficha = salvar_ficha(payload.tenant_id, ficha)
    return _ficha_com_alertas(ficha)


class AprovarDesenhoRequest(BaseModel):
    tenant_id: str


@app.post("/fichas/{ficha_id}/desenho/{versao}/aprovar")
def aprovar_desenho_endpoint(ficha_id: str, versao: int, payload: AprovarDesenhoRequest) -> Dict[str, Any]:
    """Marca uma versão do desenho como aprovada. Sem chamada de API -- só muda o estado
    persistido da ficha."""
    ficha = _carregar_ficha_ou_404(payload.tenant_id, ficha_id)

    try:
        ficha = fichas_desenho.aprovar_versao(ficha, versao)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

    ficha = salvar_ficha(payload.tenant_id, ficha)
    return _ficha_com_alertas(ficha)


@app.get("/fichas/{ficha_id}/desenho/{versao}")
def obter_desenho_ficha(ficha_id: str, versao: int, tenant_id: str) -> Response:
    """Devolve o PNG de uma versão do desenho técnico já salva em disco (só leitura -- gerar uma
    versão nova é POST /fichas/{id}/desenho, acima)."""
    _carregar_ficha_ou_404(tenant_id, ficha_id)  # valida tenant + ficha antes de tocar em arquivo

    try:
        caminho = fichas_desenho.caminho_desenho(tenant_id, ficha_id, versao)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Versão de desenho inválida: {versao}.")
    if not caminho:
        raise HTTPException(status_code=404, detail=f"Versão {versao} do desenho não encontrada para esta ficha.")

    with open(caminho, "rb") as f:
        return Response(content=f.read(), media_type="image/png")


class ImportarCroquiComoDesenhoRequest(BaseModel):
    tenant_id: str
    croqui_id: str


@app.post("/fichas/{ficha_id}/desenho/importar-croqui")
def importar_croqui_como_desenho(ficha_id: str, payload: ImportarCroquiComoDesenhoRequest) -> Dict[str, Any]:
    """Reaproveita um croqui já salvo na galeria como uma nova versão do desenho técnico da ficha
    (Fase 14, Bloco G, Task 17) -- sem moderação, sem checagem de cota, sem chamada de API: a
    imagem já foi moderada e cobrada quando foi gerada originalmente no chat."""
    ficha = _carregar_ficha_ou_404(payload.tenant_id, ficha_id)

    try:
        caminho = caminho_croqui(payload.tenant_id, payload.croqui_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de croqui inválido: '{payload.croqui_id}'.")
    if not caminho:
        raise HTTPException(status_code=404, detail=f"Croqui '{payload.croqui_id}' não encontrado.")

    with open(caminho, "rb") as f:
        conteudo = f.read()

    ficha = fichas_desenho.anexar_versao(payload.tenant_id, ficha, conteudo, prompt_visual="(Importado da galeria de croquis)")
    ficha["status"] = STATUS_DESENHO_GERADO
    ficha = salvar_ficha(payload.tenant_id, ficha)
    return _ficha_com_alertas(ficha)


@app.delete("/fichas/{ficha_id}")
def deletar_ficha_endpoint(
    ficha_id: str, tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")
) -> Dict[str, str]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    verificar_token_admin(tenant_id, x_admin_token)

    try:
        removida = deletar_ficha(tenant_id, ficha_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de ficha inválido: '{ficha_id}'.")
    if not removida:
        raise HTTPException(status_code=404, detail=f"Ficha '{ficha_id}' não encontrada.")
    return {"status": "removida"}


# ─────────────────────────────────────────────────────────────────────────────
# GALERIA DE CROQUIS (Fase 14, Bloco G, Task 13)
#
# Espelha as rotas de desenho técnico da ficha (GET .../desenho/{versao} acima) -- mesma forma de
# devolver o PNG cru, mesma isenção do gate de acesso pro <img src> conseguir carregar sem header
# customizado. Ainda sem POST (a persistência acontece dentro de /chat/croqui/confirmar, Task 14).
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/croquis")
def listar_croquis_endpoint(tenant_id: str) -> List[Dict[str, Any]]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    return listar_croquis(tenant_id)


@app.get("/croquis/{croqui_id}/imagem")
def obter_imagem_croqui(croqui_id: str, tenant_id: str) -> Response:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    try:
        caminho = caminho_croqui(tenant_id, croqui_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de croqui inválido: '{croqui_id}'.")
    if not caminho:
        raise HTTPException(status_code=404, detail=f"Croqui '{croqui_id}' não encontrado.")

    with open(caminho, "rb") as f:
        return Response(content=f.read(), media_type="image/png")


@app.delete("/croquis/{croqui_id}")
def deletar_croqui_endpoint(
    croqui_id: str, tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")
) -> Dict[str, str]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    verificar_token_admin(tenant_id, x_admin_token)

    try:
        removido = deletar_croqui(tenant_id, croqui_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"ID de croqui inválido: '{croqui_id}'.")
    if not removido:
        raise HTTPException(status_code=404, detail=f"Croqui '{croqui_id}' não encontrado.")
    return {"status": "removido"}


# ─────────────────────────────────────────────────────────────────────────────
# LOGO DA EMPRESA (Fase 11, Task 11)
#
# Cadastrado uma vez e reaproveitado em toda ficha gerada. É configuração do tenant (mesma
# natureza de PUT /config/tenant), então upload e remoção exigem token de admin -- só a leitura
# é aberta, porque a tela de configuração precisa exibir a prévia.
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/branding/logo")
async def upload_logo(
    tenant_id: str,
    arquivo: UploadFile = File(...),
    x_admin_token: str = Header(..., alias="X-Admin-Token"),
) -> Dict[str, Any]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    verificar_token_admin(tenant_id, x_admin_token)

    conteudo = await arquivo.read()
    try:
        metadados = fichas_logo.salvar_logo(tenant_id, conteudo, nome_original=arquivo.filename or "")
    except fichas_logo.LogoInvalidoError as err:
        raise HTTPException(status_code=400, detail=str(err))

    return metadados


@app.get("/branding/logo")
def obter_logo(tenant_id: str) -> Response:
    """Devolve a imagem do logo cadastrado (para a prévia na tela de configuração)."""
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")

    caminho = fichas_logo.caminho_logo(tenant_id)
    if not caminho:
        raise HTTPException(status_code=404, detail="Nenhum logo cadastrado para este tenant.")

    with open(caminho, "rb") as f:
        return Response(content=f.read(), media_type="image/png")


@app.get("/branding/logo/info")
def obter_info_logo(tenant_id: str) -> Dict[str, Any]:
    """Metadados do logo (nome original, formato, dimensões) sem trafegar a imagem -- a tela usa
    isso para saber se há logo cadastrado antes de tentar exibi-lo."""
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")

    metadados = fichas_logo.metadados_logo(tenant_id)
    return {"cadastrado": metadados is not None, "metadados": metadados}


@app.delete("/branding/logo")
def deletar_logo(tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")) -> Dict[str, str]:
    if tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' não encontrado.")
    verificar_token_admin(tenant_id, x_admin_token)

    if not fichas_logo.remover_logo(tenant_id):
        raise HTTPException(status_code=404, detail="Nenhum logo cadastrado para este tenant.")
    return {"status": "removido"}


# ─────────────────────────────────────────────────────────────────────────────
# DEBUG/OBSERVABILIDADE (stub, uso interno)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/debug/rag")
def debug_rag(tenant_id: str, x_admin_token: str = Header(..., alias="X-Admin-Token")) -> Dict[str, Any]:
    """Retorna o último relatório de debug do pipeline RAG do `tenant_id` informado.

    Exige token de admin desse mesmo tenant (Fase 13, Task 16) -- a rota devolve a pergunta e o
    texto integral dos chunks recuperados, dado sensível o bastante para justificar a mesma
    autenticação das outras rotas administrativas. `obter_ultimo_rag_debug` já segmenta por
    tenant: nunca devolve o debug de uma busca de outro tenant, mesmo que ela tenha sido a mais
    recente do processo. Uso interno/administrativo, não destinado ao front-end React.
    """
    verificar_token_admin(tenant_id, x_admin_token)
    return obter_ultimo_rag_debug(tenant_id)
