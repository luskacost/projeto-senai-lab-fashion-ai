// Unidades e contatos exibidos no card de contato (Fase 8, Bloco J). Dado estático, exibido
// diretamente na interface -- não passa pelo LLM, então nunca sai desatualizado por causa de uma
// resposta gerada.
//
// Dados FICTÍCIOS (Fase 15, Bloco H, Task H1) -- o repositório é público (portfólio no GitHub), e
// os dados reais de contato (endereços, telefones, e-mails nominais) não pertencem a um código
// versionado publicamente. O equivalente server-side (`contatos_senai.py`) tem um mecanismo de
// substituição por um arquivo local git-ignorado; aqui no frontend, que é bundled direto pro
// navegador, isso não faz sentido (o bundle final não tem "arquivo local" nenhum) -- então este
// arquivo fica só com o dado fictício mesmo.

export interface UnidadeSenai {
  nome: string;
  endereco: string;
  telefone: string;
  email?: string;
}

// Unidade principal -- destacada no topo do card de contato.
export const UNIDADE_PRINCIPAL: UnidadeSenai = {
  nome: "Unidade Exemplo Sede",
  endereco: "Rua Exemplo, nº 100, Centro, Cidade Exemplo - UF, 00.000-000",
  telefone: "(00) 0000-0000",
  email: "contato@exemplo.com.br",
};

export const OUTRAS_UNIDADES: UnidadeSenai[] = [
  {
    nome: "Escola Exemplo Norte",
    endereco: "Rua Norte, nº 10, Bairro Norte, Cidade Exemplo - UF, 00.000-001",
    telefone: "(00) 0000-0001",
    email: "norte@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Sul",
    endereco: "Rua Sul, nº 20, Bairro Sul, Cidade Exemplo - UF, 00.000-002",
    telefone: "(00) 0000-0002",
    email: "sul@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Conceição",
    endereco: "Avenida Central, nº 300, Centro, Conceição - UF, 00.000-003",
    telefone: "(00) 0000-0003",
    email: "conceicao@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Vale Verde",
    endereco: "Rua das Flores, nº 40, Vale Verde - UF, 00.000-004",
    telefone: "(00) 0000-0004",
    email: "valeverde@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Rio Claro",
    endereco: "Av. do Rio, nº 50, Rio Claro - UF, 00.000-005",
    telefone: "(00) 0000-0005",
    email: "rioclaro@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Serra Alta",
    endereco: "Rua da Serra, nº 60, Serra Alta - UF, 00.000-006",
    telefone: "(00) 0000-0006",
    email: "serraalta@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Porto Novo",
    endereco: "Av. do Porto, nº 70, Porto Novo - UF, 00.000-007",
    telefone: "(00) 0000-0007",
    email: "portonovo@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Campo Bom",
    endereco: "Rua do Campo, nº 80, Campo Bom - UF, 00.000-008",
    telefone: "(00) 0000-0008",
    email: "campobom@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Monte Azul",
    endereco: "Rua do Monte, nº 90, Monte Azul - UF, 00.000-009",
    telefone: "(00) 0000-0009",
    email: "monteazul@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Boa Vista",
    endereco: "Av. Boa Vista, nº 100, Boa Vista - UF, 00.000-010",
    telefone: "(00) 0000-0010",
    email: "boavista@exemplo.com.br",
  },
  {
    nome: "Escola Exemplo Pedra Branca",
    endereco: "Rua da Pedra, nº 110, Pedra Branca - UF, 00.000-011",
    telefone: "(00) 0000-0011",
    email: "pedrabranca@exemplo.com.br",
  },
  {
    nome: "Unidade Digital Exemplo",
    endereco: "Av. Digital, nº 120, Centro, Cidade Exemplo - UF, 00.000-012",
    telefone: "(00) 0000-0012",
    email: "digital@exemplo.com.br",
  },
];

export const CONTATOS_GERAIS = {
  centralGoiania: "0000-0000",
  demaisLocalidades: "0800 000 0000",
};
