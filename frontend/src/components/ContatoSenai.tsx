"use client";

import { Mail, MapPin, Phone, Building2 } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Card, CardContent } from "@/components/ui/card";
import { UNIDADE_PRINCIPAL, OUTRAS_UNIDADES, CONTATOS_GERAIS, UnidadeSenai } from "@/lib/contatos";

function LinhaUnidade({ unidade, destaque }: { unidade: UnidadeSenai; destaque?: boolean }) {
  return (
    <div>
      <p className={`font-medium ${destaque ? "text-base" : "text-sm"}`}>{unidade.nome}</p>
      <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
        <p className="flex items-start gap-1.5">
          <MapPin className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>{unidade.endereco}</span>
        </p>
        <p className="flex items-center gap-1.5">
          <Phone className="h-3.5 w-3.5 shrink-0" />
          <span>{unidade.telefone}</span>
        </p>
        {unidade.email && (
          <p className="flex items-center gap-1.5">
            <Mail className="h-3.5 w-3.5 shrink-0" />
            <span>{unidade.email}</span>
          </p>
        )}
      </div>
    </div>
  );
}

export default function ContatoSenai() {
  return (
    <Dialog>
      <DialogTrigger className="inline-flex items-center gap-1 text-sm font-normal text-muted-foreground hover:text-foreground">
        <Building2 className="h-3.5 w-3.5" />
        Contato
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto space-y-3 p-4">
        <DialogTitle>Unidades e contato do SENAI Goiás</DialogTitle>

        <Card className="bg-secondary/10 border-secondary/30">
          <CardContent className="p-3">
            <LinhaUnidade unidade={UNIDADE_PRINCIPAL} destaque />
          </CardContent>
        </Card>

        <p className="text-xs font-medium text-muted-foreground">Demais unidades</p>
        <div className="divide-y divide-border border rounded-md px-3">
          {OUTRAS_UNIDADES.map((unidade) => (
            <div key={unidade.nome} className="py-2">
              <LinhaUnidade unidade={unidade} />
            </div>
          ))}
        </div>

        <Separator />
        <div className="text-xs text-muted-foreground space-y-0.5">
          <p>Central de atendimento (Goiânia): {CONTATOS_GERAIS.centralGoiania}</p>
          <p>Demais localidades: {CONTATOS_GERAIS.demaisLocalidades}</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
