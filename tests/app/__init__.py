# -*- coding: utf-8 -*-

import os

# Fase 16, Bloco L: o `.env` real de quem roda a suíte pode ter `{TENANT}_LOGIN_SENHA`
# configurada (login por pessoa/tenant) -- isso muda o comportamento do gate de acesso para
# QUALQUER teste que rode neste processo (ver `_tenants_com_login_configurado` em `api/main.py`),
# derrubando testes que assumem o modo legado de senha única. Importa `api.main` uma vez aqui
# (dispara `load_dotenv()`, populando `os.environ` a partir do `.env` real) e remove essas
# variáveis do ambiente do processo de teste logo em seguida -- a suíte fica isolada do que
# estiver configurado na máquina de quem a roda. Testes que precisam de um tenant com login
# configurado (ex.: `test_login_por_tenant.py`) definem a própria variável no `setUp` deles,
# depois desta varredura já ter rodado.
#
# Precisa estar em `tests/app/__init__.py`, não em `tests/__init__.py`: `python -m unittest
# discover -s tests` trata `tests` como `top_level_dir` (adicionado ao sys.path), então os módulos
# são importados como `app.test_X`, não `tests.app.test_X` -- `tests/__init__.py` nunca chega a
# ser importado nesse modo.
import api.main as _api_main  # noqa: F401

for _chave in list(os.environ):
    if _chave.endswith("_LOGIN_SENHA"):
        os.environ.pop(_chave, None)
