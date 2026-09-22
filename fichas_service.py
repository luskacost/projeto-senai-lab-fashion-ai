# -*- coding: utf-8 -*-
"""Criação de ficha técnica a partir de texto livre (Fase 11/12).

Extraído de `POST /fichas` (api/main.py) para ter uma única implementação do pipeline
extração → verificação de proveniência → persistência, reaproveitada também pelo atalho
`gerar_ficha_tecnica` do chat (Fase 12) -- ver `agente_ferramentas._handler_gerar_ficha_tecnica`.
Antes desta Fase 12, essa lógica só existia inline na rota; duplicá-la ali e no handler do chat
teria sido o mesmo erro que `agente_ferramentas.py` documenta ter corrigido para schema+handler de
ferramenta: dois lugares que podem divergir em silêncio.

Não verifica cota diária de propósito -- isso é decisão de quem chama (a rota sabe traduzir uma
cota estourada para HTTP 429; o handler do chat sabe traduzir para uma mensagem de erro
conversacional), mesmo padrão que a checagem de moderação/cota de `gerar_imagem_croqui` já seguia:
fica na camada que decide o que fazer com o resultado, não na camada que só executa.
"""

from typing import Any, Dict, List, Tuple

from fichas_extracao import extrair_dados
from fichas_modelo import STATUS_EM_REVISAO, garantir_chaves_nao_extraidas
from fichas_repo import criar_ficha, salvar_ficha
from fichas_verificacao import verificar_proveniencia
from usage_tracker import incrementar_uso


def criar_ficha_a_partir_de_texto(
    tenant_id: str, texto_origem: str, client: Any, precificacao_padrao: Any = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Cria e persiste uma ficha a partir de texto livre. Devolve (ficha, alertas_de_proveniencia).

    Chamada real de API (extrair_dados, Structured Outputs) -- o chamador decide se/quando essa
    chamada é autorizada (cota diária), este módulo só executa o pipeline depois que essa decisão
    já foi tomada. `precificacao_padrao` (Fase 14, Bloco P, Task 19) só repassa a semente de
    ficha_vazia() para fichas_repo.criar_ficha -- ver docstring lá.
    """
    dados_extraidos = extrair_dados(client, texto_origem, tenant_id)
    dados_corrigidos, alertas = verificar_proveniencia(dados_extraidos, texto_origem)
    # A extração devolve exatamente as chaves de SCHEMA_EXTRACAO, e este dict substitui "dados"
    # inteiro logo abaixo -- sem isto, uma ficha criada por texto nasceria sem "medidas" (Fase 14,
    # Bloco M), enquanto uma ficha em branco teria a chave.
    garantir_chaves_nao_extraidas(dados_corrigidos)

    ficha = criar_ficha(tenant_id, texto_origem=texto_origem, precificacao_padrao=precificacao_padrao)
    ficha["dados"] = dados_corrigidos
    ficha["status"] = STATUS_EM_REVISAO
    ficha = salvar_ficha(tenant_id, ficha)
    incrementar_uso(tenant_id, "fichas")

    return ficha, alertas
