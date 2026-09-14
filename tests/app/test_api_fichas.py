# -*- coding: utf-8 -*-
"""Testes das rotas HTTP /fichas (Fase 11, Task 6).

`api.main.extrair_dados` é sempre mockado (`unittest.mock.patch`) -- nenhum destes testes faz uma
chamada real de API, mesmo os que exercitam o caminho "criar ficha a partir de texto livre" (que,
numa chamada real, dispararia a extração estruturada da Task 3). Antes de rodar qualquer teste
contra a API de verdade, o usuário pediu para ser avisado e dar autorização explícita primeiro.

Usa um tenant fictício, injetado em tenant_config.TENANT_CONFIG só durante esta suíte (as rotas
validam `tenant_id in TENANT_CONFIG`, e o único tenant real do projeto é "senai_labfashion" --
testar contra ele misturaria dado de teste com o índice de fichas real). Limpa
tenant_data/fichas/{tenant}_* e tenant_data/{tenant}_usage.json* no tearDown.
"""

import glob
import os
import shutil
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import fichas_desenho as fdz
import fichas_modelo as fm
import fichas_pdf as fp
import fichas_repo as fr
import tenant_config
from api.main import app
from usage_tracker import incrementar_uso

TENANT_TESTE = "teste_task6_api_fichas"
ENV_API_KEY = f"{TENANT_TESTE}_OPENAI_API_KEY".upper()
UUID_INEXISTENTE = "11111111-1111-1111-1111-111111111111"


def _limpar_tenant_teste():
    for caminho in glob.glob(os.path.join(fr.DIRETORIO_FICHAS, f"{TENANT_TESTE}_*")):
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            os.remove(caminho)
    for caminho in glob.glob(os.path.join("tenant_data", f"{TENANT_TESTE}_usage.json*")):
        os.remove(caminho)


class TestApiFichasBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tenant_config.TENANT_CONFIG[TENANT_TESTE] = {"nome": "Tenant de Teste (Task 6)"}
        os.environ[ENV_API_KEY] = "sk-fake-key-de-teste"
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        tenant_config.TENANT_CONFIG.pop(TENANT_TESTE, None)
        os.environ.pop(ENV_API_KEY, None)

    def setUp(self):
        _limpar_tenant_teste()

    def tearDown(self):
        _limpar_tenant_teste()


class TestTenantInexistente(TestApiFichasBase):
    """Toda rota valida o tenant antes de qualquer outra coisa -- confirma isso pra cada uma."""

    def test_criar(self):
        r = self.client.post("/fichas", json={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_listar(self):
        r = self.client.get("/fichas", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_obter(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_atualizar(self):
        r = self.client.put(f"/fichas/{UUID_INEXISTENTE}", json={"tenant_id": "tenant_que_nao_existe", "ficha": {}})
        self.assertEqual(r.status_code, 404)

    def test_duplicar(self):
        r = self.client.post(f"/fichas/{UUID_INEXISTENTE}/duplicar", json={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_deletar(self):
        r = self.client.delete(f"/fichas/{UUID_INEXISTENTE}", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)


class TestCriarFichaSemTexto(TestApiFichasBase):

    def test_cria_em_branco(self):
        r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        corpo = r.json()
        self.assertEqual(corpo["ficha"]["status"], fm.STATUS_RASCUNHO)
        self.assertEqual(corpo["ficha"]["texto_origem"], "")

    def test_alertas_de_ficha_vazia(self):
        r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE})
        codigos = [a["codigo"] for a in r.json()["alertas"]]
        self.assertIn("campo_essencial_ausente", codigos)
        self.assertIn("grade_vazia", codigos)

    def test_nao_chama_extracao_sem_texto(self):
        with patch("api.main.extrair_dados") as mock_extrair:
            self.client.post("/fichas", json={"tenant_id": TENANT_TESTE})
            mock_extrair.assert_not_called()

    def test_aparece_na_listagem(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get("/fichas", params={"tenant_id": TENANT_TESTE})
        self.assertIn(criado["id"], [e["id"] for e in r.json()])


class TestCriarFichaComTexto(TestApiFichasBase):

    def _dados_mockados(self):
        dados = fm.dados_vazios()
        dados["ficha"]["nome"] = {"valor": "Camisa Social", "origem": fm.ORIGEM_FORNECIDO, "trecho": "camisa social"}
        return dados

    def test_chama_extracao_com_texto(self):
        with patch("api.main.extrair_dados", return_value=self._dados_mockados()) as mock_extrair:
            r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "uma camisa social"})
            self.assertEqual(r.status_code, 200)
            mock_extrair.assert_called_once()
            args = mock_extrair.call_args.args
            self.assertEqual(args[1], "uma camisa social")
            self.assertEqual(args[2], TENANT_TESTE)

    def test_ficha_criada_com_dados_extraidos_e_verificados(self):
        with patch("api.main.extrair_dados", return_value=self._dados_mockados()):
            r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "uma camisa social"})
        corpo = r.json()
        self.assertEqual(corpo["ficha"]["dados"]["ficha"]["nome"]["valor"], "Camisa Social")
        self.assertEqual(corpo["ficha"]["status"], fm.STATUS_EM_REVISAO)
        self.assertEqual(corpo["ficha"]["texto_origem"], "uma camisa social")

    def test_alerta_de_proveniencia_quando_trecho_nao_bate(self):
        dados = fm.dados_vazios()
        dados["tecidos"] = [{**fm.tecido_vazio(), "preco": {"valor": 99.0, "origem": fm.ORIGEM_FORNECIDO, "trecho": "isso não existe no texto"}}]
        with patch("api.main.extrair_dados", return_value=dados):
            r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "quero uma camisa qualquer"})
        corpo = r.json()
        codigos = [a["codigo"] for a in corpo["alertas"]]
        self.assertIn("campo_critico_zerado", codigos)
        self.assertIsNone(corpo["ficha"]["dados"]["tecidos"][0]["preco"]["valor"])

    def test_incrementa_uso_de_fichas(self):
        with patch("api.main.extrair_dados", return_value=self._dados_mockados()):
            self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "uma camisa social"})
        from usage_tracker import carregar_uso_do_dia
        self.assertEqual(carregar_uso_do_dia(TENANT_TESTE).get("fichas"), 1)

    def test_limite_diario_bloqueia_com_429(self):
        incrementar_uso(TENANT_TESTE, "fichas", quantidade=30)  # default limite_fichas_dia
        with patch("api.main.extrair_dados", return_value=self._dados_mockados()) as mock_extrair:
            r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "uma camisa qualquer"})
            self.assertEqual(r.status_code, 429)
            mock_extrair.assert_not_called()  # nao gasta a chamada de API depois de recusar por limite

    def test_sem_api_key_configurada_devolve_500(self):
        os.environ.pop(ENV_API_KEY, None)
        try:
            with patch("api.main.extrair_dados") as mock_extrair:
                r = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE, "texto_origem": "uma camisa qualquer"})
                self.assertEqual(r.status_code, 500)
                mock_extrair.assert_not_called()
        finally:
            os.environ[ENV_API_KEY] = "sk-fake-key-de-teste"


class TestObterFicha(TestApiFichasBase):

    def test_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.get("/fichas/nao-e-um-uuid", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_obtem_ficha_criada(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criado['id']}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ficha"]["id"], criado["id"])

    def test_alertas_recalculados_a_cada_leitura(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criado['id']}", params={"tenant_id": TENANT_TESTE})
        self.assertTrue(len(r.json()["alertas"]) > 0)


class TestAtualizarFicha(TestApiFichasBase):

    def test_inexistente_404(self):
        r = self.client.put(f"/fichas/{UUID_INEXISTENTE}", json={"tenant_id": TENANT_TESTE, "ficha": {}})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.put("/fichas/nao-e-um-uuid", json={"tenant_id": TENANT_TESTE, "ficha": {}})
        self.assertEqual(r.status_code, 400)

    def test_atualiza_status(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        criado["status"] = fm.STATUS_EM_REVISAO
        r = self.client.put(f"/fichas/{criado['id']}", json={"tenant_id": TENANT_TESTE, "ficha": criado})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ficha"]["status"], fm.STATUS_EM_REVISAO)

    def test_path_e_a_fonte_de_verdade_do_id(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        payload_com_id_diferente = dict(criado)
        payload_com_id_diferente["id"] = "00000000-0000-0000-0000-000000000000"
        r = self.client.put(f"/fichas/{criado['id']}", json={"tenant_id": TENANT_TESTE, "ficha": payload_com_id_diferente})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ficha"]["id"], criado["id"])

    def test_atualizado_em_esperado_correto_salva(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.put(
            f"/fichas/{criado['id']}",
            json={"tenant_id": TENANT_TESTE, "ficha": criado, "atualizado_em_esperado": criado["atualizado_em"]},
        )
        self.assertEqual(r.status_code, 200)

    def test_atualizado_em_esperado_divergente_412(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        # Simula outra sessão salvando primeiro.
        self.client.put(f"/fichas/{criado['id']}", json={"tenant_id": TENANT_TESTE, "ficha": criado})
        r = self.client.put(
            f"/fichas/{criado['id']}",
            json={"tenant_id": TENANT_TESTE, "ficha": criado, "atualizado_em_esperado": criado["atualizado_em"]},
        )
        self.assertEqual(r.status_code, 412)


class TestDuplicarFicha(TestApiFichasBase):

    def test_inexistente_404(self):
        r = self.client.post(f"/fichas/{UUID_INEXISTENTE}/duplicar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.post("/fichas/nao-e-um-uuid/duplicar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_duplica_com_id_novo(self):
        original = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.post(f"/fichas/{original['id']}/duplicar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.json()["ficha"]["id"], original["id"])
        self.assertEqual(r.json()["ficha"]["status"], fm.STATUS_RASCUNHO)


class TestBaixarDocx(TestApiFichasBase):
    """GET /fichas/{id}/docx -- gera o Word na hora e devolve para download."""

    def test_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}/docx", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.get("/fichas/nao-e-um-uuid/docx", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_tenant_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}/docx", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_devolve_um_docx(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})

        self.assertEqual(r.status_code, 200)
        self.assertIn("wordprocessingml", r.headers["content-type"])
        # Todo .docx é um zip: os dois primeiros bytes são a assinatura "PK".
        self.assertTrue(r.content.startswith(b"PK"), "o corpo não parece um arquivo .docx")

    def test_nome_do_arquivo_usa_ref_e_nome(self):
        # O uuid da ficha não diz nada na pasta de downloads; ref + nome dizem.
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        criada["dados"]["ficha"]["ref"] = {"valor": "CM-001", "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}
        criada["dados"]["ficha"]["nome"] = {"valor": "Camisa Social", "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}
        self.client.put(f"/fichas/{criada['id']}", json={"tenant_id": TENANT_TESTE, "ficha": criada})

        r = self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})
        self.assertIn("ficha_CM-001_Camisa_Social.docx", r.headers["content-disposition"])

    def test_nome_do_arquivo_sobrevive_a_acento_e_simbolo(self):
        # O nome viaja num header HTTP: acento e caractere especial ali dão comportamento
        # inconsistente entre navegadores.
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        criada["dados"]["ficha"]["nome"] = {"valor": "Camisa Ação/Verão 50%", "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}
        self.client.put(f"/fichas/{criada['id']}", json={"tenant_id": TENANT_TESTE, "ficha": criada})

        r = self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})
        disposicao = r.headers["content-disposition"]
        self.assertEqual(r.status_code, 200)
        self.assertTrue(disposicao.isascii(), f"nome de arquivo não-ASCII no header: {disposicao}")

    def test_status_vira_documento_gerado(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.assertEqual(criada["status"], fm.STATUS_RASCUNHO)

        self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})

        depois = self.client.get(f"/fichas/{criada['id']}", params={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.assertEqual(depois["status"], fm.STATUS_DOCUMENTO_GERADO)
        self.assertEqual(depois["documentos"]["docx"], "ficha.docx")
        self.assertTrue(depois["documentos"]["gerado_em"])

    def test_gera_sempre_a_versao_atual_da_ficha(self):
        # Gerar duas vezes com uma edição no meio precisa refletir a edição -- servir um arquivo
        # guardado entregaria silenciosamente um documento desatualizado.
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})

        atual = self.client.get(f"/fichas/{criada['id']}", params={"tenant_id": TENANT_TESTE}).json()["ficha"]
        atual["dados"]["ficha"]["nome"] = {"valor": "Nome Editado Depois", "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}
        self.client.put(f"/fichas/{atual['id']}", json={"tenant_id": TENANT_TESTE, "ficha": atual})

        r = self.client.get(f"/fichas/{criada['id']}/docx", params={"tenant_id": TENANT_TESTE})

        import io as _io
        from docx import Document
        doc = Document(_io.BytesIO(r.content))
        texto = "\n".join(c.text for t in doc.tables for linha in t.rows for c in linha.cells)
        self.assertIn("Nome Editado Depois", texto)


@unittest.skipUnless(fp.libreoffice_disponivel(), "LibreOffice não instalado neste ambiente")
class TestPrevisualizarFicha(TestApiFichasBase):
    """GET /fichas/{id}/preview -- PDF para exibição na tela, sem marcar a ficha como emitida."""

    def test_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}/preview", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.get("/fichas/nao-e-um-uuid/preview", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_devolve_um_pdf(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criada['id']}/preview", params={"tenant_id": TENANT_TESTE})

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF-"))

    def test_inline_em_vez_de_attachment(self):
        # "inline" faz o navegador exibir no lugar de baixar -- é o que permite embutir num
        # <iframe> em vez de disparar um download toda vez que a prévia é aberta.
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criada['id']}/preview", params={"tenant_id": TENANT_TESTE})
        self.assertIn("inline", r.headers["content-disposition"])

    def test_nao_muda_o_status_da_ficha(self):
        # A diferença central entre preview e download: olhar a prévia não é emitir o documento.
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.assertEqual(criada["status"], fm.STATUS_RASCUNHO)

        self.client.get(f"/fichas/{criada['id']}/preview", params={"tenant_id": TENANT_TESTE})

        depois = self.client.get(f"/fichas/{criada['id']}", params={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.assertEqual(depois["status"], fm.STATUS_RASCUNHO)
        self.assertEqual(depois["documentos"]["docx"], "")
        self.assertEqual(depois["documentos"]["pdf"], "")

    def test_reflete_edicao_mais_recente(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        criada["dados"]["ficha"]["nome"] = {"valor": "Nome Na Previa", "origem": fm.ORIGEM_FORNECIDO, "trecho": ""}
        self.client.put(f"/fichas/{criada['id']}", json={"tenant_id": TENANT_TESTE, "ficha": criada})

        r = self.client.get(f"/fichas/{criada['id']}/preview", params={"tenant_id": TENANT_TESTE})

        from pypdf import PdfReader
        import io as _io
        texto = "\n".join(p.extract_text() or "" for p in PdfReader(_io.BytesIO(r.content)).pages)
        self.assertIn("Nome Na Previa", texto)


def _resposta_imagem_ok():
    from unittest.mock import MagicMock
    import base64
    png = b"\x89PNG\r\n\x1a\n" + b"conteudo minimo"
    item = MagicMock(b64_json=base64.b64encode(png).decode("ascii"))
    return MagicMock(data=[item])


class TestGerarDesenhoEndpoint(TestApiFichasBase):
    """POST /fichas/{id}/desenho -- único ponto desta suíte que simula uma chamada de API real
    (sempre via patch em api.main.OpenAI, nunca a rede de verdade)."""

    def test_tenant_inexistente_404(self):
        r = self.client.post(
            f"/fichas/{UUID_INEXISTENTE}/desenho", json={"tenant_id": "tenant_que_nao_existe"}
        )
        self.assertEqual(r.status_code, 404)

    def test_ficha_inexistente_404(self):
        r = self.client.post(f"/fichas/{UUID_INEXISTENTE}/desenho", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_sem_api_key_configurada_devolve_500(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        os.environ.pop(ENV_API_KEY, None)
        try:
            r = self.client.post(f"/fichas/{criada['id']}/desenho", json={"tenant_id": TENANT_TESTE})
            self.assertEqual(r.status_code, 500)
        finally:
            os.environ[ENV_API_KEY] = "sk-fake-key-de-teste"

    @patch("api.main.OpenAI")
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_gera_com_sucesso_e_muda_status(self, _mod, mock_openai_cls):
        mock_openai_cls.return_value.images.generate.return_value = _resposta_imagem_ok()

        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.post(f"/fichas/{criada['id']}/desenho", json={"tenant_id": TENANT_TESTE})

        self.assertEqual(r.status_code, 200)
        corpo = r.json()["ficha"]
        self.assertEqual(len(corpo["desenho"]["versoes"]), 1)
        self.assertEqual(corpo["status"], fm.STATUS_DESENHO_GERADO)

    @patch("api.main.OpenAI")
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": False, "motivo": "Fora de escopo."})
    def test_prompt_reprovado_422(self, _mod, mock_openai_cls):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.post(f"/fichas/{criada['id']}/desenho", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"], "Fora de escopo.")
        mock_openai_cls.return_value.images.generate.assert_not_called()

    @patch("api.main.OpenAI")
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_limite_diario_bloqueia_com_429(self, _mod, mock_openai_cls):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        incrementar_uso(TENANT_TESTE, "imagens", quantidade=30)  # default limite_imagens_dia
        r = self.client.post(f"/fichas/{criada['id']}/desenho", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 429)
        mock_openai_cls.return_value.images.generate.assert_not_called()


class TestAprovarDesenhoEndpoint(TestApiFichasBase):

    def test_tenant_inexistente_404(self):
        r = self.client.post(
            f"/fichas/{UUID_INEXISTENTE}/desenho/1/aprovar", json={"tenant_id": "tenant_que_nao_existe"}
        )
        self.assertEqual(r.status_code, 404)

    def test_ficha_inexistente_404(self):
        r = self.client.post(f"/fichas/{UUID_INEXISTENTE}/desenho/1/aprovar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_versao_inexistente_404(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.post(f"/fichas/{criada['id']}/desenho/1/aprovar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    @patch("api.main.OpenAI")
    @patch("fichas_desenho.validar_prompt_imagem", return_value={"aprovado": True, "motivo": ""})
    def test_aprova_versao_existente(self, _mod, mock_openai_cls):
        mock_openai_cls.return_value.images.generate.return_value = _resposta_imagem_ok()
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.client.post(f"/fichas/{criada['id']}/desenho", json={"tenant_id": TENANT_TESTE})

        r = self.client.post(f"/fichas/{criada['id']}/desenho/1/aprovar", json={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        corpo = r.json()["ficha"]
        self.assertEqual(corpo["desenho"]["versao_aprovada"], 1)
        self.assertEqual(corpo["desenho"]["versoes"][0]["status"], "aprovado")


class TestObterDesenhoFicha(TestApiFichasBase):
    """GET /fichas/{id}/desenho/{versao} -- serve um PNG já salvo em disco (Task 15). Não gera
    nada novo: a geração fica para a Task 16/17."""

    def test_ficha_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}/desenho/1", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_de_ficha_malformado_400(self):
        r = self.client.get("/fichas/nao-e-um-uuid/desenho/1", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_tenant_inexistente_404(self):
        r = self.client.get(f"/fichas/{UUID_INEXISTENTE}/desenho/1", params={"tenant_id": "tenant_que_nao_existe"})
        self.assertEqual(r.status_code, 404)

    def test_versao_sem_desenho_salvo_404(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criada['id']}/desenho/1", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_versao_invalida_400(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.get(f"/fichas/{criada['id']}/desenho/0", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_desenho_salvo_e_servido_corretamente(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        png = b"\x89PNG\r\n\x1a\n" + b"conteudo de teste"
        fdz.salvar_desenho(TENANT_TESTE, criada["id"], 1, png)

        r = self.client.get(f"/fichas/{criada['id']}/desenho/1", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/png")
        self.assertEqual(r.content, png)

    def test_versoes_diferentes_servem_arquivos_diferentes(self):
        criada = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        fdz.salvar_desenho(TENANT_TESTE, criada["id"], 1, b"conteudo v1")
        fdz.salvar_desenho(TENANT_TESTE, criada["id"], 2, b"conteudo v2")

        r1 = self.client.get(f"/fichas/{criada['id']}/desenho/1", params={"tenant_id": TENANT_TESTE})
        r2 = self.client.get(f"/fichas/{criada['id']}/desenho/2", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r1.content, b"conteudo v1")
        self.assertEqual(r2.content, b"conteudo v2")


class TestDeletarFicha(TestApiFichasBase):

    def test_inexistente_404(self):
        r = self.client.delete(f"/fichas/{UUID_INEXISTENTE}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 404)

    def test_id_malformado_400(self):
        r = self.client.delete("/fichas/nao-e-um-uuid", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 400)

    def test_deleta_e_depois_404(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        r = self.client.delete(f"/fichas/{criado['id']}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r.status_code, 200)

        r2 = self.client.get(f"/fichas/{criado['id']}", params={"tenant_id": TENANT_TESTE})
        self.assertEqual(r2.status_code, 404)

    def test_removida_do_indice(self):
        criado = self.client.post("/fichas", json={"tenant_id": TENANT_TESTE}).json()["ficha"]
        self.client.delete(f"/fichas/{criado['id']}", params={"tenant_id": TENANT_TESTE})
        r = self.client.get("/fichas", params={"tenant_id": TENANT_TESTE})
        self.assertNotIn(criado["id"], [e["id"] for e in r.json()])


if __name__ == "__main__":
    unittest.main()
