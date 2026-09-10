"use client";

import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function ImagemGerada({ src, alt }: { src: string; alt: string }) {
  const [srcAtual, setSrcAtual] = useState(src);
  const [carregada, setCarregada] = useState(false);
  const [baixando, setBaixando] = useState(false);

  useEffect(() => {
    setSrcAtual(src);
    setCarregada(false);
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
        {!carregada && <Skeleton className="absolute inset-0 rounded-lg" />}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={srcAtual}
          alt={alt}
          onLoad={() => setCarregada(true)}
          className={`h-full w-full object-cover transition-opacity duration-300 ${carregada ? "opacity-100" : "opacity-0"}`}
        />
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
