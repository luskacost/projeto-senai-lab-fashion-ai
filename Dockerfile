# Dockerfile do backend FastAPI (Fase 9/Bloco C) -- substitui o Dockerfile antigo, que ainda
# rodava a aplicação Streamlit descontinuada (ver tag pre-remocao-streamlit).
FROM python:3.12-slim

WORKDIR /app

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
