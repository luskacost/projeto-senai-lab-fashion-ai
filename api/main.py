# -*- coding: utf-8 -*-
"""Scaffold da API do SenaiLabFashionAssistant (Fase 3, Passo 16).

Casca HTTP em FastAPI para expor a lógica de negócio já existente (rag_manager.py,
conversas_manager.py, analise_dados.py, tenant_config.py) sem depender do Streamlit.
Estrutura de rotas conforme `API_CONTRATO.md`; endpoints marcados como stub ainda não
têm lógica implementada (ver roadmap: cada um é implementado em uma sessão futura).

Rodar localmente: uvicorn api.main:app --reload
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from tenant_config import TENANT_CONFIG, carregar_config_tenant, salvar_config_tenant

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
def admin_login(payload: AdminLoginRequest):
    _endpoint_nao_implementado("POST /admin/login")


# ─────────────────────────────────────────────────────────────────────────────
# CHAT (stub — Passo 17: implementar primeiro só "Base de Conhecimento")
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    tenant_id: str
    conversation_id: Optional[str] = None
    modo: str
    perfil_usuario: Optional[str] = None
    mensagem: str


@app.post("/chat")
def chat(payload: ChatRequest):
    _endpoint_nao_implementado("POST /chat")


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSAS (stub)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/conversas")
def listar_conversas(tenant_id: str, usuario_id: str):
    _endpoint_nao_implementado("GET /conversas")


class NovaConversaRequest(BaseModel):
    tenant_id: str
    usuario_id: str


@app.post("/conversas")
def criar_conversa(payload: NovaConversaRequest):
    _endpoint_nao_implementado("POST /conversas")


class RenomearConversaRequest(BaseModel):
    tenant_id: str
    usuario_id: str
    novo_titulo: str


@app.patch("/conversas/{conversa_id}")
def renomear_conversa_endpoint(conversa_id: str, payload: RenomearConversaRequest):
    _endpoint_nao_implementado("PATCH /conversas/{conversa_id}")


@app.delete("/conversas/{conversa_id}")
def deletar_conversa(conversa_id: str, tenant_id: str, usuario_id: str):
    _endpoint_nao_implementado("DELETE /conversas/{conversa_id}")


@app.get("/conversas/{conversa_id}/export")
def exportar_conversa(conversa_id: str, tenant_id: str, formato: str = "txt"):
    _endpoint_nao_implementado("GET /conversas/{conversa_id}/export")


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENTOS (Base de Conhecimento) (stub)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/documentos")
def listar_documentos(tenant_id: str):
    _endpoint_nao_implementado("GET /documentos")


@app.post("/documentos/upload")
def upload_documento(tenant_id: str):
    _endpoint_nao_implementado("POST /documentos/upload")


@app.delete("/documentos/{nome_arquivo}")
def deletar_documento(nome_arquivo: str, tenant_id: str):
    _endpoint_nao_implementado("DELETE /documentos/{nome_arquivo}")


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
def debug_rag(tenant_id: str):
    _endpoint_nao_implementado("GET /debug/rag")
