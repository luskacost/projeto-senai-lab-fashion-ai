# -*- coding: utf-8 -*-
"""Unidades e contatos (Fase 10, Bloco A).

Dados FICTÍCIOS por padrão (Fase 15, Bloco H, Task H1) -- o repositório é público (portfólio no
GitHub), então os dados reais de contato do SENAI Goiás (endereços, telefones e e-mails nominais de
15 pessoas) saíram do código versionado. Os dados reais moram em `contatos_senai_local.py`
(git-ignorado; ver `.gitignore`), carregado automaticamente abaixo SE o arquivo existir -- é assim
que o app continua respondendo com o dado real na máquina de quem já o tinha, sem que ele jamais
volte a ser commitado.

Sem `contatos_senai_local.py` (o caso de quem clona o repositório do zero), o app funciona
normalmente com os dados fictícios abaixo -- só a resposta a perguntas de contato muda, nada mais
depende disto.

Nome do arquivo local usa `_` e não `.` (`contatos_senai_local.py`, não `contatos_senai.local.py`):
um `import` do Python não resolve um nome de arquivo com ponto como se fosse um pacote/submódulo --
teria que ser um pacote de verdade (`contatos_senai/local.py`) para a sintaxe com ponto funcionar.
"""

from typing import Dict, List, Optional, TypedDict


class UnidadeSenai(TypedDict, total=False):
    nome: str
    endereco: str
    telefone: str
    email: str


UNIDADE_PRINCIPAL: UnidadeSenai = {
    "nome": "Unidade Exemplo Sede",
    "endereco": "Rua Exemplo, nº 100, Centro, Cidade Exemplo - UF, 00.000-000",
    "telefone": "(00) 0000-0000",
    "email": "contato@exemplo.com.br",
}

OUTRAS_UNIDADES: List[UnidadeSenai] = [
    {
        "nome": "Escola Exemplo Norte",
        "endereco": "Rua Norte, nº 10, Bairro Norte, Cidade Exemplo - UF, 00.000-001",
        "telefone": "(00) 0000-0001",
        "email": "norte@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Sul",
        "endereco": "Rua Sul, nº 20, Bairro Sul, Cidade Exemplo - UF, 00.000-002",
        "telefone": "(00) 0000-0002",
        "email": "sul@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Conceição",
        "endereco": "Avenida Central, nº 300, Centro, Conceição - UF, 00.000-003",
        "telefone": "(00) 0000-0003",
        "email": "conceicao@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Vale Verde",
        "endereco": "Rua das Flores, nº 40, Vale Verde - UF, 00.000-004",
        "telefone": "(00) 0000-0004",
        "email": "valeverde@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Rio Claro",
        "endereco": "Av. do Rio, nº 50, Rio Claro - UF, 00.000-005",
        "telefone": "(00) 0000-0005",
        "email": "rioclaro@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Serra Alta",
        "endereco": "Rua da Serra, nº 60, Serra Alta - UF, 00.000-006",
        "telefone": "(00) 0000-0006",
        "email": "serraalta@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Porto Novo",
        "endereco": "Av. do Porto, nº 70, Porto Novo - UF, 00.000-007",
        "telefone": "(00) 0000-0007",
        "email": "portonovo@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Campo Bom",
        "endereco": "Rua do Campo, nº 80, Campo Bom - UF, 00.000-008",
        "telefone": "(00) 0000-0008",
        "email": "campobom@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Monte Azul",
        "endereco": "Rua do Monte, nº 90, Monte Azul - UF, 00.000-009",
        "telefone": "(00) 0000-0009",
        "email": "monteazul@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Boa Vista",
        "endereco": "Av. Boa Vista, nº 100, Boa Vista - UF, 00.000-010",
        "telefone": "(00) 0000-0010",
        "email": "boavista@exemplo.com.br",
    },
    {
        "nome": "Escola Exemplo Pedra Branca",
        "endereco": "Rua da Pedra, nº 110, Pedra Branca - UF, 00.000-011",
        "telefone": "(00) 0000-0011",
        "email": "pedrabranca@exemplo.com.br",
    },
    {
        "nome": "Unidade Digital Exemplo",
        "endereco": "Av. Digital, nº 120, Centro, Cidade Exemplo - UF, 00.000-012",
        "telefone": "(00) 0000-0012",
        "email": "digital@exemplo.com.br",
    },
]

CONTATOS_GERAIS: Dict[str, str] = {
    "central_goiania": "0000-0000",
    "demais_localidades": "0800 000 0000",
}

try:
    # Sem dependência declarada em requirements.txt de propósito -- este import só funciona se
    # alguém colocar o arquivo real (git-ignorado) ao lado deste. `# type: ignore` porque o
    # módulo não existe no repositório versionado, então o checador de tipos nunca o encontra.
    from contatos_senai_local import (  # type: ignore
        UNIDADE_PRINCIPAL as _UNIDADE_PRINCIPAL_REAL,
        OUTRAS_UNIDADES as _OUTRAS_UNIDADES_REAL,
        CONTATOS_GERAIS as _CONTATOS_GERAIS_REAL,
    )
    UNIDADE_PRINCIPAL = _UNIDADE_PRINCIPAL_REAL
    OUTRAS_UNIDADES = _OUTRAS_UNIDADES_REAL
    CONTATOS_GERAIS = _CONTATOS_GERAIS_REAL
except ImportError:
    pass

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
