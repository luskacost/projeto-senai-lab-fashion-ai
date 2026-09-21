"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ApiError,
  CroquiResumo,
  deletarCroqui,
  listarCroquis,
  urlCroqui,
} from "@/lib/api";
import { APP_NOME } from "@/lib/branding";
import { limparTokenAdmin, obterTokenAdmin } from "@/lib/admin-sessao";
import { mensagemAmigavel } from "@/lib/erros";
import SenhaAdminDialog from "@/components/SenhaAdminDialog";
import ConfirmarAcaoDialog from "@/components/ConfirmarAcaoDialog";
import ImagemGerada from "@/components/ImagemGerada";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Images, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";

const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";

function formatarData(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function CroquisPage() {
  const [croquis, setCroquis] = useState<CroquiResumo[] | null>(null);
  const [excluindoId, setExcluindoId] = useState<string | null>(null);
  const [croquiPendenteDeSenha, setCroquiPendenteDeSenha] = useState<string | null>(null);
  const [croquiPendenteDeConfirmacao, setCroquiPendenteDeConfirmacao] = useState<{ id: string; resumo: string } | null>(null);

  useEffect(() => {
    recarregar();
  }, []);

  async function recarregar() {
    setCroquis(null);
    try {
      const lista = await listarCroquis(TENANT_ID);
      setCroquis(lista);
    } catch {
      toast.error("Não foi possível carregar a galeria de croquis.");
      setCroquis([]);
    }
  }

  async function excluir(croquiId: string) {
    // Mesma decisão de excluir ficha (Fase 14, Bloco S, Task 2): ação administrativa -- reaproveita
    // o token de admin já ativo nesta aba, senão pede a senha agora mesmo.
    const tokenAdmin = obterTokenAdmin();
    if (!tokenAdmin) {
      setCroquiPendenteDeSenha(croquiId);
      return;
    }
    await executarExclusao(croquiId, tokenAdmin);
  }

  async function executarExclusao(croquiId: string, tokenAdmin: string) {
    setExcluindoId(croquiId);
    try {
      await deletarCroqui(TENANT_ID, croquiId, tokenAdmin);
      setCroquis((atual) => (atual ?? []).filter((c) => c.id !== croquiId));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        limparTokenAdmin();
        toast.error("Sessão de administrador expirada. Informe a senha novamente.");
        setCroquiPendenteDeSenha(croquiId);
      } else {
        toast.error(mensagemAmigavel(e, "Não foi possível excluir o croqui."));
      }
    } finally {
      setExcluindoId(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Image src="/logo.png" alt={APP_NOME} width={430} height={124} priority className="h-8 w-auto" />
          <h1 className="text-xl font-semibold text-foreground">Galeria de Croquis</h1>
        </div>
        <Link href="/" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" />
          Voltar ao chat
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Croquis gerados ({croquis?.length ?? 0})</CardTitle>
          <CardDescription>
            Todo croqui gerado no modo &quot;Gerador de Croqui&quot; fica salvo aqui automaticamente.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {croquis === null ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="aspect-[2/3] w-full rounded-lg" />
              ))}
            </div>
          ) : croquis.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <Images className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Nenhum croqui gerado ainda.</p>
              <p className="text-xs text-muted-foreground">
                Vá até o modo &quot;Gerador de Croqui&quot; no chat para criar o primeiro.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
              {croquis.map((c) => (
                <div key={c.id} className="space-y-1.5">
                  <div className="relative">
                    <ImagemGerada src={urlCroqui(TENANT_ID, c.id)} alt={c.resumo || "Croqui gerado pela IA"} />
                    <Button
                      onClick={() => setCroquiPendenteDeConfirmacao({ id: c.id, resumo: c.resumo })}
                      disabled={excluindoId === c.id}
                      variant="secondary"
                      size="icon-sm"
                      className="absolute right-1.5 top-1.5 text-muted-foreground shadow hover:text-destructive"
                      aria-label="Excluir croqui"
                      title="Excluir croqui"
                    >
                      {excluindoId === c.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                    </Button>
                  </div>
                  {c.estilo && (
                    <Badge variant="outline" className="font-normal">
                      {c.estilo}
                    </Badge>
                  )}
                  {c.resumo && <p className="truncate text-xs text-foreground" title={c.resumo}>{c.resumo}</p>}
                  <p className="text-xs text-muted-foreground">{formatarData(c.criado_em)}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <ConfirmarAcaoDialog
        open={croquiPendenteDeConfirmacao !== null}
        onOpenChange={(aberto) => { if (!aberto) setCroquiPendenteDeConfirmacao(null); }}
        titulo="Excluir croqui"
        descricao={`Excluir "${croquiPendenteDeConfirmacao?.resumo || "este croqui"}"? Essa ação não pode ser desfeita.`}
        textoConfirmar="Excluir"
        onConfirmar={() => {
          if (croquiPendenteDeConfirmacao) excluir(croquiPendenteDeConfirmacao.id);
        }}
      />
      <SenhaAdminDialog
        open={croquiPendenteDeSenha !== null}
        onOpenChange={(aberto) => { if (!aberto) setCroquiPendenteDeSenha(null); }}
        tenantId={TENANT_ID}
        titulo="Confirmar exclusão"
        descricao="Excluir um croqui exige a senha de administrador."
        onAutorizado={(tokenAdmin) => {
          if (croquiPendenteDeSenha) executarExclusao(croquiPendenteDeSenha, tokenAdmin);
        }}
      />
    </div>
  );
}
