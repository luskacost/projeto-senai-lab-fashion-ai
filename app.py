# -*- coding: utf-8 -*-
# Importando os pacotes necessarios para o sistema
import streamlit as st
import os
from groq import Groq
from datetime import datetime
import json
import urllib.parse
import hashlib
import re
from tenant_config import TENANT_CONFIG, PERFIS_USUARIO
from usage_tracker import carregar_uso_do_dia, incrementar_uso, verificar_limite
from moderacao import validar_prompt_imagem
from resposta_cache import obter_resposta_cacheada, salvar_resposta_cache
from logger_config import obter_logger
from utils_visual import hex_to_rgb, calcular_cor_texto_contraste
from conversas_manager import carregar_conversas, salvar_conversas, criar_nova_conversa, gerar_titulo_conversa, renomear_conversa
from analise_dados import carregar_planilha, gerar_resumo_estatistico, responder_pergunta_sobre_dados
from rag_manager import (
    extrair_documento,
    EXTENSOES_SUPORTADAS,
    extrair_texto_pdf,
    indexar_documento,
    buscar_contexto_relevante,
    listar_documentos_indexados,
    remover_documento,
    formatar_bloco_debug_rag,
    obter_ultimo_rag_debug,
    RAG_DEBUG
)

# Tenta carregar variáveis do arquivo .env na raiz do projeto (desenvolvimento local)
try:
    # pyrefly: ignore [missing-import]
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# LEITURA CENTRALIZADA DE SEGREDOS POR TENANT (ST.SECRETS OU ENV VARS)
# ─────────────────────────────────────────────────────────────────────────────
def obter_secret_tenant(tenant_id: str, chave: str, default: str = "") -> str:
    """Obtém uma credencial/secret por tenant com fallback seguro para variáveis de ambiente.

    1. Tenta obter de st.secrets[tenant_id][chave]
    2. Fallback: tenta obter da variável de ambiente {TENANT_ID}_{CHAVE} em maiúsculas (ex: SENAI_LABFASHION_GROQ_API_KEY)
    3. Retorna 'default' se não encontrada em nenhuma fonte.
    """
    # 1. Tentar ler do st.secrets (suporta dict e AttrDict do Streamlit)
    try:
        if hasattr(st, "secrets") and st.secrets is not None:
            tenant_sec = st.secrets.get(tenant_id, {})
            val = ""
            if isinstance(tenant_sec, dict):
                val = tenant_sec.get(chave, "")
            else:
                val = getattr(tenant_sec, chave, "")
            if val:
                return str(val)
    except Exception:
        pass

    # 2. Fallback: Tentar ler de variável de ambiente (ex: SENAI_LABFASHION_GROQ_API_KEY)
    env_var_name = f"{tenant_id}_{chave}".upper()
    env_val = os.environ.get(env_var_name, "")
    if env_val:
        return str(env_val)

    # 3. Default (caso ausente nas duas fontes)
    return default

# ─────────────────────────────────────────────────────────────────────────────
# IDENTIFICAÇÃO E VALIDAÇÃO DO TENANT VIA QUERY PARAMETER
# Comportamento:
# 1. Sem parâmetro (ex: http://localhost:8501/): fallback automático para "senai_labfashion".
# 2. Parâmetro válido (ex: http://localhost:8501/?tenant=senai_labfashion): carrega as configurações do tenant "senai_labfashion".
# 3. Parâmetro inválido (ex: http://localhost:8501/?tenant=outro): exibe aviso amigável via st.error e encerra com st.stop().
# ─────────────────────────────────────────────────────────────────────────────
def carregar_config_tenant(tenant_id: str, config_default: dict) -> dict:
    """Carrega as configurações do tenant, fazendo merge com o arquivo local em tenant_data/{tenant_id}.json se existir."""
    config_final = dict(config_default)
    config_final["modos"] = dict(config_default.get("modos", {}))
    config_final["descricoes_modos"] = dict(config_default.get("descricoes_modos", {}))
    config_final["descricoes_detalhadas"] = dict(config_default.get("descricoes_detalhadas", {}))
    config_final["perguntas_rapidas"] = dict(config_default.get("perguntas_rapidas", {}))
    config_final["modo_padrao_por_perfil"] = dict(config_default.get("modo_padrao_por_perfil", {}))
    config_final["perguntas_por_perfil"] = dict(config_default.get("perguntas_por_perfil", {}))
    
    arquivo_custom = os.path.join("tenant_data", f"{tenant_id}.json")
    if os.path.exists(arquivo_custom):
        try:
            with open(arquivo_custom, "r", encoding="utf-8") as f:
                custom_data = json.load(f)
                if isinstance(custom_data, dict):
                    # Sobrescreve os campos autorizados de aparência e personalização
                    for campo in [
                        "nome", "cor_primaria", "cor_secundaria", "logo_url",
                        "tema", "fonte", "favicon_url", "mensagem_boas_vindas"
                    ]:
                        if campo in custom_data:
                            config_final[campo] = custom_data[campo]
        except Exception as e:
            logger = obter_logger(tenant_id)
            logger.error(f"Erro ao carregar dados customizados do tenant {tenant_id}: {e}", exc_info=True)
            pass
            
    return config_final

def obter_perguntas_rapidas(config: dict, modo: str, perfil: str = None) -> list:
    """Obtém as perguntas rápidas para o modo e perfil informados, com fallback para as perguntas padrão do modo."""
    if perfil and "perguntas_por_perfil" in config:
        perguntas_perfil = config["perguntas_por_perfil"].get(perfil, {})
        if modo in perguntas_perfil and perguntas_perfil[modo]:
            return perguntas_perfil[modo]
    return config.get("perguntas_rapidas", {}).get(modo, [])

def salvar_config_tenant(tenant_id: str, dados_custom: dict):
    """Salva os dados de customização do tenant no arquivo JSON correspondente."""
    os.makedirs("tenant_data", exist_ok=True)
    arquivo_custom = os.path.join("tenant_data", f"{tenant_id}.json")
    with open(arquivo_custom, "w", encoding="utf-8") as f:
        json.dump(dados_custom, f, ensure_ascii=False, indent=2)

tenant_id = st.query_params.get("tenant", "senai_labfashion")

if tenant_id not in TENANT_CONFIG:
    st.error(f"⚠️ O tenant '{tenant_id}' não foi encontrado nas configurações do sistema. Verifique a URL acessada.")
    st.stop()

config = carregar_config_tenant(tenant_id, TENANT_CONFIG[tenant_id])

favicon_icon = config.get("favicon_url") or "🪡"

# Configura a pagina do streamlit com titulo, icone, layout e estado inicial da sidebar
st.set_page_config(
    page_title=config["nome"],
    page_icon=favicon_icon,
    layout="wide",
    initial_sidebar_state="expanded"
)


def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

# Funções auxiliares para exportar conversas
def clean_text_for_pdf(text):
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
        "\u2022": "*",
        "\u2026": "...",
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    return "".join(c for c in text if ord(c) <= 255)

def formatar_conversa_txt(messages, tenant_id=None, usuario_nome=None, conversa_titulo=None):
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

def gerar_conversa_pdf(messages, tenant_id=None, usuario_nome=None, conversa_titulo=None):
    if tenant_id is not None:
        messages = [m for m in messages if m.get("tenant_id") == tenant_id]
        
    try:
        from fpdf import FPDF
    except ImportError:
        return None
        
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(0, 10, clean_text_for_pdf(f"{config['nome']} - Histórico de Conversa"), align="C")
    pdf.ln(8)
    
    # Subtitle with user & conversation title
    if usuario_nome or conversa_titulo:
        pdf.set_font("Helvetica", style="B", size=10)
        parts = []
        if usuario_nome:
            parts.append(f"Usuario: {usuario_nome.title()}")
        if conversa_titulo:
            parts.append(f"Conversa: {conversa_titulo}")
        pdf.cell(0, 6, clean_text_for_pdf(" | ".join(parts)), align="C")
        pdf.ln(6)

    # Subtitle with date
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
        pdf.set_text_color(40, 40, 40) # Dark gray
        pdf.multi_cell(0, 5, clean_text_for_pdf(content))
        pdf.ln(6)
        
    return bytes(pdf.output())

# Inicialização de usuário via query parameter ?usuario=... (se disponível)
if 'usuario_nome' not in st.session_state or not st.session_state.usuario_nome:
    param_usr = st.query_params.get("usuario", "")
    if param_usr:
        nome_limpo = re.sub(r'\s+', ' ', param_usr.strip()).lower()
        if nome_limpo:
            st.session_state.usuario_nome = nome_limpo
            st.session_state.usuario_id = hashlib.md5(nome_limpo.encode('utf-8')).hexdigest()[:12]
            st.query_params["usuario"] = nome_limpo

if 'usuario_nome' not in st.session_state:
    st.session_state.usuario_nome = None
if 'usuario_id' not in st.session_state:
    st.session_state.usuario_id = None
if 'conversas' not in st.session_state:
    st.session_state.conversas = []
if 'conversa_atual_id' not in st.session_state:
    st.session_state.conversa_atual_id = None
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pending_image_request' not in st.session_state:
    st.session_state.pending_image_request = None
if 'perfil_usuario' not in st.session_state:
    st.session_state.perfil_usuario = None
if 'estilo_croqui' not in st.session_state:
    st.session_state.estilo_croqui = "🎨 Ilustração de Moda"
if 'df_analise_atual' not in st.session_state:
    st.session_state.df_analise_atual = None
if 'resumo_estatistico_atual' not in st.session_state:
    st.session_state.resumo_estatistico_atual = None
if 'arquivo_analise_carregado' not in st.session_state:
    st.session_state.arquivo_analise_carregado = None

# Carrega conversas do usuário se ele já se identificou
if st.session_state.get('usuario_id'):
    if not st.session_state.conversas:
        st.session_state.conversas = carregar_conversas(tenant_id, st.session_state.usuario_id)
    
    # Se conversa_atual_id não estiver definido ou não for válida, inicializa uma nova conversa vazia
    if not st.session_state.conversa_atual_id or not any(c["id"] == st.session_state.conversa_atual_id for c in st.session_state.conversas):
        nova_conv = criar_nova_conversa()
        st.session_state.conversas.append(nova_conv)
        st.session_state.conversa_atual_id = nova_conv["id"]

def obter_conversa_atual():
    if not st.session_state.get("conversas") or not st.session_state.get("conversa_atual_id"):
        return None
    for c in st.session_state.conversas:
        if c["id"] == st.session_state.conversa_atual_id:
            return c
    return None

def sincronizar_mensagens_conversa_atual():
    conv = obter_conversa_atual()
    if conv is not None:
        st.session_state.messages = conv.get("mensagens", [])
    else:
        st.session_state.messages = []

def persistir_mensagem_atualizada():
    conv = obter_conversa_atual()
    if conv is not None:
        conv["mensagens"] = list(st.session_state.messages)
        conv["atualizado_em"] = datetime.now().isoformat()
        if conv.get("titulo") == "Nova conversa":
            primeira_user_msg = next((m.get("content", "") for m in conv["mensagens"] if m.get("role") == "user"), "")
            if primeira_user_msg:
                conv["titulo"] = gerar_titulo_conversa(primeira_user_msg)
        conversas_validas = [c for c in st.session_state.conversas if len(c.get("mensagens", [])) > 0]
        if st.session_state.get("usuario_id"):
            salvar_conversas(tenant_id, st.session_state.usuario_id, conversas_validas)

# Mantém st.session_state.messages sincronizado com a conversa atual
sincronizar_mensagens_conversa_atual()

def selecionar_perfil(p_id: str):
    """Callback executado ao clicar no botão de perfil. Define o perfil e o modo padrão ANTES da renderização do widget na sidebar."""
    st.session_state.perfil_usuario = p_id
    modo_padrao = config.get("modo_padrao_por_perfil", {}).get(p_id)
    if modo_padrao and modo_padrao in config.get("modos", {}):
        st.session_state.modo_selecionado = modo_padrao

def resetar_perfil():
    """Callback executado ao clicar em 'Trocar perfil'."""
    st.session_state.perfil_usuario = None

def resetar_usuario():
    """Callback executado ao clicar em 'Não é você? Trocar usuário'."""
    st.session_state.usuario_nome = None
    st.session_state.usuario_id = None
    st.session_state.conversas = []
    st.session_state.conversa_atual_id = None
    st.session_state.perfil_usuario = None
    st.session_state.messages = []
    st.session_state.pending_image_request = None
    st.session_state.df_analise_atual = None
    st.session_state.resumo_estatistico_atual = None
    st.session_state.arquivo_analise_carregado = None
    if "usuario" in st.query_params:
        try:
            del st.query_params["usuario"]
        except Exception:
            st.query_params["usuario"] = ""

cor_primaria = config.get("cor_primaria", "#0047AB")
cor_secundaria = config.get("cor_secundaria", "#F47B20")
cor_texto_primaria = calcular_cor_texto_contraste(cor_primaria)
cor_texto_secundaria = calcular_cor_texto_contraste(cor_secundaria)

tema = config.get("tema", "claro")
is_dark = (tema == "escuro")

fonte = config.get("fonte", "Inter")
if fonte not in ["Inter", "Roboto", "Poppins"]:
    fonte = "Inter"

# Variáveis dinâmicas de cores baseadas no tema Claro vs Escuro
bg_app = "#0E1117" if is_dark else "#FFFFFF"
bg_sidebar = "#1A1D24" if is_dark else "#F5F5F5"
text_color = "#E0E0E0" if is_dark else "#2D2D2D"
title_color = "#FFFFFF" if is_dark else "#000000"
bg_card = "#1E222A" if is_dark else "#FAFAFA"
border_card = "#2D323E" if is_dark else "#E0E0E0"

bg_chat_user = "#1B263B" if is_dark else "#F0F7FF"
bg_chat_ia = "#2B1D14" if is_dark else "#FFF5EB"
bg_input = "#1E222A" if is_dark else "#FAFAFA"
text_input = "#FFFFFF" if is_dark else "#000000"

bg_sidebar_btn = "#262A33" if is_dark else "#FFFFFF"
text_sidebar_btn = "#E0E0E0" if is_dark else "#2D2D2D"

bg_onboarding = "#1E222A" if is_dark else "#F8F9FA"
bg_step1 = "#1B263B" if is_dark else "#F0F7FF"
bg_step2 = "#2B1D14" if is_dark else "#FFF5EB"
bg_step3 = "#1E222A" if is_dark else "#F8F9FA"

border_step1 = "#2C4A6F" if is_dark else "#BEE3F8"
border_step2 = "#5A3A1E" if is_dark else "#FBD38D"
border_step3 = "#2D323E" if is_dark else "#E2E8F0"

text_subtle = "#A0A0A0" if is_dark else "#555555"

FALLBACK_BOAS_VINDAS = "O Senai LabFashion IA é o seu copiloto virtual especializado para responder dúvidas técnicas de modelagem, costura, tecidos, tendências e gerar conceitos visuais de croquis."

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family={fonte}:wght@400;500;600;700;800;900&display=swap');
    
    /* Aplica a tipografia customizada a todos os elementos de texto do Streamlit */
    .stApp, .stApp p, .stApp span, .stApp div, .stApp h1, .stApp h2, .stApp h3, .stApp button, .stApp input, .stApp textarea, .stApp label, .stApp select, .stMarkdown {{
        font-family: '{fonte}', sans-serif !important;
    }}
    
    /* Preserva os ícones de sistema do Streamlit para evitar a exibição de texto cru de ligaduras (ex: keyboard_double_arrow_right) */
    .stApp [data-testid*="Icon"],
    .stApp [data-testid*="icon"],
    .stApp [data-testid="stSidebarCollapseButton"] *,
    .stApp [data-testid="stSidebarExpandButton"] *,
    .stApp span[class*="material"],
    .stApp i[class*="material"],
    .stApp [class*="MaterialSymbols"] {{
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
    }}



    
    /* Fundo principal */
    .stApp {{
        background-color: {bg_app};
        color: {text_color};
    }}
    
    /* Sidebar */
    .stSidebar {{
        background-color: {bg_sidebar};
        border-right: 2px solid {cor_primaria};
    }}
    
    /* Títulos e textos */
    h1, h2, h3, .stTitle {{
        color: {title_color};
        font-weight: 700;
    }}
    
    .stMarkdown {{
        color: {text_color};
    }}
    
    /* BOTÕES PRINCIPAIS */
    .stButton > button {{
        background-color: {cor_primaria};
        color: {cor_texto_primaria};
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }}
    
    .stButton > button:hover {{
        background-color: {cor_primaria};
        color: {cor_texto_primaria};
        box-shadow: 0 4px 8px rgba(0, 71, 171, 0.3);
        transform: translateY(-2px);
    }}
    
    /* BOTÕES SECUNDÁRIOS */
    .stButton > button.secondary {{
        background-color: {cor_secundaria};
        color: {cor_texto_secundaria};
    }}
    
    .stButton > button.secondary:hover {{
        background-color: {cor_secundaria};
        color: {cor_texto_secundaria};
        box-shadow: 0 4px 8px rgba(244, 123, 32, 0.3);
        transform: translateY(-2px);
    }}
    
    /* Inputs e campos de texto */
    .stTextInput > div > div > input, .stTextArea > div > div > textarea {{
        background-color: {bg_input};
        border: 2px solid {border_card};
        border-radius: 4px;
        color: {text_input};
        transition: all 0.3s ease;
    }}
    
    .stTextInput > div > div > input:focus, .stTextArea > div > div > textarea:focus {{
        border-color: {cor_primaria};
        box-shadow: 0 0 0 3px rgba(0, 71, 171, 0.1);
    }}
    
    /* Chat messages */
    .stChatMessage {{
        background-color: {bg_card};
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
        border-left: 4px solid {cor_primaria};
    }}
    
    .stChatMessage.user {{
        background-color: {bg_chat_user};
        border-left-color: {cor_primaria};
    }}
    
    .stChatMessage.IA {{
        background-color: {bg_chat_ia};
        border-left-color: {cor_secundaria};
    }}
    
    /* Links */
    a {{
        color: {cor_primaria};
        text-decoration: none;
        transition: color 0.3s ease;
    }}
    
    a:hover {{
        color: {cor_secundaria};
        text-decoration: underline;
    }}
    
    /* Badges e labels */
    .badge-senai {{
        background-color: {cor_primaria};
        color: {cor_texto_primaria};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }}
    
    .badge-lab {{
        background-color: {cor_secundaria};
        color: {cor_texto_secundaria};
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
    }}
    
    /* Separadores */
    hr {{
        border: 0;
        border-top: 2px solid {border_card};
        margin: 20px 0;
    }}
    
    /* Cards e containers */
    .css-1r6slb0 {{
        background-color: {bg_card};
        border-radius: 8px;
        padding: 20px;
        border: 1px solid {border_card};
        transition: all 0.3s ease;
    }}
    
    .css-1r6slb0:hover {{
        box-shadow: 0 4px 12px rgba(0, 71, 171, 0.1);
        border-color: {cor_primaria};
    }}
    
    /* Spinner/loading */
    .stSpinner > div {{
        border-color: {cor_primaria} !important;
    }}
    
    /* Alertas e mensagens */
    .stAlert {{
        border-radius: 4px;
        border-left: 4px solid {cor_primaria};
    }}
    
    .stAlert.info {{
        border-left-color: {cor_primaria};
    }}
    
    .stAlert.success {{
        border-left-color: #28A745;
    }}
    
    .stAlert.warning {{
        border-left-color: {cor_secundaria};
    }}
    
    /* LOGO ESTILIZADA */
    .labfashion-logo {{
        display: flex;
        align-items: center;
        gap: 5px;
        font-size: 2rem;
        font-weight: 900;
        letter-spacing: -0.5px;
    }}
    
    .labfashion-logo .senai {{
        color: {cor_primaria};
    }}
    
    .labfashion-logo .lab {{
        color: {cor_secundaria};
        font-weight: 900;
    }}
    
    .labfashion-logo .fashion {{
        color: {title_color};
        font-weight: 900;
    }}
    
    /* Badge do Assistente */
    .IA-badge {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        background: linear-gradient(135deg, {cor_primaria}, {cor_secundaria});
        color: {cor_texto_primaria};
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }}
    
    /* Menu lateral */
    .sidebar-title {{
        color: {cor_primaria};
        font-weight: 800;
        font-size: 1.2rem;
        margin-bottom: 10px;
    }}
    
    .sidebar-subtitle {{
        color: {cor_secundaria};
        font-weight: 600;
        font-size: 0.9rem;
    }}
    
    /* Botões de ação rápidos */
    .quick-action {{
        background-color: {bg_card};
        border: 2px solid {border_card};
        border-radius: 8px;
        padding: 10px;
        transition: all 0.3s ease;
    }}
    
    .quick-action:hover {{
        border-color: {cor_primaria};
        background-color: {bg_chat_user};
    }}
    
    /* Estilo para botões dentro da sidebar (perguntas rápidas e ações) */
    .stSidebar .stButton > button {{
        background-color: {bg_sidebar_btn};
        color: {text_sidebar_btn};
        border: 1px solid {border_card};
        border-radius: 6px;
        padding: 0.5rem 0.8rem;
        font-weight: 500;
        font-size: 0.85rem;
        text-align: left;
        display: block;
        width: 100%;
        transition: all 0.3s ease;
        white-space: normal;
        word-wrap: break-word;
        height: auto;
    }}
    
    .stSidebar .stButton > button:hover {{
        background-color: {bg_chat_user};
        color: {cor_primaria};
        border-color: {cor_primaria};
        box-shadow: none;
        transform: none;
    }}
</style>
""", unsafe_allow_html=True)
# ─────────────────────────────────────────────────────────────────────────────
# FERRAMENTA LOCAL: Geração de imagem via Pollinations.ai (sem chave de API)
# ─────────────────────────────────────────────────────────────────────────────
SUFIXO_TECNICO = ", fashion technical flat sketch, vector line art style, black and white line drawing, no human body, no color rendering, garment schematic, white background, technical fashion illustration"

# IMPORTANTE: validar_prompt_imagem() deve sempre rodar antes desta função, independente do provedor de imagem usado (Pollinations, DALL-E, Gemini, etc.).
def chamar_api_geracao_imagem(prompt_visual: str) -> str:
    """Retorna a URL de uma imagem gerada pela Pollinations.ai a partir do prompt."""
    prompt_encoded = urllib.parse.quote(prompt_visual)
    return f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=512&height=768&nologo=true"

# ─────────────────────────────────────────────────────────────────────────────
# EXECUTOR DE FERRAMENTAS LOCAIS
# ─────────────────────────────────────────────────────────────────────────────
def executar_ferramenta_local(nome_ferramenta: str, argumentos: dict) -> str:
    """Chama a função local correspondente ao nome_ferramenta e retorna o resultado."""
    if nome_ferramenta == "gerar_imagem_croqui":
        prompt_visual = argumentos.get("prompt_visual", "")
        estilo = st.session_state.get("estilo_croqui", "🎨 Ilustração de Moda")
        if estilo == "📐 Desenho Técnico (Flat Sketch)":
            prompt_visual = f"{prompt_visual}{SUFIXO_TECNICO}, front view"
        return chamar_api_geracao_imagem(prompt_visual)
    return f"[Erro] Ferramenta '{nome_ferramenta}' não reconhecida. Nenhuma ação foi executada."

# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÃO PRINCIPAL DE CHAMADA AO AGENTE (com suporte a tool calling)
# ─────────────────────────────────────────────────────────────────────────────
def chamar_agente(client, agente_config: dict, messages_for_api: list) -> tuple:
    """Chama a API da Groq com suporte a tool calling quando o agente tiver tools.

    Se a ferramenta 'gerar_imagem_croqui' for detectada, retorna um sinal de confirmação pendente
    (pendente_dados) contendo os argumentos e o ID da chamada para aprovação prévia do usuário.
    """
    tools = agente_config.get("tools")
    imagem_url = None

    try:
        if tools is not None:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model="openai/gpt-oss-20b",
                temperature=0.7,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto",
            )
        else:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model="openai/gpt-oss-20b",
                temperature=0.7,
                max_tokens=2048,
            )
    except Exception as api_err:
        err_str = str(api_err).lower()
        if tools is not None and any(kw in err_str for kw in ["tool", "search", "not supported", "invalid"]):
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model="openai/gpt-oss-20b",
                temperature=0.7,
                max_tokens=2048,
            )
            return primeira_resposta.choices[0].message.content, None, True, None
        raise

    message = primeira_resposta.choices[0].message

    if hasattr(message, "tool_calls") and message.tool_calls:
        # Verifica se o modelo escolheu especificamente a ferramenta de croqui
        tem_gerar_croqui = any(tc.function.name == "gerar_imagem_croqui" for tc in message.tool_calls)

        if tem_gerar_croqui:
            croqui_tc = next(tc for tc in message.tool_calls if tc.function.name == "gerar_imagem_croqui")
            try:
                argumentos = json.loads(croqui_tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                argumentos = {}

            prompt_visual = argumentos.get("prompt_visual", "")
            resumo_confirmacao = argumentos.get("resumo_confirmacao", "")

            assistant_msg = {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }

            pendente_dados = {
                "tool_call_id": croqui_tc.id,
                "nome_ferramenta": "gerar_imagem_croqui",
                "argumentos": argumentos,
                "prompt_visual": prompt_visual,
                "resumo_confirmacao": resumo_confirmacao,
                "assistant_message": assistant_msg,
                "messages_for_api": list(messages_for_api),
                "estilo_croqui": st.session_state.get("estilo_croqui", "🎨 Ilustração de Moda"),
            }
            return None, None, False, pendente_dados

        # Para outras ferramentas (ex: web_search), executa normalmente
        messages_for_api.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        })

        for tool_call in message.tool_calls:
            try:
                argumentos = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                argumentos = {}
            resultado = executar_ferramenta_local(tool_call.function.name, argumentos)

            if resultado.startswith("https://image.pollinations.ai"):
                imagem_url = resultado

            messages_for_api.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(resultado),
            })

        segunda_resposta = client.chat.completions.create(
            messages=messages_for_api,
            model="openai/gpt-oss-20b",
            temperature=0.7,
            max_tokens=2048,
        )
        texto_final = segunda_resposta.choices[0].message.content
        return texto_final, imagem_url, False, None

    return message.content, imagem_url, False, None

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# BARRA LATERAL (SIDEBAR)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
  st.title(f'🪡 {config["nome"]}')
  st.markdown(' Assistente de IA especializado em moda e têxtil.')

  if st.session_state.get("usuario_nome"):
      st.markdown("---")
      st.markdown(f"👤 **Olá, {st.session_state.usuario_nome.title()}!**")
      st.button("Não é você? Trocar usuário", key="btn_trocar_usuario_side", on_click=resetar_usuario, use_container_width=True)

  if st.session_state.get("perfil_usuario"):
      st.markdown("---")
      perfil_info = PERFIS_USUARIO.get(st.session_state.perfil_usuario, {})
      nome_p = perfil_info.get("nome", st.session_state.perfil_usuario)
      icone_p = perfil_info.get("icone", "👤")
      st.markdown(f"**Perfil Ativo:** {icone_p} {nome_p}")
      st.button("🔄 Trocar perfil", key="btn_trocar_perfil_side", on_click=resetar_perfil, use_container_width=True)

  # Seção de Conversas Recentes (se o usuário já estiver identificado)
  if st.session_state.get("usuario_nome"):
      st.markdown("---")
      st.markdown("<div class='sidebar-title'>🕑 Conversas Recentes</div>", unsafe_allow_html=True)
      
      if st.button("➕ Nova conversa", key="btn_nova_conversa_side", use_container_width=True):
          nova_c = criar_nova_conversa()
          st.session_state.conversas.append(nova_c)
          st.session_state.conversa_atual_id = nova_c["id"]
          st.session_state.messages = []
          st.session_state.pending_image_request = None
          st.session_state.df_analise_atual = None
          st.session_state.resumo_estatistico_atual = None
          st.session_state.arquivo_analise_carregado = None
          st.rerun()
          
      conversas_ordenadas = sorted(
          st.session_state.conversas,
          key=lambda x: x.get("atualizado_em", ""),
          reverse=True
      )
      
      for conv in conversas_ordenadas:
          c_id = conv["id"]
          c_titulo = conv.get("titulo", "Nova conversa")
          is_atual = (c_id == st.session_state.get("conversa_atual_id"))
          
          col_conv, col_edit, col_del = st.columns([0.66, 0.17, 0.17])
          prefixo = "▶️ " if is_atual else "💬 "
          with col_conv:
              if st.button(f"{prefixo}{c_titulo}", key=f"btn_conv_select_{c_id}", use_container_width=True):
                  st.session_state.conversa_atual_id = c_id
                  st.session_state.messages = conv.get("mensagens", [])
                  st.session_state.pending_image_request = None
                  st.session_state.df_analise_atual = None
                  st.session_state.resumo_estatistico_atual = None
                  st.session_state.arquivo_analise_carregado = None
                  st.rerun()
          with col_edit:
              with st.popover("✏️", help="Renomear conversa"):
                  st.markdown("**Renomear conversa**")
                  novo_titulo_input = st.text_input("Novo título:", value=c_titulo, key=f"input_renomear_{c_id}")
                  if st.button("Salvar", key=f"btn_save_renomear_{c_id}", use_container_width=True):
                      if renomear_conversa(st.session_state.conversas, c_id, novo_titulo_input):
                          conversas_validas = [c for c in st.session_state.conversas if len(c.get("mensagens", [])) > 0]
                          if st.session_state.get("usuario_id"):
                              salvar_conversas(tenant_id, st.session_state.usuario_id, conversas_validas)
                          st.rerun()
                      else:
                          st.warning("Por favor, digite um título válido.")
          with col_del:
              with st.popover("🗑️", help="Excluir conversa"):
                  st.write(f"Excluir conversa?\n**{c_titulo}**")
                  if st.button("Sim, excluir", key=f"btn_confirm_del_{c_id}", use_container_width=True):
                      st.session_state.conversas = [c for c in st.session_state.conversas if c["id"] != c_id]
                      conversas_validas = [c for c in st.session_state.conversas if len(c.get("mensagens", [])) > 0]
                      if st.session_state.get("usuario_id"):
                          salvar_conversas(tenant_id, st.session_state.usuario_id, conversas_validas)
                      if st.session_state.conversa_atual_id == c_id:
                          if st.session_state.conversas:
                              st.session_state.conversa_atual_id = st.session_state.conversas[0]["id"]
                              st.session_state.messages = st.session_state.conversas[0].get("mensagens", [])
                          else:
                              nova_c = criar_nova_conversa()
                              st.session_state.conversas.append(nova_c)
                              st.session_state.conversa_atual_id = nova_c["id"]
                              st.session_state.messages = []
                      st.rerun()

  st.markdown("---")
  st.markdown("<div class='sidebar-title'>Modos de Assistente</div>", unsafe_allow_html=True)
  
  modos_lista = list(config["modos"].keys())
  idx_padrao = 0
  if "modo_selecionado" in st.session_state and st.session_state.modo_selecionado in modos_lista:
      idx_padrao = modos_lista.index(st.session_state.modo_selecionado)
  elif st.session_state.get("perfil_usuario"):
      m_padrao = config.get("modo_padrao_por_perfil", {}).get(st.session_state.perfil_usuario)
      if m_padrao in modos_lista:
          idx_padrao = modos_lista.index(m_padrao)

  modo_selecionado = st.selectbox(
      "Selecione o foco da conversa:",
      options=modos_lista,
      format_func=lambda x: config["descricoes_modos"][x],
      index=idx_padrao,
      key="modo_selecionado",
      help="Altere o comportamento e especialidade da IA"
  )
  
  st.markdown(config["descricoes_detalhadas"][modo_selecionado])
  st.markdown("---")

  if modo_selecionado == "Gerador de Croqui":
      st.markdown("<div class='sidebar-title'>Estilo de Croqui</div>", unsafe_allow_html=True)
      st.radio(
          "Selecione o estilo de visualização:",
          options=["🎨 Ilustração de Moda", "📐 Desenho Técnico (Flat Sketch)"],
          key="estilo_croqui",
          help="Escolha entre uma ilustração artística colorida ou um desenho técnico 2D com vistas frontal e traseira",
          label_visibility="collapsed"
      )
      st.markdown("---")

  st.markdown("<div class='sidebar-title'>Sugestões de Perguntas</div>", unsafe_allow_html=True)
  
  perguntas_sidebar = obter_perguntas_rapidas(config, modo_selecionado, st.session_state.get("perfil_usuario"))
  for idx, pergunta in enumerate(perguntas_sidebar):
      texto_puro = pergunta.split(maxsplit=1)[1] if len(pergunta.split()) > 1 else pergunta
      if st.button(pergunta, key=f"btn_side_{modo_selecionado}_{idx}", use_container_width=True):
          st.session_state.quick_question = texto_puro
          st.session_state.pending_image_request = None
          st.rerun()

  st.markdown("---")

  # Indicador de limite de uso diário do tenant
  uso_atual_side = carregar_uso_do_dia(tenant_id)
  limite_msg_side = config.get("limite_mensagens_dia", 200)
  limite_img_side = config.get("limite_imagens_dia", 30)
  st.caption(f"💬 Mensagens hoje: {uso_atual_side['mensagens']}/{limite_msg_side} · 🎨 Imagens hoje: {uso_atual_side['imagens']}/{limite_img_side}")

  st.markdown("---")

  # Obtém a chave da Groq via função centralizada (st.secrets ou env vars)
  groq_api_key = obter_secret_tenant(tenant_id, "GROQ_API_KEY")

  if st.button("Limpar Histórico de Conversa", use_container_width=True):
      st.session_state.messages = []
      conv_ativa = obter_conversa_atual()
      if conv_ativa:
          conv_ativa["mensagens"] = []
          conv_ativa["atualizado_em"] = datetime.now().isoformat()
          conversas_validas = [c for c in st.session_state.conversas if len(c.get("mensagens", [])) > 0]
          if st.session_state.get("usuario_id"):
              salvar_conversas(tenant_id, st.session_state.usuario_id, conversas_validas)
      st.session_state.pending_image_request = None
      st.session_state.df_analise_atual = None
      st.session_state.resumo_estatistico_atual = None
      st.session_state.arquivo_analise_carregado = None
      st.rerun()

  if st.session_state.messages:
      st.markdown("---")
      st.markdown("<div class='sidebar-title'>Exportar Conversa</div>", unsafe_allow_html=True)
      
      conv_ativa = obter_conversa_atual()
      titulo_export = conv_ativa.get("titulo", "Conversa") if conv_ativa else "Conversa"
      nome_export = st.session_state.get("usuario_nome", "")
      
      conversa_txt = formatar_conversa_txt(
          st.session_state.messages,
          tenant_id=tenant_id,
          usuario_nome=nome_export,
          conversa_titulo=titulo_export
      )
      st.download_button(
          label="⬇️ Baixar em TXT",
          data=conversa_txt,
          file_name=f"conversa_{tenant_id}.txt",
          mime="text/plain",
          use_container_width=True
      )
      
      try:
          conversa_pdf = gerar_conversa_pdf(
              st.session_state.messages,
              tenant_id=tenant_id,
              usuario_nome=nome_export,
              conversa_titulo=titulo_export
          )
          if conversa_pdf is not None:
              st.download_button(
                  label="⬇️ Baixar em PDF",
                  data=conversa_pdf,
                  file_name=f"conversa_{tenant_id}.pdf",
                  mime="application/pdf",
                  use_container_width=True
              )
      except Exception as e:
          logger = obter_logger(tenant_id)
          logger.error(f"Erro ao gerar PDF do histórico de conversa: {e}", exc_info=True)
          st.sidebar.error(f"Erro ao gerar PDF: {e}, tente novamente.")

if config.get("logo_url"):
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
        <img src="{config['logo_url']}" alt="{config['nome']}" style="max-height: 60px; object-fit: contain;">
        <span class="badge-senai">{config['nome']}</span>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
        <div style="font-size: 2rem; font-weight: 900; letter-spacing: -1px;">
            <span style="color: {cor_primaria};">SENAI</span>
            <span style="color: {cor_secundaria};">lab</span>
            <span style="color: #000000;">FASHION</span>
        </div>
        <span class="badge-senai">IA</span>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# NAVEGAÇÃO PRINCIPAL POR ABAS (ASSISTENTE E CONFIGURAÇÕES)
# ─────────────────────────────────────────────────────────────────────────────
tab_assistente, tab_config = st.tabs(["💬 Assistente", "⚙️ Configurações"])

with tab_assistente:
    # Adicionando um titulo ao app
    st.title('Assistente de IA especializado em Moda')
    # Adicionando um subtitulo ao app
    st.subheader("Conhecimento técnico têxtil e criatividade, unidos pela inteligência artificial.")
    
    # Banner informativo do Modo Ativo (fixo no topo do chat)
    st.info(f"**Modo de IA Ativo:** {config['descricoes_detalhadas'][modo_selecionado]}")
    
    # Exibe todas as mensagens na sessao, caso ainda nao exista
    if 'messages' not in st.session_state:
      st.session_state.messages = []
    
    # Container principal de mensagens e onboarding - posicionado estritamente ACIMA do st.chat_input
    chat_container = st.container()

    with chat_container:
        # 1. Se o nome do usuário ainda não foi definido, exibe a tela de identificação simples
        if st.session_state.get('usuario_nome') is None:
          st.markdown(f"""
          <div style="background-color: {bg_onboarding}; border-left: 5px solid {cor_primaria}; padding: 20px 24px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
              <h3 style="margin-top:0; color: {cor_primaria}; font-size: 1.35rem;">👋 Bem-vindo ao {config['nome']}!</h3>
              <p style="margin-bottom: 8px; font-size: 1rem; color: {text_color};">
                  Para identificarmos e salvarmos as suas conversas recentes, <strong>como podemos te chamar?</strong>
              </p>
              <p style="margin-bottom: 0; font-size: 0.88rem; color: {text_subtle};">
                  Digite seu nome ou apelido para continuar (sem necessidade de senha):
              </p>
          </div>
          """, unsafe_allow_html=True)
          
          with st.form(key="form_identificacao_usuario"):
              nome_input = st.text_input("Como podemos te chamar?", placeholder="Ex: Usuário 1", key="input_nome_usuario")
              btn_continuar = st.form_submit_button("Continuar ➔", use_container_width=True)
              
              if btn_continuar:
                  nome_normalizado = re.sub(r'\s+', ' ', nome_input.strip()).lower()
                  if nome_normalizado:
                      st.session_state.usuario_nome = nome_normalizado
                      st.session_state.usuario_id = hashlib.md5(nome_normalizado.encode('utf-8')).hexdigest()[:12]
                      st.query_params["usuario"] = nome_normalizado
                      st.rerun()
                  else:
                      st.warning("Por favor, digite seu nome antes de continuar.")

        # 2. Se o perfil ainda não foi escolhido, mostra a tela de seleção de perfil
        elif st.session_state.get('perfil_usuario') is None:
          st.markdown(f"""
          <div style="background-color: {bg_onboarding}; border-left: 5px solid {cor_primaria}; padding: 20px 24px; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
              <h3 style="margin-top:0; color: {cor_primaria}; font-size: 1.35rem;">👋 Bem-vindo ao {config['nome']}!</h3>
              <p style="margin-bottom: 8px; font-size: 1rem; color: {text_color};">
                  Para adaptarmos o modo padrão, as sugestões rápidas e o tom do assistente à sua rotina, <strong>qual é o seu papel na empresa?</strong>
              </p>
              <p style="margin-bottom: 0; font-size: 0.88rem; color: {text_subtle};">
                  Selecione o seu perfil abaixo para personalizar a sua experiência:
              </p>
          </div>
          """, unsafe_allow_html=True)
          
          col1, col2, col3 = st.columns(3)
          perfis_botoes = [
              ("dono_responsavel", "🧵 Dono(a) / Responsável", "Visão geral do negócio, decisões estratégicas e custos"),
              ("producao", "📐 Time de Produção", "Modelagem, tecidos, processos de costura e fichas técnicas"),
              ("criacao_estilo", "🎨 Criação / Estilo", "Croquis visuais, tendências de moda e conceito de coleção")
          ]
          
          for col, (p_id, p_titulo, p_desc) in zip([col1, col2, col3], perfis_botoes):
              with col:
                  st.markdown(f"""
                  <div style="background: {bg_card}; border: 2px solid {border_card}; padding: 20px 15px; border-radius: 10px; min-height: 140px; text-align: center; display: flex; flex-direction: column; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                      <div style="font-size: 1.1rem; font-weight: 700; color: {cor_primaria}; margin-bottom: 8px;">{p_titulo}</div>
                      <div style="font-size: 0.88rem; color: {text_subtle}; line-height: 1.3;">{p_desc}</div>
                  </div>
                  """, unsafe_allow_html=True)
                  st.button(
                      f"Selecionar {p_titulo.split(' ', 1)[1]}",
                      key=f"btn_sel_perfil_{p_id}",
                      on_click=selecionar_perfil,
                      args=(p_id,),
                      use_container_width=True
                  )
        else:
          # Exibe o Onboarding guiado se for a primeira experiência (sem mensagens)
          if len(st.session_state.messages) == 0:
            msg_boas_vindas = config.get("mensagem_boas_vindas") or FALLBACK_BOAS_VINDAS
            st.markdown(f"""
            <div style="background-color: {bg_onboarding}; border-left: 5px solid {cor_primaria}; padding: 18px 22px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">
                <h3 style="margin-top:0; color: {cor_primaria}; font-size: 1.25rem;">&#128075; Bem-vindo ao {config['nome']}!</h3>
                <p style="margin-bottom: 8px; font-size: 0.95rem; color: {text_color};">
                    <strong>O que o assistente faz:</strong> {msg_boas_vindas}
                </p>
                <p style="margin-bottom: 8px; font-size: 0.95rem; color: {text_color};">
                    <strong>Como ele te ajuda:</strong> Ele atua em 5 modos especializados (Estilo, Professor Técnico, Croquis, Tendências e Análise de Dados) para trazer respostas precisas, didáticas e análises numéricas ao setor têxtil.
                </p>
                <p style="margin-bottom: 0; font-size: 0.95rem; color: {text_subtle};">
                    <strong>&#9888;&#65039; O que ele NÃO faz:</strong> Ele não responde a assuntos fora do universo da moda e têxtil, não realiza agendamentos presenciais e não substitui a validação final técnica em oficina.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### 🚀 Como usar em 3 passos:")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"""
                <div style="background: {bg_step1}; border: 1px solid {border_step1}; padding: 15px; border-radius: 8px; height: 100%;">
                    <div style="font-size: 1.1rem; font-weight: bold; color: {cor_primaria};">1. Escolha o modo</div>
                    <div style="font-size: 0.88rem; color: {text_color}; margin-top: 6px;">Selecione na barra lateral a especialidade desejada (ex: <i>Professor Técnico</i> ou <i>Gerador de Croqui</i>).</div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style="background: {bg_step2}; border: 1px solid {border_step2}; padding: 15px; border-radius: 8px; height: 100%;">
                    <div style="font-size: 1.1rem; font-weight: bold; color: {cor_secundaria};">2. Digite ou clique</div>
                    <div style="font-size: 0.88rem; color: {text_color}; margin-top: 6px;">Escreva sua dúvida na caixa de texto abaixo ou clique em uma das sugestões rápidas em destaque.</div>
                </div>
                """, unsafe_allow_html=True)
            with col3:
                st.markdown(f"""
                <div style="background: {bg_step3}; border: 1px solid {border_step3}; padding: 15px; border-radius: 8px; height: 100%;">
                    <div style="font-size: 1.1rem; font-weight: bold; color: {text_color};">3. Baixe ou guarde</div>
                    <div style="font-size: 0.88rem; color: {text_color}; margin-top: 6px;">Exporte o histórico da sua conversa em PDF ou TXT a qualquer momento no menu lateral.</div>
                </div>
                """, unsafe_allow_html=True)

          
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"#### 💡 Sugestões de Perguntas Rápidas ({modo_selecionado}):")
            
            perguntas_main = obter_perguntas_rapidas(config, modo_selecionado, st.session_state.get("perfil_usuario"))
            pergunta_cols = st.columns(len(perguntas_main))
            for idx, pergunta in enumerate(perguntas_main):
                texto_puro = pergunta.split(maxsplit=1)[1] if len(pergunta.split()) > 1 else pergunta
                with pergunta_cols[idx]:
                    if st.button(pergunta, key=f"btn_main_{modo_selecionado}_{idx}", use_container_width=True):
                        st.session_state.quick_question = texto_puro
                        st.rerun()
            st.markdown("---")
        
        # Inicializa a variável do cliente Groq
        client = None
        
        # Verifica se o usuario forneceu a chave de API da Groq
        if groq_api_key:
          try:
            # Cria o cliente Groq com a chave de API fornecida
            client = Groq(api_key=groq_api_key)
          except Exception as e:
            logger = obter_logger(tenant_id)
            logger.error(f"Erro ao inicializar o cliente Groq: {e}", exc_info=True)
            # Exibe erro caso haja problema ao inicializar o cliente
            st.sidebar.error(f'Erro ao inicializar o cliente Groq: {e}')
            st.stop()
        # Caso nao tenha chave, mostra aviso na sidebar
        elif st.session_state.messages:
          st.sidebar.warning('Chave de API da Groq não encontrada. Por favor, entre em contato com a equipe de TI para verificar o estado da chave.')

        # Área de upload de planilha para o modo "Análise de Dados"
        if modo_selecionado == "Análise de Dados":
            st.markdown("#### 📊 Upload de Planilha")
            uploaded_file = st.file_uploader(
                "📎 Envie sua planilha de vendas, estoque ou produção",
                type=["csv", "xlsx", "xls"],
                key=f"uploader_analise_{st.session_state.get('conversa_atual_id', 'padrao')}",
                help="Envie um arquivo CSV ou Excel (.xlsx, .xls) com registros para análise de dados."
            )
            st.caption("⚠️ Apenas um resumo estatístico dos dados é enviado à IA — os dados brutos completos não saem do seu navegador/sessão.")

            if uploaded_file is not None:
                file_identifier = f"{uploaded_file.name}_{uploaded_file.size}"
                if st.session_state.get("arquivo_analise_carregado") != file_identifier:
                    df_carregado = carregar_planilha(uploaded_file, tenant_id=tenant_id)
                    if df_carregado is None:
                        st.error("Não consegui ler esse arquivo. Verifique se é um CSV ou Excel válido.")
                        st.session_state.df_analise_atual = None
                        st.session_state.resumo_estatistico_atual = None
                        st.session_state.arquivo_analise_carregado = None
                    else:
                        st.session_state.df_analise_atual = df_carregado
                        st.session_state.resumo_estatistico_atual = gerar_resumo_estatistico(df_carregado)
                        st.session_state.arquivo_analise_carregado = file_identifier
            else:
                if st.session_state.get("arquivo_analise_carregado") is not None:
                    st.session_state.df_analise_atual = None
                    st.session_state.resumo_estatistico_atual = None
                    st.session_state.arquivo_analise_carregado = None

            if st.session_state.get("df_analise_atual") is not None:
                df_preview = st.session_state.df_analise_atual
                st.dataframe(df_preview.head(10), use_container_width=True)
                st.caption(f"📋 {len(df_preview)} linhas, {len(df_preview.columns)} colunas carregadas.")

            if st.session_state.get("resumo_estatistico_atual") is not None:
                with st.expander("🔍 Ver resumo estatístico enviado à IA (debug)", expanded=False):
                    admin_pwd = obter_secret_tenant(tenant_id, "ADMIN_PASSWORD")
                    if not admin_pwd:
                        st.caption("Visualização técnica do resumo estatístico gerado em Python:")
                        st.json(st.session_state.resumo_estatistico_atual)
                    else:
                        pwd_debug = st.text_input("Senha de Administrador para exibir debug:", type="password", key=f"debug_pwd_analise_{tenant_id}")
                        if pwd_debug == admin_pwd:
                            st.success("🔓 Acesso liberado ao debug.")
                            st.caption("Visualização técnica do resumo estatístico e agregações enviadas à API:")
                            st.json(st.session_state.resumo_estatistico_atual)
                        elif pwd_debug:
                            st.error("Senha de administrador incorreta.")
                        else:
                            st.info("Digite a senha de administrador para visualizar o JSON de depuração.")

            st.markdown("---")

        # Exibe todas as mensagens anteriores armazenadas no estado da sessao
        for msg in st.session_state.messages:
          is_assistant = msg.get('role') in ['assistant', 'IA']
          with st.chat_message('assistant' if is_assistant else 'user'):
            if is_assistant and 'mode' in msg:
              st.markdown(f"<span class='IA-badge'>{msg['mode']}</span>", unsafe_allow_html=True)
            st.markdown(msg['content'])
            # Exibe expander de fontes consultadas se houver metadados de RAG
            if is_assistant and msg.get('fontes_consultadas'):
              with st.expander("📎 Fontes consultadas", expanded=False):
                for f_nome in sorted(msg['fontes_consultadas']):
                  st.markdown(f"- 📄 **{f_nome}**")
                if msg.get('trechos_consultados'):
                  st.caption("Trechos relevantes utilizados:")
                  for tr in msg['trechos_consultados']:
                    fonte_tr = tr.get('fonte', 'Documento')
                    rotulo_tr = tr.get('rotulo_unidade') or (f"Pág. {tr.get('pagina', 1)}" if tr.get('pagina') else "")
                    prefixo = f"{fonte_tr} | {rotulo_tr}" if rotulo_tr else fonte_tr
                    texto_tr = tr.get('texto', '')
                    if len(texto_tr) > 250:
                      texto_tr = texto_tr[:250] + "..."
                    st.text(f"[{prefixo}]: {texto_tr}")
            # Exibe imagens geradas se existirem na mensagem (suporta vista frontal e traseira no Desenho Técnico)
            if is_assistant:
              if msg.get('imagem_url_costas'):
                col_f, col_c = st.columns(2)
                with col_f:
                  st.image(msg['imagem_url'], caption="📐 Vista Frontal (Desenho Técnico)", use_container_width=True)
                with col_c:
                  st.image(msg['imagem_url_costas'], caption="📐 Vista Traseira (Desenho Técnico)", use_container_width=True)
              elif msg.get('imagem_url'):
                st.image(msg['imagem_url'], caption="🎨 Croqui gerado pela IA", use_container_width=True)

        # Exibe UI de confirmação de imagem pendente, se houver
        if st.session_state.get('pending_image_request'):
          pending = st.session_state.pending_image_request
          prompt_vis = pending.get("prompt_visual", "")
          resumo_conf = pending.get("resumo_confirmacao", "") or prompt_vis
          modo_pending = pending.get("modo", modo_selecionado)
          estilo_pending = pending.get("estilo_croqui", "🎨 Ilustração de Moda")

          with st.chat_message('assistant'):
            st.markdown(f"<span class='IA-badge'>{modo_pending}</span>", unsafe_allow_html=True)
            st.markdown(f"**Entendi que você quer:** {resumo_conf}")
            st.caption(f"Estilo selecionado: {estilo_pending}")
            st.markdown("Por favor, confirme se a descrição acima está correta antes de gerar a imagem:")

            col_conf, col_canc = st.columns(2)
            btn_confirmar = col_conf.button("✅ Confirmar e gerar imagem", key="btn_confirmar_croqui", use_container_width=True)
            btn_cancelar = col_canc.button("✏️ Não é isso, deixa eu explicar melhor", key="btn_cancelar_croqui", use_container_width=True)

            if btn_confirmar:
              if not client:
                st.error("Chave de API da Groq não configurada. Entre em contato com a equipe de TI.")
              else:
                # 1. Moderação / Validação de escopo do prompt visual antes da geração de imagem
                with st.spinner("Validando o conteúdo do pedido de imagem..."):
                  resultado_mod = validar_prompt_imagem(client, prompt_vis, tenant_id)

                if not resultado_mod.get("aprovado", False):
                  st.error(f"⚠️ Não foi possível gerar esta imagem: {resultado_mod.get('motivo', 'O pedido contém elementos fora do escopo de moda e vestuário.')}")
                else:
                  limite_img = config.get("limite_imagens_dia", 30)
                  qtd_necessaria = 2 if estilo_pending == "📐 Desenho Técnico (Flat Sketch)" else 1

                  if not verificar_limite(tenant_id, "imagens", limite_img, quantidade_necessaria=qtd_necessaria):
                    if qtd_necessaria == 2:
                      st.error("⚠️ O limite diário de geração de imagens foi atingido (a geração de vista frontal + traseira em Desenho Técnico requer 2 créditos de imagem restantes). Novas gerações estarão disponíveis amanhã.")
                    else:
                      st.error("⚠️ O limite diário de geração de imagens foi atingido. Novas gerações estarão disponíveis amanhã.")
                  else:
                    with st.spinner("Gerando croqui e finalizando a resposta..."):
                      try:
                        imagem_url_gerada = None
                        imagem_url_costas_gerada = None

                        if estilo_pending == "📐 Desenho Técnico (Flat Sketch)":
                          prompt_frente = f"{prompt_vis}{SUFIXO_TECNICO}, front view"
                          prompt_costas = f"{prompt_vis}{SUFIXO_TECNICO}, back view"

                          res_frente = chamar_api_geracao_imagem(prompt_frente)
                          res_costas = chamar_api_geracao_imagem(prompt_costas)

                          if res_frente.startswith("https://image.pollinations.ai"):
                            imagem_url_gerada = res_frente
                            incrementar_uso(tenant_id, "imagens")
                          if res_costas.startswith("https://image.pollinations.ai"):
                            imagem_url_costas_gerada = res_costas
                            incrementar_uso(tenant_id, "imagens")

                          resultado_ferramenta = f"Desenhos técnicos vetoriais 2D gerados com sucesso (Frente: {imagem_url_gerada}, Costas: {imagem_url_costas_gerada})."
                        else:
                          resultado_ferramenta = executar_ferramenta_local("gerar_imagem_croqui", pending["argumentos"])
                          if resultado_ferramenta.startswith("https://image.pollinations.ai"):
                            imagem_url_gerada = resultado_ferramenta
                            incrementar_uso(tenant_id, "imagens")

                        msgs_api = list(pending["messages_for_api"])
                        msgs_api.append(pending["assistant_message"])
                        msgs_api.append({
                          "role": "tool",
                          "tool_call_id": pending["tool_call_id"],
                          "content": str(resultado_ferramenta),
                        })

                        segunda_resposta = client.chat.completions.create(
                          messages=msgs_api,
                          model="openai/gpt-oss-20b",
                          temperature=0.7,
                          max_tokens=2048,
                        )
                        texto_final = segunda_resposta.choices[0].message.content

                        st.session_state.messages.append({
                          'role': 'assistant',
                          'content': texto_final,
                          'mode': modo_pending,
                          'estilo_croqui': estilo_pending,
                          'imagem_url': imagem_url_gerada,
                          'imagem_url_costas': imagem_url_costas_gerada,
                          'tenant_id': tenant_id,
                        })
                        persistir_mensagem_atualizada()

                        st.session_state.pending_image_request = None
                        st.rerun()
                      except Exception as err_conf:
                        logger = obter_logger(tenant_id)
                        logger.error(f"Erro ao gerar croqui no fluxo de confirmação: {err_conf}", exc_info=True)
                        st.error(f"Erro ao gerar croqui: {err_conf}")

            elif btn_cancelar:
              st.session_state.messages.append({
                'role': 'assistant',
                'content': "Entendido! Por favor, reescreva seu pedido com mais detalhes sobre como você gostaria que fosse o croqui.",
                'mode': modo_pending,
                'tenant_id': tenant_id,
              })
              persistir_mensagem_atualizada()
              st.session_state.pending_image_request = None
              st.rerun()

    # Entrada de texto fixa no rodapé do assistente
    chat_prompt = None
    if st.session_state.get('perfil_usuario') is not None and st.session_state.get('usuario_nome') is not None:
      chat_prompt = st.chat_input('Como posso ajudar?')
    
    # Verifica se existe uma pergunta rápida pendente vinda da sidebar ou área principal
    prompt = None
    is_quick_question = False
    if 'quick_question' in st.session_state and st.session_state.quick_question:
      prompt = st.session_state.quick_question
      del st.session_state.quick_question
      is_quick_question = True
    elif chat_prompt:
      prompt = chat_prompt
      is_quick_question = False
    
    if prompt:
      # Se estiver no modo Análise de Dados e não houver planilha carregada, avisa e bloqueia
      if modo_selecionado == "Análise de Dados" and not st.session_state.get("resumo_estatistico_atual"):
        st.warning("📎 Envie uma planilha antes de fazer perguntas sobre os dados.")
        st.stop()

      validade_cache = config.get("modos", {}).get(modo_selecionado, {}).get("validade_cache_horas", 0)
      resposta_cacheada = None
      if is_quick_question:
        resposta_cacheada = obter_resposta_cacheada(tenant_id, modo_selecionado, prompt, validade_cache)

      # Limpa qualquer confirmação pendente anterior ao enviar novo prompt
      st.session_state.pending_image_request = None

      if resposta_cacheada is not None:
        # Resposta encontrada no cache: exibe diretamente no container e persiste
        st.session_state.messages.append({'role': 'user', 'content': prompt, 'tenant_id': tenant_id})
        with chat_container:
          with st.chat_message('user'):
            st.markdown(prompt)

          with st.chat_message('assistant'):
            st.markdown(f"<span class='IA-badge'>{modo_selecionado}</span>", unsafe_allow_html=True)
            st.caption("⚡ Resposta em cache")
            st.markdown(resposta_cacheada)

        st.session_state.messages.append({
          'role': 'assistant',
          'content': resposta_cacheada,
          'mode': modo_selecionado,
          'tenant_id': tenant_id,
        })
        persistir_mensagem_atualizada()
        st.rerun()
      else:
        # Se nao houver cliente valido, mostra aviso e para a execucao
        if not client:
          st.warning('Chave de API da Groq não configurada. Entre em contato com o TI da sua empresa.')
          st.stop()

        # Verificação de limite diário de mensagens do tenant
        limite_msg = config.get("limite_mensagens_dia", 200)
        if not verificar_limite(tenant_id, "mensagens", limite_msg):
          st.error("⚠️ O limite diário de mensagens deste assistente foi atingido. Novas mensagens estarão disponíveis amanhã. Em caso de dúvida, contate o suporte de TI.")
          st.stop()

        # Armazenar a mensagem do usuário no estado da sessão
        st.session_state.messages.append({'role': 'user', 'content': prompt, 'tenant_id': tenant_id})
        persistir_mensagem_atualizada()

        # Exibir mensagem do usuário e spinner da IA dentro do chat_container (acima do input)
        with chat_container:
          with st.chat_message('user'):
            st.markdown(prompt)

          modo_cfg = config['modos'][modo_selecionado]
          prompt_modo = modo_cfg['prompt']
          if modo_selecionado == "Gerador de Croqui":
            estilo_atual = st.session_state.get("estilo_croqui", "🎨 Ilustração de Moda")
            if estilo_atual == "📐 Desenho Técnico (Flat Sketch)":
              prompt_modo = modo_cfg.get("prompt_tecnico", prompt_modo)
            else:
              prompt_modo = modo_cfg.get("prompt_ilustracao", prompt_modo)

          contexto_perfil = ""
          if st.session_state.get("perfil_usuario"):
            perfil_info = PERFIS_USUARIO.get(st.session_state.perfil_usuario, {})
            rotulo = perfil_info.get("rotulo_prompt", st.session_state.perfil_usuario)
            contexto_perfil = f"\n\nO usuário se identificou como {rotulo}. Adapte a profundidade técnica e o tom da resposta para esse perfil."

          CUSTOM_PROMPT = f"{config['base_prompt']}\n\n{prompt_modo}{contexto_perfil}"
        
          if modo_selecionado == "Análise de Dados":
            with st.chat_message('assistant'):
              with st.spinner('Analisando os dados da planilha...'):
                try:
                  slf_ai_resposta = responder_pergunta_sobre_dados(
                    client=client,
                    pergunta=prompt,
                    resumo_estatistico=st.session_state.resumo_estatistico_atual,
                    prompt_sistema=CUSTOM_PROMPT,
                    tenant_id=tenant_id
                  )

                  incrementar_uso(tenant_id, "mensagens")

                  st.markdown(f"<span class='IA-badge'>{modo_selecionado}</span>", unsafe_allow_html=True)
                  st.markdown(slf_ai_resposta)

                  st.session_state.messages.append({
                    'role': 'assistant',
                    'content': slf_ai_resposta,
                    'mode': modo_selecionado,
                    'tenant_id': tenant_id,
                  })
                  persistir_mensagem_atualizada()
                  st.rerun()
                except Exception as e:
                  logger = obter_logger(tenant_id)
                  logger.error(f"Falha ao responder pergunta sobre dados no modo '{modo_selecionado}': {e}", exc_info=True)
                  st.error("😕 Não consegui analisar os dados agora. Tente novamente em instantes ou fale com o suporte de TI.")
          elif modo_selecionado == "Base de Conhecimento":
            with st.chat_message('assistant'):
              with st.spinner('Pesquisando na base de documentos...'):
                chunks_relevantes = buscar_contexto_relevante(tenant_id, prompt, top_k=10)

                if not chunks_relevantes:
                  docs_cadastrados = listar_documentos_indexados(tenant_id)
                  if docs_cadastrados:
                    slf_ai_resposta = "Não encontrei essa informação no documento."
                  else:
                    slf_ai_resposta = "📚 Nenhum documento foi carregado ainda para este assistente na Base de Conhecimento. Peça ao administrador para adicionar materiais na aba Configurações."

                  st.markdown(f"<span class='IA-badge'>{modo_selecionado}</span>", unsafe_allow_html=True)
                  st.markdown(slf_ai_resposta)

                  st.session_state.messages.append({
                    'role': 'assistant',
                    'content': slf_ai_resposta,
                    'mode': modo_selecionado,
                    'fontes_consultadas': [],
                    'trechos_consultados': [],
                    'tenant_id': tenant_id,
                  })
                  persistir_mensagem_atualizada()
                  st.rerun()

                trechos_formatados = []
                fontes_consultadas = set()
                for i, chk in enumerate(chunks_relevantes, 1):
                  fonte = chk.get("fonte", "Documento desconhecido")
                  rotulo = chk.get("rotulo_unidade")
                  if not rotulo:
                    pag = chk.get("pagina", 1)
                    rotulo = f"Página {pag}"
                  fontes_consultadas.add(f"{fonte} ({rotulo})")

                  meta_info = []
                  if chk.get("secao") or chk.get("secao_origem"):
                    sec_val = chk.get("secao") or chk.get("secao_origem")
                    meta_info.append(f"SEÇÃO: {sec_val}")
                  if chk.get("produto") or chk.get("variante"):
                    prod_var = f"{chk.get('produto', '')} {chk.get('variante', '')}".strip()
                    meta_info.append(f"PRODUTO/VARIANTE: {prod_var}")
                  if chk.get("aba"):
                    meta_info.append(f"ABA: {chk['aba']}")
                  meta_header = " | ".join(meta_info) if meta_info else "Especificação Técnica"

                  trechos_formatados.append(
                    f"--- TRECHO {i} ---\n"
                    f"DOCUMENTO: {fonte}\n"
                    f"LOCALIZAÇÃO: {rotulo}\n"
                    f"CONTEXTO: {meta_header}\n"
                    f"CONTEÚDO:\n{chk.get('texto', '')}\n"
                  )

                contexto_rag = "\n".join(trechos_formatados)
                prompt_com_contexto = (
                  "INSTRUÇÃO IMPORTANTE: Responda à pergunta a seguir utilizando EXCLUSIVAMENTE os seguintes trechos de documentos fornecidos. "
                  "Siga rigorosamente as regras de preservação de números, medidas, códigos e isolamento de variantes.\n\n"
                  f"--- TRECHOS DOS DOCUMENTOS DISPONÍVEIS ---\n{contexto_rag}\n--- FIM DOS TRECHOS ---\n\n"
                  f"PERGUNTA DO USUÁRIO:\n{prompt}"
                )

                messages_for_api = [
                  {'role': 'system', 'content': CUSTOM_PROMPT},
                  {'role': 'user', 'content': prompt_com_contexto}
                ]

                try:
                  resposta_rag_obj = client.chat.completions.create(
                    messages=messages_for_api,
                    model="openai/gpt-oss-20b",
                    temperature=0.1,
                    max_tokens=2048,
                  )
                  slf_ai_resposta = resposta_rag_obj.choices[0].message.content
                  incrementar_uso(tenant_id, "mensagens")

                  st.markdown(f"<span class='IA-badge'>{modo_selecionado}</span>", unsafe_allow_html=True)
                  st.markdown(slf_ai_resposta)

                  with st.expander("📎 Fontes consultadas", expanded=False):
                    for f_nome in sorted(fontes_consultadas):
                      st.markdown(f"- 📄 **{f_nome}**")
                    st.caption("Trechos relevantes utilizados:")
                    for tr in chunks_relevantes:
                      fonte_tr = tr.get('fonte', 'Documento')
                      rotulo_tr = tr.get('rotulo_unidade') or f"Pág. {tr.get('pagina', 1)}"
                      texto_tr = tr.get('texto', '')
                      score_tr = tr.get('score', 0.0)
                      if len(texto_tr) > 250:
                        texto_tr = texto_tr[:250] + "..."
                      st.text(f"[{fonte_tr} | {rotulo_tr} | Score: {score_tr:.4f}]: {texto_tr}")

                    if RAG_DEBUG:
                      st.divider()
                      st.caption("🔍 Detalhes do Pipeline RAG (Debug & Observabilidade):")
                      st.code(formatar_bloco_debug_rag(obter_ultimo_rag_debug()), language="text")

                  st.session_state.messages.append({
                    'role': 'assistant',
                    'content': slf_ai_resposta,
                    'mode': modo_selecionado,
                    'fontes_consultadas': list(fontes_consultadas),
                    'trechos_consultados': chunks_relevantes,
                    'tenant_id': tenant_id,
                  })
                  persistir_mensagem_atualizada()
                  st.rerun()
                except Exception as e:
                  logger = obter_logger(tenant_id)
                  logger.error(f"Falha ao responder no modo '{modo_selecionado}': {e}", exc_info=True)
                  msg_erro = "😕 Não consegui consultar a base de conhecimento agora. Tente novamente em instantes ou fale com o suporte de TI."
                  st.error(msg_erro)
                  st.session_state.messages.append({
                    'role': 'assistant',
                    'content': msg_erro,
                    'mode': modo_selecionado,
                    'fontes_consultadas': [],
                    'trechos_consultados': [],
                    'tenant_id': tenant_id,
                  })
                  persistir_mensagem_atualizada()
                  st.rerun()
          else:
            messages_for_api = [{'role': 'system', 'content': CUSTOM_PROMPT}]
            for msg in st.session_state.messages:
              api_role = 'assistant' if msg.get('role') in ['assistant', 'IA'] else msg.get('role', 'user')
              messages_for_api.append({'role': api_role, 'content': msg.get('content', '')})
          
            with st.chat_message('assistant'):
              with st.spinner('Analisando sua pergunta...'):
                try:
                  slf_ai_resposta, imagem_url, usou_fallback, pendente_dados = chamar_agente(
                    client, config["modos"][modo_selecionado], messages_for_api
                  )

                  incrementar_uso(tenant_id, "mensagens")

                  if is_quick_question and validade_cache > 0 and slf_ai_resposta:
                    salvar_resposta_cache(tenant_id, modo_selecionado, prompt, slf_ai_resposta)
          
                  if pendente_dados:
                    pendente_dados["modo"] = modo_selecionado
                    st.session_state.pending_image_request = pendente_dados
                    st.rerun()

                  if usou_fallback:
                    st.info("ℹ️ A busca em tempo real não está disponível no momento. Respondendo com conhecimento base.")
          
                  st.markdown(f"<span class='IA-badge'>{modo_selecionado}</span>", unsafe_allow_html=True)
                  st.markdown(slf_ai_resposta)
          
                  if imagem_url:
                    st.image(imagem_url, caption="🎨 Croqui gerado pela IA", use_container_width=True)
          
                  st.session_state.messages.append({
                    'role': 'assistant',
                    'content': slf_ai_resposta,
                    'mode': modo_selecionado,
                    'imagem_url': imagem_url,
                    'tenant_id': tenant_id,
                  })
                  persistir_mensagem_atualizada()
                  st.rerun()
                except Exception as e:
                  logger = obter_logger(tenant_id)
                  logger.error(f"Falha ao processar resposta do agente para o modo '{modo_selecionado}': {e}", exc_info=True)
                  st.error("😕 Não consegui responder agora. Tente novamente em instantes ou fale com o suporte de TI.")

with tab_config:
    st.header("⚙️ Configurações de Aparência do Usuário")
    
    # Obtém a senha de admin via função centralizada (st.secrets ou env vars)
    admin_password = obter_secret_tenant(tenant_id, "ADMIN_PASSWORD")

    if not admin_password:
        st.warning("⚠️ A área de configuração de administração não está disponível para este tenant (senha não configurada nos secrets nem nas variáveis de ambiente).")
    else:
        senha_digitada = st.text_input("Digite a senha de administrador:", type="password", key=f"admin_pwd_{tenant_id}")
        
        if senha_digitada == admin_password:
            st.success("🔓 Acesso autorizado como Administrador.")
            st.markdown("---")
            
            # Nota de segurança / restrição de escopo de edição:
            # Prompts, modos e perguntas rápidas continuam vindo apenas de TENANT_CONFIG no código.
            # A edição de prompts/modos será tratada em uma tela futura separada.
            st.info("ℹ️ **Edição de Aparência:** Nesta tela é possível customizar nome, cores e logo do app.")
            
            with st.form(key=f"form_aparencia_{tenant_id}"):
                novo_nome = st.text_input("Nome da Aplicação", value=config.get("nome", ""))
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    nova_cor_p = st.color_picker("Cor Primária", value=config.get("cor_primaria", "#0047AB"))
                with col_c2:
                    nova_cor_s = st.color_picker("Cor Secundária", value=config.get("cor_secundaria", "#F47B20"))

                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    t_atual = config.get("tema", "claro")
                    idx_t = 0 if t_atual == "claro" else 1
                    opt_tema = st.radio("Tema de Cores", options=["☀️ Claro", "🌙 Escuro"], index=idx_t, horizontal=True)
                    novo_tema = "claro" if "Claro" in opt_tema else "escuro"

                with col_t2:
                    f_atual = config.get("fonte", "Inter")
                    fontes_opt = ["Inter", "Roboto", "Poppins"]
                    idx_f = fontes_opt.index(f_atual) if f_atual in fontes_opt else 0
                    nova_fonte = st.selectbox("Tipografia (Google Fonts)", options=fontes_opt, index=idx_f)

                novo_logo_url = st.text_input("URL do Logo (opcional - deixe em branco para usar o logo padrão)", value=config.get("logo_url", ""))
                novo_favicon_url = st.text_input("URL do Favicon (opcional - deixe em branco para usar o emoji 🪡)", value=config.get("favicon_url", ""))

                nova_msg_bv = st.text_area(
                    "Mensagem de Boas-vindas (Onboarding)",
                    value=config.get("mensagem_boas_vindas", FALLBACK_BOAS_VINDAS),
                    help="Personalize o texto inicial do onboarding exibido na tela principal."
                )

                st.caption(f"Prévia: tema {novo_tema}, fonte {nova_fonte}, cor primária {nova_cor_p}, cor secundária {nova_cor_s}")

                btn_salvar = st.form_submit_button("Salvar Alterações")

                if btn_salvar:
                    dados_salvar = {
                        "nome": novo_nome.strip(),
                        "cor_primaria": nova_cor_p,
                        "cor_secundaria": nova_cor_s,
                        "logo_url": novo_logo_url.strip(),
                        "tema": novo_tema,
                        "fonte": nova_fonte,
                        "favicon_url": novo_favicon_url.strip(),
                        "mensagem_boas_vindas": nova_msg_bv.strip(),
                    }
                    salvar_config_tenant(tenant_id, dados_salvar)
                    st.success("Configurações salvas com sucesso!")
                    st.rerun()


            st.markdown("---")
            st.subheader("📚 Base de Conhecimento")
            st.info("ℹ️ Documentos indexados aqui ficam disponíveis para todos os usuários deste tenant no modo Base de Conhecimento.")
            
            st.markdown("##### 📤 Enviar novos documentos")
            uploaded_rag_files = st.file_uploader(
                "Selecione um ou mais arquivos para indexar na Base de Conhecimento:",
                type=EXTENSOES_SUPORTADAS,
                accept_multiple_files=True,
                key=f"uploader_rag_{tenant_id}",
                help=f"Formatos suportados: {', '.join(ext.upper() for ext in EXTENSOES_SUPORTADAS)} (PDF, Word, Texto, Markdown, CSV, Excel, PowerPoint)."
            )

            if uploaded_rag_files:
                if st.button("📥 Indexar documentos", key=f"btn_indexar_rag_{tenant_id}", use_container_width=True):
                    prog_bar = st.progress(0, text="Iniciando extração e indexação...")
                    total_docs = len(uploaded_rag_files)
                    sucesso_count = 0

                    for idx_doc, doc_file in enumerate(uploaded_rag_files):
                        prog_val = int((idx_doc / total_docs) * 100)
                        prog_bar.progress(prog_val, text=f"Processando '{doc_file.name}' ({idx_doc + 1}/{total_docs})...")
                        try:
                            unidades_extraidas = extrair_documento(doc_file, nome_arquivo=doc_file.name)
                            if not unidades_extraidas:
                                st.warning(f"⚠️ O arquivo '{doc_file.name}' não contém texto legível, registros ou está vazio.")
                            else:
                                qtd_chunks = indexar_documento(tenant_id, doc_file.name, unidades_extraidas)
                                if qtd_chunks > 0:
                                    sucesso_count += 1
                                else:
                                    st.warning(f"⚠️ Nenhum chunk pôde ser gerado para o arquivo '{doc_file.name}'.")
                        except ValueError as err_val:
                            logger = obter_logger(tenant_id)
                            logger.warning(f"Aviso ao processar '{doc_file.name}': {err_val}")
                            st.warning(f"⚠️ {err_val}")
                        except Exception as err_idx:
                            logger = obter_logger(tenant_id)
                            logger.error(f"Erro ao processar '{doc_file.name}': {err_idx}", exc_info=True)
                            st.error(f"❌ Erro ao indexar '{doc_file.name}': {err_idx}")

                    prog_bar.progress(100, text="Processamento concluído!")
                    if sucesso_count > 0:
                        st.success(f"✅ {sucesso_count} documento(s) indexado(s) com sucesso na base de conhecimento!")
                        st.rerun()

            st.markdown("##### 📑 Documentos atualmente indexados")
            docs_cadastrados = listar_documentos_indexados(tenant_id)
            if not docs_cadastrados:
                st.caption("Nenhum documento indexado até o momento para este tenant.")
            else:
                for doc_nome in docs_cadastrados:
                    col_doc1, col_doc2 = st.columns([4, 1])
                    with col_doc1:
                        st.write(f"📄 **{doc_nome}**")
                    with col_doc2:
                        doc_hash = hashlib.md5(doc_nome.encode("utf-8")).hexdigest()[:8]
                        if st.button("🗑️ Remover", key=f"btn_del_doc_{tenant_id}_{doc_hash}", use_container_width=True):
                            removido = remover_documento(tenant_id, doc_nome)
                            if removido:
                                st.success(f"Documento '{doc_nome}' removido com sucesso!")
                                st.rerun()
                            else:
                                st.error(f"Falha ao remover documento '{doc_nome}'.")

            st.markdown("---")
            st.subheader("🧹 Gerenciamento de Cache de Respostas")
            st.caption("Limpe o cache de respostas pré-geradas caso queira forçar a atualização imediata das Perguntas Rápidas antes do prazo de expiração.")
            if st.button("🗑️ Limpar cache de respostas", key=f"btn_limpar_cache_{tenant_id}"):
                caminho_cache = os.path.join("tenant_data", f"{tenant_id}_cache.json")
                try:
                    if os.path.exists(caminho_cache):
                        os.remove(caminho_cache)
                        logger = obter_logger(tenant_id)
                        logger.info("Cache de respostas limpo manualmente pelo administrador")
                        st.success("Cache de respostas limpo com sucesso!")
                    else:
                        st.info("Nenhum arquivo de cache encontrado para este tenant.")
                except Exception as err_cache:
                    logger = obter_logger(tenant_id)
                    logger.error(f"Erro ao limpar arquivo de cache: {err_cache}", exc_info=True)
                    st.error(f"Erro ao limpar cache: {err_cache}")
        elif senha_digitada:
            st.error("🔒 Senha incorreta. Tente novamente.")



