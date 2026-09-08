"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ApiError,
  ArquivoAnexado,
  Conversa,
  GraficoBarrasDados,
  MensagemConversa,
  PendenteConfirmacao,
  ResumoEstatistico,
  atualizarConversa,
  baixarExportacaoConversa,
  confirmarCroqui,
  criarConversa,
  deletarConversa,
  enviarMensagemChat,
  listarConversas,
  uploadPlanilha,
} from "@/lib/api";
import { obterPerfilAtivo, definirPerfilAtivo, limparPerfilAtivo, obterUsuarioId } from "@/lib/usuario";
import { APP_NOME, MENSAGEM_BOAS_VINDAS } from "@/lib/branding";
import ConversasHistorico from "@/components/ConversasHistorico";
import ImagemGerada from "@/components/ImagemGerada";
import GraficoBarras from "@/components/GraficoBarras";
import SeletorModo from "@/components/SeletorModo";
import SeletorPerfil from "@/components/SeletorPerfil";
import { MODOS_DISPONIVEIS, ehModoDeAgente } from "@/lib/modos";
import { MODO_PADRAO_POR_PERFIL, PERGUNTAS_POR_PERFIL, PerfilId } from "@/lib/perfis";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { badgeVariants } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Bot, Download, Loader2, Paperclip, Palette, Ruler, Send, Settings, X } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import { toast } from "sonner";
import { AnimatePresence, motion } from "motion/react";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
const SUGESTOES_POR_MODO: Record<string, string[]> = {
  "Base de Conhecimento": [
    "Qual a diferença entre viscose e algodão?",
    "Como calcular o consumo de tecido para um vestido godê?",
    "Quais os principais tipos de costura para malha?",
  ],
  "Gerador de Croqui": [
    "Crie um croqui de vestido midi em linho",
    "Gere um desenho técnico de uma calça wide leg",
    "Ilustre uma jaqueta jeans oversized",
  ],
  "Consultor de Estilo": [
    "Quais cores combinam com verde oliva?",
    "Sugira um look casual elegante masculino.",
    "Como valorizar a silhueta ampulheta?",
  ],
  "Professor Técnico": [
    "Qual agulha usar para costurar seda?",
    "Como fazer a graduação de moldes?",
    "Explique a diferença entre urdume e trama.",
  ],
  "Tendências": [
    "Quais as cores tendência para esta estação?",
    "O que é upcycling na moda atual?",
    "Quais macro-tendências vêm da Geração Z?",
  ],
  "Análise de Dados": [
    "Qual o resumo geral e principais totais da planilha?",
    "Quais são os itens ou categorias mais frequentes?",
    "Quais métricas e médias foram identificadas?",
  ],
};
const ESTILO_ILUSTRACAO = "🎨 Ilustração de Moda";
const ESTILO_TECNICO = "📐 Desenho Técnico (Flat Sketch)";

function embaralhar<T>(lista: T[]): T[] {
  const copia = [...lista];
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

// Extrai um gráfico simples (top 10) da primeira combinação categoria x métrica que o backend
// já pré-calculou (analise_dados.py:gerar_resumo_estatistico) -- sem chamada extra ao LLM.
function extrairGraficoDoResumo(resumo: ResumoEstatistico | undefined): GraficoBarrasDados | null {
  const agregacoes = resumo?.agregacoes;
  if (!agregacoes) return null;

  const primeiraCategoria = Object.keys(agregacoes)[0];
  if (!primeiraCategoria) return null;
  const metricas = agregacoes[primeiraCategoria];
  const primeiraMetrica = Object.keys(metricas)[0];
  if (!primeiraMetrica) return null;

  const top10 = metricas[primeiraMetrica].top_10;
  const itens = Object.entries(top10).map(([rotulo, valor]) => ({ rotulo, valor }));
  if (!itens.length) return null;

  return { titulo: `${primeiraMetrica} por ${primeiraCategoria} (top ${itens.length})`, itens };
}

function sugestoesBase(modoAlvo: string, perfilAlvo: string | null): string[] {
  return (
    (perfilAlvo ? PERGUNTAS_POR_PERFIL[perfilAlvo as PerfilId]?.[modoAlvo] : undefined) ??
    SUGESTOES_POR_MODO[modoAlvo] ??
    []
  );
}

export default function ChatPage() {
  const [usuarioId, setUsuarioId] = useState<string | null>(null);
  const [conversas, setConversas] = useState<Conversa[]>([]);
  const [conversaAtualId, setConversaAtualId] = useState<string | null>(null);
  const [mensagens, setMensagens] = useState<MensagemConversa[]>([]);
  const [entrada, setEntrada] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [modo, setModo] = useState(MODOS_DISPONIVEIS[0]);
  const [estiloCroqui, setEstiloCroqui] = useState(ESTILO_ILUSTRACAO);
  const [pendenteConfirmacao, setPendenteConfirmacao] = useState<PendenteConfirmacao | null>(null);
  const [enviandoPlanilha, setEnviandoPlanilha] = useState(false);
  const [arquivoAnexado, setArquivoAnexado] = useState<ArquivoAnexado | null>(null);
  const [perfilAtivo, setPerfilAtivo] = useState<string | null>(null);
  const [sugestoesAtuais, setSugestoesAtuais] = useState<string[]>(() => embaralhar(sugestoesBase(MODOS_DISPONIVEIS[0], null)));
  const fimDaListaRef = useRef<HTMLDivElement>(null);
  const inputPlanilhaRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const uid = obterUsuarioId();
    setUsuarioId(uid);
    const perfilSalvo = obterPerfilAtivo();
    setPerfilAtivo(perfilSalvo);
    setSugestoesAtuais(embaralhar(sugestoesBase(MODOS_DISPONIVEIS[0], perfilSalvo)));

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
      .catch(() => toast.error("Não foi possível carregar as conversas."));
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
  }

  function selecionarPerfil(perfil: string) {
    definirPerfilAtivo(perfil);
    setPerfilAtivo(perfil);
    const modoPadrao = MODO_PADRAO_POR_PERFIL[perfil as PerfilId];
    const modoAlvo = modoPadrao ?? modo;
    if (modoPadrao) {
      setModo(modoPadrao);
      setPendenteConfirmacao(null);
    }
    setSugestoesAtuais(embaralhar(sugestoesBase(modoAlvo, perfil)));
  }

  function limparPerfil() {
    limparPerfilAtivo();
    setPerfilAtivo(null);
    setSugestoesAtuais(embaralhar(sugestoesBase(modo, null)));
  }

  async function novaConversa() {
    if (!usuarioId) return;
    try {
      const nova = await criarConversa(TENANT_ID, usuarioId);
      setConversas((atual) => [...atual, nova]);
      setConversaAtualId(nova.id);
      setMensagens([]);
      setPendenteConfirmacao(null);
    } catch (e) {
      toast.error(mensagemDeErro(e, "criar conversa"));
    }
  }

  async function renomearConversaAtual(id: string, novoTitulo: string) {
    if (!usuarioId) return;
    try {
      const atualizada = await atualizarConversa(TENANT_ID, usuarioId, id, { novoTitulo });
      setConversas((atual) => atual.map((c) => (c.id === id ? atualizada : c)));
    } catch (e) {
      toast.error(mensagemDeErro(e, "renomear conversa"));
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
      toast.error(mensagemDeErro(e, "excluir conversa"));
    }
  }

  async function exportarConversaAtual(formato: "txt" | "pdf") {
    if (!usuarioId || !conversaAtualId) return;
    try {
      await baixarExportacaoConversa(TENANT_ID, usuarioId, conversaAtualId, formato);
    } catch (e) {
      toast.error(mensagemDeErro(e, `exportar conversa em ${formato.toUpperCase()}`));
    }
  }

  async function anexarPlanilha(arquivo: File) {
    if (!conversaAtualId) return;
    setEnviandoPlanilha(true);
    try {
      const resultado = await uploadPlanilha(TENANT_ID, conversaAtualId, arquivo);
      setArquivoAnexado({
        nome: resultado.nome_arquivo,
        linhas: resultado.linhas,
        colunas: resultado.colunas.length,
        grafico: extrairGraficoDoResumo(resultado.resumo_estatistico),
      });
      toast.success(`"${resultado.nome_arquivo}" anexada. Pode perguntar sobre os dados.`);
    } catch (e) {
      toast.error(mensagemDeErro(e, "enviar planilha"));
    } finally {
      setEnviandoPlanilha(false);
      if (inputPlanilhaRef.current) inputPlanilhaRef.current.value = "";
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
      { role: "user", content: texto, tenant_id: TENANT_ID, arquivo_anexado: arquivoAnexado },
    ];
    setMensagens(mensagensComUsuario);
    setEntrada("");
    setArquivoAnexado(null);
    setCarregando(true);

    try {
      const resposta = await enviarMensagemChat({
        tenantId: TENANT_ID,
        mensagem: texto,
        modo,
        conversationId: conversaAtualId,
        historico: ehModoDeAgente(modo)
          ? mensagensComUsuario.map((m) => ({ role: m.role, content: m.content }))
          : undefined,
        estiloCroqui: modo === "Gerador de Croqui" ? estiloCroqui : undefined,
        perfilUsuario: perfilAtivo,
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
          trechos_consultados: resposta.trechos_consultados,
          imagem_url: resposta.imagem_url ?? null,
        },
      ];
      setMensagens(mensagensFinais);
      await persistirMensagens(mensagensFinais);
    } catch (e) {
      toast.error(mensagemDeErro(e, "enviar mensagem"));
    } finally {
      setCarregando(false);
    }
  }

  async function resolverConfirmacao(confirmado: boolean) {
    if (!pendenteConfirmacao) return;
    setCarregando(true);
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
      toast.error(mensagemDeErro(e, "confirmar geração de imagem"));
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

  return (
    <div className="flex h-screen w-full flex-col">
      <header className="h-14 shrink-0 px-4 border-b border-border bg-card text-foreground flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <ConversasHistorico
              conversas={conversas}
              conversaAtualId={conversaAtualId}
              onSelecionar={selecionarConversa}
              onNovaConversa={novaConversa}
              onRenomear={renomearConversaAtual}
              onDeletar={excluirConversa}
            />
            <Image src="/logo.png" alt={APP_NOME} width={430} height={124} priority className="h-8 w-auto shrink-0" />
            <SeletorModo
              modoAtivo={modo}
              perfilAtivo={perfilAtivo}
              onSelecionar={(novoModo) => {
                setModo(novoModo);
                setPendenteConfirmacao(null);
                setSugestoesAtuais(embaralhar(sugestoesBase(novoModo, perfilAtivo)));
              }}
            />
            <SeletorPerfil perfilAtivo={perfilAtivo} onSelecionar={selecionarPerfil} onLimpar={limparPerfil} />
            {modo === "Gerador de Croqui" && (
              <ToggleGroup
                value={[estiloCroqui]}
                onValueChange={(valores) => valores.length > 0 && setEstiloCroqui(valores[0])}
                variant="outline"
                size="sm"
              >
                <ToggleGroupItem value={ESTILO_ILUSTRACAO} className="gap-1.5 text-sm">
                  <Palette className="h-3.5 w-3.5" />
                  Ilustração
                </ToggleGroupItem>
                <ToggleGroupItem value={ESTILO_TECNICO} className="gap-1.5 text-sm">
                  <Ruler className="h-3.5 w-3.5" />
                  Desenho Técnico
                </ToggleGroupItem>
              </ToggleGroup>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {mensagens.length > 0 && (
              <div className="flex gap-1 text-sm font-normal">
                <button
                  onClick={() => exportarConversaAtual("txt")}
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                  title="Baixar conversa em TXT"
                >
                  <Download className="h-3.5 w-3.5" />
                  TXT
                </button>
                <button
                  onClick={() => exportarConversaAtual("pdf")}
                  className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                  title="Baixar conversa em PDF"
                >
                  <Download className="h-3.5 w-3.5" />
                  PDF
                </button>
              </div>
            )}
            <Link
              href="/admin"
              className="inline-flex items-center gap-1 text-sm font-normal text-muted-foreground hover:text-foreground"
            >
              <Settings className="h-3.5 w-3.5" />
              Configurações
            </Link>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-4 bg-background">
          <div className="max-w-3xl mx-auto space-y-4">
          <AnimatePresence mode="wait">
            {mensagens.length === 0 && !carregando && (
              <motion.div
                key={modo}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="mt-12 flex flex-col items-center text-center gap-4"
              >
                <Avatar className="h-12 w-12">
                  <AvatarFallback className="bg-secondary text-secondary-foreground">
                    <Bot className="h-6 w-6" />
                  </AvatarFallback>
                </Avatar>
                <p className="text-muted-foreground max-w-md">{MENSAGEM_BOAS_VINDAS}</p>
                <div className="flex flex-col gap-2 w-full max-w-md">
                  {sugestoesAtuais.map((sugestao) => (
                    <Button
                      key={sugestao}
                      variant="outline"
                      className="h-auto justify-start whitespace-normal text-left py-2.5 px-3.5 font-normal text-foreground"
                      onClick={() => setEntrada(sugestao)}
                    >
                      {sugestao}
                    </Button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {mensagens.map((m, i) => (
            <motion.div
              key={i}
              initial={i === mensagens.length - 1 ? { opacity: 0, y: 6 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "assistant" && (
                <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                  <AvatarFallback className="bg-secondary text-secondary-foreground">
                    <Bot className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
              )}
              <div
                className={`max-w-[80%] min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere] ${
                  m.role === "user"
                    ? "rounded-2xl rounded-br-sm px-4 py-2 bg-primary text-primary-foreground"
                    : "text-foreground"
                }`}
              >
                {m.arquivo_anexado && (
                  <div className="mb-1.5 flex w-fit items-center gap-1.5 rounded-lg bg-primary-foreground/15 px-2.5 py-1.5 text-xs">
                    <Paperclip className="h-3.5 w-3.5" />
                    <span className="font-medium">{m.arquivo_anexado.nome}</span>
                    <span className="opacity-80">
                      ({m.arquivo_anexado.linhas} linhas, {m.arquivo_anexado.colunas} colunas)
                    </span>
                  </div>
                )}
                {m.arquivo_anexado?.grafico && <GraficoBarras dados={m.arquivo_anexado.grafico} />}
                {m.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-headings:mt-3 prose-headings:mb-1.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  m.content
                )}

                {m.imagem_url && m.imagem_url_costas ? (
                  <div className="mt-2 grid grid-cols-2 gap-2 max-w-xs">
                    <div className="space-y-1">
                      <ImagemGerada src={m.imagem_url} alt="Vista frontal (desenho técnico)" />
                      <p className="text-center text-xs text-muted-foreground">Frente</p>
                    </div>
                    <div className="space-y-1">
                      <ImagemGerada src={m.imagem_url_costas} alt="Vista traseira (desenho técnico)" />
                      <p className="text-center text-xs text-muted-foreground">Costas</p>
                    </div>
                  </div>
                ) : (
                  m.imagem_url && (
                    <div className="mt-2 w-48">
                      <ImagemGerada src={m.imagem_url} alt="Croqui gerado pela IA" />
                    </div>
                  )
                )}

                {m.fontes_consultadas && m.fontes_consultadas.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.fontes_consultadas.map((f, fi) => {
                      const trecho = m.trechos_consultados?.[fi];
                      return (
                        <Popover key={fi}>
                          <PopoverTrigger
                            className={badgeVariants({
                              variant: "outline",
                              className: "cursor-pointer font-normal",
                            })}
                          >
                            {fi + 1}. {f}
                          </PopoverTrigger>
                          <PopoverContent className="text-xs">
                            <p className="font-medium text-foreground">{f}</p>
                            <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
                              {trecho?.texto ?? "Trecho não disponível para esta fonte."}
                            </p>
                          </PopoverContent>
                        </Popover>
                      );
                    })}
                  </div>
                )}
              </div>
            </motion.div>
          ))}

          {pendenteConfirmacao && (
            <motion.div
              initial={{ opacity: 0, y: 6, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.2 }}
              className="flex gap-3 justify-start"
            >
              <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                <AvatarFallback className="bg-secondary text-secondary-foreground">
                  <Bot className="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <Card className="max-w-[80%] border-2 border-primary bg-primary/[0.06] py-3 gap-2">
                <CardContent className="space-y-2">
                  <p className="text-sm">
                    <strong>Entendi que você quer:</strong>{" "}
                    {typeof pendenteConfirmacao.resumo_confirmacao === "string"
                      ? pendenteConfirmacao.resumo_confirmacao
                      : ""}
                  </p>
                  <p className="text-xs text-muted-foreground">Por favor, confirme antes de gerar a imagem:</p>
                  <div className="flex gap-2 pt-1">
                    <Button onClick={() => resolverConfirmacao(true)} disabled={carregando}>
                      Confirmar e gerar imagem
                    </Button>
                    <Button onClick={() => resolverConfirmacao(false)} disabled={carregando} variant="outline">
                      Não é isso
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {carregando && (
            <div className="flex gap-3 justify-start">
              <Avatar className="h-7 w-7 shrink-0 mt-0.5">
                <AvatarFallback className="bg-secondary text-secondary-foreground">
                  <Bot className="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {modo === "Gerador de Croqui" ? "Pensando no seu croqui..." : "Pesquisando na base de documentos..."}
              </div>
            </div>
          )}

          <div ref={fimDaListaRef} />
          </div>
        </main>

        <footer className="p-4 border-t border-border bg-card">
          <div className="max-w-3xl mx-auto">
          {arquivoAnexado && (
            <div className="mb-2 inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted px-2.5 py-1.5 text-xs text-foreground">
              <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-medium">{arquivoAnexado.nome}</span>
              <span className="text-muted-foreground">
                ({arquivoAnexado.linhas} linhas, {arquivoAnexado.colunas} colunas)
              </span>
              <button
                type="button"
                onClick={() => setArquivoAnexado(null)}
                className="ml-1 text-muted-foreground hover:text-foreground"
                aria-label="Remover anexo"
                title="Remover anexo"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="flex gap-2 items-end">
            {modo === "Análise de Dados" && (
              <>
                <input
                  ref={inputPlanilhaRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(e) => {
                    const arquivo = e.target.files?.[0];
                    if (arquivo) anexarPlanilha(arquivo);
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon-lg"
                  className="rounded-xl shrink-0"
                  disabled={enviandoPlanilha || !conversaAtualId}
                  onClick={() => inputPlanilhaRef.current?.click()}
                  aria-label="Anexar planilha"
                  title="Anexar planilha (CSV ou Excel)"
                >
                  {enviandoPlanilha ? <Loader2 className="animate-spin" /> : <Paperclip />}
                </Button>
              </>
            )}
            <Textarea
              value={entrada}
              onChange={(e) => setEntrada(e.target.value)}
              onKeyDown={aoPressionarTecla}
              disabled={!!pendenteConfirmacao}
              placeholder={
                pendenteConfirmacao
                  ? "Responda a confirmação acima antes de continuar..."
                  : modo === "Análise de Dados"
                  ? "Anexe uma planilha e pergunte sobre os dados..."
                  : "Digite sua pergunta..."
              }
              className="flex-1 max-h-40 overflow-y-auto resize-none rounded-xl min-h-11 py-2.5"
            />
            <Button
              onClick={enviar}
              disabled={carregando || !entrada.trim() || !!pendenteConfirmacao}
              size="icon-lg"
              className="rounded-xl shrink-0"
              aria-label="Enviar mensagem"
            >
              {carregando ? <Loader2 className="animate-spin" /> : <Send />}
            </Button>
          </div>
          </div>
        </footer>
    </div>
  );
}
