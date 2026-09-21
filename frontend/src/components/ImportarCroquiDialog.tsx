"use client";

// Fase 14, Bloco G, Task 17 -- reaproveitar um croqui já salvo na galeria (/croquis) como versão
// do desenho técnico da ficha, sem gastar uma nova chamada de gpt-image-1 (a imagem já foi
// moderada e paga quando foi gerada no chat). Mostra um aviso quando o croqui escolhido é do
// estilo "Ilustração de Moda": a caixa de desenho técnico do documento espera um flat sketch
// (vetor, preto e branco, sem corpo humano) -- uma ilustração figurativa fica destoante ali.
import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CroquiResumo, listarCroquis, urlCroqui } from "@/lib/api";
import { ESTILO_TECNICO } from "@/lib/estilos-croqui";
import { mensagemAmigavel } from "@/lib/erros";
import { AlertTriangle, Images, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function ImportarCroquiDialog({
  open,
  onOpenChange,
  tenantId,
  importando,
  onImportar,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenantId: string;
  importando: boolean;
  onImportar: (croquiId: string) => void;
}) {
  const [croquis, setCroquis] = useState<CroquiResumo[] | null>(null);
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCroquis(null);
    setSelecionadoId(null);
    listarCroquis(tenantId)
      .then(setCroquis)
      .catch((e) => {
        toast.error(mensagemAmigavel(e, "Não foi possível carregar a galeria de croquis."));
        setCroquis([]);
      });
  }, [open, tenantId]);

  const selecionado = croquis?.find((c) => c.id === selecionadoId) ?? null;
  const ehFigurativo = selecionado !== null && selecionado.estilo !== ESTILO_TECNICO;

  return (
    <Dialog open={open} onOpenChange={(aberto) => { if (!importando) onOpenChange(aberto); }}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Importar croqui da galeria</DialogTitle>
          <DialogDescription>
            Escolha um croqui já gerado para usar como desenho técnico desta ficha -- não gasta
            uma nova geração de imagem.
          </DialogDescription>
        </DialogHeader>

        {croquis === null ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : croquis.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Images className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Nenhum croqui na galeria ainda.</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4">
            {croquis.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setSelecionadoId(c.id)}
                disabled={importando}
                className={`relative aspect-[2/3] overflow-hidden rounded-lg border-2 ${
                  selecionadoId === c.id ? "border-primary" : "border-transparent"
                }`}
                title={c.resumo || "Croqui"}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={urlCroqui(tenantId, c.id)} alt={c.resumo || "Croqui"} className="h-full w-full object-cover" />
              </button>
            ))}
          </div>
        )}

        {ehFigurativo && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <p>
              Este croqui é do estilo <Badge variant="outline" className="mx-0.5 font-normal">Ilustração de Moda</Badge>
              -- é figurativo (pose, corpo, cor), diferente do flat sketch vetorial que a caixa de
              desenho técnico do documento espera. Pode ficar destoante no documento final.
            </p>
          </div>
        )}

        <Button
          onClick={() => selecionadoId && onImportar(selecionadoId)}
          disabled={!selecionadoId || importando}
          className="w-full"
        >
          {importando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          {importando ? "Importando..." : "Usar este croqui como desenho técnico"}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
