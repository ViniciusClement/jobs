"""Normalização de texto bruto de vagas (seção 5 do prompt mestre)."""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_MARCADORES_MOJIBAKE = ("â€", "Ã", "Â")

_GLIFOS_LISTA = "•◇◆▪›"
_RE_GLIFO_LISTA = re.compile(
    r"^([ \t]*)[" + re.escape(_GLIFOS_LISTA) + r"]\s*|^([ \t]*)[*\-]\s+"
)

_RE_LINK_MARKDOWN = re.compile(r"\[([^\]\[]+)\]\((https?://[^\s)]+)\)")

_RE_HASHTAG_ATS = re.compile(r"#LI-([A-Za-z0-9]+)")

_PISTAS_HASHTAG = {
    "remote": "remoto",
    "hybrid": "híbrido",
    "onsite": "presencial",
}

_RE_PALAVRA_COLADA = re.compile(r"(?<=[a-zàâãéêíóôõúç])(?=[A-ZÀÂÃÉÊÍÓÔÕÚÇ])")

# Termos CamelCase legítimos que NÃO são "palavras coladas" por erro de
# conversão HTML->texto (ex.: "assessmentsSocial") e não devem ser separados.
_TERMOS_CAMEL_PROTEGIDOS = [
    "PowerShell", "BloodHound", "GitHub", "GitLab", "SharePoint", "LinkedIn",
    "JavaScript", "TypeScript", "WordPress", "OAuth", "GraphQL", "MongoDB",
    "PostgreSQL", "RabbitMQ", "DevSecOps", "DevOps", "macOS", "iOS", "iPhone",
    "OneDrive", "OneNote", "YouTube",
]
_RE_TERMOS_PROTEGIDOS = re.compile("|".join(re.escape(t) for t in _TERMOS_CAMEL_PROTEGIDOS))

_RE_ESPACOS_MULTIPLOS = re.compile(r"[ \t]+")
_RE_LINHAS_VAZIAS_MULTIPLAS = re.compile(r"\n{3,}")

_PARAMS_RASTREIO = re.compile(r"^(utm_|tk$|trk$|trackingId$|refId$|gh_src$)", re.IGNORECASE)


def corrigir_mojibake(texto: str) -> str:
    """Tenta corrigir mojibake comum (texto utf-8 decodificado como cp1252)."""
    if not any(marcador in texto for marcador in _MARCADORES_MOJIBAKE):
        return texto
    try:
        convertido = texto.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto
    return convertido


def remover_entidades_html(texto: str) -> str:
    texto = texto.replace("&nbsp;", " ")
    return html.unescape(texto)


def normalizar_glifos_lista(texto: str) -> str:
    linhas = texto.split("\n")
    novas = []
    for linha in linhas:
        nova = _RE_GLIFO_LISTA.sub(lambda m: (m.group(1) or m.group(2) or "") + "- ", linha)
        novas.append(nova)
    return "\n".join(novas)


def extrair_links_markdown(texto: str) -> str:
    return _RE_LINK_MARKDOWN.sub(lambda m: f"{m.group(1)} ({m.group(2)})", texto)


def remover_hashtags_ats(texto: str) -> tuple[str, list[str]]:
    pistas: list[str] = []

    def _sub(m: re.Match) -> str:
        sufixo = m.group(1).lower()
        for chave, pista in _PISTAS_HASHTAG.items():
            if sufixo.startswith(chave) or chave.startswith(sufixo[:2]):
                if sufixo.startswith(chave):
                    pistas.append(pista)
                    break
        return ""

    texto_limpo = _RE_HASHTAG_ATS.sub(_sub, texto)
    return texto_limpo, pistas


def remover_ruido(texto: str, config_ruido: dict) -> str:
    exatas = {s.lower() for s in config_ruido.get("linhas_exatas", [])}
    regexes = [re.compile(r, re.IGNORECASE) for r in config_ruido.get("regex", [])]
    linhas_saida = []
    for linha in texto.split("\n"):
        candidata = linha.strip()
        if not candidata:
            linhas_saida.append(linha)
            continue
        if candidata.lower() in exatas:
            continue
        if any(rx.match(candidata) for rx in regexes):
            continue
        linhas_saida.append(linha)
    return "\n".join(linhas_saida)


def separar_palavras_coladas(texto: str) -> str:
    protegidos: dict[str, str] = {}

    def _proteger(m: re.Match) -> str:
        chave = f"\x00PROT{len(protegidos)}\x00"
        protegidos[chave] = m.group(0)
        return chave

    texto_protegido = _RE_TERMOS_PROTEGIDOS.sub(_proteger, texto)
    texto_separado = _RE_PALAVRA_COLADA.sub(" ", texto_protegido)
    for chave, original in protegidos.items():
        texto_separado = texto_separado.replace(chave, original)
    return texto_separado


def normalizar_espacos(texto: str) -> str:
    linhas = [_RE_ESPACOS_MULTIPLOS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas)
    texto = _RE_LINHAS_VAZIAS_MULTIPLAS.sub("\n\n", texto)
    return texto.strip()


def normalizar_url(url: str | None) -> str | None:
    """Remove parâmetros de rastreio; no Indeed mantém só jk/fromjk."""
    if not url:
        return url
    partes = urlsplit(url.strip())
    host = partes.netloc.lower()
    pares = parse_qsl(partes.query, keep_blank_values=True)

    if "indeed." in host:
        identificador = None
        for chave, valor in pares:
            if chave in ("jk", "fromjk"):
                identificador = (chave, valor)
                break
        nova_query = urlencode([identificador]) if identificador else ""
        return urlunsplit((partes.scheme, partes.netloc, partes.path, nova_query, ""))

    pares_filtrados = [(k, v) for k, v in pares if not _PARAMS_RASTREIO.match(k)]
    nova_query = urlencode(pares_filtrados)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, nova_query, ""))


def normalizar_texto(texto: str) -> tuple[str, list[str]]:
    """Pipeline completo de limpeza. Retorna (texto_limpo, pistas)."""
    texto = corrigir_mojibake(texto)
    texto = remover_entidades_html(texto)
    texto = extrair_links_markdown(texto)
    texto, pistas = remover_hashtags_ats(texto)
    texto = normalizar_glifos_lista(texto)
    texto = separar_palavras_coladas(texto)
    texto = normalizar_espacos(texto)
    return texto, pistas


def normalizar_texto_com_ruido(texto: str, config_ruido: dict) -> tuple[str, list[str]]:
    texto, pistas = normalizar_texto(texto)
    texto = remover_ruido(texto, config_ruido)
    texto = normalizar_espacos(texto)
    return texto, pistas
