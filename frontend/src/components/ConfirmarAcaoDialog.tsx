"use client";

// Substitui window.confirm() nativo (Fase 14, Bloco U, Task 7) -- o diálogo do sistema
// operacional aparece fora da identidade visual do app (às vezes em inglês) e não segue nenhum
// dos padrões de acessibilidade/estilo do resto da interface. Um só componente reutilizado nos 4
// pontos que hoje usam window.confirm (excluir conversa, remover logo, remover documento,
// excluir ficha).
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export default function ConfirmarAcaoDialog({
  open,
  onOpenChange,
  titulo,
  descricao,
  textoConfirmar = "Confirmar",
  destrutivo = true,
  onConfirmar,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titulo: string;
  descricao: string;
  textoConfirmar?: string;
  destrutivo?: boolean;
  onConfirmar: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descricao}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            variant={destrutivo ? "destructive" : "default"}
            onClick={() => {
              onOpenChange(false);
              onConfirmar();
            }}
          >
            {textoConfirmar}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
