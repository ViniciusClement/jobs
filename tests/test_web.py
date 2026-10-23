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

    # ------------------------------------------------------------------
    # Edição completa de vaga, pipeline e perfil profissional
    # ------------------------------------------------------------------

    def _vaga_completa(self):
        return {
            "id": "v-1", "chave_dedup": "k1", "titulo": "Pentester", "empresa": "ACME", "locais": ["Remoto"],
            "status": "novo", "notas": "nota antiga", "ignorada": False, "familia_cargo": "pentest",
            "salario": None, "anos_experiencia": None,
            "restricoes": {"cidadania": None, "residencia": None, "clearance": None,
                           "clearance_obrigatorio": None, "outras": []},
            "skills": [
                {"categoria": "Linguagens", "skill": "Python", "classe": "mencionado", "peso": 0.6,
                 "grupo_alternativo": None, "evidencia": "Python"},
                {"categoria": "Linguagens", "skill": "Go", "classe": "diferencial", "peso": 0.4,
                 "grupo_alternativo": None, "evidencia": "Go"},
            ],
        }

    def test_pagina_editar_vaga_mostra_todos_os_campos(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [self._vaga_completa()]})
        corpo = self.client.get("/privado/vaga/v-1/editar").data.decode("utf-8")
        for nome in ("familia_cargo", "salario_min", "anos_min", "restricao_cidadania",
                     "skill-0-classe", "nova-0-skill", 'name="status"', 'name="notas"'):
            self.assertIn(nome, corpo)

    def test_editar_vaga_salva_campos_extras_skills_e_status(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [self._vaga_completa()]})
        resposta = self.client.post("/privado/vaga/v-1/editar", data={
            "titulo": "Pentester Sênior", "empresa": "ACME", "locais": "Remoto, Brasil",
            "modalidade": "remoto", "senioridade": "sênior", "contrato": "CLT", "tipo_vinculo": "full_time",
            "mercado": "INT", "familia_cargo": "red_team", "url": "",
            "salario_min": "120000", "salario_max": "150.000", "salario_moeda": "USD", "salario_periodo": "ano",
            "anos_min": "5", "anos_max": "",
            "restricao_cidadania": "us, ca", "restricao_residencia": "", "restricao_clearance": "secret",
            "restricao_clearance_obrigatorio": "on",
            "skill-0-classe": "obrigatorio", "skill-1-classe": "diferencial", "skill-1-remover": "on",
            "nova-0-skill": "kerberos", "nova-0-categoria": "", "nova-0-classe": "mencionado",
            "status": "aplicado", "notas": "nova nota",
        })
        self.assertEqual(resposta.status_code, 302)
        v = run_mod.obter_vaga("v-1")
        self.assertEqual(v["titulo"], "Pentester Sênior")
        self.assertEqual(v["locais"], ["Remoto", "Brasil"])
        self.assertEqual(v["familia_cargo"], "red_team")
        self.assertEqual(v["salario"]["min"], 120000)
        self.assertEqual(v["salario"]["max"], 150000)
        self.assertEqual(v["salario"]["moeda"], "USD")
        self.assertEqual(v["anos_experiencia"]["min"], 5)
        self.assertEqual(v["restricoes"]["cidadania"], ["US", "CA"])
        self.assertTrue(v["restricoes"]["clearance_obrigatorio"])
        self.assertEqual(v["status"], "aplicado")
        self.assertEqual(v["notas"], "nova nota")
        nomes = {s["skill"]: s for s in v["skills"]}
        self.assertNotIn("Go", nomes)
        self.assertEqual(nomes["Python"]["classe"], "obrigatorio")
        self.assertEqual(nomes["Python"]["peso"], 1.0)
        # nome normalizado para o canônico da taxonomia, categoria inferida dela:
        self.assertIn("Kerberos", nomes)
        self.assertEqual(nomes["Kerberos"]["categoria"], "Active Directory")

    def test_editar_vaga_rejeita_valores_fora_das_listas(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [self._vaga_completa()]})
        self.client.post("/privado/vaga/v-1/editar", data={
            "titulo": "X", "modalidade": "<script>", "mercado": "XX", "status": "hackeado",
            "skill-0-classe": "inventada",
        })
        v = run_mod.obter_vaga("v-1")
        self.assertIsNone(v["modalidade"])
        self.assertIsNone(v["mercado"])
        self.assertEqual(v["status"], "novo")
        self.assertEqual(v["skills"][0]["classe"], "mencionado")

    def test_pagina_editar_vaga_escapa_titulo_malicioso(self):
        vaga = self._vaga_completa()
        vaga["titulo"] = '"><script>alert(1)</script>'
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [vaga]})
        corpo = self.client.get("/privado/vaga/v-1/editar").data.decode("utf-8")
        self.assertNotIn("<script>alert(1)</script>", corpo)

    def test_mover_status_pelo_pipeline_preserva_notas(self):
        run_mod.salvar_vagas({"schema_version": 1, "vagas": [self._vaga_completa()]})
        resposta = self.client.post("/privado/vaga/v-1/status", data={"status": "entrevista"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("#pipeline", resposta.headers["Location"])
        v = run_mod.obter_vaga("v-1")
        self.assertEqual(v["status"], "entrevista")
        self.assertEqual(v["notas"], "nota antiga")
        self.client.post("/privado/vaga/v-1/status", data={"status": "invalido"})
        self.assertEqual(run_mod.obter_vaga("v-1")["status"], "entrevista")

    def test_painel_privado_tem_aba_pipeline_e_publico_nao(self):
        self.assertIn(b'id="aba-pipeline"', self.client.get("/privado").data)
        self.assertNotIn(b'id="aba-pipeline"', self.client.get("/").data)

    def test_editar_perfil_profissional(self):
        run_mod.salvar_perfil_profissional({"nome": "Fulano", "experiencias": [
            {"cargo": "Analista", "empresa": "A", "inicio": "2020", "fim": "2022", "duracao": "2 anos",
             "localizacao": None, "descricao": None},
            {"cargo": "Estagiário", "empresa": "B", "inicio": "2019", "fim": "2020", "duracao": None,
             "localizacao": None, "descricao": None},
        ]})
        corpo = self.client.get("/perfil-profissional/editar").data.decode("utf-8")
        self.assertIn('name="exp-0-cargo"', corpo)
        resposta = self.client.post("/perfil-profissional/editar", data={
            "nome": "Fulano de Tal", "headline": "Pentester", "localizacao": "SP", "resumo": "Resumo.",
            "exp-0-cargo": "Analista Sr", "exp-0-empresa": "A", "exp-0-inicio": "2020", "exp-0-fim": "2022",
            "exp-1-cargo": "Estagiário", "exp-1-remover": "on",
            "exp-2-cargo": "Pentester", "exp-2-empresa": "C", "exp-2-inicio": "2023",
            "edu-0-detalhe": "Ciência da Computação", "edu-0-periodo": "2015 – 2019",
            "certificacoes": "OSCP\neJPT\nOSCP", "skills_linkedin": "Burp Suite, Python\nNmap",
            "idiomas": "Inglês — Avançado\nPortuguês",
        })
        self.assertEqual(resposta.status_code, 302)
        p = run_mod.obter_perfil_profissional()
        self.assertEqual(p["nome"], "Fulano de Tal")
        self.assertEqual([e["cargo"] for e in p["experiencias"]], ["Analista Sr", "Pentester"])
        self.assertEqual(p["experiencias"][0]["duracao"], "2 anos")  # campo não editável preservado
        self.assertEqual(p["certificacoes"], ["OSCP", "eJPT"])
        self.assertEqual(p["skills_linkedin"], ["Burp Suite", "Python", "Nmap"])
        self.assertEqual(p["idiomas"][0], {"idioma": "Inglês", "nivel": "Avançado"})
        self.assertEqual(p["idiomas"][1], {"idioma": "Português", "nivel": None})
        self.assertEqual(self.client.get("/perfil-profissional?salvo=1").status_code, 200)

    def test_perfil_profissional_com_valor_malicioso_nao_gera_xss(self):
        self.client.post("/perfil-profissional/editar", data={
            "nome": '"><script>alert(1)</script>', "resumo": "<img src=x onerror=alert(1)>",
        })
        for rota in ("/perfil-profissional", "/perfil-profissional/editar"):
            corpo = self.client.get(rota).data.decode("utf-8")
            self.assertNotIn("<script>alert(1)</script>", corpo)
            self.assertNotIn("<img src=x", corpo)


if __name__ == "__main__":
    unittest.main()
