"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, enviarMensagemChat, obterConfigTenant, TenantConfig } from "@/lib/api";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
const MODO = "Base de Conhecimento";

interface Mensagem {
  role: "user" | "assistant";
  content: string;
  fontes?: string[];
}

export default function ChatPage() {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [entrada, setEntrada] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const conversationId = useRef<string>(crypto.randomUUID());
  const fimDaListaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    obterConfigTenant(TENANT_ID)
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    fimDaListaRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || carregando) return;

    setMensagens((atual) => [...atual, { role: "user", content: texto }]);
    setEntrada("");
    setCarregando(true);
    setErro(null);

    try {
      const resposta = await enviarMensagemChat({
        tenantId: TENANT_ID,
        mensagem: texto,
        modo: MODO,
        conversationId: conversationId.current,
      });
      setMensagens((atual) => [
        ...atual,
        { role: "assistant", content: resposta.resposta, fontes: resposta.fontes_consultadas },
      ]);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Falha ao conectar com a API.";
      setErro(msg);
    } finally {
      setCarregando(false);
    }
  }

  function aoPressionarTecla(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  }

  const corPrimaria = config?.cor_primaria ?? "#0047AB";

  return (
    <div className="flex flex-col h-screen max-w-3xl mx-auto w-full">
      <header
        className="px-4 py-3 text-white font-semibold text-lg shadow-sm"
        style={{ backgroundColor: corPrimaria }}
      >
        {config?.nome ?? "SenaiLabFashion IA"}
        <span className="ml-2 text-sm font-normal opacity-80">{MODO}</span>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-4 space-y-4 bg-gray-50">
        {mensagens.length === 0 && !carregando && (
          <p className="text-center text-gray-400 mt-8">
            {config?.mensagem_boas_vindas ?? "Faça uma pergunta sobre a base de conhecimento."}
          </p>
        )}

        {mensagens.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-white text-gray-900 border border-gray-200 rounded-bl-sm"
              }`}
            >
              {m.content}
              {m.fontes && m.fontes.length > 0 && (
                <details className="mt-2 text-xs opacity-75">
                  <summary className="cursor-pointer">Fontes consultadas</summary>
                  <ul className="list-disc list-inside mt-1">
                    {m.fontes.map((f, fi) => (
                      <li key={fi}>{f}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}

        {carregando && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2 text-gray-400">
              Pesquisando na base de documentos...
            </div>
          </div>
        )}

        {erro && (
          <div className="text-center text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {erro}
          </div>
        )}

        <div ref={fimDaListaRef} />
      </main>

      <footer className="p-4 border-t border-gray-200 bg-white">
        <div className="flex gap-2 items-end">
          <textarea
            value={entrada}
            onChange={(e) => setEntrada(e.target.value)}
            onKeyDown={aoPressionarTecla}
            placeholder="Digite sua pergunta..."
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={enviar}
            disabled={carregando || !entrada.trim()}
            className="rounded-xl px-4 py-2 text-white font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ backgroundColor: corPrimaria }}
          >
            Enviar
          </button>
        </div>
      </footer>
    </div>
  );
}
