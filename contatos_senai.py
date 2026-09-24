# -*- coding: utf-8 -*-
"""Unidades e contatos do SENAI Goiás (Fase 10, Bloco A).

Dado estático, portado de frontend/src/lib/contatos.ts (fonte original: Fase 8, Bloco J,
https://senaigoias.com.br/unidades) -- os dois arquivos precisam ser mantidos em sincronia
manualmente se a lista mudar, já que o card de contato do frontend (ContatoSenai.tsx) exibe o
dado direto sem passar pelo backend, e agora o agente também precisa dele para responder perguntas
em texto (ex: "qual o telefone da unidade de Catalão?"). Nenhum dos dois lados busca o outro em
runtime -- são duas cópias do mesmo dado estático, cada uma servindo um consumidor diferente
(UI vs. LLM).
"""

from typing import Dict, List, Optional, TypedDict


class UnidadeSenai(TypedDict, total=False):
    nome: str
    endereco: str
    telefone: str
    email: str


UNIDADE_PRINCIPAL: UnidadeSenai = {
    "nome": "FATEC SENAI Ítalo Bologna",
    "endereco": "Rua Armogaste José da Silveira, nº 612, Centro Oeste, Goiânia - GO, 74.560-020",
    "telefone": "(62) 3226-4500",
    "email": "dario@fieg.com.br",
}

OUTRAS_UNIDADES: List[UnidadeSenai] = [
    {
        "nome": "Escola SENAI Aparecida",
        "endereco": "Rua dos Pirineus, Qd. 01 Lt. 01, St. Village Garavelo, Aparecida de Goiânia - GO, 74.968-539",
        "telefone": "(62) 3236-6900",
        "email": "volneicesar.sesi@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Barro Alto",
        "endereco": "Rua Pedra de Fogo, Qd. 17 Lt. 16, St. Alfredo Batista, Barro Alto - GO, 76.390-000",
        "telefone": "(62) 3347-6662",
        "email": "thiago.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Catalão",
        "endereco": "Avenida Dr. Lamartine P. Avelar, nº 1400, Vila Chaud, Catalão - GO, 75.704-020",
        "telefone": "(64) 3445-1700",
        "email": "danilo.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Dr. Celso Charuri",
        "endereco": "Rua Barita, Qd. 122 Lt. 01/02, St. Vila Oliveira, Aparecida de Goiânia - GO, 74.955-060",
        "telefone": "(62) 3254-1850",
        "email": "volneicesar.sesi@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Fernando Bezerra",
        "endereco": "Av. Guanabara, nº 217, St. Pausanes, Rio Verde - GO, 75.904-015",
        "telefone": "(64) 3624-4400",
        "email": "tays.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Itumbiara",
        "endereco": "Avenida Olívia Fagundes, nº 32, Setor Oeste, Itumbiara - GO, 75.526-478",
        "telefone": "(64) 3432-2500",
        "email": "abilio.sesi@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Jardim Colorado",
        "endereco": "Rua SC 29, s/n, Qd. 24 Lt. Área, Jardim Colorado, Goiânia - GO, 74.474-036",
        "telefone": "(62) 3522-7100",
        "email": "sesisenaicolorado@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Jataí",
        "endereco": "Av. Veriano de Oliveira Lima, Samuel Grahan, Jataí - GO, 75.804-055",
        "telefone": "(64) 3606-4984",
        "email": "albinoandrade.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Mineiros",
        "endereco": "Av. Ino Resende, s/n, Quadra 27, Lotes 1 a 4, Setor Ioris, Mineiros - GO, 75.834-039",
        "telefone": "(64) 3661-9434",
        "email": "albinoandrade.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Niquelândia",
        "endereco": "Avenida Brasil, s/n, Conjunto Habitacional Codemin, Niquelândia - GO, 76.420-000",
        "telefone": "(62) 3354-1802",
        "email": "thiago.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Paulo Vargas",
        "endereco": "Rua Prof. Lázaro Costa, nº 348, St. Vila Canaã, Goiânia - GO, 74.415-420",
        "telefone": "(62) 3235-8100",
        "email": "aliana.senai@fieg.com.br",
    },
    {
        "nome": "Escola SENAI Sama",
        "endereco": "Mina Cana Brava, St. Vila Res. Sama, Minaçu - GO, 76.450-000",
        "telefone": "(62) 3379-8000",
        "email": "rodrigoss.senai@fieg.com.br",
    },
    {
        "nome": "Faculdade de Tecnologia SENAI de Desenvolvimento Gerencial",
        "endereco": "Rua 227 A, nº 582, St. Leste Universitário, Goiânia - GO, 74.610-060",
        "telefone": "(62) 3269-1200",
        "email": "fatesg.senai@fieg.com.br",
    },
    {
        "nome": "FATEC SENAI Roberto Mange",
        "endereco": "Av. Eng. Roberto Mange, nº 239, Jundiaí, Anápolis - GO, 75.113-630",
        "telefone": "(62) 3902-6200",
        "email": "almiro.senai@fieg.com.br",
    },
    {
        "nome": "Núcleo de Formação Profissional SENAI Senador Canedo",
        "endereco": "Av. Progresso, Qd. 02 Lt. 03, St. Conjunto Sabiá, Senador Canedo - GO, 75.250-000",
        "telefone": "(62) 3512-3652",
        "email": "volneicesar.sesi@fieg.com.br",
    },
    {
        "nome": "Unidade Digital SESI SENAI",
        "endereco": "Av. Anhanguera, nº 5.440, Ed. José Aquino Porto, Palácio da Indústria, Centro, Goiânia - GO, 74.043-010",
        "telefone": "(62) 3219-9300",
        "email": "digital@fieg.com.br",
    },
    {
        "nome": "Unidade Integrada SESI/SENAI de Quirinópolis",
        "endereco": "Avenida Progresso GO 164 Km 10, Setor Agroindustrial, Quirinópolis - GO, 75.861-460",
        "telefone": "(64) 3515-9900",
        "email": "abilio.sesi@fieg.com.br",
    },
    {
        "nome": "Unidades Móveis",
        "endereco": "Rua Prof. Lázaro Costa, nº 348, St. Vila Canaã, Goiânia - GO, 74.415-420",
        "telefone": "(62) 3219-1494",
        "email": "paolorodrigues@fieg.com.br",
    },
]

CONTATOS_GERAIS: Dict[str, str] = {
    "central_goiania": "4002-6213",
    "demais_localidades": "0800 642 1313",
}

TODAS_UNIDADES: List[UnidadeSenai] = [UNIDADE_PRINCIPAL] + OUTRAS_UNIDADES


def _normalizar(texto: str) -> str:
    """Normaliza para comparação tolerante a acento/maiúsculas (ex: 'catalao' == 'Catalão')."""
    import unicodedata
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def buscar_unidades(termo: Optional[str] = None) -> List[UnidadeSenai]:
    """Filtra unidades cujo nome ou endereço contenha `termo` (case/acento-insensível).

    Sem termo, devolve todas. Usado tanto pela tool do agente quanto, potencialmente, por uma
    futura rota HTTP -- mantém a lógica de busca fora do handler da tool.
    """
    if not termo:
        return list(TODAS_UNIDADES)

    termo_norm = _normalizar(termo)
    return [
        u for u in TODAS_UNIDADES
        if termo_norm in _normalizar(u.get("nome", "")) or termo_norm in _normalizar(u.get("endereco", ""))
    ]
