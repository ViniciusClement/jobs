"""Coletor automático via endpoints JSON públicos oficiais dos ATS (Fase 3).

Só usa os endpoints documentados abaixo, sem login e sem raspar HTML de
página de carreiras. Formatos verificados em 2026-10 contra boards reais
(GitLab/Greenhouse, Vivrelle/Lever, Strava/Ashby, Arista Networks/
SmartRecruiters) antes de implementar — ver resumo da Fase 3.

- Greenhouse:       https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
- Lever:             https://api.lever.co/v0/postings/{slug}?mode=json
- Ashby:             https://api.ashbyhq.com/posting-api/job-board/{slug}
- SmartRecruiters:   https://api.smartrecruiters.com/v1/companies/{slug}/postings
  (SmartRecruiters exige uma segunda chamada por vaga, no endpoint de
  detalhe, para obter jobAd.sections/postingUrl — a listagem não traz isso.)

NÃO coleta LinkedIn, Indeed, Gupy ou qualquer site que proíba automação —
essas fontes continuam manuais via `colar`/`dividir`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

USER_AGENT = "RadarDeVagas/1.0 (+projeto pessoal de estudo de carreira, uso nao comercial)"
TIMEOUT_PADRAO = 15
PAUSA_ENTRE_REQUISICOES = 1.0


def _pausar(segundos: float = PAUSA_ENTRE_REQUISICOES) -> None:
    time.sleep(segundos)


def _fazer_requisicao_json(url: str, timeout: int = TIMEOUT_PADRAO):
    """Única função que toca a rede neste módulo — as demais recebem
    `buscar_json` por injeção, o que permite testar com fixtures sem rede."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            corpo = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} ao acessar {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"falha de rede ao acessar {url}: {exc.reason}") from exc
    return json.loads(corpo)


# ---------------------------------------------------------------------------
# HTML -> texto limpo (preservando listas)
# ---------------------------------------------------------------------------

class _HTMLParaTexto(HTMLParser):
    _TAGS_QUEBRA = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
    _TAGS_LISTA = {"li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._TAGS_LISTA:
            self.partes.append("\n- ")
        elif tag in self._TAGS_QUEBRA:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self._TAGS_QUEBRA or tag in self._TAGS_LISTA:
            self.partes.append("\n")

    def handle_data(self, data):
        self.partes.append(data)

    def texto(self) -> str:
        bruto = "".join(self.partes)
        linhas = [l.strip() for l in bruto.split("\n")]
        return "\n".join(l for l in linhas if l)


def html_para_texto(html_bruto: str | None) -> str:
    if not html_bruto:
        return ""
    parser = _HTMLParaTexto()
    parser.feed(html_bruto)
    parser.close()
    return parser.texto()


# ---------------------------------------------------------------------------
# Conversões auxiliares de data/modalidade/salário
# ---------------------------------------------------------------------------

def _iso_para_data(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _epoch_ms_para_data(valor) -> str | None:
    if not valor:
        return None
    try:
        return datetime.fromtimestamp(valor / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


_MAPA_MODALIDADE = {
    "remote": "remoto", "hybrid": "híbrido", "onsite": "presencial", "on-site": "presencial",
}


def _modalidade_de_texto(valor: str | None) -> str | None:
    return _MAPA_MODALIDADE.get((valor or "").strip().lower())


def _periodo_lever(interval: str | None) -> str | None:
    if not interval:
        return None
    i = interval.lower()
    if "year" in i:
        return "ano"
    if "month" in i:
        return "mes"
    if "hour" in i:
        return "hora"
    return None


def formatar_salario_para_texto(salario: dict | None) -> str | None:
    """Formata salário estruturado como uma linha reconhecível pelo
    extrair_salario do radar.parser (que lê $X-$Y ou R$ X a Y do texto)."""
    if not salario:
        return None
    minimo, maximo, moeda = salario.get("min"), salario.get("max"), salario.get("moeda")
    if minimo is None and maximo is None:
        return None
    periodo = {"ano": "per year", "mes": "per month", "hora": "per hour"}.get(salario.get("periodo"), "per year")

    if moeda == "USD":
        if minimo is not None and maximo is not None:
            return f"Salary: ${minimo:,.0f}-${maximo:,.0f} {periodo}"
        if maximo is not None:
            return f"Salary: up to ${maximo:,.0f} {periodo}"
        return f"Salary: from ${minimo:,.0f} {periodo}"

    if moeda == "BRL":
        periodo_pt = {"per year": "ano", "per month": "mês", "per hour": "hora"}[periodo]
        if minimo is not None and maximo is not None:
            return f"Salário: R$ {minimo:,.0f} a {maximo:,.0f} por {periodo_pt}".replace(",", ".")
        valor = maximo if maximo is not None else minimo
        return f"Salário: R$ {valor:,.0f} por {periodo_pt}".replace(",", ".")

    valores = " - ".join(str(v) for v in (minimo, maximo) if v is not None)
    return f"Salário: {moeda or ''} {valores}".strip()


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------

def coletar_greenhouse(slug: str, buscar_json=_fazer_requisicao_json) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    dados = buscar_json(url) or {}
    vagas = []
    for job in dados.get("jobs") or []:
        departamentos = ", ".join(d.get("name") for d in (job.get("departments") or []) if d.get("name"))
        vagas.append({
            "titulo": job.get("title"),
            "url": job.get("absolute_url"),
            "id_externo": str(job.get("id") or ""),
            "descricao_html": job.get("content") or "",
            "local": (job.get("location") or {}).get("name"),
            "data": _iso_para_data(job.get("updated_at") or job.get("first_published")),
            "departamento": departamentos or None,
            "modalidade": None,
            "salario": None,
            "empresa": job.get("company_name"),
        })
    return vagas


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------

def coletar_lever(slug: str, buscar_json=_fazer_requisicao_json) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    dados = buscar_json(url) or []
    vagas = []
    for posting in dados if isinstance(dados, list) else []:
        categorias = posting.get("categories") or {}
        sr = posting.get("salaryRange")
        salario = None
        if sr:
            salario = {
                "min": sr.get("min"), "max": sr.get("max"),
                "moeda": sr.get("currency"), "periodo": _periodo_lever(sr.get("interval")),
            }
        listas_texto = "".join(
            f"<h3>{l.get('text', '')}</h3>{l.get('content', '')}" for l in (posting.get("lists") or [])
        )
        descricao_html = (posting.get("description") or "") + listas_texto
        vagas.append({
            "titulo": posting.get("text"),
            "url": posting.get("hostedUrl") or posting.get("applyUrl"),
            "id_externo": posting.get("id"),
            "descricao_html": descricao_html,
            "local": categorias.get("location"),
            "data": _epoch_ms_para_data(posting.get("createdAt")),
            "departamento": categorias.get("team") or categorias.get("department"),
            "modalidade": _modalidade_de_texto(posting.get("workplaceType")),
            "salario": salario,
            "empresa": None,
        })
    return vagas


# ---------------------------------------------------------------------------
# Ashby
# ---------------------------------------------------------------------------

def coletar_ashby(slug: str, buscar_json=_fazer_requisicao_json) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    dados = buscar_json(url) or {}
    vagas = []
    for job in dados.get("jobs") or []:
        modalidade = _modalidade_de_texto(job.get("workplaceType"))
        if modalidade is None and job.get("isRemote"):
            modalidade = "remoto"
        vagas.append({
            "titulo": job.get("title"),
            "url": job.get("jobUrl") or job.get("applyUrl"),
            "id_externo": job.get("id"),
            "descricao_html": job.get("descriptionHtml") or job.get("descriptionPlain") or "",
            "local": job.get("location"),
            "data": _iso_para_data(job.get("publishedAt")),
            "departamento": job.get("department") or job.get("team"),
            "modalidade": modalidade,
            "salario": None,
            "empresa": None,
        })
    return vagas


# ---------------------------------------------------------------------------
# SmartRecruiters (lista + detalhe por vaga)
# ---------------------------------------------------------------------------

def coletar_smartrecruiters(slug: str, buscar_json=_fazer_requisicao_json, pausar=_pausar) -> list[dict]:
    url_base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    dados = buscar_json(url_base) or {}
    vagas = []
    for item in dados.get("content") or []:
        posting_id = item.get("id")
        if not posting_id:
            continue
        pausar()
        try:
            detalhe = buscar_json(f"{url_base}/{posting_id}") or {}
        except Exception as exc:
            print(f"  aviso: falha ao buscar detalhe da vaga {posting_id} ({slug}): {exc}")
            continue

        secoes = (detalhe.get("jobAd") or {}).get("sections") or {}
        partes_html = []
        for chave in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
            secao = secoes.get(chave)
            if secao and secao.get("text"):
                partes_html.append(f"<h3>{secao.get('title') or chave}</h3>{secao['text']}")

        local = detalhe.get("location") or {}
        partes_local = [local.get("city"), local.get("region"), local.get("country")]
        modalidade = None
        if local.get("remote"):
            modalidade = "remoto"
        elif local.get("hybrid"):
            modalidade = "híbrido"

        vagas.append({
            "titulo": detalhe.get("name"),
            "url": detalhe.get("postingUrl"),
            "id_externo": str(posting_id),
            "descricao_html": "".join(partes_html),
            "local": ", ".join(p for p in partes_local if p) or None,
            "data": _iso_para_data(detalhe.get("releasedDate")),
            "departamento": (detalhe.get("department") or {}).get("label"),
            "modalidade": modalidade,
            "salario": None,
            "empresa": (detalhe.get("company") or {}).get("name"),
        })
    return vagas


COLETORES = {
    "greenhouse": coletar_greenhouse,
    "lever": coletar_lever,
    "ashby": coletar_ashby,
    "smartrecruiters": coletar_smartrecruiters,
}


# ---------------------------------------------------------------------------
# Filtro de título e montagem do .txt (seção 6)
# ---------------------------------------------------------------------------

def passa_filtro_titulo(titulo: str | None, filtros: dict) -> bool:
    if not titulo:
        return False
    t = titulo.lower()
    exclui = filtros.get("titulo_exclui") or []
    if any(termo.lower() in t for termo in exclui):
        return False
    inclui = filtros.get("titulo_inclui") or []
    if inclui and not any(termo.lower() in t for termo in inclui):
        return False
    return True


def montar_texto_vaga(vaga: dict, tipo_ats: str, mercado: str, empresa_padrao: str) -> str:
    empresa = vaga.get("empresa") or empresa_padrao
    cabecalho = (
        f"Empresa: {empresa} | Local: {vaga.get('local') or ''} | URL: {vaga.get('url') or ''} | "
        f"Data: {vaga.get('data') or ''} | Origem: {tipo_ats} | Mercado: {mercado} | Status: novo"
    )
    linhas_corpo = [vaga.get("titulo") or "(sem título)"]
    if vaga.get("modalidade"):
        linhas_corpo.append(f"Modalidade: {vaga['modalidade']}")
    if vaga.get("departamento"):
        linhas_corpo.append(f"Departamento: {vaga['departamento']}")
    linha_salario = formatar_salario_para_texto(vaga.get("salario"))
    if linha_salario:
        linhas_corpo.append(linha_salario)
    linhas_corpo.append("")
    linhas_corpo.append(html_para_texto(vaga.get("descricao_html")))
    corpo = "\n".join(linhas_corpo)
    return f"{cabecalho}\n---\n{corpo}\n"
