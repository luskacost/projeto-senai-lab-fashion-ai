"use client";

// Senha única de acesso ao app inteiro (Fase 14, Bloco S) -- envolve todas as páginas em
// layout.tsx. Sem SENAI_LABFASHION_ACCESS_PASSWORD configurada no backend, POST /acesso/login
// sempre autoriza (ver api/main.py:acesso_login), então em ambiente de desenvolvimento local isto
// nunca aparece na prática -- o portão só se torna real quando o backend define a variável.
import { useEffect, useState } from "react";
import Image from "next/image";
import { acessoLogin } from "@/lib/api";
import {
  definirTenantIdAtivo,
  definirTokenAcesso,
  obterTokenAcesso,
  registrarAoPerderAcesso,
} from "@/lib/acesso";
import { mensagemAmigavel } from "@/lib/erros";
import { APP_NOME } from "@/lib/branding";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

export default function PortaoDeAcesso({ children }: { children: React.ReactNode }) {
  // null = ainda verificando localStorage (evita piscar a tela de senha antes de checar);
  // depois disso, true/false conforme haja token salvo.
  const [autenticado, setAutenticado] = useState<boolean | null>(null);
  // Usuário = tenant_id da consultoria (Fase 16, Bloco L) -- em desenvolvimento local (nenhum
  // tenant com LOGIN_SENHA configurada no backend) pode ficar em branco, o backend ignora.
  const [usuario, setUsuario] = useState("");
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
      const resultado = await acessoLogin(senha, usuario || undefined);
      if (resultado.autorizado && resultado.token) {
        definirTokenAcesso(resultado.token);
        if (resultado.tenantId) definirTenantIdAtivo(resultado.tenantId);
        setAutenticado(true);
      } else {
        setErro("Usuário ou senha incorretos.");
      }
    } catch (e) {
      setErro(mensagemAmigavel(e, "Não foi possível entrar. Tente novamente."));
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
              <CardDescription>Informe seu usuário e senha para entrar no assistente.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                type="text"
                value={usuario}
                onChange={(e) => setUsuario(e.target.value)}
                placeholder="Usuário"
                autoFocus
              />
              <Input
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                placeholder="Senha"
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
