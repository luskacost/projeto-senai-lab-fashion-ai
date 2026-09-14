# -*- coding: utf-8 -*-
"""Conversão do .docx da ficha para PDF via LibreOffice headless (Fase 11, Task 13).

O PDF precisa sair visualmente idêntico ao Word -- mesma paginação, mesmas tabelas, mesmo logo.
Isso descarta gerar o PDF do zero (fpdf2, como o export de conversa faz): seria um segundo layout
para manter em sincronia com o template, e qualquer divergência entre os dois apareceria como
"o PDF não bate com o Word".

## Por que LibreOffice e não o Word

A máquina de desenvolvimento tem MS Word instalado, e converter por COM funcionaria aqui. Mas o
deploy é numa VPS Linux (decisão da Fase 9), onde Word não existe. Dois caminhos de conversão
diferentes significaria dois resultados possivelmente diferentes para o mesmo documento -- o PDF
que o usuário valida no Windows não seria o que sai em produção. LibreOffice roda igual nos dois.

## Detalhes que só aparecem sob uso real

- **Perfil isolado por chamada** (`-env:UserInstallation`): o LibreOffice usa um perfil de usuário
  único por padrão, e duas conversões simultâneas disputam o mesmo perfil -- a segunda trava ou
  falha silenciosamente. Um perfil temporário por invocação elimina a disputa.
- **Timeout**: o `soffice` pode ficar preso (documento estranho, diálogo invisível). Sem timeout,
  a requisição HTTP inteira fica pendurada.
- **`--outdir` em vez de nome de saída**: o LibreOffice não aceita escolher o nome do arquivo
  final; ele escreve `<mesmo nome>.pdf` no diretório indicado. O arquivo é movido depois.
"""

import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Optional

import fichas_repo
from logger_config import obter_logger

NOME_ARQUIVO_PDF = "ficha.pdf"

TIMEOUT_CONVERSAO_SEGUNDOS = 120

# Caminhos onde o LibreOffice costuma ficar em cada sistema. LIBREOFFICE_PATH permite apontar para
# uma instalação fora do padrão (ex: caminho específico da imagem Docker) sem alterar código.
_CAMINHOS_PADRAO = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/lib/libreoffice/program/soffice",
    "/opt/libreoffice/program/soffice",
)


class LibreOfficeIndisponivelError(RuntimeError):
    """LibreOffice não encontrado -- a conversão para PDF não é possível neste ambiente."""


class ConversaoPdfError(RuntimeError):
    """O LibreOffice foi executado mas não produziu o PDF."""


def encontrar_libreoffice() -> Optional[str]:
    """Caminho do executável do LibreOffice, ou None se não houver.

    Devolver None em vez de levantar permite que o chamador decida o que fazer -- a rota HTTP
    responde 501, e os testes se pulam sozinhos.
    """
    caminho_configurado = os.environ.get("LIBREOFFICE_PATH")
    if caminho_configurado:
        return caminho_configurado if os.path.exists(caminho_configurado) else None

    for caminho in _CAMINHOS_PADRAO:
        if os.path.exists(caminho):
            return caminho

    # PATH, por último: em Linux o binário costuma estar lá com nomes diferentes.
    for nome in ("soffice", "libreoffice"):
        encontrado = shutil.which(nome)
        if encontrado:
            return encontrado

    return None


def libreoffice_disponivel() -> bool:
    return encontrar_libreoffice() is not None


def converter_para_pdf(caminho_docx: str, caminho_pdf: str, tenant_id: str = "") -> str:
    """Converte um .docx em PDF preservando o layout. Devolve o caminho do PDF gerado."""
    executavel = encontrar_libreoffice()
    if not executavel:
        raise LibreOfficeIndisponivelError(
            "LibreOffice não encontrado. Instale-o ou aponte a variável LIBREOFFICE_PATH para o "
            "executável (soffice)."
        )

    if not os.path.exists(caminho_docx):
        raise ConversaoPdfError(f"Arquivo de origem não existe: {caminho_docx}")

    # Diretório temporário para a saída e para o perfil do LibreOffice desta invocação.
    with tempfile.TemporaryDirectory(prefix="ficha_pdf_") as temporario:
        perfil = os.path.join(temporario, f"perfil_{uuid.uuid4().hex}")
        comando = [
            executavel,
            f"-env:UserInstallation=file:///{perfil.replace(os.sep, '/')}",
            "--headless",
            "--norestore",
            "--convert-to", "pdf",
            "--outdir", temporario,
            caminho_docx,
        ]

        try:
            resultado = subprocess.run(
                comando,
                capture_output=True,
                timeout=TIMEOUT_CONVERSAO_SEGUNDOS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ConversaoPdfError(
                f"A conversão para PDF passou de {TIMEOUT_CONVERSAO_SEGUNDOS}s e foi interrompida."
            )

        # O LibreOffice nomeia a saída com o mesmo nome do arquivo de entrada, trocando a extensão.
        nome_esperado = os.path.splitext(os.path.basename(caminho_docx))[0] + ".pdf"
        pdf_temporario = os.path.join(temporario, nome_esperado)

        if not os.path.exists(pdf_temporario):
            # O soffice frequentemente sai com código 0 mesmo falhando -- verificar a existência do
            # arquivo é a única checagem confiável.
            saida = (resultado.stdout or b"").decode("utf-8", "replace").strip()
            erro = (resultado.stderr or b"").decode("utf-8", "replace").strip()
            if tenant_id:
                obter_logger(tenant_id).error(
                    f"LibreOffice não gerou o PDF (código {resultado.returncode}). stdout={saida!r} stderr={erro!r}"
                )
            raise ConversaoPdfError("O LibreOffice não conseguiu converter o documento para PDF.")

        destino = os.path.dirname(caminho_pdf)
        if destino:
            os.makedirs(destino, exist_ok=True)
        shutil.move(pdf_temporario, caminho_pdf)

    return caminho_pdf


def gerar_pdf_da_ficha(tenant_id: str, ficha_id: str, caminho_docx: str) -> str:
    """Converte o .docx já gerado da ficha e salva o PDF na pasta dela."""
    caminho_pdf = fichas_repo.caminho_arquivo_da_ficha(tenant_id, ficha_id, NOME_ARQUIVO_PDF)
    return converter_para_pdf(caminho_docx, caminho_pdf, tenant_id=tenant_id)


def contar_paginas(caminho_pdf: str) -> int:
    """Número de páginas do PDF.

    Existe para a verificação que só o PDF permite: conferir que a ficha continua cabendo em 3
    páginas. Fonte ausente no servidor causa substituição de fonte, reflow e uma página a mais --
    e isso é invisível olhando só o .docx.
    """
    from pypdf import PdfReader

    return len(PdfReader(caminho_pdf).pages)
