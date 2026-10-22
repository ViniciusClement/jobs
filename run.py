#!/usr/bin/env python3
"""Radar de Vagas: acompanha vagas de Red Team / Pentest / Segurança Ofensiva
do mercado privado (BR e internacional). Veja README.md para o fluxo de uso."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from radar import analise
from radar import coletor
from radar import cv as cv_mod
from radar import db
from radar import html as html_mod
from radar import ia as ia_mod
from radar import limpeza as limpeza_mod
from radar import parser
from radar import skills as skills_mod

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VAGAS_DIR = BASE_DIR / "vagas"
INBOX_DIR = VAGAS_DIR / "inbox"
RAW_DIR = VAGAS_DIR / "raw"
PROCESSADAS_DIR = VAGAS_DIR / "processadas"
CV_DIR = BASE_DIR / "cv"
PRIVADO_DIR = BASE_DIR / "privado"
DOCS_DIR = BASE_DIR / "docs"

STATUS_VALIDOS = ("novo", "interessado", "aplicado", "entrevista", "oferta", "recusado", "arquivada")

_STOPWORDS = set(
    """
    a o os as de do da dos das em no na nos nas para por com sem que quem qual quais e ou
    mas se nao sim ao aos a as um uma uns umas e sao foi eram ser estar ter ja tambem muito
    mais menos entre sobre ate apos antes durante sua seu suas seus nossa nosso voce voces
    nos eles elas ele ela isso isto aquele aquela todo toda todos todas esse essa esses essas
    the and but if then else for of to in on at by with from as is are was were be been being
    this that these those it its you your we our they their he she his her i me my will can
    """.split()
)


def _ler_json(caminho: Path, padrao):
    if not caminho.exists():
        return padrao
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _escrever_json_atomico(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    tmp.replace(caminho)


def _ler_texto(caminho: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return caminho.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return caminho.read_text(encoding="utf-8", errors="replace")


def carregar_config() -> dict:
    return {
        "ruido": _ler_json(DATA_DIR / "ruido.json", {}),
        "secoes": _ler_json(DATA_DIR / "secoes.json", {}),
        "filtros": _ler_json(DATA_DIR / "filtros.json", {}),
        "familias": _ler_json(DATA_DIR / "familias.json", {}),
        "skills_regras": skills_mod.compilar_regras(_ler_json(DATA_DIR / "skills.json", {})),
    }


def _caminho_db() -> Path:
    return DATA_DIR / "radar.db"


def _conectar_db():
    return db.conectar(_caminho_db())


def carregar_vagas() -> dict:
    """Lê do SQLite (data/radar.db). Se o banco ainda estiver vazio e um
    data/vagas.json antigo existir (Fases 1-4), importa automaticamente
    uma única vez — upgrade transparente, sem passo manual de migração."""
    conn = _conectar_db()
    try:
        if db.contar_vagas(conn) == 0:
            caminho_legado = DATA_DIR / "vagas.json"
            if caminho_legado.exists():
                legado = _ler_json(caminho_legado, {"vagas": []})
                if legado.get("vagas"):
                    db.salvar_vagas_em_lote(conn, legado["vagas"])
        return {"schema_version": 1, "vagas": db.listar_vagas(conn)}
    finally:
        conn.close()


def salvar_vagas(dados: dict) -> None:
    conn = _conectar_db()
    try:
        db.substituir_todas_as_vagas(conn, dados["vagas"])
    finally:
        conn.close()


def obter_perfil() -> dict:
    """Lê do SQLite. Se não houver perfil salvo ainda, migra de
    privado/perfil.json (Fase 2) uma única vez, ou usa o padrão (BR/BR)."""
    conn = _conectar_db()
    try:
        perfil = db.obter_perfil(conn)
        if perfil is None:
            caminho_legado = PRIVADO_DIR / "perfil.json"
            if caminho_legado.exists():
                perfil = _ler_json(caminho_legado, dict(db.PERFIL_PADRAO))
            else:
                perfil = dict(db.PERFIL_PADRAO)
            db.salvar_perfil(conn, perfil)
        return perfil
    finally:
        conn.close()


def salvar_perfil(perfil: dict) -> None:
    conn = _conectar_db()
    try:
        db.salvar_perfil(conn, perfil)
    finally:
        conn.close()


def salvar_elegibilidade(elegibilidade: dict) -> None:
    conn = _conectar_db()
    try:
        db.salvar_elegibilidade(conn, elegibilidade)
    finally:
        conn.close()


def registrar_historico(entrada: dict) -> None:
    conn = _conectar_db()
    try:
        db.registrar_historico(conn, entrada)
    finally:
        conn.close()


def listar_historico() -> list[dict]:
    conn = _conectar_db()
    try:
        return db.listar_historico(conn)
    finally:
        conn.close()


def obter_perfil_profissional() -> dict:
    conn = _conectar_db()
    try:
        return db.obter_perfil_profissional(conn) or {}
    finally:
        conn.close()


def salvar_perfil_profissional(perfil_profissional: dict) -> None:
    conn = _conectar_db()
    try:
        db.salvar_perfil_profissional(conn, perfil_profissional)
    finally:
        conn.close()


def obter_vaga(vaga_id: str) -> dict | None:
    conn = _conectar_db()
    try:
        return db.obter_vaga(conn, vaga_id)
    finally:
        conn.close()


def atualizar_vaga(vaga_id: str, campos: dict) -> bool:
    """Atualiza campos de uma vaga já existente (edição manual de dados
    extraídos, ex.: título/empresa/local, diferente de só status/notas)."""
    dados_vagas = carregar_vagas()
    for v in dados_vagas["vagas"]:
        if v["id"] == vaga_id:
            v.update(campos)
            salvar_vagas(dados_vagas)
            return True
    return False


def gerar_ficha_md(vaga: dict) -> str:
    linhas = [
        f"# {vaga['titulo'] or '(sem título)'}",
        "",
        f"- Empresa: {vaga['empresa'] or 'não divulgada'}",
        f"- Local(is): {', '.join(vaga['locais']) or 'não informado'}",
        f"- Modalidade: {vaga['modalidade'] or 'não informada'}",
        f"- Mercado: {vaga['mercado'] or 'não informado'}",
        f"- Família: {vaga['familia_cargo']}",
        f"- Senioridade: {vaga['senioridade'] or 'não informada'}",
        f"- Data: {vaga['data']}{' (estimada)' if vaga['data_estimada'] else ''}",
        f"- Status: {vaga['status']}",
        f"- URL: {vaga['url'] or 'não informada'}",
        "",
        "## Skills detectadas",
    ]
    if vaga["skills"]:
        for s in sorted(vaga["skills"], key=lambda s: (-s["peso"], s["skill"])):
            grupo = f" (grupo {s['grupo_alternativo']})" if s["grupo_alternativo"] else ""
            linhas.append(f"- [{s['categoria']}] {s['skill']} — {s['classe']}{grupo}")
    else:
        linhas.append("- (nenhuma skill detectada)")
    return "\n".join(linhas) + "\n"


def processar_bloco(bloco: str, config: dict, data_processamento: date, dados_vagas: dict) -> str:
    vaga = parser.montar_vaga(bloco, data_processamento, config)

    if vaga["ignorada"]:
        dados_vagas["vagas"].append(vaga)
        return f"[ignored] {vaga['titulo'] or vaga['id']}: {vaga['ignorada_motivo']}"

    existentes = dados_vagas["vagas"]
    for existente in existentes:
        if existente["chave_dedup"] == vaga["chave_dedup"]:
            return f"[exact duplicate discarded] {vaga['titulo'] or vaga['id']}"

    melhor_ratio = 0.0
    melhor_id = None
    for existente in existentes:
        if existente.get("ignorada"):
            continue
        ratio = difflib.SequenceMatcher(None, existente["texto_bruto"], vaga["texto_bruto"]).ratio()
        if ratio > melhor_ratio:
            melhor_ratio = ratio
            melhor_id = existente["id"]

    aviso = ""
    if melhor_ratio > 0.9 and melhor_id:
        vaga["possivel_duplicata_de"] = melhor_id
        aviso = f"[possible duplicate of {melhor_id}, similarity {melhor_ratio:.2f}] "

    dados_vagas["vagas"].append(vaga)

    PROCESSADAS_DIR.mkdir(parents=True, exist_ok=True)
    slug_arquivo = f"{vaga['data']}-{vaga['slug']}.md"
    (PROCESSADAS_DIR / slug_arquivo).write_text(gerar_ficha_md(vaga), encoding="utf-8")

    return f"{aviso}[processed] {vaga['titulo'] or vaga['id']} ({vaga['id']})"


def cmd_processar(args) -> None:
    config = carregar_config()
    dados_vagas = carregar_vagas()
    hoje = date.today()

    arquivos = sorted(INBOX_DIR.glob("*.txt"))
    if not arquivos:
        print("No new files in vagas/inbox/.")
        return

    for caminho in arquivos:
        texto = _ler_texto(caminho)
        blocos = parser.dividir_arquivo(texto)
        print(f"\n== {caminho.name} ({len(blocos)} job(s)) ==")
        for bloco in blocos:
            print(processar_bloco(bloco, config, hoje, dados_vagas))

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        destino = RAW_DIR / caminho.name
        if destino.exists():
            destino = RAW_DIR / f"{caminho.stem}-{hoje.isoformat()}{caminho.suffix}"
        caminho.replace(destino)

    salvar_vagas(dados_vagas)
    print(f"\n{len(dados_vagas['vagas'])} job(s) in the database (data/radar.db).")


def _dividir_heuristico(texto: str) -> list[str]:
    """Fallback sem '=== VAGA ===': tenta repetições de 'Full job description'."""
    marcador = re.compile(r"^full job description$", re.IGNORECASE)
    linhas = texto.split("\n")
    indices = [i for i, l in enumerate(linhas) if marcador.match(l.strip())]
    if len(indices) >= 2:
        blocos = []
        for idx, inicio in enumerate(indices):
            fim = indices[idx + 1] if idx + 1 < len(indices) else len(linhas)
            blocos.append("\n".join(linhas[inicio:fim]).strip())
        return blocos
    return [texto]


def cmd_dividir(args) -> None:
    caminho = Path(args.file)
    texto = _ler_texto(caminho)
    blocos = parser.dividir_arquivo(texto)
    origem = "'=== VAGA ===' separator"
    if len(blocos) <= 1:
        blocos = _dividir_heuristico(texto)
        origem = "heuristic (no separator found)"

    print(f"Split preview ({origem}): {len(blocos)} block(s).\n")
    for i, bloco in enumerate(blocos, start=1):
        primeira_linha = next((l.strip() for l in bloco.split("\n") if l.strip()), "(empty)")
        print(f"  Block {i}: {len(bloco)} characters — starts with: \"{primeira_linha[:70]}\"")

    if len(blocos) <= 1:
        print("\nWarning: could not split safely; nothing will be separated.")
        return

    if args.dry_run:
        print("\n--dry-run: no file was written.")
        return

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    for i, bloco in enumerate(blocos, start=1):
        destino = INBOX_DIR / f"{caminho.stem}-{i:02d}.txt"
        destino.write_text(bloco.strip() + "\n", encoding="utf-8")
        print(f"Saved: {destino}")


def cmd_reprocessar(args) -> None:
    config = carregar_config()
    dados_vagas = carregar_vagas()
    novas = []
    hoje = date.today()
    for vaga_antiga in dados_vagas["vagas"]:
        try:
            data_ref = date.fromisoformat(vaga_antiga["data"]) if not vaga_antiga.get("data_estimada") else hoje
        except (KeyError, ValueError):
            data_ref = hoje
        nova = parser.montar_vaga(vaga_antiga["texto_bruto"], data_ref, config)
        nova["id"] = vaga_antiga["id"]
        nova["status"] = vaga_antiga.get("status", "novo")
        nova["notas"] = vaga_antiga.get("notas")
        novas.append(nova)
    dados_vagas["vagas"] = novas
    salvar_vagas(dados_vagas)
    print(f"Reprocessed {len(novas)} job(s).")


def cmd_status(args) -> None:
    dados_vagas = carregar_vagas()
    for vaga in dados_vagas["vagas"]:
        if vaga["id"] == args.id:
            vaga["status"] = args.new_status
            if args.note:
                vaga["notas"] = args.note
            salvar_vagas(dados_vagas)
            print(f"Status of {args.id} updated to '{args.new_status}'.")
            return
    print(f"Job {args.id} not found.")


def cmd_termos(args) -> None:
    dados_vagas = carregar_vagas()
    skills_cfg = _ler_json(DATA_DIR / "skills.json", {})
    nomes_taxonomia = set()
    for categorias in skills_cfg.values():
        for nome, cfg in categorias.items():
            nomes_taxonomia.add(nome.lower())
            nomes_taxonomia.update(s.lower() for s in cfg.get("sinonimos", []))

    contagem: dict[str, int] = {}
    contexto: dict[str, str] = {}
    for vaga in dados_vagas["vagas"]:
        if vaga.get("ignorada"):
            continue
        for linha in vaga["texto_bruto"].split("\n"):
            tokens = re.findall(r"[a-zà-öø-ÿ0-9+#./-]+", linha.lower())
            tokens = [t for t in tokens if len(t) > 2 and t not in _STOPWORDS and t not in nomes_taxonomia]
            for t in tokens:
                contagem[t] = contagem.get(t, 0) + 1
                contexto.setdefault(t, linha.strip()[:100])
            for i in range(len(tokens) - 1):
                bigrama = f"{tokens[i]} {tokens[i + 1]}"
                contagem[bigrama] = contagem.get(bigrama, 0) + 1
                contexto.setdefault(bigrama, linha.strip()[:100])

    if not contagem:
        print("Not enough terms (no job processed yet?).")
        return

    print("Top terms/bigrams outside the taxonomy:\n")
    for termo, n in sorted(contagem.items(), key=lambda item: -item[1])[: args.top]:
        print(f"  {n:4d}x  {termo}   (ex.: \"{contexto.get(termo, '')}\")")


_CAMPOS_CSV_EXCLUIR = {"texto_bruto", "contato_recrutador"}


def cmd_exportar(args) -> None:
    dados_vagas = carregar_vagas()
    vagas = dados_vagas["vagas"]
    if not vagas:
        print("No jobs to export.")
        return
    campos = [c for c in vagas[0].keys() if c not in _CAMPOS_CSV_EXCLUIR]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    destino = DATA_DIR / "vagas.csv"
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        for v in vagas:
            linha = {}
            for c in campos:
                valor = v.get(c)
                if isinstance(valor, (list, dict)):
                    valor = json.dumps(valor, ensure_ascii=False)
                linha[c] = valor
            writer.writerow(linha)
    print(f"Exported: {destino} ({len(vagas)} job(s)).")


def _formatar_percentual(valor) -> str:
    return "n/d" if valor is None else f"{valor * 100:.0f}%"


def _prioridade_lacuna(score: float) -> str:
    if score >= 0.3:
        return "alta"
    if score >= 0.1:
        return "média"
    return "baixa"


def montar_relatorio_cv(
    caminho_cv: Path, cv_utilizavel: bool, resultados_por_recorte: dict,
    lacunas: list[dict], vagas_elegiveis_ordenadas: list[tuple[dict, float]],
) -> str:
    n_vagas_todos = resultados_por_recorte.get("todos", {}).get("n_vagas", 0)
    cobertura_todos = resultados_por_recorte.get("todos", {}).get("cobertura_geral")
    n_elegiveis = len(vagas_elegiveis_ordenadas)

    linhas = [
        f"# Relatório de CV — {date.today().isoformat()}",
        "",
        f"CV utilizado: `{caminho_cv.name}`",
        "",
        "## Resumo",
        "",
    ]
    if not cv_utilizavel:
        linhas += [
            "**Aviso:** o texto extraído do CV é muito curto (possível PDF em imagem, sem OCR). "
            "A cobertura abaixo aparece como 'n/d' até isso ser corrigido.",
            "",
        ]
    else:
        linhas += [
            f"- {n_vagas_todos} vaga(s) ativa(s) consideradas (todas as fontes, exceto ignoradas).",
            f"- Cobertura geral do seu CV sobre essas vagas: {_formatar_percentual(cobertura_todos)}.",
            f"- {len(lacunas)} skill(s) identificada(s) como lacuna em pelo menos uma vaga.",
            f"- {n_elegiveis} vaga(s) elegível(is) (sim/talvez) com match calculável.",
            "",
        ]

    linhas += ["## Cobertura por recorte", "", "| Recorte | Vagas ativas | Cobertura geral |", "|---|---|---|"]
    for recorte, dados in resultados_por_recorte.items():
        linhas.append(f"| {recorte} | {dados['n_vagas']} | {_formatar_percentual(dados['cobertura_geral'])} |")
    linhas.append("")

    linhas += ["## Top lacunas (recorte: todos)", ""]
    if lacunas:
        linhas += ["| Categoria | Skill | score_lacuna | Vagas onde é lacuna | Prioridade |", "|---|---|---|---|---|"]
        for l in lacunas[:20]:
            linhas.append(
                f"| {l['categoria']} | {l['skill']} | {l['score_lacuna']:.2f} | {l['n_vagas']} | "
                f"{_prioridade_lacuna(l['score_lacuna'])} |"
            )
    else:
        linhas.append("(nenhuma lacuna identificada ou CV não utilizável)")
    linhas.append("")

    linhas += ["## Plano de estudo por categoria", ""]
    por_categoria: dict[str, list] = {}
    for l in lacunas:
        por_categoria.setdefault(l["categoria"], []).append(l)
    categorias_ordenadas = sorted(
        por_categoria.items(), key=lambda kv: -max(i["score_lacuna"] for i in kv[1])
    )
    for categoria, itens in categorias_ordenadas:
        linhas.append(f"**{categoria}**")
        for item in sorted(itens, key=lambda i: -i["score_lacuna"]):
            linhas.append(f"- [{_prioridade_lacuna(item['score_lacuna'])}] {item['skill']} (score_lacuna={item['score_lacuna']:.2f})")
        linhas.append("")
    if not categorias_ordenadas:
        linhas += ["(sem lacunas para montar um plano de estudo)", ""]

    linhas += ["## Palavras-chave sugeridas para o CV", ""]
    palavras_chave = [l["skill"] for l in sorted(lacunas, key=lambda l: -l["score_lacuna"])[:15]]
    linhas.append(", ".join(palavras_chave) if palavras_chave else "(nenhuma sugestão — sem lacunas ou CV não utilizável)")
    linhas.append("")

    linhas += ["## Vagas elegíveis com maior match", ""]
    if vagas_elegiveis_ordenadas:
        linhas += ["| Match | Título | Empresa | Mercado | URL |", "|---|---|---|---|---|"]
        for vaga, m in vagas_elegiveis_ordenadas[:15]:
            linhas.append(
                f"| {_formatar_percentual(m)} | {vaga.get('titulo') or '(sem título)'} | "
                f"{vaga.get('empresa') or 'não divulgada'} | {vaga.get('mercado') or '—'} | "
                f"{vaga.get('url') or '—'} |"
            )
    else:
        linhas.append("(nenhuma vaga elegível com match calculável)")
    linhas.append("")

    linhas.append(
        "> Nota: lacuna não significa necessariamente falta de conhecimento — se você já tem a "
        "skill, escreva-a explicitamente no CV (ajuda em triagens por ATS); se não tem, é uma "
        "sugestão de estudo."
    )
    return "\n".join(linhas) + "\n"


def cmd_analisar(args) -> None:
    config = carregar_config()
    dados_vagas = carregar_vagas()
    todas_vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]

    caminho_forcado = Path(args.cv) if getattr(args, "cv", None) else None
    try:
        caminho_cv, texto_cv = cv_mod.carregar_cv(CV_DIR, caminho_forcado)
    except FileNotFoundError as exc:
        print(str(exc))
        return

    cv_utilizavel = cv_mod.cv_e_utilizavel(texto_cv)
    skills_cv = cv_mod.detectar_skills_cv(texto_cv, config["skills_regras"]) if cv_utilizavel else set()

    perfil = obter_perfil()

    elegibilidade = {}
    for vaga in todas_vagas:
        status, motivos = analise.calcular_elegibilidade(vaga, perfil)
        elegibilidade[vaga["id"]] = {"elegivel": status, "motivos": motivos}
    salvar_elegibilidade(elegibilidade)
    print(f"Eligibility calculated for {len(elegibilidade)} job(s) (database).")

    hoje = date.today()

    resultados_por_recorte = {}
    for recorte in analise.RECORTES:
        vagas_recorte = analise.filtrar_recorte(todas_vagas, recorte, perfil)
        cobertura = analise.cobertura_geral(vagas_recorte, skills_cv) if cv_utilizavel else None
        resultados_por_recorte[recorte] = {"n_vagas": len(vagas_recorte), "cobertura_geral": cobertura}

        registrar_historico({
            "data": hoje.isoformat(), "recorte": recorte,
            "n_vagas_ativas": len(vagas_recorte), "cobertura_geral": cobertura,
        })

    print(f"History updated ({len(analise.RECORTES)} scope(s) for today).")

    vagas_todos = analise.filtrar_recorte(todas_vagas, "todos", perfil)
    lacunas = analise.calcular_lacunas(vagas_todos, skills_cv) if cv_utilizavel else []
    lacunas.sort(key=lambda l: -l["score_lacuna"])

    vagas_elegiveis_ordenadas: list[tuple[dict, float]] = []
    if cv_utilizavel:
        for vaga in vagas_todos:
            if elegibilidade.get(vaga["id"], {}).get("elegivel") == "nao":
                continue
            m = analise.match_vaga(vaga, skills_cv)
            if m is not None:
                vagas_elegiveis_ordenadas.append((vaga, m))
        vagas_elegiveis_ordenadas.sort(key=lambda par: -par[1])

    relatorio = montar_relatorio_cv(
        caminho_cv, cv_utilizavel, resultados_por_recorte, lacunas, vagas_elegiveis_ordenadas
    )
    PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    (PRIVADO_DIR / "relatorio-cv.md").write_text(relatorio, encoding="utf-8")
    print("Relatório gerado em privado/relatorio-cv.md")


def _url_ja_existe(url_normalizada: str, vagas_existentes: list[dict]) -> bool:
    return any(v.get("url") == url_normalizada for v in vagas_existentes)


def cmd_coletar(args) -> None:
    fontes = _ler_json(DATA_DIR / "fontes.json", {"ats": [], "filtros": {}})
    dados_vagas = carregar_vagas()
    vagas_existentes = dados_vagas["vagas"]
    filtros = fontes.get("filtros") or {}

    total_novas = 0
    total_arquivadas = 0
    total_ja_coletadas = 0

    for fonte in fontes.get("ats") or []:
        tipo = fonte.get("tipo")
        slug = fonte.get("slug")
        mercado = fonte.get("mercado") or "INT"
        empresa_padrao = fonte.get("empresa") or (slug or tipo or "fonte").capitalize()

        coletor_fn = coletor.COLETORES.get(tipo)
        if coletor_fn is None:
            print(f"[{tipo}] unknown ATS type (use greenhouse/lever/ashby/smartrecruiters) — skipping.")
            continue
        if not slug or slug == "TROCAR":
            print(f"[{tipo}] slug not configured yet in data/fontes.json ('TROCAR') — skipping.")
            continue

        print(f"\n== {tipo}:{slug} ==")
        try:
            vagas_coletadas = coletor_fn(slug)
        except Exception as exc:
            print(f"  error collecting {tipo}:{slug}: {exc}")
            continue

        urls_desta_fonte: set[str] = set()
        for vaga in vagas_coletadas:
            url_normalizada = limpeza_mod.normalizar_url(vaga.get("url"))
            vaga["url"] = url_normalizada
            if url_normalizada:
                urls_desta_fonte.add(url_normalizada)

            if not coletor.passa_filtro_titulo(vaga.get("titulo"), filtros):
                continue
            if url_normalizada and _url_ja_existe(url_normalizada, vagas_existentes):
                total_ja_coletadas += 1
                continue

            texto_txt = coletor.montar_texto_vaga(vaga, tipo, mercado, empresa_padrao)
            if args.dry_run:
                print(f"  [dry-run] new job: {vaga.get('titulo')} ({url_normalizada})")
                total_novas += 1
                continue

            INBOX_DIR.mkdir(parents=True, exist_ok=True)
            slug_arquivo = parser.gerar_slug(vaga.get("titulo"), empresa_padrao)
            nome_arquivo = f"coletor-{tipo}-{slug_arquivo}.txt"
            (INBOX_DIR / nome_arquivo).write_text(texto_txt, encoding="utf-8")
            print(f"  new job: {vaga.get('titulo')} -> vagas/inbox/{nome_arquivo}")
            total_novas += 1

        # Vaga que sumiu da fonte (mesma origem+slug, não vista nesta coleta,
        # ainda não trabalhada pelo usuário) -> arquivada, sem apagar.
        for existente in vagas_existentes:
            if existente.get("origem") != tipo:
                continue
            url_existente = existente.get("url") or ""
            if slug.lower() not in url_existente.lower():
                continue
            if existente.get("status") not in ("novo", "interessado"):
                continue
            if url_existente in urls_desta_fonte:
                continue
            if args.dry_run:
                print(f"  [dry-run] disappeared from source, would be archived: {existente.get('titulo')}")
                total_arquivadas += 1
                continue
            existente["status"] = "arquivada"
            nota_antiga = existente.get("notas")
            existente["notas"] = f"{nota_antiga}; closed at source" if nota_antiga else "closed at source"
            total_arquivadas += 1
            print(f"  archived (closed at source): {existente.get('titulo')}")

        coletor._pausar()

    if not args.dry_run and total_arquivadas:
        salvar_vagas(dados_vagas)

    print(
        f"\nCollection complete: {total_novas} new, {total_ja_coletadas} already collected (dedup by URL), "
        f"{total_arquivadas} archived for having left the source."
    )
    if args.dry_run:
        print("--dry-run: nothing was saved (no .txt in the inbox, no database write).")
    else:
        print("New jobs are in vagas/inbox/ — run 'python run.py process' to process them.")


def montar_payload_publico(vagas: list[dict]) -> dict:
    """Payload do painel público — usado pelo `gerar-html` (snapshot estático,
    para GitHub Pages) e pela rota "/" da app web (ao vivo)."""
    hoje = date.today()
    return {
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
        "privado": False,
        "vagas": [html_mod.montar_vaga_payload(v, False, html_mod.PERFIL_PUBLICO_GENERICO) for v in vagas],
        "comparacao_br_int": analise.comparar_br_int(vagas),
        "comparacao_familias": analise.comparar_familias(vagas),
        "tendencia": analise.tendencia_skills(vagas, hoje),
        "qualidade_dados": analise.qualidade_dados(vagas),
    }


def montar_payload_privado(vagas: list[dict]) -> dict:
    """Payload do painel privado (match/elegibilidade/Meu CV). Como efeito
    colateral, recalcula e grava a elegibilidade no banco — mantém
    privado/elegibilidade sempre fresca a cada vez que o painel é visto."""
    hoje = date.today()
    perfil = obter_perfil()

    caminho_cv = cv_mod.encontrar_cv_mais_recente(CV_DIR)
    skills_cv: set[tuple[str, str]] = set()
    cv_utilizavel = False
    if caminho_cv is not None:
        try:
            texto_cv = cv_mod.extrair_texto(caminho_cv)
            cv_utilizavel = cv_mod.cv_e_utilizavel(texto_cv)
            if cv_utilizavel:
                config = carregar_config()
                skills_cv = cv_mod.detectar_skills_cv(texto_cv, config["skills_regras"])
        except Exception as exc:
            print(f"Warning: could not read the CV for the private dashboard: {exc}")

    vagas_privadas = []
    elegibilidade_calculada = {}
    for v in vagas:
        status_eleg, motivos_eleg = analise.calcular_elegibilidade(v, perfil)
        elegibilidade_calculada[v["id"]] = {"elegivel": status_eleg, "motivos": motivos_eleg}
        payload_vaga = html_mod.montar_vaga_payload(
            v, True, perfil, skills_cv=skills_cv, elegibilidade_vaga=elegibilidade_calculada[v["id"]]
        )
        payload_vaga["match"] = analise.match_vaga(v, skills_cv) if cv_utilizavel else None
        vagas_privadas.append(payload_vaga)
    salvar_elegibilidade(elegibilidade_calculada)

    lacunas = analise.calcular_lacunas(vagas, skills_cv) if cv_utilizavel else []
    for l in lacunas:
        l["prioridade"] = _prioridade_lacuna(l["score_lacuna"])
    lacunas.sort(key=lambda l: -l["score_lacuna"])

    # KPIs executivos: cobertura geral por recorte (precisa da lógica de
    # unidade de exigência/grupo alternativo, que só existe em Python) e o
    # score de perfil — o resto dos KPIs (totais, top skill...) o JS já
    # calcula a partir do array de vagas embutido, sem precisar disso.
    cobertura_por_recorte = {}
    for recorte in analise.RECORTES:
        vagas_recorte = analise.filtrar_recorte(vagas, recorte, perfil)
        cobertura_por_recorte[recorte] = analise.cobertura_geral(vagas_recorte, skills_cv) if cv_utilizavel else None

    perfil_profissional = obter_perfil_profissional()
    score_perfil = analise.calcular_score_perfil(perfil_profissional, skills_cv, vagas)

    return {
        "gerado_em": datetime.now().isoformat(timespec="minutes"),
        "privado": True,
        "vagas": vagas_privadas,
        "comparacao_br_int": analise.comparar_br_int(vagas),
        "comparacao_familias": analise.comparar_familias(vagas),
        "tendencia": analise.tendencia_skills(vagas, hoje),
        "qualidade_dados": analise.qualidade_dados(vagas),
        "meu_cv": {"cv_utilizavel": cv_utilizavel, "lacunas": lacunas, "historico": listar_historico()},
        "cobertura_por_recorte": cobertura_por_recorte,
        "score_perfil": score_perfil,
    }


def cmd_gerar_html(args) -> None:
    """Gera um SNAPSHOT estático (docs/index.html + privado/index.html) a
    partir do banco agora — útil para publicar docs/ no GitHub Pages. Para
    uso do dia a dia com edição ao vivo, prefira `python run.py servir`."""
    dados_vagas = carregar_vagas()
    vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]

    payload_publico = montar_payload_publico(vagas)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(
        html_mod.gerar_html(payload_publico, "Radar de Vagas — Painel público"), encoding="utf-8"
    )
    print(f"Generated: docs/index.html ({len(vagas)} public job(s)).")

    payload_privado = montar_payload_privado(vagas)
    PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    (PRIVADO_DIR / "index.html").write_text(
        html_mod.gerar_html(payload_privado, "Radar de Vagas — Painel privado"), encoding="utf-8"
    )
    cv_utilizavel = payload_privado["meu_cv"]["cv_utilizavel"]
    print(f"Generated: privado/index.html ({len(payload_privado['vagas'])} job(s), usable CV: {cv_utilizavel}).")


def cmd_ia(args) -> None:
    caminho_cv = cv_mod.encontrar_cv_mais_recente(CV_DIR)
    if caminho_cv is None:
        print(f"No CV found in {CV_DIR} (put a .pdf/.docx/.txt/.md there).")
        return
    print(f"CV used: {caminho_cv}")
    try:
        texto_cv = cv_mod.extrair_texto(caminho_cv)
    except RuntimeError as exc:
        print(str(exc))
        return
    if not cv_mod.cv_e_utilizavel(texto_cv):
        print("CV too short (possibly a scanned/image PDF) — cannot generate suggestions.")
        return

    config = carregar_config()
    skills_cv = cv_mod.detectar_skills_cv(texto_cv, config["skills_regras"])

    dados_vagas = carregar_vagas()
    vagas = [v for v in dados_vagas["vagas"] if not v.get("ignorada")]
    lacunas = analise.calcular_lacunas(vagas, skills_cv)

    try:
        sugestao = ia_mod.sugerir(texto_cv, lacunas, vagas)
    except RuntimeError as exc:
        print(str(exc))
        return

    PRIVADO_DIR.mkdir(parents=True, exist_ok=True)
    conteudo = (
        "# Sugestões de CV (gerado por IA — revise antes de usar)\n\n"
        "> Aviso: nada aqui deve ser copiado sem revisão. A IA foi instruída a não "
        "inventar experiência nem sugerir contornar exigências de cidadania/residência/clearance, "
        "mas verifique cada frase contra o que você realmente fez.\n\n"
        f"{sugestao}\n"
    )
    (PRIVADO_DIR / "sugestoes-cv.md").write_text(conteudo, encoding="utf-8")
    print("Suggestions saved to privado/sugestoes-cv.md")


def cmd_import_linkedin(args) -> None:
    caminho = Path(args.pdf)
    if not caminho.exists():
        print(f"File not found: {caminho}")
        return
    from radar import linkedin_import

    try:
        perfil_profissional = linkedin_import.importar_pdf_perfil(caminho)
    except RuntimeError as exc:
        print(str(exc))
        return
    salvar_perfil_profissional(perfil_profissional)
    n_exp = len(perfil_profissional.get("experiencias") or [])
    n_skills = len(perfil_profissional.get("skills_linkedin") or [])
    print(
        f"Imported LinkedIn profile for '{perfil_profissional.get('nome')}': "
        f"{n_exp} experience(s), {n_skills} self-reported skill(s). Saved to the database."
    )
    print("See it at: python run.py serve -> /perfil-profissional")


def cmd_servir(args) -> None:
    try:
        from radar import web as web_mod
    except ImportError as exc:
        print(f"The web interface requires Flask: pip install flask\n(original error: {exc})")
        return
    app = web_mod.criar_app()
    print(f"Serving at http://127.0.0.1:{args.port} — Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=args.port, debug=False)


def _obter_clipboard() -> str | None:
    try:
        import tkinter

        raiz = tkinter.Tk()
        raiz.withdraw()
        texto = raiz.clipboard_get()
        raiz.destroy()
        if texto and texto.strip():
            return texto
    except Exception:
        pass
    try:
        import subprocess

        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
        )
        if resultado.returncode == 0 and resultado.stdout.strip():
            return resultado.stdout
    except Exception:
        pass
    return None


def cmd_colar(args) -> None:
    texto = _obter_clipboard()
    if not texto:
        print("Could not read the clipboard (tkinter/powershell unavailable or empty).")
        print("Paste the text manually into a .txt file inside vagas/inbox/ and run 'python run.py process'.")
        return
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"colado-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    destino = INBOX_DIR / nome
    destino.write_text(texto, encoding="utf-8")
    print(f"Saved to {destino}. Processing...")
    cmd_processar(args)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    for diretorio in (INBOX_DIR, RAW_DIR, PROCESSADAS_DIR, DATA_DIR):
        diretorio.mkdir(parents=True, exist_ok=True)

    ap = argparse.ArgumentParser(
        prog="run.py",
        description="Radar de Vagas: tracks Red Team / Pentest / Offensive Security jobs in the private market.",
    )
    ap.add_argument(
        "--ai", action="store_true",
        help="Generates privado/sugestoes-cv.md via AI (optional; requires ANTHROPIC_API_KEY+ANTHROPIC_MODEL or OLLAMA_URL/OLLAMA_MODEL).",
    )
    sub = ap.add_subparsers(dest="comando")

    sub.add_parser("process", help="Processes the .txt files in the inbox and saves to the database (default with no subcommand).")
    sub.add_parser("paste", help="Reads the clipboard, saves it to the inbox, and processes it.")

    p_dividir = sub.add_parser("split", help="Splits a .txt with several jobs into separate files in the inbox.")
    p_dividir.add_argument("file")
    p_dividir.add_argument("--dry-run", action="store_true")

    sub.add_parser("reprocess", help="Reprocesses all jobs from the raw text, preserving status/notes.")

    p_status = sub.add_parser("status", help="Updates the status of a job.")
    p_status.add_argument("id")
    p_status.add_argument("new_status", choices=STATUS_VALIDOS)
    p_status.add_argument("--note")

    p_termos = sub.add_parser("terms", help="Lists frequent terms/bigrams outside the taxonomy.")
    p_termos.add_argument("--top", type=int, default=30)

    sub.add_parser("export", help="Exports data/vagas.csv (utf-8-sig), without contacts or raw text.")

    p_analisar = sub.add_parser(
        "analyze",
        help="Reads the CV, calculates eligibility/coverage/gaps in the database, and generates privado/relatorio-cv.md.",
    )
    p_analisar.add_argument("--cv", help="Path to a specific CV (default: the most recent one in cv/).")

    p_coletar = sub.add_parser(
        "collect",
        help="Collects jobs via public APIs (Greenhouse/Lever/Ashby/SmartRecruiters) configured in data/fontes.json.",
    )
    p_coletar.add_argument("--dry-run", action="store_true", help="Writes nothing; just shows what would be done.")

    sub.add_parser(
        "generate-html",
        help="Generates a static snapshot docs/index.html + privado/index.html (to publish on GitHub Pages).",
    )

    p_servir = sub.add_parser(
        "serve",
        help="Starts the local web app (Flask) to view the dashboards and edit jobs/profile/status in the browser.",
    )
    p_servir.add_argument("--port", type=int, default=8000)

    p_linkedin = sub.add_parser(
        "import-linkedin",
        help="Imports your LinkedIn profile from a 'Save to PDF' export into the professional profile dashboard.",
    )
    p_linkedin.add_argument("pdf", help="Path to the LinkedIn profile PDF (download it from your own profile page).")

    args = ap.parse_args()

    if args.ai:
        cmd_ia(args)
        return

    comandos = {
        None: cmd_processar,
        "process": cmd_processar,
        "paste": cmd_colar,
        "split": cmd_dividir,
        "reprocess": cmd_reprocessar,
        "status": cmd_status,
        "terms": cmd_termos,
        "export": cmd_exportar,
        "analyze": cmd_analisar,
        "collect": cmd_coletar,
        "generate-html": cmd_gerar_html,
        "serve": cmd_servir,
        "import-linkedin": cmd_import_linkedin,
    }
    comandos[args.comando](args)


if __name__ == "__main__":
    main()
