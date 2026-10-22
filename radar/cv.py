"""Leitura do CV e detecção de skills nele (seção 1 da Fase 2).

Nunca grava e-mail, telefone ou links pessoais em nenhuma saída: este módulo
só extrai texto e detecta skills em memória; quem chama decide o que fazer
com o resultado (e não deve persistir o texto bruto do CV)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

LIMITE_CV_CURTO = 500

_EXTENSOES_SUPORTADAS = {".pdf", ".docx", ".txt", ".md"}

_NS_DOCX = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _ler_texto_arquivo(caminho: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return caminho.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return caminho.read_text(encoding="utf-8", errors="replace")


def _extrair_texto_pdf(caminho: Path) -> str:
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError(
            "Leitura de PDF requer a biblioteca 'pypdf'. Instale com: pip install pypdf"
        ) from exc
    leitor = pypdf.PdfReader(str(caminho))
    paginas = [pagina.extract_text() or "" for pagina in leitor.pages]
    return "\n".join(paginas)


def _extrair_texto_docx(caminho: Path) -> str:
    with zipfile.ZipFile(caminho) as z:
        with z.open("word/document.xml") as f:
            arvore = ET.parse(f)
    paragrafos = []
    for p in arvore.getroot().iter(f"{{{_NS_DOCX}}}p"):
        textos = [t.text or "" for t in p.iter(f"{{{_NS_DOCX}}}t")]
        paragrafos.append("".join(textos))
    return "\n".join(paragrafos)


def extrair_texto(caminho: Path) -> str:
    sufixo = caminho.suffix.lower()
    if sufixo == ".pdf":
        return _extrair_texto_pdf(caminho)
    if sufixo == ".docx":
        return _extrair_texto_docx(caminho)
    if sufixo in (".txt", ".md"):
        return _ler_texto_arquivo(caminho)
    raise ValueError(f"Extensão não suportada: {sufixo} (use PDF, DOCX, TXT ou MD)")


def encontrar_cv_mais_recente(diretorio_cv: Path) -> Path | None:
    """Arquivo de modificação mais recente direto em diretorio_cv (ignora subpastas)."""
    if not diretorio_cv.exists():
        return None
    candidatos = [
        p for p in diretorio_cv.iterdir()
        if p.is_file() and p.suffix.lower() in _EXTENSOES_SUPORTADAS and p.name.lower() != "readme.md"
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def cv_e_utilizavel(texto_cv: str) -> bool:
    return len(texto_cv.strip()) >= LIMITE_CV_CURTO


def carregar_cv(diretorio_cv: Path, caminho_forcado: Path | None = None) -> tuple[Path, str]:
    """Localiza e extrai o texto do CV. Imprime no console qual arquivo foi usado."""
    caminho = caminho_forcado or encontrar_cv_mais_recente(diretorio_cv)
    if caminho is None:
        raise FileNotFoundError(
            f"Nenhum CV encontrado em {diretorio_cv} (coloque um .pdf/.docx/.txt/.md ali ou use --cv)."
        )
    print(f"CV utilizado: {caminho}")
    texto = extrair_texto(caminho)
    if not cv_e_utilizavel(texto):
        print(
            f"Aviso: o texto extraído do CV tem só {len(texto.strip())} caractere(s) "
            f"(mínimo esperado: {LIMITE_CV_CURTO}) — pode ser um PDF em imagem sem OCR. "
            "A cobertura NÃO será calculada sobre este CV."
        )
    return caminho, texto


def detectar_skills_cv(texto_cv: str, regras: list) -> set[tuple[str, str]]:
    """Mesmo matcher usado nas vagas (radar.skills), aplicado ao texto inteiro do CV."""
    encontrados: set[tuple[str, str]] = set()
    for linha in texto_cv.split("\n"):
        if not linha.strip():
            continue
        for categoria, nome, patterns in regras:
            if any(p.search(linha) for p in patterns):
                encontrados.add((categoria, nome))
    return encontrados
