# -*- coding: utf-8 -*-
"""Scaffold da API do SenaiLabFashionAssistant (Fase 3, Passo 16).

Casca HTTP em FastAPI para expor a lógica de negócio já existente (rag_manager.py,
conversas_manager.py, analise_dados.py, tenant_config.py) sem depender do Streamlit.
Estrutura de rotas conforme `API_CONTRATO.md`; endpoints marcados como stub ainda não
têm lógica implementada (ver roadmap: cada um é implementado em uma sessão futura).

Rodar localmente: uvicorn api.main:app --reload
"""

import hmac
import io
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
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
from usage_tracker import incrementar_uso, verificar_limite
from logger_config import obter_logger
from geracao_imagem import ESTILO_ILUSTRACAO, ESTILO_TECNICO, SUFIXO_TECNICO
from agente_ferramentas import ContextoExecucao, executar_ferramenta
from agente_openai import chamar_agente, montar_input_historico, retomar_apos_confirmacao

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
)


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
_ADMIN_LOGIN_TENTATIVAS: Dict[str, Dict[str, Any]] = {}  # tenant_id -> {"falhas": int, "bloqueado_ate": timestamp}

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
def admin_login(payload: AdminLoginRequest) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    agora = time.time()
    estado = _ADMIN_LOGIN_TENTATIVAS.get(payload.tenant_id, {"falhas": 0, "bloqueado_ate": 0.0})
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
        _ADMIN_LOGIN_TENTATIVAS[payload.tenant_id] = estado
        return {"autorizado": False, "token": None}

    _ADMIN_LOGIN_TENTATIVAS.pop(payload.tenant_id, None)
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
    )

    # Fase 10, Task 8: limite_buscas_web_dia -- diferente do limite de imagens (que bloqueia a
    # rota com 429, porque a geração de imagem É o pedido do usuário), aqui a busca web é só uma
    # ferramenta a mais que o modo pode usar. Bloquear a rota inteira deixaria o modo Tendências
    # inutilizável pelo resto do dia assim que a cota estourasse -- em vez disso, quando a cota
    # já foi atingida, a chamada segue sem a ferramenta (o modelo responde com conhecimento
    # próprio) em vez de falhar. Só desliga a busca se o modo de fato a usaria.
    usar_web_search = modo_cfg.get("usar_web_search", False)
    if usar_web_search:
        limite_buscas = config.get("limite_buscas_web_dia", 50)
        if not verificar_limite(payload.tenant_id, "buscas_web", limite_buscas, quantidade_necessaria=1):
            obter_logger(payload.tenant_id).warning(
                f"Limite diário de buscas web atingido para o modo '{payload.modo}' -- respondendo sem web_search nesta chamada."
            )
            usar_web_search = False

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
                "fontes_consultadas": sorted(fontes_consultadas),
                "trechos_consultados": chunks_relevantes
            }

    incrementar_uso(payload.tenant_id, "mensagens")
    return resultado


class ConfirmarCroquiRequest(BaseModel):
    tenant_id: str
    confirmado: bool
    pendente: Dict[str, Any]


@app.post("/chat/croqui/confirmar")
def confirmar_croqui(payload: ConfirmarCroquiRequest) -> Dict[str, Any]:
    """Segundo passo do modo "Gerador de Croqui": confirma ou cancela a geração de imagem.

    `payload.pendente` é o mesmo dict retornado em `pendente_confirmacao` por POST /chat --
    o front-end o mantém em memória e o devolve aqui inalterado, evitando qualquer estado
    guardado no servidor entre as duas chamadas.
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

    prompt_vis = payload.pendente.get("prompt_visual", "")
    estilo = payload.pendente.get("estilo_croqui", ESTILO_ILUSTRACAO)
    # gerar_ficha_tecnica só faz sentido pareada com o fluxo frente/costas do Desenho Técnico
    # (Fase 8) -- força esse caminho mesmo no caso hipotético de o modelo tê-la chamado fora do
    # estilo técnico, já que não existe um equivalente de ficha técnica para Ilustração de Moda.
    eh_ficha_tecnica = payload.pendente.get("nome_ferramenta") == "gerar_ficha_tecnica"

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
    if estilo == ESTILO_TECNICO or eh_ficha_tecnica:
        prompt_final = f"{prompt_vis}{SUFIXO_TECNICO}"
        resultado_mod_final = validar_prompt_imagem(client, prompt_final, payload.tenant_id)
        if not resultado_mod_final.get("aprovado", False):
            raise HTTPException(
                status_code=422,
                detail=resultado_mod_final.get("motivo", "O pedido contém elementos fora do escopo de moda e vestuário.")
            )

    nome_ferramenta = payload.pendente.get("nome_ferramenta", "gerar_imagem_croqui")
    contexto = ContextoExecucao(tenant_id=payload.tenant_id, estilo_croqui=estilo, client=client)
    resultado_ferramenta = executar_ferramenta(nome_ferramenta, payload.pendente.get("argumentos", {}), contexto)

    imagem_url_gerada = resultado_ferramenta.dados_extras.get("imagem_url")
    if imagem_url_gerada:
        incrementar_uso(payload.tenant_id, "imagens")

    instructions = payload.pendente.get("instructions", "")
    texto_final = retomar_apos_confirmacao(
        client, instructions, payload.pendente, resultado_ferramenta.conteudo, tenant_id=payload.tenant_id
    )

    return {
        "resposta": texto_final,
        "imagem_url": imagem_url_gerada
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
        unidades_extraidas = extrair_documento(conteudo, nome_arquivo=arquivo.filename)
    except ValueError as err_val:
        raise HTTPException(status_code=400, detail=str(err_val))

    if not unidades_extraidas:
        raise HTTPException(status_code=422, detail=f"O arquivo '{arquivo.filename}' não contém texto legível, registros ou está vazio.")

    qtd_chunks = indexar_documento(tenant_id, arquivo.filename, unidades_extraidas)
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

    df = carregar_planilha(stream, tenant_id)
    if df is None:
        raise HTTPException(status_code=422, detail=f"Não foi possível ler a planilha '{arquivo.filename}' (formato inválido, corrompida ou vazia).")

    resumo = gerar_resumo_estatistico(df)
    salvar_resumo_estatistico(tenant_id, conversation_id, resumo)

    return {
        "nome_arquivo": arquivo.filename,
        "linhas": len(df),
        "colunas": list(df.columns),
        "resumo_estatistico": resumo
    }


# ─────────────────────────────────────────────────────────────────────────────
# DEBUG/OBSERVABILIDADE (stub, uso interno)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/debug/rag")
def debug_rag(tenant_id: str) -> Dict[str, Any]:
    """Retorna o último relatório de debug do pipeline RAG gerado neste processo.

    Limitação herdada de rag_manager.py: o debug é um estado global do módulo
    (_ULTIMO_RAG_DEBUG), não segmentado por tenant nem por requisição — em um
    servidor com múltiplos workers/requisições concorrentes, reflete apenas a
    última busca executada neste processo, não necessariamente a do `tenant_id`
    informado. Uso interno/administrativo, não destinado ao front-end React.
    """
    return obter_ultimo_rag_debug()
