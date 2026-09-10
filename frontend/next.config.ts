import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Fase 9/Bloco C: build enxuto pro Dockerfile (frontend/Dockerfile) -- traça só os módulos
  // de node_modules realmente usados em vez de copiar a árvore inteira pra imagem final.
  output: "standalone",
};

export default nextConfig;
