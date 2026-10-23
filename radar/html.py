"""Geração dos dois HTML estáticos (seção Fase 4): docs/index.html (público)
e privado/index.html (privado). Um único template compartilhado — o que
muda entre os dois é o payload JSON embutido (campo "privado": bool) e,
client-side, quais seções a página mostra."""

from __future__ import annotations

import html as html_lib
import json
import re

from radar import estilo

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


def _salario_payload(salario: dict | None) -> dict | None:
    if not isinstance(salario, dict):
        return None
    if salario.get("min") is None and salario.get("max") is None:
        return None
    return {k: salario.get(k) for k in ("min", "max", "moeda", "periodo")}


def _anos_payload(anos: dict | None) -> dict | None:
    if not isinstance(anos, dict):
        return None
    return {k: anos.get(k) for k in ("min", "max")}


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
        # salário e anos de experiência vêm do próprio anúncio (já públicos) —
        # o gráfico de faixas salariais do painel lia v.salario, que nunca
        # chegava ao payload.
        "salario": _salario_payload(vaga.get("salario")),
        "anos_experiencia": _anos_payload(vaga.get("anos_experiencia")),
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
__ESTILO_BASE__
section.pagina{display:none}
section.pagina.ativa{display:flex;flex-direction:column;gap:22px}
.filtros{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:12px;padding:16px;
  border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}
.filtros label{display:flex;flex-direction:column;gap:6px;font-size:12.5px;color:var(--muted);min-width:0}
.filtros .busca{grid-column:span 2}
@media (max-width:520px){.filtros .busca{grid-column:auto}}
.filtros .check{color:var(--fg);align-self:end}
.barra-ferramentas{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px}
.lista-vagas{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr));gap:16px}
.vaga{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;
  display:flex;flex-direction:column;gap:12px;min-width:0}
.vaga:hover{border-color:var(--border-strong)}
.vaga-topo{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}
.vaga h3{font-size:16px;font-weight:600}
.vaga .empresa{margin:4px 0 0;font-size:13.5px;color:var(--fg-2)}
.match{flex:0 0 auto;display:flex;flex-direction:column;align-items:center;width:68px;padding:8px 0;border-radius:10px;
  background:var(--surface-2);border:1px solid var(--border)}
.match strong{font-family:var(--mono);font-size:20px;font-weight:500}
.match small{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.match.alto strong{color:var(--accent)} .match.medio strong{color:var(--warn)} .match.baixo strong{color:var(--danger)}
.linha-estado{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.motivo{font-size:13px;color:var(--muted);margin:0}
details{border-top:1px solid var(--border);padding-top:8px}
details summary{cursor:pointer;font-size:13.5px;color:var(--fg-2);min-height:28px}
details p{white-space:pre-wrap;margin:6px 0 4px;font-size:13.5px;color:var(--fg-2)}
.vaga-acoes{display:flex;flex-wrap:wrap;gap:8px;padding-top:4px}
.form-status{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;padding-top:12px;border-top:1px solid var(--border)}
.form-status textarea{grid-column:1/-1;min-height:60px}
.notas-caixa{background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:8px 10px;font-size:13px}
.tabela-caixa{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:14px}
th{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 14px;text-align:left;font-family:var(--mono);
  font-size:11px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
th.ordenavel{cursor:pointer} th.ordenavel:hover{color:var(--fg)}
td{border-bottom:1px solid var(--border);padding:12px 14px;text-align:left;vertical-align:middle}
tbody tr:hover{background:var(--surface-2)}
tbody tr:last-child td{border-bottom:0}
.td-titulo strong{display:block;font-weight:500}
.td-titulo span{font-size:12.5px;color:var(--muted)}
.mini-match{display:flex;align-items:center;gap:8px;min-width:120px}
.mini-match .trilha{flex:1;height:6px}
.mini-match span{font-family:var(--mono);font-size:12.5px;min-width:36px;text-align:right}
.comparacao{display:flex;flex-direction:column;gap:14px}
.comparacao .linha{display:flex;flex-direction:column;gap:5px}
.comparacao .topo{display:flex;justify-content:space-between;gap:8px;font-size:14px}
.comparacao .topo span:last-child{font-family:var(--mono);font-size:12.5px;color:var(--muted)}
.comparacao .trilha{height:6px}
.familias{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px}
.familia{display:flex;flex-direction:column;gap:10px;padding:14px;border-radius:10px;background:var(--surface-2);border:1px solid var(--border)}
.familia .topo{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.familia strong{font-size:14px}
.familia .n{font-family:var(--mono);font-size:12.5px;color:var(--muted)}
.salario{display:flex;flex-direction:column;gap:6px}
.salario .topo{display:flex;justify-content:space-between;gap:8px;font-size:14px}
.salario .topo span:last-child{font-family:var(--mono);font-size:12.5px;color:var(--fg-2)}
.salario .marca-mediana{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--fg);border-radius:1px}
.salario .trilha{overflow:visible}
.kanban-caixa{overflow-x:auto;padding-bottom:8px}
.kanban{display:grid;grid-template-columns:repeat(6,minmax(230px,1fr));gap:14px;min-width:1440px}
.coluna{display:flex;flex-direction:column;gap:10px;padding:12px;border-radius:var(--radius);background:var(--surface-2);
  border:1px solid var(--border);min-height:420px}
.coluna-topo{display:flex;align-items:center;gap:8px;padding:2px 4px 10px;border-bottom:2px solid currentColor}
.coluna-topo strong{font-size:14px;color:var(--fg);text-transform:capitalize}
.coluna-topo span{margin-left:auto;font-family:var(--mono);font-size:13px;color:var(--muted)}
.cartao{display:flex;flex-direction:column;gap:8px;padding:14px;border-radius:10px;background:var(--surface);border:1px solid var(--border)}
.cartao h3{font-size:14px;font-weight:600;line-height:1.3}
.cartao .empresa{font-size:13px;color:var(--fg-2);margin:0}
.cartao .topo{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.cartao .topo .m{font-family:var(--mono)}
.cartao-acoes{display:flex;gap:6px}
.cartao-acoes form{margin:0;display:flex}
.cartao-acoes form:last-child{flex:1}
.cartao-acoes form:last-child button{flex:1}
.mais-cartoes{font-size:12.5px;color:var(--muted);text-align:center;padding:6px}
.grafico-linha{width:100%;height:auto}
.grafico-linha .eixo{stroke:var(--border-strong);stroke-width:1}
.grafico-linha .linha{fill:none;stroke:var(--accent);stroke-width:2.5}
.grafico-linha .ponto{fill:var(--accent)}
.grafico-linha text{fill:var(--muted);font-size:10px;font-family:var(--mono)}
.plano{display:flex;flex-direction:column;gap:10px}
.plano-item{display:flex;flex-direction:column;gap:8px;padding:14px;border-radius:10px;background:var(--surface-2);border:1px solid var(--border)}
.plano-item .topo{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.plano-item strong{font-size:14px}
.prio{font-family:var(--mono);font-size:12px}
.prio.alta{color:var(--danger-fg)} .prio.media{color:var(--warn-fg)} .prio.baixa{color:var(--muted)}
</style>
</head>
<body>
<div class="app">
__LATERAL__
<main class="conteudo">

<section class="pagina ativa" id="pagina-painel" aria-labelledby="titulo-painel">
  <header class="cabecalho-pagina">
    <div class="titulos">
      <div class="olho">~/painel</div>
      <h1 id="titulo-painel">__TITULO__</h1>
      <p id="subtitulo"></p>
    </div>
    <div class="acoes" id="acoes-app-viva" hidden>
      <form method="post" action="/acoes/coletar"><button class="btn" type="submit">__ICONE_BAIXAR__Coletar vagas novas</button></form>
      <form method="post" action="/acoes/analisar"><button class="btn" type="submit">__ICONE_RECARREGAR__Recalcular análise/CV</button></form>
      <a class="btn btn-primario" href="/adicionar">__ICONE_MAIS__Adicionar vaga</a>
    </div>
  </header>
  <div class="seg" id="seletor-recorte" role="group" aria-label="Recorte de mercado"></div>
  <div class="kpis" id="kpis-executivos"></div>
  <div class="grade" id="grade-painel"></div>
  <div class="grade">
    <div class="card">
      <div class="card-topo">
        <h2>BR × Internacional</h2>
        <div class="legenda"><span><i style="background:var(--info)"></i>BR</span><span><i style="background:var(--neutral)"></i>INT</span></div>
      </div>
      <p class="sub">Skills com a maior diferença de frequência entre os dois mercados</p>
      <div id="comparacao-br-int"></div>
    </div>
    <div class="card">
      <h2>Por família de cargo</h2>
      <div id="comparacao-familias"></div>
    </div>
  </div>
</section>

<section class="pagina" id="pagina-vagas" aria-labelledby="titulo-vagas">
  <header class="cabecalho-pagina">
    <div class="titulos">
      <div class="olho">~/vagas</div>
      <h1 id="titulo-vagas">Vagas</h1>
      <p id="contador-vagas"></p>
    </div>
    <div class="acoes" id="acoes-vagas-app-viva" hidden>
      <a class="btn btn-primario" href="/adicionar">__ICONE_MAIS__Adicionar vaga</a>
    </div>
  </header>
  <div class="filtros">
    <label class="busca">Busca<input type="search" id="f-busca" placeholder="título, empresa ou skill"></label>
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
    <label id="rotulo-status" hidden>Status<select id="f-status"><option value="">Todos</option></select></label>
    <label class="check" id="rotulo-so-elegiveis" hidden><input type="checkbox" id="f-so-elegiveis"> Só elegíveis</label>
  </div>
  <div class="barra-ferramentas">
    <div class="seg alternador-visualizacao" role="group" aria-label="Visualização">
      <button type="button" data-vis="cards" class="ativo" aria-pressed="true">Cards</button>
      <button type="button" data-vis="tabela" aria-pressed="false">Tabela</button>
    </div>
    <label class="campo" style="flex-direction:row;align-items:center;gap:8px"><span>Ordenar</span>
      <select id="f-ordem" style="width:auto">
        <option value="data">Mais recentes</option>
        <option value="match" id="opcao-ordem-match" hidden>Maior match</option>
        <option value="titulo">Título (A–Z)</option>
      </select>
    </label>
  </div>
  <div class="lista-vagas" id="lista-vagas"></div>
  <div id="tabela-vagas-container" hidden></div>
</section>

<section class="pagina" id="pagina-pipeline" aria-labelledby="titulo-pipeline">
  <header class="cabecalho-pagina">
    <div class="titulos">
      <div class="olho">~/pipeline</div>
      <h1 id="titulo-pipeline">Pipeline de candidatura</h1>
      <p id="resumo-pipeline"></p>
    </div>
  </header>
  <div class="kanban-caixa"><div class="kanban" id="kanban"></div></div>
</section>

<section class="pagina" id="pagina-meu-cv" aria-labelledby="titulo-meu-cv">
  <header class="cabecalho-pagina">
    <div class="titulos">
      <div class="olho">~/meu-cv</div>
      <h1 id="titulo-meu-cv">Meu CV × mercado</h1>
      <p>O que falta no seu currículo, priorizado pela frequência nas vagas</p>
    </div>
  </header>
  <div class="grade">
    <div class="card">
      <div class="card-topo"><h2>Lacunas priorizadas</h2><div class="legenda"><span><i style="background:var(--warn)"></i>score de lacuna</span></div></div>
      <div id="cv-lacunas"></div>
    </div>
    <div class="card">
      <h2>Plano de estudo</h2>
      <div id="cv-plano"></div>
    </div>
  </div>
  <div class="card">
    <h2>Evolução da cobertura <span class="muted" style="font-weight:400">· recorte todos</span></h2>
    <div id="cv-evolucao"></div>
  </div>
</section>

<footer class="rodape">Gerado em <span id="gerado-em"></span> · Radar de Vagas</footer>
</main>
</div>

<script type="application/json" id="dados-radar">__DADOS_JSON__</script>
<script>
const DADOS = JSON.parse(document.getElementById('dados-radar').textContent);
const PESOS = {obrigatorio: 1.0, mencionado: 0.6, diferencial: 0.4};
const ETAPAS = ['novo','interessado','aplicado','entrevista','oferta','recusado'];
const STATUS_TODOS = ETAPAS.concat(['arquivada']);

document.getElementById('subtitulo').textContent = DADOS.privado
  ? 'Painel privado — match com seu CV, elegibilidade, status e notas.'
  : 'Mercado de Red Team, Pentest e Segurança Ofensiva.';
document.getElementById('gerado-em').textContent = DADOS.gerado_em || '';

let recorteAtual = 'todos';

function vagasDoRecorte(recorte){
  if (recorte === 'BR') return DADOS.vagas.filter(v => v.mercado === 'BR');
  if (recorte === 'INT_acessivel') return DADOS.vagas.filter(v => v.recorte_int === 'acessivel');
  if (recorte === 'INT_restrito') return DADOS.vagas.filter(v => v.recorte_int === 'restrito');
  return DADOS.vagas;
}

function rankingSkills(vagas){
  const soma = new Map(), vagasPorSkill = new Map(), noCv = new Map();
  for (const v of vagas){
    for (const s of v.skills){
      const chave = s.categoria + '||' + s.skill;
      soma.set(chave, (soma.get(chave)||0) + s.peso);
      if (!vagasPorSkill.has(chave)) vagasPorSkill.set(chave, new Set());
      vagasPorSkill.get(chave).add(v.id);
      if (s.no_cv) noCv.set(chave, true);
    }
  }
  const n = vagas.length;
  const linhas = [];
  for (const [chave, s] of soma){
    const [categoria, skill] = chave.split('||');
    const nVagas = vagasPorSkill.get(chave).size;
    linhas.push({categoria, skill, nVagas, percentual: n ? nVagas/n : null, score: n ? s/n : null, noCv: !!noCv.get(chave)});
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
    const nVagas = vagasPorCat.get(categoria).size;
    linhas.push({categoria, score: n ? s/n : null, nVagas, percentual: n ? nVagas/n : null});
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
    const chave = (moeda || '?') + '||' + (periodo || '?');
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
  return linhas.sort((a,b)=> b.n - a.n);
}

function formatarPct(v){ return (v===null||v===undefined) ? 'n/d' : Math.round(v*100) + '%'; }
function formatarNum(v){ return Math.round(v).toLocaleString('pt-BR'); }
function el(tag, props={}, filhos=[]){
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(props)){
    if (v === null || v === undefined || v === false) continue;
    if (k === 'texto') e.textContent = v; else e.setAttribute(k, v === true ? '' : v);
  }
  for (const f of filhos) if (f) e.appendChild(typeof f === 'string' ? document.createTextNode(f) : f);
  return e;
}
function trilha(pct, classe, extraEstilo){
  const t = el('span', {class:'trilha'});
  const f = el('span', {class:'fill ' + (classe||'')});
  f.style.width = Math.max(0, Math.min(100, pct)) + '%';
  if (extraEstilo) Object.assign(f.style, extraEstilo);
  t.appendChild(f);
  return t;
}
function card(titulo, sub){
  const c = el('div', {class:'card'});
  const topo = el('div', {class:'card-topo'}, [el('h2', {texto: titulo})]);
  c.appendChild(topo);
  if (sub) c.appendChild(el('p', {class:'sub', texto: sub}));
  return c;
}
function classeMatch(m){ return m >= 0.7 ? 'alto' : (m >= 0.45 ? 'medio' : 'baixo'); }
function pillStatus(status){ return el('span', {class:'pill', 'data-status': status, texto: status}); }
const ROTULO_ELEG = {sim:'sim', nao:'não', talvez:'talvez'};
function pillEleg(eleg){ return el('span', {class:'pill eleg-' + eleg, texto: 'elegível: ' + (ROTULO_ELEG[eleg] || eleg)}); }

function renderBarras(container, linhas, rotuloFn, max, classeFn){
  container.innerHTML = '';
  const lista = el('div', {class:'barras'});
  const maiorScore = Math.max(...linhas.slice(0,max).map(l=>l.score||0), 0.0001);
  for (const linha of linhas.slice(0, max)){
    lista.appendChild(el('div', {class:'barra'}, [
      el('span', {class:'nome', texto: rotuloFn(linha), title: rotuloFn(linha)}),
      trilha(Math.max(2, Math.round(((linha.score||0)/maiorScore)*100)), classeFn ? classeFn(linha) : ''),
      el('span', {class:'valor', texto: linha.nVagas + ' · ' + formatarPct(linha.percentual)}),
    ]));
  }
  container.appendChild(lista);
  if (!linhas.length) container.appendChild(el('p', {class:'vazio', texto:'Sem dados neste recorte.'}));
}

const ROTULO_RECORTE = {BR:'BR', INT_acessivel:'INT acessível', INT_restrito:'INT restrito', todos:'todos'};

function renderKpis(vagas){
  const cont = document.getElementById('kpis-executivos');
  cont.innerHTML = '';

  function tile(rotulo, valor, nota, destaque, href){
    const filhos = [el('div', {class:'kpi-rotulo', texto: rotulo}), el('div', {class:'kpi-valor', texto: valor, title: valor})];
    if (nota) filhos.push(el('div', {class:'kpi-nota', texto: nota}));
    cont.appendChild(el(href ? 'a' : 'div', {class: 'kpi' + (destaque ? ' destaque' : ''), href: href || null}, filhos));
  }

  tile('Vagas ativas', String(vagas.length), 'recorte: ' + ROTULO_RECORTE[recorteAtual], false);

  const remoto = distribuicao(vagas, 'modalidade').find(d => d.valor === 'remoto');
  tile('Remoto', remoto ? formatarPct(remoto.percentual) : 'n/d',
    remoto ? remoto.n + ' de ' + vagas.length + ' vaga(s)' : 'sem dados', false);

  const ranking = rankingSkills(vagas);
  tile('Skill #1', ranking.length ? ranking[0].skill : '—',
    ranking.length ? 'em ' + formatarPct(ranking[0].percentual) + ' das vagas' : 'sem dados', false);

  if (DADOS.privado){
    const coberturaAtual = (DADOS.cobertura_por_recorte || {})[recorteAtual];
    tile('Cobertura do CV', formatarPct(coberturaAtual), 'skills do mercado no seu CV', true);
    if (DADOS.score_perfil){
      tile('Score de perfil', DADOS.score_perfil.score + '/100',
        DADOS.score_perfil.classificacao + ' · referência 50+', true, DADOS.app_viva ? '/perfil-profissional' : null);
    }
    const lacunasAltas = ((DADOS.meu_cv || {}).lacunas || []).filter(l => l.prioridade === 'alta').length;
    tile('Lacunas altas', String(lacunasAltas), 'veja Meu CV', lacunasAltas > 0, '#meu-cv');
  }
}

function renderPainel(){
  const vagas = vagasDoRecorte(recorteAtual);
  const grade = document.getElementById('grade-painel');
  grade.innerHTML = '';
  renderKpis(vagas);

  const skillsCard = card('Top 15 skills', 'Peso ponderado: obrigatório > mencionado > diferencial');
  if (DADOS.privado){
    skillsCard.firstChild.appendChild(el('div', {class:'legenda'}, [
      el('span', {}, [el('i', {style:'background:var(--accent)'}), 'no seu CV']),
      el('span', {}, [el('i', {style:'background:var(--warn)'}), 'lacuna']),
    ]));
  }
  const divSkills = el('div'); skillsCard.appendChild(divSkills);
  renderBarras(divSkills, rankingSkills(vagas), l => l.skill, 15, DADOS.privado ? (l => l.noCv ? 'ok' : 'falta') : null);
  grade.appendChild(skillsCard);

  const catCard = card('Categorias');
  const divCat = el('div'); catCard.appendChild(divCat);
  renderBarras(divCat, rankingCategorias(vagas), l => l.categoria, 10, () => 'info');
  grade.appendChild(catCard);

  const salCard = card('Faixas salariais', 'Na moeda original do anúncio, sem conversão · traço = mediana');
  const faixas = faixasSalariais(vagas);
  const listaSal = el('div', {class:'barras'});
  if (!faixas.length) listaSal.appendChild(el('p', {class:'vazio', texto:'Sem dados de salário neste recorte.'}));
  for (const f of faixas){
    const teto = f.max * 1.08 || 1;
    const t = trilha(((f.max - f.min) / teto) * 100, 'ok', {left: (f.min / teto * 100) + '%'});
    const marca = el('span', {class:'marca-mediana'}); marca.style.left = (f.mediana / teto * 100) + '%';
    t.appendChild(marca);
    listaSal.appendChild(el('div', {class:'salario'}, [
      el('div', {class:'topo'}, [
        el('span', {texto: f.moeda + ' · ' + f.periodo + ' (' + f.n + ')'}),
        el('span', {texto: formatarNum(f.min) + ' – ' + formatarNum(f.max) + ' · med. ' + formatarNum(f.mediana)}),
      ]),
      t,
    ]));
  }
  salCard.appendChild(listaSal);
  grade.appendChild(salCard);

  const perfilCard = card('Perfil das vagas');
  for (const [campo, titulo] of [['senioridade','Senioridade'], ['modalidade','Modalidade'], ['tipo_vinculo','Vínculo']]){
    const bloco = el('div', {class:'barras'});
    bloco.appendChild(el('div', {class:'rotulo-secao', texto: titulo}));
    const dist = distribuicao(vagas, campo);
    if (!dist.length) bloco.appendChild(el('p', {class:'vazio', texto:'Sem dados.'}));
    for (const d of dist.slice(0, 6)){
      bloco.appendChild(el('div', {class:'barra'}, [
        el('span', {class:'nome', texto: d.valor}), trilha(d.percentual*100, 'neutro'),
        el('span', {class:'valor', texto: d.n + ' · ' + formatarPct(d.percentual)}),
      ]));
    }
    perfilCard.appendChild(bloco);
  }
  grade.appendChild(perfilCard);
}

function renderComparacaoBrInt(){
  const cont = document.getElementById('comparacao-br-int');
  cont.innerHTML = '';
  const dados = (DADOS.comparacao_br_int || []).slice(0, 8);
  if (!dados.length){ cont.appendChild(el('p', {class:'vazio', texto:'Sem dados suficientes.'})); return; }
  const lista = el('div', {class:'comparacao'});
  for (const d of dados){
    lista.appendChild(el('div', {class:'linha'}, [
      el('div', {class:'topo'}, [el('span', {texto: d.skill}), el('span', {texto: formatarPct(d.br) + ' · ' + formatarPct(d.int)})]),
      trilha((d.br||0)*100, 'info'), trilha((d.int||0)*100, 'neutro'),
    ]));
  }
  cont.appendChild(lista);
}

function renderComparacaoFamilias(){
  const cont = document.getElementById('comparacao-familias');
  cont.innerHTML = '';
  const familias = DADOS.comparacao_familias || {};
  const chaves = Object.keys(familias).sort((a,b)=> familias[b].n_vagas - familias[a].n_vagas);
  if (!chaves.length){ cont.appendChild(el('p', {class:'vazio', texto:'Sem dados.'})); return; }
  const maior = Math.max(...chaves.map(k => familias[k].n_vagas), 1);
  const grade = el('div', {class:'familias'});
  for (const familia of chaves){
    const info = familias[familia];
    const chips = el('div', {class:'chips'});
    for (const s of (info.top_skills||[]).slice(0,5)) chips.appendChild(el('span', {class:'chip', texto: s.skill}));
    grade.appendChild(el('div', {class:'familia'}, [
      el('div', {class:'topo'}, [el('strong', {texto: familia.replace(/_/g, ' ')}), el('span', {class:'n', texto: info.n_vagas + ' vaga(s)'})]),
      trilha(info.n_vagas / maior * 100, 'ok'),
      chips,
    ]));
  }
  cont.appendChild(grade);
}

function popularSelect(id, valores){
  const select = document.getElementById(id);
  for (const v of valores) select.appendChild(el('option', {value: v, texto: v}));
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
  if (DADOS.privado) popularSelect('f-status', STATUS_TODOS);
}

function tipoRestricao(v){
  if (!v.restricoes_chips || !v.restricoes_chips.length) return 'nenhuma';
  const texto = v.restricoes_chips.join(' ');
  if (texto.includes('cidadania')) return 'cidadania';
  if (texto.includes('residência')) return 'residencia';
  if (texto.includes('clearance')) return 'clearance';
  return 'nenhuma';
}

function chipsDeSkills(v){
  const chipsContainer = el('div', {class:'chips'});
  const grupos = new Map();
  function chipDeSkill(s){
    let classe = 'chip';
    if (DADOS.privado) classe += s.no_cv ? ' cv-sim' : ' cv-nao';
    return el('span', {class: classe, texto: s.skill, title: s.evidencia || null});
  }
  for (const s of v.skills){
    if (s.grupo_alternativo){
      if (!grupos.has(s.grupo_alternativo)) grupos.set(s.grupo_alternativo, []);
      grupos.get(s.grupo_alternativo).push(s);
    } else chipsContainer.appendChild(chipDeSkill(s));
  }
  for (const membros of grupos.values()){
    const grupoDiv = el('span', {class:'grupo-chips'}, [el('span', {class:'rotulo-grupo', texto:'um destes:'})]);
    for (const m of membros) grupoDiv.appendChild(chipDeSkill(m));
    chipsContainer.appendChild(grupoDiv);
  }
  return chipsContainer;
}

function chipMeta(k, valor, classe){
  return el('span', {class:'chip' + (classe ? ' ' + classe : '')}, [el('span', {class:'k', texto: k}), ' ' + valor]);
}

function formStatus(v){
  const form = el('form', {class:'form-status', method:'post', action:'/privado/vaga/' + encodeURIComponent(v.id) + '/atualizar'});
  const select = el('select', {name:'status', 'aria-label':'Status da candidatura'});
  for (const opcao of STATUS_TODOS){
    const opt = el('option', {value: opcao, texto: opcao});
    if ((v.status || 'novo') === opcao) opt.selected = true;
    select.appendChild(opt);
  }
  const textarea = el('textarea', {name:'nota', placeholder:'notas sobre esta vaga…', 'aria-label':'Notas'});
  textarea.value = v.notas || '';
  form.appendChild(select);
  form.appendChild(el('button', {type:'submit', class:'btn btn-pequeno', texto:'Salvar'}));
  form.appendChild(textarea);
  return form;
}

function renderCardVaga(v){
  const cardEl = el('article', {class:'vaga'});
  const titulos = el('div', {style:'min-width:0'}, [
    el('h3', {texto: v.titulo || '(sem título)'}),
    el('p', {class:'empresa', texto: (v.empresa || 'empresa não divulgada') + (v.locais && v.locais.length ? ' · ' + v.locais.join(', ') : '')}),
  ]);
  const topo = el('div', {class:'vaga-topo'}, [titulos]);
  if (DADOS.privado && typeof v.match === 'number'){
    topo.appendChild(el('div', {class:'match ' + classeMatch(v.match)}, [el('strong', {texto: formatarPct(v.match)}), el('small', {texto:'match'})]));
  }
  cardEl.appendChild(topo);

  const meta = el('div', {class:'chips'});
  if (v.modalidade) meta.appendChild(chipMeta('modalidade', v.modalidade));
  if (v.senioridade) meta.appendChild(chipMeta('nível', v.senioridade));
  if (v.contrato || v.tipo_vinculo) meta.appendChild(chipMeta('contrato', [v.contrato, v.tipo_vinculo].filter(Boolean).join(' / ')));
  if (v.familia_cargo && v.familia_cargo !== 'outro') meta.appendChild(chipMeta('família', v.familia_cargo.replace(/_/g,' ')));
  if (v.salario) meta.appendChild(chipMeta('salário', (v.salario.moeda||'') + ' ' + [v.salario.min, v.salario.max].filter(x => x !== null && x !== undefined).map(formatarNum).join('–')));
  if (v.data) meta.appendChild(chipMeta('data', v.data + (v.data_estimada ? ' (est.)' : '')));
  if (v.possivelmente_expirada) meta.appendChild(el('span', {class:'chip alerta', texto:'possivelmente expirada'}));
  if (v.modalidade_conflito) meta.appendChild(el('span', {class:'chip alerta', texto:'modalidade conflitante'}));
  for (const c of (v.restricoes_chips || [])) meta.appendChild(el('span', {class:'chip alerta', texto: c}));
  cardEl.appendChild(meta);

  if (DADOS.privado){
    const estado = el('div', {class:'linha-estado'}, [pillStatus(v.status || 'novo')]);
    if (v.elegivel) estado.appendChild(pillEleg(v.elegivel));
    cardEl.appendChild(estado);
    if (v.elegivel_motivos && v.elegivel_motivos.length) cardEl.appendChild(el('p', {class:'motivo', texto: v.elegivel_motivos.join(' · ')}));
  }

  cardEl.appendChild(chipsDeSkills(v));

  const rotulosSecao = {descricao:'Descrição', responsabilidades:'Responsabilidades', requisitos:'Requisitos',
    diferenciais:'Diferenciais', beneficios:'Benefícios', sobre_empresa:'Sobre a empresa'};
  for (const [chave, rotulo] of Object.entries(rotulosSecao)){
    if (v.secoes && v.secoes[chave]){
      cardEl.appendChild(el('details', {}, [el('summary', {texto: rotulo}), el('p', {texto: v.secoes[chave]})]));
    }
  }

  const acoes = el('div', {class:'vaga-acoes'});
  if (v.url) acoes.appendChild(el('a', {class:'btn btn-pequeno link-vaga', href: v.url, target:'_blank', rel:'noopener noreferrer', texto:'Ver vaga original ↗'}));
  if (DADOS.privado && DADOS.app_viva){
    acoes.appendChild(el('a', {class:'btn btn-pequeno btn-claro', href: '/privado/vaga/' + encodeURIComponent(v.id) + '/editar', texto:'Editar vaga'}));
  }
  if (acoes.childNodes.length) cardEl.appendChild(acoes);

  if (DADOS.privado){
    if (DADOS.app_viva) cardEl.appendChild(formStatus(v));
    else if (v.notas) cardEl.appendChild(el('div', {class:'notas-caixa', texto: v.notas}));
  }
  return cardEl;
}

const ORDEM_TABELA = {campo: 'data', direcao: -1};

function renderTabelaVagas(vagas){
  const container = document.getElementById('tabela-vagas-container');
  container.innerHTML = '';
  if (!vagas.length){ container.appendChild(el('p', {class:'vazio', texto:'Nenhuma vaga com esses filtros.'})); return; }

  const colunas = [
    {campo:'titulo', rotulo:'Vaga'}, {campo:'modalidade', rotulo:'Modalidade'}, {campo:'senioridade', rotulo:'Nível'},
    {campo:'mercado', rotulo:'Mercado'}, {campo:'data', rotulo:'Data'},
  ];
  if (DADOS.privado) colunas.push({campo:'match', rotulo:'Match'}, {campo:'elegivel', rotulo:'Elegível'}, {campo:'status', rotulo:'Status'});

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
    const seta = ORDEM_TABELA.campo === col.campo ? (ORDEM_TABELA.direcao === 1 ? ' ▲' : ' ▼') : '';
    const th = el('th', {class:'ordenavel', scope:'col', tabindex:'0', texto: col.rotulo + seta,
      'aria-sort': ORDEM_TABELA.campo === col.campo ? (ORDEM_TABELA.direcao === 1 ? 'ascending' : 'descending') : null});
    const ordenar = () => {
      if (ORDEM_TABELA.campo === col.campo) ORDEM_TABELA.direcao *= -1;
      else { ORDEM_TABELA.campo = col.campo; ORDEM_TABELA.direcao = 1; }
      renderTabelaVagas(vagas);
    };
    th.addEventListener('click', ordenar);
    th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); ordenar(); } });
    cabecalho.appendChild(th);
  }
  cabecalho.appendChild(el('th', {scope:'col'}, [el('span', {class:'sr-only', texto:'Ações'})]));
  tabela.appendChild(el('thead', {}, [cabecalho]));

  const tbody = el('tbody');
  for (const v of ordenadas){
    const tr = el('tr');
    tr.appendChild(el('td', {class:'td-titulo'}, [el('strong', {texto: v.titulo || '(sem título)'}), el('span', {texto: v.empresa || 'não divulgada'})]));
    tr.appendChild(el('td', {texto: v.modalidade || '—'}));
    tr.appendChild(el('td', {texto: v.senioridade || '—'}));
    tr.appendChild(el('td', {texto: v.mercado || '—'}));
    tr.appendChild(el('td', {class:'mono', texto: (v.data || '—') + (v.data_estimada ? ' (est.)' : '')}));
    if (DADOS.privado){
      const m = typeof v.match === 'number' ? v.match : null;
      tr.appendChild(el('td', {}, [m === null ? el('span', {class:'muted', texto:'n/d'}) :
        el('div', {class:'mini-match'}, [trilha(m*100, m >= 0.7 ? 'ok' : (m >= 0.45 ? 'falta' : 'perigo')), el('span', {texto: formatarPct(m)})])]));
      tr.appendChild(el('td', {}, [v.elegivel ? el('span', {class:'pill eleg-' + v.elegivel, texto: ROTULO_ELEG[v.elegivel] || v.elegivel}) : el('span', {class:'muted', texto:'—'})]));
      tr.appendChild(el('td', {}, [pillStatus(v.status || 'novo')]));
    }
    const tdLink = el('td', {style:'white-space:nowrap'});
    if (v.url) tdLink.appendChild(el('a', {class:'link-vaga', href: v.url, target:'_blank', rel:'noopener noreferrer', texto:'abrir ↗'}));
    if (DADOS.privado && DADOS.app_viva){
      tdLink.appendChild(document.createTextNode('  '));
      tdLink.appendChild(el('a', {href: '/privado/vaga/' + encodeURIComponent(v.id) + '/editar', texto:'editar'}));
    }
    tr.appendChild(tdLink);
    tbody.appendChild(tr);
  }
  tabela.appendChild(tbody);
  container.appendChild(el('div', {class:'tabela-caixa'}, [tabela]));
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
  const status = DADOS.privado ? document.getElementById('f-status').value : '';
  const soElegiveis = DADOS.privado && document.getElementById('f-so-elegiveis').checked;
  const ordem = document.getElementById('f-ordem').value;

  let vagas = vagasDoRecorte(recorteAtual);
  if (busca) vagas = vagas.filter(v => ((v.titulo||'') + ' ' + (v.empresa||'') + ' ' + v.skills.map(s => s.skill).join(' ')).toLowerCase().includes(busca));
  if (senioridade) vagas = vagas.filter(v => v.senioridade === senioridade);
  if (modalidade) vagas = vagas.filter(v => v.modalidade === modalidade);
  if (contrato) vagas = vagas.filter(v => v.contrato === contrato);
  if (vinculo) vagas = vagas.filter(v => v.tipo_vinculo === vinculo);
  if (familia) vagas = vagas.filter(v => v.familia_cargo === familia);
  if (skill) vagas = vagas.filter(v => v.skills.some(s => s.skill === skill));
  if (restricao) vagas = vagas.filter(v => tipoRestricao(v) === restricao);
  if (status) vagas = vagas.filter(v => (v.status || 'novo') === status);
  if (soElegiveis) vagas = vagas.filter(v => v.elegivel !== 'nao');

  vagas = [...vagas].sort((a,b) => {
    if (ordem === 'match') return (b.match ?? -1) - (a.match ?? -1);
    if (ordem === 'titulo') return (a.titulo||'').localeCompare(b.titulo||'', 'pt-BR');
    return (b.data||'').localeCompare(a.data||'');
  });

  document.getElementById('contador-vagas').textContent = vagas.length + ' vaga(s) · recorte ' + ROTULO_RECORTE[recorteAtual];

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
    btn.setAttribute('aria-pressed', btn.dataset.vis === modo ? 'true' : 'false');
  }
}
for (const btn of document.querySelectorAll('.alternador-visualizacao button')){
  btn.addEventListener('click', () => alternarVisualizacao(btn.dataset.vis));
}

function formMover(v, destino, rotulo, icone, principal){
  const form = el('form', {method:'post', action:'/privado/vaga/' + encodeURIComponent(v.id) + '/status'});
  form.appendChild(el('input', {type:'hidden', name:'status', value: destino}));
  const botao = el('button', {type:'submit', class:'btn btn-pequeno' + (principal ? '' : ' btn-icone'), 'aria-label': rotulo + ': ' + (v.titulo || 'vaga'), title: rotulo});
  if (principal) botao.appendChild(document.createTextNode(destino + ' →'));
  else botao.appendChild(document.createTextNode('←'));
  form.appendChild(botao);
  return form;
}

function renderPipeline(){
  if (!DADOS.privado) return;
  const kanban = document.getElementById('kanban');
  kanban.innerHTML = '';
  const MAX_POR_COLUNA = 15;
  const CORES = {novo:'var(--muted)', interessado:'var(--info)', aplicado:'var(--neutral)', entrevista:'var(--warn)', oferta:'var(--accent)', recusado:'var(--danger)'};
  let ativas = 0;
  ETAPAS.forEach((etapa, i) => {
    const vagas = DADOS.vagas.filter(v => (v.status || 'novo') === etapa)
      .sort((a,b) => (b.match ?? -1) - (a.match ?? -1));
    if (etapa !== 'novo' && etapa !== 'recusado') ativas += vagas.length;
    const coluna = el('section', {class:'coluna', 'aria-label': etapa});
    const topo = el('div', {class:'coluna-topo'}, [el('strong', {texto: etapa}), el('span', {texto: String(vagas.length)})]);
    topo.style.color = CORES[etapa];
    coluna.appendChild(topo);
    for (const v of vagas.slice(0, MAX_POR_COLUNA)){
      const cartao = el('article', {class:'cartao'}, [
        el('div', {class:'topo'}, [el('span', {class:'m', texto: typeof v.match === 'number' ? formatarPct(v.match) + ' match' : 'match n/d'}), el('span', {texto: v.mercado || ''})]),
        el('h3', {texto: v.titulo || '(sem título)'}),
        el('p', {class:'empresa', texto: v.empresa || 'empresa não divulgada'}),
      ]);
      if (DADOS.app_viva){
        const acoes = el('div', {class:'cartao-acoes'});
        if (i > 0) acoes.appendChild(formMover(v, ETAPAS[i-1], 'Voltar para ' + ETAPAS[i-1], 'seta-esq', false));
        if (i < ETAPAS.length - 1) acoes.appendChild(formMover(v, ETAPAS[i+1], 'Mover para ' + ETAPAS[i+1], 'seta-dir', true));
        cartao.appendChild(acoes);
      }
      coluna.appendChild(cartao);
    }
    if (vagas.length > MAX_POR_COLUNA) coluna.appendChild(el('div', {class:'mais-cartoes', texto: '+' + (vagas.length - MAX_POR_COLUNA) + ' outras — filtre por status na aba Vagas'}));
    if (!vagas.length) coluna.appendChild(el('p', {class:'vazio', style:'text-align:center', texto:'Nada aqui ainda'}));
    kanban.appendChild(coluna);
  });
  document.getElementById('resumo-pipeline').textContent = ativas + ' candidatura(s) em andamento' +
    (DADOS.app_viva ? ' · use os botões para mover uma vaga de etapa' : '');
  const contador = document.getElementById('contador-aba-pipeline');
  if (contador) contador.textContent = String(ativas);
}

function renderMeuCv(){
  if (!DADOS.privado || !DADOS.meu_cv) return;
  document.getElementById('aba-meu-cv').hidden = false;
  const cv = DADOS.meu_cv;

  const lacunasCont = document.getElementById('cv-lacunas');
  lacunasCont.innerHTML = '';
  if (!cv.cv_utilizavel) lacunasCont.appendChild(el('p', {class:'vazio', texto:'CV não utilizável (texto muito curto ou ausente em cv/).'}));
  else if (!cv.lacunas.length) lacunasCont.appendChild(el('p', {class:'vazio', texto:'Nenhuma lacuna identificada.'}));
  else {
    const lista = el('div', {class:'barras'});
    const maior = Math.max(...cv.lacunas.slice(0,15).map(l => l.score_lacuna), 0.0001);
    for (const l of cv.lacunas.slice(0, 15)){
      lista.appendChild(el('div', {class:'barra'}, [
        el('span', {class:'nome', texto: l.skill, title: l.categoria}),
        trilha(l.score_lacuna / maior * 100, 'falta'),
        el('span', {class:'valor prio ' + (l.prioridade === 'média' ? 'media' : l.prioridade), texto: l.prioridade}),
      ]));
    }
    lacunasCont.appendChild(lista);
  }

  const planoCont = document.getElementById('cv-plano');
  planoCont.innerHTML = '';
  const porCategoria = new Map();
  for (const l of cv.lacunas || []){
    if (!porCategoria.has(l.categoria)) porCategoria.set(l.categoria, []);
    porCategoria.get(l.categoria).push(l);
  }
  if (!porCategoria.size) planoCont.appendChild(el('p', {class:'vazio', texto:'Sem plano — nenhuma lacuna.'}));
  const plano = el('div', {class:'plano'});
  const ordem = [...porCategoria.entries()].sort((a,b) => b[1].reduce((s,x)=>s+x.score_lacuna,0) - a[1].reduce((s,x)=>s+x.score_lacuna,0));
  ordem.forEach(([categoria, itens], idx) => {
    const chips = el('div', {class:'chips'});
    for (const i of itens.slice(0, 8)) chips.appendChild(el('span', {class:'chip falta', texto: i.skill}));
    plano.appendChild(el('div', {class:'plano-item'}, [
      el('div', {class:'topo'}, [el('strong', {texto: categoria}), el('span', {class:'prio', texto: 'prioridade ' + (idx + 1)})]),
      chips,
    ]));
  });
  planoCont.appendChild(plano);

  const evolCont = document.getElementById('cv-evolucao');
  evolCont.innerHTML = '';
  const entradas = (cv.historico || []).filter(h => h.recorte === 'todos').sort((a,b)=> a.data.localeCompare(b.data));
  if (!entradas.length){ evolCont.appendChild(el('p', {class:'vazio', texto:'Sem histórico ainda.'})); }
  else renderGraficoLinha(evolCont, entradas, 'cobertura_geral');
}

function renderGraficoLinha(container, entradas, campo){
  const pontos = entradas.filter(e => e[campo] !== null && e[campo] !== undefined);
  if (pontos.length < 2){
    container.appendChild(el('p', {class:'vazio', texto:'Pontos insuficientes para o gráfico (mínimo 2 dias com dado).'}));
    return;
  }
  const largura = 760, altura = 180, margem = 30;
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
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Cobertura do CV de ' + formatarPct(valores[0]) + ' para ' + formatarPct(valores[valores.length-1]));

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
    ponto.setAttribute('cx', x); ponto.setAttribute('cy', y); ponto.setAttribute('r', 3.5);
    ponto.setAttribute('class', 'ponto');
    const tituloEl = document.createElementNS(svgNS, 'title');
    tituloEl.textContent = pontos[i].data + ': ' + formatarPct(pontos[i][campo]);
    ponto.appendChild(tituloEl);
    svg.appendChild(ponto);
  });

  for (const [x, texto, ancora] of [[margem, pontos[0].data, 'start'], [largura - margem, pontos[pontos.length - 1].data, 'end']]){
    const t = document.createElementNS(svgNS, 'text');
    t.setAttribute('x', x); t.setAttribute('y', altura - 8); t.setAttribute('text-anchor', ancora);
    t.textContent = texto;
    svg.appendChild(t);
  }
  container.appendChild(svg);
}

function montarSeletorRecorte(){
  const cont = document.getElementById('seletor-recorte');
  const recortes = [['BR','BR'], ['INT_acessivel','INT acessível'], ['INT_restrito','INT restrito'], ['todos','Todos']];
  for (const [valor, rotulo] of recortes){
    const btn = el('button', {type:'button', texto: rotulo, 'aria-pressed': valor === recorteAtual ? 'true' : 'false'});
    if (valor === recorteAtual) btn.classList.add('ativo');
    btn.addEventListener('click', () => {
      recorteAtual = valor;
      for (const b of cont.querySelectorAll('button')){ b.classList.remove('ativo'); b.setAttribute('aria-pressed', 'false'); }
      btn.classList.add('ativo'); btn.setAttribute('aria-pressed', 'true');
      renderPainel();
      aplicarFiltrosVagas();
    });
    cont.appendChild(btn);
  }
}

function paginaExiste(nome){
  const botao = document.querySelector('[data-pagina="' + nome + '"]');
  return !!document.getElementById('pagina-' + nome) && !!botao && !botao.hidden;
}

function trocarAba(nome, atualizarHash){
  if (!paginaExiste(nome)) nome = 'painel';
  for (const sec of document.querySelectorAll('section.pagina')) sec.classList.remove('ativa');
  document.getElementById('pagina-' + nome).classList.add('ativa');
  for (const btn of document.querySelectorAll('[data-pagina]')){
    const atual = btn.dataset.pagina === nome;
    btn.classList.toggle('atual', atual);
    if (atual) btn.setAttribute('aria-current', 'page'); else btn.removeAttribute('aria-current');
  }
  if (atualizarHash) history.replaceState(null, '', '#' + nome);
  window.scrollTo(0, 0);
}

for (const btn of document.querySelectorAll('[data-pagina]')){
  btn.addEventListener('click', () => trocarAba(btn.dataset.pagina, true));
}
window.addEventListener('hashchange', () => trocarAba(window.location.hash.slice(1) || 'painel', false));

if (DADOS.privado){
  document.getElementById('rotulo-so-elegiveis').hidden = false;
  document.getElementById('rotulo-status').hidden = false;
  document.getElementById('opcao-ordem-match').hidden = false;
}
if (DADOS.privado && DADOS.app_viva){
  document.getElementById('acoes-app-viva').hidden = false;
  document.getElementById('acoes-vagas-app-viva').hidden = false;
}

montarSeletorRecorte();
construirListasDeFiltro();
renderPainel();
renderComparacaoBrInt();
renderComparacaoFamilias();
aplicarFiltrosVagas();
renderPipeline();
renderMeuCv();
const contadorVagas = document.getElementById('contador-aba-vagas');
if (contadorVagas) contadorVagas.textContent = String(DADOS.vagas.length);
trocarAba((window.location.hash || '#painel').slice(1), false);

for (const idCampo of ['f-busca','f-senioridade','f-modalidade','f-contrato','f-vinculo','f-familia','f-skill','f-restricao','f-status','f-so-elegiveis','f-ordem']){
  const elemento = document.getElementById(idCampo);
  elemento.addEventListener('input', aplicarFiltrosVagas);
  elemento.addEventListener('change', aplicarFiltrosVagas);
}
</script>
</body>
</html>
"""


def _lateral(payload: dict) -> str:
    """Barra lateral do painel: botões que trocam de aba sem recarregar
    (funciona no snapshot estático) e, só na app local, links para as
    páginas de edição/ferramentas."""
    privado = bool(payload.get("privado"))
    viva = bool(payload.get("app_viva"))

    abas = [("painel", "Painel", "painel", False), ("vagas", "Vagas", "vagas", False)]
    if privado:
        abas += [("pipeline", "Pipeline", "pipeline", False), ("meu-cv", "Meu CV", "cv", True)]

    itens = []
    for chave, rotulo, nome_icone, oculto in abas:
        itens.append(
            f'<button type="button" class="menu-item" data-pagina="{chave}" id="aba-{chave}"'
            f'{" hidden" if oculto else ""}>{estilo.icone(nome_icone)}{rotulo}'
            f'<span class="contador" id="contador-aba-{chave}"></span></button>'
        )

    if viva:
        itens.append('<div class="menu-grupo">Ferramentas</div>')
        for chave, rotulo, nome_icone, href in estilo.MENU_APP_FERRAMENTAS:
            if chave == "publico" and not privado:
                rotulo, nome_icone, href = "Painel privado", "escudo", "/privado"
            itens.append(f'<a class="menu-item" href="{href}">{estilo.icone(nome_icone)}{rotulo}</a>')

    return (
        f'<aside class="lateral">{estilo.marca(None)}'
        f'<nav class="menu" aria-label="Principal">{"".join(itens)}</nav></aside>'
    )


def gerar_html(payload: dict, titulo: str) -> str:
    dados_json = _embutir_json(payload)
    titulo_seguro = html_lib.escape(titulo)
    return (
        _TEMPLATE.replace("__ESTILO_BASE__", estilo.CSS_BASE)
        .replace("__LATERAL__", _lateral(payload))
        .replace("__ICONE_BAIXAR__", estilo.icone("baixar", 16))
        .replace("__ICONE_RECARREGAR__", estilo.icone("recarregar", 16))
        .replace("__ICONE_MAIS__", estilo.icone("mais", 16))
        .replace("__TITULO__", titulo_seguro)
        .replace("__DADOS_JSON__", dados_json)
    )
