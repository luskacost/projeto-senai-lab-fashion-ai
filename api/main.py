# -*- coding: utf-8 -*-
"""Scaffold da API do SenaiLabFashionAssistant (Fase 3, Passo 16).

Casca HTTP em FastAPI para expor a lógica de negócio já existente (rag_manager.py,
conversas_manager.py, analise_dados.py, tenant_config.py) sem depender do Streamlit.
Estrutura de rotas conforme `API_CONTRATO.md`; endpoints marcados como stub ainda não
têm lógica implementada (ver roadmap: cada um é implementado em uma sessão futura).

Rodar localmente: uvicorn api.main:app --reload
"""

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
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
    formatar_conversa_txt,
    gerar_conversa_pdf
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


def _endpoint_nao_implementado(nome: str):
    raise HTTPException(
        status_code=501,
        detail=f"Endpoint '{nome}' ainda não implementado — ver API_CONTRATO.md e o roadmap (Fase 3, Passo 17+)."
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
def atualizar_config_tenant(payload: ConfigTenantUpdate) -> Dict[str, str]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")
    salvar_config_tenant(payload.tenant_id, payload.dados_custom)
    return {"status": "salvo"}


# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICAÇÃO/ADMIN (stub)
# ─────────────────────────────────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    tenant_id: str
    senha: str


@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest) -> Dict[str, bool]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")
    senha_correta = obter_secret_tenant(payload.tenant_id, "ADMIN_PASSWORD")
    return {"autorizado": bool(senha_correta) and payload.senha == senha_correta}


# ─────────────────────────────────────────────────────────────────────────────
# CHAT (Passo 17: implementado o modo "Base de Conhecimento";
# demais modos — Análise de Dados, Gerador de Croqui, custom — ficam para Passo 18+)
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    tenant_id: str
    conversation_id: Optional[str] = None
    modo: str
    perfil_usuario: Optional[str] = None
    mensagem: str


def _montar_custom_prompt(config: Dict[str, Any], modo_selecionado: str, perfil_usuario: Optional[str]) -> str:
    """Monta o prompt de sistema (base_prompt + prompt do modo + contexto de perfil).

    Espelha a montagem de CUSTOM_PROMPT em app.py, exceto pela seleção de estilo do
    "Gerador de Croqui" (prompt_tecnico/prompt_ilustracao) — não relevante para o modo
    "Base de Conhecimento" implementado aqui.
    """
    modo_cfg = config["modos"][modo_selecionado]
    prompt_modo = modo_cfg["prompt"]

    contexto_perfil = ""
    if perfil_usuario:
        perfil_info = PERFIS_USUARIO.get(perfil_usuario, {})
        rotulo = perfil_info.get("rotulo_prompt", perfil_usuario)
        contexto_perfil = f"\n\nO usuário se identificou como {rotulo}. Adapte a profundidade técnica e o tom da resposta para esse perfil."

    return f"{config['base_prompt']}\n\n{prompt_modo}{contexto_perfil}"


@app.post("/chat")
def chat(payload: ChatRequest) -> Dict[str, Any]:
    if payload.tenant_id not in TENANT_CONFIG:
        raise HTTPException(status_code=404, detail=f"Tenant '{payload.tenant_id}' não encontrado.")

    config = carregar_config_tenant(payload.tenant_id, TENANT_CONFIG[payload.tenant_id])

    if payload.modo not in config["modos"]:
        raise HTTPException(status_code=400, detail=f"Modo '{payload.modo}' inválido para o tenant '{payload.tenant_id}'.")

    if payload.modo != "Base de Conhecimento":
        _endpoint_nao_implementado(f"POST /chat (modo='{payload.modo}')")

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


class RenomearConversaRequest(BaseModel):
    tenant_id: str
    usuario_id: str
    novo_titulo: str


@app.patch("/conversas/{conversa_id}")
def renomear_conversa_endpoint(conversa_id: str, payload: RenomearConversaRequest) -> Dict[str, Any]:
    conversas = carregar_conversas(payload.tenant_id, payload.usuario_id)
    sucesso = renomear_conversa(conversas, conversa_id, payload.novo_titulo)
    if not sucesso:
        raise HTTPException(status_code=404, detail=f"Conversa '{conversa_id}' não encontrada ou título vazio.")
    salvar_conversas(payload.tenant_id, payload.usuario_id, conversas)
    return next(c for c in conversas if c["id"] == conversa_id)


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
async def upload_documento(tenant_id: str, arquivo: UploadFile = File(...)) -> Dict[str, Any]:
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
def deletar_documento(nome_arquivo: str, tenant_id: str) -> Dict[str, str]:
    removido = remover_documento(tenant_id, nome_arquivo)
    if not removido:
        raise HTTPException(status_code=404, detail=f"Documento '{nome_arquivo}' não encontrado para o tenant '{tenant_id}'.")
    return {"status": "removido"}


# ─────────────────────────────────────────────────────────────────────────────
# ANÁLISE DE DADOS (upload de planilha) (stub)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/planilha/upload")
def upload_planilha(tenant_id: str, conversation_id: str):
    _endpoint_nao_implementado("POST /planilha/upload")


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
