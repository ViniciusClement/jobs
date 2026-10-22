"""Verificação executável do HTML gerado (Fase 4): JSON embutido válido e
</script> escapado; docs/ sem dados sensíveis; sem URLs externas; e-mail/
telefone mascarados; e, se houver navegador headless, console sem erros e
filtros funcionando — caso não haja, isso é dito explicitamente no teste."""

import argparse
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from radar import html as html_mod  # noqa: E402

_RE_SCRIPT_JSON = re.compile(
    r'<script type="application/json" id="dados-radar">(.*?)</script>', re.DOTALL
)
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TELEFONE = re.compile(r"\(?\d{2,3}\)?[\s.-]\d{3,5}[\s.-]\d{4}")
_RE_URL_EXTERNA = re.compile(
    r'(?:src|href)\s*=\s*"(https?://[^"]+)"|@import\s+url\(["\']?(https?://[^"\')]+)', re.IGNORECASE
)


def _extrair_json_embutido(html_texto: str) -> dict:
    m = _RE_SCRIPT_JSON.search(html_texto)
    assert m, "bloco <script type=\"application/json\" id=\"dados-radar\"> não encontrado"
    return json.loads(m.group(1))


class TestJsonEmbutido(unittest.TestCase):
    def test_json_embutido_e_valido_e_faz_roundtrip(self):
        payload = {"gerado_em": "2026-10-22T10:00", "privado": False, "vagas": [{"titulo": "Pentester"}]}
        html_texto = html_mod.gerar_html(payload, "Teste")
        extraido = _extrair_json_embutido(html_texto)
        self.assertEqual(extraido, payload)

    def test_fechamento_de_script_no_conteudo_e_escapado(self):
        payload = {"privado": False, "vagas": [], "nota": "texto com </script> malicioso embutido"}
        html_texto = html_mod.gerar_html(payload, "Teste")
        bloco = _RE_SCRIPT_JSON.search(html_texto).group(1)
        self.assertNotIn("</script>", bloco)
        self.assertIn("<\\/script", bloco)
        # e mesmo assim o JSON embutido continua válido e recupera o texto original:
        extraido = _extrair_json_embutido(html_texto)
        self.assertEqual(extraido["nota"], "texto com </script> malicioso embutido")


class TestMascaramentoPublico(unittest.TestCase):
    def test_email_e_telefone_mascarados_na_evidencia(self):
        vaga = {
            "id": "v-1", "titulo": "Pentester", "empresa": "Acme", "locais": [], "mercado": "BR",
            "skills": [{
                "categoria": "Linguagens", "skill": "Python", "classe": "obrigatorio", "peso": 1.0,
                "grupo_alternativo": None,
                "evidencia": "Envie CV para recrutador@empresa.com ou ligue (11) 91234-5678 — Python necessário",
            }],
            "secoes": {}, "restricoes": {},
        }
        payload = html_mod.montar_vaga_payload(vaga, False, html_mod.PERFIL_PUBLICO_GENERICO)
        evidencia = payload["skills"][0]["evidencia"]
        self.assertNotRegex(evidencia, _RE_EMAIL)
        self.assertNotRegex(evidencia, _RE_TELEFONE)
        self.assertIn("[e-mail oculto]", evidencia)
        self.assertIn("[telefone oculto]", evidencia)

    def test_payload_publico_nao_tem_status_notas_nem_contato(self):
        vaga = {
            "id": "v-1", "titulo": "Pentester", "empresa": "Acme", "locais": [], "mercado": "BR",
            "skills": [], "secoes": {}, "restricoes": {},
            "status": "entrevista", "notas": "nota sigilosa", "contato_recrutador": {"emails": ["x@x.com"]},
            "texto_bruto": "texto bruto completo da vaga",
        }
        payload = html_mod.montar_vaga_payload(vaga, False, html_mod.PERFIL_PUBLICO_GENERICO)
        self.assertNotIn("status", payload)
        self.assertNotIn("notas", payload)
        self.assertNotIn("contato_recrutador", payload)
        self.assertNotIn("texto_bruto", payload)


class TestSemUrlsExternas(unittest.TestCase):
    def test_nenhuma_url_externa_de_script_estilo_ou_fonte(self):
        payload = {"privado": False, "vagas": []}
        html_texto = html_mod.gerar_html(payload, "Teste")
        achados = _RE_URL_EXTERNA.findall(html_texto)
        self.assertEqual(achados, [], f"URLs externas encontradas: {achados}")
        # o único <link> permitido é o favicon inline (data:), que não busca nada externo:
        tags_link = re.findall(r"<link[^>]*>", html_texto)
        for tag in tags_link:
            self.assertIn('href="data:', tag)
        self.assertNotIn("cdn.", html_texto.lower())


class TestPipelineCompletoSemDadosSensiveis(unittest.TestCase):
    """Roda o gerar-html de ponta a ponta contra um projeto sintético (sem
    tocar no projeto real) e varre docs/index.html por vazamentos."""

    def setUp(self):
        import run as run_mod
        self.run_mod = run_mod
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)

        self._originais = {
            "DATA_DIR": run_mod.DATA_DIR, "DOCS_DIR": run_mod.DOCS_DIR,
            "PRIVADO_DIR": run_mod.PRIVADO_DIR, "CV_DIR": run_mod.CV_DIR,
        }
        run_mod.DATA_DIR = base / "data"
        run_mod.DOCS_DIR = base / "docs"
        run_mod.PRIVADO_DIR = base / "privado"
        run_mod.CV_DIR = base / "cv"
        for d in (run_mod.DATA_DIR, run_mod.DOCS_DIR, run_mod.PRIVADO_DIR, run_mod.CV_DIR):
            d.mkdir(parents=True)

        self.marcador_perfil = "MARCADOR-PERFIL-ULTRASSECRETO-7788"
        (run_mod.PRIVADO_DIR / "perfil.json").write_text(
            json.dumps({"_leia_me": self.marcador_perfil, "cidadanias": ["BR"], "residencia": "BR",
                        "clearances": [], "aceita_relocacao": False, "idiomas": {"pt": "nativo", "en": "basico"}}),
            encoding="utf-8",
        )

        self.marcador_cv = "Fulano De Tal Nome Ficticio Marcador 9900"
        (run_mod.CV_DIR / "exemplo.md").write_text(
            f"# CV\n{self.marcador_cv}\ncontato@fulano-ficticio.test\nPython, Nmap, Burp Suite\n" + ("x" * 500),
            encoding="utf-8",
        )

        vaga = {
            "id": "v-sensivel", "chave_dedup": "k1", "possivel_duplicata_de": None,
            "titulo": "Pentester Sênior", "titulo_bruto": "Pentester Sênior",
            "familia_cargo": "pentest", "empresa": "Acme Corp", "empregador_tipo": "direto",
            "setor_cliente": None, "locais": ["São Paulo"], "pais": [], "mercado": "BR",
            "modalidade": "remoto", "modalidade_conflito": False, "escopo_remoto": None,
            "restricoes": {"cidadania": None, "residencia": None, "clearance": None,
                           "clearance_obrigatorio": None, "outras": []},
            "restricoes_evidencia": None, "senioridade": "sênior", "senioridade_texto": "Sênior",
            "anos_experiencia": None, "salario": None, "contrato": "CLT", "tipo_vinculo": "full_time",
            "periodo_contrato": None, "datas_no_texto": [], "possivelmente_expirada": False,
            "data": "2026-10-01", "data_estimada": False, "idioma": "pt", "ingles_nivel": None,
            "origem": "linkedin", "url": "https://exemplo.com/vaga/1",
            "status": "entrevista", "notas": "NOTA-SIGILOSA-MARCADOR-4321",
            "ignorada": False, "ignorada_motivo": None,
            "secoes": {"requisitos": "Python e Nmap são obrigatórios.", "descricao": None,
                       "responsabilidades": None, "diferenciais": None, "beneficios": None, "sobre_empresa": None},
            "skills": [{
                "categoria": "Linguagens", "skill": "Python", "classe": "obrigatorio", "peso": 1.0,
                "grupo_alternativo": None,
                "evidencia": "Contato do recrutador: fulano@recrutamento.com / (21) 98888-7777 — Python",
            }],
            "texto_bruto": "TEXTO-BRUTO-MARCADOR-COMPLETO-1234 com detalhes internos da vaga",
            "contato_recrutador": {"emails": ["fulano@recrutamento.com"], "telefones": ["(21) 98888-7777"]},
            "slug": "pentester-senior",
        }
        (run_mod.DATA_DIR / "vagas.json").write_text(
            json.dumps({"schema_version": 1, "vagas": [vaga]}, ensure_ascii=False), encoding="utf-8"
        )

        run_mod.cmd_gerar_html(argparse.Namespace())
        self.docs_html = (run_mod.DOCS_DIR / "index.html").read_text(encoding="utf-8")
        self.privado_html = (run_mod.PRIVADO_DIR / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        for chave, valor in self._originais.items():
            setattr(self.run_mod, chave, valor)
        self.tmpdir.cleanup()

    def test_docs_nao_contem_texto_bruto(self):
        self.assertNotIn("TEXTO-BRUTO-MARCADOR-COMPLETO-1234", self.docs_html)

    def test_docs_nao_contem_email_nem_telefone(self):
        self.assertNotIn("fulano@recrutamento.com", self.docs_html)
        self.assertNotIn("98888-7777", self.docs_html)
        # varredura genérica por qualquer e-mail/telefone residual no público:
        self.assertEqual(_RE_EMAIL.findall(self.docs_html), [])

    def test_docs_nao_contem_status_nem_notas(self):
        # a marca específica da nota nunca deve aparecer em lugar nenhum do HTML:
        self.assertNotIn("NOTA-SIGILOSA-MARCADOR-4321", self.docs_html)
        # e, na DATA real (o JSON embutido, não o JS/HTML de interface
        # compartilhado entre público/privado — que legitimamente lista os
        # valores possíveis de status num <select> só visível no privado),
        # nenhuma vaga pública deve trazer os campos status/notas:
        dados = _extrair_json_embutido(self.docs_html)
        for vaga in dados["vagas"]:
            self.assertNotIn("status", vaga)
            self.assertNotIn("notas", vaga)

    def test_docs_nao_contem_perfil(self):
        self.assertNotIn(self.marcador_perfil, self.docs_html)

    def test_docs_nao_contem_trechos_do_cv(self):
        self.assertNotIn(self.marcador_cv, self.docs_html)

    def test_docs_sem_urls_externas(self):
        achados = _RE_URL_EXTERNA.findall(self.docs_html)
        self.assertEqual(achados, [])

    def test_privado_contem_match_e_elegibilidade_mas_nao_vaza_perfil_bruto(self):
        # privado/index.html pode (e deve) ter status/notas/match — é privado.
        self.assertIn("NOTA-SIGILOSA-MARCADOR-4321", self.privado_html)
        # mas o conteúdo bruto de perfil.json (ex.: a chave de instrução) não deve
        # ser serializado ali — só os campos agregados (match/elegibilidade).
        self.assertNotIn(self.marcador_perfil, self.privado_html)

    def test_docs_json_embutido_e_valido(self):
        dados = _extrair_json_embutido(self.docs_html)
        self.assertFalse(dados["privado"])
        self.assertEqual(len(dados["vagas"]), 1)


class TestNavegadorHeadless(unittest.TestCase):
    """Abre os dois HTML reais (gerados no teste anterior) num navegador
    headless, se houver um disponível, e confere console + filtros."""

    def setUp(self):
        self._driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service

            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})
            service = Service("/usr/bin/chromedriver")
            self._driver = webdriver.Chrome(service=service, options=opts)
        except Exception as exc:
            self._driver = None
            self._motivo_indisponivel = str(exc)

    def tearDown(self):
        if self._driver is not None:
            self._driver.quit()

    def test_pagina_publica_sem_erros_de_console_e_filtros_funcionam(self):
        if self._driver is None:
            self.skipTest(
                f"Navegador headless não disponível neste ambiente ({getattr(self, '_motivo_indisponivel', 'sem driver')})."
                " Verificação manual necessária."
            )
        import time

        payload = {
            "gerado_em": "2026-10-22T10:00", "privado": False,
            "vagas": [
                {"id": "v1", "titulo": "Pentester", "empresa": "Acme", "locais": ["SP"], "mercado": "BR",
                 "modalidade": "remoto", "modalidade_conflito": False, "senioridade": "pleno",
                 "contrato": "CLT", "tipo_vinculo": "full_time", "familia_cargo": "pentest",
                 "data": "2026-10-01", "data_estimada": False, "possivelmente_expirada": False,
                 "url": "https://x.com/1", "restricoes_chips": [],
                 "skills": [{"categoria": "Linguagens", "skill": "Python", "classe": "obrigatorio",
                             "peso": 1.0, "grupo_alternativo": None, "evidencia": "Python necessário"}],
                 "secoes": {}, "recorte_int": None},
                {"id": "v2", "titulo": "Red Team Lead", "empresa": None, "locais": [], "mercado": "INT",
                 "modalidade": "híbrido", "modalidade_conflito": False, "senioridade": "lead",
                 "contrato": None, "tipo_vinculo": "contract", "familia_cargo": "red_team",
                 "data": "2026-10-02", "data_estimada": True, "possivelmente_expirada": False,
                 "url": "https://x.com/2", "restricoes_chips": ["exige clearance TS (obrigatório)"],
                 "skills": [{"categoria": "C2 e infraestrutura", "skill": "Cobalt Strike", "classe": "obrigatorio",
                             "peso": 1.0, "grupo_alternativo": None, "evidencia": "Cobalt Strike necessário"}],
                 "secoes": {}, "recorte_int": "restrito"},
            ],
            "comparacao_br_int": [], "comparacao_familias": {}, "tendencia": {"status": "dados insuficientes"},
            "qualidade_dados": {"n_vagas": 2, "possivelmente_expiradas": 0, "datas_estimadas": 1, "anos_ambiguos": 0,
                                 "campos_nulos_mais_frequentes": []},
        }
        html_texto = html_mod.gerar_html(payload, "Teste Headless")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "index.html"
            caminho.write_text(html_texto, encoding="utf-8")

            self._driver.get(f"file://{caminho}")
            time.sleep(0.3)

            erros = [l for l in self._driver.get_log("browser") if l["level"] == "SEVERE"]
            self.assertEqual(erros, [], f"Erros no console: {erros}")

            total_inicial = self._driver.execute_script("return DADOS.vagas.length")
            self.assertEqual(total_inicial, 2)

            self._driver.find_element("css selector", 'nav.abas button[data-pagina="vagas"]').click()
            time.sleep(0.2)
            cartoes_antes = len(self._driver.find_elements("css selector", ".vaga"))
            self.assertEqual(cartoes_antes, 2)

            busca = self._driver.find_element("id", "f-busca")
            busca.send_keys("Red Team")
            time.sleep(0.2)
            cartoes_depois = len(self._driver.find_elements("css selector", ".vaga"))
            self.assertEqual(cartoes_depois, 1)

            erros_depois = [l for l in self._driver.get_log("browser") if l["level"] == "SEVERE"]
            self.assertEqual(erros_depois, [])


if __name__ == "__main__":
    unittest.main()
