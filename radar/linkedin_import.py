"""Importador do PDF de perfil do LinkedIn ("Mais" > "Salvar como PDF" na
própria página do seu perfil — não é scraping: você baixa o arquivo e
aponta pra ele). Layout de duas colunas: barra lateral (Contato/Principais
competências/Languages/Certifications/Publications) + coluna principal
(Nome, headline, localização, Resumo, Experiência, Formação acadêmica).

Por design, a seção "Contato" é SEMPRE ignorada — nunca extrai nem grava
telefone/e-mail, mesma regra do CV (radar/cv.py)."""

from __future__ import annotations

import re
from pathlib import Path

_RE_PAGINA = re.compile(r"^Page \d+ of \d+$")
_RE_RESUMO = re.compile(r"^(Resumo|About)$", re.MULTILINE)
_RE_EXPERIENCIA = re.compile(r"^(Experiência|Experience)$", re.MULTILINE)
_RE_FORMACAO = re.compile(r"^(Formação acadêmica|Education)$", re.MULTILINE)
_RE_SKILLS_HEADER = re.compile(r"^(Principais competências|Top Skills)$", re.MULTILINE)
_RE_LANGUAGES_HEADER = re.compile(r"^(Languages|Idiomas)$", re.MULTILINE)
_RE_CERT_SIDEBAR_HEADER = re.compile(r"^(Certifications|Certificações)$", re.MULTILINE)

_RE_DATA_RANGE = re.compile(r"^(?P<inicio>.+?)\s*-\s*(?P<fim>.+?)\s*\((?P<duracao>[^)]+)\)$")
_RE_LOCALIZACAO = re.compile(r"^[A-ZÀ-Ý][\wÀ-ÿ\s]+,\s*[A-ZÀ-Ý][\wÀ-ÿ\s]+,\s*[A-ZÀ-Ý][\wÀ-ÿ\s]+$")
_RE_PARENTESES_COM_ANO = re.compile(r"\(([^()]*\d{4}[^()]*)\)")
_RE_CERTIFICACOES_INLINE = re.compile(r"Certifications:\s*(.*?)(?:Profiles:|$)", re.DOTALL)
_RE_IDIOMA_NIVEL = re.compile(r"^(.+?)\s*\(([^)]+)\)$")


def _extrair_texto(caminho_pdf: Path) -> str:
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError(
            "Importar PDF do LinkedIn requer a biblioteca 'pypdf'. Instale com: pip install pypdf"
        ) from exc
    leitor = pypdf.PdfReader(str(caminho_pdf))
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


def _limpar_linhas(texto: str) -> str:
    linhas = [l.strip() for l in texto.split("\n")]
    linhas = [l for l in linhas if l and not _RE_PAGINA.match(l)]
    return "\n".join(linhas)


def _rejuntar_linhas_quebradas(bloco: str) -> list[str]:
    """Uma linha é continuação da anterior (quebra de linha do PDF no meio
    de um item, não um item novo) quando começa minúscula/parêntese, ou
    quando o item anterior ficou com um '(' sem fechar."""
    itens: list[str] = []
    for linha in bloco.split("\n"):
        linha = linha.strip()
        if not linha:
            continue
        anterior_incompleto = bool(itens) and itens[-1].count("(") > itens[-1].count(")")
        if itens and (linha[0].islower() or linha.startswith("(") or anterior_incompleto):
            itens[-1] = f"{itens[-1]} {linha}"
        else:
            itens.append(linha)
    return itens


def _extrair_secao_sidebar(cabecalho: str, inicio_regex: re.Pattern, regexes_fim: list[re.Pattern]) -> list[str]:
    m_inicio = inicio_regex.search(cabecalho)
    if not m_inicio:
        return []
    fim = len(cabecalho)
    for r in regexes_fim:
        m_fim = r.search(cabecalho, m_inicio.end())
        if m_fim and m_fim.start() < fim:
            fim = m_fim.start()
    return _rejuntar_linhas_quebradas(cabecalho[m_inicio.end():fim])


def _extrair_cabecalho_pessoa(cabecalho: str) -> tuple[str | None, str | None, str | None]:
    """Nome, headline e localização são as últimas 3 linhas não vazias antes
    de 'Resumo' (depois de toda a barra lateral já ter sido emitida)."""
    linhas = [l.strip() for l in cabecalho.split("\n") if l.strip()]
    if len(linhas) < 3:
        return None, None, None
    nome, headline, localizacao = linhas[-3], linhas[-2], linhas[-1]
    if not _RE_LOCALIZACAO.match(localizacao):
        localizacao = None
    return nome or None, headline or None, localizacao


def _extrair_idiomas(cabecalho: str) -> list[dict]:
    itens = _extrair_secao_sidebar(
        cabecalho, _RE_LANGUAGES_HEADER, [_RE_CERT_SIDEBAR_HEADER, re.compile(r"^Publications$", re.MULTILINE)]
    )
    idiomas = []
    for item in itens:
        m = _RE_IDIOMA_NIVEL.match(item)
        if m:
            idiomas.append({"idioma": m.group(1).strip(), "nivel": m.group(2).strip()})
        else:
            idiomas.append({"idioma": item, "nivel": None})
    return idiomas


def _extrair_certificacoes(cabecalho: str, bloco_resumo: str) -> list[str]:
    certs = set(_extrair_secao_sidebar(
        cabecalho, _RE_CERT_SIDEBAR_HEADER, [re.compile(r"^Publications$", re.MULTILINE)]
    ))
    m_inline = _RE_CERTIFICACOES_INLINE.search(bloco_resumo)
    if m_inline:
        for linha in m_inline.group(1).split("\n"):
            linha = linha.strip(" :")
            if linha:
                certs.add(linha)
    return sorted(certs)


def _extrair_experiencias(bloco: str) -> list[dict]:
    linhas = [l for l in bloco.split("\n") if l.strip()]
    indices_data = [i for i, l in enumerate(linhas) if _RE_DATA_RANGE.match(l.strip())]
    experiencias = []
    for pos, i in enumerate(indices_data):
        m = _RE_DATA_RANGE.match(linhas[i].strip())
        cargo = linhas[i - 1].strip() if i - 1 >= 0 else None
        empresa = linhas[i - 2].strip() if i - 2 >= 0 else None
        j = i + 1
        localizacao = None
        if j < len(linhas) and _RE_LOCALIZACAO.match(linhas[j].strip()):
            localizacao = linhas[j].strip()
            j += 1
        fim_bloco = indices_data[pos + 1] - 2 if pos + 1 < len(indices_data) else len(linhas)
        fim_bloco = max(fim_bloco, j)
        descricao = " ".join(l.strip() for l in linhas[j:fim_bloco]).strip()
        experiencias.append({
            "empresa": empresa, "cargo": cargo,
            "inicio": m.group("inicio").strip(), "fim": m.group("fim").strip(),
            "duracao": m.group("duracao").strip(),
            "localizacao": localizacao,
            "descricao": descricao or None,
        })
    return experiencias


def _extrair_educacao(bloco: str) -> list[dict]:
    texto_colapsado = re.sub(r"\s+", " ", bloco).strip()
    entradas = []
    pos_anterior = 0
    for m in _RE_PARENTESES_COM_ANO.finditer(texto_colapsado):
        trecho = texto_colapsado[pos_anterior:m.start()].strip(" ·")
        if trecho:
            entradas.append({"detalhe": trecho, "periodo": m.group(1).strip()})
        pos_anterior = m.end()
    return entradas


def importar_pdf_perfil(caminho_pdf: Path) -> dict:
    texto = _limpar_linhas(_extrair_texto(caminho_pdf))

    m_resumo = _RE_RESUMO.search(texto)
    m_exp = _RE_EXPERIENCIA.search(texto)
    m_form = _RE_FORMACAO.search(texto)

    cabecalho = texto[: m_resumo.start()] if m_resumo else texto
    bloco_resumo = texto[m_resumo.end(): m_exp.start()] if (m_resumo and m_exp) else (
        texto[m_resumo.end():] if m_resumo else ""
    )
    bloco_experiencia = texto[m_exp.end(): m_form.start()] if (m_exp and m_form) else (
        texto[m_exp.end():] if m_exp else ""
    )
    bloco_formacao = texto[m_form.end():] if m_form else ""

    nome, headline, localizacao = _extrair_cabecalho_pessoa(cabecalho)
    skills_linkedin = _extrair_secao_sidebar(
        cabecalho, _RE_SKILLS_HEADER, [_RE_LANGUAGES_HEADER, _RE_CERT_SIDEBAR_HEADER]
    )

    # O "Resumo" costuma ter um texto livre seguido de blocos "Certifications:"
    # e "Profiles:" — separa só o texto livre como resumo de verdade.
    resumo_livre = re.split(r"\nCertifications:|\nProfiles:", bloco_resumo, maxsplit=1)[0].strip()

    return {
        "nome": nome,
        "headline": headline,
        "localizacao": localizacao,
        "resumo": resumo_livre or None,
        "experiencias": _extrair_experiencias(bloco_experiencia),
        "educacao": _extrair_educacao(bloco_formacao),
        "certificacoes": _extrair_certificacoes(cabecalho, bloco_resumo),
        "idiomas": _extrair_idiomas(cabecalho),
        "skills_linkedin": skills_linkedin,
    }
