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

from flask import Flask, Response, redirect, request, url_for

import run as run_mod
from radar import parser

_ESTILO_FORM = """
<style>
:root{--bg:#f5f6f8;--fg:#1a1a1a;--card:#fff;--border:#dde1e6;--muted:#5a6270;--accent:#2b6cb0;--accent-bg:#e7f0fb}
@media (prefers-color-scheme: dark){:root{--bg:#15161a;--fg:#eaeaea;--card:#1f2024;--border:#333640;--muted:#9aa2af;--accent:#6ea8e0;--accent-bg:#1c2b3a}}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:0 16px 48px}
header{padding:16px 0}
nav a{color:var(--accent);text-decoration:none;margin-right:14px;font-size:.9rem}
.caixa{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;max-width:640px;margin:16px 0}
label{display:block;font-size:.82rem;color:var(--muted);margin:12px 0 4px}
input[type=text],input[type=email],textarea,select{width:100%;background:var(--bg);color:var(--fg);
  border:1px solid var(--border);border-radius:6px;padding:8px;font-size:.9rem;font-family:inherit}
textarea{min-height:220px;font-family:ui-monospace,monospace;font-size:.82rem}
button{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:9px 18px;font-size:.9rem;
  cursor:pointer;margin-top:14px}
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
  <nav>
    <a href="{url_for('painel_publico')}">Painel público</a>
    <a href="{url_for('painel_privado')}">Painel privado</a>
    <a href="{url_for('pagina_adicionar')}">+ Adicionar vaga</a>
    <a href="{url_for('pagina_perfil')}">Perfil</a>
  </nav>
</header>
{corpo}
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

    return app
