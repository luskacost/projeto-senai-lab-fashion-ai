# -*- coding: utf-8 -*-
"""
Módulo para gerenciamento e persistência de conversas do usuário.

===============================================================================
NOTA DE SEGURANÇA IMPORTANTE:
Este mecanismo de identificação por nome (st.session_state.usuario_nome) é apenas
uma identificação por conveniência e UX, NÃO uma autenticação real com senha.
Qualquer pessoa que souber ou adivinhar o nome de outro usuário poderá acessar
o histórico de conversas associado a esse nome.
Para dados sensíveis ou ambientes de produção crítica, recomenda-se atualizar
este sistema para autenticação robusta (ex: Login com Senha / OAuth / SSO).
===============================================================================
"""

import os
import json
import uuid
import re
from datetime import datetime

DIRETORIO_CONVERSAS = os.path.join("tenant_data", "conversas")

def carregar_conversas(tenant_id: str, usuario_id: str) -> list:
    """
    Lê o arquivo de conversas do usuário (tenant_data/conversas/{tenant_id}_{usuario_id}.json).
    Cria a pasta tenant_data/conversas/ se não existir.
    Retorna a lista de conversas salvas, cada uma no formato:
    {"id": str, "titulo": str, "mensagens": list, "criado_em": str, "atualizado_em": str}.
    Se o arquivo não existir ou estiver corrompido, retorna lista vazia (nunca quebra o app).
    """
    try:
        os.makedirs(DIRETORIO_CONVERSAS, exist_ok=True)
        caminho_arquivo = os.path.join(DIRETORIO_CONVERSAS, f"{tenant_id}_{usuario_id}.json")
        if os.path.exists(caminho_arquivo):
            with open(caminho_arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        return []
    except Exception:
        # Garante resiliência: se o arquivo estiver corrompido ou houver erro de I/O, não quebra a aplicação
        return []

def salvar_conversas(tenant_id: str, usuario_id: str, conversas: list):
    """
    Sobrescreve o arquivo JSON com a lista completa atualizada de conversas do usuário.
    """
    try:
        os.makedirs(DIRETORIO_CONVERSAS, exist_ok=True)
        caminho_arquivo = os.path.join(DIRETORIO_CONVERSAS, f"{tenant_id}_{usuario_id}.json")
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(conversas, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def criar_nova_conversa() -> dict:
    """
    Retorna uma nova estrutura de conversa vazia com id gerado via str(uuid.uuid4()),
    titulo inicial "Nova conversa", mensagens: [], timestamps atuais em formato ISO.
    """
    agora = datetime.now().isoformat()
    return {
        "id": str(uuid.uuid4()),
        "titulo": "Nova conversa",
        "mensagens": [],
        "criado_em": agora,
        "atualizado_em": agora
    }

def gerar_titulo_conversa(primeira_mensagem: str) -> str:
    """
    Trunca a primeira mensagem do usuário para no máximo 40 caracteres (adicionando "..." se cortado)
    para servir de título provisório, sem precisar de chamada extra à API.
    """
    if not primeira_mensagem:
        return "Nova conversa"
    
    # Remove quebras de linha e espaços duplos
    texto_limpo = re.sub(r'\s+', ' ', primeira_mensagem).strip()
    
    if len(texto_limpo) > 40:
        return texto_limpo[:40].strip() + "..."
    return texto_limpo

def renomear_conversa(conversas: list, conversa_id: str, novo_titulo: str) -> bool:
    """
    Atualiza o título de uma conversa específica pelo ID na lista informada.
    """
    novo_titulo_limpo = novo_titulo.strip()
    if not novo_titulo_limpo:
        return False
        
    for conv in conversas:
        if conv.get("id") == conversa_id:
            conv["titulo"] = novo_titulo_limpo
            conv["atualizado_em"] = datetime.now().isoformat()
            return True
    return False

