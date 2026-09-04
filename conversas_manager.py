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
from typing import Any, Dict, List, Optional

from utils_visual import hex_to_rgb

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


def clean_text_for_pdf(text: str) -> str:
    """Normaliza caracteres tipográficos especiais e remove não-latin1 para exportação em PDF."""
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "•": "*",
        "…": "...",
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    return "".join(c for c in text if ord(c) <= 255)


def formatar_conversa_txt(
    messages: List[Dict[str, Any]],
    config: Dict[str, Any],
    tenant_id: Optional[str] = None,
    usuario_nome: Optional[str] = None,
    conversa_titulo: Optional[str] = None
) -> str:
    """Formata o histórico de mensagens de uma conversa em texto plano para exportação."""
    if tenant_id is not None:
        messages = [m for m in messages if m.get("tenant_id") == tenant_id]

    data_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    linhas = [
        "==================================================",
        f"{config['nome'].upper()} - HISTÓRICO DE CONVERSA",
    ]
    if usuario_nome:
        linhas.append(f"Usuário: {usuario_nome.title()}")
    if conversa_titulo:
        linhas.append(f"Conversa: {conversa_titulo}")
    linhas.extend([
        f"Exportado em: {data_str}",
        "==================================================\n"
    ])
    for msg in messages:
        role = msg.get("role", "user")
        mode = msg.get("mode", "")
        content = msg.get("content", "")

        if role == "user":
            linhas.append(f"[USUÁRIO]:\n{content}\n")
        else:
            header = f"[IA - {mode}]" if mode else "[IA]"
            linhas.append(f"{header}:\n{content}\n")
        linhas.append("-" * 50 + "\n")

    return "\n".join(linhas)


def gerar_conversa_pdf(
    messages: List[Dict[str, Any]],
    config: Dict[str, Any],
    tenant_id: Optional[str] = None,
    usuario_nome: Optional[str] = None,
    conversa_titulo: Optional[str] = None
) -> Optional[bytes]:
    """Gera o histórico de mensagens de uma conversa como PDF (fpdf2). Retorna None se fpdf2 ausente."""
    if tenant_id is not None:
        messages = [m for m in messages if m.get("tenant_id") == tenant_id]

    try:
        from fpdf import FPDF
    except ImportError:
        return None

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, clean_text_for_pdf(f"{config['nome']} - Histórico de Conversa"), align="C")
    pdf.ln(8)

    if usuario_nome or conversa_titulo:
        pdf.set_font("Helvetica", style="B", size=10)
        parts = []
        if usuario_nome:
            parts.append(f"Usuario: {usuario_nome.title()}")
        if conversa_titulo:
            parts.append(f"Conversa: {conversa_titulo}")
        pdf.cell(0, 6, clean_text_for_pdf(" | ".join(parts)), align="C")
        pdf.ln(6)

    pdf.set_font("Helvetica", style="I", size=9)
    data_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.cell(0, 6, clean_text_for_pdf(f"Exportado em: {data_str}"), align="C")
    pdf.ln(8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    cor_p = hex_to_rgb(config["cor_primaria"])
    cor_s = hex_to_rgb(config["cor_secundaria"])

    for msg in messages:
        role = msg.get("role", "user")
        mode = msg.get("mode", "")
        content = msg.get("content", "")

        if role == "user":
            header_text = "USUÁRIO:"
            pdf.set_font("Helvetica", style="B", size=11)
            pdf.set_text_color(*cor_p)
        else:
            header_text = f"IA ({mode}):" if mode else "IA:"
            pdf.set_font("Helvetica", style="B", size=11)
            pdf.set_text_color(*cor_s)

        pdf.multi_cell(0, 6, clean_text_for_pdf(header_text))
        pdf.ln(2)

        pdf.set_font("Helvetica", style="", size=10)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 5, clean_text_for_pdf(content))
        pdf.ln(6)

    return bytes(pdf.output())

