# -*- coding: utf-8 -*-
"""Logo da empresa impresso na ficha técnica (Fase 11, Task 11).

O logo é cadastrado uma vez e reaproveitado em toda ficha gerada -- o usuário nunca precisa
reenviá-lo. Fica em `tenant_data/branding/`, fora da pasta das fichas, porque pertence ao tenant,
não a uma ficha específica.

## Por que o arquivo é normalizado para PNG

O upload aceita PNG/JPG/JPEG, mas é sempre convertido e gravado como PNG. Isso resolve três
coisas de uma vez: o resto do código lida com um formato só (nada de adivinhar extensão), a
transparência é preservada (requisito explícito do usuário -- logo com fundo transparente não pode
virar um retângulo branco no documento), e um arquivo que só *finge* ser imagem não passa, porque
a conversão exige que o Pillow consiga de fato decodificá-lo.

SVG é recusado de propósito: o Word não embute SVG por esse caminho (python-docx/docxtpl só
inserem bitmap). Recusar com mensagem clara é melhor que aceitar e falhar na hora de gerar o
documento, quando o usuário já não associa mais o erro ao upload.

## Por que largura e altura são calculadas aqui

Passar só a largura para o `InlineImage` preservaria a proporção, mas um logo alto e estreito
estouraria a altura da célula e empurraria o cabeçalho inteiro para baixo. O cálculo abaixo
escolhe a escala que faz a imagem caber nos dois eixos -- nunca deforma (requisito do usuário:
"preservar proporção, nunca esticar") e nunca invade o resto do cabeçalho.
"""

import io
import json
import os
from typing import Any, Dict, Optional, Tuple

from PIL import Image, UnidentifiedImageError
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Cm

from logger_config import obter_logger

DIRETORIO_BRANDING = os.path.join("tenant_data", "branding")

# A célula do logo no template tem 4,00 cm de largura e altura livre (cresce com o conteúdo).
# 3,6 cm deixa uma folga para a margem interna da célula; 2,2 cm de teto de altura impede que um
# logo quadrado ou vertical infle o cabeçalho e empurre a ficha para uma página a mais.
LARGURA_MAX_CM = 3.6
ALTURA_MAX_CM = 2.2

# Um logo é um arquivo pequeno por natureza. O limite geral de upload do projeto (20MB) faria
# sentido para um PDF técnico, não para isto -- e um limite apertado reduz a superfície de abuso.
LIMITE_LOGO_BYTES = 5 * 1024 * 1024

FORMATOS_ACEITOS = ("PNG", "JPEG")
EXTENSOES_ACEITAS = (".png", ".jpg", ".jpeg")


class LogoInvalidoError(ValueError):
    """Upload recusado: arquivo grande demais, formato não suportado ou não é uma imagem."""


def _caminho_png(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_BRANDING, f"{tenant_id}_logo.png")


def _caminho_metadados(tenant_id: str) -> str:
    return os.path.join(DIRETORIO_BRANDING, f"{tenant_id}_logo.json")


def caminho_logo(tenant_id: str) -> Optional[str]:
    """Caminho do logo cadastrado, ou None se o tenant não tem logo."""
    caminho = _caminho_png(tenant_id)
    return caminho if os.path.exists(caminho) else None


def metadados_logo(tenant_id: str) -> Optional[Dict[str, Any]]:
    """Nome original, formato de origem e dimensões -- para a tela de configuração mostrar o que
    está cadastrado sem precisar abrir a imagem."""
    caminho = _caminho_metadados(tenant_id)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        obter_logger(tenant_id).error(f"Erro ao ler metadados do logo: {e}", exc_info=True)
        return None


def salvar_logo(tenant_id: str, conteudo: bytes, nome_original: str = "") -> Dict[str, Any]:
    """Valida, normaliza para PNG e grava o logo do tenant. Devolve os metadados salvos.

    Levanta LogoInvalidoError com mensagem em português para qualquer recusa -- a rota HTTP
    repassa essa mensagem direto ao usuário.
    """
    if not conteudo:
        raise LogoInvalidoError("Arquivo vazio.")

    if len(conteudo) > LIMITE_LOGO_BYTES:
        limite_mb = LIMITE_LOGO_BYTES // (1024 * 1024)
        raise LogoInvalidoError(f"O logo excede o limite de {limite_mb}MB.")

    if nome_original.lower().endswith(".svg"):
        raise LogoInvalidoError(
            "Arquivos SVG não podem ser inseridos no documento Word. Envie o logo em PNG ou JPG."
        )

    try:
        imagem = Image.open(io.BytesIO(conteudo))
        imagem.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise LogoInvalidoError("O arquivo enviado não é uma imagem válida (aceitos: PNG, JPG).")

    formato_origem = (imagem.format or "").upper()
    if formato_origem not in FORMATOS_ACEITOS:
        raise LogoInvalidoError(
            f"Formato '{formato_origem or 'desconhecido'}' não suportado. Envie o logo em PNG ou JPG."
        )

    # RGBA preserva a transparência de PNGs; JPEG (sem canal alfa) é convertido do mesmo jeito,
    # apenas ficando opaco -- comportamento correto, já que ele não tinha transparência nenhuma.
    imagem_png = imagem.convert("RGBA")

    os.makedirs(DIRETORIO_BRANDING, exist_ok=True)
    imagem_png.save(_caminho_png(tenant_id), format="PNG")

    metadados = {
        "nome_original": nome_original,
        "formato_origem": formato_origem,
        "largura_px": imagem_png.width,
        "altura_px": imagem_png.height,
    }
    with open(_caminho_metadados(tenant_id), "w", encoding="utf-8") as f:
        json.dump(metadados, f, ensure_ascii=False, indent=2)

    return metadados


def remover_logo(tenant_id: str) -> bool:
    """Remove o logo cadastrado. True se havia algo para remover."""
    removeu = False
    for caminho in (_caminho_png(tenant_id), _caminho_metadados(tenant_id)):
        if os.path.exists(caminho):
            try:
                os.remove(caminho)
                removeu = True
            except Exception as e:
                obter_logger(tenant_id).error(f"Erro ao remover logo: {e}", exc_info=True)
    return removeu


def calcular_dimensoes_cm(largura_px: int, altura_px: int) -> Tuple[float, float]:
    """Dimensões de impressão que cabem na área reservada, mantendo a proporção original.

    Usa a MENOR escala entre os dois eixos: é o que garante que a imagem caiba inteira na caixa.
    Escalar só pela largura deformaria nada, mas deixaria um logo vertical alto demais; escalar os
    eixos independentemente esticaria a imagem -- os dois cenários que o usuário pediu para evitar.
    """
    if largura_px <= 0 or altura_px <= 0:
        return (LARGURA_MAX_CM, ALTURA_MAX_CM)

    escala = min(LARGURA_MAX_CM / largura_px, ALTURA_MAX_CM / altura_px)
    return (largura_px * escala, altura_px * escala)


def logo_para_documento(modelo: DocxTemplate, tenant_id: str) -> Optional[InlineImage]:
    """InlineImage pronto para o contexto do docxtpl, ou None se não há logo cadastrado.

    None vira string vazia no render (o template simplesmente imprime a célula em branco), que é
    exatamente o comportamento pedido: "se não houver logo cadastrado, a área deve permanecer
    limpa".
    """
    caminho = caminho_logo(tenant_id)
    if not caminho:
        return None

    try:
        with Image.open(caminho) as imagem:
            largura_cm, altura_cm = calcular_dimensoes_cm(imagem.width, imagem.height)
        return InlineImage(modelo, caminho, width=Cm(largura_cm), height=Cm(altura_cm))
    except Exception as e:
        # Um logo ilegível não pode impedir a geração da ficha inteira -- o documento sai sem ele.
        obter_logger(tenant_id).error(f"Erro ao preparar o logo para o documento: {e}", exc_info=True)
        return None
