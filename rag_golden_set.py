# -*- coding: utf-8 -*-
"""Golden set versionado para avaliação do RAG (Fase 13, Task 7).

## Por que este corpus é inteiramente fictício

O golden set anterior (`tests/rag/test_cases.json`, 8 casos) dependia de conteúdo pré-indexado no
tenant real `senai_labfashion` -- irreproduzível em máquina limpa, já que `tenant_data/` é
gitignored, e uma má ideia de qualquer forma: dado de cliente não entra no controle de versão.
Decisão travada em `3d06216`/`bad839c` e mantida aqui.

Todo o conteúdo abaixo é inventado para este arquivo: os códigos de tecido (TX-xxx), as
referências de peça (JL-100, AV-220...), os fornecedores e as normas (NF-xxxx) não existem.

## Como o corpus foi desenhado

Um corpus onde toda pergunta tem uma resposta óbvia e única não mede nada -- recall@5 daria 1,0
sempre. Três decisões deliberadas para que o ranking tenha o que errar:

1. **Distratores estruturais.** As quatro peças do manual têm exatamente os mesmos campos
   (tecido, gramatura, largura, composição, acabamento, aviamentos) com valores diferentes.
   Perguntar a gramatura de uma delas coloca as outras três como candidatas quase idênticas --
   é o cenário de contaminação cruzada entre variantes, que o audit da Fase 13 mostrou ser o
   ponto fraco real do pipeline.
2. **Distrator temático.** `normas_ensaios.txt` fala de têxteis (mesmo vocabulário: tecido,
   encolhimento, resistência) mas nunca responde nada sobre especificação de peça. Serve para
   que "recuperou algo do domínio" não se confunda com "recuperou a resposta".
3. **Sobreposição parcial entre formatos.** Quatro dos tecidos do catálogo CSV aparecem também
   no manual em texto corrido; os outros oito só existem na tabela. Isso permite casos que
   exigem o documento certo (não só o assunto certo) e casos multi-documento de verdade.
"""

import io
from typing import Dict, List

import document_extractors
import rag_manager
from rag_eval import CasoAvaliacao

TENANT_GOLDEN = "rag_golden_set"

NOME_MANUAL = "manual_tecnico_uniformes.txt"
NOME_CATALOGO = "catalogo_tecidos.csv"
NOME_NORMAS = "normas_ensaios.txt"

MANUAL_TECNICO = """MANUAL TECNICO DE UNIFORMES PROFISSIONAIS - CONTEUDO FICTICIO PARA TESTES

1. JALECO AMBULATORIAL REF JL-100
Tecido: Oxford TX-200
Composicao: 67% poliester e 33% algodao
Gramatura: 180 g/m2
Largura util: 150 cm
Cores disponiveis: branco e verde agua
Acabamento: tratamento antimicrobiano e pre-encolhido
Aviamentos: 4 botoes de pressao e 3 bolsos frontais

2. AVENTAL DE COZINHA REF AV-220
Tecido: Brim TX-310
Composicao: 100% algodao
Gramatura: 240 g/m2
Largura util: 160 cm
Cores disponiveis: preto e vermelho
Acabamento: impermeabilizante hidrorrepelente
Aviamentos: 1 fivela metalica e tira ajustavel no pescoco

3. CAMISA POLO CORPORATIVA REF PL-330
Tecido: Pique TX-450
Composicao: 50% poliester e 50% algodao
Gramatura: 200 g/m2
Largura util: 180 cm
Cores disponiveis: azul marinho e cinza mescla
Acabamento: antipilling
Aviamentos: 3 botoes de madreperola e gola ribana

4. CALCA OPERACIONAL REF CL-440
Tecido: Sarja TX-520
Composicao: 98% algodao e 2% elastano
Gramatura: 260 g/m2
Largura util: 165 cm
Cores disponiveis: caqui e chumbo
Acabamento: tratamento antiestatico
Aviamentos: 1 ziper metalico, 6 passantes e 2 bolsos cargo
"""

CATALOGO_TECIDOS = (
    "Codigo,Nome,Composicao,Gramatura,Largura,Fornecedor,Preco por metro\n"
    "TX-200,Oxford,67% poliester 33% algodao,180,150,Fiacao Aurora,18.50\n"
    "TX-310,Brim,100% algodao,240,160,Tecelagem Bandeira,22.90\n"
    "TX-450,Pique,50% poliester 50% algodao,200,180,Malharia Cristal,26.40\n"
    "TX-520,Sarja,98% algodao 2% elastano,260,165,Tecelagem Bandeira,31.75\n"
    "TX-610,Tricoline,100% algodao,120,145,Fiacao Aurora,15.20\n"
    "TX-700,Microfibra,100% poliester,90,160,Malharia Cristal,12.80\n"
    "TX-750,Helanca,92% poliamida 8% elastano,210,170,Tecelagem Bandeira,28.30\n"
    "TX-800,Gabardine,65% poliester 35% viscose,270,150,Fiacao Aurora,33.10\n"
    "TX-860,Linho misto,55% linho 45% viscose,190,140,Malharia Cristal,41.60\n"
    "TX-910,Moletom,80% algodao 20% poliester,320,180,Tecelagem Bandeira,29.90\n"
    "TX-940,Cambraia,100% algodao,140,150,Fiacao Aurora,19.70\n"
    "TX-980,Neoprene,85% poliester 15% elastano,350,155,Malharia Cristal,47.25\n"
)

GUIA_NORMAS = """GUIA DE ENSAIOS TEXTEIS - CONTEUDO FICTICIO PARA TESTES

ENSAIO DE SOLIDEZ DA COR A LAVAGEM
Norma ficticia NF-2201. Avalia a perda de cor apos ciclos sucessivos de lavagem domestica.
O resultado e expresso em escala cinza de 1 a 5, onde 5 indica nenhuma alteracao perceptivel.

ENSAIO DE RESISTENCIA AO RASGO
Norma ficticia NF-3310. Mede a forca necessaria para propagar um rasgo iniciado no corpo de prova.
Aplicavel a tecidos planos de uso profissional submetidos a esforco mecanico repetido.

ENSAIO DE ENCOLHIMENTO APOS LAVAGEM
Norma ficticia NF-4405. Determina a variacao dimensional do tecido apos lavagem e secagem.
Tecidos pre-encolhidos devem apresentar variacao inferior a 3% no sentido do comprimento.

ENSAIO DE PILLING
Norma ficticia NF-5512. Avalia a formacao de bolinhas na superficie apos atrito controlado.
Tecidos com acabamento antipilling tendem a obter nota superior a 4 na escala de avaliacao.
"""


def indexar_corpus(tenant_id: str = TENANT_GOLDEN) -> Dict[str, int]:
    """Indexa os três documentos sintéticos no tenant informado. Devolve nome -> nº de chunks.

    O CSV passa por `extrair_documento_com_dados_tabulares` (a versão fiel, que preserva as
    linhas estruturadas) em vez de `extrair_documento` -- assim o motor tabular tem os dados reais
    para trabalhar, e não a reconstrução heurística por parsing de texto que a rota de upload da
    API acaba usando hoje.
    """
    resultado: Dict[str, int] = {}

    resultado[NOME_MANUAL] = rag_manager.indexar_documento(tenant_id, NOME_MANUAL, MANUAL_TECNICO)
    resultado[NOME_NORMAS] = rag_manager.indexar_documento(tenant_id, NOME_NORMAS, GUIA_NORMAS)

    unidades, sheets = document_extractors.extrair_documento_com_dados_tabulares(
        io.BytesIO(CATALOGO_TECIDOS.encode("utf-8")), NOME_CATALOGO
    )
    resultado[NOME_CATALOGO] = rag_manager.indexar_documento(
        tenant_id, NOME_CATALOGO, unidades, dados_tabulares=sheets
    )

    return resultado


def remover_corpus(tenant_id: str = TENANT_GOLDEN) -> None:
    for nome in (NOME_MANUAL, NOME_NORMAS, NOME_CATALOGO):
        rag_manager.remover_documento(tenant_id, nome)


def casos(tenant_id: str = TENANT_GOLDEN) -> List[CasoAvaliacao]:
    """Os 36 casos do golden set, 4 por categoria.

    Os critérios foram calibrados contra o texto REAL dos chunks (ver o bloco `__main__` deste
    arquivo, que imprime o corpus já chunkado) -- não contra o texto que o corpus "deveria"
    produzir. Isso importa porque o chunking não respeita fronteiras de seção: o manual vira 4
    chunks cujos limites cortam no meio de uma peça, e um critério escrito de cabeça falharia por
    motivo errado.

    Padrão dos critérios: **identificador da entidade + valor**, nunca o valor sozinho. "180"
    aparece como gramatura do TX-200 e como largura do TX-450 e do TX-910 -- exigir ["TX-200",
    "180"] no mesmo chunk elimina o falso positivo sem depender de o chunk vir formatado de um
    jeito específico.
    """
    def caso(**kwargs) -> CasoAvaliacao:
        return CasoAvaliacao(tenant_id=tenant_id, **kwargs)

    return [
        # ── lookup_direto: um atributo de uma entidade nomeada, presente literalmente ──────────
        caso(id="LD-01", categoria="lookup_direto",
             query="Qual a gramatura do tecido TX-310?",
             termos_relevantes=["TX-310", "240"]),
        caso(id="LD-02", categoria="lookup_direto",
             query="Qual a largura util do jaleco ambulatorial JL-100?",
             termos_relevantes=["JL-100", "150"]),
        caso(id="LD-03", categoria="lookup_direto",
             query="Qual o fornecedor do tecido TX-800?",
             termos_relevantes=["TX-800", "Fiacao Aurora"]),
        caso(id="LD-04", categoria="lookup_direto",
             query="Qual a composicao do tecido TX-750?",
             termos_relevantes=["TX-750", "92% poliamida"]),

        # ── numerico_exato: número/medida que precisa ser recuperado com a unidade certa ───────
        caso(id="NE-01", categoria="numerico_exato",
             query="Qual a gramatura em g/m2 do tecido da calca operacional?",
             termos_relevantes=["260 g/m2"]),
        caso(id="NE-02", categoria="numerico_exato",
             query="Quanto custa o metro do tecido Neoprene?",
             termos_relevantes=["TX-980", "47.25"]),
        caso(id="NE-03", categoria="numerico_exato",
             query="Qual o preco por metro do tecido Linho misto?",
             termos_relevantes=["Linho misto", "41.60"]),
        caso(id="NE-04", categoria="numerico_exato",
             query="Qual a largura em centimetros do tecido Moletom?",
             termos_relevantes=["Moletom", "180"]),

        # ── desambiguacao: quatro peças com a mesma estrutura de campos competem entre si ──────
        caso(id="DE-01", categoria="desambiguacao",
             query="Qual a gramatura do avental de cozinha?",
             termos_relevantes=["AV-220", "240"]),
        caso(id="DE-02", categoria="desambiguacao",
             query="Qual o acabamento da camisa polo corporativa PL-330?",
             termos_relevantes=["PL-330", "antipilling"]),
        caso(id="DE-03", categoria="desambiguacao",
             query="Qual o acabamento do avental AV-220?",
             termos_relevantes=["AV-220", "impermeabilizante"]),
        caso(id="DE-04", categoria="desambiguacao",
             query="Quais os aviamentos da calca operacional CL-440?",
             termos_relevantes=["CL-440", "passantes"]),

        # ── conceitual: a pergunta não contém o termo que está no documento ───────────────────
        caso(id="CO-01", categoria="conceitual",
             query="Qual peca tem protecao contra micro-organismos?",
             termos_relevantes=["antimicrobiano"]),
        caso(id="CO-02", categoria="conceitual",
             query="Qual peca resiste a formacao de bolinhas no tecido?",
             termos_relevantes=["antipilling"]),
        caso(id="CO-03", categoria="conceitual",
             query="Qual peca e indicada para trabalho com liquidos e respingos?",
             termos_relevantes=["hidrorrepelente"]),
        caso(id="CO-04", categoria="conceitual",
             query="Qual ensaio mede a variacao de tamanho da peca depois de lavar?",
             termos_relevantes=["NF-4405"]),

        # ── multi_documento: o vínculo peça→tecido está no manual, o atributo está no catálogo ─
        caso(id="MD-01", categoria="multi_documento",
             query="Qual o preco por metro do tecido usado no jaleco JL-100?",
             termos_relevantes=["TX-200", "18.50"]),
        caso(id="MD-02", categoria="multi_documento",
             query="Qual o fornecedor do tecido da camisa polo corporativa?",
             termos_relevantes=["TX-450", "Malharia Cristal"]),
        caso(id="MD-03", categoria="multi_documento",
             query="Qual o fornecedor do tecido usado na calca operacional?",
             termos_relevantes=["TX-520", "Tecelagem Bandeira"]),
        caso(id="MD-04", categoria="multi_documento",
             query="Quanto custa o metro do tecido do avental de cozinha?",
             termos_relevantes=["TX-310", "22.90"]),

        # ── tabular_agregacao: a resposta não existe no corpus, precisa ser calculada ──────────
        caso(id="TA-01", categoria="tabular_agregacao", resposta_computada=True,
             query="Quantos tecidos existem no catalogo?",
             termos_relevantes=["12"],
             # "12" sozinho casa por substring em lugares que não são resposta nenhuma:
             # "Gramatura: 120", "Preco por metro: 12.80" e até "NF-5512" (número de norma).
             # Excluir linha de catálogo ("Fornecedor:") e trecho de norma ("NF-") é mais estável
             # do que depender da frase exata que o motor tabular usa para relatar a contagem.
             termos_proibidos=["Fornecedor:", "NF-"]),
        caso(id="TA-02", categoria="tabular_agregacao", resposta_computada=True,
             query="Qual a gramatura media dos tecidos do catalogo?",
             # Média real = 2570/12 = 214,17. Substring "214.1" tolera arredondamento
             # (214.1/214.16/214.17) sem aceitar outro número qualquer.
             termos_relevantes=["214.1"]),
        caso(id="TA-03", categoria="tabular_agregacao", resposta_computada=True,
             query="Qual a soma dos precos por metro de todos os tecidos?",
             termos_relevantes=["327.4"]),
        caso(id="TA-04", categoria="tabular_agregacao", resposta_computada=True,
             query="Quantos fornecedores diferentes existem no catalogo?",
             # Uma resposta correta de DISTINCT precisa nomear os três fornecedores; nenhum chunk
             # do corpus contém os três juntos, então só um cálculo certo satisfaz o critério.
             termos_relevantes=["Fiacao Aurora", "Tecelagem Bandeira", "Malharia Cristal"]),

        # ── tabular_filtro: filtro numérico/comparativo sobre a tabela ─────────────────────────
        # Único caso de filtro cuja resposta abrange mais de uma linha: nenhum chunk do corpus
        # contém TX-910 e TX-980 juntos (são linhas separadas), então só um resultado computado
        # pelo motor tabular pode satisfazer o critério -- daí resposta_computada=True. Os outros
        # três casos de filtro têm resposta de uma linha só, e são satisfeitos pela recuperação
        # do chunk daquela linha.
        caso(id="TF-01", categoria="tabular_filtro", resposta_computada=True,
             query="Quais tecidos tem gramatura acima de 300?",
             termos_relevantes=["TX-910", "TX-980"],
             # Um filtro quebrado devolve as 12 linhas -- que contêm as duas certas. Os proibidos
             # são linhas que o filtro deveria ter descartado.
             termos_proibidos=["TX-200", "TX-700"]),
        caso(id="TF-02", categoria="tabular_filtro",
             query="Quais tecidos custam menos de 15 reais por metro?",
             termos_relevantes=["TX-700"],
             termos_proibidos=["TX-980", "TX-200"]),
        caso(id="TF-03", categoria="tabular_filtro",
             query="Qual o tecido mais caro por metro do catalogo?",
             termos_relevantes=["TX-980"],
             termos_proibidos=["TX-200"]),
        caso(id="TF-04", categoria="tabular_filtro",
             query="Qual o tecido mais leve do catalogo, de menor gramatura?",
             termos_relevantes=["TX-700"],
             termos_proibidos=["TX-980"]),

        # ── anti_alucinacao: a informação não existe em lugar nenhum da base ──────────────────
        caso(id="AA-01", categoria="anti_alucinacao", deve_abster=True,
             query="Qual o CNPJ do fornecedor Fiacao Aurora?",
             termos_relevantes=["CNPJ"]),
        caso(id="AA-02", categoria="anti_alucinacao", deve_abster=True,
             query="Qual o prazo de entrega do tecido TX-200?",
             termos_relevantes=["prazo de entrega"]),
        caso(id="AA-03", categoria="anti_alucinacao", deve_abster=True,
             query="Qual a norma de resistencia ao fogo aplicavel aos uniformes?",
             termos_relevantes=["fogo"]),
        caso(id="AA-04", categoria="anti_alucinacao", deve_abster=True,
             query="Qual o telefone de contato da Malharia Cristal?",
             termos_relevantes=["telefone"]),

        # ── ausencia_parcial: a entidade existe, o atributo perguntado não ────────────────────
        # Mais sutil que anti_alucinacao: cada termo existe isoladamente no corpus, mas nunca
        # juntos no mesmo chunk -- é a combinação que não existe.
        caso(id="AP-01", categoria="ausencia_parcial", deve_abster=True,
             query="Qual a gramatura do tecido TX-999?",
             termos_relevantes=["TX-999"]),
        caso(id="AP-02", categoria="ausencia_parcial", deve_abster=True,
             query="Qual o preco por metro do jaleco JL-100 pronto?",
             termos_relevantes=["JL-100", "Preco"]),
        caso(id="AP-03", categoria="ausencia_parcial", deve_abster=True,
             query="Quais as cores disponiveis do tecido TX-800?",
             termos_relevantes=["TX-800", "Cores"]),
        caso(id="AP-04", categoria="ausencia_parcial", deve_abster=True,
             query="Qual o acabamento do tecido TX-610?",
             termos_relevantes=["TX-610", "Acabamento"]),
    ]


if __name__ == "__main__":
    # Utilitário de calibração: indexa o corpus num tenant descartável e imprime os chunks reais,
    # para os casos serem escritos contra o texto que o pipeline de fato produz -- e não contra o
    # texto que o autor do golden set imagina que ele produz.
    import shutil
    import os

    tenant_debug = "rag_golden_set_calibracao"
    caminho = os.path.join("tenant_data", "chroma", tenant_debug)
    shutil.rmtree(caminho, ignore_errors=True)
    rag_manager._CHROMA_CLIENTS.pop(tenant_debug, None)

    contagens = indexar_corpus(tenant_debug)
    print("Chunks por documento:", contagens)

    colecao = rag_manager._obter_colecao_tenant(tenant_debug)
    dados = colecao.get(include=["documents", "metadatas"])
    for texto, meta in sorted(zip(dados["documents"], dados["metadatas"]), key=lambda p: (p[1].get("fonte", ""), p[1].get("chunk_index", 0))):
        print("\n" + "=" * 70)
        print(f"FONTE: {meta.get('fonte')} | chunk_index={meta.get('chunk_index')} | rotulo={meta.get('rotulo_unidade')}")
        print("-" * 70)
        print(texto)

    shutil.rmtree(caminho, ignore_errors=True)
