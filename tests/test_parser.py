import json
import unittest
from datetime import date
from pathlib import Path

from radar import parser
from radar import skills as skills_mod

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _carregar_config():
    with open(DATA_DIR / "ruido.json", encoding="utf-8") as f:
        ruido = json.load(f)
    with open(DATA_DIR / "secoes.json", encoding="utf-8") as f:
        secoes = json.load(f)
    with open(DATA_DIR / "filtros.json", encoding="utf-8") as f:
        filtros = json.load(f)
    with open(DATA_DIR / "familias.json", encoding="utf-8") as f:
        familias = json.load(f)
    with open(DATA_DIR / "skills.json", encoding="utf-8") as f:
        skills_cfg = json.load(f)
    return {
        "ruido": ruido,
        "secoes": secoes,
        "filtros": filtros,
        "familias": familias,
        "skills_regras": skills_mod.compilar_regras(skills_cfg),
    }


CONFIG = _carregar_config()
HOJE = date(2026, 10, 22)


def montar(texto):
    return parser.montar_vaga(texto, HOJE, CONFIG)


class TestCabecalho(unittest.TestCase):
    def test_parse_cabecalho_completo(self):
        bloco = (
            "Empresa: Acme Corp | Local: Remoto | URL: https://x.com/1 | "
            "Data: 2026-10-01 | Origem: linkedin | Mercado: BR | Status: interessado\n"
            "---\n"
            "Penetration Tester\nPython required"
        )
        campos, corpo = parser.parse_cabecalho(bloco)
        self.assertEqual(campos["empresa"], "Acme Corp")
        self.assertEqual(campos["data"], "2026-10-01")
        self.assertEqual(campos["mercado"], "BR")
        self.assertTrue(corpo.startswith("Penetration Tester"))

    def test_sem_cabecalho(self):
        bloco = "Penetration Tester\nPython required"
        campos, corpo = parser.parse_cabecalho(bloco)
        self.assertEqual(campos, {})
        self.assertEqual(corpo, bloco)


class TestDivisaoLote(unittest.TestCase):
    def test_divide_por_separador(self):
        texto = "Vaga 1\nPython\n=== VAGA ===\nVaga 2\nGo\n=== VAGA ===\nVaga 3\nRust"
        blocos = parser.dividir_arquivo(texto)
        self.assertEqual(len(blocos), 3)
        self.assertTrue(blocos[0].startswith("Vaga 1"))
        self.assertTrue(blocos[2].startswith("Vaga 3"))

    def test_sem_separador_retorna_bloco_unico(self):
        texto = "Vaga única\nPython"
        blocos = parser.dividir_arquivo(texto)
        self.assertEqual(len(blocos), 1)


class TestSecoesCabecalho(unittest.TestCase):
    def test_cabecalhos_em_frase_pt(self):
        corpo = (
            "Pentester\n"
            "Os desafios da função são:\n"
            "Realizar testes de intrusão\n"
            "É muito importante que você tenha e/ou saiba:\n"
            "Python\n"
            "E quais são os benefícios?\n"
            "Vale refeição\n"
        )
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        self.assertIn("Realizar testes de intrusão", "\n".join(secoes["responsabilidades"]))
        self.assertIn("Python", "\n".join(secoes["requisitos"]))
        self.assertIn("Vale refeição", "\n".join(secoes["beneficios"]))

    def test_cabecalhos_en(self):
        corpo = (
            "Penetration Tester\n"
            "Key Responsibilities\n"
            "Perform penetration tests\n"
            "Required Skills & Experience\n"
            "Python\n"
            "Position Description\n"
            "We test things\n"
        )
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        self.assertIn("Perform penetration tests", "\n".join(secoes["responsabilidades"]))
        self.assertIn("Python", "\n".join(secoes["requisitos"]))
        self.assertIn("We test things", "\n".join(secoes["descricao"]))

    def test_prioridade_do_cabecalho_sobre_pista_de_linha(self):
        """'required' aparece na linha, mas a seção é Diferenciais -> classe diferencial."""
        corpo = (
            "Pentester\n"
            "Skills/Experience Preferred (not all required)\n"
            "OSCP required for this role\n"
        )
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        regras = CONFIG["skills_regras"]
        encontrados = skills_mod.detectar_skills(secoes, regras)
        oscp = next(s for s in encontrados if s["skill"] == "OSCP")
        self.assertEqual(oscp["classe"], "diferencial")

    def test_sem_cabecalho_classifica_linha_a_linha(self):
        corpo = (
            "Pentester\n"
            "OSCP is a plus for this position\n"
            "Python is required for this role\n"
            "We use Burp Suite daily\n"
        )
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        regras = CONFIG["skills_regras"]
        encontrados = {s["skill"]: s for s in skills_mod.detectar_skills(secoes, regras)}
        self.assertEqual(encontrados["OSCP"]["classe"], "diferencial")
        self.assertEqual(encontrados["Python"]["classe"], "obrigatorio")
        self.assertEqual(encontrados["Burp Suite"]["classe"], "mencionado")


class TestFalsosPositivosEVariantes(unittest.TestCase):
    def _skills_do_texto(self, texto):
        secoes = parser.detectar_secoes(texto, CONFIG["secoes"])
        return {s["skill"] for s in skills_mod.detectar_skills(secoes, CONFIG["skills_regras"])}

    def test_go_falsos_positivos(self):
        self.assertNotIn("Go", self._skills_do_texto("Go to market strategy for the team"))
        self.assertNotIn("Go", self._skills_do_texto("Be a go-getter and join us"))
        self.assertNotIn("Go", self._skills_do_texto("let's go, apply today"))
        self.assertNotIn("Go", self._skills_do_texto("We run a Go Phish exercise"))

    def test_go_verdadeiros_positivos(self):
        self.assertIn("Go", self._skills_do_texto("Experience with Golang is a plus"))
        self.assertIn("Go", self._skills_do_texto("Go (linguagem) usada no backend"))
        self.assertIn("Go", self._skills_do_texto("Temos experiência em Go e Python"))
        self.assertIn("Go", self._skills_do_texto("Python, PowerShell, Go, Bash"))

    def test_c_falsos_positivos(self):
        self.assertNotIn("C/C++", self._skills_do_texto("Reporting to the C-level executives"))
        self.assertNotIn("C/C++", self._skills_do_texto("Rich in Vitamina C"))
        self.assertNotIn("C/C++", self._skills_do_texto("Meetings with the C suite"))

    def test_c_verdadeiros_positivos(self):
        self.assertIn("C/C++", self._skills_do_texto("Strong skills in C/C++"))
        self.assertIn("C/C++", self._skills_do_texto("Conhecimento em linguagem C"))
        self.assertIn("C/C++", self._skills_do_texto("Experiência em programação em C"))

    def test_computer_forensics_na_descricao_da_empresa_nao_e_skill(self):
        corpo = (
            "Pentester\n"
            "About Us\n"
            "We are a Computer Forensics and Cyber Security company.\n"
        )
        self.assertEqual(self._skills_do_texto(corpo), set())

    def test_variantes_e_typos_sao_detectados(self):
        self.assertIn("MITRE ATT&CK", self._skills_do_texto("Experience with Mittre Attack framework"))
        self.assertIn("MITRE ATT&CK", self._skills_do_texto("Uses MITRE ATT&CK for emulation"))
        self.assertIn("Checkmarx", self._skills_do_texto("Static analysis with CheckMarkx"))
        self.assertIn("Spear phishing", self._skills_do_texto("Conducts Spear Phishin campaigns"))
        self.assertIn("ffuf", self._skills_do_texto("Uses Fuff for fuzzing endpoints"))

    def test_oscp_com_asterisco(self):
        self.assertIn("OSCP", self._skills_do_texto("Certifications: OSCP* preferred"))

    def test_pentest_plus_variantes_de_caixa(self):
        self.assertIn("Pentest+", self._skills_do_texto("Holds Pentest+ certification"))
        self.assertIn("Pentest+", self._skills_do_texto("Holds PenTest+ certification"))


class TestRestricoesESalarioEAnos(unittest.TestCase):
    def test_restricao_cidadania_e_clearance(self):
        corpo = "Penetration Tester\nMust be a U.S. Citizen or Green Card holder.\nTop Secret clearance required.\n"
        restricoes, evidencia = parser.extrair_restricoes(corpo)
        self.assertEqual(restricoes["cidadania"], ["US"])
        self.assertEqual(restricoes["clearance"], "ts")
        self.assertTrue(restricoes["clearance_obrigatorio"])
        self.assertIsNotNone(evidencia)

    def test_residencia_brasil(self):
        corpo = "Pentester\nVaga para residente no Brasil.\n"
        restricoes, _ = parser.extrair_restricoes(corpo)
        self.assertEqual(restricoes["residencia"], "BR")

    def test_salario_faixa_usd(self):
        corpo = "Salary: $140,000-$180,000 per year"
        salario = parser.extrair_salario(corpo)
        self.assertEqual(salario["min"], 140000)
        self.assertEqual(salario["max"], 180000)
        self.assertEqual(salario["moeda"], "USD")
        self.assertEqual(salario["periodo"], "ano")

    def test_salario_up_to(self):
        corpo = "Up to $150k per year, depending on experience"
        salario = parser.extrair_salario(corpo)
        self.assertIsNone(salario["min"])
        self.assertEqual(salario["max"], 150000)

    def test_salario_brl(self):
        corpo = "Remuneração: R$ 8.000 a 12.000 por mês"
        salario = parser.extrair_salario(corpo)
        self.assertEqual(salario["min"], 8000)
        self.assertEqual(salario["max"], 12000)
        self.assertEqual(salario["moeda"], "BRL")
        self.assertEqual(salario["periodo"], "mes")

    def test_anos_faixa(self):
        anos = parser.extrair_anos_experiencia("Requires 3 – 10 years of experience")
        self.assertEqual(anos["min"], 3)
        self.assertEqual(anos["max"], 10)
        self.assertFalse(anos["ambiguo"])

    def test_anos_mais(self):
        anos = parser.extrair_anos_experiencia("10+ years of experience required")
        self.assertEqual(anos["min"], 10)
        self.assertIsNone(anos["max"])

    def test_anos_extenso(self):
        anos = parser.extrair_anos_experiencia("Three years of experience in security")
        self.assertEqual(anos["min"], 3)
        self.assertEqual(anos["max"], 3)

    def test_anos_ambiguo_soma(self):
        anos = parser.extrair_anos_experiencia("3 years + additional (2) years as intern")
        self.assertTrue(anos["ambiguo"])
        self.assertIsNone(anos["min"])
        self.assertIsNone(anos["max"])


class TestGrupoAlternativo(unittest.TestCase):
    def test_grupo_alternativo_na_mesma_linha(self):
        corpo = "Pentester\nRequisitos:\nOne or more of the following: Python, PowerShell, Go, Bash\n"
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        encontrados = {s["skill"]: s for s in skills_mod.detectar_skills(secoes, CONFIG["skills_regras"])}
        grupos = {encontrados[s]["grupo_alternativo"] for s in ("Python", "Go", "Bash") if s in encontrados}
        self.assertEqual(len(grupos), 1)
        self.assertNotIn(None, grupos)

    def test_sem_gatilho_nao_forma_grupo(self):
        corpo = "Pentester\nRequisitos:\nConhecimento em Python e Bash\n"
        secoes = parser.detectar_secoes(corpo, CONFIG["secoes"])
        encontrados = {s["skill"]: s for s in skills_mod.detectar_skills(secoes, CONFIG["skills_regras"])}
        self.assertIsNone(encontrados["Python"]["grupo_alternativo"])


class TestSetorPublicoEGovernoContratada(unittest.TestCase):
    def test_ignora_orgao_publico(self):
        vaga = montar("Analista de Segurança\nConcurso público para órgão público municipal.\n")
        self.assertTrue(vaga["ignorada"])
        self.assertIsNotNone(vaga["ignorada_motivo"])

    def test_empresa_privada_contratada_do_governo_nao_e_ignorada(self):
        vaga = montar(
            "Empresa: Defense Contractor LLC | Local: EUA | URL: | Data: | Origem: | Mercado: INT | Status: novo\n"
            "---\n"
            "Penetration Tester\nFederal contractor providing defense services. Clearance required.\n"
        )
        self.assertFalse(vaga["ignorada"])
        self.assertEqual(vaga["setor_cliente"], "governo_contratada")


class TestTituloEFamilia(unittest.TestCase):
    def test_titulo_limpo_remove_sufixo_de_local(self):
        titulo, titulo_bruto = parser.extrair_titulo("Penetration Tester - Remote (US)\nResto do texto")
        self.assertEqual(titulo, "Penetration Tester")
        self.assertEqual(titulo_bruto, "Penetration Tester - Remote (US)")

    def test_familia_red_team(self):
        self.assertEqual(parser.detectar_familia_cargo("Red Team Operator", CONFIG["familias"]), "red_team")

    def test_familia_pentest(self):
        self.assertEqual(parser.detectar_familia_cargo("Penetration Tester", CONFIG["familias"]), "pentest")

    def test_familia_outro(self):
        self.assertEqual(parser.detectar_familia_cargo("Analista Financeiro", CONFIG["familias"]), "outro")

    def test_rotulo_position_tem_prioridade_mesmo_apos_boilerplate(self):
        # Caso real: colado do LinkedIn, começa com "About the job" (boilerplate)
        # e o título real só aparece várias linhas depois, como "Position: X".
        corpo = (
            "About the job\n"
            "SIXGEN's mission is to deliver agile, mission-ready cybersecurity solutions.\n"
            "Position Overview\n"
            "Position: Senior Web Application Penetration Tester\n"
            "Job Type: Full-time\n"
        )
        titulo, titulo_bruto = parser.extrair_titulo(corpo, CONFIG["secoes"])
        self.assertEqual(titulo, "Senior Web Application Penetration Tester")
        self.assertEqual(titulo_bruto, "Position: Senior Web Application Penetration Tester")

    def test_pula_boilerplate_about_us_quando_sem_rotulo(self):
        corpo = "About Us\nTexto curto sobre a empresa.\n"
        titulo, titulo_bruto = parser.extrair_titulo(corpo, CONFIG["secoes"])
        self.assertNotEqual(titulo, "About Us")
        self.assertEqual(titulo, "Texto curto sobre a empresa.")

    def test_sem_rotulo_e_so_frase_longa_titulo_fica_null(self):
        # Caso real: só a caixa de descrição foi colada, sem o título em
        # lugar nenhum do texto — melhor não inventar um "título" com a
        # primeira frase longa do parágrafo.
        corpo = (
            "About Us\n\n"
            "Visa is a world leader in payments technology, facilitating transactions "
            "between consumers, merchants, financial institutions and government entities "
            "across more than 200 countries and territories, dedicated to uplifting everyone.\n"
        )
        titulo, titulo_bruto = parser.extrair_titulo(corpo, CONFIG["secoes"])
        self.assertIsNone(titulo)
        self.assertTrue(titulo_bruto.startswith("Visa is a world leader"))

    def test_sem_secoes_config_mantem_comportamento_simples(self):
        titulo, titulo_bruto = parser.extrair_titulo("About the job\nResto do texto")
        self.assertEqual(titulo, "About the job")


class TestEmpregador(unittest.TestCase):
    def test_agencia_detectada_por_frase(self):
        corpo = "Pentester\nWe are recruiting on behalf of our client, a leading fintech.\n"
        empresa, tipo = parser.detectar_empregador(corpo, "Agência XPTO")
        self.assertIsNone(empresa)
        self.assertEqual(tipo, "agencia")

    def test_direto_com_cabecalho(self):
        empresa, tipo = parser.detectar_empregador("Pentester\nJoin our team.\n", "Acme Corp")
        self.assertEqual(empresa, "Acme Corp")
        self.assertEqual(tipo, "direto")

    def test_sem_evidencia_fica_null(self):
        empresa, tipo = parser.detectar_empregador("Pentester\nJoin our team.\n", None)
        self.assertIsNone(empresa)
        self.assertIsNone(tipo)


if __name__ == "__main__":
    unittest.main()
