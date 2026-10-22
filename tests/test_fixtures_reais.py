"""Testes com anúncios reais (não sintéticos). A pasta tests/fixtures_reais/ é
ignorada pelo git — cada teste é PULADO individualmente se o arquivo esperado
não existir. Coloque os .txt reais (um por vaga) com o nome indicado em cada
classe para habilitar o respectivo teste."""

import unittest
from datetime import date
from pathlib import Path

from radar import parser
from tests.test_parser import CONFIG

FIXTURES_REAIS_DIR = Path(__file__).resolve().parent / "fixtures_reais"
HOJE = date(2026, 10, 22)


def _achar(padrao: str):
    if not FIXTURES_REAIS_DIR.exists():
        return None
    candidatos = sorted(FIXTURES_REAIS_DIR.glob(padrao))
    return candidatos[0] if candidatos else None


def _montar(caminho: Path):
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    return parser.montar_vaga(texto, HOJE, CONFIG)


def _skills(vaga):
    return {s["skill"] for s in vaga["skills"]}


class _BaseFixtureReal(unittest.TestCase):
    padrao_arquivo = ""

    def setUp(self):
        self.caminho = _achar(self.padrao_arquivo)
        if not self.caminho:
            self.skipTest(
                f"tests/fixtures_reais/{self.padrao_arquivo} não encontrado — pulando (pasta vazia/sem o arquivo)."
            )
        self.vaga = _montar(self.caminho)


class TestRiachuelo(_BaseFixtureReal):
    padrao_arquivo = "*riachuelo*"

    def test_campos(self):
        self.assertEqual(self.vaga["idioma"], "pt")
        self.assertEqual(self.vaga["modalidade"], "remoto")
        self.assertEqual(self.vaga["mercado"], "BR")
        skills = _skills(self.vaga)
        for s in ("Python", "PowerShell", "Go", "Bash"):
            self.assertIn(s, skills)
        for s in ("OSCP", "OSEP", "CRTO", "CRTE", "OSEE", "GXPN"):
            self.assertIn(s, skills)


class TestLSEG(_BaseFixtureReal):
    padrao_arquivo = "*lseg*"

    def test_campos(self):
        self.assertTrue(self.vaga["data_estimada"])
        self.assertTrue(any("R0122063" in (l or "") for l in [self.vaga.get("titulo_bruto") or "", self.vaga["texto_bruto"]]))


class TestOscarAssociates(_BaseFixtureReal):
    padrao_arquivo = "*oscar*"

    def test_campos(self):
        self.assertIsNone(self.vaga["empresa"])
        self.assertEqual(self.vaga["empregador_tipo"], "agencia")
        self.assertIn("C/C++", _skills(self.vaga))


class TestDotWave(_BaseFixtureReal):
    padrao_arquivo = "*dotwave*"

    def test_campos(self):
        self.assertEqual(self.vaga["restricoes"]["clearance"], "ts")
        self.assertTrue(self.vaga["restricoes"]["clearance_obrigatorio"])
        self.assertTrue(self.vaga["possivelmente_expirada"])
        self.assertEqual(self.vaga["anos_experiencia"]["min"], 10)


class TestKratos(_BaseFixtureReal):
    padrao_arquivo = "*kratos*"

    def test_campos(self):
        self.assertEqual(self.vaga["salario"]["moeda"], "USD")
        self.assertEqual(self.vaga["salario"]["min"], 90000)
        self.assertEqual(self.vaga["salario"]["max"], 120000)
        self.assertIn("OSCP", _skills(self.vaga))


class TestConsultoriaNY(_BaseFixtureReal):
    padrao_arquivo = "*consultoria*ny*"

    def test_campos(self):
        self.assertIsNone(self.vaga["empresa"])
        self.assertTrue(self.vaga["modalidade_conflito"])
        self.assertIsNone(self.vaga["senioridade"])


class TestTestPros(_BaseFixtureReal):
    padrao_arquivo = "*testpros*"

    def test_campos(self):
        self.assertEqual(self.vaga["restricoes"]["cidadania"], ["US"])
        self.assertEqual(self.vaga["restricoes"]["clearance"], "public_trust")
        self.assertEqual(self.vaga["setor_cliente"], "governo_contratada")
        self.assertNotIn("Computer Forensics", _skills(self.vaga))


class TestConverge(_BaseFixtureReal):
    padrao_arquivo = "*converge*"

    def test_campos(self):
        skills = _skills(self.vaga)
        self.assertIn("OSCP", skills)
        self.assertIn("OSWE", skills)
        self.assertIn("MITRE ATT&CK", skills)
        self.assertIn("OSSTMM", skills)


class TestZync(_BaseFixtureReal):
    padrao_arquivo = "*zync*"

    def test_campos(self):
        self.assertEqual(self.vaga["titulo"], "Penetration Tester")
        self.assertEqual(self.vaga["modalidade"], "híbrido")
        self.assertEqual(self.vaga["salario"]["max"], 150000)
        self.assertIsNone(self.vaga["salario"]["min"])
        self.assertIn("CREST", _skills(self.vaga))


if __name__ == "__main__":
    unittest.main()
