# -*- coding: utf-8 -*-
"""Testes de fichas_desenho.py (Fases 11, Tasks 15-16).

`gerar_imagem_desenho`/`gerar_nova_versao` são sempre exercitados com client mockado
(`MagicMock`) -- nenhum destes testes faz uma chamada real de API. Usa um tenant/ficha fictícios
e limpa o diretório da ficha no tearDown.
"""

import base64
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

import fichas_modelo as fm
import fichas_desenho as fdz
import fichas_repo as fr

TENANT_TESTE = "teste_task15_desenho"
FICHA_TESTE = "88888888-8888-8888-8888-888888888888"

PNG_MINIMO = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _resposta_com_imagem(conteudo: bytes = PNG_MINIMO):
    item = MagicMock(b64_json=base64.b64encode(conteudo).decode("ascii"))
    return MagicMock(data=[item])


class TestFichaDesenhoBase(unittest.TestCase):
    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        diretorio = fr._dir_ficha(TENANT_TESTE, FICHA_TESTE)
        if os.path.isdir(diretorio):
            shutil.rmtree(diretorio, ignore_errors=True)


class TestGerarImagemDesenho(TestFichaDesenhoBase):

    def test_sucesso_devolve_bytes_crus(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()

        resultado = fdz.gerar_imagem_desenho(client, "camisa branca, desenho tecnico", TENANT_TESTE)

        self.assertEqual(resultado, PNG_MINIMO)
        self.assertIsInstance(resultado, bytes)

    def test_nao_devolve_data_uri(self):
        # A diferença central em relação a geracao_imagem.chamar_api_geracao_imagem(): esta função
        # nunca deve devolver a string "data:image/png;base64,...".
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        resultado = fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertNotIsInstance(resultado, str)

    def test_usa_o_modelo_gpt_image_1(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertEqual(client.images.generate.call_args.kwargs["model"], "gpt-image-1")

    def test_tamanho_padrao_e_retrato(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertEqual(client.images.generate.call_args.kwargs["size"], "1024x1536")

    def test_tamanho_customizado_e_repassado(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE, tamanho="1024x1024")
        self.assertEqual(client.images.generate.call_args.kwargs["size"], "1024x1024")

    def test_falha_na_api_devolve_none(self):
        client = MagicMock()
        client.images.generate.side_effect = RuntimeError("falha de rede")
        resultado = fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        self.assertIsNone(resultado)

    def test_falha_na_api_nao_propaga_excecao(self):
        client = MagicMock()
        client.images.generate.side_effect = Exception("qualquer erro")
        try:
            fdz.gerar_imagem_desenho(client, "prompt qualquer", TENANT_TESTE)
        except Exception:
            self.fail("gerar_imagem_desenho não deveria propagar exceção da API")


class TestPersistencia(TestFichaDesenhoBase):

    def test_salvar_e_recuperar(self):
        caminho = fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 1, PNG_MINIMO)
        self.assertTrue(os.path.exists(caminho))
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), PNG_MINIMO)

    def test_nome_do_arquivo_inclui_a_versao(self):
        caminho = fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 3, PNG_MINIMO)
        self.assertTrue(caminho.endswith("desenho_v3.png"))

    def test_versoes_diferentes_nao_se_sobrescrevem(self):
        # É o que permite comparar v_n com v_{n-1} na revisão (Task 17) -- gerar uma versão nova
        # não pode apagar a anterior.
        fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 1, PNG_MINIMO)
        conteudo_v2 = PNG_MINIMO + b"\x00extra"
        fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 2, conteudo_v2)

        self.assertIsNotNone(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1))
        with open(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1), "rb") as f:
            self.assertEqual(f.read(), PNG_MINIMO)
        with open(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 2), "rb") as f:
            self.assertEqual(f.read(), conteudo_v2)

    def test_caminho_inexistente_devolve_none(self):
        self.assertIsNone(fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, 1))

    def test_versao_invalida_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fdz.salvar_desenho(TENANT_TESTE, FICHA_TESTE, 0, PNG_MINIMO)
        with self.assertRaises(ValueError):
            fdz.caminho_desenho(TENANT_TESTE, FICHA_TESTE, -1)

    def test_ficha_id_malformado_levanta_value_error(self):
        # caminho_arquivo_da_ficha (fichas_repo) já valida o formato do ficha_id -- confirma que
        # a validação continua acontecendo passando por este módulo.
        with self.assertRaises(ValueError):
            fdz.salvar_desenho(TENANT_TESTE, "../../etc/passwd", 1, PNG_MINIMO)


def _campo(valor):
    return {"valor": valor, "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}


def _ficha_com_dados() -> dict:
    ficha = fm.ficha_vazia()
    ficha["id"] = FICHA_TESTE
    d = ficha["dados"]
    d["ficha"]["nome"] = _campo("Camisa Social Branca")
    d["ficha"]["descricao"] = _campo("Manga longa, gola italiana")
    cor = fm.cor_beneficiamento_vazia()
    cor["cor"] = _campo("Branco")
    d["cores_beneficiamentos"] = [cor]
    tecido = fm.tecido_vazio()
    tecido["descricao"] = _campo("Tricoline")
    d["tecidos"] = [tecido]
    return ficha


class TestMontarPromptVisual(unittest.TestCase):
    """Puro, sem chamada nenhuma -- só monta o texto a partir dos dados já verificados da ficha."""

    def test_ficha_vazia_produz_prompt_vazio(self):
        self.assertEqual(fdz.montar_prompt_visual(fm.dados_vazios()), "")

    def test_inclui_apenas_campos_preenchidos(self):
        dados = fm.dados_vazios()
        dados["ficha"]["nome"] = _campo("Camisa Social Branca")
        prompt = fdz.montar_prompt_visual(dados)
        self.assertIn("Camisa Social Branca", prompt)
        self.assertNotIn("DESCRIÇÃO:", prompt)  # descricao não foi preenchida

    def test_inclui_cores_e_tecidos_quando_presentes(self):
        prompt = fdz.montar_prompt_visual(_ficha_com_dados()["dados"])
        self.assertIn("Branco", prompt)
        self.assertIn("Tricoline", prompt)

    def test_nao_inventa_detalhe_nao_mencionado(self):
        # Regra central do produto: bolso/zíper/botão só aparecem se a ficha já os menciona.
        prompt = fdz.montar_prompt_visual(_ficha_com_dados()["dados"])
        for termo_proibido in ("bolso", "zíper", "botão", "pocket", "zipper", "button"):
            self.assertNotIn(termo_proibido, prompt.lower())


class TestAcumularInstrucao(unittest.TestCase):

    def test_sem_instrucao_mantem_o_anterior(self):
        self.assertEqual(fdz.acumular_instrucao("ajuste anterior", ""), "ajuste anterior")

    def test_primeira_instrucao_sem_historico(self):
        self.assertEqual(fdz.acumular_instrucao("", "manga 3/4"), "manga 3/4")

    def test_concatena_com_o_historico(self):
        resultado = fdz.acumular_instrucao("manga 3/4", "gola mais alta")
        self.assertIn("manga 3/4", resultado)
        self.assertIn("gola mais alta", resultado)


class TestGerarNovaVersao(unittest.TestCase):

    def _client_ok(self):
        client = MagicMock()
        client.images.generate.return_value = _resposta_com_imagem()
        return client

    def setUp(self):
        self._limpar()

    def tearDown(self):
        self._limpar()

    def _limpar(self):
        diretorio = fr._dir_ficha(TENANT_TESTE, FICHA_TESTE)
        if os.path.isdir(diretorio):
            shutil.rmtree(diretorio, ignore_errors=True)

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_primeira_versao_e_numero_1(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        self.assertEqual(len(ficha["desenho"]["versoes"]), 1)
        self.assertEqual(ficha["desenho"]["versoes"][0]["versao"], 1)

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_versao_nasce_aguardando_aprovacao(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        self.assertEqual(ficha["desenho"]["versoes"][0]["status"], fm.DESENHO_AGUARDANDO_APROVACAO)
        self.assertTrue(ficha["desenho"]["solicitado"])

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_arquivo_e_salvo_em_disco(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        self.assertIsNotNone(fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 1))

    @patch("fichas_desenho.incrementar_uso")
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_incrementa_a_cota_de_imagens(self, _mod, mock_incrementar):
        fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        mock_incrementar.assert_called_once_with(TENANT_TESTE, "imagens")

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": False, "motivo": "Fora do escopo de moda."})
    def test_prompt_reprovado_nao_chama_a_api_de_imagem(self, _mod):
        client = self._client_ok()
        with self.assertRaises(fdz.PromptReprovadoError) as ctx:
            fdz.gerar_nova_versao(client, TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        self.assertEqual(ctx.exception.motivo, "Fora do escopo de moda.")
        client.images.generate.assert_not_called()

    @patch("fichas_desenho.verificar_limite", return_value=False)
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_limite_excedido_nao_chama_a_api_de_imagem(self, _mod, _limite):
        client = self._client_ok()
        with self.assertRaises(fdz.LimiteDeImagensExcedidoError):
            fdz.gerar_nova_versao(client, TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        client.images.generate.assert_not_called()

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_falha_na_geracao_nao_incrementa_cota(self, _mod):
        client = MagicMock()
        client.images.generate.side_effect = RuntimeError("falha de rede")
        with patch("fichas_desenho.incrementar_uso") as mock_incrementar:
            with self.assertRaises(RuntimeError):
                fdz.gerar_nova_versao(client, TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
            mock_incrementar.assert_not_called()

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_segunda_versao_acumula_instrucao(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        ficha = fdz.gerar_nova_versao(
            self._client_ok(), TENANT_TESTE, ficha, limite_imagens_dia=30, instrucao_adicional="manga 3/4, não curta"
        )
        self.assertEqual(len(ficha["desenho"]["versoes"]), 2)
        v2 = ficha["desenho"]["versoes"][1]
        self.assertEqual(v2["versao"], 2)
        self.assertIn("manga 3/4, não curta", v2["instrucoes_acumuladas"])
        self.assertIn("manga 3/4, não curta", v2["prompt_visual"])

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_terceira_versao_acumula_as_duas_instrucoes_anteriores(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        ficha = fdz.gerar_nova_versao(
            self._client_ok(), TENANT_TESTE, ficha, limite_imagens_dia=30, instrucao_adicional="manga 3/4"
        )
        ficha = fdz.gerar_nova_versao(
            self._client_ok(), TENANT_TESTE, ficha, limite_imagens_dia=30, instrucao_adicional="gola mais alta"
        )
        v3 = ficha["desenho"]["versoes"][2]
        self.assertIn("manga 3/4", v3["instrucoes_acumuladas"])
        self.assertIn("gola mais alta", v3["instrucoes_acumuladas"])

    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_versoes_anteriores_nao_sao_substituidas(self, _mod):
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, _ficha_com_dados(), limite_imagens_dia=30)
        ficha = fdz.gerar_nova_versao(self._client_ok(), TENANT_TESTE, ficha, limite_imagens_dia=30)
        self.assertIsNotNone(fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 1))
        self.assertIsNotNone(fdz.caminho_desenho(TENANT_TESTE, ficha["id"], 2))


class TestAprovarVersao(unittest.TestCase):

    def _ficha_com_versoes(self, quantas=2) -> dict:
        ficha = _ficha_com_dados()
        ficha["desenho"]["versoes"] = [
            {"versao": i, "prompt_visual": "x", "instrucoes_acumuladas": "", "status": fm.DESENHO_AGUARDANDO_APROVACAO, "criado_em": ""}
            for i in range(1, quantas + 1)
        ]
        return ficha

    def test_aprova_a_versao_pedida(self):
        ficha = fdz.aprovar_versao(self._ficha_com_versoes(), 2)
        self.assertEqual(ficha["desenho"]["versao_aprovada"], 2)
        self.assertEqual(ficha["desenho"]["versoes"][1]["status"], fm.DESENHO_APROVADO)

    def test_nao_muda_outras_versoes_nao_aprovadas(self):
        ficha = fdz.aprovar_versao(self._ficha_com_versoes(), 2)
        self.assertEqual(ficha["desenho"]["versoes"][0]["status"], fm.DESENHO_AGUARDANDO_APROVACAO)

    def test_aprovar_outra_versao_rebaixa_a_anterior(self):
        # Só uma pode valer por vez -- versao_aprovada é um único número.
        ficha = fdz.aprovar_versao(self._ficha_com_versoes(), 1)
        ficha = fdz.aprovar_versao(ficha, 2)
        self.assertEqual(ficha["desenho"]["versao_aprovada"], 2)
        self.assertEqual(ficha["desenho"]["versoes"][0]["status"], fm.DESENHO_AGUARDANDO_APROVACAO)
        self.assertEqual(ficha["desenho"]["versoes"][1]["status"], fm.DESENHO_APROVADO)

    def test_versao_inexistente_levanta_value_error(self):
        with self.assertRaises(ValueError):
            fdz.aprovar_versao(self._ficha_com_versoes(), 99)


if __name__ == "__main__":
    unittest.main()
