"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, FichaComAlertas, obterFicha } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Loader2 } from "lucide-react";
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

// dados.ficha ainda é solto (Record<string, unknown>) até a Task 8 modelar o formulário
// completo -- aqui só precisamos ler ficha.nome.valor com segurança, sem `any`.
function extrairNome(dados: Record<string, unknown>): string {
  const bloco = dados?.["ficha"] as Record<string, unknown> | undefined;
  const campoNome = bloco?.["nome"] as { valor?: unknown } | undefined;
  return typeof campoNome?.valor === "string" ? campoNome.valor : "";
}

export default function FichaDetalhePage() {
  const params = useParams<{ id: string }>();
  const fichaId = params.id;
  const [dados, setDados] = useState<FichaComAlertas | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!fichaId) return;
    let cancelado = false;

    (async () => {
      setCarregando(true);
      setErro(null);
      try {
        const resultado = await obterFicha(TENANT_ID, fichaId);
        if (!cancelado) setDados(resultado);
      } catch (e) {
        if (cancelado) return;
        const msg = e instanceof ApiError ? e.message : "Falha ao carregar a ficha.";
        setErro(msg);
        toast.error(msg);
      } finally {
        if (!cancelado) setCarregando(false);
      }
    })();

    return () => {
      cancelado = true;
    };
  }, [fichaId]);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 p-6">
      <Link href="/fichas" className="flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" />
        Voltar às fichas
      </Link>

      {carregando ? (
        <p className="text-sm text-muted-foreground">Carregando...</p>
      ) : erro ? (
        <p className="text-sm text-destructive">{erro}</p>
      ) : dados ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>{extrairNome(dados.ficha.dados) || "Ficha sem nome"}</CardTitle>
              <Badge variant="outline">{dados.ficha.status}</Badge>
            </div>
            <CardDescription>Criada em {formatarData(dados.ficha.criado_em)}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {dados.ficha.texto_origem && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">Descrição original</p>
                <p className="text-sm text-muted-foreground">{dados.ficha.texto_origem}</p>
              </div>
            )}

            {dados.alertas.length > 0 && (
              <div className="space-y-1 rounded-lg border border-border bg-muted p-3">
                <p className="text-sm font-medium text-foreground">Alertas ({dados.alertas.length})</p>
                <ul className="space-y-1">
                  {dados.alertas.map((a, i) => (
                    <li key={`${a.codigo}-${i}`} className="text-xs text-muted-foreground">
                      • {a.mensagem}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="text-xs italic text-muted-foreground">
              O editor completo de revisão chega na próxima etapa (Fase 11, Task 8).
            </p>
          </CardContent>
        </Card>
      ) : (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      )}
    </div>
  );
}
