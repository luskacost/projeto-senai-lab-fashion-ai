"use client";

// Senha única de acesso ao app inteiro (Fase 14, Bloco S) -- envolve todas as páginas em
// layout.tsx. Sem SENAI_LABFASHION_ACCESS_PASSWORD configurada no backend, POST /acesso/login
// sempre autoriza (ver api/main.py:acesso_login), então em ambiente de desenvolvimento local isto
// nunca aparece na prática -- o portão só se torna real quando o backend define a variável.
import { useEffect, useState } from "react";
import Image from "next/image";
import { acessoLogin, ApiError } from "@/lib/api";
import { definirTokenAcesso, obterTokenAcesso, registrarAoPerderAcesso } from "@/lib/acesso";
import { APP_NOME } from "@/lib/branding";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

export default function PortaoDeAcesso({ children }: { children: React.ReactNode }) {
  // null = ainda verificando localStorage (evita piscar a tela de senha antes de checar);
  // depois disso, true/false conforme haja token salvo.
  const [autenticado, setAutenticado] = useState<boolean | null>(null);
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);

  useEffect(() => {
    setAutenticado(!!obterTokenAcesso());
    // Registrado uma única vez: qualquer chamada da API em qualquer página que receba o header
    // X-Auth-Gate: acesso (token inválido/expirado/servidor reiniciado) cai aqui e devolve o
    // usuário para a tela de senha, sem cada página precisar tratar isso por conta própria.
    registrarAoPerderAcesso(() => setAutenticado(false));
  }, []);

  async function fazerLogin(e: React.FormEvent) {
    e.preventDefault();
    setValidando(true);
    setErro(null);
    try {
      const token = await acessoLogin(senha);
      if (token) {
        definirTokenAcesso(token);
        setAutenticado(true);
      } else {
        setErro("Senha incorreta.");
      }
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Falha ao conectar com a API.");
    } finally {
      setValidando(false);
    }
  }

  // Evita renderizar a tela de senha por um instante antes de saber se já há token salvo.
  if (autenticado === null) return null;

  if (!autenticado) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-6 bg-background">
        <Image src="/logo.png" alt={APP_NOME} width={430} height={124} priority className="h-10 w-auto" />
        <form onSubmit={fazerLogin} className="w-full max-w-sm px-4">
          <Card>
            <CardHeader>
              <CardTitle>Acesso ao {APP_NOME}</CardTitle>
              <CardDescription>Informe a senha de acesso para entrar no assistente.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                placeholder="Senha"
                autoFocus
              />
              {erro && <p className="text-sm text-destructive">{erro}</p>}
              <Button type="submit" disabled={validando || !senha} className="w-full">
                {validando && <Loader2 className="animate-spin" />}
                {validando ? "Validando..." : "Entrar"}
              </Button>
            </CardContent>
          </Card>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
