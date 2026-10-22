import unittest

from radar import limpeza


class TestMojibake(unittest.TestCase):
    def test_corrige_aspas_mojibake(self):
        texto = "Voceâ€™s a great fit"
        corrigido = limpeza.corrigir_mojibake(texto)
        self.assertIn("’", corrigido)

    def test_texto_normal_nao_e_alterado(self):
        texto = "Texto já em utf-8 normal, sem mojibake."
        self.assertEqual(limpeza.corrigir_mojibake(texto), texto)


class TestEntidadesHtml(unittest.TestCase):
    def test_remove_nbsp_e_entidades(self):
        texto = "Requisitos:&nbsp;Python &amp; Bash"
        resultado = limpeza.remover_entidades_html(texto)
        self.assertNotIn("&nbsp;", resultado)
        self.assertIn("&", resultado)
        self.assertNotIn("&amp;", resultado)


class TestGlifosLista(unittest.TestCase):
    def test_normaliza_bullets_diversos(self):
        texto = "• Python\n◇ Go\n▪ Bash\n› Rust"
        resultado = limpeza.normalizar_glifos_lista(texto)
        for linha in resultado.split("\n"):
            self.assertTrue(linha.startswith("- "))


class TestLinksMarkdown(unittest.TestCase):
    def test_preserva_texto_e_url(self):
        texto = "Veja [nosso site](https://exemplo.com/vagas) para mais detalhes."
        resultado = limpeza.extrair_links_markdown(texto)
        self.assertIn("nosso site", resultado)
        self.assertIn("https://exemplo.com/vagas", resultado)
        self.assertNotIn("[nosso site]", resultado)


class TestHashtagsAts(unittest.TestCase):
    def test_remove_hashtag_e_gera_pista_remoto(self):
        texto = "Vaga para pentester #LI-Remote"
        resultado, pistas = limpeza.remover_hashtags_ats(texto)
        self.assertNotIn("#LI-Remote", resultado)
        self.assertIn("remoto", pistas)


class TestRuido(unittest.TestCase):
    def test_remove_linhas_de_ruido(self):
        config = {
            "linhas_exatas": ["apply now", "full job description"],
            "regex": [r"^posted\s+\d+\+?\s*days?\s+ago$"],
        }
        texto = "Full job description\nPenetration Tester\nPosted 30+ Days Ago\nApply Now\nPython required"
        resultado = limpeza.remover_ruido(texto, config)
        self.assertNotIn("Full job description", resultado)
        self.assertNotIn("Posted 30+ Days Ago", resultado)
        self.assertNotIn("Apply Now", resultado)
        self.assertIn("Python required", resultado)


class TestPalavrasColadas(unittest.TestCase):
    def test_separa_palavras_coladas(self):
        texto = "Realizamos assessmentsSocial de engenharia"
        resultado = limpeza.separar_palavras_coladas(texto)
        self.assertIn("assessments Social", resultado)

    def test_nao_separa_camelcase_legitimo(self):
        texto = "Experiência com PowerShell, BloodHound e GitHub Actions"
        resultado = limpeza.separar_palavras_coladas(texto)
        self.assertIn("PowerShell", resultado)
        self.assertIn("BloodHound", resultado)
        self.assertIn("GitHub", resultado)
        self.assertNotIn("Power Shell", resultado)
        self.assertNotIn("Blood Hound", resultado)


class TestNormalizarUrl(unittest.TestCase):
    def test_remove_parametros_de_rastreio(self):
        url = "https://exemplo.com/vaga/123?utm_source=linkedin&utm_medium=social&ref=home"
        resultado = limpeza.normalizar_url(url)
        self.assertNotIn("utm_source", resultado)
        self.assertNotIn("utm_medium", resultado)

    def test_indeed_mantem_so_jk(self):
        url = "https://www.indeed.com/viewjob?jk=abc123def456&tk=xyz&from=serp"
        resultado = limpeza.normalizar_url(url)
        self.assertIn("jk=abc123def456", resultado)
        self.assertNotIn("tk=", resultado)
        self.assertNotIn("from=", resultado)

    def test_url_vazia(self):
        self.assertIsNone(limpeza.normalizar_url(None))


if __name__ == "__main__":
    unittest.main()
