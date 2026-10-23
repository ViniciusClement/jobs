"""App web local (Flask) — python run.py servir.

Serve os mesmos painéis de radar.html (lidos ao vivo do SQLite) e adiciona
formulários para editar o que antes só dava pra mudar via CLI/JSON: colar
uma vaga nova, editar qualquer campo de uma vaga (inclusive skills,
salário e restrições), editar o perfil de elegibilidade e o perfil
profissional, mudar status/notas, disparar coleta/análise com um clique.
Importa `run` (o script raiz) para reusar toda a lógica já testada de
persistência/pipeline — nada de lógica de negócio duplicada aqui, só rotas
HTTP e HTML."""

from __future__ import annotations

import argparse
import html as html_lib
import re
from datetime import date
from pathlib import Path

from flask import Flask, Response, redirect, request, url_for

import run as run_mod
from radar import estilo, parser
from radar import skills as skills_mod

_OPCOES_MODALIDADE = ["remoto", "híbrido", "presencial"]
_OPCOES_SENIORIDADE = ["estágio", "júnior", "pleno", "sênior", "especialista", "lead"]
_OPCOES_CONTRATO = ["CLT", "PJ", "outro"]
_OPCOES_VINCULO = ["full_time", "part_time", "contract", "direct_hire", "permanent"]
_OPCOES_MERCADO = ["BR", "INT"]
_OPCOES_MOEDA = ["BRL", "USD", "EUR", "GBP", "CAD", "AUD"]
_OPCOES_PERIODO = ["mes", "ano", "hora"]
_OPCOES_CLASSE = list(skills_mod.PESOS)
_OPCOES_INGLES = ["basico", "intermediario", "avancado", "fluente", "nativo"]
_MAX_LINHAS_REPETIDAS = 200


def _e(valor) -> str:
    """Escapa qualquer valor para texto ou atributo HTML (aspas incluídas)."""
    return html_lib.escape("" if valor is None else str(valor), quote=True)


_ESTILO_PAGINAS = """
.estreito{max-width:1040px;width:100%}
.layout-perfil{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
.layout-perfil .principal{flex:3 1 520px;min-width:0;display:flex;flex-direction:column;gap:16px}
.layout-perfil .lateral-dir{flex:2 1 320px;min-width:0;display:flex;flex-direction:column;gap:16px}
.identidade{display:flex;flex-direction:row;flex-wrap:wrap;gap:18px;align-items:center}
.avatar{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:var(--raised);border:1px solid var(--border-strong);font-family:var(--mono);font-size:24px;color:var(--accent);flex:0 0 auto}
.identidade h2{font-size:22px}
.identidade .headline{margin:4px 0 0;color:var(--fg-2);font-size:15px}
.identidade .local{margin:2px 0 0;color:var(--muted);font-size:13px}
.linha-tempo{display:flex;flex-direction:column}
.exp-item{display:flex;gap:14px;padding:14px 0;border-top:1px solid var(--border)}
.exp-item:first-child{border-top:0;padding-top:0}
.exp-item .ponto{flex:0 0 auto;width:10px;height:10px;margin-top:6px;border-radius:50%;border:2px solid var(--accent)}
.exp-item strong{display:block;font-size:15px}
.exp-empresa{font-size:13.5px;color:var(--fg-2)}
.exp-periodo{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:2px}
.exp-descricao{font-size:14px;color:var(--fg-2);margin:6px 0 0;white-space:pre-line}
.texto-livre{margin:0;font-size:14px;line-height:1.65;color:var(--fg-2);white-space:pre-line}
.score{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.score-info{display:flex;flex-direction:column;gap:4px}
.score-info strong{font-size:18px}
.lista-simples{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:14px;color:var(--fg-2)}
.melhoria{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid var(--border);font-size:14px}
.melhoria:first-of-type{border-top:0}
.prio{font-family:var(--mono);font-size:12px}.prio.alta{color:var(--danger-fg)}.prio.media{color:var(--warn-fg)}.prio.baixa{color:var(--muted)}
.melhoria small{display:block;color:var(--muted);font-size:12.5px}
.linha-repetida .acoes-linha{display:flex;align-items:flex-end;justify-content:flex-end}
.linha-repetida .campo.largo{grid-column:1/-1}
.lista-repetida{display:flex;flex-direction:column;gap:12px}
.skill-linha{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,2fr) minmax(0,1.2fr) auto;gap:10px;align-items:center;
  padding:10px 12px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2)}
.skill-linha .nome{font-size:14px;font-weight:500;overflow:hidden;text-overflow:ellipsis}
.skill-linha .cat{font-size:12.5px;color:var(--muted)}
@media (max-width:640px){.skill-linha{grid-template-columns:1fr 1fr}}
"""


def _layout(titulo: str, corpo: str, atual: str | None = None) -> str:
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Radar de Vagas</title><link rel="icon" href="data:,">
<style>{estilo.CSS_BASE}{_ESTILO_PAGINAS}</style></head><body>
<div class="app">
{estilo.sidebar_app(atual)}
<main class="conteudo">
{corpo}
</main>
</div>
</body></html>"""


def _cabecalho(olho: str, titulo: str, sub: str = "", acoes: str = "") -> str:
    sub_html = f"<p>{sub}</p>" if sub else ""
    acoes_html = f'<div class="acoes">{acoes}</div>' if acoes else ""
    return (
        f'<header class="cabecalho-pagina"><div class="titulos"><div class="olho">{_e(olho)}</div>'
        f"<h1>{_e(titulo)}</h1>{sub_html}</div>{acoes_html}</header>"
    )


def _select_opcoes(valores: list[str], atual: str | None, vazio: str | None = "—") -> str:
    opcoes = [f'<option value="">{_e(vazio)}</option>'] if vazio is not None else []
    for v in valores:
        sel = " selected" if v == atual else ""
        opcoes.append(f'<option value="{_e(v)}"{sel}>{_e(v)}</option>')
    # valor salvo fora da lista (ex.: extraído antes de a lista mudar): preserva em vez de apagar.
    if atual and atual not in valores:
        opcoes.append(f'<option value="{_e(atual)}" selected>{_e(atual)}</option>')
    return "".join(opcoes)


def _campo_texto(nome: str, rotulo: str, valor, largo: bool = False, tipo: str = "text", placeholder: str = "") -> str:
    classe = "campo largo" if largo else "campo"
    ph = f' placeholder="{_e(placeholder)}"' if placeholder else ""
    return (
        f'<label class="{classe}"><span>{_e(rotulo)}</span>'
        f'<input type="{tipo}" name="{nome}" value="{_e(valor)}"{ph}></label>'
    )


def _campo_select(nome: str, rotulo: str, opcoes: list[str], atual, vazio: str | None = "—") -> str:
    return (
        f'<label class="campo"><span>{_e(rotulo)}</span>'
        f'<select name="{nome}">{_select_opcoes(opcoes, atual, vazio)}</select></label>'
    )


def _valor_permitido(valor: str | None, permitidos: list[str]) -> str | None:
    valor = (valor or "").strip()
    return valor if valor in permitidos else None


def _int_ou_none(valor: str | None) -> int | None:
    texto = re.sub(r"[^\d]", "", valor or "")
    return int(texto) if texto else None


def _lista_de_texto(valor: str | None, separadores: str = ",\n") -> list[str]:
    partes = re.split("[" + re.escape(separadores) + "]", valor or "")
    vistos, saida = set(), []
    for p in partes:
        p = p.strip()
        if p and p.lower() not in vistos:
            vistos.add(p.lower())
            saida.append(p)
    return saida


def _indices(form, prefixo: str) -> list[int]:
    achados = set()
    rx = re.compile(rf"^{re.escape(prefixo)}-(\d+)-")
    for chave in form.keys():
        m = rx.match(chave)
        if m:
            achados.add(int(m.group(1)))
    return sorted(achados)[:_MAX_LINHAS_REPETIDAS]


# ---------------------------------------------------------------------------
# Taxonomia de skills (para o editor de skills da vaga)
# ---------------------------------------------------------------------------

def _taxonomia_skills() -> dict[str, str]:
    """{nome canônico da skill: categoria} a partir de data/skills.json."""
    bruto = run_mod._ler_json(run_mod.DATA_DIR / "skills.json", {}) or {}
    mapa = {}
    for categoria, skills in bruto.items():
        if isinstance(skills, dict):
            for nome in skills:
                mapa[nome] = categoria
    return mapa


# ---------------------------------------------------------------------------
# Editar vaga
# ---------------------------------------------------------------------------

def _familias_disponiveis() -> list[str]:
    familias = list((run_mod._ler_json(run_mod.DATA_DIR / "familias.json", {}) or {}).keys())
    return familias + (["outro"] if "outro" not in familias else [])


def _pagina_editar_vaga(vaga: dict, salvo: bool = False) -> str:
    taxonomia = _taxonomia_skills()
    categorias = sorted(set(taxonomia.values()))
    salario = vaga.get("salario") or {}
    anos = vaga.get("anos_experiencia") or {}
    restricoes = vaga.get("restricoes") or {}

    linhas_skills = []
    for i, s in enumerate(vaga.get("skills") or []):
        grupo = ' · <span class="mono">um destes</span>' if s.get("grupo_alternativo") else ""
        linhas_skills.append(
            f'<div class="skill-linha">'
            f'<div><div class="nome">{_e(s.get("skill"))}</div><div class="cat">{_e(s.get("categoria"))}{grupo}</div></div>'
            f'<div class="cat" title="{_e(s.get("evidencia"))}">{_e((s.get("evidencia") or "")[:80])}</div>'
            f'<label class="campo"><span class="sr-only">Classe de {_e(s.get("skill"))}</span>'
            f'<select name="skill-{i}-classe">{_select_opcoes(_OPCOES_CLASSE, s.get("classe"), None)}</select></label>'
            f'<label class="check"><input type="checkbox" name="skill-{i}-remover"> Remover</label>'
            f"</div>"
        )
    skills_html = "".join(linhas_skills) or '<p class="vazio">Nenhuma skill detectada nesta vaga.</p>'

    datalist = "".join(f'<option value="{_e(n)}">' for n in sorted(taxonomia))
    novas = []
    for i in range(3):
        novas.append(
            f'<div class="linha-repetida">'
            f'<label class="campo"><span>Nova skill</span><input type="text" name="nova-{i}-skill" list="lista-skills" '
            f'placeholder="ex.: Kerberos"></label>'
            f'<label class="campo"><span>Categoria (se não estiver na taxonomia)</span>'
            f'<select name="nova-{i}-categoria">{_select_opcoes(categorias, None, "automática")}</select></label>'
            f'<label class="campo"><span>Classe</span>'
            f'<select name="nova-{i}-classe">{_select_opcoes(_OPCOES_CLASSE, "obrigatorio", None)}</select></label>'
            f"</div>"
        )

    aviso = '<div class="aviso">Alterações salvas.</div>' if salvo else ""
    titulo = vaga.get("titulo") or "(sem título)"
    acoes = '<a class="btn" href="/privado#vagas">Voltar às vagas</a>'
    if vaga.get("url"):
        acoes += f'<a class="btn" href="{_e(vaga["url"])}" target="_blank" rel="noopener noreferrer">Abrir anúncio ↗</a>'

    return f"""
{_cabecalho("~/vagas/editar", titulo, _e((vaga.get("empresa") or "empresa não divulgada") + " · campos extraídos automaticamente — corrija o que precisar"), acoes)}
{aviso}
<form method="post" class="estreito" style="display:flex;flex-direction:column;gap:16px">
  <section class="card"><h2>Identificação</h2><div class="campos">
    {_campo_texto("titulo", "Título", vaga.get("titulo"), largo=True)}
    {_campo_texto("empresa", "Empresa", vaga.get("empresa"))}
    {_campo_texto("locais", "Local(is), separados por vírgula", ", ".join(vaga.get("locais") or []))}
    {_campo_texto("url", "URL do anúncio", vaga.get("url"), largo=True, tipo="url", placeholder="https://")}
  </div></section>

  <section class="card"><h2>Classificação</h2><div class="campos">
    {_campo_select("modalidade", "Modalidade", _OPCOES_MODALIDADE, vaga.get("modalidade"))}
    {_campo_select("senioridade", "Senioridade", _OPCOES_SENIORIDADE, vaga.get("senioridade"))}
    {_campo_select("contrato", "Contrato", _OPCOES_CONTRATO, vaga.get("contrato"))}
    {_campo_select("tipo_vinculo", "Vínculo", _OPCOES_VINCULO, vaga.get("tipo_vinculo"))}
    {_campo_select("mercado", "Mercado", _OPCOES_MERCADO, vaga.get("mercado"))}
    {_campo_select("familia_cargo", "Família de cargo", _familias_disponiveis(), vaga.get("familia_cargo"))}
  </div></section>

  <section class="card"><h2>Remuneração e experiência</h2>
    <p class="sub">Salário fica na moeda original — o painel não converte moedas.</p>
    <div class="campos">
    {_campo_texto("salario_min", "Salário mínimo", salario.get("min"), tipo="number")}
    {_campo_texto("salario_max", "Salário máximo", salario.get("max"), tipo="number")}
    {_campo_select("salario_moeda", "Moeda", _OPCOES_MOEDA, salario.get("moeda"))}
    {_campo_select("salario_periodo", "Período", _OPCOES_PERIODO, salario.get("periodo"))}
    {_campo_texto("anos_min", "Anos de experiência (mín.)", anos.get("min"), tipo="number")}
    {_campo_texto("anos_max", "Anos de experiência (máx.)", anos.get("max"), tipo="number")}
  </div></section>

  <section class="card"><h2>Restrições</h2>
    <p class="sub">Usadas no cálculo de elegibilidade e no recorte INT acessível × restrito.</p>
    <div class="campos">
    {_campo_texto("restricao_cidadania", "Cidadania exigida (códigos, ex.: US, CA)", ", ".join(restricoes.get("cidadania") or []))}
    {_campo_texto("restricao_residencia", "Residência exigida (código)", restricoes.get("residencia"))}
    {_campo_texto("restricao_clearance", "Clearance (ex.: secret, ts/sci)", restricoes.get("clearance"))}
    <label class="check" style="align-self:end"><input type="checkbox" name="restricao_clearance_obrigatorio"{" checked" if restricoes.get("clearance_obrigatorio") else ""}> Clearance obrigatório</label>
  </div></section>

  <section class="card"><h2>Skills exigidas</h2>
    <p class="sub">Classe define o peso no ranking e no match (obrigatório 1.0 · mencionado 0.6 · diferencial 0.4).
    Use o nome da taxonomia para a skill contar no match com o seu CV.</p>
    <div class="lista-repetida">{skills_html}</div>
    <div class="rotulo-secao">Adicionar</div>
    <div class="lista-repetida">{"".join(novas)}</div>
    <datalist id="lista-skills">{datalist}</datalist>
  </section>

  <section class="card"><h2>Candidatura</h2><div class="campos">
    {_campo_select("status", "Status", list(run_mod.STATUS_VALIDOS), vaga.get("status") or "novo", None)}
    <label class="campo largo"><span>Notas</span><textarea name="notas" rows="4">{_e(vaga.get("notas"))}</textarea></label>
  </div></section>

  <div class="rodape-form">
    <a class="btn btn-fantasma" href="/privado#vagas">Cancelar</a>
    <button class="btn" type="submit" name="continuar" value="1">Salvar e continuar editando</button>
    <button class="btn btn-primario" type="submit">Salvar alterações</button>
  </div>
</form>
"""


def _campos_vaga_do_form(form, vaga: dict) -> dict:
    """Converte o formulário de edição em campos da vaga, validando listas
    fechadas (select) e números — valor inválido vira None em vez de lixo."""
    locais = _lista_de_texto(form.get("locais"), ",")

    salario = None
    s_min, s_max = _int_ou_none(form.get("salario_min")), _int_ou_none(form.get("salario_max"))
    if s_min is not None or s_max is not None:
        anterior = vaga.get("salario") or {}
        salario = {
            "min": s_min, "max": s_max,
            "moeda": _valor_permitido(form.get("salario_moeda"), _OPCOES_MOEDA + [anterior.get("moeda") or ""]) or None,
            "periodo": _valor_permitido(form.get("salario_periodo"), _OPCOES_PERIODO) or "ano",
            "texto": anterior.get("texto"),
        }

    anos = None
    a_min, a_max = _int_ou_none(form.get("anos_min")), _int_ou_none(form.get("anos_max"))
    if a_min is not None or a_max is not None:
        anos = dict(vaga.get("anos_experiencia") or {})
        anos.update({"min": a_min, "max": a_max, "ambiguo": False})

    restricoes_anteriores = vaga.get("restricoes") or {}
    clearance = (form.get("restricao_clearance") or "").strip().lower() or None
    restricoes = {
        "cidadania": [c.upper() for c in _lista_de_texto(form.get("restricao_cidadania"), ",")] or None,
        "residencia": (form.get("restricao_residencia") or "").strip().upper() or None,
        "clearance": clearance,
        "clearance_obrigatorio": (form.get("restricao_clearance_obrigatorio") == "on") if clearance else None,
        "outras": restricoes_anteriores.get("outras") or [],
    }

    skills = []
    for i, s in enumerate(vaga.get("skills") or []):
        if form.get(f"skill-{i}-remover") == "on":
            continue
        s = dict(s)
        classe = _valor_permitido(form.get(f"skill-{i}-classe"), _OPCOES_CLASSE)
        if classe and classe != s.get("classe"):
            s["classe"] = classe
            s["peso"] = skills_mod.PESOS[classe]
        skills.append(s)

    taxonomia = _taxonomia_skills()
    canonico = {nome.lower(): nome for nome in taxonomia}
    existentes = {(s["categoria"], s["skill"].lower()) for s in skills}
    for i in _indices(form, "nova"):
        nome = (form.get(f"nova-{i}-skill") or "").strip()[:80]
        if not nome:
            continue
        nome = canonico.get(nome.lower(), nome)
        categoria = taxonomia.get(nome) or _valor_permitido(form.get(f"nova-{i}-categoria"), sorted(set(taxonomia.values()))) or "Outras"
        if (categoria, nome.lower()) in existentes:
            continue
        classe = _valor_permitido(form.get(f"nova-{i}-classe"), _OPCOES_CLASSE) or "obrigatorio"
        skills.append({
            "categoria": categoria, "skill": nome, "classe": classe, "peso": skills_mod.PESOS[classe],
            "grupo_alternativo": None, "evidencia": "(adicionada manualmente)",
        })
        existentes.add((categoria, nome.lower()))

    status = form.get("status") or ""
    familias = _familias_disponiveis()
    return {
        "titulo": (form.get("titulo") or "").strip() or None,
        "empresa": (form.get("empresa") or "").strip() or None,
        "locais": locais,
        "modalidade": _valor_permitido(form.get("modalidade"), _OPCOES_MODALIDADE),
        "senioridade": _valor_permitido(form.get("senioridade"), _OPCOES_SENIORIDADE),
        "contrato": _valor_permitido(form.get("contrato"), _OPCOES_CONTRATO),
        "tipo_vinculo": _valor_permitido(form.get("tipo_vinculo"), _OPCOES_VINCULO),
        "mercado": _valor_permitido(form.get("mercado"), _OPCOES_MERCADO),
        "familia_cargo": _valor_permitido(form.get("familia_cargo"), familias + [vaga.get("familia_cargo") or ""]) or "outro",
        "url": (form.get("url") or "").strip() or None,
        "salario": salario,
        "anos_experiencia": anos,
        "restricoes": restricoes,
        "skills": skills,
        "status": status if status in run_mod.STATUS_VALIDOS else (vaga.get("status") or "novo"),
        "notas": (form.get("notas") or "").strip() or None,
    }


# ---------------------------------------------------------------------------
# Perfil profissional
# ---------------------------------------------------------------------------

def _svg_gauge_score(score: int) -> str:
    import math

    raio = 54
    circunferencia = 2 * math.pi * raio
    preenchido = circunferencia * (max(0, min(100, score)) / 100)
    cor = "var(--accent)" if score >= 50 else ("var(--warn)" if score >= 30 else "var(--danger)")
    return f"""<svg width="132" height="132" viewBox="0 0 132 132" role="img" aria-label="Score {score} de 100">
  <circle cx="66" cy="66" r="{raio}" fill="none" stroke="var(--track)" stroke-width="12"/>
  <circle cx="66" cy="66" r="{raio}" fill="none" stroke="{cor}" stroke-width="12"
    stroke-dasharray="{preenchido:.1f} {circunferencia:.1f}" stroke-linecap="round" transform="rotate(-90 66 66)"/>
  <text x="66" y="73" text-anchor="middle" font-size="32" font-family="var(--mono)" fill="var(--fg)">{score}</text>
  <text x="66" y="92" text-anchor="middle" font-size="11" fill="var(--muted)">de 100</text>
</svg>"""


def _periodo_experiencia(e: dict) -> str:
    periodo = " – ".join(p for p in (e.get("inicio"), e.get("fim")) if p)
    extras = [x for x in (e.get("duracao"), e.get("localizacao")) if x]
    return " · ".join([periodo] + extras) if periodo else " · ".join(extras)


def _render_experiencias(experiencias: list[dict]) -> str:
    if not experiencias:
        return '<p class="vazio vazio-perfil">Nenhuma experiência cadastrada ainda.</p>'
    itens = []
    for e in experiencias:
        descricao_bruta = e.get("descricao") or ""
        descricao_corte = descricao_bruta[:600] + ("…" if len(descricao_bruta) > 600 else "")
        desc_html = f'<p class="exp-descricao">{_e(descricao_corte)}</p>' if descricao_corte else ""
        itens.append(
            '<div class="exp-item"><span class="ponto" aria-hidden="true"></span><div>'
            f'<strong>{_e(e.get("cargo"))}</strong>'
            f'<div class="exp-empresa">{_e(e.get("empresa"))}</div>'
            f'<div class="exp-periodo">{_e(_periodo_experiencia(e))}</div>'
            f"{desc_html}</div></div>"
        )
    return f'<div class="linha-tempo">{"".join(itens)}</div>'


def _render_educacao(educacao: list[dict]) -> str:
    if not educacao:
        return '<p class="vazio vazio-perfil">Nenhuma formação cadastrada ainda.</p>'
    itens = []
    for e in educacao:
        itens.append(
            '<div class="exp-item"><span class="ponto" aria-hidden="true"></span><div>'
            f'<strong>{_e(e.get("detalhe"))}</strong>'
            f'<div class="exp-periodo">{_e(e.get("periodo"))}</div>'
            "</div></div>"
        )
    return f'<div class="linha-tempo">{"".join(itens)}</div>'


def _render_chips(itens: list[str], classe: str = "") -> str:
    if not itens:
        return '<p class="vazio vazio-perfil">Nada cadastrado ainda.</p>'
    return '<div class="chips">' + "".join(f'<span class="chip {classe} chip-ld">{_e(i)}</span>' for i in itens) + "</div>"


def _render_sugestoes(sugestoes: list[str]) -> str:
    return "".join(f"<li>{_e(s)}</li>" for s in sugestoes)


def _render_melhorias_curriculo(lacunas: list[dict], n_vagas: int) -> str:
    """Lacunas de maior prioridade entre as skills do mercado e o CV,
    traduzidas em sugestões concretas do que adicionar ao currículo."""
    if not n_vagas:
        return '<p class="vazio-perfil">Sem vagas analisadas ainda — adicione vagas para gerar sugestões.</p>'
    if not lacunas:
        return '<p class="vazio-perfil">Nenhuma lacuna identificada — seu CV cobre bem as skills exigidas pelo mercado atual.</p>'
    itens = []
    for l in sorted(lacunas, key=lambda x: -x["score_lacuna"])[:8]:
        prioridade = "alta" if l["score_lacuna"] >= 0.3 else ("média" if l["score_lacuna"] >= 0.1 else "baixa")
        itens.append(
            "<li>"
            f'<strong>{_e(l["skill"])}</strong> ({_e(l["categoria"])}) — '
            f'aparece em {l["n_vagas"]} de {n_vagas} vaga(s) analisada(s), prioridade {prioridade}. '
            "Se você já tem essa experiência, inclua no currículo; senão, considere como próximo passo de estudo."
            "</li>"
        )
    return f'<ul class="melhorias lista-simples">{"".join(itens)}</ul>'


def _render_melhorias_compacto(lacunas: list[dict], n_vagas: int) -> str:
    """Versão enxuta das melhorias para a tela (o PDF usa a versão em texto)."""
    if not n_vagas or not lacunas:
        return _render_melhorias_curriculo(lacunas, n_vagas)
    itens = []
    for l in sorted(lacunas, key=lambda x: -x["score_lacuna"])[:8]:
        prioridade = "alta" if l["score_lacuna"] >= 0.3 else ("média" if l["score_lacuna"] >= 0.1 else "baixa")
        classe = {"alta": "alta", "média": "media", "baixa": "baixa"}[prioridade]
        itens.append(
            f'<div class="melhoria"><div><strong>{_e(l["skill"])}</strong>'
            f'<small>{_e(l["categoria"])} · em {l["n_vagas"]} de {n_vagas} vaga(s)</small></div>'
            f'<span class="prio {classe}">{prioridade}</span></div>'
        )
    return (
        "".join(itens)
        + '<p class="sub">Se você já tem essa experiência, inclua no currículo; senão, é o próximo passo de estudo.</p>'
    )


def _iniciais(nome: str | None) -> str:
    partes = [p for p in (nome or "").split() if p]
    if not partes:
        return "?"
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


def _pagina_perfil_profissional(perfil: dict, score_info: dict, lacunas: list[dict], n_vagas: int, salvo: bool = False) -> str:
    aviso = ""
    if salvo:
        aviso = '<div class="aviso">Perfil salvo. O score foi recalculado.</div>'
    elif not perfil.get("nome"):
        aviso = (
            '<div class="aviso atencao">Nenhum perfil cadastrado ainda. Preencha manualmente em <strong>Editar perfil</strong> '
            'ou, no LinkedIn, abra seu perfil → "Mais" → "Salvar como PDF" e importe o arquivo ao lado '
            '(ou <code>python run.py import-linkedin caminho/Profile.pdf</code>).</div>'
        )

    soft_pct = score_info["soft_skills_pct"]
    soft_rotulo = "n/d" if soft_pct is None else f"{soft_pct}%"
    barras = []
    for rotulo, peso, pct, classe in (
        ("Hard skills", "55%", score_info["hard_skills_pct"], "ok"),
        ("Soft skills", "20%", soft_pct or 0, "info"),
        ("Completude", "25%", score_info["completude_pct"], "neutro"),
    ):
        valor = soft_rotulo if rotulo == "Soft skills" else f"{pct}%"
        barras.append(
            f'<div class="barra" style="grid-template-columns:minmax(0,170px) minmax(0,1fr) auto">'
            f'<span class="nome">{rotulo} <span class="muted">· {peso}</span></span>'
            f'<span class="trilha"><span class="fill {classe}" style="width:{pct}%"></span></span>'
            f'<span class="valor">{valor}</span></div>'
        )

    idiomas = [
        f'{i.get("idioma")}' + (f' — {i.get("nivel")}' if i.get("nivel") else "")
        for i in (perfil.get("idiomas") or []) if isinstance(i, dict) and i.get("idioma")
    ]

    acoes = (
        f'<a class="btn" href="/perfil-profissional/exportar.pdf">{estilo.icone("baixar", 16)}Exportar PDF revisado</a>'
        f'<a class="btn btn-claro" href="/perfil-profissional/editar">{estilo.icone("editar", 16)}Editar perfil</a>'
    )

    return f"""
{_cabecalho("~/perfil", "Meu perfil", "Perfil profissional (estilo LinkedIn) + score frente às vagas do radar", acoes)}
{aviso}
<div class="layout-perfil">
  <div class="principal">
    <section class="card identidade" aria-label="Identificação">
      <div class="avatar" aria-hidden="true">{_e(_iniciais(perfil.get('nome')))}</div>
      <div style="min-width:0">
        <h2>{_e(perfil.get('nome') or 'Perfil não cadastrado')}</h2>
        <p class="headline">{_e(perfil.get('headline'))}</p>
        <p class="local">{_e(perfil.get('localizacao'))}</p>
      </div>
    </section>
    <section class="card"><h2>Resumo</h2>
      <p class="texto-livre">{_e(perfil.get('resumo') or '(sem resumo — adicione em Editar perfil)')}</p></section>
    <section class="card"><h2>Experiência</h2>{_render_experiencias(perfil.get('experiencias') or [])}</section>
    <div class="grade-3">
      <section class="card"><h2>Formação</h2>{_render_educacao(perfil.get('educacao') or [])}</section>
      <section class="card"><h2>Certificações</h2>{_render_chips(perfil.get('certificacoes') or [], 'ok')}</section>
    </div>
    <section class="card"><h2>Skills autodeclaradas</h2>{_render_chips(perfil.get('skills_linkedin') or [])}
      <div class="rotulo-secao">Idiomas</div>{_render_chips(idiomas)}</section>
  </div>
  <div class="lateral-dir">
    <section class="card" aria-label="Score do perfil">
      <div class="score">{_svg_gauge_score(score_info['score'])}
        <div class="score-info"><span class="rotulo-secao">Score de perfil</span>
          <strong>{_e(score_info['classificacao'])}</strong>
          <span class="muted" style="font-size:13px">Referência do SSI do LinkedIn: 50+ é bom · {n_vagas} vaga(s) no radar</span></div>
      </div>
      <div class="barras">{''.join(barras)}</div>
    </section>
    <section class="card"><h2>Sugestões</h2><ul class="sugestoes lista-simples">{_render_sugestoes(score_info['sugestoes'])}</ul></section>
    <section class="card"><h2>Melhorias sugeridas no currículo</h2>
      <p class="sub">Skills mais exigidas pelas vagas cadastradas e ausentes do seu CV atual.</p>
      {_render_melhorias_compacto(lacunas, n_vagas)}</section>
    <section class="card"><h2>Importar do LinkedIn</h2>
      <p class="sub">Substitui o perfil atual pelo conteúdo do PDF exportado.</p>
      <form method="post" action="/perfil-profissional/importar" enctype="multipart/form-data" style="display:flex;flex-direction:column;gap:12px">
        <label class="campo"><span>PDF do perfil</span><input type="file" name="pdf" accept="application/pdf" required></label>
        <button class="btn" type="submit">{estilo.icone("subir", 16)}Importar PDF</button>
      </form>
    </section>
  </div>
</div>
"""


def _linha_experiencia(i, e: dict) -> str:
    return (
        f'<div class="linha-repetida">'
        f'{_campo_texto(f"exp-{i}-cargo", "Cargo", e.get("cargo"))}'
        f'{_campo_texto(f"exp-{i}-empresa", "Empresa", e.get("empresa"))}'
        f'{_campo_texto(f"exp-{i}-inicio", "Início", e.get("inicio"), placeholder="jan de 2023")}'
        f'{_campo_texto(f"exp-{i}-fim", "Fim", e.get("fim"), placeholder="o momento")}'
        f'{_campo_texto(f"exp-{i}-localizacao", "Local", e.get("localizacao"))}'
        f'<div class="acoes-linha"><label class="check"><input type="checkbox" name="exp-{i}-remover"> Remover</label></div>'
        f'<label class="campo largo"><span>Descrição</span><textarea name="exp-{i}-descricao" rows="3">{_e(e.get("descricao"))}</textarea></label>'
        f"</div>"
    )


def _linha_educacao(i, e: dict) -> str:
    return (
        f'<div class="linha-repetida">'
        f'{_campo_texto(f"edu-{i}-detalhe", "Curso · instituição", e.get("detalhe"))}'
        f'{_campo_texto(f"edu-{i}-periodo", "Período", e.get("periodo"), placeholder="2018 – 2022")}'
        f'<div class="acoes-linha"><label class="check"><input type="checkbox" name="edu-{i}-remover"> Remover</label></div>'
        f"</div>"
    )


def _pagina_editar_perfil_profissional(perfil: dict) -> str:
    exps = perfil.get("experiencias") or []
    edus = perfil.get("educacao") or []
    linhas_exp = "".join(_linha_experiencia(i, e) for i, e in enumerate(exps)) + _linha_experiencia(len(exps), {})
    linhas_edu = "".join(_linha_educacao(i, e) for i, e in enumerate(edus)) + _linha_educacao(len(edus), {})
    idiomas = "\n".join(
        f'{i.get("idioma")}' + (f' — {i.get("nivel")}' if i.get("nivel") else "")
        for i in (perfil.get("idiomas") or []) if isinstance(i, dict) and i.get("idioma")
    )
    return f"""
{_cabecalho("~/perfil/editar", "Editar perfil", "Tudo aqui entra no score (completude) e no PDF do perfil revisado", '<a class="btn" href="/perfil-profissional">Voltar ao perfil</a>')}
<form method="post" class="estreito" style="display:flex;flex-direction:column;gap:16px">
  <section class="card"><h2>Identificação</h2><div class="campos">
    {_campo_texto("nome", "Nome", perfil.get("nome"))}
    {_campo_texto("localizacao", "Localização", perfil.get("localizacao"))}
    {_campo_texto("headline", "Headline", perfil.get("headline"), largo=True, placeholder="o que você faz + especialidade")}
  </div></section>

  <section class="card"><h2>Resumo</h2>
    <label class="campo"><span>Sobre você — experiência, foco e o tipo de vaga que procura</span>
      <textarea name="resumo" rows="6">{_e(perfil.get("resumo"))}</textarea></label>
  </section>

  <section class="card"><div class="card-topo"><h2>Experiência</h2>
    <button class="btn btn-pequeno" type="button" data-adicionar="exp">{estilo.icone("mais", 14)}Adicionar experiência</button></div>
    <div class="lista-repetida" id="lista-exp" data-proximo="{len(exps) + 1}">{linhas_exp}</div>
    <template id="tpl-exp">{_linha_experiencia("__N__", {})}</template>
  </section>

  <section class="card"><div class="card-topo"><h2>Formação</h2>
    <button class="btn btn-pequeno" type="button" data-adicionar="edu">{estilo.icone("mais", 14)}Adicionar formação</button></div>
    <div class="lista-repetida" id="lista-edu" data-proximo="{len(edus) + 1}">{linhas_edu}</div>
    <template id="tpl-edu">{_linha_educacao("__N__", {})}</template>
  </section>

  <section class="card"><h2>Skills, certificações e idiomas</h2><div class="campos">
    <label class="campo"><span>Certificações (uma por linha)</span>
      <textarea name="certificacoes" rows="5">{_e(chr(10).join(perfil.get("certificacoes") or []))}</textarea></label>
    <label class="campo"><span>Skills autodeclaradas (uma por linha ou separadas por vírgula)</span>
      <textarea name="skills_linkedin" rows="5">{_e(chr(10).join(perfil.get("skills_linkedin") or []))}</textarea></label>
    <label class="campo"><span>Idiomas (um por linha, ex.: Inglês — Avançado)</span>
      <textarea name="idiomas" rows="5">{_e(idiomas)}</textarea></label>
  </div></section>

  <div class="rodape-form">
    <a class="btn btn-fantasma" href="/perfil-profissional">Cancelar</a>
    <button class="btn btn-primario" type="submit">Salvar perfil</button>
  </div>
</form>
<script>
for (const botao of document.querySelectorAll('[data-adicionar]')) {{
  botao.addEventListener('click', () => {{
    const tipo = botao.dataset.adicionar;
    const lista = document.getElementById('lista-' + tipo);
    const n = Number(lista.dataset.proximo);
    lista.dataset.proximo = String(n + 1);
    const html = document.getElementById('tpl-' + tipo).innerHTML.split('__N__').join(String(n));
    lista.insertAdjacentHTML('beforeend', html);
    const primeiro = lista.lastElementChild.querySelector('input, textarea');
    if (primeiro) primeiro.focus();
  }});
}}
</script>
"""


def _perfil_profissional_do_form(form, anterior: dict) -> dict:
    def texto(chave, limite=200):
        return (form.get(chave) or "").strip()[:limite] or None

    experiencias = []
    for i in _indices(form, "exp"):
        if form.get(f"exp-{i}-remover") == "on":
            continue
        item = {
            "cargo": texto(f"exp-{i}-cargo"), "empresa": texto(f"exp-{i}-empresa"),
            "inicio": texto(f"exp-{i}-inicio", 40), "fim": texto(f"exp-{i}-fim", 40),
            "localizacao": texto(f"exp-{i}-localizacao"),
            "descricao": texto(f"exp-{i}-descricao", 5000),
        }
        if not any(item.values()):
            continue
        # preserva campos que o formulário não edita (ex.: duração calculada no import)
        anteriores = anterior.get("experiencias") or []
        if i < len(anteriores) and isinstance(anteriores[i], dict):
            item = {**anteriores[i], **item}
        experiencias.append(item)

    educacao = []
    for i in _indices(form, "edu"):
        if form.get(f"edu-{i}-remover") == "on":
            continue
        item = {"detalhe": texto(f"edu-{i}-detalhe", 300), "periodo": texto(f"edu-{i}-periodo", 60)}
        if any(item.values()):
            educacao.append(item)

    idiomas = []
    for linha in (form.get("idiomas") or "").splitlines():
        linha = linha.strip()
        if not linha:
            continue
        partes = re.split(r"\s+[—–-]\s+|\s*\(\s*|\s*:\s*", linha, maxsplit=1)
        nivel = partes[1].rstrip(")").strip() if len(partes) > 1 else None
        idiomas.append({"idioma": partes[0].strip()[:60], "nivel": (nivel or None) and nivel[:60]})

    novo = dict(anterior)
    novo.update({
        "nome": texto("nome"), "headline": texto("headline", 300), "localizacao": texto("localizacao"),
        "resumo": texto("resumo", 8000),
        "experiencias": experiencias, "educacao": educacao,
        "certificacoes": [c[:120] for c in _lista_de_texto(form.get("certificacoes"), "\n")],
        "skills_linkedin": [s[:80] for s in _lista_de_texto(form.get("skills_linkedin"), ",\n")],
        "idiomas": idiomas,
    })
    return novo


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

_ESTILO_PERFIL_PDF = """
<style>
@page{size:A4;margin:28mm 20mm}
*{box-sizing:border-box}
body{font-family:Helvetica,Arial,sans-serif;color:#15180f;font-size:10.5pt;line-height:1.45;margin:0}
h1{font-size:18pt;margin:0 0 2pt}
h2{font-size:9pt;color:#6b7268;text-transform:uppercase;letter-spacing:.06em;margin:20pt 0 8pt;
  border-bottom:1pt solid #d8dbd3;padding-bottom:4pt}
p{margin:4pt 0}
.cabecalho{border-bottom:2pt solid #0E7A4B;padding-bottom:10pt;margin-bottom:6pt}
.cabecalho .headline{color:#3a3f35;font-size:11.5pt}
.cabecalho .local{color:#6b7268;font-size:9.5pt}
.bloco-score{display:flex;gap:18pt;margin:6pt 0}
.bloco-score div{font-size:9pt;color:#6b7268}
.bloco-score strong{display:block;font-size:14pt;color:#0E7A4B}
.exp-item{margin:0 0 10pt;padding-left:10pt;border-left:2pt solid #d8dbd3}
.exp-item .ponto{display:none}
.exp-empresa{color:#0E7A4B;font-weight:bold;font-size:10pt}
.exp-periodo{color:#6b7268;font-size:8.5pt}
.exp-descricao{font-size:9.5pt;white-space:pre-line}
.chip-ld{display:inline-block;background:#eef3ec;border-radius:10pt;padding:2pt 8pt;font-size:8.5pt;margin:0 4pt 4pt 0}
ul{padding-left:14pt;margin:4pt 0}
li{margin:3pt 0;font-size:9.5pt}
.vazio-perfil{color:#6b7268;font-style:italic;font-size:9.5pt}
footer{margin-top:18pt;color:#9aa296;font-size:7.5pt}
</style>
"""


def _pagina_perfil_pdf(perfil: dict, score_info: dict, lacunas: list[dict], n_vagas: int) -> str:
    """HTML standalone (sem nav/CSS dark mode) usado só para gerar o PDF do
    perfil revisado via weasyprint — paleta fixa clara, pensada pra papel."""
    soft_pct = score_info["soft_skills_pct"]
    soft_rotulo = "n/d" if soft_pct is None else f"{soft_pct}%"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Perfil revisado</title>{_ESTILO_PERFIL_PDF}</head><body>
  <div class="cabecalho">
    <h1>{_e(perfil.get('nome') or 'Perfil não importado')}</h1>
    <p class="headline">{_e(perfil.get('headline'))}</p>
    <p class="local">{_e(perfil.get('localizacao'))}</p>
  </div>

  <div class="bloco-score">
    <div>Score de perfil<strong>{score_info['score']}/100</strong>{_e(score_info['classificacao'])}</div>
    <div>Hard skills<strong>{score_info['hard_skills_pct']}%</strong></div>
    <div>Soft skills<strong>{soft_rotulo}</strong></div>
    <div>Completude<strong>{score_info['completude_pct']}%</strong></div>
  </div>

  <h2>Resumo</h2>
  <p>{_e(perfil.get('resumo') or '(sem resumo)')}</p>

  <h2>Melhorias sugeridas no currículo</h2>
  {_render_melhorias_curriculo(lacunas, n_vagas)}

  <h2>Experiência</h2>
  {_render_experiencias(perfil.get('experiencias') or [])}

  <h2>Formação</h2>
  {_render_educacao(perfil.get('educacao') or [])}

  <h2>Skills autodeclaradas</h2>
  {_render_chips(perfil.get('skills_linkedin') or [])}

  <h2>Certificações</h2>
  {_render_chips(perfil.get('certificacoes') or [])}

  <footer>Gerado por Radar de Vagas em {date.today().isoformat()} — documento de uso pessoal.</footer>
</body></html>"""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def criar_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _bloquear_post_de_outra_origem():
        """Mitigação leve de CSRF: o servidor só escuta em 127.0.0.1, mas
        qualquer aba aberta no mesmo navegador (um site malicioso, por
        exemplo) poderia tentar enviar um POST pra cá sem você querer.
        Rejeita POSTs cuja Origin/Referer não seja o próprio host."""
        if request.method != "POST":
            return None
        origem = request.headers.get("Origin") or request.headers.get("Referer")
        if origem and request.host not in origem:
            return Response("Origem da requisição não permitida.", status=403)
        return None

    @app.route("/")
    def painel_publico():
        dados_vagas = run_mod.carregar_vagas()
        vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]
        payload = run_mod.montar_payload_publico(vagas)
        payload["app_viva"] = True
        return Response(run_mod.html_mod.gerar_html(payload, "Radar de Vagas — Painel público"), mimetype="text/html")

    @app.route("/privado")
    def painel_privado():
        dados_vagas = run_mod.carregar_vagas()
        vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]
        payload = run_mod.montar_payload_privado(vagas)
        payload["app_viva"] = True
        return Response(run_mod.html_mod.gerar_html(payload, "Radar de Vagas — Painel privado"), mimetype="text/html")

    @app.route("/privado/vaga/<vaga_id>/atualizar", methods=["POST"])
    def atualizar_vaga(vaga_id):
        novo_status = request.form.get("status", "")
        nota = request.form.get("nota", "")
        dados_vagas = run_mod.carregar_vagas()
        for v in dados_vagas["vagas"]:
            if v["id"] == vaga_id:
                if novo_status in run_mod.STATUS_VALIDOS:
                    v["status"] = novo_status
                v["notas"] = nota or None
                break
        run_mod.salvar_vagas(dados_vagas)
        return redirect(url_for("painel_privado") + "#vagas")

    @app.route("/privado/vaga/<vaga_id>/status", methods=["POST"])
    def mover_status_vaga(vaga_id):
        """Só troca o status (botões do pipeline) — não mexe nas notas."""
        novo_status = request.form.get("status", "")
        if novo_status in run_mod.STATUS_VALIDOS and run_mod.obter_vaga(vaga_id) is not None:
            run_mod.atualizar_vaga(vaga_id, {"status": novo_status})
        return redirect(url_for("painel_privado") + "#pipeline")

    @app.route("/adicionar", methods=["GET", "POST"])
    def pagina_adicionar():
        aviso = None
        if request.method == "POST":
            texto = request.form.get("texto", "").strip()
            if texto:
                config = run_mod.carregar_config()
                dados_vagas = run_mod.carregar_vagas()
                avisos = [
                    run_mod.processar_bloco(bloco, config, date.today(), dados_vagas)
                    for bloco in parser.dividir_arquivo(texto)
                ]
                run_mod.salvar_vagas(dados_vagas)
                aviso = "; ".join(avisos) or "Nada para processar."
            else:
                aviso = "Nada para processar — cole o texto de uma vaga."
        # aviso pode conter o título da vaga colada (texto de terceiros) —
        # escapar antes de embutir em HTML (evita XSS refletido).
        aviso_html = f'<div class="aviso">{html_lib.escape(aviso)}</div>' if aviso else ""
        corpo = f"""
{_cabecalho("~/vagas/adicionar", "Adicionar vaga", "Cole o texto do anúncio — HTML, mojibake e ruído são limpos automaticamente")}
{aviso_html}
<div class="layout-perfil">
  <form method="post" class="card principal">
    <label class="campo"><span>Texto da vaga</span>
      <textarea class="codigo" name="texto" placeholder="Cole aqui o texto da vaga..."></textarea></label>
    <div class="rodape-form" style="border-top:0;padding-top:0">
      <a class="btn btn-fantasma" href="/privado#vagas">Cancelar</a>
      <button class="btn btn-primario" type="submit">Processar e salvar</button>
    </div>
  </form>
  <aside class="card lateral-dir">
    <h2>Formato</h2>
    <p class="sub">Várias vagas de uma vez: separe com uma linha <code>=== VAGA ===</code>.</p>
    <p class="sub">Cabeçalho opcional, seguido de uma linha <code>---</code>:</p>
    <p class="sub"><code>Empresa: ... | Local: ... | URL: ... | Data: AAAA-MM-DD | Origem: ... | Mercado: BR|INT | Status: ...</code></p>
    <p class="sub">Depois de salvar, ajuste qualquer campo em <strong>Vagas → Editar vaga</strong>.</p>
  </aside>
</div>
"""
        return Response(_layout("Adicionar vaga", corpo, "adicionar"), mimetype="text/html")

    @app.route("/perfil", methods=["GET", "POST"])
    def pagina_perfil():
        salvo = False
        if request.method == "POST":
            novo_perfil = {
                "cidadanias": [c.strip().upper() for c in request.form.get("cidadanias", "").split(",") if c.strip()],
                "residencia": (request.form.get("residencia") or "").strip().upper() or None,
                "clearances": [c.strip() for c in request.form.get("clearances", "").split(",") if c.strip()],
                "aceita_relocacao": request.form.get("aceita_relocacao") == "on",
                "idiomas": {
                    "pt": request.form.get("idioma_pt") or "nativo",
                    "en": request.form.get("idioma_en") or "basico",
                },
            }
            run_mod.salvar_perfil(novo_perfil)
            salvo = True

        perfil = run_mod.obter_perfil()
        idiomas = perfil.get("idiomas") or {}
        corpo = f"""
{_cabecalho("~/elegibilidade", "Perfil de elegibilidade", "Usado para calcular sim / não / talvez em cada vaga e o recorte INT acessível × restrito")}
{'<div class="aviso">Perfil salvo. A elegibilidade é recalculada na próxima vez que o painel privado abrir.</div>' if salvo else ''}
<form method="post" class="card estreito" style="max-width:760px">
  <div class="campos">
    {_campo_texto("cidadanias", "Cidadanias (separadas por vírgula, ex.: BR, US)", ", ".join(perfil.get("cidadanias") or []))}
    {_campo_texto("residencia", "Residência (código de país, ex.: BR)", perfil.get("residencia"))}
    {_campo_texto("clearances", "Clearances (separados por vírgula, ex.: secret, ts)", ", ".join(perfil.get("clearances") or []))}
    {_campo_select("idioma_en", "Inglês", _OPCOES_INGLES, idiomas.get("en"), None)}
    {_campo_texto("idioma_pt", "Português", idiomas.get("pt", "nativo"))}
    <label class="check" style="align-self:end"><input type="checkbox" name="aceita_relocacao" id="aceita_relocacao"{" checked" if perfil.get("aceita_relocacao") else ""}> Aceito relocação</label>
  </div>
  <div class="rodape-form"><button class="btn btn-primario" type="submit">Salvar</button></div>
</form>
"""
        return Response(_layout("Elegibilidade", corpo, "elegibilidade"), mimetype="text/html")

    @app.route("/acoes/coletar", methods=["POST"])
    def acao_coletar():
        run_mod.cmd_coletar(argparse.Namespace(dry_run=False))
        run_mod.cmd_processar(argparse.Namespace())  # botão de um clique: coleta + processa
        return redirect(url_for("painel_privado"))

    @app.route("/acoes/analisar", methods=["POST"])
    def acao_analisar():
        run_mod.cmd_analisar(argparse.Namespace(cv=None))
        return redirect(url_for("painel_privado"))

    @app.route("/privado/vaga/<vaga_id>/editar", methods=["GET", "POST"])
    def editar_vaga(vaga_id):
        vaga = run_mod.obter_vaga(vaga_id)
        if vaga is None:
            return Response("Vaga não encontrada.", status=404)

        if request.method == "POST":
            run_mod.atualizar_vaga(vaga_id, _campos_vaga_do_form(request.form, vaga))
            if request.form.get("continuar") == "1":
                return redirect(url_for("editar_vaga", vaga_id=vaga_id, salvo=1))
            return redirect(url_for("painel_privado") + "#vagas")

        corpo = _pagina_editar_vaga(vaga, salvo=request.args.get("salvo") == "1")
        return Response(_layout(f"Editar — {vaga.get('titulo') or vaga_id}", corpo, "vagas"), mimetype="text/html")

    def _carregar_contexto_perfil():
        """Reúne perfil profissional, vagas ativas, skills do CV e score —
        usado tanto pela página /perfil-profissional quanto pelo export PDF,
        para as duas verem exatamente os mesmos números."""
        dados_vagas = run_mod.carregar_vagas()
        vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]

        perfil_prof = run_mod.obter_perfil_profissional()
        caminho_cv = run_mod.cv_mod.encontrar_cv_mais_recente(run_mod.CV_DIR)
        skills_cv = set()
        if caminho_cv is not None:
            try:
                texto_cv = run_mod.cv_mod.extrair_texto(caminho_cv)
                if run_mod.cv_mod.cv_e_utilizavel(texto_cv):
                    config = run_mod.carregar_config()
                    skills_cv = run_mod.cv_mod.detectar_skills_cv(texto_cv, config["skills_regras"])
            except Exception:
                pass

        score_info = run_mod.analise.calcular_score_perfil(perfil_prof, skills_cv, vagas)
        lacunas = run_mod.analise.calcular_lacunas(vagas, skills_cv) if vagas else []
        return perfil_prof, vagas, score_info, lacunas

    @app.route("/perfil-profissional")
    def perfil_profissional():
        perfil_prof, vagas, score_info, lacunas = _carregar_contexto_perfil()
        corpo = _pagina_perfil_profissional(
            perfil_prof, score_info, lacunas, len(vagas), salvo=request.args.get("salvo") == "1"
        )
        titulo_pagina = f"Meu perfil — {perfil_prof.get('nome')}" if perfil_prof.get("nome") else "Meu perfil"
        return Response(_layout(titulo_pagina, corpo, "perfil-profissional"), mimetype="text/html")

    @app.route("/perfil-profissional/editar", methods=["GET", "POST"])
    def editar_perfil_profissional():
        perfil_prof = run_mod.obter_perfil_profissional() or {}
        if request.method == "POST":
            run_mod.salvar_perfil_profissional(_perfil_profissional_do_form(request.form, perfil_prof))
            return redirect(url_for("perfil_profissional", salvo=1))
        corpo = _pagina_editar_perfil_profissional(perfil_prof)
        return Response(_layout("Editar perfil", corpo, "perfil-profissional"), mimetype="text/html")

    @app.route("/perfil-profissional/exportar.pdf")
    def exportar_perfil_pdf():
        perfil_prof, vagas, score_info, lacunas = _carregar_contexto_perfil()
        html_pdf = _pagina_perfil_pdf(perfil_prof, score_info, lacunas, len(vagas))

        import weasyprint

        pdf_bytes = weasyprint.HTML(string=html_pdf).write_pdf()
        nome_arquivo = "perfil-revisado.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
        )

    @app.route("/perfil-profissional/importar", methods=["POST"])
    def importar_perfil_linkedin():
        arquivo = request.files.get("pdf")
        if not arquivo or not arquivo.filename:
            return redirect(url_for("perfil_profissional"))
        import tempfile

        from radar import linkedin_import

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            arquivo.save(tmp.name)
            caminho_tmp = Path(tmp.name)
        try:
            perfil_prof = linkedin_import.importar_pdf_perfil(caminho_tmp)
            run_mod.salvar_perfil_profissional(perfil_prof)
        finally:
            caminho_tmp.unlink(missing_ok=True)
        return redirect(url_for("perfil_profissional"))

    return app
