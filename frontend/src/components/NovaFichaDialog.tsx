"use client";

// Fase 14, Bloco F, Task 10 -- POST /fichas já aceita `texto_origem` e faz extração estruturada +
// verificação de proveniência (fichas_extracao/fichas_verificacao), mas a tela /fichas só chamava
// criarFicha() sem texto, então toda ficha nascia com ~40 campos em branco mesmo quando a pessoa
// já sabia descrever a peça. Este diálogo dá as duas opções sem esconder a diferença: descrever
// gasta uma chamada real à IA para preencher os campos; criar em branco não gasta nada.
import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Sparkles } from "lucide-react";

export default function NovaFichaDialog({
  open,
  onOpenChange,
  criando,
  onCriarEmBranco,
  onCriarComTexto,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  criando: boolean;
  onCriarEmBranco: () => void;
  onCriarComTexto: (texto: string) => void;
}) {
  const [texto, setTexto] = useState("");

  return (
    <Dialog open={open} onOpenChange={(aberto) => { if (!criando) { onOpenChange(aberto); if (!aberto) setTexto(""); } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Nova ficha técnica</DialogTitle>
          <DialogDescription>
            Descreva a peça com suas palavras e a IA preenche os campos técnicos automaticamente
            -- você revisa e ajusta depois. Ou comece em branco e preencha tudo manualmente.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          disabled={criando}
          placeholder="Ex.: Vestido midi em viscose estampada, manga longa, decote V, forro em algodão..."
          className="min-h-28 resize-none"
        />
        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={onCriarEmBranco} disabled={criando}>
            {criando && !texto.trim() ? <Loader2 className="animate-spin" /> : null}
            Criar em branco
          </Button>
          <Button onClick={() => onCriarComTexto(texto.trim())} disabled={criando || !texto.trim()}>
            {criando && texto.trim() ? <Loader2 className="animate-spin" /> : <Sparkles />}
            Descrever com IA
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
