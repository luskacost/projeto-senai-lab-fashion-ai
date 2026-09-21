"use client";

// Confirmação de administrador para ações destrutivas fora de /admin (Fase 14, Bloco S, Task 2)
// -- ex.: excluir uma ficha técnica. Reaproveita a mesma rota/token de POST /admin/login que a
// tela /admin já usa; se a pessoa já autenticou nesta aba (sessionStorage), o chamador nem chega
// a abrir este diálogo -- ver excluir() em fichas/page.tsx.
import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { adminLogin } from "@/lib/api";
import { definirTokenAdmin } from "@/lib/admin-sessao";
import { mensagemAmigavel } from "@/lib/erros";

export default function SenhaAdminDialog({
  open,
  onOpenChange,
  tenantId,
  titulo = "Confirmação de administrador",
  descricao = "Esta ação exige a senha de administrador.",
  onAutorizado,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenantId: string;
  titulo?: string;
  descricao?: string;
  onAutorizado: (tokenAdmin: string) => void;
}) {
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [validando, setValidando] = useState(false);

  async function confirmar(e: React.FormEvent) {
    e.preventDefault();
    setValidando(true);
    setErro(null);
    try {
      const token = await adminLogin(tenantId, senha);
      if (token) {
        definirTokenAdmin(token);
        setSenha("");
        onOpenChange(false);
        onAutorizado(token);
      } else {
        setErro("Senha incorreta.");
      }
    } catch (e) {
      setErro(mensagemAmigavel(e, "Não foi possível confirmar. Tente novamente."));
    } finally {
      setValidando(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descricao}</DialogDescription>
        </DialogHeader>
        <form onSubmit={confirmar} className="space-y-4">
          <Input
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            placeholder="Senha de administrador"
            autoFocus
          />
          {erro && <p className="text-sm text-destructive">{erro}</p>}
          <Button type="submit" disabled={validando || !senha} className="w-full">
            {validando && <Loader2 className="animate-spin" />}
            {validando ? "Validando..." : "Confirmar"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
