"""Geração dos dois HTML estáticos (seção Fase 4): docs/index.html (público)
e privado/index.html (privado). Um único template compartilhado — o que
muda entre os dois é o payload JSON embutido (campo "privado": bool) e,
client-side, quais seções a página mostra."""

from __future__ import annotations

import json
import re

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TELEFONE = re.compile(r"\(?\d{2,3}\)?[\s.-]\d{3,5}[\s.-]\d{4}")

LIMITE_EVIDENCIA = 200

# Perfil genérico e público usado SÓ para classificar o recorte "INT
# acessível/restrito" no docs/ público — é uma convenção do projeto (vagas
# acessíveis a um candidato brasileiro em geral), não os dados reais do
# usuário. privado/perfil.json (privado) é usado no privado/index.html.
PERFIL_PUBLICO_GENERICO = {"cidadanias": ["BR"], "residencia": "BR", "aceita_relocacao": False}


def mascarar_contato(texto: str | None) -> str | None:
    if not texto:
        return texto
    texto = _RE_EMAIL.sub("[e-mail oculto]", texto)
    texto = _RE_TELEFONE.sub("[telefone oculto]", texto)
    return texto


def _chips_restricao(restricoes: dict | None) -> list[str]:
    restricoes = restricoes or {}
    chips = []
    if restricoes.get("cidadania"):
        chips.append(f"exige cidadania: {', '.join(restricoes['cidadania'])}")
    if restricoes.get("residencia"):
        chips.append(f"exige residência em {restricoes['residencia']}")
    if restricoes.get("clearance"):
        obrig = "obrigatório" if restricoes.get("clearance_obrigatorio") else "diferencial"
        chips.append(f"clearance {restricoes['clearance'].upper()} ({obrig})")
    return chips


def _recorte_int(vaga: dict, perfil: dict) -> str | None:
    if vaga.get("mercado") != "INT":
        return None
    restricoes = vaga.get("restricoes") or {}
    cidadania_exigida = restricoes.get("cidadania")
    if cidadania_exigida and not (set(perfil.get("cidadanias") or []) & set(cidadania_exigida)):
        return "restrito"
    residencia_exigida = restricoes.get("residencia")
    if residencia_exigida and residencia_exigida != perfil.get("residencia") and not perfil.get("aceita_relocacao"):
        return "restrito"
    return "acessivel"


def montar_vaga_payload(
    vaga: dict, privado: bool, perfil: dict,
    skills_cv: set[tuple[str, str]] | None = None,
    elegibilidade_vaga: dict | None = None,
) -> dict:
    skills_payload = []
    for s in vaga.get("skills") or []:
        item = {
            "categoria": s["categoria"], "skill": s["skill"], "classe": s["classe"],
            "peso": s["peso"], "grupo_alternativo": s.get("grupo_alternativo"),
            "evidencia": mascarar_contato(s.get("evidencia") or "")[:LIMITE_EVIDENCIA],
        }
        if privado:
            item["no_cv"] = bool(skills_cv) and (s["categoria"], s["skill"]) in skills_cv
        skills_payload.append(item)

    secoes_payload = {
        chave: mascarar_contato(valor) for chave, valor in (vaga.get("secoes") or {}).items() if valor
    }

    payload = {
        "id": vaga["id"],
        "titulo": vaga.get("titulo"),
        "empresa": vaga.get("empresa"),
        "locais": vaga.get("locais") or [],
        "mercado": vaga.get("mercado"),
        "modalidade": vaga.get("modalidade"),
        "modalidade_conflito": bool(vaga.get("modalidade_conflito")),
        "senioridade": vaga.get("senioridade"),
        "contrato": vaga.get("contrato"),
        "tipo_vinculo": vaga.get("tipo_vinculo"),
        "familia_cargo": vaga.get("familia_cargo") or "outro",
        "data": vaga.get("data"),
        "data_estimada": bool(vaga.get("data_estimada")),
        "possivelmente_expirada": bool(vaga.get("possivelmente_expirada")),
        "url": vaga.get("url"),
        "restricoes_chips": _chips_restricao(vaga.get("restricoes")),
        "skills": skills_payload,
        "secoes": secoes_payload,
        "recorte_int": _recorte_int(vaga, perfil),
    }

    if privado:
        payload["status"] = vaga.get("status") or "novo"
        payload["notas"] = vaga.get("notas")
        if elegibilidade_vaga:
            payload["elegivel"] = elegibilidade_vaga.get("elegivel")
            payload["elegivel_motivos"] = elegibilidade_vaga.get("motivos") or []

    return payload


def _embutir_json(dados: dict) -> str:
    texto = json.dumps(dados, ensure_ascii=False)
    return texto.replace("</script", "<\\/script").replace("<!--", "<\\!--")


_TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITULO__</title>
<link rel="icon" href="data:,">
<style>
:root{
  --bg:#f6f7f8; --fg:#2b3640; --card:#ffffff; --border:#e1e4e8; --muted:#64707a;
  --accent:#1f6f78; --accent-bg:#e5f2f1; --chip-bg:#eef1f3; --green:#2f9e44; --green-bg:#e9f7ef;
  --red:#d6475c; --red-bg:#fceef0; --bar-bg:#e7eaed;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#14181a; --fg:#e7ebec; --card:#1d2225; --border:#2c3337; --muted:#9aa6ac;
    --accent:#4fb6bf; --accent-bg:#162b2c; --chip-bg:#262c2f; --green:#51cf66; --green-bg:#16301f;
    --red:#ff7a8a; --red-bg:#3a1b22; --bar-bg:#262c2f;
  }
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  margin:0;padding:0 16px 48px;line-height:1.45}
h1,h2,h3{line-height:1.25}
header{position:sticky;top:0;z-index:10;background:var(--bg);padding:14px 0 0;margin-bottom:4px}
header h1{margin:0 0 4px;font-size:1.3rem;font-weight:700;letter-spacing:-.01em}
header p{margin:0 0 10px;color:var(--muted);font-size:.85rem}
.site-nav{display:flex;gap:2px;flex-wrap:wrap;background:var(--chip-bg);border:1px solid var(--border);
  border-radius:10px;padding:5px;margin-bottom:0}
.site-nav a{color:var(--muted);text-decoration:none;font-size:.82rem;font-weight:600;
  padding:7px 14px;border-radius:7px;white-space:nowrap}
.site-nav a:hover{color:var(--fg);background:var(--card)}
.site-nav a.atual{color:#fff;background:var(--accent)}
nav.abas{display:flex;gap:4px;margin:14px 0 0;border-bottom:1px solid var(--border);flex-wrap:wrap}
nav.abas button{background:none;border:none;color:var(--muted);padding:9px 16px;cursor:pointer;
  border-bottom:2px solid transparent;font-size:.88rem;font-weight:600;border-radius:6px 6px 0 0;
  transition:color .15s,background .15s}
nav.abas button:hover{color:var(--fg);background:var(--chip-bg)}
nav.abas button.ativa{border-bottom-color:var(--accent);color:var(--accent)}
section.pagina{display:none}
section.pagina.ativa{display:block}
.grade{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:14px 0}
.painel-card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}
.painel-card h3{margin:0 0 10px;font-size:.95rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.totais{display:flex;gap:18px;flex-wrap:wrap}
.totais .num{font-size:1.6rem;font-weight:700}
.totais .rotulo{font-size:.8rem;color:var(--muted)}
.barra-linha{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:.85rem}
.barra-linha .nome{flex:0 0 150px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.barra-linha .trilha{flex:1;background:var(--bar-bg);border-radius:4px;height:10px;overflow:hidden}
.barra-linha .preenchimento{background:var(--accent);height:100%}
.barra-linha .valor{flex:0 0 42px;text-align:right;color:var(--muted)}
select,input[type="search"]{background:var(--card);color:var(--fg);border:1px solid var(--border);
  border-radius:6px;padding:6px 8px;font-size:.9rem}
.filtros{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0;align-items:center}
.filtros label{font-size:.78rem;color:var(--muted);display:flex;flex-direction:column;gap:2px}
.recortes{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.recortes button{border:1px solid var(--border);background:var(--card);color:var(--fg);
  border-radius:20px;padding:6px 14px;cursor:pointer;font-size:.85rem}
.recortes button.ativo{background:var(--accent);color:#fff;border-color:var(--accent)}
.lista-vagas{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-top:12px}
.vaga{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;font-size:.88rem;
  transition:box-shadow .15s,border-color .15s}
.vaga:hover{box-shadow:0 2px 10px rgba(0,0,0,.06);border-color:var(--accent)}
.vaga h4{margin:0 0 4px;font-size:1rem}
.vaga .empresa{color:var(--muted);margin:0 0 8px}
.linha-meta{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
.selo{background:var(--chip-bg);border-radius:999px;padding:3px 10px;font-size:.72rem;color:var(--fg)}
.selo.alerta{background:var(--red-bg);color:var(--red)}
.selo.match{background:var(--accent-bg);color:var(--accent);font-weight:700}
.chip{background:var(--chip-bg);border-radius:999px;padding:3px 10px;font-size:.74rem;cursor:default;
  transition:transform .1s}
.chip:hover{transform:translateY(-1px)}
.chip.cv-sim{background:var(--green-bg);color:var(--green)}
.chip.cv-nao{background:var(--red-bg);color:var(--red)}
.grupo-chips{border:1px dashed var(--border);border-radius:999px;padding:5px 10px;display:flex;gap:5px;
  flex-wrap:wrap;align-items:center}
.grupo-chips .rotulo-grupo{font-size:.68rem;color:var(--muted)}
.chips-skills{display:flex;gap:5px;flex-wrap:wrap;margin:8px 0}
.chips-restricao{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0}
.chip-restricao{background:var(--red-bg);color:var(--red);border-radius:999px;padding:3px 10px;font-size:.72rem}
details{margin:4px 0}
details summary{cursor:pointer;font-size:.82rem;color:var(--accent)}
details p{white-space:pre-wrap;margin:6px 0 10px;font-size:.84rem}
a.link-vaga{color:var(--accent);font-size:.85rem;font-weight:600}
.elegivel-sim{color:var(--green)}
.elegivel-nao{color:var(--red)}
.elegivel-talvez{color:#e8a33d}
table{border-collapse:collapse;width:100%;font-size:.84rem}
table th{position:sticky;top:0;background:var(--card);border-bottom:2px solid var(--border);
  padding:7px 8px;text-align:left;font-size:.75rem;text-transform:uppercase;letter-spacing:.02em;
  color:var(--muted);cursor:default}
table th.ordenavel{cursor:pointer}
table th.ordenavel:hover{color:var(--accent)}
table td{border-bottom:1px solid var(--border);padding:7px 8px;text-align:left}
table.tabela-vagas tbody tr:hover{background:var(--chip-bg)}
table.tabela-vagas tbody tr:nth-child(even){background:color-mix(in srgb, var(--chip-bg) 45%, transparent)}
.muted{color:var(--muted)}
.vazio{color:var(--muted);font-style:italic;padding:12px 0}
.barrinha-status{display:flex;align-items:center;gap:6px;font-size:.78rem;color:var(--muted);margin-top:6px}
.notas-caixa{background:var(--chip-bg);border-radius:6px;padding:6px 8px;font-size:.78rem;margin-top:6px}
.form-status{margin-top:10px;display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--border);padding-top:8px}
.form-status select,.form-status textarea{background:var(--bg);color:var(--fg);border:1px solid var(--border);
  border-radius:6px;padding:5px 7px;font-size:.78rem;font-family:inherit;width:100%}
.form-status textarea{resize:vertical;min-height:40px}
.form-status button{align-self:flex-start;background:var(--accent);color:#fff;border:none;border-radius:6px;
  padding:5px 12px;font-size:.78rem;cursor:pointer}
.alternador-visualizacao{display:flex;gap:4px;margin:10px 0}
.alternador-visualizacao button{border:1px solid var(--border);background:var(--card);color:var(--muted);
  border-radius:6px;padding:5px 12px;font-size:.8rem;cursor:pointer}
.alternador-visualizacao button.ativo{background:var(--accent);color:#fff;border-color:var(--accent)}
.kpis-executivos{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0}
.kpi-tile{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;
  position:relative;overflow:hidden}
.kpi-tile.destaque{border-color:var(--accent)}
.kpi-tile .kpi-rotulo{font-size:.74rem;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}
.kpi-tile .kpi-valor{font-size:2rem;font-weight:800;margin:4px 0 2px;line-height:1}
.kpi-tile .kpi-nota{font-size:.76rem;color:var(--muted)}
.kpi-tile a{color:inherit;text-decoration:none;display:block}
.kpi-tile a:hover .kpi-valor{color:var(--accent)}
.grafico-linha{width:100%;height:auto}
.grafico-linha .eixo{stroke:var(--border);stroke-width:1}
.grafico-linha .linha{fill:none;stroke:var(--accent);stroke-width:2.5}
.grafico-linha .ponto{fill:var(--accent)}
.grafico-linha text{fill:var(--muted);font-size:9px}
footer{margin-top:30px;color:var(--muted);font-size:.78rem}
@media (max-width:480px){
  .barra-linha .nome{flex-basis:100px}
}
</style>
</head>
<body>
<header>
  <h1>__TITULO__</h1>
  <p id="subtitulo"></p>
  <nav class="site-nav" id="site-nav" hidden>
    <a href="/">Painel público</a>
    <a href="/privado">Painel privado</a>
    <a href="/privado#vagas">Vagas</a>
    <a href="/privado#meu-cv">Meu CV</a>
    <a href="/perfil-profissional">Meu perfil</a>
    <a href="/adicionar">+ Adicionar vaga</a>
    <a href="/perfil">Configurar perfil</a>
  </nav>
</header>

<nav class="abas">
  <button data-pagina="painel" class="ativa">Painel</button>
  <button data-pagina="vagas">Vagas</button>
  <button data-pagina="meu-cv" id="aba-meu-cv" hidden>Meu CV</button>
</nav>

<section class="pagina ativa" id="pagina-painel">
  <div class="recortes" id="seletor-recorte"></div>
  <div class="recortes" id="acoes-app-viva" hidden>
    <form method="post" action="/acoes/coletar" style="margin:0"><button type="submit">↻ Coletar vagas novas</button></form>
    <form method="post" action="/acoes/analisar" style="margin:0"><button type="submit">↻ Recalcular análise/CV</button></form>
  </div>
  <div class="kpis-executivos" id="kpis-executivos"></div>
  <div class="grade" id="grade-painel"></div>
  <div class="grade">
    <div class="painel-card">
      <h3>Comparação BR × Internacional</h3>
      <div id="comparacao-br-int"></div>
    </div>
    <div class="painel-card">
      <h3>Comparação por família de cargo</h3>
      <div id="comparacao-familias"></div>
    </div>
    <div class="painel-card">
      <h3>Em alta (30 dias vs. anterior)</h3>
      <div id="tendencia"></div>
    </div>
    <div class="painel-card">
      <h3>Qualidade dos dados</h3>
      <div id="qualidade-dados"></div>
    </div>
  </div>
</section>

<section class="pagina" id="pagina-vagas">
  <div class="filtros">
    <label>Busca<input type="search" id="f-busca" placeholder="título ou empresa"></label>
    <label>Senioridade<select id="f-senioridade"><option value="">Todas</option></select></label>
    <label>Modalidade<select id="f-modalidade"><option value="">Todas</option></select></label>
    <label>Contrato<select id="f-contrato"><option value="">Todos</option></select></label>
    <label>Vínculo<select id="f-vinculo"><option value="">Todos</option></select></label>
    <label>Família<select id="f-familia"><option value="">Todas</option></select></label>
    <label>Skill<select id="f-skill"><option value="">Todas</option></select></label>
    <label>Restrição<select id="f-restricao">
      <option value="">Todas</option>
      <option value="nenhuma">Sem restrição</option>
      <option value="cidadania">Exige cidadania</option>
      <option value="residencia">Exige residência</option>
      <option value="clearance">Exige clearance</option>
    </select></label>
    <label id="rotulo-so-elegiveis" hidden><input type="checkbox" id="f-so-elegiveis"> Só elegíveis</label>
  </div>
  <div class="alternador-visualizacao">
    <button data-vis="cards" class="ativo">Cards</button>
    <button data-vis="tabela">Tabela</button>
  </div>
  <p class="muted" id="contador-vagas"></p>
  <div class="lista-vagas" id="lista-vagas"></div>
  <div id="tabela-vagas-container" hidden></div>
</section>

<section class="pagina" id="pagina-meu-cv">
  <div class="grade">
    <div class="painel-card">
      <h3>Lacunas priorizadas</h3>
      <div id="cv-lacunas"></div>
    </div>
    <div class="painel-card">
      <h3>Plano de estudo</h3>
      <div id="cv-plano"></div>
    </div>
    <div class="painel-card">
      <h3>Evolução da cobertura (recorte: todos)</h3>
      <div id="cv-evolucao"></div>
    </div>
  </div>
</section>

<footer>Gerado em <span id="gerado-em"></span> — Radar de Vagas.</footer>

<script type="application/json" id="dados-radar">__DADOS_JSON__</script>
<script>
const DADOS = JSON.parse(document.getElementById('dados-radar').textContent);
const PESOS = {obrigatorio: 1.0, mencionado: 0.6, diferencial: 0.4};

document.getElementById('subtitulo').textContent = DADOS.privado
  ? 'Painel privado — inclui match com seu CV, elegibilidade, status e notas.'
  : 'Painel público do mercado de Red Team / Pentest / Segurança Ofensiva.';
document.getElementById('gerado-em').textContent = DADOS.gerado_em || '';

let recorteAtual = 'todos';

function vagasDoRecorte(recorte){
  if (recorte === 'BR') return DADOS.vagas.filter(v => v.mercado === 'BR');
  if (recorte === 'INT_acessivel') return DADOS.vagas.filter(v => v.recorte_int === 'acessivel');
  if (recorte === 'INT_restrito') return DADOS.vagas.filter(v => v.recorte_int === 'restrito');
  return DADOS.vagas;
}

function rankingSkills(vagas){
  const soma = new Map(), vagasPorSkill = new Map();
  for (const v of vagas){
    for (const s of v.skills){
      const chave = s.categoria + '||' + s.skill;
      soma.set(chave, (soma.get(chave)||0) + s.peso);
      if (!vagasPorSkill.has(chave)) vagasPorSkill.set(chave, new Set());
      vagasPorSkill.get(chave).add(v.id);
    }
  }
  const n = vagas.length;
  const linhas = [];
  for (const [chave, s] of soma){
    const [categoria, skill] = chave.split('||');
    const nVagas = vagasPorSkill.get(chave).size;
    linhas.push({categoria, skill, nVagas, percentual: n ? nVagas/n : null, score: n ? s/n : null});
  }
  linhas.sort((a,b)=> (b.score||0) - (a.score||0));
  return linhas;
}

function rankingCategorias(vagas){
  const soma = new Map(), vagasPorCat = new Map();
  for (const v of vagas){
    for (const s of v.skills){
      soma.set(s.categoria, (soma.get(s.categoria)||0) + s.peso);
      if (!vagasPorCat.has(s.categoria)) vagasPorCat.set(s.categoria, new Set());
      vagasPorCat.get(s.categoria).add(v.id);
    }
  }
  const n = vagas.length;
  const linhas = [];
  for (const [categoria, s] of soma){
    linhas.push({categoria, score: n ? s/n : null, nVagas: vagasPorCat.get(categoria).size});
  }
  linhas.sort((a,b)=> (b.score||0) - (a.score||0));
  return linhas;
}

function distribuicao(vagas, campo){
  const n = vagas.length;
  if (!n) return [];
  const contagem = new Map();
  for (const v of vagas){
    const valor = v[campo] || 'não informado';
    contagem.set(valor, (contagem.get(valor)||0) + 1);
  }
  return [...contagem.entries()].map(([valor, c]) => ({valor, n: c, percentual: c/n}))
    .sort((a,b)=> b.n - a.n);
}

function faixasSalariais(vagas){
  const grupos = new Map();
  for (const v of vagas){
    if (!v.salario) continue;
    const {min, max, moeda, periodo} = v.salario;
    const valores = [min, max].filter(x => x !== null && x !== undefined);
    if (!valores.length) continue;
    const representativo = valores.reduce((a,b)=>a+b,0) / valores.length;
    const chave = moeda + '||' + periodo;
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(representativo);
  }
  const linhas = [];
  for (const [chave, valores] of grupos){
    const [moeda, periodo] = chave.split('||');
    const ordenados = [...valores].sort((a,b)=>a-b);
    const mediana = ordenados.length % 2 === 0
      ? (ordenados[ordenados.length/2 - 1] + ordenados[ordenados.length/2]) / 2
      : ordenados[(ordenados.length-1)/2];
    linhas.push({moeda, periodo, n: ordenados.length, min: ordenados[0], mediana, max: ordenados[ordenados.length-1]});
  }
  return linhas;
}

function formatarPct(v){ return (v===null||v===undefined) ? 'n/d' : Math.round(v*100) + '%'; }
function el(tag, props={}, filhos=[]){
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(props)){
    if (k === 'texto') e.textContent = v; else e.setAttribute(k, v);
  }
  for (const f of filhos) e.appendChild(f);
  return e;
}

function renderBarras(container, linhas, rotuloFn, max){
  container.innerHTML = '';
  const maiorScore = Math.max(...linhas.slice(0,max).map(l=>l.score||0), 0.0001);
  for (const linha of linhas.slice(0, max)){
    const div = el('div', {class:'barra-linha'});
    div.appendChild(el('span', {class:'nome', texto: rotuloFn(linha)}));
    const trilha = el('span', {class:'trilha'});
    const preench = el('span', {class:'preenchimento'});
    preench.style.width = Math.max(2, Math.round(((linha.score||0)/maiorScore)*100)) + '%';
    trilha.appendChild(preench);
    div.appendChild(trilha);
    div.appendChild(el('span', {class:'valor', texto: linha.nVagas + ' (' + formatarPct(linha.percentual) + ')'}));
    container.appendChild(div);
  }
  if (!linhas.length) container.appendChild(el('p', {class:'vazio', texto:'Sem dados neste recorte.'}));
}

function renderKpis(vagas){
  const cont = document.getElementById('kpis-executivos');
  cont.innerHTML = '';

  function tile(rotulo, valor, nota, destaque, href){
    const inner = [el('div', {class:'kpi-rotulo', texto: rotulo}), el('div', {class:'kpi-valor', texto: valor})];
    if (nota) inner.push(el('div', {class:'kpi-nota', texto: nota}));
    const tileEl = el('div', {class: 'kpi-tile' + (destaque ? ' destaque' : '')});
    if (href){
      const a = el('a', {href: href});
      for (const n of inner) a.appendChild(n);
      tileEl.appendChild(a);
    } else {
      for (const n of inner) tileEl.appendChild(n);
    }
    cont.appendChild(tileEl);
  }

  tile('Vagas ativas (' + recorteAtual + ')', String(vagas.length), null, false);

  const dist = distribuicao(vagas, 'modalidade');
  const remoto = dist['remoto'];
  tile('Modalidade remoto', remoto ? formatarPct(remoto.percentual) : 'n/d',
    remoto ? remoto.n + ' de ' + vagas.length + ' vaga(s)' : 'sem dados', false);

  const ranking = rankingSkills(vagas);
  tile('Skill #1 do mercado', ranking.length ? ranking[0].skill : '—',
    ranking.length ? 'em ' + formatarPct(ranking[0].percentual) + ' das vagas' : 'sem dados', false);

  if (DADOS.privado){
    const coberturaAtual = (DADOS.cobertura_por_recorte || {})[recorteAtual];
    tile('Cobertura do CV', formatarPct(coberturaAtual), 'recorte: ' + recorteAtual, true);

    if (DADOS.score_perfil){
      tile('Score de perfil', DADOS.score_perfil.score + '/100',
        DADOS.score_perfil.classificacao + ' (referência: 50+)', true, '/perfil-profissional');
    }

    const lacunasAltas = ((DADOS.meu_cv || {}).lacunas || []).filter(l => l.prioridade === 'alta').length;
    tile('Lacunas de alta prioridade', String(lacunasAltas), 'veja a aba Meu CV', lacunasAltas > 0);
  }
}

function renderPainel(){
  const vagas = vagasDoRecorte(recorteAtual);
  const grade = document.getElementById('grade-painel');
  grade.innerHTML = '';
  renderKpis(vagas);

  const skillsCard = el('div', {class:'painel-card'});
  skillsCard.appendChild(el('h3', {texto:'Top 15 skills'}));
  const divSkills = el('div'); skillsCard.appendChild(divSkills);
  renderBarras(divSkills, rankingSkills(vagas), l => l.skill, 15);
  grade.appendChild(skillsCard);

  const catCard = el('div', {class:'painel-card'});
  catCard.appendChild(el('h3', {texto:'Categorias'}));
  const divCat = el('div'); catCard.appendChild(divCat);
  renderBarras(divCat, rankingCategorias(vagas), l => l.categoria, 10);
  grade.appendChild(catCard);

  for (const [campo, titulo] of [['senioridade','Senioridade'], ['modalidade','Modalidade'], ['tipo_vinculo','Vínculo'], ['familia_cargo','Família']]){
    const card = el('div', {class:'painel-card'});
    card.appendChild(el('h3', {texto: titulo}));
    const dist = distribuicao(vagas, campo);
    if (!dist.length) card.appendChild(el('p', {class:'vazio', texto:'Sem dados.'}));
    for (const d of dist){
      card.appendChild(el('div', {class:'barra-linha'}, [
        el('span', {class:'nome', texto: d.valor}),
        el('span', {class:'valor', texto: d.n + ' (' + formatarPct(d.percentual) + ')'}),
      ]));
    }
    grade.appendChild(card);
  }

  const salCard = el('div', {class:'painel-card'});
  salCard.appendChild(el('h3', {texto:'Faixas salariais (sem conversão de moeda)'}));
  const faixas = faixasSalariais(vagas);
  if (!faixas.length) salCard.appendChild(el('p', {class:'vazio', texto:'Sem dados de salário.'}));
  for (const f of faixas){
    salCard.appendChild(el('p', {texto: f.moeda + '/' + f.periodo + ' — N=' + f.n + ' · mín ' + Math.round(f.min) + ' · mediana ' + Math.round(f.mediana) + ' · máx ' + Math.round(f.max)}));
  }
  grade.appendChild(salCard);
}

function renderComparacaoBrInt(){
  const cont = document.getElementById('comparacao-br-int');
  cont.innerHTML = '';
  const dados = (DADOS.comparacao_br_int || []).slice(0, 10);
  if (!dados.length){ cont.appendChild(el('p', {class:'vazio', texto:'Sem dados suficientes.'})); return; }
  const tabela = el('table');
  tabela.innerHTML = '<tr><th>Skill</th><th>BR</th><th>INT</th><th>Δ</th></tr>' + dados.map(d =>
    '<tr><td>'+d.skill+'</td><td>'+formatarPct(d.br)+'</td><td>'+formatarPct(d.int)+'</td><td>'+formatarPct(d.diferenca)+'</td></tr>'
  ).join('');
  cont.appendChild(tabela);
}

function renderComparacaoFamilias(){
  const cont = document.getElementById('comparacao-familias');
  cont.innerHTML = '';
  const familias = DADOS.comparacao_familias || {};
  const chaves = Object.keys(familias);
  if (!chaves.length){ cont.appendChild(el('p', {class:'vazio', texto:'Sem dados.'})); return; }
  for (const familia of chaves){
    const info = familias[familia];
    const top = (info.top_skills||[]).slice(0,5).map(s=>s.skill).join(', ') || '—';
    cont.appendChild(el('p', {texto: familia + ' (' + info.n_vagas + ' vagas): ' + top}));
  }
}

function renderTendencia(){
  const cont = document.getElementById('tendencia');
  cont.innerHTML = '';
  const t = DADOS.tendencia || {status: 'dados insuficientes'};
  if (t.status !== 'ok'){ cont.appendChild(el('p', {class:'vazio', texto:'Dados insuficientes.'})); return; }
  const emAlta = t.tendencias.filter(x=>x.variacao>0).slice(0,10);
  if (!emAlta.length){ cont.appendChild(el('p', {class:'vazio', texto:'Nenhuma skill em alta no momento.'})); return; }
  for (const x of emAlta){
    cont.appendChild(el('p', {texto: x.skill + ': ' + formatarPct(x.participacao_anterior) + ' → ' + formatarPct(x.participacao_recente)}));
  }
}

function renderQualidadeDados(){
  const cont = document.getElementById('qualidade-dados');
  cont.innerHTML = '';
  const q = DADOS.qualidade_dados;
  if (!q){ cont.appendChild(el('p', {class:'vazio', texto:'Sem dados.'})); return; }
  cont.appendChild(el('p', {texto: q.n_vagas + ' vaga(s) · ' + q.possivelmente_expiradas + ' possivelmente expirada(s) · ' + q.datas_estimadas + ' com data estimada · ' + q.anos_ambiguos + ' com anos de experiência ambíguos'}));
}

function popularSelect(id, valores){
  const select = document.getElementById(id);
  for (const v of valores){
    const opt = el('option', {value: v, texto: v});
    select.appendChild(opt);
  }
}

function construirListasDeFiltro(){
  const senioridades = new Set(), modalidades = new Set(), contratos = new Set(), vinculos = new Set(), familias = new Set();
  const skills = new Set();
  for (const v of DADOS.vagas){
    if (v.senioridade) senioridades.add(v.senioridade);
    if (v.modalidade) modalidades.add(v.modalidade);
    if (v.contrato) contratos.add(v.contrato);
    if (v.tipo_vinculo) vinculos.add(v.tipo_vinculo);
    if (v.familia_cargo) familias.add(v.familia_cargo);
    for (const s of v.skills) skills.add(s.skill);
  }
  popularSelect('f-senioridade', [...senioridades].sort());
  popularSelect('f-modalidade', [...modalidades].sort());
  popularSelect('f-contrato', [...contratos].sort());
  popularSelect('f-vinculo', [...vinculos].sort());
  popularSelect('f-familia', [...familias].sort());
  popularSelect('f-skill', [...skills].sort());
}

function tipoRestricao(v){
  if (!v.restricoes_chips || !v.restricoes_chips.length) return 'nenhuma';
  const texto = v.restricoes_chips.join(' ');
  if (texto.includes('cidadania')) return 'cidadania';
  if (texto.includes('residência')) return 'residencia';
  if (texto.includes('clearance')) return 'clearance';
  return 'nenhuma';
}

function renderCardVaga(v){
  const card = el('div', {class:'vaga'});
  card.appendChild(el('h4', {texto: v.titulo || '(sem título)'}));
  card.appendChild(el('p', {class:'empresa', texto: v.empresa || 'empresa não divulgada'}));

  const meta = el('div', {class:'linha-meta'});
  if (v.locais && v.locais.length) meta.appendChild(el('span', {class:'selo', texto: v.locais.join(', ')}));
  if (v.modalidade) meta.appendChild(el('span', {class:'selo', texto: v.modalidade}));
  if (v.senioridade) meta.appendChild(el('span', {class:'selo', texto: v.senioridade}));
  if (v.contrato || v.tipo_vinculo) meta.appendChild(el('span', {class:'selo', texto: [v.contrato, v.tipo_vinculo].filter(Boolean).join(' / ')}));
  if (v.data) meta.appendChild(el('span', {class:'selo', texto: v.data + (v.data_estimada ? ' (estimada)' : '')}));
  if (v.possivelmente_expirada) meta.appendChild(el('span', {class:'selo alerta', texto:'possivelmente expirada'}));
  if (v.modalidade_conflito) meta.appendChild(el('span', {class:'selo alerta', texto:'modalidade conflitante'}));
  if (DADOS.privado && typeof v.match === 'number') meta.appendChild(el('span', {class:'selo match', texto:'match ' + formatarPct(v.match)}));
  card.appendChild(meta);

  if (v.restricoes_chips && v.restricoes_chips.length){
    const chipsR = el('div', {class:'chips-restricao'});
    for (const c of v.restricoes_chips) chipsR.appendChild(el('span', {class:'chip-restricao', texto: c}));
    card.appendChild(chipsR);
  }

  if (DADOS.privado && v.elegivel){
    const classe = 'elegivel-' + v.elegivel;
    const p = el('p', {class: classe, texto: 'Elegibilidade: ' + v.elegivel});
    if (v.elegivel_motivos && v.elegivel_motivos.length) p.title = v.elegivel_motivos.join('; ');
    card.appendChild(p);
  }

  const chipsContainer = el('div', {class:'chips-skills'});
  const semGrupo = v.skills.filter(s => !s.grupo_alternativo);
  const grupos = new Map();
  for (const s of v.skills){
    if (s.grupo_alternativo){
      if (!grupos.has(s.grupo_alternativo)) grupos.set(s.grupo_alternativo, []);
      grupos.get(s.grupo_alternativo).push(s);
    }
  }
  function chipDeSkill(s){
    let classe = 'chip';
    if (DADOS.privado) classe += s.no_cv ? ' cv-sim' : ' cv-nao';
    const chip = el('span', {class: classe, texto: s.skill});
    chip.title = s.evidencia || '';
    return chip;
  }
  for (const s of semGrupo) chipsContainer.appendChild(chipDeSkill(s));
  for (const membros of grupos.values()){
    const grupoDiv = el('span', {class:'grupo-chips'});
    grupoDiv.appendChild(el('span', {class:'rotulo-grupo', texto:'um destes:'}));
    for (const m of membros) grupoDiv.appendChild(chipDeSkill(m));
    chipsContainer.appendChild(grupoDiv);
  }
  card.appendChild(chipsContainer);

  const rotulosSecao = {descricao:'Descrição', responsabilidades:'Responsabilidades', requisitos:'Requisitos',
    diferenciais:'Diferenciais', beneficios:'Benefícios', sobre_empresa:'Sobre a empresa'};
  for (const [chave, rotulo] of Object.entries(rotulosSecao)){
    if (v.secoes && v.secoes[chave]){
      const det = el('details');
      det.appendChild(el('summary', {texto: rotulo}));
      det.appendChild(el('p', {texto: v.secoes[chave]}));
      card.appendChild(det);
    }
  }

  if (v.url) card.appendChild(el('a', {class:'link-vaga', href: v.url, target:'_blank', rel:'noopener', texto:'Ver vaga original →'}));
  if (DADOS.privado && DADOS.app_viva){
    card.appendChild(document.createTextNode(' '));
    card.appendChild(el('a', {class:'link-vaga', href: '/privado/vaga/' + v.id + '/editar', texto:'✎ Editar campos'}));
  }

  if (DADOS.privado){
    if (DADOS.app_viva){
      const form = el('form', {class:'form-status', method:'post', action:'/privado/vaga/' + v.id + '/atualizar'});
      const select = el('select', {name:'status'});
      for (const opcao of ['novo','interessado','aplicado','entrevista','oferta','recusado','arquivada']){
        const opt = el('option', {value: opcao, texto: opcao});
        if ((v.status || 'novo') === opcao) opt.selected = true;
        select.appendChild(opt);
      }
      const textarea = el('textarea', {name:'nota', placeholder:'notas sobre esta vaga...'});
      textarea.value = v.notas || '';
      const botao = el('button', {type:'submit', texto:'Salvar status/notas'});
      form.appendChild(select); form.appendChild(textarea); form.appendChild(botao);
      card.appendChild(form);
    } else {
      card.appendChild(el('div', {class:'barrinha-status', texto:'Status: ' + (v.status || 'novo')}));
      if (v.notas) card.appendChild(el('div', {class:'notas-caixa', texto: v.notas}));
    }
  }

  return card;
}


const ORDEM_TABELA = {campo: 'data', direcao: -1};

function renderTabelaVagas(vagas){
  const container = document.getElementById('tabela-vagas-container');
  container.innerHTML = '';
  if (!vagas.length){ container.appendChild(el('p', {class:'vazio', texto:'Nenhuma vaga com esses filtros.'})); return; }

  const colunas = [
    {campo:'titulo', rotulo:'Título'}, {campo:'empresa', rotulo:'Empresa'},
    {campo:'modalidade', rotulo:'Modalidade'}, {campo:'senioridade', rotulo:'Senioridade'},
    {campo:'mercado', rotulo:'Mercado'}, {campo:'data', rotulo:'Data'},
  ];
  if (DADOS.privado) colunas.push({campo:'match', rotulo:'Match'}, {campo:'status', rotulo:'Status'});

  const ordenadas = [...vagas].sort((a,b) => {
    const campo = ORDEM_TABELA.campo;
    let va = a[campo], vb = b[campo];
    if (campo === 'match'){ va = va ?? -1; vb = vb ?? -1; }
    va = va ?? ''; vb = vb ?? '';
    if (va < vb) return -1 * ORDEM_TABELA.direcao;
    if (va > vb) return 1 * ORDEM_TABELA.direcao;
    return 0;
  });

  const tabela = el('table', {class:'tabela-vagas'});
  const cabecalho = el('tr');
  for (const col of colunas){
    const th = el('th', {class:'ordenavel', texto: col.rotulo + (ORDEM_TABELA.campo === col.campo ? (ORDEM_TABELA.direcao === 1 ? ' ▲' : ' ▼') : '')});
    th.addEventListener('click', () => {
      if (ORDEM_TABELA.campo === col.campo) ORDEM_TABELA.direcao *= -1;
      else { ORDEM_TABELA.campo = col.campo; ORDEM_TABELA.direcao = 1; }
      renderTabelaVagas(vagas);
    });
    cabecalho.appendChild(th);
  }
  cabecalho.appendChild(el('th', {texto:''}));
  const thead = el('thead'); thead.appendChild(cabecalho); tabela.appendChild(thead);

  const tbody = el('tbody');
  for (const v of ordenadas){
    const tr = el('tr');
    tr.appendChild(el('td', {texto: v.titulo || '(sem título)'}));
    tr.appendChild(el('td', {texto: v.empresa || 'não divulgada'}));
    tr.appendChild(el('td', {texto: v.modalidade || '—'}));
    tr.appendChild(el('td', {texto: v.senioridade || '—'}));
    tr.appendChild(el('td', {texto: v.mercado || '—'}));
    tr.appendChild(el('td', {texto: (v.data || '—') + (v.data_estimada ? ' (est.)' : '')}));
    if (DADOS.privado){
      tr.appendChild(el('td', {texto: typeof v.match === 'number' ? formatarPct(v.match) : 'n/d'}));
      tr.appendChild(el('td', {texto: v.status || 'novo'}));
    }
    const tdLink = el('td');
    if (v.url) tdLink.appendChild(el('a', {class:'link-vaga', href: v.url, target:'_blank', rel:'noopener', texto:'abrir →'}));
    tr.appendChild(tdLink);
    tbody.appendChild(tr);
  }
  tabela.appendChild(tbody);
  container.appendChild(tabela);
}

function aplicarFiltrosVagas(){
  const busca = document.getElementById('f-busca').value.trim().toLowerCase();
  const senioridade = document.getElementById('f-senioridade').value;
  const modalidade = document.getElementById('f-modalidade').value;
  const contrato = document.getElementById('f-contrato').value;
  const vinculo = document.getElementById('f-vinculo').value;
  const familia = document.getElementById('f-familia').value;
  const skill = document.getElementById('f-skill').value;
  const restricao = document.getElementById('f-restricao').value;
  const soElegiveis = DADOS.privado && document.getElementById('f-so-elegiveis').checked;

  let vagas = vagasDoRecorte(recorteAtual);
  if (busca) vagas = vagas.filter(v => ((v.titulo||'') + ' ' + (v.empresa||'')).toLowerCase().includes(busca));
  if (senioridade) vagas = vagas.filter(v => v.senioridade === senioridade);
  if (modalidade) vagas = vagas.filter(v => v.modalidade === modalidade);
  if (contrato) vagas = vagas.filter(v => v.contrato === contrato);
  if (vinculo) vagas = vagas.filter(v => v.tipo_vinculo === vinculo);
  if (familia) vagas = vagas.filter(v => v.familia_cargo === familia);
  if (skill) vagas = vagas.filter(v => v.skills.some(s => s.skill === skill));
  if (restricao) vagas = vagas.filter(v => tipoRestricao(v) === restricao);
  if (soElegiveis) vagas = vagas.filter(v => v.elegivel !== 'nao');

  document.getElementById('contador-vagas').textContent = vagas.length + ' vaga(s) encontrada(s).';

  const lista = document.getElementById('lista-vagas');
  lista.innerHTML = '';
  if (!vagas.length) lista.appendChild(el('p', {class:'vazio', texto:'Nenhuma vaga com esses filtros.'}));
  else for (const v of vagas) lista.appendChild(renderCardVaga(v));

  renderTabelaVagas(vagas);
}

function alternarVisualizacao(modo){
  document.getElementById('lista-vagas').hidden = modo !== 'cards';
  document.getElementById('tabela-vagas-container').hidden = modo !== 'tabela';
  for (const btn of document.querySelectorAll('.alternador-visualizacao button')){
    btn.classList.toggle('ativo', btn.dataset.vis === modo);
  }
}

for (const btn of document.querySelectorAll('.alternador-visualizacao button')){
  btn.addEventListener('click', () => alternarVisualizacao(btn.dataset.vis));
}

function renderMeuCv(){
  if (!DADOS.privado || !DADOS.meu_cv) return;
  document.getElementById('aba-meu-cv').hidden = false;
  const cv = DADOS.meu_cv;

  const lacunasCont = document.getElementById('cv-lacunas');
  lacunasCont.innerHTML = '';
  if (!cv.cv_utilizavel) lacunasCont.appendChild(el('p', {class:'vazio', texto:'CV não utilizável (texto muito curto).'}));
  else if (!cv.lacunas.length) lacunasCont.appendChild(el('p', {class:'vazio', texto:'Nenhuma lacuna identificada.'}));
  else {
    const tabela = el('table');
    tabela.innerHTML = '<tr><th>Skill</th><th>score_lacuna</th><th>Prioridade</th></tr>' +
      cv.lacunas.slice(0,20).map(l => '<tr><td>'+l.skill+'</td><td>'+l.score_lacuna.toFixed(2)+'</td><td>'+l.prioridade+'</td></tr>').join('');
    lacunasCont.appendChild(tabela);
  }

  const planoCont = document.getElementById('cv-plano');
  planoCont.innerHTML = '';
  const porCategoria = new Map();
  for (const l of cv.lacunas || []){
    if (!porCategoria.has(l.categoria)) porCategoria.set(l.categoria, []);
    porCategoria.get(l.categoria).push(l);
  }
  if (!porCategoria.size) planoCont.appendChild(el('p', {class:'vazio', texto:'Sem plano — nenhuma lacuna.'}));
  for (const [categoria, itens] of porCategoria){
    const p = el('p');
    p.appendChild(el('strong', {texto: categoria}));
    p.appendChild(document.createTextNode(': ' + itens.map(i => i.skill + ' (' + i.prioridade + ')').join(', ')));
    planoCont.appendChild(p);
  }

  const evolCont = document.getElementById('cv-evolucao');
  evolCont.innerHTML = '';
  const entradas = (cv.historico || []).filter(h => h.recorte === 'todos').sort((a,b)=> a.data.localeCompare(b.data));
  if (!entradas.length){ evolCont.appendChild(el('p', {class:'vazio', texto:'Sem histórico ainda.'})); }
  else {
    renderGraficoLinha(evolCont, entradas, 'cobertura_geral');
    const tabela = el('table');
    tabela.innerHTML = '<tr><th>Data</th><th>Vagas ativas</th><th>Cobertura geral</th></tr>' +
      entradas.map(h => '<tr><td>'+h.data+'</td><td>'+h.n_vagas_ativas+'</td><td>'+formatarPct(h.cobertura_geral)+'</td></tr>').join('');
    evolCont.appendChild(tabela);
  }
}

function renderGraficoLinha(container, entradas, campo){
  const pontos = entradas.filter(e => e[campo] !== null && e[campo] !== undefined);
  if (pontos.length < 2){
    container.appendChild(el('p', {class:'vazio', texto:'Pontos insuficientes para o gráfico (mínimo 2 dias com dado).'}));
    return;
  }
  const largura = 560, altura = 160, margem = 28;
  const valores = pontos.map(p => p[campo]);
  const minV = Math.min(...valores, 0);
  const maxV = Math.max(...valores, minV + 0.01);
  const passoX = (largura - margem * 2) / (pontos.length - 1);
  const escalaY = v => altura - margem - ((v - minV) / (maxV - minV)) * (altura - margem * 2);
  const coords = pontos.map((p, i) => [margem + i * passoX, escalaY(p[campo])]);

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + largura + ' ' + altura);
  svg.setAttribute('class', 'grafico-linha');

  const eixo = document.createElementNS(svgNS, 'line');
  eixo.setAttribute('x1', margem); eixo.setAttribute('x2', largura - margem);
  eixo.setAttribute('y1', altura - margem); eixo.setAttribute('y2', altura - margem);
  eixo.setAttribute('class', 'eixo');
  svg.appendChild(eixo);

  const linha = document.createElementNS(svgNS, 'polyline');
  linha.setAttribute('points', coords.map(c => c.join(',')).join(' '));
  linha.setAttribute('class', 'linha');
  svg.appendChild(linha);

  coords.forEach(([x, y], i) => {
    const ponto = document.createElementNS(svgNS, 'circle');
    ponto.setAttribute('cx', x); ponto.setAttribute('cy', y); ponto.setAttribute('r', 3);
    ponto.setAttribute('class', 'ponto');
    const tituloEl = document.createElementNS(svgNS, 'title');
    tituloEl.textContent = pontos[i].data + ': ' + formatarPct(pontos[i][campo]);
    ponto.appendChild(tituloEl);
    svg.appendChild(ponto);
  });

  const txtInicio = document.createElementNS(svgNS, 'text');
  txtInicio.setAttribute('x', margem); txtInicio.setAttribute('y', altura - 8); txtInicio.setAttribute('text-anchor', 'start');
  txtInicio.textContent = pontos[0].data;
  svg.appendChild(txtInicio);

  const txtFim = document.createElementNS(svgNS, 'text');
  txtFim.setAttribute('x', largura - margem); txtFim.setAttribute('y', altura - 8); txtFim.setAttribute('text-anchor', 'end');
  txtFim.textContent = pontos[pontos.length - 1].data;
  svg.appendChild(txtFim);

  container.appendChild(svg);
}

function montarSeletorRecorte(){
  const cont = document.getElementById('seletor-recorte');
  const recortes = [['BR','BR'], ['INT_acessivel','INT acessível'], ['INT_restrito','INT restrito'], ['todos','Todos']];
  for (const [valor, rotulo] of recortes){
    const btn = el('button', {texto: rotulo});
    if (valor === recorteAtual) btn.classList.add('ativo');
    btn.addEventListener('click', () => {
      recorteAtual = valor;
      for (const b of cont.querySelectorAll('button')) b.classList.remove('ativo');
      btn.classList.add('ativo');
      renderPainel();
      aplicarFiltrosVagas();
    });
    cont.appendChild(btn);
  }
}

function trocarAba(nome){
  for (const sec of document.querySelectorAll('section.pagina')) sec.classList.remove('ativa');
  document.getElementById('pagina-' + nome).classList.add('ativa');
  for (const btn of document.querySelectorAll('nav.abas button')) btn.classList.remove('ativa');
  document.querySelector('nav.abas button[data-pagina="' + nome + '"]').classList.add('ativa');
}

for (const btn of document.querySelectorAll('nav.abas button')){
  btn.addEventListener('click', () => trocarAba(btn.dataset.pagina));
}

if (DADOS.privado) document.getElementById('rotulo-so-elegiveis').hidden = false;
if (DADOS.privado && DADOS.app_viva) document.getElementById('acoes-app-viva').hidden = false;

if (DADOS.app_viva){
  const siteNav = document.getElementById('site-nav');
  siteNav.hidden = false;
  const caminhoAtual = window.location.pathname;
  const hashAtual = window.location.hash;
  let melhorMatch = null;
  for (const a of siteNav.querySelectorAll('a')){
    const url = new URL(a.getAttribute('href'), window.location.origin);
    if (url.pathname !== caminhoAtual) continue;
    // prefere o item cujo hash bate exatamente; sem hash, cai no item "base" da página (ex.: Painel público/privado).
    if (url.hash === hashAtual) { melhorMatch = a; break; }
    if (!url.hash && !melhorMatch) melhorMatch = a;
  }
  if (melhorMatch) melhorMatch.classList.add('atual');

  if (hashAtual === '#vagas' && document.getElementById('pagina-vagas')) trocarAba('vagas');
  else if (hashAtual === '#meu-cv' && document.getElementById('pagina-meu-cv')) trocarAba('meu-cv');
}

montarSeletorRecorte();
construirListasDeFiltro();
renderPainel();
renderComparacaoBrInt();
renderComparacaoFamilias();
renderTendencia();
renderQualidadeDados();
aplicarFiltrosVagas();
renderMeuCv();

for (const idCampo of ['f-busca','f-senioridade','f-modalidade','f-contrato','f-vinculo','f-familia','f-skill','f-restricao','f-so-elegiveis']){
  const elemento = document.getElementById(idCampo);
  elemento.addEventListener('input', aplicarFiltrosVagas);
  elemento.addEventListener('change', aplicarFiltrosVagas);
}
</script>
</body>
</html>
"""


def gerar_html(payload: dict, titulo: str) -> str:
    dados_json = _embutir_json(payload)
    return _TEMPLATE.replace("__DADOS_JSON__", dados_json).replace("__TITULO__", titulo)
