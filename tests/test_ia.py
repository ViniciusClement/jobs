"""Testes de radar.ia com backend SIMULADO (mock), sem rede — item 1 da
Fase 5: a IA é opcional, desligada por padrão, e o prompt nunca deve levar
texto bruto de vaga, contato de recrutador, nem e-mail/telefone do CV."""

import json
import os
import unittest
from unittest import mock

from radar import ia


class TestMontarPrompt(unittest.TestCase):
    def test_mascara_email_e_telefone_do_cv(self):
        cv = "Nome: Fulano\nE-mail: fulano@exemplo.com\nTelefone: (11) 91234-5678\nPython, Nmap"
        prompt = ia.montar_prompt(cv, [], [])
        self.assertNotIn("fulano@exemplo.com", prompt)
        self.assertNotIn("91234-5678", prompt)
        self.assertIn("[e-mail oculto]", prompt)
        self.assertIn("[telefone oculto]", prompt)

    def test_nao_inclui_texto_bruto_nem_contato_recrutador_da_vaga(self):
        vagas = [{
            "titulo": "Pentester", "familia_cargo": "pentest",
            "skills": [{"categoria": "Linguagens", "skill": "Python"}],
            "texto_bruto": "TEXTO-BRUTO-SECRETO-DA-VAGA-9999",
            "contato_recrutador": {"emails": ["recrutador@empresa.com"]},
        }]
        prompt = ia.montar_prompt("CV qualquer", [], vagas)
        self.assertNotIn("TEXTO-BRUTO-SECRETO-DA-VAGA-9999", prompt)
        self.assertNotIn("recrutador@empresa.com", prompt)
        self.assertIn("Pentester", prompt)
        self.assertIn("Python", prompt)

    def test_inclui_regras_obrigatorias(self):
        prompt = ia.montar_prompt("CV", [], [])
        self.assertIn("NUNCA invente experiência", prompt)
        self.assertIn("cidadania, residência ou clearance", prompt)
        self.assertIn("A desenvolver", prompt)

    def test_lacunas_aparecem_no_prompt(self):
        lacunas = [{"categoria": "Certificações ofensivas", "skill": "OSCP", "score_lacuna": 0.42}]
        prompt = ia.montar_prompt("CV", lacunas, [])
        self.assertIn("OSCP", prompt)
        self.assertIn("0.42", prompt)


class TestSelecaoDeBackend(unittest.TestCase):
    def test_sem_configuracao_levanta_erro_claro(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                ia.sugerir("CV", [], [])
            self.assertIn("IA desligada", str(ctx.exception))

    def test_backend_simulado_e_usado_sem_rede(self):
        chamadas = []

        def backend_fake(prompt):
            chamadas.append(prompt)
            return "Resumo fictício gerado pelo backend simulado."

        resultado = ia.sugerir("CV de teste", [], [], chamar_backend=backend_fake)
        self.assertEqual(resultado, "Resumo fictício gerado pelo backend simulado.")
        self.assertEqual(len(chamadas), 1)
        self.assertIn("CV de teste", chamadas[0])

    def test_claude_sem_api_key_da_erro_claro(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                ia._chamar_claude("prompt qualquer")
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_claude_sem_model_da_erro_claro_mesmo_com_api_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                ia._chamar_claude("prompt qualquer")
            self.assertIn("ANTHROPIC_MODEL", str(ctx.exception))
            self.assertIn("nunca é fixado no código", str(ctx.exception))

    def test_ollama_sem_model_da_erro_claro(self):
        with mock.patch.dict(os.environ, {"OLLAMA_URL": "http://localhost:11434"}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                ia._chamar_ollama("prompt qualquer")
            self.assertIn("OLLAMA_MODEL", str(ctx.exception))

    def test_prioriza_claude_quando_ambos_configurados(self):
        with mock.patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": "m", "OLLAMA_URL": "http://x", "OLLAMA_MODEL": "y"},
            clear=True,
        ):
            self.assertIs(ia._selecionar_backend(), ia._chamar_claude)

    def test_usa_ollama_quando_so_ele_configurado(self):
        with mock.patch.dict(os.environ, {"OLLAMA_URL": "http://localhost:11434", "OLLAMA_MODEL": "llama3"}, clear=True):
            self.assertIs(ia._selecionar_backend(), ia._chamar_ollama)


class TestChamadasHttpSimuladas(unittest.TestCase):
    """Simula a camada de rede (urlopen) para garantir que o payload enviado
    está correto, sem nenhuma requisição real."""

    def test_chamar_claude_monta_requisicao_e_parseia_resposta(self):
        resposta_fake = mock.MagicMock()
        resposta_fake.read.return_value = b'{"content": [{"type": "text", "text": "ola"}, {"type": "text", "text": " mundo"}]}'
        resposta_fake.__enter__.return_value = resposta_fake
        resposta_fake.__exit__.return_value = False

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": "modelo-x"}, clear=True):
            with mock.patch("radar.ia.urllib.request.urlopen", return_value=resposta_fake) as m_urlopen:
                resultado = ia._chamar_claude("meu prompt")
        self.assertEqual(resultado, "ola mundo")
        req_enviada = m_urlopen.call_args[0][0]
        self.assertEqual(req_enviada.get_header("X-api-key"), "k")
        corpo = json.loads(req_enviada.data.decode("utf-8"))
        self.assertEqual(corpo["model"], "modelo-x")
        self.assertEqual(corpo["messages"][0]["content"], "meu prompt")

    def test_chamar_ollama_monta_requisicao_e_parseia_resposta(self):
        resposta_fake = mock.MagicMock()
        resposta_fake.read.return_value = b'{"response": "sugestao do ollama"}'
        resposta_fake.__enter__.return_value = resposta_fake
        resposta_fake.__exit__.return_value = False

        with mock.patch.dict(os.environ, {"OLLAMA_URL": "http://localhost:11434", "OLLAMA_MODEL": "llama3"}, clear=True):
            with mock.patch("radar.ia.urllib.request.urlopen", return_value=resposta_fake):
                resultado = ia._chamar_ollama("meu prompt")
        self.assertEqual(resultado, "sugestao do ollama")


if __name__ == "__main__":
    unittest.main()
