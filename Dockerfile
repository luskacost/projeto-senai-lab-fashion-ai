FROM python:3.11-slim

WORKDIR /app

# Otimização de tamanho da imagem Docker:
# O sentence-transformers depende de PyTorch (torch). Para evitar o download da versão pesada com suporte a CUDA (>2GB),
# instalamos previamente a variante CPU-only do PyTorch (~150MB), reduzindo drasticamente o tamanho final da imagem.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copia e instala apenas as dependências para aproveitar o cache de camadas do Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação
COPY . .

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
