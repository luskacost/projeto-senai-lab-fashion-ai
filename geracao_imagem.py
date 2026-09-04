# -*- coding: utf-8 -*-
"""Geração de imagens de croqui (Pollinations.ai) e orquestração de tool calling do Groq.

Extraído de app.py para ser reaproveitado pela API sem depender do Streamlit. As duas únicas
dependências de st.session_state existentes na versão original (estilo_croqui) viraram
parâmetros explícitos.
"""

import json
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from rag_config import GROQ_MODEL

SUFIXO_TECNICO = (
    ", fashion technical flat sketch, vector line art style, black and white line drawing, "
    "no human body, no color rendering, garment schematic, white background, technical fashion illustration"
)

ESTILO_ILUSTRACAO = "🎨 Ilustração de Moda"
ESTILO_TECNICO = "📐 Desenho Técnico (Flat Sketch)"


# IMPORTANTE: validar_prompt_imagem() (moderacao.py) deve sempre rodar antes desta função,
# independente do provedor de imagem usado (Pollinations, DALL-E, Gemini, etc.).
def chamar_api_geracao_imagem(prompt_visual: str) -> str:
    """Retorna a URL de uma imagem gerada pela Pollinations.ai a partir do prompt."""
    prompt_encoded = urllib.parse.quote(prompt_visual)
    return f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=512&height=768&nologo=true"


def executar_ferramenta_local(
    nome_ferramenta: str,
    argumentos: Dict[str, Any],
    estilo_croqui: str = ESTILO_ILUSTRACAO
) -> str:
    """Chama a função local correspondente ao nome_ferramenta e retorna o resultado."""
    if nome_ferramenta == "gerar_imagem_croqui":
        prompt_visual = argumentos.get("prompt_visual", "")
        if estilo_croqui == ESTILO_TECNICO:
            prompt_visual = f"{prompt_visual}{SUFIXO_TECNICO}, front view"
        return chamar_api_geracao_imagem(prompt_visual)
    return f"[Erro] Ferramenta '{nome_ferramenta}' não reconhecida. Nenhuma ação foi executada."


def chamar_agente(
    client: Any,
    agente_config: Dict[str, Any],
    messages_for_api: List[Dict[str, Any]],
    estilo_croqui: str = ESTILO_ILUSTRACAO
) -> Tuple[Optional[str], Optional[str], bool, Optional[Dict[str, Any]]]:
    """Chama a API da Groq com suporte a tool calling quando o agente tiver tools.

    Se a ferramenta 'gerar_imagem_croqui' for detectada, retorna um sinal de confirmação
    pendente (pendente_dados) contendo os argumentos e o ID da chamada para aprovação prévia
    do usuário -- a geração da imagem em si só ocorre após confirmação explícita (ver
    api/main.py: POST /chat/croqui/confirmar).

    Retorna (texto_resposta, imagem_url, usou_fallback_sem_tools, pendente_dados).
    """
    tools = agente_config.get("tools")
    imagem_url = None

    try:
        if tools is not None:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=GROQ_MODEL,
                temperature=0.7,
                max_tokens=2048,
                tools=tools,
                tool_choice="auto",
            )
        else:
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=GROQ_MODEL,
                temperature=0.7,
                max_tokens=2048,
            )
    except Exception as api_err:
        err_str = str(api_err).lower()
        if tools is not None and any(kw in err_str for kw in ["tool", "search", "not supported", "invalid"]):
            primeira_resposta = client.chat.completions.create(
                messages=messages_for_api,
                model=GROQ_MODEL,
                temperature=0.7,
                max_tokens=2048,
            )
            return primeira_resposta.choices[0].message.content, None, True, None
        raise

    message = primeira_resposta.choices[0].message

    if hasattr(message, "tool_calls") and message.tool_calls:
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
                "estilo_croqui": estilo_croqui,
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
            resultado = executar_ferramenta_local(tool_call.function.name, argumentos, estilo_croqui)

            if resultado.startswith("https://image.pollinations.ai"):
                imagem_url = resultado

            messages_for_api.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(resultado),
            })

        segunda_resposta = client.chat.completions.create(
            messages=messages_for_api,
            model=GROQ_MODEL,
            temperature=0.7,
            max_tokens=2048,
        )
        texto_final = segunda_resposta.choices[0].message.content
        return texto_final, imagem_url, False, None

    return message.content, imagem_url, False, None
