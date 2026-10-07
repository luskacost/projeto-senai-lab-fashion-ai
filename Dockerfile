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

# Modelo de embeddings do RAG (rag_manager._carregar_modelo_sentence_transformer) baixado no build,
# não na primeira pergunta em produção: sem isto, todo deploy novo baixava ~470MB do HuggingFace
# antes de responder (e dependia do HuggingFace estar no ar e sem limitar requisições anônimas).
# HF_HUB_OFFLINE=1 depois do download faz o app usar só o que já está na imagem.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1

# IP real do usuário atrás de proxy (Railway, Traefik): o uvicorn só lê o X-Forwarded-For quando a
# conexão vem de um IP listado aqui -- as redes privadas, onde os proxies das hospedagens vivem.
# NUNCA usar "*": com curinga, o uvicorn pega o PRIMEIRO IP do cabeçalho, que é o que o próprio
# cliente mandou (proxies só acrescentam o IP real no fim), e qualquer um forjaria o IP para
# escapar do bloqueio de login (Fase 14) e do limite de requisições (Fase 16, D1). Com a lista de
# redes, ele percorre o cabeçalho de trás pra frente e devolve o primeiro IP não-confiável: o real.
# Ver tests/app/test_config_deploy.py.
ENV FORWARDED_ALLOW_IPS="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,100.64.0.0/10,127.0.0.1,fc00::/7,::1"

# Copia o restante do código da aplicação
COPY . .

EXPOSE 8000

# `sh -c` para expandir ${PORT}: hospedagens como o Railway escolhem a porta e a informam em PORT;
# localmente, sem PORT definida, continua 8000. `exec` mantém o uvicorn como processo principal
# do contêiner (recebe o sinal de desligamento direto, sem o sh no meio).
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
