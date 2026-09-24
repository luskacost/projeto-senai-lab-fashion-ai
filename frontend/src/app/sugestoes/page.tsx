"use client";

import { useState } from "react";
import Link from "next/link";
import { criarSugestao } from "@/lib/api";
import { obterTenantIdAtivo } from "@/lib/acesso";
import { mensagemAmigavel } from "@/lib/erros";
import { APP_NOME } from "@/lib/branding";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Lightbulb, Loader2, MessageSquareWarning } from "lucide-react";
import { toast } from "sonner";

// Fase 16, Bloco L: tenant deixou de ser fixo em tempo de build -- ver page.tsx (home) para a
// explicação completa. NEXT_PUBLIC_TENANT_ID vira só o fallback de modo legado.
function tenantIdAtivo(): string {
  return obterTenantIdAtivo() ?? process.env.NEXT_PUBLIC_TENANT_ID ?? "senai_labfashion";
}

export default function SugestoesPage() {
  const [tipo, setTipo] = useState<"sugestao" | "bug">("sugestao");
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    setEnviando(true);
    try {
      await criarSugestao(tenantIdAtivo(), tipo, texto);
      toast.success("Obrigado! Sua mensagem foi enviada.");
      setTexto("");
    } catch (e) {
      toast.error(mensagemAmigavel(e, "Não foi possível enviar. Tente novamente."));
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-center gap-3">
          <Link href="/" className="text-muted-foreground hover:text-foreground" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-lg font-semibold">Sugestões e reporte de erro</h1>
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>Fale com a equipe do {APP_NOME}</CardTitle>
            <CardDescription>
              Encontrou um erro ou tem uma ideia de melhoria? Sua mensagem vai direto para quem
              cuida do sistema.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={enviar} className="space-y-4">
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant={tipo === "sugestao" ? "default" : "outline"}
                  onClick={() => setTipo("sugestao")}
                  className="gap-1.5"
                >
                  <Lightbulb className="h-4 w-4" />
                  Sugestão
                </Button>
                <Button
                  type="button"
                  variant={tipo === "bug" ? "default" : "outline"}
                  onClick={() => setTipo("bug")}
                  className="gap-1.5"
                >
                  <MessageSquareWarning className="h-4 w-4" />
                  Reportar erro
                </Button>
              </div>

              <Textarea
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder={
                  tipo === "bug"
                    ? "Descreva o que aconteceu: o que você tentou fazer, o que esperava, e o que aconteceu de errado."
                    : "Descreva sua ideia de melhoria."
                }
                rows={6}
                autoFocus
              />

              <Button type="submit" disabled={enviando || !texto.trim()}>
                {enviando && <Loader2 className="animate-spin" />}
                {enviando ? "Enviando..." : "Enviar"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
