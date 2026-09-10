"use client";

import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function ImagemGerada({ src, alt }: { src: string; alt: string }) {
  const [srcAtual, setSrcAtual] = useState(src);
  const [baixando, setBaixando] = useState(false);

  // Toda imagem gerada hoje já chega como data URI (base64 embutido no próprio payload da
  // API, Fase 9/Bloco A -- gpt-image-1 não retorna URL) -- não há uma busca de rede separada
  // pra "aguardar" como fazia sentido antigamente com a URL hotlinkada do Pollinations, então
  // não há skeleton de carregamento nem onLoad: a imagem já está disponível assim que renderiza.
  useEffect(() => {
    setSrcAtual(src);
  }, [src]);

  async function baixarImagem() {
    setBaixando(true);
    try {
      const res = await fetch(srcAtual);
      if (!res.ok) throw new Error("Falha ao baixar imagem");
      const blob = await res.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "croqui.png";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch {
      window.open(srcAtual, "_blank");
      toast.error("Não foi possível baixar a imagem diretamente. Abrimos ela em uma nova aba.");
    } finally {
      setBaixando(false);
    }
  }

  return (
    <Dialog>
      <DialogTrigger className="relative block aspect-[2/3] w-full cursor-pointer overflow-hidden rounded-lg border-0 bg-transparent p-0 appearance-none focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={srcAtual} alt={alt} className="h-full w-full object-cover" />
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto p-2">
        <DialogTitle className="sr-only">{alt}</DialogTitle>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={srcAtual} alt={alt} className="h-auto max-h-[70vh] w-full rounded-lg object-contain" />
        <div className="flex justify-center gap-2 pb-1">
          <Button variant="outline" size="sm" onClick={baixarImagem} disabled={baixando}>
            {baixando ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
            Baixar imagem
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
