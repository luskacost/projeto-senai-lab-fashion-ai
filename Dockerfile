# Dockerfile do backend FastAPI (Fase 9/Bloco C) -- substitui o Dockerfile antigo, que ainda
# rodava a aplicação Streamlit descontinuada (ver tag pre-remocao-streamlit).
FROM python:3.12-slim

WORKDIR /app

# LibreOffice (deploy em produção, Fase A): fichas_pdf.py converte o .docx da ficha em PDF
# chamando o binário `soffice` como processo externo -- sem ele, /fichas/{id}/pdf e o preview
# devolvem 501 (ver encontrar_libreoffice() em fichas_pdf.py, que procura em /usr/bin/soffice e no
# PATH). `libreoffice-writer` em vez do pacote `libreoffice` completo evita baixar Impress/Calc/
# clipart/ajuda que este app nunca usa; `--no-install-recommends` tira mais peso ainda -- mesmo
# assim soma uns 300-400MB à imagem final. `rm -rf /var/lib/apt/lists/*` descarta o índice do apt
# depois de instalar, que não serve pra nada depois disso e só ocupa espaço na camada.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice-writer && \
    rm -rf /var/lib/apt/lists/*

# Otimização de tamanho da imagem: sentence-transformers depende de PyTorch (torch). Instalar
# antes a variante CPU-only (~150MB) evita baixar a build com suporte a CUDA (>2GB) que o
# requirements.txt puxaria por padrão.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copia e instala só as dependências primeiro, pra aproveitar o cache de camadas do Docker
# quando só o código da aplicação mudar (sem precisar reinstalar tudo de novo).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação
COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
