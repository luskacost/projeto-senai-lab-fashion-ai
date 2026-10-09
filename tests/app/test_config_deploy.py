# -*- coding: utf-8 -*-
"""Configuração de deploy (Dockerfile / docker-compose.prod.yml) -- propriedades de segurança.

Não testa código Python do app: testa os arquivos de deploy, porque um erro neles não aparece em
nenhum outro teste e só se manifesta em produção.

O principal: qual IP o backend enxerga atrás de um proxy (Railway, Traefik). O bloqueio de login
(Fase 14) e o limite de requisições (Fase 16, D1) são por IP. Com `--forwarded-allow-ips=*`, o
uvicorn pega o PRIMEIRO item do `X-Forwarded-For` -- e o primeiro item é o que o próprio cliente
mandou, porque proxies como o do Railway só ACRESCENTAM o IP real no fim. Um atacante forjaria o
cabeçalho e escaparia do bloqueio. Confiando só em redes privadas (onde os proxies vivem), o
uvicorn percorre a lista de trás pra frente e devolve o primeiro IP não-confiável: o real.
"""

import os
import re
import unittest

from uvicorn.middleware.proxy_headers import _TrustedHosts

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _ler(caminho_relativo: str) -> str:
    with open(os.path.join(RAIZ, caminho_relativo), encoding="utf-8") as f:
        return f.read()


def _valor_forwarded_allow_ips() -> str:
    achado = re.search(r'^ENV FORWARDED_ALLOW_IPS="?([^"\n]+)"?', _ler("Dockerfile"), re.MULTILINE)
    return achado.group(1).strip() if achado else ""


class TestIpRealAtrasDoProxy(unittest.TestCase):

    def test_dockerfile_define_proxies_confiaveis_sem_curinga(self):
        valor = _valor_forwarded_allow_ips()
        self.assertTrue(valor, "Dockerfile precisa definir ENV FORWARDED_ALLOW_IPS")
        self.assertNotIn("*", valor)

    def test_cliente_nao_consegue_forjar_o_proprio_ip(self):
        confiaveis = _TrustedHosts(_valor_forwarded_allow_ips())
        # O cliente mandou "6.6.6.6"; o proxy acrescentou o IP real que viu (200.150.10.20).
        host, _ = confiaveis.get_trusted_client_address("6.6.6.6, 200.150.10.20")
        self.assertEqual(host, "200.150.10.20")

    def test_proxy_em_rede_privada_e_confiavel_e_ip_publico_nao(self):
        confiaveis = _TrustedHosts(_valor_forwarded_allow_ips())
        for ip_de_proxy in ("10.1.2.3", "172.18.0.5", "192.168.1.10", "100.64.0.7"):
            self.assertIn(ip_de_proxy, confiaveis)
        self.assertNotIn("200.150.10.20", confiaveis)

    def test_compose_de_producao_nao_volta_a_confiar_em_todo_mundo(self):
        self.assertNotIn("forwarded-allow-ips=*", _ler("docker-compose.prod.yml"))


class TestPortaDefinidaPelaHospedagem(unittest.TestCase):

    def test_dockerfile_usa_a_porta_da_variavel_port_com_8000_de_padrao(self):
        # Railway (e outras) escolhem a porta e informam em PORT; localmente continua 8000.
        self.assertIn("${PORT:-8000}", _ler("Dockerfile"))


class TestModeloDeEmbeddingsEmbutido(unittest.TestCase):

    def test_dockerfile_baixa_o_modelo_no_build_e_roda_offline(self):
        dockerfile = _ler("Dockerfile")
        self.assertIn("paraphrase-multilingual-MiniLM-L12-v2", dockerfile)
        self.assertIn("HF_HUB_OFFLINE=1", dockerfile)


class TestFrontendEscutaEmTodasAsInterfaces(unittest.TestCase):

    def test_frontend_dockerfile_fixa_hostname_0_0_0_0_no_estagio_final(self):
        # O servidor standalone do Next escuta no endereço de HOSTNAME. Dentro do Docker, HOSTNAME
        # é o ID do contêiner, então o proxy da hospedagem não alcança o processo (502 "Application
        # failed to respond" no Railway). Fixar no estágio final deixa a config no repositório.
        dockerfile = _ler("frontend/Dockerfile")
        estagio_final = dockerfile.split("AS runner", 1)[1]
        self.assertRegex(estagio_final, r'(?m)^ENV HOSTNAME="?0\.0\.0\.0"?\s*$')


if __name__ == "__main__":
    unittest.main()
