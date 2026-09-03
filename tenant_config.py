"""Configurações de Tenants para a aplicação Streamlit Senai LabFashion IA."""

PERFIS_USUARIO = {
    "dono_responsavel": {
        "nome": "Dono(a) / Responsável",
        "icone": "🧵",
        "descricao": "Visão geral do negócio, custos e estratégias",
        "rotulo_prompt": "Dono(a) ou Responsável Geral pela empresa de moda",
    },
    "producao": {
        "nome": "Time de Produção",
        "icone": "📐",
        "descricao": "Modelagem, tecidos, costura e processos técnicos",
        "rotulo_prompt": "integrante do Time de Produção (modelagem, tecidos, costura e processos técnicos)",
    },
    "criacao_estilo": {
        "nome": "Criação / Estilo",
        "icone": "🎨",
        "descricao": "Croquis, tendências, estética e conceito de coleção",
        "rotulo_prompt": "integrante do Time de Criação e Estilo (croquis, tendências e conceito de coleção)",
    },
}

TENANT_CONFIG = {
    "senai_labfashion": {
        "nome": "SENAI LabFashion IA",
        "cor_primaria": "#0047AB",
        "cor_secundaria": "#F47B20",
        "limite_mensagens_dia": 200,
        "limite_imagens_dia": 30,
        "base_prompt": """Você é o LabFashion IA do Senai LabFashion. Responda apenas sobre moda, têxtil, croquis e modelagem.
Mantenha tom técnico e profissional. Nunca gere conteúdo sexual, violento, discriminatório ou ilegal.
Recuse perguntas fora do escopo educadamente. Respeite as políticas de segurança (não mencione nem use pessoas reais ou celebridades).
Para temas sensíveis (como plus size, diversidade, sustentabilidade e cadeia produtiva), responda com respeito, precisão técnica e responsabilidade social.""",
        "modos": {
            "Consultor de Estilo": {
                "prompt": "Seu modo de atuação atual é: Consultor de Estilo. Ajude o usuário com consultoria de imagem, combinações de estilo, indicação de looks para diferentes ocasiões e biotipos, harmonização de cores (círculo cromático) e estética visual. Seja elegante, inspirador e dê dicas práticas de como se vestir bem.",
                "tools": None,
                "validade_cache_horas": 720,
            },
            "Professor Técnico": {
                "prompt": "Seu modo de atuação atual é: Professor Técnico. Foque inteiramente em modelagem teórica e prática (moulage, bi-dimensional), técnicas de costura, tipos de tecidos e fibras (suas propriedades, caimento e composição), confecção, fichas técnicas de produto e tecnologia da confecção. Seja didático, altamente técnico e preciso nas nomenclaturas do setor têxtil.",
                "tools": None,
                "validade_cache_horas": 720,
            },
            "Gerador de Croqui": {
                "prompt": "Seu modo de atuação atual é: Gerador de Croqui. Ajude o usuário a desenhar e conceber novos designs. Quando o usuário pedir um croqui, chame a ferramenta gerar_imagem_croqui com dois parâmetros obrigatórios: 1) prompt_visual: ultra-detalhado em inglês (pose, silhueta, cores exatas, textura, tecido, fundo neutro de estúdio fotográfico de moda); 2) resumo_confirmacao: uma frase curta em português simples e amigável, sem jargões técnicos de IA ou termos em inglês (ex: 'Um vestido midi floral, visto de frente'), descrevendo o que vai ser gerado do ponto de vista de um usuário leigo. Após gerar, descreva o conceito ao usuário em português.",
                "prompt_ilustracao": "Seu modo de atuação atual é: Gerador de Croqui (Estilo: Ilustração de Moda). Ajude o usuário a desenhar e conceber novos designs de ilustração artística de moda. Quando o usuário pedir um croqui, chame a ferramenta gerar_imagem_croqui com dois parâmetros obrigatórios: 1) prompt_visual: ultra-detalhado em inglês (pose dramática ou natural, silhueta estilizada, cores exatas, textura de tecido realista, iluminação de estúdio fotográfico de moda); 2) resumo_confirmacao: uma frase curta em português simples e amigável, sem jargões técnicos de IA ou termos em inglês (ex: 'Um vestido midi floral, visto de frente'), descrevendo o que vai ser gerado. Após gerar, descreva o conceito ao usuário em português.",
                "prompt_tecnico": "Seu modo de atuação atual é: Gerador de Croqui (Estilo: Desenho Técnico / Flat Sketch). Ajude o usuário a conceber desenhos técnicos de vestuário (flat sketch para ficha técnica). Quando o usuário pedir um croqui ou desenho técnico, chame a ferramenta gerar_imagem_croqui com dois parâmetros obrigatórios: 1) prompt_visual: detalhado em inglês focado estritamente em vetor técnico de vestuário sem corpo humano (flat garment schematic, vector line art, front view, clear stitching lines and seams, white background, black and white line drawing, minimal or no color rendering); 2) resumo_confirmacao: uma frase curta em português simples descrevendo a peça para desenho técnico (ex: 'Desenho técnico de jaqueta jeans com bolsos frontais'). Após gerar, descreva os detalhes construtivos ao usuário em português.",
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "gerar_imagem_croqui",
                        "description": "Gera uma imagem de croqui de moda a partir de um prompt visual em inglês e um resumo simples em português para confirmação do usuário",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt_visual": {
                                    "type": "string",
                                    "description": "Descrição detalhada do croqui em inglês: pose, silhueta, cores, tecido, fundo"
                                },
                                "resumo_confirmacao": {
                                    "type": "string",
                                    "description": "Frase curta em português simples, sem jargões técnicos, descrevendo a peça para confirmação do usuário (ex: 'Um vestido midi floral, visto de frente')"
                                }
                            },
                            "required": ["prompt_visual", "resumo_confirmacao"]
                        }
                    }
                }],
                "validade_cache_horas": 0,
            },
            "Tendências": {
                "prompt": "Seu modo de atuação atual é: Tendências. Analise macro e microtendências de moda global, coleções recentes de alta-costura e prêt-à-porter, comportamento de consumo de moda, cartela de cores sazonais e o impacto cultural de movimentos históricos na moda moderna. Traga insights informados sobre o futuro do mercado da moda.",
                "tools": [{"type": "web_search"}],
                "validade_cache_horas": 24,
            },
            "Análise de Dados": {
                "prompt": "Seu modo de atuação atual é: Análise de Dados. Interprete os resumos estatísticos estruturados previamente calculados pelo sistema (você não tem acesso aos dados brutos diretamente, apenas ao resumo estruturado gerado em Python). Responda sempre em português claro, didático e objetivo, sem jargões estatísticos desnecessários. NUNCA invente números, métricas ou cálculos que não estejam presentes no resumo fornecido. Se o usuário perguntar algo que exija dados não contidos no resumo estruturado (por exemplo, detalhes de uma linha específica ausente no resumo), explique educadamente que esse dado específico não consta no resumo disponível da planilha.",
                "tools": None,
                "validade_cache_horas": 0,
            },
            "Base de Conhecimento": {
                "prompt": (
                    "Seu modo de atuação atual é: Base de Conhecimento. Você é um assistente de consulta documental especializado em dados factuais, especificações técnicas, fichas técnicas, tabelas e manuais.\n\n"
                    "DIRETRIZES DE GROUNDEDNESS E PRECISÃO ESTRITA:\n"
                    "1. Responda EXCLUSIVAMENTE com base no CONTEXTO RECUPERADO fornecido no prompt. Não use conhecimento externo nem adicione suposições gerais.\n"
                    "2. NUNCA invente números, medidas, códigos, nomes, entidades ou especificações técnicas. Preserve unidades (g/m², oz, cm, mm, %, etc.) e códigos (ex: M518) exatamente como constam no contexto.\n"
                    "3. Se uma informação solicitada não estiver presente ou não puder ser confirmada com segurança nos trechos recuperados, responda com clareza e sem rodeios: 'Não encontrei essa informação no documento.'\n"
                    "4. Para perguntas comparativas (ex: entre entidades ou variantes): associe cada característica estritamente à sua entidade correta. Nunca misture nem transfira atributos de uma entidade para outra.\n"
                    "5. Para perguntas que conectam múltiplos conceitos/tópicos (multi-hop) que aparecem em trechos ou páginas diferentes: sintetize uma resposta conectando os diferentes trechos recuperados estritamente com base nas evidências presentes no texto. Se o documento abordar os temas separadamente sem detalhar explicitamente uma mecânica causal direta entre eles (ex: listar uma técnica e listar riscos em seções distintas), apresente o que o documento descreve sobre cada conceito e aponte com clareza que o material não detalha o mecanismo causal direto, em vez de inventar uma conexão inexistente.\n"
                    "6. Quando a pergunta utilizar um termo genérico de produto (ex: 'camisa jeans', 'camisa masculina'), resolva de forma determinística para a variante correspondente no documento (ex: 'camisa jeans' resolve para a variante Millie Denim Maskskin / 100% Liocel / 4,5 oz / lavagem clara), respondendo diretamente sem apontar falsos conflitos.\n"
                    "7. Se houver divergência real interna explicitamente descrita no documento sobre o mesmo item (ex: quantidades diferentes em tabela vs texto descritivo), informe ambos os valores sem inventar reconciliação.\n"
                    "8. Sempre cite a fonte e página utilizada quando disponível (ex: 'Segundo [Documento], página X...')."
                ),
                "tools": None,
                "validade_cache_horas": 0,
            },
        },
        "descricoes_modos": {
            "Consultor de Estilo": "👔 Consultor de Estilo (Estilo e Looks)",
            "Professor Técnico": "📐 Professor Técnico (Costura e Modelagem)",
            "Gerador de Croqui": "🎨 Gerador de Croqui (Desenho e Croquis)",
            "Tendências": "📈 Tendências (Consumo e Mercado)",
            "Análise de Dados": "📊 Análise de Dados (Planilhas e Indicadores)",
            "Base de Conhecimento": "📚 Base de Conhecimento (Materiais e Manuais)",
        },
        "descricoes_detalhadas": {
            "Consultor de Estilo": "👔 **Consultor de Estilo**: Focado em combinações, harmonia de cores, looks e consultoria de imagem pessoal.",
            "Professor Técnico": "📐 **Professor Técnico**: Especializado em costura, modelagem, tecidos e processos têxteis.",
            "Gerador de Croqui": "🎨 **Gerador de Croqui**: Cria conceitos visuais em 2 estilos: Ilustração de Moda (conceito artístico) ou Desenho Técnico / Flat Sketch (diagrama 2D com vistas frontal e traseira).",
            "Tendências": "📈 **Tendências**: Analisa comportamento de consumo, desfiles e previsões de mercado.",
            "Análise de Dados": "📊 **Análise de Dados**: Envie uma planilha de vendas, estoque ou produção e faça perguntas sobre os números.",
            "Base de Conhecimento": "📚 **Base de Conhecimento**: Pergunte sobre os materiais e documentos que a empresa disponibilizou (apostilas, manuais, fichas técnicas).",
        },
        "modo_padrao_por_perfil": {
            "dono_responsavel": "Análise de Dados",
            "producao": "Professor Técnico",
            "criacao_estilo": "Gerador de Croqui",
        },
        "perguntas_rapidas": {
            "Consultor de Estilo": [
                "🎨 Quais cores combinam com verde oliva?",
                "👔 Sugira um look casual elegante masculino.",
                "📐 Como valorizar a silhueta ampulheta?"
            ],
            "Professor Técnico": [
                "🪡 Qual agulha usar para costurar seda?",
                "✂️ Como fazer a graduação de moldes?",
                "🧵 Explique a diferença entre urdume e trama."
            ],
            "Gerador de Croqui": [
                "👗 Prompt para vestido de noiva minimalista.",
                "🎨 Ideia de croqui para coleção outono/inverno.",
                "✨ Como descrever tecidos brilhantes no prompt?"
            ],
            "Tendências": [
                "📈 Quais as cores tendência para esta estação?",
                "♻️ O que é upcycling na moda atual?",
                "🌍 Quais macro-tendências vêm da Geração Z?"
            ],
            "Análise de Dados": [
                "📊 Qual o resumo geral e principais totais da planilha?",
                "📈 Quais são os itens ou categorias mais frequentes?",
                "📋 Quais métricas e médias foram identificadas?"
            ],
            "Base de Conhecimento": [
                "📚 O que os materiais da empresa dizem sobre processos técnicos?",
                "📋 Quais diretrizes e especificações constam nos documentos?",
                "🔍 Resuma os pontos principais do material indexado."
            ]
        },
        "perguntas_por_perfil": {
            "dono_responsavel": {
                "Análise de Dados": [
                    "💰 Qual o total acumulado e a média dos valores na planilha?",
                    "📊 Quais categorias ou produtos têm maior volume de ocorrências?",
                    "📈 Quais são os valores mínimos e máximos identificados?"
                ],
                "Tendências": [
                    "📈 Quais as principais tendências de consumo para a próxima estação?",
                    "💰 Como otimizar custos de coleção mantendo o valor percebido?",
                    "🌍 Qual o impacto das macro-tendências globais no mercado de moda?"
                ],
                "Consultor de Estilo": [
                    "👔 Como posicionar o estilo da marca para o nosso público-alvo?",
                    "🎨 Quais combinações de cores agregam mais valor comercial?",
                    "📐 Como adequar o mix de produtos aos biotipos dos clientes?"
                ],
                "Professor Técnico": [
                    "🧵 Como avaliar o custo-benefício e viabilidade de novos tecidos?",
                    "✂️ Quais gargalos técnicos mais afetam o prazo de entrega?",
                    "🪡 Como padronizar o controle de qualidade na confecção?"
                ],
                "Gerador de Croqui": [
                    "✨ Conceito visual de coleção executiva minimalista.",
                    "👗 Ideias de croqui para linha premium da marca.",
                    "🎨 Como transmitir sofisticação comercial através dos croquis?"
                ],
                "Base de Conhecimento": [
                    "📋 Quais normas e manuais internos da empresa constam nos materiais?",
                    "📊 Quais diretrizes estratégicas e de qualidade estão descritas nos documentos?",
                    "📑 Resuma os principais procedimentos operacionais documentados."
                ]
            },
            "producao": {
                "Professor Técnico": [
                    "🪡 Qual agulha e linha ideais para tecidos planos finos?",
                    "✂️ Como calcular o consumo e encaixe de tecido com precisão?",
                    "🧵 Qual a diferença prática entre urdume e trama na costura?"
                ],
                "Análise de Dados": [
                    "📦 Qual a média e o volume total dos itens registrados?",
                    "🧵 Quais tipos de materiais ou produtos aparecem com mais frequência?",
                    "📉 Há registros com quantidades mínimas ou pontos de atenção?"
                ],
                "Gerador de Croqui": [
                    "📐 Como traduzir um croqui complexo em ficha técnica de modelagem?",
                    "👗 Prompt para croqui técnico focado em detalhes de costura.",
                    "🎨 Como visualizar caimento de tecido pesado em croqui?"
                ],
                "Consultor de Estilo": [
                    "📐 Quais tecidos proporcionam melhor caimento para cada biotipo?",
                    "👔 Como garantir a vestibilidade mantendo a proposta de estilo?",
                    "🎨 Quais acabamentos agregam melhor estrutura ao look?"
                ],
                "Tendências": [
                    "♻️ Quais tecidos sustentáveis estão em alta para produção?",
                    "📈 Novas tecnologias têxteis para aumento de durabilidade.",
                    "🌍 Inovações em processos de tingimento e acabamento eco-friendly."
                ],
                "Base de Conhecimento": [
                    "🧵 Quais especificações técnicas de costura constam nas apostilas e manuais?",
                    "📐 Quais tabelas de medidas e moldes estão descritas nos documentos?",
                    "🪡 Quais passos de montagem e acabamento são recomendados nas fichas?"
                ]
            },
            "criacao_estilo": {
                "Gerador de Croqui": [
                    "🎨 Croqui de vestido de festa fluido com movimento natural.",
                    "✨ Ideias inovadoras de silhueta para coleção outono/inverno.",
                    "👗 Prompt para conjunto alfaiataria moderno e desconstruído."
                ],
                "Análise de Dados": [
                    "🎨 Quais modelos ou categorias são mais frequentes na planilha?",
                    "👗 Como estão distribuídas as ocorrências por tipo de peça?",
                    "📊 Qual o volume total de itens cadastrados?"
                ],
                "Tendências": [
                    "📈 Cartela de cores e estampas em alta para a próxima estação.",
                    "🌍 Macro-tendências de comportamento da Geração Z na moda.",
                    "♻️ Como aplicar o conceito de upcycling na criação de modelos."
                ],
                "Consultor de Estilo": [
                    "🎨 Quais harmonias de cores valorizam estampas exclusivas?",
                    "👔 Sugestões de combinações de texturas para editorial de moda.",
                    "📐 Como compor looks versátiles para a nova coleção?"
                ],
                "Professor Técnico": [
                    "🧵 Quais tecidos transmitem o caimento ideal para este design?",
                    "✂️ Como viabilizar recortes complexos sem perder a estrutura?",
                    "🪡 Técnicas de moulage para desenvolver formas orgânicas."
                ],
                "Base de Conhecimento": [
                    "🎨 Quais conceitos de coleção e diretrizes criativas estão nos documentos?",
                    "📖 O que as apostilas internas descrevem sobre harmonia e estética?",
                    "✨ Quais fichas de inspiração e referências foram cadastradas?"
                ]
            }
        }
    }
}


