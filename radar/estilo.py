"""Sistema visual compartilhado entre o template do painel (radar/html.py)
e as páginas da app local (radar/web.py): tokens de cor (tema escuro e
claro automáticos via prefers-color-scheme), tipografia, componentes base
(botões, cards, campos, chips, pílulas de status) e a barra lateral.

Tudo inline — nenhuma fonte, script ou CSS externo (o snapshot estático
publicado no GitHub Pages não pode buscar nada de fora)."""

from __future__ import annotations

import html as html_lib

CSS_BASE = r"""
:root{
  --sans:"IBM Plex Sans","Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:"IBM Plex Mono","JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  --bg:#0B0E13; --surface:#12161D; --surface-2:#0F131A; --raised:#19212B;
  --border:#222833; --border-strong:#2C3440; --track:#1C222C;
  --fg:#E7EAEE; --fg-2:#C9D2DD; --muted:#9BA4B1;
  --accent:#4ADE9B; --accent-hover:#86EFC0; --accent-ink:#06281A; --accent-soft:#0F1F18; --accent-line:#24503C;
  --warn:#F2B45A; --warn-fg:#F5C987; --warn-soft:#231B0E; --warn-line:#5A4320;
  --danger:#F07A6A; --danger-fg:#F49B8E; --danger-soft:#24130F; --danger-line:#5A2C24;
  --info:#6AA8F7; --neutral:#C9D2DD;
  --radius:12px; --radius-sm:8px;
  color-scheme:dark;
}
@media (prefers-color-scheme: light){
  :root{
    --bg:#F5F6F8; --surface:#FFFFFF; --surface-2:#EFF1F4; --raised:#E6EBF0;
    --border:#E0E4E9; --border-strong:#C9D0D8; --track:#E6EAEF;
    --fg:#12161D; --fg-2:#2E3742; --muted:#566170;
    --accent:#0E7A4B; --accent-hover:#0A5E39; --accent-ink:#FFFFFF; --accent-soft:#E3F4EC; --accent-line:#A9D9C2;
    --warn:#9A5B00; --warn-fg:#7A4700; --warn-soft:#FBF0DD; --warn-line:#E8C98E;
    --danger:#C0362C; --danger-fg:#A3271F; --danger-soft:#FBE9E7; --danger-line:#F0B8B0;
    --info:#1F5FBF; --neutral:#5B6573;
    color-scheme:light;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.5;
  -webkit-font-smoothing:antialiased}
h1,h2,h3,h4{line-height:1.25;margin:0}
a{color:var(--accent)} a:hover{color:var(--accent-hover)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code{font-family:var(--mono);font-size:.85em;background:var(--surface-2);border:1px solid var(--border);
  border-radius:4px;padding:1px 5px}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.muted{color:var(--muted)}
.mono{font-family:var(--mono)}

/* ---- shell ---- */
.app{display:flex;flex-direction:column;min-height:100vh}
.lateral{background:var(--surface-2);border-bottom:1px solid var(--border);padding:14px 16px;display:flex;
  flex-direction:column;gap:12px}
.marca{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--fg);padding:0 6px}
.marca strong{font-family:var(--mono);font-weight:600;font-size:16px;display:block}
.marca strong span{color:var(--accent)}
.marca small{display:block;font-size:12px;color:var(--muted)}
.menu{display:flex;gap:4px;overflow-x:auto;padding-bottom:2px}
.menu-grupo{display:none}
.menu-item{display:flex;align-items:center;gap:10px;min-height:44px;padding:0 12px;border-radius:var(--radius-sm);
  color:var(--fg-2);text-decoration:none;font-size:14px;font-family:inherit;background:none;border:0;cursor:pointer;
  white-space:nowrap;text-align:left}
.menu-item svg{flex:0 0 auto;color:var(--muted)}
.menu-item:hover{background:var(--raised);color:var(--fg)}
.menu-item.atual,.menu-item[aria-current="page"]{background:var(--raised);color:var(--fg);font-weight:500}
.menu-item.atual svg,.menu-item[aria-current="page"] svg{color:var(--accent)}
.menu-item .contador{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--muted)}
.conteudo{flex:1;min-width:0;padding:24px 16px 56px;display:flex;flex-direction:column;gap:22px}
@media (min-width:900px){
  .app{flex-direction:row}
  .lateral{flex:0 0 240px;position:sticky;top:0;height:100vh;overflow-y:auto;border-bottom:0;
    border-right:1px solid var(--border);padding:24px 16px;gap:22px}
  .menu{flex-direction:column;overflow:visible}
  .menu-grupo{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
    color:var(--muted);padding:8px 12px 0}
  .conteudo{padding:32px 40px 64px}
}

/* ---- cabeçalho de página ---- */
.cabecalho-pagina{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px}
.cabecalho-pagina .titulos{display:flex;flex-direction:column;gap:6px;min-width:0}
.olho{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.cabecalho-pagina h1{font-size:28px;font-weight:600;letter-spacing:-.01em}
.cabecalho-pagina p{margin:0;color:var(--muted);font-size:14px}
.acoes{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.acoes form{margin:0}

/* ---- botões ---- */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 16px;
  border-radius:var(--radius-sm);border:1px solid var(--border-strong);background:var(--surface);color:var(--fg);
  font:inherit;font-size:14px;font-weight:500;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn:hover{background:var(--raised);color:var(--fg)}
.btn-primario{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:600}
.btn-primario:hover{background:var(--accent-hover);border-color:var(--accent-hover);color:var(--accent-ink)}
.btn-claro{background:var(--fg);border-color:var(--fg);color:var(--bg);font-weight:600}
.btn-claro:hover{background:var(--fg-2);color:var(--bg)}
.btn-fantasma{background:transparent}
.btn-perigo{background:transparent;border-color:var(--danger-line);color:var(--danger-fg)}
.btn-perigo:hover{background:var(--danger-soft);color:var(--danger-fg)}
.btn-pequeno{min-height:36px;padding:0 12px;font-size:13px}
.btn-icone{width:40px;min-height:40px;padding:0}
.btn[disabled]{opacity:.4;cursor:default}

/* ---- cards ---- */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:22px;
  display:flex;flex-direction:column;gap:16px;min-width:0}
.card-topo{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px 12px}
.card h2{font-size:17px;font-weight:600}
.card .sub{font-size:13px;color:var(--muted);margin:0}
.rotulo-secao{font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:16px}
.grade-3{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:16px}
.vazio{color:var(--muted);font-size:14px;padding:6px 0;margin:0}
.legenda{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted)}
.legenda span{display:inline-flex;align-items:center;gap:6px}
.legenda i{width:10px;height:10px;border-radius:2px;display:inline-block}

/* ---- KPIs ---- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;
  display:flex;flex-direction:column;gap:6px;text-decoration:none;color:var(--fg)}
a.kpi:hover{border-color:var(--border-strong);color:var(--fg)}
.kpi.destaque{border-color:var(--accent-line)}
.kpi-rotulo{font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.kpi-valor{font-family:var(--mono);font-size:30px;font-weight:500;letter-spacing:-.02em;line-height:1.1;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kpi-nota{font-size:13px;color:var(--muted)}

/* ---- barras ---- */
.barras{display:flex;flex-direction:column;gap:11px}
.barra{display:grid;grid-template-columns:minmax(0,150px) minmax(0,1fr) auto;align-items:center;gap:12px;font-size:14px}
.barra .nome{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.barra .valor{font-family:var(--mono);font-size:12.5px;color:var(--fg-2);text-align:right;min-width:64px}
.trilha{position:relative;height:8px;border-radius:4px;background:var(--track);overflow:hidden}
.trilha .fill{position:absolute;top:0;bottom:0;left:0;border-radius:4px;background:var(--accent)}
.fill.ok{background:var(--accent)} .fill.falta{background:var(--warn)} .fill.info{background:var(--info)}
.fill.neutro{background:var(--neutral)} .fill.perigo{background:var(--danger)}

/* ---- segmentado ---- */
.seg{display:inline-flex;flex-wrap:wrap;gap:4px;padding:4px;border:1px solid var(--border);border-radius:10px;
  background:var(--surface-2)}
.seg button{min-height:38px;padding:0 14px;border-radius:7px;border:0;background:transparent;color:var(--fg-2);
  font:inherit;font-size:14px;font-weight:500;cursor:pointer}
.seg button:hover{color:var(--fg)}
.seg button.ativo,.seg button[aria-pressed="true"]{background:var(--fg);color:var(--bg)}

/* ---- chips / pílulas ---- */
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;font-size:13px;
  background:var(--raised);color:var(--fg);border:1px solid var(--border-strong)}
.chip.cv-sim,.chip.ok{background:var(--accent-soft);color:var(--accent);border-color:var(--accent-line)}
.chip.cv-nao,.chip.falta{background:var(--warn-soft);color:var(--warn-fg);border-color:var(--warn-line)}
.chip.alerta{background:var(--danger-soft);color:var(--danger-fg);border-color:var(--danger-line)}
.chip .k{color:var(--muted)}
.grupo-chips{display:inline-flex;flex-wrap:wrap;gap:4px;align-items:center;border:1px dashed var(--border-strong);
  border-radius:8px;padding:3px 6px}
.grupo-chips .rotulo-grupo{font-size:11px;color:var(--muted);font-family:var(--mono)}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;
  font-weight:500;border:1px solid var(--border-strong);background:var(--surface-2);color:var(--fg-2);white-space:nowrap}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.pill[data-status="novo"]{color:var(--muted)}
.pill[data-status="interessado"]{color:var(--info)}
.pill[data-status="aplicado"]{color:var(--neutral)}
.pill[data-status="entrevista"]{color:var(--warn)}
.pill[data-status="oferta"]{color:var(--accent)}
.pill[data-status="recusado"]{color:var(--danger)}
.pill[data-status="arquivada"]{color:var(--muted)}
.pill.eleg-sim{color:var(--accent)} .pill.eleg-nao{color:var(--danger)} .pill.eleg-talvez{color:var(--warn)}

/* ---- formulários ---- */
.campos{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:14px}
.campo{display:flex;flex-direction:column;gap:6px;min-width:0}
.campo.largo{grid-column:1/-1}
.campo > span,.campo-rotulo{font-size:12.5px;color:var(--muted)}
input[type=text],input[type=url],input[type=email],input[type=search],input[type=number],select,textarea{
  width:100%;min-height:42px;padding:0 12px;border-radius:var(--radius-sm);border:1px solid var(--border-strong);
  background:var(--surface-2);color:var(--fg);font:inherit;font-size:14px}
textarea{padding:10px 12px;line-height:1.5;resize:vertical;min-height:90px}
textarea.codigo{font-family:var(--mono);font-size:13px;min-height:240px}
input[type=checkbox]{width:18px;height:18px;accent-color:var(--accent);margin:0}
.check{display:inline-flex;align-items:center;gap:10px;min-height:40px;font-size:14px;cursor:pointer}
fieldset{border:0;margin:0;padding:0;min-width:0}
legend{padding:0 0 10px;font-size:15px;font-weight:600}
.aviso{display:flex;gap:10px;padding:12px 14px;border-radius:10px;font-size:14px;
  background:var(--accent-soft);border:1px solid var(--accent-line);color:var(--fg)}
.aviso.atencao{background:var(--warn-soft);border-color:var(--warn-line)}
.rodape-form{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px;padding-top:16px;border-top:1px solid var(--border)}
.linha-repetida{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:10px;
  padding:14px;border:1px solid var(--border);border-radius:10px;background:var(--surface-2)}
footer.rodape{color:var(--muted);font-size:12.5px;font-family:var(--mono)}
"""

_ICONES = {
    "painel": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
              '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "vagas": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    "pipeline": '<rect x="3" y="4" width="5" height="16" rx="1.5"/><rect x="10" y="4" width="5" height="11" rx="1.5"/>'
                '<rect x="17" y="4" width="4" height="7" rx="1.5"/>',
    "cv": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/>',
    "perfil": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "escudo": '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "globo": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "baixar": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M4 19h16"/>',
    "subir": '<path d="M12 15V3"/><path d="M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>',
    "recarregar": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "editar": '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13 7l4 4"/>',
    "seta-esq": '<path d="M15 6l-6 6 6 6"/>',
    "seta-dir": '<path d="M9 6l6 6-6 6"/>',
    "externo": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
}

LOGO_SVG = (
    '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true">'
    '<circle cx="15" cy="15" r="13" stroke="currentColor" stroke-width="1.5" style="color:var(--accent)"/>'
    '<circle cx="15" cy="15" r="7.5" stroke="currentColor" stroke-opacity=".45" stroke-width="1.5" style="color:var(--accent)"/>'
    '<path d="M15 15 L25 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="color:var(--accent)"/>'
    '<circle cx="15" cy="15" r="2.2" fill="currentColor" style="color:var(--accent)"/></svg>'
)


def icone(nome: str, tamanho: int = 18) -> str:
    return (
        f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICONES[nome]}</svg>'
    )


def marca(href: str | None) -> str:
    conteudo = f'{LOGO_SVG}<span><strong>radar<span>/</span>vagas</strong><small>segurança ofensiva</small></span>'
    if href:
        return f'<a class="marca" href="{html_lib.escape(href)}">{conteudo}</a>'
    return f'<div class="marca">{conteudo}</div>'


# Itens da barra lateral da app local. Cada item: (chave, rótulo, ícone, href).
MENU_APP = [
    ("painel", "Painel", "painel", "/privado#painel"),
    ("vagas", "Vagas", "vagas", "/privado#vagas"),
    ("pipeline", "Pipeline", "pipeline", "/privado#pipeline"),
    ("meu-cv", "Meu CV", "cv", "/privado#meu-cv"),
]
MENU_APP_FERRAMENTAS = [
    ("perfil-profissional", "Meu perfil", "perfil", "/perfil-profissional"),
    ("adicionar", "Adicionar vaga", "mais", "/adicionar"),
    ("elegibilidade", "Elegibilidade", "escudo", "/perfil"),
    ("publico", "Painel público", "globo", "/"),
]


def sidebar_app(atual: str | None) -> str:
    """Barra lateral renderizada no servidor para as páginas da app local
    (formulários, perfil). O painel em si (html.py) monta a sua própria,
    com botões que trocam de aba sem recarregar."""

    def item(chave, rotulo, nome_icone, href):
        corrente = ' aria-current="page"' if chave == atual else ""
        return f'<a class="menu-item" href="{href}"{corrente}>{icone(nome_icone)}{html_lib.escape(rotulo)}</a>'

    principais = "".join(item(*i) for i in MENU_APP)
    ferramentas = "".join(item(*i) for i in MENU_APP_FERRAMENTAS)
    return (
        f'<aside class="lateral">{marca("/privado")}'
        f'<nav class="menu" aria-label="Principal">{principais}'
        f'<div class="menu-grupo">Ferramentas</div>{ferramentas}</nav></aside>'
    )
