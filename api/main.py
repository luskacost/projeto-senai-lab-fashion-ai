# -*- coding: utf-8 -*-
"""Scaffold da API do SenaiLabFashionAssistant (Fase 3, Passo 16).

Casca HTTP em FastAPI para expor a lógica de negócio já existente (rag_manager.py,
conversas_manager.py, analise_dados.py, tenant_config.py) sem depender do Streamlit.
Estrutura de rotas conforme `API_CONTRATO.md`; endpoints marcados como stub ainda não
têm lógica implementada (ver roadmap: cada um é implementado em uma sessão futura).

Rodar localmente: uvicorn api.main:app --reload
"""

import hashlib
import hmac
import io
import secrets
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq

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
from rag_config import GROQ_MODEL
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
from geracao_imagem import (
    ESTILO_ILUSTRACAO,
    ESTILO_TECNICO,
    SUFIXO_TECNICO,
    chamar_api_geracao_imagem,
    executar_ferramenta_local,
    chamar_agente
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

# CORS liberado para o front-end React/Next.js em desenvolvimento local (Fase 4).
# Restringir para o(s) domínio(s) reais de produção quando o front-end for implantado.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

    api_key = obter_secret_tenant(payload.tenant_id, "GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"GROQ_API_KEY não configurada para o tenant '{payload.tenant_id}'.")

    client = Groq(api_key=api_key)
    resposta = responder_pergunta_sobre_dados(
        client=client,
        pergunta=payload.mensagem,
        resumo_estatistico=resumo_estatistico,
        prompt_sistema=custom_prompt,
        modelo=GROQ_MODEL,
        tenant_id=payload.tenant_id
    )
    return {"resposta": resposta, "fontes_consultadas": [], "trechos_consultados": []}


def _chat_via_agente(payload: "ChatRequest", config: Dict[str, Any]) -> Dict[str, Any]:
    """Modos baseados em agente com tool calling (Groq): Gerador de Croqui, Consultor de Estilo,
    Professor Técnico e Tendências.

    A função é agnóstica ao modo -- chamar_agente() só usa as "tools" configuradas para o modo
    em questão (None para Consultor de Estilo/Professor Técnico, buscar_tendencias_web para Tendências,
    a função gerar_imagem_croqui para Gerador de Croqui). Só o Gerador de Croqui de fato aciona
    o fluxo de confirmação abaixo (pendente_confirmacao), pois é o único modo com essa tool.

    Quando o modelo decide chamar a ferramenta gerar_imagem_croqui, a geração da imagem em si
    NÃO ocorre aqui -- retorna pendente_confirmacao para o front-end exibir a confirmação
    ("Entendi que você quer: ...") antes de gastar uma chamada de geração de imagem. A
    confirmação/cancelamento é feita em POST /chat/croqui/confirmar.
    """
    estilo = payload.estilo_croqui or ESTILO_ILUSTRACAO
    custom_prompt = _montar_custom_prompt(config, payload.modo, payload.perfil_usuario, estilo)

    messages_for_api: List[Dict[str, str]] = [{"role": "system", "content": custom_prompt}]
    if payload.historico:
        for m in payload.historico:
            role = "assistant" if m.role in ("assistant", "IA") else m.role
            messages_for_api.append({"role": role, "content": m.content})
    else:
        messages_for_api.append({"role": "user", "content": payload.mensagem})

    api_key = obter_secret_tenant(payload.tenant_id, "GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"GROQ_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
    client = Groq(api_key=api_key)

    texto, imagem_url, usou_fallback, pendente, fontes_busca_web = chamar_agente(
        client, config["modos"][payload.modo], messages_for_api, payload.tenant_id, estilo
    )

    if pendente:
        pendente["modo"] = payload.modo
        return {
            "resposta": None,
            "imagem_url": None,
            "pendente_confirmacao": pendente,
            "fontes_consultadas": [],
            "trechos_consultados": []
        }

    return {
        "resposta": texto,
        "imagem_url": imagem_url,
        "pendente_confirmacao": None,
        "fontes_consultadas": [f["titulo"] for f in fontes_busca_web],
        "trechos_consultados": [
            {"fonte": f["titulo"], "texto": f"{f['trecho']}\n\nURL: {f['url']}"} for f in fontes_busca_web
        ]
    }


@app.post("/chat")
def chat(payload: ChatRequest) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])

    if payload.modo not in config["modos"]:
        raise HTTPException(status_code=400, detail=f"Modo '{payload.modo}' inválido para o tenant '{payload.tenant_id}'.")

    if payload.modo == "Análise de Dados":
        return _chat_analise_dados(payload, config)

    if payload.modo != "Base de Conhecimento":
        return _chat_via_agente(payload, config)

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
        return {"resposta": resposta, "fontes_consultadas": [], "trechos_consultados": []}

    prompt_com_contexto, fontes_consultadas = montar_prompt_final(chunks_relevantes, payload.mensagem)
    custom_prompt = _montar_custom_prompt(config, payload.modo, payload.perfil_usuario)

    api_key = obter_secret_tenant(payload.tenant_id, "GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"GROQ_API_KEY não configurada para o tenant '{payload.tenant_id}'.")

    client = Groq(api_key=api_key)
    resposta_obj = client.chat.completions.create(
        messages=[
            {"role": "system", "content": custom_prompt},
            {"role": "user", "content": prompt_com_contexto}
        ],
        model=GROQ_MODEL,
        temperature=0.1,
        max_tokens=2048
    )
    resposta = resposta_obj.choices[0].message.content

    return {
        "resposta": resposta,
        "fontes_consultadas": sorted(fontes_consultadas),
        "trechos_consultados": chunks_relevantes
    }


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
            "imagem_url": None,
            "imagem_url_costas": None
        }

    api_key = obter_secret_tenant(payload.tenant_id, "GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail=f"GROQ_API_KEY não configurada para o tenant '{payload.tenant_id}'.")
    client = Groq(api_key=api_key)

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
    qtd_necessaria = 2 if (estilo == ESTILO_TECNICO or eh_ficha_tecnica) else 1
    if not verificar_limite(payload.tenant_id, "imagens", limite_img, quantidade_necessaria=qtd_necessaria):
        raise HTTPException(status_code=429, detail="Limite diário de geração de imagens atingido. Novas gerações estarão disponíveis amanhã.")

    imagem_url_gerada = None
    imagem_url_costas_gerada = None

    if estilo == ESTILO_TECNICO or eh_ficha_tecnica:
        prompt_frente = f"{prompt_vis}{SUFIXO_TECNICO}, front view"
        prompt_costas = f"{prompt_vis}{SUFIXO_TECNICO}, back view"

        # Modera os dois prompts finais individualmente (não só o prompt_vis base acima) --
        # são eles, com os sufixos técnicos já aplicados, que de fato chegam ao provedor de
        # imagem. Hoje ambos derivam do mesmo prompt_vis já aprovado, mas validar o texto final
        # de cada vista fecha o gap para qualquer mudança futura que os faça divergir.
        for prompt_final, rotulo in ((prompt_frente, "frente"), (prompt_costas, "costas")):
            resultado_mod_vista = validar_prompt_imagem(client, prompt_final, payload.tenant_id)
            if not resultado_mod_vista.get("aprovado", False):
                raise HTTPException(
                    status_code=422,
                    detail=resultado_mod_vista.get(
                        "motivo", f"O pedido contém elementos fora do escopo de moda e vestuário (vista de {rotulo})."
                    )
                )

        # Seed derivado do prompt_vis (não do prompt final, que já muda por vista) para que
        # frente e costas do mesmo croqui usem o mesmo seed -- gera imagens mais consistentes
        # entre si na Pollinations do que dois seeds aleatórios independentes.
        seed_compartilhado = int(hashlib.sha256(prompt_vis.encode("utf-8")).hexdigest(), 16) % (2**31)
        res_frente = chamar_api_geracao_imagem(prompt_frente, seed=seed_compartilhado)
        res_costas = chamar_api_geracao_imagem(prompt_costas, seed=seed_compartilhado)
        if res_frente.startswith("https://image.pollinations.ai"):
            imagem_url_gerada = res_frente
            incrementar_uso(payload.tenant_id, "imagens")
        if res_costas.startswith("https://image.pollinations.ai"):
            imagem_url_costas_gerada = res_costas
            incrementar_uso(payload.tenant_id, "imagens")
        # Não repassa as URLs das imagens pro modelo no resultado da tool -- ele não precisa delas
        # pra nada (a interface já exibe as imagens sozinha) e incluí-las aqui só convida o modelo
        # a reproduzi-las na resposta em texto, duplicando as imagens como link feio na conversa.
        frente_ok = "sucesso" if imagem_url_gerada else "falhou"
        costas_ok = "sucesso" if imagem_url_costas_gerada else "falhou"
        if eh_ficha_tecnica:
            resultado_ferramenta = (
                f"Ficha técnica gerada: desenho técnico de frente ({frente_ok}) e de costas ({costas_ok}). "
                f"Agora monte a tabela markdown estruturada de medidas/materiais/aviamentos conforme instruído."
            )
        else:
            resultado_ferramenta = f"Desenhos técnicos vetoriais 2D gerados: frente ({frente_ok}), costas ({costas_ok})."
    else:
        resultado_ferramenta = executar_ferramenta_local("gerar_imagem_croqui", payload.pendente.get("argumentos", {}), payload.tenant_id, estilo)
        if resultado_ferramenta.startswith("https://image.pollinations.ai"):
            imagem_url_gerada = resultado_ferramenta
            incrementar_uso(payload.tenant_id, "imagens")

    msgs_api = list(payload.pendente.get("messages_for_api", []))
    msgs_api.append(payload.pendente.get("assistant_message"))
    msgs_api.append({
        "role": "tool",
        "tool_call_id": payload.pendente.get("tool_call_id"),
        "content": str(resultado_ferramenta),
    })

    segunda_resposta = client.chat.completions.create(
        messages=msgs_api,
        model=GROQ_MODEL,
        temperature=0.7,
        max_tokens=2048,
    )
    texto_final = segunda_resposta.choices[0].message.content

    return {
        "resposta": texto_final,
        "imagem_url": imagem_url_gerada,
        "imagem_url_costas": imagem_url_costas_gerada
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
