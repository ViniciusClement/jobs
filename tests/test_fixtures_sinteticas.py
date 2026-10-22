"""Exercita as fixtures sintéticas de tests/fixtures/ (seção 7 do protocolo:
uma vaga sintética curta por padrão de limpeza/parsing/skills)."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from radar import parser  # noqa: E402
import run as run_mod  # noqa: E402
from tests.test_parser import CONFIG  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
HOJE = date(2026, 10, 22)


def _ler(nome: str) -> str:
    return (FIXTURES_DIR / nome).read_text(encoding="utf-8")


def _montar(nome: str) -> dict:
    return parser.montar_vaga(_ler(nome), HOJE, CONFIG)


def _skills(vaga: dict) -> set:
    return {s["skill"] for s in vaga["skills"]}


def _processar_blocos_em_tmp(blocos: list[str]) -> tuple[dict, list[str]]:
    dados = {"schema_version": 1, "vagas": []}
    original = run_mod.PROCESSADAS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        run_mod.PROCESSADAS_DIR = Path(tmp)
        try:
            avisos = [run_mod.processar_bloco(b, CONFIG, HOJE, dados) for b in blocos]
        finally:
            run_mod.PROCESSADAS_DIR = original
    return dados, avisos


class TestFixtureMojibakeERuido(unittest.TestCase):
    def test_limpeza_aplicada(self):
        vaga = _montar("mojibake_e_ruido.txt")
        self.assertNotIn("â€“", vaga["texto_bruto"])
        self.assertNotIn("Posted 30+ Days Ago", vaga["texto_bruto"])
        self.assertNotIn("Apply Now", vaga["texto_bruto"])
        skills = _skills(vaga)
        self.assertIn("Python", skills)
        self.assertIn("Nmap", skills)
        self.assertEqual(vaga["modalidade"], "remoto")


class TestFixtureCabecalhosPtEn(unittest.TestCase):
    def test_secoes_detectadas(self):
        texto = _ler("cabecalhos_pt_en.txt")
        secoes = parser.detectar_secoes(texto, CONFIG["secoes"])
        self.assertIn("Realizar testes de intrusão", "\n".join(secoes["responsabilidades"]))
        self.assertIn("Perform red team engagements", "\n".join(secoes["responsabilidades"]))
        self.assertIn("OSCP certification required", "\n".join(secoes["requisitos"]))
        self.assertIn("We help companies find", "\n".join(secoes["descricao"]))


class TestFixtureFalsosPositivos(unittest.TestCase):
    def test_go_e_c_ainda_detectados_apesar_das_armadilhas(self):
        vaga = _montar("falsos_positivos_go_c.txt")
        skills = _skills(vaga)
        self.assertIn("Go", skills)
        self.assertIn("C/C++", skills)


class TestFixtureGrupoAlternativo(unittest.TestCase):
    def test_grupos_formados(self):
        vaga = _montar("grupo_alternativo.txt")
        por_skill = {s["skill"]: s for s in vaga["skills"]}
        grupos_requisitos = {por_skill[s]["grupo_alternativo"] for s in ("Python", "Go", "Bash")}
        self.assertEqual(len(grupos_requisitos), 1)
        self.assertNotIn(None, grupos_requisitos)
        grupos_diferenciais = {por_skill[s]["grupo_alternativo"] for s in ("OSCP", "OSEP", "CRTO")}
        self.assertEqual(len(grupos_diferenciais), 1)
        self.assertNotIn(None, grupos_diferenciais)


class TestFixtureRestricoesSalarioAnos(unittest.TestCase):
    def test_campos(self):
        vaga = _montar("restricoes_salario_anos.txt")
        self.assertEqual(vaga["restricoes"]["cidadania"], ["US"])
        self.assertEqual(vaga["restricoes"]["clearance"], "ts")
        self.assertEqual(vaga["salario"]["min"], 140000)
        self.assertEqual(vaga["salario"]["max"], 180000)
        self.assertEqual(vaga["anos_experiencia"]["min"], 3)
        self.assertEqual(vaga["anos_experiencia"]["max"], 10)


class TestFixtureSetorPublicoVsGovernoContratada(unittest.TestCase):
    def test_blocos(self):
        texto = _ler("setor_publico_vs_governo_contratada.txt")
        blocos = parser.dividir_arquivo(texto)
        self.assertEqual(len(blocos), 2)
        vaga_publica = parser.montar_vaga(blocos[0], HOJE, CONFIG)
        vaga_contratada = parser.montar_vaga(blocos[1], HOJE, CONFIG)
        self.assertTrue(vaga_publica["ignorada"])
        self.assertFalse(vaga_contratada["ignorada"])
        self.assertEqual(vaga_contratada["setor_cliente"], "governo_contratada")


class TestFixtureLotes(unittest.TestCase):
    def test_lote_com_separador(self):
        blocos = parser.dividir_arquivo(_ler("lote_com_separador.txt"))
        self.assertEqual(len(blocos), 3)

    def test_lote_sem_separador_usa_heuristica(self):
        blocos = run_mod._dividir_heuristico(_ler("lote_sem_separador.txt"))
        self.assertEqual(len(blocos), 2)


class TestFixtureClassificacaoSemCabecalho(unittest.TestCase):
    def test_classes(self):
        vaga = _montar("classificacao_sem_cabecalho.txt")
        por_skill = {s["skill"]: s for s in vaga["skills"]}
        self.assertEqual(por_skill["OSCP"]["classe"], "diferencial")
        self.assertEqual(por_skill["Python"]["classe"], "obrigatorio")
        self.assertEqual(por_skill["Burp Suite"]["classe"], "mencionado")


class TestFixtureVariantesTypos(unittest.TestCase):
    def test_variantes(self):
        skills = _skills(_montar("variantes_e_typos.txt"))
        for esperado in ("MITRE ATT&CK", "Checkmarx", "Spear phishing", "ffuf", "OSCP", "Pentest+"):
            self.assertIn(esperado, skills)


class TestFixtureDedup(unittest.TestCase):
    def test_dedup_exata(self):
        blocos = parser.dividir_arquivo(_ler("dedup_exata.txt"))
        dados, avisos = _processar_blocos_em_tmp(blocos)
        self.assertEqual(len(dados["vagas"]), 1)
        self.assertIn("duplicata exata descartada", avisos[1])

    def test_dedup_quase_duplicata(self):
        blocos = parser.dividir_arquivo(_ler("dedup_quase.txt"))
        dados, avisos = _processar_blocos_em_tmp(blocos)
        self.assertEqual(len(dados["vagas"]), 2)
        self.assertIn("possível duplicata de", avisos[1])


if __name__ == "__main__":
    unittest.main()
