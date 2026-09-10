# -*- coding: utf-8 -*-
"""Módulo de moderação e validação de escopo para geração de imagens de moda.

NOTA DE ARQUITETURA:
Esta camada de moderação é complementar aos filtros nativos que provedores pagos de geração
de imagem (como DALL-E, Gemini/Imagen) possam possuir. O objetivo desta camada prévia é:
(a) Economizar chamadas caras de API de imagem bloqueando prompts inadequados ou fora de escopo antes de enviá-los ao provedor;
(b) Aplicar regras de negócio específicas do produto (garantir escopo estrito de moda/vestuário/têxtil) que filtros genéricos de segurança não cobrem.
"""

import json
from logger_config import obter_logger
from rag_config import OPENAI_TEXT_MODEL

PROMPT_SISTEMA_MODERACAO = (
    "Você é um classificador de segurança e escopo para uma ferramenta de geração de imagens de moda e têxtil. "
    "Analise a descrição visual enviada pelo usuário e responda APENAS em formato JSON válido, no formato exato:\n"
    '{"aprovado": true, "motivo": "..."} ou {"aprovado": false, "motivo": "..."}.\n\n'
    "REGRAS DE CLASSIFICAÇÃO:\n"
    "1. Reprove (aprovado: false) se a descrição contiver: conteúdo sexual ou sugestivo, violência, discriminação, nudez, "
    "menores de idade em contexto inadequado, armas, veículos, animais não integrados à moda, paisagens sem relação com vestuário, "
    "ou qualquer elemento claramente fora do escopo de moda, vestuário, tecidos, croquis, modelos de moda ou confecção têxtil.\n"
    "2. Aprove (aprovado: true) se a descrição for focado em roupas, calçados, bolsas, acessórios de moda, tecidos, "
    "estampas, alfaiataria, croquis, desenhos técnicos ou estética visual de moda (mesmo que conceitual, estilizado ou de alta-costura).\n"
    "3. O campo 'motivo' deve ser SEMPRE em português, curto, educado e sem detalhar termos explícitos ou sensíveis "
    "(exemplo se aprovado: 'Conteúdo dentro do escopo de moda.'; exemplo se reprovado: 'O pedido contém elementos fora do escopo de moda e vestuário.')."
)

def validar_prompt_imagem(client, prompt_visual: str, tenant_id: str) -> dict:
    """Valida se o prompt visual está dentro do escopo de moda/têxtil e livre de conteúdo impróprio.
    
    Usa a API de texto da OpenAI com temperatura 0 e baixo max_tokens para classificação barata e rápida.
    Em caso de falha de parse ou de rede, adota comportamento fail-safe (retorna aprovado: False).
    """
    logger = obter_logger(tenant_id)

    if not prompt_visual or not isinstance(prompt_visual, str):
        logger.info("Moderação de imagem reprovada: prompt visual inválido ou ausente")
        return {
            "aprovado": False,
            "motivo": "Descrição visual inválida ou ausente."
        }

    try:
        messages = [
            {"role": "system", "content": PROMPT_SISTEMA_MODERACAO},
            {"role": "user", "content": f"Descrição visual para analisar: {prompt_visual}"}
        ]

        try:
            resposta = client.chat.completions.create(
                messages=messages,
                model=OPENAI_TEXT_MODEL,
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_object"}
            )
        except Exception as e_resp:
            logger.warning(f"Response format json_object falhou no modelo de moderação, tentando fallback sem formato estruturado: {e_resp}")
            # Fallback caso response_format não seja suportado em alguma versão do modelo
            resposta = client.chat.completions.create(
                messages=messages,
                model=OPENAI_TEXT_MODEL,
                temperature=0.0,
                max_tokens=300
            )

        content = resposta.choices[0].message.content or ""
        content_clean = content.strip()

        # Remove formatação markdown se houver
        if content_clean.startswith("```"):
            linhas = content_clean.splitlines()
            if len(linhas) >= 2:
                content_clean = "\n".join(linhas[1:-1]).strip()

        dados = json.loads(content_clean)

        if isinstance(dados, dict) and "aprovado" in dados:
            aprovado = bool(dados["aprovado"])
            motivo = str(dados.get("motivo", "")).strip()
            if not motivo:
                motivo = "Conteúdo aprovado no escopo de moda." if aprovado else "O pedido contém elementos fora do escopo de moda."
            
            if not aprovado:
                logger.info(f"Moderação de imagem reprovada. Motivo: {motivo}")

            return {
                "aprovado": aprovado,
                "motivo": motivo
            }

        # Se o formato JSON não contiver a chave "aprovado", aciona fail-safe
        logger.warning("Resposta da API de moderação não continha a chave 'aprovado'")
        return {
            "aprovado": False,
            "motivo": "Não foi possível validar o conteúdo da imagem no momento. Tente reformular sua descrição."
        }

    except Exception as e:
        # Em caso de erro técnico ou falha de leitura, bloqueia por padrão (fail-safe)
        logger.error(f"Erro inesperado durante moderação de prompt visual: {e}", exc_info=True)
        return {
            "aprovado": False,
            "motivo": "Não foi possível validar o conteúdo da imagem no momento. Tente reformular sua descrição."
        }

