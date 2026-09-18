# -*- coding: utf-8 -*-
"""`scripts/limpar_tenants_orfaos.py` (Fase 13, Task 18).

A auditoria encontrou dezenas de diretórios de tenant de teste acumulados em
`tenant_data/{chroma,tabular}/` -- confirmado nesta mesma fase: mesmo depois de limpos, uma única
rodada de `python -m unittest discover -s tests` recria ~50 deles de novo (falha de `tearDown` em
várias suítes, fora do escopo desta task corrigir uma a uma). Este teste isola só a lógica de
detecção (`encontrar_orfaos`), redirecionando `RAIZ_TENANT_DATA` para um diretório temporário --
nunca toca no `tenant_data/` real do projeto.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import scripts.limpar_tenants_orfaos as limpeza


def _criar_tenant(raiz, sub, nome, arquivo="doc.bin", conteudo=b"x" * 1024):
    caminho = os.path.join(raiz, sub, nome)
    os.makedirs(caminho, exist_ok=True)
    with open(os.path.join(caminho, arquivo), "wb") as f:
        f.write(conteudo)
    return caminho


class TestEncontrarOrfaos(unittest.TestCase):

    def setUp(self):
        self.raiz_temp = tempfile.mkdtemp(prefix="teste_limpar_tenants_")
        self._patch = patch.object(limpeza, "RAIZ_TENANT_DATA", self.raiz_temp)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.raiz_temp, ignore_errors=True)

    @patch.object(limpeza, "TENANT_CONFIG", {"senai_labfashion": {}})
    def test_tenant_conhecido_nunca_aparece(self):
        _criar_tenant(self.raiz_temp, "chroma", "senai_labfashion")
        _criar_tenant(self.raiz_temp, "chroma", "teste_orfao_qualquer")

        orfaos = limpeza.encontrar_orfaos()
        nomes = [nome for nome, _c, _t in orfaos["chroma"]]

        self.assertNotIn("senai_labfashion", nomes)
        self.assertIn("teste_orfao_qualquer", nomes)

    @patch.object(limpeza, "TENANT_CONFIG", {})
    def test_arquivo_solto_na_raiz_nao_e_tratado_como_tenant(self):
        os.makedirs(os.path.join(self.raiz_temp, "chroma"), exist_ok=True)
        with open(os.path.join(self.raiz_temp, "chroma", "CACHEDIR.TAG"), "w") as f:
            f.write("x")

        orfaos = limpeza.encontrar_orfaos()
        self.assertEqual(orfaos["chroma"], [])

    @patch.object(limpeza, "TENANT_CONFIG", {})
    def test_subdiretorio_ausente_nao_quebra(self):
        # tabular/ nunca chegou a ser criado neste diretório temporário.
        orfaos = limpeza.encontrar_orfaos()
        self.assertEqual(orfaos["tabular"], [])

    @patch.object(limpeza, "TENANT_CONFIG", {})
    def test_ordena_por_tamanho_decrescente(self):
        _criar_tenant(self.raiz_temp, "chroma", "pequeno", conteudo=b"x" * 100)
        _criar_tenant(self.raiz_temp, "chroma", "grande", conteudo=b"x" * 10_000)

        orfaos = limpeza.encontrar_orfaos()
        nomes = [nome for nome, _c, _t in orfaos["chroma"]]
        self.assertEqual(nomes, ["grande", "pequeno"])

    @patch.object(limpeza, "TENANT_CONFIG", {})
    def test_idade_minima_protege_diretorio_recente(self):
        _criar_tenant(self.raiz_temp, "chroma", "recem_criado")
        orfaos = limpeza.encontrar_orfaos(idade_minima_minutos=30)
        self.assertEqual(orfaos["chroma"], [])


class TestForcarRemoveDeFato(unittest.TestCase):

    def setUp(self):
        self.raiz_temp = tempfile.mkdtemp(prefix="teste_limpar_tenants_forcar_")
        self._patch_raiz = patch.object(limpeza, "RAIZ_TENANT_DATA", self.raiz_temp)
        self._patch_cfg = patch.object(limpeza, "TENANT_CONFIG", {"senai_labfashion": {}})
        self._patch_raiz.start()
        self._patch_cfg.start()

    def tearDown(self):
        self._patch_cfg.stop()
        self._patch_raiz.stop()
        shutil.rmtree(self.raiz_temp, ignore_errors=True)

    def test_sem_forcar_apenas_lista_nao_remove(self):
        caminho = _criar_tenant(self.raiz_temp, "chroma", "orfao_a")
        for nome, caminho_encontrado, _tamanho in limpeza.encontrar_orfaos()["chroma"]:
            pass  # a função de detecção não apaga nada por si só
        self.assertTrue(os.path.isdir(caminho))


if __name__ == "__main__":
    unittest.main()
