# -*- coding: utf-8 -*-
"""Insere os placeholders do docxtpl no template .docx da ficha técnica (Fase 11, Task 9).

O arquivo que o usuário forneceu (`templates/ficha_tecnica_v1.docx`) é um formulário em branco:
os campos são linhas de sublinhado ("____") para preencher à mão, não placeholders. Este script
faz a conversão de uma vez -- substitui cada linha de sublinhado pelo `{{ ... }}` correspondente e
prepara as tabelas dinâmicas com `{%tr for ... %}`.

Está versionado (em vez de ter sido uma edição manual no Word) por dois motivos:

1. **Reprodutibilidade.** Se o usuário enviar uma v2 do formulário em branco, rodar este script
   nela reproduz exatamente a mesma anotação, sem depender de ninguém lembrar quais células
   recebem o quê.
2. **Segurança do run splitting.** Editar essas células no Word faria o próprio Word fatiar o
   texto em vários runs e quebrar os placeholders (ver fichas_template.py). Escrevendo pelo
   python-docx, cada placeholder cai inteiro dentro de um run só -- e o preflight comprova.

Uso:
    python scripts/anotar_template.py [caminho_do_docx]

O script **recusa rodar** se a estrutura não for a do formulário em branco esperado (número de
tabelas/linhas/colunas), para nunca anotar duas vezes o mesmo arquivo nem mutilar um documento
diferente por engano.
"""

import copy
import os
import sys

from docx import Document
from docx.enum.table import WD_ROW_HEIGHT_RULE
from docx.shared import Cm
from docx.table import Table
from docx.text.paragraph import Paragraph

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fichas_template import (  # noqa: E402  (precisa do sys.path acima)
    CAMINHO_TEMPLATE,
    formatar_relatorio,
    inspecionar_template,
)

# Estrutura do formulário em branco, como recebido. É a assinatura que o script exige encontrar
# antes de modificar qualquer coisa -- (linhas, colunas) de cada uma das 12 tabelas.
ESTRUTURA_ESPERADA = [
    (2, 4),   # 0  cabeçalho: logo + título + REF/DATA/PÁG
    (4, 4),   # 1  IDENTIFICAÇÃO DO PRODUTO
    (5, 5),   # 2  CORES / BENEFICIAMENTOS  (cabeçalho + 4 linhas em branco)
    (3, 12),  # 3  GRADE parte 1 (PP..XG, 34..44) + 2 linhas de checkbox
    (1, 6),   # 4  GRADE parte 2 (46..56), sem linha de checkbox
    (6, 6),   # 5  AVIAMENTOS (cabeçalho + 5 linhas)
    (6, 7),   # 6  TECIDOS (cabeçalho + 5 linhas)
    (1, 4),   # 7  AMOSTRA DE TECIDOS -- rótulos
    (2, 4),   # 8  AMOSTRA DE TECIDOS -- espaço físico p/ colar amostra
    (3, 5),   # 9  CUSTOS
    (7, 3),   # 10 SEQUÊNCIA OPERACIONAL (cabeçalho + 6 etapas)
    (4, 4),   # 11 MODELAGEM (cabeçalho + 3 linhas)
]

# (tabela, linha, coluna) -> texto que substitui o conteúdo da célula.
CELULAS = {
    # Cabeçalho. PÁG. fica de fora: é numeração da página impressa, não dado da ficha.
    (0, 0, 0): "{{ logo }}",
    (0, 1, 1): "REF.: {{ ref }}",
    (0, 1, 2): "DATA: {{ data }}",

    # IDENTIFICAÇÃO DO PRODUTO (coluna par = rótulo fixo, coluna ímpar = valor).
    (1, 0, 1): "{{ nome }}",
    (1, 0, 3): "{{ colecao }}",
    (1, 1, 1): "{{ descricao }}",
    (1, 1, 3): "{{ designer }}",
    (1, 2, 1): "{{ tecnica }}",
    (1, 2, 3): "{{ empresa }}",
    (1, 3, 1): "{{ ref }}",   # "CÓD. / REF." repete o mesmo dado do cabeçalho, de propósito
    (1, 3, 3): "{{ data }}",

    # CORES / BENEFICIAMENTOS -- linha 1 abre o laço, linha 2 é o modelo, linha 3 fecha.
    (2, 1, 0): "{%tr for cb in cores_beneficiamentos %}",
    (2, 2, 0): "{{ cb.item }}",
    (2, 2, 1): "{{ cb.descricao }}",
    (2, 2, 2): "{{ cb.cor }}",
    (2, 2, 3): "{{ cb.beneficiamento }}",
    (2, 2, 4): "{{ cb.observacoes }}",
    (2, 3, 0): "{%tr endfor %}",

    # AVIAMENTOS
    (5, 1, 0): "{%tr for a in aviamentos %}",
    (5, 2, 0): "{{ a.descricao }}",
    (5, 2, 1): "{{ a.composicao }}",
    (5, 2, 2): "{{ a.cor }}",
    (5, 2, 3): "{{ a.quantidade }}",
    (5, 2, 4): "{{ a.fornecedor }}",
    (5, 2, 5): "{{ a.preco }}",
    (5, 3, 0): "{%tr endfor %}",

    # TECIDOS
    (6, 1, 0): "{%tr for t in tecidos %}",
    (6, 2, 0): "{{ t.descricao }}",
    (6, 2, 1): "{{ t.composicao }}",
    (6, 2, 2): "{{ t.cor }}",
    (6, 2, 3): "{{ t.quantidade }}",
    (6, 2, 4): "{{ t.largura }}",
    (6, 2, 5): "{{ t.fornecedor }}",
    (6, 2, 6): "{{ t.preco }}",
    (6, 3, 0): "{%tr endfor %}",

    # CUSTOS: uma linha de valores + uma linha de observação por categoria.
    (9, 1, 0): "R$ {{ custo_aviamentos }}",
    (9, 1, 1): "R$ {{ custo_tecidos }}",
    (9, 1, 2): "R$ {{ custo_costura }}",
    (9, 1, 3): "R$ {{ custo_outros }}",
    (9, 1, 4): "R$ {{ custo_total }}",
    (9, 2, 0): "OBS.: {{ obs_aviamentos }}",
    (9, 2, 1): "OBS.: {{ obs_tecidos }}",
    (9, 2, 2): "OBS.: {{ obs_costura }}",
    (9, 2, 3): "OBS.: {{ obs_outros }}",
    (9, 2, 4): "OBS.: {{ obs_total }}",

    # SEQUÊNCIA OPERACIONAL -- a coluna ETAPA é numerada pelo próprio laço (loop.index), não é
    # dado extraído (por isso não existe no schema da Task 1).
    (10, 1, 0): "{%tr for op in sequencia_operacional %}",
    (10, 2, 0): "{{ loop.index }}",
    (10, 2, 1): "{{ op.descricao }}",
    (10, 2, 2): "{{ op.maquinas }}",
    (10, 3, 0): "{%tr endfor %}",

    # MODELAGEM -- partes/observações variam por linha; modelista e quantidade de moldes são
    # valores únicos da ficha e só aparecem na primeira linha (decisão confirmada com o usuário).
    # Consequência para o render (Task 10): `partes` nunca pode chegar vazia, senão a linha
    # inteira some e leva junto modelista/nº de moldes.
    (11, 1, 0): "{%tr for p in partes %}",
    (11, 2, 0): "{{ p.descricao }}",
    (11, 2, 1): "{{ numero_moldes if loop.first else '' }}",
    (11, 2, 2): "{{ modelista if loop.first else '' }}",
    (11, 2, 3): "{{ p.observacoes }}",
    (11, 3, 0): "{%tr endfor %}",
}

# Células das linhas de abertura/fechamento de laço que precisam ficar vazias: a linha inteira é
# consumida pelo docxtpl, mas deixar os "____" do formulário nelas atrapalha a leitura do template
# aberto no Word (parece que sobrou lixo).
CELULAS_A_LIMPAR = [
    (2, 1, c) for c in range(1, 5)
] + [
    (2, 3, c) for c in range(1, 5)
] + [
    (5, 1, c) for c in range(1, 6)
] + [
    (5, 3, c) for c in range(1, 6)
] + [
    (6, 1, c) for c in range(1, 7)
] + [
    (6, 3, c) for c in range(1, 7)
] + [
    (10, 1, c) for c in range(1, 3)
] + [
    (10, 3, c) for c in range(1, 3)
] + [
    (11, 1, c) for c in range(1, 4)
] + [
    (11, 3, c) for c in range(1, 4)
]

# Linhas em branco que sobram depois do trio for/modelo/endfor. O formulário impresso trazia
# várias linhas fixas para preencher à mão; com o laço, a linha-modelo é repetida conforme os
# dados e as demais viram lixo.
LINHAS_A_REMOVER = {
    2: [4],                 # CORES / BENEFICIAMENTOS: sobra 1
    3: [2],                 # GRADE: 2ª linha de checkbox, duplicada (normalização aprovada)
    5: [4, 5],              # AVIAMENTOS: sobram 2
    6: [4, 5],              # TECIDOS: sobram 2
    10: [4, 5, 6],          # SEQUÊNCIA OPERACIONAL: sobram 3
    # MODELAGEM (11) já tem exatamente 3 linhas além do cabeçalho -- nada a remover.
}

# Tamanhos da grade por posição de coluna, nas duas tabelas em que ela foi diagramada.
GRADE_TABELA_3 = ["PP", "P", "M", "G", "GG", "XG", "34", "36", "38", "40", "42", "44"]
GRADE_TABELA_4 = ["46", "48", "50", "52", "54", "56"]

# Rótulos que separam visualmente os dois grupos de tamanhos. O formulário original diagramou
# comerciais (PP..XG) e numéricos (34..56) numa faixa contínua de colunas, sem nada indicando onde
# um grupo termina e o outro começa -- o editor web já separava, o documento impresso não.
# Faixas são (primeira_coluna, ultima_coluna) inclusivas, na linha de rótulos de cada tabela.
ROTULOS_GRADE_TABELA_3 = [
    ((0, 5), "TAMANHOS COMERCIAIS"),   # PP..XG
    ((6, 11), "TAMANHOS NUMÉRICOS"),   # 34..44
]
ROTULOS_GRADE_TABELA_4 = [
    ((0, 5), "TAMANHOS NUMÉRICOS (CONT.)"),  # 46..56, continuação do bloco acima
]

# Altura reservada para o desenho técnico. Valor inicial conservador: grande o bastante para um
# desenho legível, pequeno o bastante para não empurrar a ficha de 3 para 4 páginas. A checagem
# real de paginação só é possível quando houver renderização em PDF (Task 13/14) -- ajustar lá se
# necessário.
ALTURA_AREA_DESENHO_CM = 6.0


def _definir_texto_celula(celula, texto: str) -> None:
    """Escreve `texto` na célula mantendo tudo num único run.

    Escreve no run que já tinha texto (é ele que carrega a formatação visível -- fonte, tamanho,
    negrito) e esvazia os outros. Cada célula do template tem exatamente um parágrafo com um run
    vazio + um run com o conteúdo; preservar essa forma é o que garante que o placeholder saia
    contíguo no XML e o docxtpl consiga enxergá-lo.
    """
    paragrafo = celula.paragraphs[0]
    if not paragrafo.runs:
        paragrafo.add_run(texto)
        return

    indice_alvo = next((i for i, run in enumerate(paragrafo.runs) if (run.text or "").strip()), 0)
    for indice, run in enumerate(paragrafo.runs):
        run.text = texto if indice == indice_alvo else ""


def _validar_estrutura(doc: Document) -> None:
    estrutura = [(len(t.rows), len(t.columns)) for t in doc.tables]
    if estrutura != ESTRUTURA_ESPERADA:
        raise SystemExit(
            "Estrutura inesperada -- o script não vai modificar este arquivo.\n"
            f"  esperado: {ESTRUTURA_ESPERADA}\n"
            f"  encontrado: {estrutura}\n"
            "Se o template já foi anotado antes, não rode de novo: use o arquivo versionado no Git."
        )


def _remover_linhas(tabela, indices) -> None:
    for indice in sorted(indices, reverse=True):
        elemento = tabela.rows[indice]._tr
        elemento.getparent().remove(elemento)


def _adicionar_secao_desenho(doc: Document) -> None:
    """Cria a seção "DESENHO TÉCNICO" na primeira página, logo abaixo da identificação do produto.

    O formulário oficial não reservou espaço para o desenho -- só o PDF de referência que o
    usuário enviou antes tinha essa área. Sem ela, o desenho aprovado (Bloco C) não teria onde ser
    impresso. Decisão confirmada com o usuário: adicionar a seção em vez de sacrificar a área de
    AMOSTRA DE TECIDOS, que serve para colar amostras físicas de tecido na ficha impressa.

    Título e caixa são cópias de elementos que já existem no documento (um título de seção e a
    tabela da amostra), para herdarem fonte, bordas e largura sem precisar recriar formatação --
    e assim a seção nova não destoa visualmente do resto da ficha.
    """
    titulo_modelo = next(p for p in doc.paragraphs if p.text.strip() == "CORES / BENEFICIAMENTOS")
    novo_titulo = copy.deepcopy(titulo_modelo._p)

    caixa_modelo = doc.tables[8]  # AMOSTRA DE TECIDOS: mesma largura e bordas do resto da ficha
    nova_caixa = copy.deepcopy(caixa_modelo._tbl)

    # Inserir a caixa primeiro e o título depois faz os dois caírem na ordem certa, já que
    # addnext() sempre insere imediatamente após o elemento de referência.
    ancora = doc.tables[1]._tbl  # IDENTIFICAÇÃO DO PRODUTO
    ancora.addnext(nova_caixa)
    ancora.addnext(novo_titulo)

    Paragraph(novo_titulo, doc).runs[0].text = "DESENHO TÉCNICO"

    tabela = Table(nova_caixa, doc)
    _remover_linhas(tabela, [1])
    celula = tabela.rows[0].cells[0].merge(tabela.rows[0].cells[-1])

    # Mesclar concatena os parágrafos de todas as células envolvidas -- sem isso, a caixa do
    # desenho herdaria os três "ESPAÇO PARA AMOSTRA" das outras colunas junto com o placeholder.
    for paragrafo in celula.paragraphs[1:]:
        paragrafo._p.getparent().remove(paragrafo._p)
    _definir_texto_celula(celula, "{{ desenho_tecnico }}")

    # Sem altura explícita a linha encolhe para uma linha de texto -- o desenho precisa de área
    # reservada de verdade. AT_LEAST deixa a caixa crescer se a imagem inserida for maior.
    tabela.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    tabela.rows[0].height = Cm(ALTURA_AREA_DESENHO_CM)


def _adicionar_linha_de_marcas(tabela, tamanhos) -> None:
    """A tabela 4 (tamanhos 46-56) veio só com o cabeçalho, sem linha de marcação embaixo -- ao
    contrário da tabela 3. Duplica o cabeçalho como nova linha (preservando larguras e bordas da
    própria tabela) e a transforma na linha de marcas."""
    nova_linha = copy.deepcopy(tabela.rows[0]._tr)
    tabela.rows[0]._tr.addnext(nova_linha)

    for indice_coluna, tamanho in enumerate(tamanhos):
        celula = tabela.rows[1].cells[indice_coluna]
        _definir_texto_celula(celula, "{{ grade['" + tamanho + "'] }}")
        for run in celula.paragraphs[0].runs:
            run.bold = False  # o cabeçalho é negrito; a linha de marcas não deve ser


def _adicionar_linha_de_rotulos(tabela, faixas) -> None:
    """Insere, acima do cabeçalho da grade, uma linha de rótulos mesclados por grupo de tamanhos.

    A linha nasce como cópia do próprio cabeçalho para herdar larguras de coluna, bordas e negrito
    sem recriar formatação -- mesma técnica de `_adicionar_linha_de_marcas`. Depois cada faixa de
    colunas vira uma célula só, com o rótulo do grupo.
    """
    nova_linha = copy.deepcopy(tabela.rows[0]._tr)
    tabela.rows[0]._tr.addprevious(nova_linha)

    for (primeira, ultima), rotulo in faixas:
        celulas = tabela.rows[0].cells
        celula = celulas[primeira].merge(celulas[ultima])

        # Mesclar concatena os parágrafos de todas as células envolvidas: sem limpar, o rótulo
        # sairia seguido dos nomes de tamanho que vieram do cabeçalho copiado.
        for paragrafo in celula.paragraphs[1:]:
            paragrafo._p.getparent().remove(paragrafo._p)
        _definir_texto_celula(celula, rotulo)
        for run in celula.paragraphs[0].runs:
            run.bold = True


def anotar(caminho: str) -> None:
    doc = Document(caminho)
    _validar_estrutura(doc)

    for (indice_tabela, indice_linha, indice_coluna), texto in CELULAS.items():
        celula = doc.tables[indice_tabela].rows[indice_linha].cells[indice_coluna]
        _definir_texto_celula(celula, texto)

    for indice_tabela, indice_linha, indice_coluna in CELULAS_A_LIMPAR:
        celula = doc.tables[indice_tabela].rows[indice_linha].cells[indice_coluna]
        _definir_texto_celula(celula, "")

    # Grade: a linha 1 da tabela 3 vira as marcas dos 12 primeiros tamanhos.
    for indice_coluna, tamanho in enumerate(GRADE_TABELA_3):
        celula = doc.tables[3].rows[1].cells[indice_coluna]
        _definir_texto_celula(celula, "{{ grade['" + tamanho + "'] }}")

    _adicionar_linha_de_marcas(doc.tables[4], GRADE_TABELA_4)

    for indice_tabela, indices in LINHAS_A_REMOVER.items():
        _remover_linhas(doc.tables[indice_tabela], indices)

    # Depois das remoções por índice acima, senão a linha de rótulos deslocaria tudo.
    _adicionar_linha_de_rotulos(doc.tables[3], ROTULOS_GRADE_TABELA_3)
    _adicionar_linha_de_rotulos(doc.tables[4], ROTULOS_GRADE_TABELA_4)

    # Por último: inserir uma tabela nova desloca os índices de todas as tabelas seguintes, então
    # isso só pode acontecer depois de todas as operações endereçadas por índice acima.
    _adicionar_secao_desenho(doc)

    doc.save(caminho)
    print(f"Template anotado: {caminho}")


if __name__ == "__main__":
    caminho_alvo = sys.argv[1] if len(sys.argv) > 1 else CAMINHO_TEMPLATE
    anotar(caminho_alvo)
    print()
    print(formatar_relatorio(inspecionar_template(caminho_alvo)))
