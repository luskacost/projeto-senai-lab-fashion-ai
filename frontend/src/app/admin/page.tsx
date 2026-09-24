"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ApiError,
  InfoLogo,
  Sugestao,
  adminLogin,
  deletarDocumento,
  deletarLogo,
  listarDocumentos,
  listarSugestoes,
  listarTodasSugestoes,
  obterInfoLogo,
  uploadDocumento,
  uploadLogo,
  urlLogo,
} from "@/lib/api";
import { APP_NOME } from "@/lib/branding";
import { definirTokenAdmin, limparTokenAdmin, obterTokenAdmin } from "@/lib/admin-sessao";
import { obterTenantIdAtivo } from "@/lib/acesso";
import { mensagemAmigavel } from "@/lib/erros";
import ConfirmarAcaoDialog from "@/components/ConfirmarAcaoDialog";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowLeft, FileText, ImageIcon, Loader2, MessageSquareWarning, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

// Fase 16, Bloco L: tenant deixou de ser fixo em tempo de build -- ver page.tsx (home) para a
// explicação completa. NEXT_PUBLIC_TENANT_ID vira só o fallback de modo legado.
function tenantIdAtivo(): string {
  return obterTenantIdAtivo() ?? process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
}
// Guarda o token de sessão de verdade (emitido por POST /admin/login e validado no backend em
// cada rota administrativa, Fase 9/Bloco B) -- não é mais um "1" opaco que só escondia o botão
// no front-end sem nenhuma checagem real do lado do servidor.

export default function AdminPage() {
  const [tokenAdmin, setTokenAdmin] = useState<string | null>(null);
  const [senha, setSenha] = useState("");
  const [erroLogin, setErroLogin] = useState<string | null>(null);
  const [validandoLogin, setValidandoLogin] = useState(false);

  const [documentos, setDocumentos] = useState<string[]>([]);
  const [carregandoDocs, setCarregandoDocs] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const inputArquivoRef = useRef<HTMLInputElement>(null);

  const [confirmandoRemocaoLogo, setConfirmandoRemocaoLogo] = useState(false);
  const [documentoPendenteDeRemocao, setDocumentoPendenteDeRemocao] = useState<string | null>(null);
  const [infoLogo, setInfoLogo] = useState<InfoLogo | null>(null);
  const [enviandoLogo, setEnviandoLogo] = useState(false);
  // Muda a cada upload/remoção para furar o cache do navegador -- a URL do logo é sempre a mesma.
  const [versaoLogo, setVersaoLogo] = useState(() => Date.now());
  const inputLogoRef = useRef<HTMLInputElement>(null);

  const [sugestoes, setSugestoes] = useState<Sugestao[]>([]);
  const [carregandoSugestoes, setCarregandoSugestoes] = useState(false);
  // `null` = ou ainda carregando, ou este tenant não é o TENANT_DONO (backend recusou com 401,
  // tratado como "sem visão agregada" em vez de erro -- ver listarTodasSugestoes em lib/api.ts).
  // Quando vier preenchido, a seção mostra o conteúdo de TODOS os tenants agrupado, em vez de só
  // o do próprio tenant logado.
  const [sugestoesTodas, setSugestoesTodas] = useState<Record<string, Sugestao[]> | null>(null);

  useEffect(() => {
    const tokenSalvo = obterTokenAdmin();
    if (tokenSalvo) setTokenAdmin(tokenSalvo);
  }, []);

  useEffect(() => {
    if (tokenAdmin) {
      recarregarDocumentos();
      recarregarLogo();
      recarregarSugestoes();
    }
  }, [tokenAdmin]);

  // Se o token expirou (ex: passou das 4h) ou foi revogado, qualquer chamada administrativa
  // retorna 401 -- desloga de volta pra tela de login em vez de mostrar um erro confuso.
  function tratarErroAdmin(e: unknown, mensagemPadrao: string) {
    if (e instanceof ApiError && e.status === 401) {
      limparTokenAdmin();
      setTokenAdmin(null);
      toast.error("Sessão de administrador expirada. Faça login novamente.");
      return;
    }
    toast.error(mensagemAmigavel(e, mensagemPadrao));
  }

  async function recarregarDocumentos() {
    setCarregandoDocs(true);
    try {
      const lista = await listarDocumentos(tenantIdAtivo());
      setDocumentos(lista);
    } catch {
      toast.error("Não foi possível carregar a lista de documentos.");
    } finally {
      setCarregandoDocs(false);
    }
  }

  // Fase 16, Bloco S: listagem read-only das sugestões/reportes enviados pelos usuários -- não é
  // uma tela de revisão à parte, só uma seção a mais dentro do painel administrativo já existente.
  async function recarregarSugestoes() {
    if (!tokenAdmin) return;
    setCarregandoSugestoes(true);
    try {
      const [lista, todas] = await Promise.all([
        listarSugestoes(tenantIdAtivo(), tokenAdmin),
        listarTodasSugestoes(tokenAdmin),
      ]);
      setSugestoes(lista.slice().reverse()); // mais recente primeiro
      setSugestoesTodas(todas);
    } catch (e) {
      tratarErroAdmin(e, "Não foi possível carregar as sugestões.");
    } finally {
      setCarregandoSugestoes(false);
    }
  }

  async function fazerLogin(e: React.FormEvent) {
    e.preventDefault();
    setValidandoLogin(true);
    setErroLogin(null);
    try {
      const token = await adminLogin(tenantIdAtivo(), senha);
      if (token) {
        setTokenAdmin(token);
        definirTokenAdmin(token);
      } else {
        setErroLogin("Senha incorreta.");
      }
    } catch (e) {
      setErroLogin(mensagemAmigavel(e, "Não foi possível entrar. Tente novamente."));
    } finally {
      setValidandoLogin(false);
    }
  }

  async function enviarArquivo() {
    const arquivo = inputArquivoRef.current?.files?.[0];
    if (!arquivo || !tokenAdmin) return;

    setEnviando(true);
    try {
      const resultado = await uploadDocumento(tenantIdAtivo(), arquivo, tokenAdmin);
      toast.success(`"${resultado.nome_arquivo}" adicionado com sucesso.`);
      if (inputArquivoRef.current) inputArquivoRef.current.value = "";
      await recarregarDocumentos();
    } catch (e) {
      tratarErroAdmin(e, "Falha ao enviar o arquivo.");
    } finally {
      setEnviando(false);
    }
  }

  async function recarregarLogo() {
    try {
      setInfoLogo(await obterInfoLogo(tenantIdAtivo()));
    } catch {
      toast.error("Não foi possível verificar o logo cadastrado.");
    }
  }

  async function enviarLogo() {
    const arquivo = inputLogoRef.current?.files?.[0];
    if (!arquivo || !tokenAdmin) return;

    setEnviandoLogo(true);
    try {
      await uploadLogo(tenantIdAtivo(), arquivo, tokenAdmin);
      toast.success("Logo atualizado. Ele será usado nas próximas fichas geradas.");
      if (inputLogoRef.current) inputLogoRef.current.value = "";
      setVersaoLogo(Date.now());
      await recarregarLogo();
    } catch (e) {
      tratarErroAdmin(e, "Falha ao enviar o logo.");
    } finally {
      setEnviandoLogo(false);
    }
  }

  async function removerLogo() {
    if (!tokenAdmin) return;
    try {
      await deletarLogo(tenantIdAtivo(), tokenAdmin);
      setVersaoLogo(Date.now());
      await recarregarLogo();
    } catch (e) {
      tratarErroAdmin(e, "Falha ao remover o logo.");
    }
  }

  async function excluirDocumento(nome: string) {
    if (!tokenAdmin) return;
    try {
      await deletarDocumento(tenantIdAtivo(), nome, tokenAdmin);
      await recarregarDocumentos();
    } catch (e) {
      tratarErroAdmin(e, "Falha ao remover o documento.");
    }
  }

  if (!tokenAdmin) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-background">
        <Image src="/logo.png" alt={APP_NOME} width={430} height={124} priority className="h-10 w-auto" />
        <form onSubmit={fazerLogin} className="w-full max-w-sm">
          <Card>
            <CardHeader>
              <CardTitle>Acesso administrativo</CardTitle>
              <CardDescription>Informe a senha de administrador para gerenciar a Base de Conhecimento.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                placeholder="Senha"
                autoFocus
              />
              {erroLogin && <p className="text-sm text-destructive">{erroLogin}</p>}
              <Button type="submit" disabled={validandoLogin || !senha} className="w-full">
                {validandoLogin && <Loader2 className="animate-spin" />}
                {validandoLogin ? "Validando..." : "Entrar"}
              </Button>
              <Link
                href="/"
                className="flex items-center justify-center gap-1 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Voltar ao chat
              </Link>
            </CardContent>
          </Card>
        </form>
      </div>
    );
  }

  // Agregado (todos os tenants, com tenantId anexado) quando disponível -- só o TENANT_DONO
  // recebe `sugestoesTodas` preenchido (ver listarTodasSugestoes em lib/api.ts). Caso contrário,
  // cai no comportamento de sempre: só as sugestões do próprio tenant logado.
  const itensSugestoesExibidos: (Sugestao & { tenantId?: string })[] = sugestoesTodas
    ? Object.entries(sugestoesTodas)
        .flatMap(([tid, lista]) => lista.map((s) => ({ ...s, tenantId: tid })))
        .sort((a, b) => new Date(b.criado_em).getTime() - new Date(a.criado_em).getTime())
    : sugestoes;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Base de Conhecimento — {APP_NOME}</h1>
        <Link href="/" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar ao chat
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Logo da empresa</CardTitle>
          <CardDescription>
            Usado no cabeçalho das fichas técnicas geradas. Envie uma vez — ele é reaproveitado em
            todas as fichas. Formatos aceitos: PNG ou JPG (máx. 5MB).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {infoLogo?.cadastrado ? (
            <div className="flex items-center gap-4 rounded-lg border border-border p-3">
              {/* <img> em vez de next/image: a URL vem da API com cache-buster e não passa pelo
                  otimizador do Next, que exigiria configurar o domínio remoto. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={urlLogo(tenantIdAtivo(), versaoLogo)}
                alt="Logo cadastrado"
                className="h-12 w-auto max-w-40 object-contain"
              />
              <div className="min-w-0 flex-1 text-sm">
                <p className="truncate text-foreground">{infoLogo.metadados?.nome_original || "logo"}</p>
                <p className="text-xs text-muted-foreground">
                  {infoLogo.metadados?.largura_px}×{infoLogo.metadados?.altura_px} px
                </p>
              </div>
              <Button
                onClick={() => setConfirmandoRemocaoLogo(true)}
                variant="ghost"
                size="icon-sm"
                className="shrink-0 text-muted-foreground hover:text-destructive"
                aria-label="Remover logo"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-lg border border-dashed border-border p-3 text-sm text-muted-foreground">
              <ImageIcon className="h-4 w-4 shrink-0" />
              Nenhum logo cadastrado — as fichas serão geradas com a área do logo em branco.
            </div>
          )}

          <div className="flex gap-2">
            <input
              ref={inputLogoRef}
              type="file"
              accept=".png,.jpg,.jpeg"
              className="flex-1 text-sm text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium"
            />
            <Button onClick={enviarLogo} disabled={enviandoLogo} className="shrink-0">
              {enviandoLogo ? <Loader2 className="animate-spin" /> : <Upload />}
              {enviandoLogo ? "Enviando..." : infoLogo?.cadastrado ? "Substituir" : "Enviar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Adicionar novo documento</CardTitle>
          <CardDescription>Formatos aceitos: PDF, Word, TXT, Markdown, CSV, Excel, PowerPoint. O assistente passa a poder responder perguntas sobre o conteúdo deste arquivo no modo "Base de Conhecimento".</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <input
              ref={inputArquivoRef}
              type="file"
              className="flex-1 text-sm text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium"
            />
            <Button onClick={enviarArquivo} disabled={enviando} className="shrink-0">
              {enviando ? <Loader2 className="animate-spin" /> : <Upload />}
              {enviando ? "Adicionando..." : "Adicionar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Documentos disponíveis ({documentos.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {carregandoDocs ? (
            <ul className="divide-y divide-border">
              {[0, 1, 2].map((i) => (
                <li key={i} className="flex items-center gap-2 py-2">
                  <Skeleton className="h-4 w-4 shrink-0 rounded" />
                  <Skeleton className="h-4 w-48 max-w-[60%]" />
                </li>
              ))}
            </ul>
          ) : documentos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum documento foi cadastrado ainda.</p>
          ) : (
            <ul className="divide-y divide-border">
              {documentos.map((doc) => (
                <li key={doc} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="flex items-center gap-2 min-w-0 truncate text-foreground">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {doc}
                  </span>
                  <Button
                    onClick={() => setDocumentoPendenteDeRemocao(doc)}
                    variant="ghost"
                    size="icon-sm"
                    className="shrink-0 text-muted-foreground hover:text-destructive"
                    aria-label="Remover"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Sugestões e reportes de erro ({itensSugestoesExibidos.length})
          </CardTitle>
          <CardDescription>
            {sugestoesTodas
              ? "Enviados pelos usuários através da tela \"Sugestões\" -- de todos os consultores."
              : "Enviados pelos usuários através da tela \"Sugestões\"."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {carregandoSugestoes ? (
            <ul className="divide-y divide-border">
              {[0, 1].map((i) => (
                <li key={i} className="flex items-center gap-2 py-2">
                  <Skeleton className="h-4 w-4 shrink-0 rounded" />
                  <Skeleton className="h-4 w-64 max-w-[70%]" />
                </li>
              ))}
            </ul>
          ) : itensSugestoesExibidos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma sugestão ou reporte ainda.</p>
          ) : (
            <ul className="divide-y divide-border">
              {itensSugestoesExibidos.map((s) => (
                <li key={`${s.tenantId ?? ""}-${s.id}`} className="space-y-1 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant={s.tipo === "bug" ? "destructive" : "secondary"} className="gap-1">
                      <MessageSquareWarning className="h-3 w-3" />
                      {s.tipo === "bug" ? "Erro" : "Sugestão"}
                    </Badge>
                    {s.tenantId && <Badge variant="outline">{s.tenantId}</Badge>}
                    <span className="text-xs text-muted-foreground">
                      {new Date(s.criado_em).toLocaleString("pt-BR")}
                    </span>
                  </div>
                  <p className="text-foreground whitespace-pre-wrap">{s.texto}</p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ConfirmarAcaoDialog
        open={confirmandoRemocaoLogo}
        onOpenChange={setConfirmandoRemocaoLogo}
        titulo="Remover logo"
        descricao="As fichas técnicas passarão a ser geradas sem o logo da empresa."
        textoConfirmar="Remover"
        onConfirmar={removerLogo}
      />
      <ConfirmarAcaoDialog
        open={documentoPendenteDeRemocao !== null}
        onOpenChange={(aberto) => { if (!aberto) setDocumentoPendenteDeRemocao(null); }}
        titulo="Remover documento"
        descricao={`Remover "${documentoPendenteDeRemocao}" da Base de Conhecimento? Isso não pode ser desfeito.`}
        textoConfirmar="Remover"
        onConfirmar={() => {
          if (documentoPendenteDeRemocao) excluirDocumento(documentoPendenteDeRemocao);
        }}
      />
    </div>
  );
}
