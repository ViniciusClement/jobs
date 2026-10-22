import argparse
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import run as run_mod  # noqa: E402
from radar import coletor  # noqa: E402
from radar import skills as skills_mod  # noqa: E402


def _config():
    data_dir = BASE_DIR / "data"
    with open(data_dir / "ruido.json", encoding="utf-8") as f:
        ruido = json.load(f)
    with open(data_dir / "secoes.json", encoding="utf-8") as f:
        secoes = json.load(f)
    with open(data_dir / "filtros.json", encoding="utf-8") as f:
        filtros = json.load(f)
    with open(data_dir / "familias.json", encoding="utf-8") as f:
        familias = json.load(f)
    with open(data_dir / "skills.json", encoding="utf-8") as f:
        skills_cfg = json.load(f)
    return {
        "ruido": ruido,
        "secoes": secoes,
        "filtros": filtros,
        "familias": familias,
        "skills_regras": skills_mod.compilar_regras(skills_cfg),
    }


CONFIG = _config()
HOJE = date(2026, 10, 22)


class TestDedup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self._processadas_original = run_mod.PROCESSADAS_DIR
        run_mod.PROCESSADAS_DIR = Path(self.tmpdir.name)

    def tearDown(self):
        run_mod.PROCESSADAS_DIR = self._processadas_original
        self.tmpdir.cleanup()

    def test_duplicata_exata_descartada(self):
        dados = {"schema_version": 1, "vagas": []}
        bloco = (
            "Empresa: Acme | Local: SP | URL: https://x.com/vaga1 | Data: 2026-10-01 | "
            "Origem: linkedin | Mercado: BR | Status: novo\n---\nPentester\nPython required\n"
        )
        aviso1 = run_mod.processar_bloco(bloco, CONFIG, HOJE, dados)
        self.assertIn("[processada]", aviso1)
        self.assertEqual(len(dados["vagas"]), 1)

        aviso2 = run_mod.processar_bloco(bloco, CONFIG, HOJE, dados)
        self.assertIn("duplicata exata descartada", aviso2)
        self.assertEqual(len(dados["vagas"]), 1)

    def test_quase_duplicata_marcada_mas_nao_descartada(self):
        dados = {"schema_version": 1, "vagas": []}
        bloco1 = "Pentester\nTeste de intrusão em aplicações web usando Burp Suite e Nmap diariamente para o cliente.\n"
        bloco2 = "Pentester\nTeste de intrusão em aplicações web usando Burp Suite e Nmap diariamente para o cliente!\n"
        run_mod.processar_bloco(bloco1, CONFIG, HOJE, dados)
        aviso2 = run_mod.processar_bloco(bloco2, CONFIG, HOJE, dados)
        self.assertIn("possível duplicata de", aviso2)
        self.assertEqual(len(dados["vagas"]), 2)
        self.assertIsNotNone(dados["vagas"][1]["possivel_duplicata_de"])

    def test_vaga_ignorada_e_registrada_sem_passar_por_dedup(self):
        dados = {"schema_version": 1, "vagas": []}
        bloco = "Analista\nConcurso público para órgão público municipal.\n"
        aviso = run_mod.processar_bloco(bloco, CONFIG, HOJE, dados)
        self.assertIn("[ignorada]", aviso)
        self.assertEqual(len(dados["vagas"]), 1)
        self.assertTrue(dados["vagas"][0]["ignorada"])


class TestDivisaoHeuristica(unittest.TestCase):
    def test_divide_por_full_job_description_repetido(self):
        texto = "Full job description\nVaga 1 texto\nFull job description\nVaga 2 texto\n"
        blocos = run_mod._dividir_heuristico(texto)
        self.assertEqual(len(blocos), 2)
        self.assertTrue(blocos[0].startswith("Full job description\nVaga 1"))

    def test_sem_padrao_retorna_bloco_unico(self):
        texto = "Vaga única sem marcador"
        blocos = run_mod._dividir_heuristico(texto)
        self.assertEqual(len(blocos), 1)


class TestStatusEExportar(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self._data_dir_original = run_mod.DATA_DIR
        run_mod.DATA_DIR = Path(self.tmpdir.name)

    def tearDown(self):
        run_mod.DATA_DIR = self._data_dir_original
        self.tmpdir.cleanup()

    def test_status_atualiza_vaga_existente(self):
        vaga = {"id": "v-abcd1234", "status": "novo", "notas": None}
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [vaga]})
        args = argparse.Namespace(id="v-abcd1234", novo_status="interessado", nota="gostei")
        run_mod.cmd_status(args)
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "interessado")
        self.assertEqual(dados["vagas"][0]["notas"], "gostei")

    def test_status_vaga_inexistente_nao_quebra(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": []})
        args = argparse.Namespace(id="v-naoexiste", novo_status="interessado", nota=None)
        run_mod.cmd_status(args)  # não deve lançar exceção

    def test_exportar_gera_csv_sem_contato_e_texto_bruto(self):
        vaga = {
            "id": "v-1", "titulo": "Pentester", "texto_bruto": "segredo do texto",
            "contato_recrutador": {"emails": ["x@x.com"]}, "status": "novo",
        }
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [vaga]})
        run_mod.cmd_exportar(argparse.Namespace())
        conteudo = (run_mod.DATA_DIR / "vagas.csv").read_text(encoding="utf-8-sig")
        self.assertNotIn("segredo do texto", conteudo)
        self.assertNotIn("x@x.com", conteudo)
        self.assertIn("Pentester", conteudo)


class TestColetar(unittest.TestCase):
    """Orquestração de run.cmd_coletar (dedup por URL, arquivamento de vaga
    que sumiu da fonte, --dry-run, filtro de título) — sem rede: o
    coletor_fn de 'greenhouse' é substituído por uma função de teste."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self._data_dir_original = run_mod.DATA_DIR
        self._inbox_dir_original = run_mod.INBOX_DIR
        run_mod.DATA_DIR = base / "data"
        run_mod.INBOX_DIR = base / "inbox"
        run_mod.DATA_DIR.mkdir(parents=True)
        run_mod.INBOX_DIR.mkdir(parents=True)

        self._coletores_original = dict(coletor.COLETORES)
        self._vagas_fake: list[dict] = []
        coletor.COLETORES["greenhouse"] = lambda slug: list(self._vagas_fake)

        fontes = {
            "ats": [{"tipo": "greenhouse", "slug": "empresaficticia", "mercado": "BR", "empresa": "Empresa Fictícia"}],
            "filtros": {"titulo_inclui": ["pentest"], "titulo_exclui": ["vendas"]},
        }
        with open(run_mod.DATA_DIR / "fontes.json", "w", encoding="utf-8") as f:
            json.dump(fontes, f)

    def tearDown(self):
        run_mod.DATA_DIR = self._data_dir_original
        run_mod.INBOX_DIR = self._inbox_dir_original
        coletor.COLETORES.clear()
        coletor.COLETORES.update(self._coletores_original)
        self.tmpdir.cleanup()

    def _vaga(self, titulo, url, id_externo="id1"):
        return {
            "titulo": titulo, "url": url, "id_externo": id_externo,
            "descricao_html": "<p>Descrição</p>", "local": "Remoto", "data": "2026-10-01",
            "departamento": None, "modalidade": None, "salario": None, "empresa": None,
        }

    def test_filtro_de_titulo_exclui_vaga_nao_relevante(self):
        self._vagas_fake = [
            self._vaga("Pentester Pleno", "https://x.com/jobs/1"),
            self._vaga("Vendas Externo", "https://x.com/jobs/2"),
        ]
        run_mod.salvar_vagas({"schema_version": 1, "vagas": []})
        run_mod.cmd_coletar(argparse.Namespace(dry_run=False))
        arquivos = list(run_mod.INBOX_DIR.glob("*.txt"))
        self.assertEqual(len(arquivos), 1)
        self.assertIn("Pentester", arquivos[0].read_text(encoding="utf-8"))

    def test_dedup_por_url_nao_escreve_vaga_ja_existente(self):
        self._vagas_fake = [self._vaga("Pentester Pleno", "https://x.com/jobs/1")]
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "titulo": "Pentester Pleno", "url": "https://x.com/jobs/1", "origem": "greenhouse", "status": "novo"}
        ]})
        run_mod.cmd_coletar(argparse.Namespace(dry_run=False))
        self.assertEqual(list(run_mod.INBOX_DIR.glob("*.txt")), [])

    def test_vaga_que_sumiu_e_arquivada_quando_status_e_novo(self):
        self._vagas_fake = []  # nada retornado desta vez: a vaga "desapareceu" da fonte
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "titulo": "Pentester Pleno", "url": "https://x.com/empresaficticia/jobs/1",
             "origem": "greenhouse", "status": "novo", "notas": None}
        ]})
        run_mod.cmd_coletar(argparse.Namespace(dry_run=False))
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "arquivada")
        self.assertEqual(dados["vagas"][0]["notas"], "encerrada na fonte")

    def test_vaga_que_sumiu_mas_ja_em_entrevista_nao_e_sobrescrita(self):
        self._vagas_fake = []
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "titulo": "Pentester Pleno", "url": "https://x.com/empresaficticia/jobs/1",
             "origem": "greenhouse", "status": "entrevista", "notas": None}
        ]})
        run_mod.cmd_coletar(argparse.Namespace(dry_run=False))
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "entrevista")

    def test_dry_run_nao_grava_nada(self):
        self._vagas_fake = [self._vaga("Pentester Pleno", "https://x.com/jobs/1")]
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "titulo": "Pentester Antigo", "url": "https://x.com/empresaficticia/jobs/old",
             "origem": "greenhouse", "status": "novo", "notas": None}
        ]})
        run_mod.cmd_coletar(argparse.Namespace(dry_run=True))
        self.assertEqual(list(run_mod.INBOX_DIR.glob("*.txt")), [])
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "novo")  # não foi arquivada em dry-run


class TestIaOrquestracao(unittest.TestCase):
    """cmd_ia (run.py --ia) com backend simulado — sem rede."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self._originais = {
            "DATA_DIR": run_mod.DATA_DIR, "PRIVADO_DIR": run_mod.PRIVADO_DIR, "CV_DIR": run_mod.CV_DIR,
        }
        run_mod.DATA_DIR = base / "data"
        run_mod.PRIVADO_DIR = base / "privado"
        run_mod.CV_DIR = base / "cv"
        for d in (run_mod.DATA_DIR, run_mod.PRIVADO_DIR, run_mod.CV_DIR):
            d.mkdir(parents=True)
        run_mod.salvar_vagas({"schema_version": 1, "vagas": []})

    def tearDown(self):
        for chave, valor in self._originais.items():
            setattr(run_mod, chave, valor)
        self.tmpdir.cleanup()

    def test_sem_cv_nao_quebra(self):
        run_mod.cmd_ia(argparse.Namespace())
        self.assertFalse((run_mod.PRIVADO_DIR / "sugestoes-cv.md").exists())

    def test_sem_backend_configurado_nao_grava_nada(self):
        (run_mod.CV_DIR / "exemplo.md").write_text("Python, Nmap, Burp Suite. " + "x" * 500, encoding="utf-8")
        with mock.patch.dict(os.environ, {}, clear=True):
            run_mod.cmd_ia(argparse.Namespace())
        self.assertFalse((run_mod.PRIVADO_DIR / "sugestoes-cv.md").exists())

    def test_backend_simulado_gera_arquivo_com_aviso(self):
        (run_mod.CV_DIR / "exemplo.md").write_text("Python, Nmap, Burp Suite. " + "x" * 500, encoding="utf-8")
        with mock.patch("radar.ia._selecionar_backend", return_value=lambda prompt: "SUGESTAO-FALSA-DE-TESTE"):
            run_mod.cmd_ia(argparse.Namespace())
        conteudo = (run_mod.PRIVADO_DIR / "sugestoes-cv.md").read_text(encoding="utf-8")
        self.assertIn("SUGESTAO-FALSA-DE-TESTE", conteudo)
        self.assertIn("revise antes de usar", conteudo.lower())


if __name__ == "__main__":
    unittest.main()
