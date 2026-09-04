"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  Conversa,
  MensagemConversa,
  PendenteConfirmacao,
  atualizarConversa,
  baixarExportacaoConversa,
  confirmarCroqui,
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
const MODOS_DISPONIVEIS = ["Base de Conhecimento", "Gerador de Croqui"];
const ESTILO_ILUSTRACAO = "🎨 Ilustração de Moda";
const ESTILO_TECNICO = "📐 Desenho Técnico (Flat Sketch)";

export default function ChatPage() {
  const [config, setConfig] = useState<TenantConfig | null>(null);
  const [usuarioId, setUsuarioId] = useState<string | null>(null);
  const [conversas, setConversas] = useState<Conversa[]>([]);
  const [conversaAtualId, setConversaAtualId] = useState<string | null>(null);
  const [mensagens, setMensagens] = useState<MensagemConversa[]>([]);
  const [entrada, setEntrada] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [modo, setModo] = useState(MODOS_DISPONIVEIS[0]);
  const [estiloCroqui, setEstiloCroqui] = useState(ESTILO_ILUSTRACAO);
  const [pendenteConfirmacao, setPendenteConfirmacao] = useState<PendenteConfirmacao | null>(null);
  const fimDaListaRef = useRef<HTMLDivElement>(null);

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
  }, [mensagens, carregando, pendenteConfirmacao]);

  function mensagemDeErro(e: unknown, contexto: string): string {
    if (e instanceof ApiError) return e.message;
    return `Falha ao conectar com a API (${contexto}). Verifique se o servidor está rodando e tente novamente.`;
  }

  function selecionarConversa(id: string) {
    const conv = conversas.find((c) => c.id === id);
    if (!conv) return;
    setConversaAtualId(id);
    setMensagens(conv.mensagens);
    setPendenteConfirmacao(null);
    setErro(null);
  }

  async function novaConversa() {
    if (!usuarioId) return;
    try {
      const nova = await criarConversa(TENANT_ID, usuarioId);
      setConversas((atual) => [...atual, nova]);
      setConversaAtualId(nova.id);
      setMensagens([]);
      setPendenteConfirmacao(null);
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

  async function exportarConversaAtual(formato: "txt" | "pdf") {
    if (!usuarioId || !conversaAtualId) return;
    try {
      await baixarExportacaoConversa(TENANT_ID, usuarioId, conversaAtualId, formato);
    } catch (e) {
      setErro(mensagemDeErro(e, `exportar conversa em ${formato.toUpperCase()}`));
    }
  }

  async function persistirMensagens(lista: MensagemConversa[]) {
    if (!usuarioId || !conversaAtualId) return;
    const conversaAtualizada = await atualizarConversa(TENANT_ID, usuarioId, conversaAtualId, { mensagens: lista });
    setConversas((atual) => atual.map((c) => (c.id === conversaAtualId ? conversaAtualizada : c)));
  }

  async function enviar() {
    const texto = entrada.trim();
    if (!texto || carregando || pendenteConfirmacao || !usuarioId || !conversaAtualId) return;

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
        modo,
        conversationId: conversaAtualId,
        historico:
          modo === "Gerador de Croqui"
            ? mensagensComUsuario.map((m) => ({ role: m.role, content: m.content }))
            : undefined,
        estiloCroqui: modo === "Gerador de Croqui" ? estiloCroqui : undefined,
      });

      if (resposta.pendente_confirmacao) {
        setPendenteConfirmacao(resposta.pendente_confirmacao);
        await persistirMensagens(mensagensComUsuario);
        return;
      }

      const mensagensFinais: MensagemConversa[] = [
        ...mensagensComUsuario,
        {
          role: "assistant",
          content: resposta.resposta ?? "",
          mode: modo,
          tenant_id: TENANT_ID,
          fontes_consultadas: resposta.fontes_consultadas,
          imagem_url: resposta.imagem_url ?? null,
        },
      ];
      setMensagens(mensagensFinais);
      await persistirMensagens(mensagensFinais);
    } catch (e) {
      setErro(mensagemDeErro(e, "enviar mensagem"));
    } finally {
      setCarregando(false);
    }
  }

  async function resolverConfirmacao(confirmado: boolean) {
    if (!pendenteConfirmacao) return;
    setCarregando(true);
    setErro(null);
    try {
      const resultado = await confirmarCroqui(TENANT_ID, confirmado, pendenteConfirmacao);
      const mensagensFinais: MensagemConversa[] = [
        ...mensagens,
        {
          role: "assistant",
          content: resultado.resposta,
          mode: "Gerador de Croqui",
          tenant_id: TENANT_ID,
          imagem_url: resultado.imagem_url,
          imagem_url_costas: resultado.imagem_url_costas,
        },
      ];
      setMensagens(mensagensFinais);
      setPendenteConfirmacao(null);
      await persistirMensagens(mensagensFinais);
    } catch (e) {
      setErro(mensagemDeErro(e, "confirmar geração de imagem"));
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
        <header className="px-4 py-3 text-white shadow-sm flex items-center justify-between gap-3" style={{ backgroundColor: corPrimaria }}>
          <div className="flex items-center gap-3 min-w-0">
            <span className="font-semibold text-lg truncate">{config?.nome ?? "SenaiLabFashion IA"}</span>
            <select
              value={modo}
              onChange={(e) => {
                setModo(e.target.value);
                setPendenteConfirmacao(null);
              }}
              className="text-sm rounded-lg bg-white/20 text-white px-2 py-1 border-none focus:outline-none focus:ring-2 focus:ring-white/50"
            >
              {MODOS_DISPONIVEIS.map((m) => (
                <option key={m} value={m} className="text-gray-900">
                  {m}
                </option>
              ))}
            </select>
            {modo === "Gerador de Croqui" && (
              <select
                value={estiloCroqui}
                onChange={(e) => setEstiloCroqui(e.target.value)}
                className="text-sm rounded-lg bg-white/20 text-white px-2 py-1 border-none focus:outline-none focus:ring-2 focus:ring-white/50"
              >
                <option value={ESTILO_ILUSTRACAO} className="text-gray-900">
                  {ESTILO_ILUSTRACAO}
                </option>
                <option value={ESTILO_TECNICO} className="text-gray-900">
                  {ESTILO_TECNICO}
                </option>
              </select>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {mensagens.length > 0 && (
              <div className="flex gap-1 text-sm font-normal">
                <button
                  onClick={() => exportarConversaAtual("txt")}
                  className="opacity-80 hover:opacity-100"
                  title="Baixar conversa em TXT"
                >
                  ⬇️ TXT
                </button>
                <button
                  onClick={() => exportarConversaAtual("pdf")}
                  className="opacity-80 hover:opacity-100"
                  title="Baixar conversa em PDF"
                >
                  ⬇️ PDF
                </button>
              </div>
            )}
            <Link href="/admin" className="text-sm font-normal opacity-80 hover:opacity-100">
              ⚙️ Configurações
            </Link>
          </div>
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

                {m.imagem_url && m.imagem_url_costas ? (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={m.imagem_url} alt="Vista frontal (desenho técnico)" className="rounded-lg w-full" />
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={m.imagem_url_costas} alt="Vista traseira (desenho técnico)" className="rounded-lg w-full" />
                  </div>
                ) : (
                  m.imagem_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.imagem_url} alt="Croqui gerado pela IA" className="mt-2 rounded-lg max-w-full" />
                  )
                )}

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

          {pendenteConfirmacao && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-white border border-gray-200 rounded-bl-sm space-y-2">
                <p className="text-sm text-gray-700">
                  <strong>Entendi que você quer:</strong>{" "}
                  {typeof pendenteConfirmacao.resumo_confirmacao === "string"
                    ? pendenteConfirmacao.resumo_confirmacao
                    : ""}
                </p>
                <p className="text-xs text-gray-500">Por favor, confirme antes de gerar a imagem:</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => resolverConfirmacao(true)}
                    disabled={carregando}
                    className="rounded-lg px-3 py-1.5 text-sm text-white font-medium disabled:opacity-40"
                    style={{ backgroundColor: corPrimaria }}
                  >
                    ✅ Confirmar e gerar imagem
                  </button>
                  <button
                    onClick={() => resolverConfirmacao(false)}
                    disabled={carregando}
                    className="rounded-lg px-3 py-1.5 text-sm border border-gray-300 text-gray-700 disabled:opacity-40"
                  >
                    ✏️ Não é isso
                  </button>
                </div>
              </div>
            </div>
          )}

          {carregando && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-2 text-gray-400">
                {modo === "Gerador de Croqui" ? "Pensando no seu croqui..." : "Pesquisando na base de documentos..."}
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
              disabled={!!pendenteConfirmacao}
              placeholder={pendenteConfirmacao ? "Responda a confirmação acima antes de continuar..." : "Digite sua pergunta..."}
              rows={1}
              className="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
            <button
              onClick={enviar}
              disabled={carregando || !entrada.trim() || !!pendenteConfirmacao}
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
