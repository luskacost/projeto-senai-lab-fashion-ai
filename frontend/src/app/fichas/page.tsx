"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  ApiError,
  FichaResumo,
  criarFicha,
  deletarFicha,
  duplicarFicha,
  listarFichas,
} from "@/lib/api";
import { ROTULO_STATUS_FICHA, VARIANTE_STATUS_FICHA } from "@/lib/fichas-status";
import { APP_NOME } from "@/lib/branding";
import { limparTokenAdmin, obterTokenAdmin } from "@/lib/admin-sessao";
import { obterTenantIdAtivo } from "@/lib/acesso";
import { mensagemAmigavel } from "@/lib/erros";
import SenhaAdminDialog from "@/components/SenhaAdminDialog";
import ConfirmarAcaoDialog from "@/components/ConfirmarAcaoDialog";
import NovaFichaDialog from "@/components/NovaFichaDialog";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Copy, FileStack, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

// Fase 16, Bloco L: tenant deixou de ser fixo em tempo de build -- ver page.tsx (home) para a
// explicação completa. NEXT_PUBLIC_TENANT_ID vira só o fallback de modo legado.
function tenantIdAtivo(): string {
  return obterTenantIdAtivo() ?? process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
}

function formatarData(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function FichasPage() {
  const router = useRouter();
  const [fichas, setFichas] = useState<FichaResumo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [criando, setCriando] = useState(false);
  const [dialogoNovaFichaAberto, setDialogoNovaFichaAberto] = useState(false);
  const [duplicandoId, setDuplicandoId] = useState<string | null>(null);
  const [excluindoId, setExcluindoId] = useState<string | null>(null);
  const [fichaPendenteDeSenha, setFichaPendenteDeSenha] = useState<string | null>(null);
  const [fichaPendenteDeConfirmacao, setFichaPendenteDeConfirmacao] = useState<{ id: string; nome: string } | null>(null);

  useEffect(() => {
    recarregar();
  }, []);

  async function recarregar() {
    setCarregando(true);
    try {
      const lista = await listarFichas(tenantIdAtivo());
      setFichas(lista);
    } catch {
      toast.error("Não foi possível carregar a lista de fichas técnicas.");
    } finally {
      setCarregando(false);
    }
  }

  async function novaFicha(textoOrigem?: string) {
    setCriando(true);
    try {
      const { ficha } = await criarFicha(tenantIdAtivo(), textoOrigem);
      router.push(`/fichas/${ficha.id}`);
    } catch (e) {
      toast.error(mensagemAmigavel(e, "Não foi possível criar a ficha."));
      setCriando(false);
    }
  }

  async function duplicar(fichaId: string) {
    setDuplicandoId(fichaId);
    try {
      const { ficha } = await duplicarFicha(tenantIdAtivo(), fichaId);
      toast.success("Ficha duplicada.");
      router.push(`/fichas/${ficha.id}`);
    } catch (e) {
      toast.error(mensagemAmigavel(e, "Não foi possível duplicar a ficha."));
      setDuplicandoId(null);
    }
  }

  async function excluir(fichaId: string, nome: string) {
    // Excluir ficha é uma ação administrativa (Fase 14, Bloco S, Task 2) -- se a pessoa já
    // autenticou em /admin nesta aba, reaproveita o token; senão, pede a senha agora mesmo.
    const tokenAdmin = obterTokenAdmin();
    if (!tokenAdmin) {
      setFichaPendenteDeSenha(fichaId);
      return;
    }
    await executarExclusao(fichaId, tokenAdmin);
  }

  async function executarExclusao(fichaId: string, tokenAdmin: string) {
    setExcluindoId(fichaId);
    try {
      await deletarFicha(tenantIdAtivo(), fichaId, tokenAdmin);
      setFichas((atual) => atual.filter((f) => f.id !== fichaId));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        limparTokenAdmin();
        toast.error("Sessão de administrador expirada. Informe a senha novamente.");
        setFichaPendenteDeSenha(fichaId);
      } else {
        toast.error(mensagemAmigavel(e, "Não foi possível excluir a ficha."));
      }
    } finally {
      setExcluindoId(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Image src="/logo.png" alt={APP_NOME} width={430} height={124} priority className="h-8 w-auto" />
          <h1 className="text-xl font-semibold text-foreground">Fichas Técnicas</h1>
        </div>
        <Link href="/" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar ao chat
        </Link>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>Suas fichas ({fichas.length})</CardTitle>
              <CardDescription>Descreva a peça, revise os dados e gere o documento final.</CardDescription>
            </div>
            <Button onClick={() => setDialogoNovaFichaAberto(true)} disabled={criando} className="shrink-0">
              {criando ? <Loader2 className="animate-spin" /> : <Plus />}
              {criando ? "Criando..." : "Nova ficha"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {carregando ? (
            <ul className="divide-y divide-border">
              {[0, 1, 2].map((i) => (
                <li key={i} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-4 w-40 max-w-[70%]" />
                    <Skeleton className="h-3 w-56 max-w-[90%]" />
                  </div>
                </li>
              ))}
            </ul>
          ) : fichas.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <FileStack className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Nenhuma ficha técnica criada ainda.</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {fichas.map((f) => (
                <li key={f.id} className="flex items-center justify-between gap-3 py-3">
                  <Link href={`/fichas/${f.id}`} className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-foreground">
                        {f.nome || "Ficha sem nome"}
                      </span>
                      <Badge variant={VARIANTE_STATUS_FICHA[f.status]} className="shrink-0">
                        {ROTULO_STATUS_FICHA[f.status] ?? f.status}
                      </Badge>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {f.ref ? `Ref. ${f.ref} · ` : ""}
                      Atualizado em {formatarData(f.atualizado_em)}
                      {/* Fase 14, Bloco AP: saber a quem perguntar sobre a peça sem abrir a ficha. */}
                      {f.aprovada_por ? ` · Aprovada por ${f.aprovada_por}` : ""}
                    </p>
                  </Link>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      onClick={() => duplicar(f.id)}
                      disabled={duplicandoId === f.id}
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-foreground"
                      aria-label="Duplicar"
                      title="Duplicar"
                    >
                      {duplicandoId === f.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
                    </Button>
                    <Button
                      onClick={() => setFichaPendenteDeConfirmacao({ id: f.id, nome: f.nome })}
                      disabled={excluindoId === f.id}
                      variant="ghost"
                      size="icon-sm"
                      className="text-muted-foreground hover:text-destructive"
                      aria-label="Excluir"
                      title="Excluir"
                    >
                      {excluindoId === f.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <NovaFichaDialog
        open={dialogoNovaFichaAberto}
        onOpenChange={setDialogoNovaFichaAberto}
        criando={criando}
        onCriarEmBranco={() => { setDialogoNovaFichaAberto(false); novaFicha(); }}
        onCriarComTexto={(texto) => { setDialogoNovaFichaAberto(false); novaFicha(texto); }}
      />
      <ConfirmarAcaoDialog
        open={fichaPendenteDeConfirmacao !== null}
        onOpenChange={(aberto) => { if (!aberto) setFichaPendenteDeConfirmacao(null); }}
        titulo="Excluir ficha"
        descricao={`Excluir a ficha "${fichaPendenteDeConfirmacao?.nome || "sem nome"}"? Essa ação não pode ser desfeita.`}
        textoConfirmar="Excluir"
        onConfirmar={() => {
          if (fichaPendenteDeConfirmacao) excluir(fichaPendenteDeConfirmacao.id, fichaPendenteDeConfirmacao.nome);
        }}
      />
      <SenhaAdminDialog
        open={fichaPendenteDeSenha !== null}
        onOpenChange={(aberto) => { if (!aberto) setFichaPendenteDeSenha(null); }}
        tenantId={tenantIdAtivo()}
        titulo="Confirmar exclusão"
        descricao="Excluir uma ficha técnica exige a senha de administrador."
        onAutorizado={(tokenAdmin) => {
          if (fichaPendenteDeSenha) executarExclusao(fichaPendenteDeSenha, tokenAdmin);
        }}
      />
    </div>
  );
}
