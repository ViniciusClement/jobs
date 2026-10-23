"""App web local (Flask) — python run.py servir.

Serve os mesmos painéis de radar.html (lidos ao vivo do SQLite) e adiciona
formulários para editar o que antes só dava pra mudar via CLI/JSON: colar
uma vaga nova, editar o perfil, mudar status/notas de uma vaga, disparar
coleta/análise/IA com um clique. Importa `run` (o script raiz) para
reusar toda a lógica já testada de persistência/pipeline — nada de lógica
de negócio duplicada aqui, só rotas HTTP."""

from __future__ import annotations

import argparse
import html as html_lib
from datetime import date
from pathlib import Path

from flask import Flask, Response, redirect, request, url_for

import run as run_mod
from radar import parser

_ESTILO_FORM = """
<style>
:root{--mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --bg:#f7f7f5;--fg:#15180f;--card:#fff;--border:#e2e5de;--muted:#6b7268;--accent:#1f8a5c;--accent-bg:#e7f3ec}
@media (prefers-color-scheme: dark){:root{--bg:#0a0c0a;--fg:#e6ebe4;--card:#121412;--border:#232923;--muted:#8a9388;--accent:#39d98a;--accent-bg:#102018}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:0 16px 48px}
header{padding:18px 0}
header h1{margin:0 0 4px;font-size:1.1rem}
header h1::before{content:'> ';color:var(--accent);font-family:var(--mono)}
nav{display:flex;gap:2px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding:0 0 10px;font-family:var(--mono)}
nav a{color:var(--muted);text-decoration:none;font-size:.76rem;font-weight:600;letter-spacing:.02em;
  padding:7px 12px;border-radius:5px;white-space:nowrap;text-transform:uppercase}
nav a:hover{color:var(--fg);background:var(--accent-bg)}
.caixa{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;max-width:640px;margin:16px 0}
label{display:block;font-size:.82rem;color:var(--muted);margin:12px 0 4px}
input[type=text],input[type=email],textarea,select{width:100%;background:var(--bg);color:var(--fg);
  border:1px solid var(--border);border-radius:6px;padding:8px;font-size:.9rem;font-family:inherit}
textarea{min-height:220px;font-family:var(--mono);font-size:.82rem}
button{background:var(--accent);color:#06130c;border:none;border-radius:6px;padding:9px 18px;font-size:.85rem;
  cursor:pointer;margin-top:14px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.02em;font-weight:600}
button.secundario{background:var(--card);color:var(--accent);border:1px solid var(--accent)}
.aviso{background:var(--accent-bg);color:var(--accent);border-radius:8px;padding:10px 14px;margin:14px 0;font-size:.85rem}
.checkbox-linha{display:flex;align-items:center;gap:8px;margin-top:12px}
.checkbox-linha input{width:auto}
a.voltar{color:var(--muted);font-size:.85rem}
</style>
"""


def _layout(titulo: str, corpo: str) -> str:
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo}</title><link rel="icon" href="data:,">{_ESTILO_FORM}</head><body>
<header>
  <h1>Radar de Vagas</h1>
  <nav>
    <a href="{url_for('painel_publico')}">Painel público</a>
    <a href="{url_for('painel_privado')}">Painel privado</a>
    <a href="{url_for('painel_privado')}#vagas">Vagas</a>
    <a href="{url_for('painel_privado')}#meu-cv">Meu CV</a>
    <a href="{url_for('perfil_profissional')}">Meu perfil</a>
    <a href="{url_for('pagina_adicionar')}">+ Adicionar vaga</a>
    <a href="{url_for('pagina_perfil')}">Configurar perfil</a>
  </nav>
</header>
{corpo}
</body></html>"""


_OPCOES_MODALIDADE = ["remoto", "híbrido", "presencial"]
_OPCOES_SENIORIDADE = ["estágio", "júnior", "pleno", "sênior", "especialista", "lead"]
_OPCOES_CONTRATO = ["CLT", "PJ", "outro"]
_OPCOES_VINCULO = ["full_time", "part_time", "contract", "direct_hire", "permanent"]
_OPCOES_MERCADO = ["BR", "INT"]


def _select_opcoes(valores: list[str], atual: str | None) -> str:
    opcoes = ['<option value="">—</option>']
    for v in valores:
        sel = " selected" if v == atual else ""
        opcoes.append(f'<option value="{html_lib.escape(v)}"{sel}>{html_lib.escape(v)}</option>')
    return "".join(opcoes)


def _pagina_editar_vaga(vaga: dict) -> str:
    return f"""
<div class="caixa">
  <h2>Editar vaga</h2>
  <p>Corrige campos extraídos automaticamente. Status/notas continuam editáveis no card do painel privado.</p>
  <form method="post">
    <label>Título</label>
    <input type="text" name="titulo" value="{html_lib.escape(vaga.get('titulo') or '')}">
    <label>Empresa</label>
    <input type="text" name="empresa" value="{html_lib.escape(vaga.get('empresa') or '')}">
    <label>Local(is) (separados por vírgula)</label>
    <input type="text" name="locais" value="{html_lib.escape(', '.join(vaga.get('locais') or []))}">
    <label>Modalidade</label>
    <select name="modalidade">{_select_opcoes(_OPCOES_MODALIDADE, vaga.get('modalidade'))}</select>
    <label>Senioridade</label>
    <select name="senioridade">{_select_opcoes(_OPCOES_SENIORIDADE, vaga.get('senioridade'))}</select>
    <label>Contrato</label>
    <select name="contrato">{_select_opcoes(_OPCOES_CONTRATO, vaga.get('contrato'))}</select>
    <label>Vínculo</label>
    <select name="tipo_vinculo">{_select_opcoes(_OPCOES_VINCULO, vaga.get('tipo_vinculo'))}</select>
    <label>Mercado</label>
    <select name="mercado">{_select_opcoes(_OPCOES_MERCADO, vaga.get('mercado'))}</select>
    <label>URL</label>
    <input type="text" name="url" value="{html_lib.escape(vaga.get('url') or '')}">
    <button type="submit">Salvar alterações</button>
  </form>
  <p><a class="voltar" href="/privado">← voltar ao painel</a></p>
</div>
"""


def _svg_gauge_score(score: int) -> str:
    import math

    raio = 54
    circunferencia = 2 * math.pi * raio
    preenchido = circunferencia * (max(0, min(100, score)) / 100)
    cor = "#2f9e44" if score >= 50 else ("#e8a33d" if score >= 30 else "#d6475c")
    return f"""<svg width="140" height="140" viewBox="0 0 140 140">
  <circle cx="70" cy="70" r="{raio}" fill="none" stroke="var(--border)" stroke-width="14"/>
  <circle cx="70" cy="70" r="{raio}" fill="none" stroke="{cor}" stroke-width="14"
    stroke-dasharray="{preenchido:.1f} {circunferencia:.1f}" stroke-linecap="round"
    transform="rotate(-90 70 70)"/>
  <text x="70" y="78" text-anchor="middle" font-size="30" font-weight="700" fill="var(--fg)">{score}</text>
</svg>"""


def _render_experiencias(experiencias: list[dict]) -> str:
    if not experiencias:
        return '<p class="vazio-perfil">Nenhuma experiência importada ainda.</p>'
    itens = []
    for e in experiencias:
        periodo = f"{e.get('inicio') or ''} – {e.get('fim') or ''}"
        if e.get("duracao"):
            periodo += f" · {e['duracao']}"
        if e.get("localizacao"):
            periodo += f" · {e['localizacao']}"
        descricao_bruta = e.get("descricao") or ""
        descricao_corte = descricao_bruta[:400] + ("…" if len(descricao_bruta) > 400 else "")
        desc_html = f'<p class="exp-descricao">{html_lib.escape(descricao_corte)}</p>' if descricao_corte else ""
        itens.append(
            '<div class="exp-item">'
            f'<strong>{html_lib.escape(e.get("cargo") or "")}</strong>'
            f'<div class="exp-empresa">{html_lib.escape(e.get("empresa") or "")}</div>'
            f'<div class="exp-periodo">{html_lib.escape(periodo)}</div>'
            f"{desc_html}"
            "</div>"
        )
    return "".join(itens)


def _render_educacao(educacao: list[dict]) -> str:
    if not educacao:
        return '<p class="vazio-perfil">Nenhuma formação importada ainda.</p>'
    itens = []
    for e in educacao:
        itens.append(
            '<div class="exp-item">'
            f'<div>{html_lib.escape(e.get("detalhe") or "")}</div>'
            f'<div class="exp-periodo">{html_lib.escape(e.get("periodo") or "")}</div>'
            "</div>"
        )
    return "".join(itens)


def _render_chips(itens: list[str]) -> str:
    if not itens:
        return '<p class="vazio-perfil">Nada cadastrado ainda.</p>'
    return "".join(f'<span class="chip-ld">{html_lib.escape(i)}</span>' for i in itens)


def _render_sugestoes(sugestoes: list[str]) -> str:
    return "".join(f"<li>{html_lib.escape(s)}</li>" for s in sugestoes)


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
            f'<strong>{html_lib.escape(l["skill"])}</strong> ({html_lib.escape(l["categoria"])}) — '
            f'aparece em {l["n_vagas"]} de {n_vagas} vaga(s) analisada(s), prioridade {prioridade}. '
            "Se você já tem essa experiência, inclua no currículo; senão, considere como próximo passo de estudo."
            "</li>"
        )
    return f'<ul class="melhorias">{"".join(itens)}</ul>'


_ESTILO_PERFIL_PROFISSIONAL = """
<style>
h2,h3{font-family:var(--mono);letter-spacing:-.01em}
h3{font-size:.85rem;text-transform:uppercase;color:var(--muted);letter-spacing:.04em;margin-top:28px}
.cartao-perfil{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start;margin:16px 0}
.cartao-perfil .avatar{width:88px;height:88px;border-radius:50%;background:var(--accent-bg);
  color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:2rem;
  font-weight:700;flex:0 0 auto;font-family:var(--mono)}
.bloco-score{display:flex;gap:20px;align-items:center;flex-wrap:wrap}
.barras-score{display:flex;flex-direction:column;gap:8px;min-width:220px}
.barra-score-linha{display:flex;align-items:center;gap:8px;font-size:.82rem;font-family:var(--mono)}
.barra-score-linha .nome{flex:0 0 110px}
.barra-score-linha .trilha{flex:1;background:var(--border);border-radius:4px;height:8px;overflow:hidden}
.barra-score-linha .preenchido{background:var(--accent);height:100%;display:block}
.exp-item{border-left:2px solid var(--border);padding:6px 0 14px 14px;margin-left:4px}
.exp-empresa{color:var(--accent);font-weight:600;font-size:.88rem}
.exp-periodo{color:var(--muted);font-size:.78rem;margin:2px 0;font-family:var(--mono)}
.exp-descricao{font-size:.84rem;margin-top:4px}
.chip-ld{display:inline-block;background:var(--accent-bg);color:var(--accent);border-radius:999px;
  padding:4px 12px;font-size:.8rem;margin:0 6px 6px 0}
.vazio-perfil{color:var(--muted);font-style:italic}
ul.sugestoes,ul.melhorias{padding-left:18px}
ul.sugestoes li,ul.melhorias li{margin:6px 0;font-size:.86rem}
ul.melhorias li strong{color:var(--accent);font-family:var(--mono);font-weight:600}
.acoes-perfil{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.acoes-perfil a.botao,.acoes-perfil button{background:var(--accent);color:#06130c;border:none;border-radius:6px;
  padding:9px 16px;font-size:.82rem;font-family:var(--mono);text-transform:uppercase;letter-spacing:.02em;
  font-weight:600;text-decoration:none;cursor:pointer;display:inline-block}
.acoes-perfil a.botao.secundario{background:var(--card);color:var(--accent);border:1px solid var(--accent)}
</style>
"""


def _pagina_perfil_profissional(perfil: dict, score_info: dict, lacunas: list[dict], n_vagas: int) -> str:
    aviso_sem_dados = ""
    if not perfil.get("nome"):
        aviso_sem_dados = (
            '<div class="aviso">Nenhum perfil importado ainda. No seu LinkedIn: abra seu próprio '
            'perfil → "Mais" → "Salvar como PDF" — e importe o arquivo abaixo (ou rode '
            '<code>python run.py import-linkedin caminho/Profile.pdf</code> pela CLI).</div>'
        )

    soft_pct = score_info["soft_skills_pct"]
    soft_rotulo = "n/d" if soft_pct is None else f"{soft_pct}%"

    return f"""{_ESTILO_PERFIL_PROFISSIONAL}
<div class="caixa" style="max-width:860px">
  {aviso_sem_dados}
  <div class="cartao-perfil">
    <div class="avatar">{html_lib.escape((perfil.get('nome') or '?')[:1])}</div>
    <div>
      <h2 style="margin:0">{html_lib.escape(perfil.get('nome') or 'Perfil não importado')}</h2>
      <p style="margin:2px 0;color:var(--muted)">{html_lib.escape(perfil.get('headline') or '')}</p>
      <p style="margin:2px 0;color:var(--muted);font-size:.85rem">{html_lib.escape(perfil.get('localizacao') or '')}</p>
    </div>
  </div>

  <h3>Score de perfil (referência: SSI do LinkedIn — 50%+ é bom)</h3>
  <div class="bloco-score">
    {_svg_gauge_score(score_info['score'])}
    <div class="barras-score">
      <div class="barra-score-linha"><span class="nome">Hard skills</span>
        <span class="trilha"><span class="preenchido" style="width:{score_info['hard_skills_pct']}%"></span></span>
        <span>{score_info['hard_skills_pct']}%</span></div>
      <div class="barra-score-linha"><span class="nome">Soft skills</span>
        <span class="trilha"><span class="preenchido" style="width:{soft_pct or 0}%"></span></span>
        <span>{soft_rotulo}</span></div>
      <div class="barra-score-linha"><span class="nome">Completude</span>
        <span class="trilha"><span class="preenchido" style="width:{score_info['completude_pct']}%"></span></span>
        <span>{score_info['completude_pct']}%</span></div>
    </div>
  </div>
  <p><strong>Classificação:</strong> {html_lib.escape(score_info['classificacao'])}</p>

  <div class="acoes-perfil">
    <a class="botao" href="/perfil-profissional/exportar.pdf">⭳ Exportar perfil revisado (PDF)</a>
  </div>

  <h3>Sugestões</h3>
  <ul class="sugestoes">{_render_sugestoes(score_info['sugestoes'])}</ul>

  <h3>Melhorias sugeridas no currículo</h3>
  <p style="color:var(--muted);font-size:.84rem;margin-top:-6px">
    Com base nas skills mais exigidas pelas vagas cadastradas e ausentes do seu CV atual.
  </p>
  {_render_melhorias_curriculo(lacunas, n_vagas)}

  <h3>Resumo</h3>
  <p>{html_lib.escape(perfil.get('resumo') or '(sem resumo importado)')}</p>

  <h3>Experiência</h3>
  {_render_experiencias(perfil.get('experiencias') or [])}

  <h3>Formação</h3>
  {_render_educacao(perfil.get('educacao') or [])}

  <h3>Skills autodeclaradas (LinkedIn)</h3>
  {_render_chips(perfil.get('skills_linkedin') or [])}

  <h3>Certificações</h3>
  {_render_chips(perfil.get('certificacoes') or [])}

  <h3>Importar/atualizar do LinkedIn</h3>
  <form method="post" action="/perfil-profissional/importar" enctype="multipart/form-data">
    <input type="file" name="pdf" accept="application/pdf" required>
    <button type="submit">Importar PDF</button>
  </form>
</div>
"""


_ESTILO_PERFIL_PDF = """
<style>
@page{size:A4;margin:28mm 20mm}
*{box-sizing:border-box}
body{font-family:Helvetica,Arial,sans-serif;color:#15180f;font-size:10.5pt;line-height:1.45;margin:0}
h1{font-size:18pt;margin:0 0 2pt}
h2{font-size:9pt;color:#6b7268;text-transform:uppercase;letter-spacing:.06em;margin:20pt 0 8pt;
  border-bottom:1pt solid #d8dbd3;padding-bottom:4pt}
p{margin:4pt 0}
.cabecalho{border-bottom:2pt solid #1f8a5c;padding-bottom:10pt;margin-bottom:6pt}
.cabecalho .headline{color:#3a3f35;font-size:11.5pt}
.cabecalho .local{color:#6b7268;font-size:9.5pt}
.bloco-score{display:flex;gap:18pt;margin:6pt 0}
.bloco-score div{font-size:9pt;color:#6b7268}
.bloco-score strong{display:block;font-size:14pt;color:#1f8a5c}
.exp-item{margin:0 0 10pt;padding-left:10pt;border-left:2pt solid #d8dbd3}
.exp-empresa{color:#1f8a5c;font-weight:bold;font-size:10pt}
.exp-periodo{color:#6b7268;font-size:8.5pt}
.exp-descricao{font-size:9.5pt}
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
    <h1>{html_lib.escape(perfil.get('nome') or 'Perfil não importado')}</h1>
    <p class="headline">{html_lib.escape(perfil.get('headline') or '')}</p>
    <p class="local">{html_lib.escape(perfil.get('localizacao') or '')}</p>
  </div>

  <div class="bloco-score">
    <div>Score de perfil<strong>{score_info['score']}/100</strong>{html_lib.escape(score_info['classificacao'])}</div>
    <div>Hard skills<strong>{score_info['hard_skills_pct']}%</strong></div>
    <div>Soft skills<strong>{soft_rotulo}</strong></div>
    <div>Completude<strong>{score_info['completude_pct']}%</strong></div>
  </div>

  <h2>Resumo</h2>
  <p>{html_lib.escape(perfil.get('resumo') or '(sem resumo importado)')}</p>

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
        return redirect(url_for("painel_privado"))

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
        # aviso pode conter o título da vaga colada (texto de terceiros) —
        # escapar antes de embutir em HTML (evita XSS refletido).
        aviso_html = html_lib.escape(aviso) if aviso else ""
        corpo = f"""
<div class="caixa">
  <h2>Adicionar vaga</h2>
  <p>Cole o texto de uma ou mais vagas (use uma linha <code>=== VAGA ===</code>
  para separar várias). O cabeçalho opcional
  <code>Empresa: ... | Local: ... | URL: ... | Data: AAAA-MM-DD | Origem: ... | Mercado: BR|INT | Status: ...</code>
  seguido de <code>---</code> também é aceito.</p>
  {f'<div class="aviso">{aviso_html}</div>' if aviso_html else ''}
  <form method="post">
    <textarea name="texto" placeholder="Cole aqui o texto da vaga..."></textarea>
    <button type="submit">Processar</button>
  </form>
</div>
"""
        return Response(_layout("Adicionar vaga", corpo), mimetype="text/html")

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

        def _attr(valor: str) -> str:
            """Escapa valor do perfil antes de embutir num atributo HTML
            (evita quebrar o atributo ou injetar HTML/JS com aspas)."""
            return html_lib.escape(str(valor), quote=True)

        corpo = f"""
<div class="caixa">
  <h2>Perfil</h2>
  <p>Usado para calcular elegibilidade e o recorte INT acessível/restrito no painel privado.</p>
  {'<div class="aviso">Perfil salvo.</div>' if salvo else ''}
  <form method="post">
    <label>Cidadanias (separadas por vírgula, ex.: BR, US)</label>
    <input type="text" name="cidadanias" value="{_attr(', '.join(perfil.get('cidadanias') or []))}">
    <label>Residência (código de país, ex.: BR)</label>
    <input type="text" name="residencia" value="{_attr(perfil.get('residencia') or '')}">
    <label>Clearances (separados por vírgula, ex.: secret, ts)</label>
    <input type="text" name="clearances" value="{_attr(', '.join(perfil.get('clearances') or []))}">
    <div class="checkbox-linha">
      <input type="checkbox" name="aceita_relocacao" id="aceita_relocacao" {'checked' if perfil.get('aceita_relocacao') else ''}>
      <label for="aceita_relocacao" style="margin:0">Aceito relocação</label>
    </div>
    <label>Inglês (basico | intermediario | avancado | fluente | nativo)</label>
    <input type="text" name="idioma_en" value="{_attr((perfil.get('idiomas') or {}).get('en', ''))}">
    <label>Português</label>
    <input type="text" name="idioma_pt" value="{_attr((perfil.get('idiomas') or {}).get('pt', 'nativo'))}">
    <button type="submit">Salvar</button>
  </form>
</div>
"""
        return Response(_layout("Perfil", corpo), mimetype="text/html")

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
            locais_texto = request.form.get("locais", "")
            campos = {
                "titulo": request.form.get("titulo") or None,
                "empresa": request.form.get("empresa") or None,
                "locais": [l.strip() for l in locais_texto.split(",") if l.strip()],
                "modalidade": request.form.get("modalidade") or None,
                "senioridade": request.form.get("senioridade") or None,
                "contrato": request.form.get("contrato") or None,
                "tipo_vinculo": request.form.get("tipo_vinculo") or None,
                "mercado": request.form.get("mercado") or None,
                "url": request.form.get("url") or None,
            }
            run_mod.atualizar_vaga(vaga_id, campos)
            return redirect(url_for("painel_privado"))

        corpo = _pagina_editar_vaga(vaga)
        return Response(_layout(f"Editar — {vaga.get('titulo') or vaga_id}", corpo), mimetype="text/html")

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
        corpo = _pagina_perfil_profissional(perfil_prof, score_info, lacunas, len(vagas))
        titulo_pagina = f"Meu perfil — {perfil_prof.get('nome')}" if perfil_prof.get("nome") else "Meu perfil"
        return Response(_layout(titulo_pagina, corpo), mimetype="text/html")

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
