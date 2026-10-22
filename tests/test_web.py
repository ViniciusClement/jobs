"""Testes da app web local (Flask) via test_client — sem servidor de verdade
subindo, sem rede. Confirma as rotas de leitura (painéis) e as de escrita
(adicionar vaga, atualizar status/notas, editar perfil, ações de
coletar/analisar), todas batendo no SQLite via as mesmas funções do run.py."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import run as run_mod  # noqa: E402

try:
    from radar import web
    _FLASK_DISPONIVEL = True
except ImportError:
    _FLASK_DISPONIVEL = False

_ARQUIVOS_TAXONOMIA = ["ruido.json", "secoes.json", "filtros.json", "familias.json", "skills.json"]


@unittest.skipUnless(_FLASK_DISPONIVEL, "Flask não instalado (pip install flask) — app web é opcional.")
class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = Path(self.tmpdir.name)
        self._originais = {
            "DATA_DIR": run_mod.DATA_DIR, "PRIVADO_DIR": run_mod.PRIVADO_DIR,
            "CV_DIR": run_mod.CV_DIR, "DOCS_DIR": run_mod.DOCS_DIR,
            "INBOX_DIR": run_mod.INBOX_DIR, "RAW_DIR": run_mod.RAW_DIR,
            "PROCESSADAS_DIR": run_mod.PROCESSADAS_DIR,
        }
        run_mod.DATA_DIR = base / "data"
        run_mod.PRIVADO_DIR = base / "privado"
        run_mod.CV_DIR = base / "cv"
        run_mod.DOCS_DIR = base / "docs"
        run_mod.INBOX_DIR = base / "vagas" / "inbox"
        run_mod.RAW_DIR = base / "vagas" / "raw"
        run_mod.PROCESSADAS_DIR = base / "vagas" / "processadas"
        for d in (
            run_mod.DATA_DIR, run_mod.PRIVADO_DIR, run_mod.CV_DIR, run_mod.DOCS_DIR,
            run_mod.INBOX_DIR, run_mod.RAW_DIR, run_mod.PROCESSADAS_DIR,
        ):
            d.mkdir(parents=True)
        # carregar_config() lê de DATA_DIR — sem a taxonomia real copiada
        # aqui, nenhuma skill seria detectada nos testes que processam vaga.
        for nome in _ARQUIVOS_TAXONOMIA:
            shutil.copy(BASE_DIR / "data" / nome, run_mod.DATA_DIR / nome)

        self.app = web.criar_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        for chave, valor in self._originais.items():
            setattr(run_mod, chave, valor)
        self.tmpdir.cleanup()

    def test_painel_publico_responde_200_e_tem_json_embutido(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'id="dados-radar"', resposta.data)
        self.assertIn(b'"privado": false', resposta.data)

    def test_painel_privado_responde_200(self):
        resposta = self.client.get("/privado")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b'"privado": true', resposta.data)

    def test_adicionar_vaga_via_formulario(self):
        resposta = self.client.post(
            "/adicionar",
            data={"texto": "Pentester Pleno\nRequisitos:\nPython e Nmap obrigatorios.\n"},
        )
        self.assertEqual(resposta.status_code, 200)
        dados = run_mod.carregar_vagas()
        self.assertEqual(len(dados["vagas"]), 1)
        self.assertEqual(dados["vagas"][0]["titulo"], "Pentester Pleno")

    def test_adicionar_vaga_vazia_nao_quebra(self):
        resposta = self.client.post("/adicionar", data={"texto": ""})
        self.assertEqual(resposta.status_code, 200)
        dados = run_mod.carregar_vagas()
        self.assertEqual(len(dados["vagas"]), 0)

    def test_atualizar_status_e_notas_de_vaga_existente(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "chave_dedup": "k1", "titulo": "Pentester", "status": "novo", "notas": None, "ignorada": False}
        ]})
        resposta = self.client.post(
            "/privado/vaga/v-1/atualizar", data={"status": "interessado", "nota": "boa vaga"}
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/privado", resposta.headers["Location"])
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "interessado")
        self.assertEqual(dados["vagas"][0]["notas"], "boa vaga")

    def test_atualizar_status_invalido_e_ignorado_mas_nota_salva(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "chave_dedup": "k1", "titulo": "Pentester", "status": "novo", "notas": None, "ignorada": False}
        ]})
        self.client.post("/privado/vaga/v-1/atualizar", data={"status": "status-invalido", "nota": "ok"})
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "novo")
        self.assertEqual(dados["vagas"][0]["notas"], "ok")

    def test_pagina_perfil_get_mostra_valores_atuais(self):
        run_mod.salvar_perfil({"cidadanias": ["BR"], "residencia": "BR", "clearances": [],
                                "aceita_relocacao": False, "idiomas": {"pt": "nativo", "en": "avancado"}})
        resposta = self.client.get("/perfil")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn(b"BR", resposta.data)
        self.assertIn(b"avancado", resposta.data)

    def test_pagina_perfil_post_salva_novo_perfil(self):
        resposta = self.client.post("/perfil", data={
            "cidadanias": "BR, US", "residencia": "br", "clearances": "secret",
            "aceita_relocacao": "on", "idioma_en": "fluente", "idioma_pt": "nativo",
        })
        self.assertEqual(resposta.status_code, 200)
        perfil = run_mod.obter_perfil()
        self.assertEqual(perfil["cidadanias"], ["BR", "US"])
        self.assertEqual(perfil["residencia"], "BR")
        self.assertEqual(perfil["clearances"], ["secret"])
        self.assertTrue(perfil["aceita_relocacao"])
        self.assertEqual(perfil["idiomas"]["en"], "fluente")

    def test_acao_analisar_nao_quebra_sem_vagas(self):
        resposta = self.client.post("/acoes/analisar")
        self.assertEqual(resposta.status_code, 302)

    def test_acao_coletar_com_fontes_vazias_nao_quebra(self):
        import json
        (run_mod.DATA_DIR / "fontes.json").write_text(json.dumps({"ats": [], "filtros": {}}), encoding="utf-8")
        resposta = self.client.post("/acoes/coletar")
        self.assertEqual(resposta.status_code, 302)

    def test_post_com_origin_de_outro_site_e_bloqueado(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "chave_dedup": "k1", "titulo": "Pentester", "status": "novo", "notas": None, "ignorada": False}
        ]})
        resposta = self.client.post(
            "/privado/vaga/v-1/atualizar", data={"status": "interessado", "nota": "x"},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertEqual(resposta.status_code, 403)
        dados = run_mod.carregar_vagas()
        self.assertEqual(dados["vagas"][0]["status"], "novo")

    def test_post_com_origin_do_proprio_host_funciona(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [
            {"id": "v-1", "chave_dedup": "k1", "titulo": "Pentester", "status": "novo", "notas": None, "ignorada": False}
        ]})
        resposta = self.client.post(
            "/privado/vaga/v-1/atualizar", data={"status": "interessado", "nota": "x"},
            headers={"Origin": "http://localhost"},
            base_url="http://localhost",
        )
        self.assertEqual(resposta.status_code, 302)

    def test_acao_coletar_ja_processa_vagas_coletadas(self):
        from radar import coletor

        originais = dict(coletor.COLETORES)
        coletor.COLETORES["greenhouse"] = lambda slug: [{
            "titulo": "Pentester Pleno", "url": "https://x.com/jobs/1", "id_externo": "1",
            "descricao_html": "<p>Python e Nmap obrigatorios.</p>", "local": "Remoto", "data": "2026-10-01",
            "departamento": None, "modalidade": None, "salario": None, "empresa": None,
        }]
        try:
            import json
            fontes = {"ats": [{"tipo": "greenhouse", "slug": "empresaficticia", "mercado": "BR", "empresa": None}], "filtros": {}}
            (run_mod.DATA_DIR / "fontes.json").write_text(json.dumps(fontes), encoding="utf-8")
            resposta = self.client.post("/acoes/coletar")
            self.assertEqual(resposta.status_code, 302)
        finally:
            coletor.COLETORES.clear()
            coletor.COLETORES.update(originais)

        dados = run_mod.carregar_vagas()
        self.assertEqual(len(dados["vagas"]), 1)
        self.assertEqual(dados["vagas"][0]["titulo"], "Pentester Pleno")
        # já processada (tem skills detectadas), não só um .txt cru parado na inbox:
        self.assertTrue(any(s["skill"] == "Python" for s in dados["vagas"][0]["skills"]))
        self.assertEqual(list(run_mod.INBOX_DIR.glob("*.txt")), [])

    def test_adicionar_vaga_com_titulo_malicioso_nao_gera_xss(self):
        # Simula um "anúncio" colado com uma tag <script> no título — o aviso
        # de confirmação precisa escapar isso, não injetar HTML de volta.
        payload = "<script>alert(1)</script> Pentester\nRequisitos:\nPython obrigatorio.\n"
        resposta = self.client.post("/adicionar", data={"texto": payload})
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.data.decode("utf-8")
        self.assertNotIn("<script>alert(1)</script>", corpo)
        self.assertIn("&lt;script&gt;", corpo)

    def test_pagina_perfil_com_valor_malicioso_nao_gera_xss(self):
        # Um valor de perfil com aspas/HTML não pode escapar do atributo
        # value="..." nem injetar uma tag nova na página.
        self.client.post("/perfil", data={
            "cidadanias": '"><script>alert(1)</script>', "residencia": "BR",
            "clearances": "", "idioma_en": "basico", "idioma_pt": "nativo",
        })
        resposta = self.client.get("/perfil")
        corpo = resposta.data.decode("utf-8")
        # cidadanias é normalizado para maiúsculas antes de salvar — o que
        # importa é que o resultado esteja escapado, não a caixa exata.
        self.assertNotIn("<script>", corpo.lower())
        self.assertNotIn('"><script', corpo.lower())
        self.assertIn("&quot;&gt;&lt;script&gt;", corpo.lower())


if __name__ == "__main__":
    unittest.main()
