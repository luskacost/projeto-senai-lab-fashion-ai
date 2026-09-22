"use client";

// Fase 14, Bloco AP, Task 25 -- diálogo de registro de aprovação (e de reabertura, que pede os
// mesmos dois campos).
//
// O rótulo é "registro de aprovação", NUNCA "assinatura digital": não há autenticação nenhuma por
// trás: quem digita o nome é quem estiver no computador. Chamar isso de assinatura prometeria uma
// garantia que o campo não tem, e é justamente em cima dessa promessa falsa que alguém decidiria
// confiar no documento sem conferir. O aviso na tela existe para que a limitação seja visível a
// quem aprova, não só conhecida por quem programou.
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Loader2 } from "lucide-react";

export default function RegistroAprovacaoDialog({
  open,
  onOpenChange,
  modo,
  processando,
  onConfirmar,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modo: "aprovar" | "reabrir";
  processando: boolean;
  onConfirmar: (nome: string, observacao: string) => void;
}) {
  const [nome, setNome] = useState("");
  const [observacao, setObservacao] = useState("");

  useEffect(() => {
    if (open) {
      setNome("");
      setObservacao("");
    }
  }, [open]);

  const aprovando = modo === "aprovar";

  return (
    <Dialog open={open} onOpenChange={(aberto) => { if (!processando) onOpenChange(aberto); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{aprovando ? "Registrar aprovação" : "Reabrir para edição"}</DialogTitle>
          <DialogDescription>
            {aprovando
              ? "Registra quem está aprovando esta ficha e quando. É um registro nominal, não uma assinatura digital -- serve para saber a quem perguntar sobre a peça."
              : "Devolve a ficha para edição. A aprovação atual deixa de valer, mas fica registrada no histórico."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="nome-registro">{aprovando ? "Quem está aprovando" : "Quem está reabrindo"}</Label>
            <Input
              id="nome-registro"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              disabled={processando}
              placeholder="Nome completo"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="observacao-registro">Observação (opcional)</Label>
            <Textarea
              id="observacao-registro"
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              disabled={processando}
              rows={2}
              placeholder={aprovando ? "Ex.: conferido com a modelista" : "Ex.: erro na medida da gola"}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={processando}>
            Cancelar
          </Button>
          <Button onClick={() => onConfirmar(nome.trim(), observacao.trim())} disabled={processando || !nome.trim()}>
            {processando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {aprovando ? "Registrar aprovação" : "Reabrir ficha"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
