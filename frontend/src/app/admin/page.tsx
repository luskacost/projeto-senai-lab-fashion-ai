"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ApiError,
  InfoLogo,
  adminLogin,
  deletarDocumento,
  deletarLogo,
  listarDocumentos,
  obterInfoLogo,
  uploadDocumento,
  uploadLogo,
  urlLogo,
} from "@/lib/api";
import { APP_NOME } from "@/lib/branding";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowLeft, FileText, ImageIcon, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
// Guarda o token de sessão de verdade (emitido por POST /admin/login e validado no backend em
// cada rota administrativa, Fase 9/Bloco B) -- não é mais um "1" opaco que só escondia o botão
// no front-end sem nenhuma checagem real do lado do servidor.
const CHAVE_SESSAO_ADMIN = "labfashion_admin_token";

export default function AdminPage() {
  const [tokenAdmin, setTokenAdmin] = useState<string | null>(null);
  const [senha, setSenha] = useState("");
  const [erroLogin, setErroLogin] = useState<string | null>(null);
  const [validandoLogin, setValidandoLogin] = useState(false);

  const [documentos, setDocumentos] = useState<string[]>([]);
  const [carregandoDocs, setCarregandoDocs] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const inputArquivoRef = useRef<HTMLInputElement>(null);

  const [infoLogo, setInfoLogo] = useState<InfoLogo | null>(null);
  const [enviandoLogo, setEnviandoLogo] = useState(false);
  // Muda a cada upload/remoção para furar o cache do navegador -- a URL do logo é sempre a mesma.
  const [versaoLogo, setVersaoLogo] = useState(() => Date.now());
  const inputLogoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const tokenSalvo = window.sessionStorage.getItem(CHAVE_SESSAO_ADMIN);
      if (tokenSalvo) setTokenAdmin(tokenSalvo);
    }
  }, []);

  useEffect(() => {
    if (tokenAdmin) {
      recarregarDocumentos();
      recarregarLogo();
    }
  }, [tokenAdmin]);

  // Se o token expirou (ex: passou das 4h) ou foi revogado, qualquer chamada administrativa
  // retorna 401 -- desloga de volta pra tela de login em vez de mostrar um erro confuso.
  function tratarErroAdmin(e: unknown, mensagemPadrao: string) {
    if (e instanceof ApiError && e.status === 401) {
      window.sessionStorage.removeItem(CHAVE_SESSAO_ADMIN);
      setTokenAdmin(null);
      toast.error("Sessão de administrador expirada. Faça login novamente.");
      return;
    }
    toast.error(e instanceof ApiError ? e.message : mensagemPadrao);
  }

  async function recarregarDocumentos() {
    setCarregandoDocs(true);
    try {
      const lista = await listarDocumentos(TENANT_ID);
      setDocumentos(lista);
    } catch {
      toast.error("Não foi possível carregar a lista de documentos.");
    } finally {
      setCarregandoDocs(false);
    }
  }

  async function fazerLogin(e: React.FormEvent) {
    e.preventDefault();
    setValidandoLogin(true);
    setErroLogin(null);
    try {
      const token = await adminLogin(TENANT_ID, senha);
      if (token) {
        setTokenAdmin(token);
        window.sessionStorage.setItem(CHAVE_SESSAO_ADMIN, token);
      } else {
        setErroLogin("Senha incorreta.");
      }
    } catch (e) {
      setErroLogin(e instanceof ApiError ? e.message : "Falha ao conectar com a API.");
    } finally {
      setValidandoLogin(false);
    }
  }

  async function enviarArquivo() {
    const arquivo = inputArquivoRef.current?.files?.[0];
    if (!arquivo || !tokenAdmin) return;

    setEnviando(true);
    try {
      const resultado = await uploadDocumento(TENANT_ID, arquivo, tokenAdmin);
      toast.success(`"${resultado.nome_arquivo}" indexado com sucesso (${resultado.chunks_indexados} trechos).`);
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
      setInfoLogo(await obterInfoLogo(TENANT_ID));
    } catch {
      toast.error("Não foi possível verificar o logo cadastrado.");
    }
  }

  async function enviarLogo() {
    const arquivo = inputLogoRef.current?.files?.[0];
    if (!arquivo || !tokenAdmin) return;

    setEnviandoLogo(true);
    try {
      await uploadLogo(TENANT_ID, arquivo, tokenAdmin);
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
    if (!tokenAdmin || !window.confirm("Remover o logo da empresa? As fichas passarão a ser geradas sem ele.")) return;
    try {
      await deletarLogo(TENANT_ID, tokenAdmin);
      setVersaoLogo(Date.now());
      await recarregarLogo();
    } catch (e) {
      tratarErroAdmin(e, "Falha ao remover o logo.");
    }
  }

  async function excluirDocumento(nome: string) {
    if (!tokenAdmin || !window.confirm(`Remover "${nome}" da Base de Conhecimento?`)) return;
    try {
      await deletarDocumento(TENANT_ID, nome, tokenAdmin);
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
                src={urlLogo(TENANT_ID, versaoLogo)}
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
                onClick={removerLogo}
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
          <CardTitle>Indexar novo documento</CardTitle>
          <CardDescription>Formatos aceitos: PDF, Word, TXT, Markdown, CSV, Excel, PowerPoint.</CardDescription>
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
              {enviando ? "Enviando..." : "Indexar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Documentos indexados ({documentos.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {carregandoDocs ? (
            <p className="text-sm text-muted-foreground">Carregando...</p>
          ) : documentos.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum documento indexado ainda.</p>
          ) : (
            <ul className="divide-y divide-border">
              {documentos.map((doc) => (
                <li key={doc} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span className="flex items-center gap-2 min-w-0 truncate text-foreground">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {doc}
                  </span>
                  <Button
                    onClick={() => excluirDocumento(doc)}
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
    </div>
  );
}
