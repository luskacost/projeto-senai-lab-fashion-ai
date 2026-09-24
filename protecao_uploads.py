# -*- coding: utf-8 -*-
"""Proteção contra zip bomb em uploads de formatos baseados em ZIP (Fase 15, V7).

.docx, .xlsx e .pptx são, por baixo, arquivos ZIP. `docx.Document`, `openpyxl.load_workbook` e
`pptx.Presentation` descompactam o conteúdo inteiro na memória sem limite próprio -- um arquivo de
poucos MB (dentro do limite de upload) pode conter uma taxa de compressão absurda e virar vários
GB depois de descompactado, derrubando o processo por exaustão de memória. Isolado num módulo sem
dependência do resto do projeto (mesmo padrão de `conteudo_nao_confiavel.py`) porque é usado tanto
por `document_extractors.py` (RAG) quanto por `analise_dados.py` (planilha), que não devem
depender um do outro.
"""

import io
import zipfile

LIMITE_PADRAO_DESCOMPACTADO_BYTES = 300 * 1024 * 1024  # 300MB


def verificar_zip_bomb(conteudo: bytes, limite_bytes: int = LIMITE_PADRAO_DESCOMPACTADO_BYTES) -> None:
    """Levanta ValueError se o total descompactado do arquivo ZIP ultrapassar `limite_bytes`.

    Se `conteudo` não for um ZIP válido, não faz nada -- quem chamou vai tentar abrir o arquivo
    com a biblioteca específica (python-docx/openpyxl/python-pptx) logo em seguida, que vai
    rejeitá-lo com sua própria mensagem de "arquivo corrompido"."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as arquivo_zip:
            total_descompactado = sum(info.file_size for info in arquivo_zip.infolist())
    except zipfile.BadZipFile:
        return

    if total_descompactado > limite_bytes:
        raise ValueError(
            f"O arquivo descompactaria para mais de {limite_bytes // (1024 * 1024)}MB, "
            "acima do limite permitido."
        )
