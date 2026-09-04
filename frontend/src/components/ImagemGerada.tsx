"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export default function ImagemGerada({ src, alt }: { src: string; alt: string }) {
  const [carregada, setCarregada] = useState(false);

  return (
    <Dialog>
      <DialogTrigger className="relative block aspect-[2/3] w-full cursor-pointer overflow-hidden rounded-lg border-0 bg-transparent p-0 appearance-none focus:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {!carregada && <Skeleton className="absolute inset-0 rounded-lg" />}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          onLoad={() => setCarregada(true)}
          className={`h-full w-full object-cover transition-opacity duration-300 ${carregada ? "opacity-100" : "opacity-0"}`}
        />
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl p-2">
        <DialogTitle className="sr-only">{alt}</DialogTitle>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} className="h-auto w-full rounded-lg" />
      </DialogContent>
    </Dialog>
  );
}
