"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, adminLogin, deletarDocumento, listarDocumentos, uploadDocumento } from "@/lib/api";
import { APP_NOME } from "@/lib/branding";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FileText, Loader2, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
const CHAVE_SESSAO_ADMIN = "labfashion_admin_ok";

export default function AdminPage() {
  const [autorizado, setAutorizado] = useState(false);
  const [senha, setSenha] = useState("");
  const [erroLogin, setErroLogin] = useState<string | null>(null);
  const [validandoLogin, setValidandoLogin] = useState(false);

  const [documentos, setDocumentos] = useState<string[]>([]);
  const [carregandoDocs, setCarregandoDocs] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const inputArquivoRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (typeof window !== "undefined" && window.sessionStorage.getItem(CHAVE_SESSAO_ADMIN) === "1") {
      setAutorizado(true);
    }
  }, []);

  useEffect(() => {
    if (autorizado) {
      recarregarDocumentos();
    }
  }, [autorizado]);

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
      const ok = await adminLogin(TENANT_ID, senha);
      if (ok) {
        setAutorizado(true);
        window.sessionStorage.setItem(CHAVE_SESSAO_ADMIN, "1");
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
    if (!arquivo) return;

    setEnviando(true);
    try {
      const resultado = await uploadDocumento(TENANT_ID, arquivo);
      toast.success(`"${resultado.nome_arquivo}" indexado com sucesso (${resultado.chunks_indexados} trechos).`);
      if (inputArquivoRef.current) inputArquivoRef.current.value = "";
      await recarregarDocumentos();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Falha ao enviar o arquivo.");
    } finally {
      setEnviando(false);
    }
  }

  async function excluirDocumento(nome: string) {
    if (!window.confirm(`Remover "${nome}" da Base de Conhecimento?`)) return;
    try {
      await deletarDocumento(TENANT_ID, nome);
      await recarregarDocumentos();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Falha ao remover o documento.");
    }
  }

  if (!autorizado) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
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
              <Link href="/" className="block text-center text-sm text-muted-foreground hover:text-foreground">
                ← Voltar ao chat
              </Link>
            </CardContent>
          </Card>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-foreground">Base de Conhecimento — {APP_NOME}</h1>
        <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
          ← Voltar ao chat
        </Link>
      </div>

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
