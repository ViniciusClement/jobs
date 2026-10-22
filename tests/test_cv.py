import tempfile
import unittest
import zipfile
from pathlib import Path

from radar import cv as cv_mod
from radar import skills as skills_mod
from tests.test_parser import CONFIG


def _gerar_pdf_minimo(texto: str) -> bytes:
    """PDF mínimo válido (xref table completa) com um Tj mostrando `texto`."""
    objs = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/MediaBox[0 0 200 200]/Contents 5 0 R>>endobj\n",
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    stream_content = f"BT /F1 12 Tf 10 100 Td ({texto}) Tj ET".encode("latin-1")
    objs.append(
        b"5 0 obj<</Length " + str(len(stream_content)).encode() + b">>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n"
    )
    header = b"%PDF-1.4\n"
    offsets = [0]
    pos = len(header)
    body = b""
    for o in objs:
        offsets.append(pos)
        body += o
        pos += len(o)
    xref_offset = len(header) + len(body)
    n = len(objs) + 1
    xref = b"xref\n0 " + str(n).encode() + b"\n0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += ("%010d 00000 n \n" % off).encode()
    trailer = (
        b"trailer\n<</Size " + str(n).encode() + b"/Root 1 0 R>>\nstartxref\n"
        + str(xref_offset).encode() + b"\n%%EOF"
    )
    return header + body + xref + trailer


def _gerar_docx_minimo(texto: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>"
    )
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", xml)
    return buffer.getvalue()


class TestEncontrarCvMaisRecente(unittest.TestCase):
    def test_ignora_readme_e_subpastas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "README.md").write_text("não é CV", encoding="utf-8")
            (base / "arquivo").mkdir()
            (base / "arquivo" / "cv-antigo.txt").write_text("CV antigo" * 200, encoding="utf-8")
            (base / "cv-atual.txt").write_text("CV atual" * 200, encoding="utf-8")
            encontrado = cv_mod.encontrar_cv_mais_recente(base)
            self.assertEqual(encontrado.name, "cv-atual.txt")

    def test_nenhum_cv_retorna_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "README.md").write_text("não é CV", encoding="utf-8")
            self.assertIsNone(cv_mod.encontrar_cv_mais_recente(base))


class TestCvUtilizavel(unittest.TestCase):
    def test_texto_curto_nao_utilizavel(self):
        self.assertFalse(cv_mod.cv_e_utilizavel("texto curto"))

    def test_texto_longo_utilizavel(self):
        self.assertTrue(cv_mod.cv_e_utilizavel("x" * 600))


class TestDetectarSkillsCv(unittest.TestCase):
    def test_detecta_skills_do_cv_exemplo(self):
        caminho = Path(__file__).resolve().parent.parent / "cv" / "exemplo.md"
        texto = caminho.read_text(encoding="utf-8")
        skills_cv = cv_mod.detectar_skills_cv(texto, CONFIG["skills_regras"])
        esperado = {
            ("Linguagens", "Python"), ("Ferramentas de pentest", "Burp Suite"),
            ("Ferramentas de pentest", "Nmap"), ("Ferramentas de pentest", "Metasploit"),
            ("Ferramentas de pentest", "Kali Linux"), ("Web/API", "OWASP Top 10"),
            ("Active Directory", "Kerberos"), ("Soft skills/relatórios", "CTF"),
        }
        self.assertTrue(esperado.issubset(skills_cv))

    def test_nao_detecta_email_nem_telefone_como_skill(self):
        texto = "Contato: exemplo@email.com, telefone (11) 91234-5678. Python."
        skills_cv = cv_mod.detectar_skills_cv(texto, CONFIG["skills_regras"])
        self.assertIn(("Linguagens", "Python"), skills_cv)
        # nenhuma skill da taxonomia corresponde a e-mail/telefone — não há o que vazar.
        for categoria, skill in skills_cv:
            self.assertNotIn("@", skill)


class TestExtrairTexto(unittest.TestCase):
    def test_extensao_nao_suportada(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "cv.xyz"
            caminho.write_text("conteúdo", encoding="utf-8")
            with self.assertRaises(ValueError):
                cv_mod.extrair_texto(caminho)

    def test_le_txt_e_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "cv.md"
            caminho.write_text("# CV\nPython, Nmap", encoding="utf-8")
            self.assertIn("Python", cv_mod.extrair_texto(caminho))

    def test_le_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "cv.pdf"
            caminho.write_bytes(_gerar_pdf_minimo("Python Nmap"))
            texto = cv_mod.extrair_texto(caminho)
            self.assertIn("Python", texto)
            self.assertIn("Nmap", texto)

    def test_le_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "cv.docx"
            caminho.write_bytes(_gerar_docx_minimo("Python, Burp Suite e Nmap"))
            texto = cv_mod.extrair_texto(caminho)
            self.assertIn("Python", texto)
            self.assertIn("Burp Suite", texto)

    def test_pdf_sem_pypdf_da_erro_claro(self):
        import sys
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "cv.pdf"
            caminho.write_bytes(_gerar_pdf_minimo("Python"))
            with mock.patch.dict(sys.modules, {"pypdf": None}):
                with self.assertRaises(RuntimeError) as ctx:
                    cv_mod.extrair_texto(caminho)
                self.assertIn("pip install pypdf", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
