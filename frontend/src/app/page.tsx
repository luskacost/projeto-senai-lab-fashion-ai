"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  Conversa,
  MensagemConversa,
  atualizarConversa,
  criarConversa,
  deletarConversa,
  enviarMensagemChat,
  listarConversas,
  obterConfigTenant,
  TenantConfig,
} from "@/lib/api";
import { obterUsuarioId } from "@/lib/usuario";
import ConversasSidebar from "@/components/ConversasSidebar";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
const MODO = "Base de Conhecimento";

export default function ChatPage() {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [usuarioId, setUsuarioId] = useState<string | null>(null);
  const [conversas, setConversas] = useState<Conversa[]>([]);
  const [conversaAtualId, setConversaAtualId] = useState<string | null>(null);
  const [mensagens, setMensagens] = useState<MensagemConversa[]>([]);
  const [entrada, setEntrada] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const fimDaListaRef = useRef<HTMLDivElement>(null);

  // Carrega config do tenant e identidade/conversas do usuário.
  useEffect(() => {
    obterConfigTenant(TENANT_ID)
      .then(setConfig)
      .catch(() => setConfig(null));

    const uid = obterUsuarioId();
    setUsuarioId(uid);

    listarConversas(TENANT_ID, uid)
      .then(async (lista) => {
        if (lista.length === 0) {
          const nova = await criarConversa(TENANT_ID, uid);
          setConversas([nova]);
          setConversaAtualId(nova.id);
          setMensagens([]);
          return;
        }
        setConversas(lista);
        const maisRecente = [...lista].sort(
          (a, b) => new Date(b.atualizado_em).getTime() - new Date(a.atualizado_em).getTime()
        )[0];
        setConversaAtualId(maisRecente.id);
        setMensagens(maisRecente.mensagens);
      })
      .catch(() => setErro("Não foi possível carregar as conversas."));
  }, []);

  useEffect(() => {
    fimDaListaRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  function selecionarConversa(id: string) {
    const conv = conversas.find((c) => c.id === id);
    if (!conv) return;
    setConversaAtualId(id);
    setMensagens(conv.mensagens);
    setErro(null);
  }

  function mensagemDeErro(e: unknown, contexto: string): string {
    if (e instanceof ApiError) return e.message;
    return `Falha ao conectar com a API (${contexto}). Verifique se o servidor está rodando e tente novamente.`;
  }

  async function novaConversa() {
    if (!usuarioId) return;
    try {
      const nova = await criarConversa(TENANT_ID, usuarioId);
      setConversas((atual) => [...atual, nova]);
      setConversaAtualId(nova.id);
      setMensagens([]);
      setErro(null);
    } catch (e) {
      setErro(mensagemDeErro(e, "criar conversa"));
    }
  }

  async function renomearConversaAtual(id: string, novoTitulo: string) {
    if (!usuarioId) return;
    try {
      const atualizada = await atualizarConversa(TENANT_ID, usuarioId, id, { novoTitulo });
      setConversas((atual) => atual.map((c) => (c.id === id ? atualizada : c)));
    } catch (e) {
      setErro(mensagemDeErro(e, "renomear conversa"));
    }
  }

  async function excluirConversa(id: string) {
    if (!usuarioId) return;
    try {
      await deletarConversa(TENANT_ID, usuarioId, id);
      const restantes = conversas.filter((c) => c.id !== id);
      setConversas(restantes);

      if (conversaAtualId === id) {
        if (restantes.length > 0) {
          selecionarConversa(restantes[0].id);
        } else {
          await novaConversa();
        }
      }
    } catch (e) {
      setErro(mensagemDeErro(e, "excluir conversa"));
    }
  }

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || carregando || !usuarioId || !conversaAtualId) return;

    const mensagensComUsuario: MensagemConversa[] = [
      ...mensagens,
      { role: "user", content: texto, tenant_id: TENANT_ID },
    ];
    setMensagens(mensagensComUsuario);
    setEntrada("");
    setCarregando(true);
    setErro(null);

    try {
      const resposta = await enviarMensagemChat({
        tenantId: TENANT_ID,
        mensagem: texto,
        modo: MODO,
        conversationId: conversaAtualId,
      });

      const mensagensFinais: MensagemConversa[] = [
        ...mensagensComUsuario,
        {
          role: "assistant",
          content: resposta.resposta,
          mode: MODO,
          tenant_id: TENANT_ID,
          fontes_consultadas: resposta.fontes_consultadas,
        },
      ];
      setMensagens(mensagensFinais);

      const conversaAtualizada = await atualizarConversa(TENANT_ID, usuarioId, conversaAtualId, {
        mensagens: mensagensFinais,
      });
      setConversas((atual) => atual.map((c) => (c.id === conversaAtualId ? conversaAtualizada : c)));
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
    <div className="flex h-screen w-full">
      <ConversasSidebar
        conversas={conversas}
        conversaAtualId={conversaAtualId}
        corPrimaria={corPrimaria}
        onSelecionar={selecionarConversa}
        onNovaConversa={novaConversa}
        onRenomear={renomearConversaAtual}
        onDeletar={excluirConversa}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <header className="px-4 py-3 text-white font-semibold text-lg shadow-sm flex items-center justify-between" style={{ backgroundColor: corPrimaria }}>
          <div>
            {config?.nome ?? "SenaiLabFashion IA"}
            <span className="ml-2 text-sm font-normal opacity-80">{MODO}</span>
          </div>
          <Link href="/admin" className="text-sm font-normal opacity-80 hover:opacity-100">
            ⚙️ Configurações
          </Link>
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
                {m.fontes_consultadas && m.fontes_consultadas.length > 0 && (
                  <details className="mt-2 text-xs opacity-75">
                    <summary className="cursor-pointer">Fontes consultadas</summary>
                    <ul className="list-disc list-inside mt-1">
                      {m.fontes_consultadas.map((f, fi) => (
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
    </div>
  );
}
