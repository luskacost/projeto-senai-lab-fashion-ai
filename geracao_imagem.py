# -*- coding: utf-8 -*-
"""Geração de imagens de croqui via gpt-image-1 (OpenAI).

Extraído de app.py para ser reaproveitado pela API sem depender do Streamlit.

A orquestração de tool calling que vivia aqui (chamar_agente, executar_ferramenta_local) e a
busca web via Tavily (buscar_tendencias_web) foram removidas na Fase 10: a primeira foi
substituída por agente_openai.chamar_agente() (Responses API, Task 3-4) e a segunda pelo
web_search nativo da OpenAI (Task 5) -- Tendências, Engenharia Têxtil e Assistente Geral usam
usar_web_search=True em vez de uma tool própria (ver tenant_config.py). Nenhuma rota chamava mais
as funções antigas desde a Task 4; a remoção fecha essa dívida em vez de deixá-las mortas no
código.
"""

from typing import Any, Optional

from logger_config import obter_logger

SUFIXO_TECNICO = (
    ", fashion technical flat sketch, vector line art style, black and white line drawing, "
    "no human body, no color rendering, garment schematic, white background, technical fashion "
    "illustration, front view and back view shown together side by side in the same image"
)

ESTILO_ILUSTRACAO = "🎨 Ilustração de Moda"
ESTILO_TECNICO = "📐 Desenho Técnico (Flat Sketch)"

PREFIXO_IMAGEM_GERADA = "data:image/png;base64,"


def eh_imagem_gerada(valor: Any) -> bool:
    """True se `valor` é uma imagem retornada por chamar_api_geracao_imagem (data URI base64)."""
    return isinstance(valor, str) and valor.startswith(PREFIXO_IMAGEM_GERADA)


# IMPORTANTE: validar_prompt_imagem() (moderacao.py) deve sempre rodar antes desta função,
# independente do provedor de imagem usado.
def chamar_api_geracao_imagem(client: Any, prompt_visual: str, tenant_id: str, tamanho: str = "1024x1536") -> Optional[str]:
    """Gera uma imagem via gpt-image-1 (OpenAI, sucessor do DALL-E 3 -- "dall-e-3" não existe mais
    como model id na API) a partir do prompt e retorna uma data URI base64 (`data:image/png;base64,...`)
    -- ou None se a geração falhar (ex: rejeitada pelo filtro de conteúdo da própria OpenAI, erro
    de rede/quota).

    Diferente do antigo Pollinations.ai (URL hotlinkada, sem geração real nesta chamada) e do que
    se esperava do DALL-E 3 (URL temporária hospedada pela OpenAI), gpt-image-1 retorna os bytes
    da imagem em base64 (`b64_json`), não uma URL -- por isso o retorno aqui é uma data URI, que
    o `<img src>` do front-end consome nativamente sem nenhuma mudança. NUNCA repassar esse valor
    de volta pro LLM como conteúdo de mensagem (é gigante em tokens) -- ver
    agente_ferramentas._handler_gerar_imagem_croqui/_handler_gerar_ficha_tecnica, que só repassam
    um indicador curto de sucesso/falha.

    `tamanho` default é retrato (1024x1536), mais próximo do enquadramento de figurino de moda que
    o antigo 512x768. Não há parâmetro de seed: nenhuma versão do DALL-E/gpt-image expõe controle
    de determinismo na API pública -- para consistência entre frente/costas do Desenho Técnico,
    contamos só com prompts bem descritivos, sem garantia visual.
    """
    try:
        resposta = client.images.generate(
            model="gpt-image-1",
            prompt=prompt_visual,
            size=tamanho,
            n=1,
        )
        return PREFIXO_IMAGEM_GERADA + resposta.data[0].b64_json
    except Exception as e:
        obter_logger(tenant_id).error(f"Falha ao gerar imagem via gpt-image-1: {e}", exc_info=True)
        return None
