"""Testes do coletor com respostas JSON SINTÉTICAS (sem rede) — seção 5 da
Fase 3: cada ATS, campo ausente, resposta vazia, vaga que sumiu, filtro de
título."""

import json
import unittest
from pathlib import Path

from radar import coletor

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _ler_fixture(nome: str):
    with open(FIXTURES_DIR / nome, encoding="utf-8") as f:
        return json.load(f)


def _sem_pausa():
    pass


class TestGreenhouse(unittest.TestCase):
    def test_coleta_e_converte_campos(self):
        dados = _ler_fixture("coletor_greenhouse.json")
        vagas = coletor.coletar_greenhouse("empresaficticia", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 2)
        v1 = vagas[0]
        self.assertEqual(v1["titulo"], "Penetration Tester")
        self.assertEqual(v1["url"], "https://boards.greenhouse.io/empresaficticia/jobs/1001")
        self.assertEqual(v1["local"], "São Paulo, BR")
        self.assertEqual(v1["data"], "2026-10-05")
        self.assertEqual(v1["departamento"], "Security")
        self.assertIn("Python", v1["descricao_html"])

    def test_campo_ausente_nao_quebra(self):
        dados = {"jobs": [{"id": 1, "title": "Pentester"}]}
        vagas = coletor.coletar_greenhouse("x", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 1)
        self.assertIsNone(vagas[0]["local"])
        self.assertIsNone(vagas[0]["data"])

    def test_resposta_vazia(self):
        vagas = coletor.coletar_greenhouse("x", buscar_json=lambda url: {"jobs": []})
        self.assertEqual(vagas, [])

    def test_resposta_sem_chave_jobs(self):
        vagas = coletor.coletar_greenhouse("x", buscar_json=lambda url: {})
        self.assertEqual(vagas, [])


class TestLever(unittest.TestCase):
    def test_coleta_e_converte_campos(self):
        dados = _ler_fixture("coletor_lever.json")
        vagas = coletor.coletar_lever("empresaficticia", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 2)
        v1 = vagas[0]
        self.assertEqual(v1["titulo"], "Red Team Operator")
        self.assertEqual(v1["local"], "Remote - Brazil")
        self.assertEqual(v1["departamento"], "Security")
        self.assertEqual(v1["modalidade"], "remoto")
        self.assertEqual(v1["salario"], {"min": 120000, "max": 160000, "moeda": "USD", "periodo": "ano"})
        self.assertIn("Cobalt Strike", v1["descricao_html"])

    def test_campo_ausente_nao_quebra(self):
        dados = [{"id": "x", "text": "Pentester"}]
        vagas = coletor.coletar_lever("x", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 1)
        self.assertIsNone(vagas[0]["salario"])
        self.assertIsNone(vagas[0]["modalidade"])

    def test_resposta_vazia(self):
        vagas = coletor.coletar_lever("x", buscar_json=lambda url: [])
        self.assertEqual(vagas, [])

    def test_resposta_formato_inesperado(self):
        vagas = coletor.coletar_lever("x", buscar_json=lambda url: {"erro": "não é uma lista"})
        self.assertEqual(vagas, [])


class TestAshby(unittest.TestCase):
    def test_coleta_e_converte_campos(self):
        dados = _ler_fixture("coletor_ashby.json")
        vagas = coletor.coletar_ashby("empresaficticia", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 2)
        v1 = vagas[0]
        self.assertEqual(v1["titulo"], "Application Security Engineer")
        self.assertEqual(v1["modalidade"], "remoto")
        self.assertEqual(v1["departamento"], "Engineering")
        self.assertIn("SAST", v1["descricao_html"])

    def test_campo_ausente_nao_quebra(self):
        dados = {"jobs": [{"id": "a", "title": "Pentester"}]}
        vagas = coletor.coletar_ashby("x", buscar_json=lambda url: dados)
        self.assertEqual(len(vagas), 1)
        self.assertIsNone(vagas[0]["modalidade"])
        self.assertIsNone(vagas[0]["local"])

    def test_resposta_vazia(self):
        vagas = coletor.coletar_ashby("x", buscar_json=lambda url: {"jobs": []})
        self.assertEqual(vagas, [])


class TestSmartRecruiters(unittest.TestCase):
    def _buscar_json_fake(self, url: str):
        if url.endswith("/sr-001"):
            return _ler_fixture("coletor_smartrecruiters_detalhe_sr-001.json")
        if url.endswith("/sr-002"):
            return _ler_fixture("coletor_smartrecruiters_detalhe_sr-002.json")
        return _ler_fixture("coletor_smartrecruiters_lista.json")

    def test_coleta_lista_mais_detalhe(self):
        vagas = coletor.coletar_smartrecruiters(
            "empresaficticia", buscar_json=self._buscar_json_fake, pausar=_sem_pausa
        )
        self.assertEqual(len(vagas), 2)
        v1 = next(v for v in vagas if v["id_externo"] == "sr-001")
        self.assertEqual(v1["titulo"], "Security Researcher")
        self.assertEqual(v1["modalidade"], "remoto")
        self.assertEqual(v1["departamento"], "Security")
        self.assertIn("Metasploit", v1["descricao_html"])
        self.assertEqual(v1["url"], "https://careers.smartrecruiters.com/empresaficticia/security-researcher")
        self.assertEqual(v1["empresa"], "Empresa Fictícia")

    def test_resposta_vazia(self):
        vagas = coletor.coletar_smartrecruiters(
            "x", buscar_json=lambda url: {"content": []}, pausar=_sem_pausa
        )
        self.assertEqual(vagas, [])

    def test_erro_no_detalhe_de_uma_vaga_nao_derruba_as_outras(self):
        def buscar(url):
            if url.endswith("/sr-001"):
                raise RuntimeError("HTTP 500")
            if url.endswith("/sr-002"):
                return _ler_fixture("coletor_smartrecruiters_detalhe_sr-002.json")
            return _ler_fixture("coletor_smartrecruiters_lista.json")

        vagas = coletor.coletar_smartrecruiters("x", buscar_json=buscar, pausar=_sem_pausa)
        self.assertEqual(len(vagas), 1)
        self.assertEqual(vagas[0]["id_externo"], "sr-002")


class TestFiltroTitulo(unittest.TestCase):
    FILTROS = {"titulo_inclui": ["pentest", "security"], "titulo_exclui": ["vendas", "sales"]}

    def test_inclui_quando_bate_termo(self):
        self.assertTrue(coletor.passa_filtro_titulo("Senior Security Engineer", self.FILTROS))

    def test_exclui_quando_bate_termo_de_exclusao_mesmo_com_inclusao(self):
        self.assertFalse(coletor.passa_filtro_titulo("Security Sales Manager", self.FILTROS))

    def test_exclui_quando_nao_bate_nenhum_termo_de_inclusao(self):
        self.assertFalse(coletor.passa_filtro_titulo("Office Manager", self.FILTROS))

    def test_titulo_ausente_nao_passa(self):
        self.assertFalse(coletor.passa_filtro_titulo(None, self.FILTROS))

    def test_sem_filtro_inclui_aceita_tudo_exceto_exclusoes(self):
        self.assertTrue(coletor.passa_filtro_titulo("Qualquer Coisa", {"titulo_exclui": ["vendas"]}))


class TestHtmlParaTexto(unittest.TestCase):
    def test_preserva_listas_como_marcadores(self):
        html = "<p>Intro</p><ul><li>Python</li><li>Nmap</li></ul>"
        texto = coletor.html_para_texto(html)
        self.assertIn("Intro", texto)
        self.assertIn("- Python", texto)
        self.assertIn("- Nmap", texto)

    def test_html_vazio(self):
        self.assertEqual(coletor.html_para_texto(""), "")
        self.assertEqual(coletor.html_para_texto(None), "")


class TestFormatarSalario(unittest.TestCase):
    def test_usd_faixa(self):
        texto = coletor.formatar_salario_para_texto({"min": 100000, "max": 150000, "moeda": "USD", "periodo": "ano"})
        self.assertEqual(texto, "Salary: $100,000-$150,000 per year")

    def test_brl_faixa(self):
        texto = coletor.formatar_salario_para_texto({"min": 8000, "max": 12000, "moeda": "BRL", "periodo": "mes"})
        self.assertEqual(texto, "Salário: R$ 8.000 a 12.000 por mês")

    def test_nenhum_valor(self):
        self.assertIsNone(coletor.formatar_salario_para_texto({"min": None, "max": None, "moeda": "USD"}))
        self.assertIsNone(coletor.formatar_salario_para_texto(None))


class TestMontarTextoVaga(unittest.TestCase):
    def test_cabecalho_e_corpo(self):
        vaga = {
            "titulo": "Pentester", "url": "https://x.com/1", "local": "Remoto",
            "data": "2026-10-01", "modalidade": "remoto", "departamento": "Security",
            "salario": None, "descricao_html": "<p>Teste</p>", "empresa": None,
        }
        texto = coletor.montar_texto_vaga(vaga, "greenhouse", "BR", "Empresa Padrão")
        cabecalho, corpo = texto.split("\n---\n", 1)
        self.assertIn("Empresa: Empresa Padrão", cabecalho)
        self.assertIn("Origem: greenhouse", cabecalho)
        self.assertIn("Mercado: BR", cabecalho)
        self.assertTrue(corpo.startswith("Pentester"))
        self.assertIn("Modalidade: remoto", corpo)
        self.assertIn("Teste", corpo)


if __name__ == "__main__":
    unittest.main()
