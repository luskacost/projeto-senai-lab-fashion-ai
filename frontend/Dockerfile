# Dockerfile do frontend Next.js (Fase 9/Bloco C).
#
# IMPORTANTE: NEXT_PUBLIC_API_URL é embutido no bundle em tempo de BUILD (não é lido em tempo
# de execução do container) -- por isso precisa ser passado como build arg (docker build
# --build-arg ou docker-compose build.args), não como variável de ambiente do container em
# runtime. Deve apontar para uma URL alcançável pelo NAVEGADOR do usuário final (não um hostname
# interno da rede Docker como "http://backend:8000"), já que as chamadas à API partem do
# navegador, não do processo Node.
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_TENANT_ID=senai_labfashion
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_TENANT_ID=${NEXT_PUBLIC_TENANT_ID}
RUN npm run build

# Imagem final enxuta: só o output "standalone" (server.js + node_modules traçados) + estáticos
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
# O servidor standalone escuta no endereço de HOSTNAME, que dentro do Docker é o ID do contêiner --
# o proxy da hospedagem (Railway) não o alcança e responde 502. 0.0.0.0 escuta em todas as
# interfaces. A porta vem de PORT (a hospedagem define; sem ela, 3000).
ENV HOSTNAME="0.0.0.0"
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
