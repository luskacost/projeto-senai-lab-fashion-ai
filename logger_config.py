# -*- coding: utf-8 -*-
"""Módulo de configuração centralizada de logging estruturado para o Senai LabFashion IA.

SEGURANÇA E PRIVACIDADE DE DADOS:
Nenhuma chave de API (ex: GROQ_API_KEY), senha de administração (ex: ADMIN_PASSWORD) ou conteúdo
integral/bruto de prompts digitados pelos usuários deve ser gravado em log.
Apenas metadados operacionais (tenant_id, modo de IA, tipo de evento de negócio, mensagens técnicas
de erro e stack traces do sistema) são registrados.
"""

import os
import logging
import sys
from logging.handlers import RotatingFileHandler

# Fase 9/Bloco E: nível configurável por variável de ambiente (default INFO, igual ao
# comportamento anterior) -- útil para baixar pra DEBUG num ambiente de investigação sem
# precisar editar código, ou subir pra WARNING em produção pra reduzir volume de log.
NIVEL_LOG = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)


class TenantFormatter(logging.Formatter):
    """Formatter customizado que garante a presença do campo tenant_id no registro de log,

    utilizando 'desconhecido' como fallback caso não tenha sido fornecido.
    """

    def format(self, record):
        if not hasattr(record, "tenant_id") or not record.tenant_id:
            record.tenant_id = "desconhecido"
        return super().format(record)


class TenantAdapter(logging.LoggerAdapter):
    """LoggerAdapter para injetar automaticamente o tenant_id nas chamadas de log."""

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        tenant = extra.get("tenant_id", self.extra.get("tenant_id", "desconhecido"))
        kwargs["extra"] = extra
        extra["tenant_id"] = tenant
        return msg, kwargs


_logger_inicializado = False


def _configurar_logger_base() -> logging.Logger:
    global _logger_inicializado
    logger = logging.getLogger("labfashion_ia")
    logger.setLevel(NIVEL_LOG)

    if not _logger_inicializado:
        os.makedirs("logs", exist_ok=True)
        caminho_log = os.path.join("logs", "app.log")

        formato = "%(asctime)s | %(levelname)s | tenant=%(tenant_id)s | %(message)s"
        formatter = TenantFormatter(formato, datefmt="%Y-%m-%d %H:%M:%S")

        # Configura rotação automática (5MB por arquivo, mantém até 5 backups antigos)
        file_handler = RotatingFileHandler(
            caminho_log,
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(NIVEL_LOG)
        file_handler.setFormatter(formatter)

        # Handler de stdout (Fase 9/Bloco E): essencial pra rodar num contêiner/servidor real,
        # onde o supervisor de processo/orquestrador (Docker, systemd, etc.) coleta logs via
        # stdout/stderr -- só o arquivo local não seria visível nessas ferramentas.
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setLevel(NIVEL_LOG)
        stdout_handler.setFormatter(formatter)

        # Evita duplicar handlers se a função for chamada mais de uma vez
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(stdout_handler)

        _logger_inicializado = True

    return logger


def obter_logger(tenant_id: str = None) -> TenantAdapter:
    """Retorna um LoggerAdapter pré-configurado com o tenant_id especificado (ou 'desconhecido')."""
    logger_base = _configurar_logger_base()
    return TenantAdapter(logger_base, {"tenant_id": tenant_id or "desconhecido"})
