"""Elegibilidade e fórmulas de análise de mercado (cobertura, lacunas, ranking).

Convenções desta implementação, fixadas aqui porque a seção 12 não as
detalha por completo:
- "vagas ativas" = vagas com ignorada=False (seção 8: ignoradas ficam fora
  de toda estatística). Não excluímos arquivadas/expiradas daqui; isso é
  reportado separadamente em qualidade_dados().
- Para ranking de mercado (score_skill, ranking_skills, coocorrência, em
  alta, comparação BR×INT, comparação por família), cada skill conta
  individualmente, mesmo dentro de grupo alternativo (regra explícita da
  seção 12).
- Para match_vaga/cobertura_geral/lacunas, a "unidade de exigência" trata
  cada grupo alternativo como uma única unidade (também regra da seção 12).
- "INT acessível" considera só compatibilidade de cidadania/residência
  (não clearance) — é o que a seção 12 define explicitamente para esse
  recorte. O filtro privado "só elegíveis" usa elegibilidade completa
  (cidadania + residência + clearance + idioma) e inclui "sim" e "talvez"
  (só exclui "não", que é o caso definitivamente inviável).
- Faixa salarial por vaga = média de min/max quando os dois existem, ou o
  valor disponível quando só um existe; a estatística (mín/mediana/máx) é
  calculada sobre esses valores representativos, por moeda+período, sem
  conversão.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date

_NIVEIS_INGLES = {"basico": 1, "intermediario": 2, "avancado": 3, "fluente": 4, "nativo": 5}


# ---------------------------------------------------------------------------
# Elegibilidade (seção 11)
# ---------------------------------------------------------------------------

def calcular_elegibilidade(vaga: dict, perfil: dict) -> tuple[str, list[str]]:
    """Retorna (elegivel, motivos). elegivel em {"sim", "nao", "talvez"}."""
    motivos: list[str] = []
    bloqueante = False
    incerto = False

    restricoes = vaga.get("restricoes") or {}

    cidadania_exigida = restricoes.get("cidadania")
    if cidadania_exigida:
        cidadanias_perfil = set(perfil.get("cidadanias") or [])
        if not (cidadanias_perfil & set(cidadania_exigida)):
            bloqueante = True
            motivos.append(f"exige cidadania: {', '.join(cidadania_exigida)}")

    residencia_exigida = restricoes.get("residencia")
    if residencia_exigida and residencia_exigida != perfil.get("residencia"):
        if perfil.get("aceita_relocacao"):
            incerto = True
            motivos.append(f"exige residência em {residencia_exigida} (você aceita relocação)")
        else:
            bloqueante = True
            motivos.append(f"exige residência em {residencia_exigida}")

    clearance_exigido = restricoes.get("clearance")
    if clearance_exigido:
        tem_clearance = clearance_exigido in (perfil.get("clearances") or [])
        if not tem_clearance:
            if restricoes.get("clearance_obrigatorio"):
                bloqueante = True
                motivos.append(f"exige clearance obrigatório: {clearance_exigido}")
            else:
                incerto = True
                motivos.append(f"clearance {clearance_exigido} é diferencial e você não possui")

    ingles_exigido = vaga.get("ingles_nivel")
    if ingles_exigido:
        nivel_exigido = _NIVEIS_INGLES.get(ingles_exigido)
        nivel_perfil = _NIVEIS_INGLES.get((perfil.get("idiomas") or {}).get("en", ""))
        if nivel_exigido and nivel_perfil and nivel_perfil < nivel_exigido:
            incerto = True
            motivos.append(
                f"exige inglês nível {ingles_exigido}, perfil indica {perfil['idiomas']['en']}"
            )

    if bloqueante:
        return "nao", motivos
    if incerto:
        return "talvez", motivos
    return "sim", motivos or ["nenhuma restrição identificada"]


def _cidadania_residencia_compativel(vaga: dict, perfil: dict) -> bool:
    """Usado só para o recorte INT acessível/restrito (seção 12): ignora clearance."""
    restricoes = vaga.get("restricoes") or {}
    cidadania_exigida = restricoes.get("cidadania")
    if cidadania_exigida:
        if not (set(perfil.get("cidadanias") or []) & set(cidadania_exigida)):
            return False
    residencia_exigida = restricoes.get("residencia")
    if residencia_exigida and residencia_exigida != perfil.get("residencia"):
        if not perfil.get("aceita_relocacao"):
            return False
    return True


# ---------------------------------------------------------------------------
# Recortes (seção 12)
# ---------------------------------------------------------------------------

RECORTES = ("BR", "INT_acessivel", "INT_restrito", "todos")


def filtrar_recorte(
    vagas: list[dict], recorte: str, perfil: dict | None = None,
    elegibilidade: dict | None = None, so_elegiveis: bool = False,
) -> list[dict]:
    perfil = perfil or {}
    if recorte == "BR":
        base = [v for v in vagas if v.get("mercado") == "BR"]
    elif recorte == "INT_acessivel":
        base = [v for v in vagas if v.get("mercado") == "INT" and _cidadania_residencia_compativel(v, perfil)]
    elif recorte == "INT_restrito":
        base = [v for v in vagas if v.get("mercado") == "INT" and not _cidadania_residencia_compativel(v, perfil)]
    elif recorte == "todos":
        base = list(vagas)
    else:
        raise ValueError(f"Recorte desconhecido: {recorte}")

    if so_elegiveis and elegibilidade is not None:
        base = [v for v in base if elegibilidade.get(v["id"], {}).get("elegivel") != "nao"]
    return base


# ---------------------------------------------------------------------------
# Unidades de exigência (seção 12) — usadas por match_vaga/cobertura/lacunas
# ---------------------------------------------------------------------------

def unidades_de_exigencia(vaga: dict) -> list[dict]:
    unidades = []
    vistos_grupos = set()
    for s in vaga.get("skills") or []:
        grupo = s.get("grupo_alternativo")
        if grupo:
            if grupo in vistos_grupos:
                continue
            vistos_grupos.add(grupo)
            membros = [m for m in vaga["skills"] if m.get("grupo_alternativo") == grupo]
            unidades.append({
                "peso": membros[0]["peso"],
                "membros": [(m["categoria"], m["skill"]) for m in membros],
            })
        else:
            unidades.append({"peso": s["peso"], "membros": [(s["categoria"], s["skill"])]})
    return unidades


def match_vaga(vaga: dict, skills_cv: set[tuple[str, str]]) -> float | None:
    unidades = unidades_de_exigencia(vaga)
    total = sum(u["peso"] for u in unidades)
    if total == 0:
        return None
    atendido = sum(u["peso"] for u in unidades if any(m in skills_cv for m in u["membros"]))
    return atendido / total


def cobertura_geral(vagas: list[dict], skills_cv: set[tuple[str, str]]) -> float | None:
    total = 0.0
    atendido = 0.0
    for vaga in vagas:
        for u in unidades_de_exigencia(vaga):
            total += u["peso"]
            if any(m in skills_cv for m in u["membros"]):
                atendido += u["peso"]
    if total == 0:
        return None
    return atendido / total


def calcular_lacunas(vagas: list[dict], skills_cv: set[tuple[str, str]]) -> list[dict]:
    """Lacuna numa vaga = skill ausente do CV cujo grupo (se houver) também
    não tem nenhum membro no CV. score_lacuna = soma dos pesos nas vagas
    onde é lacuna ÷ nº de vagas ativas (do recorte recebido)."""
    soma_pesos: dict[tuple[str, str], float] = defaultdict(float)
    n_vagas_lacuna: dict[tuple[str, str], int] = defaultdict(int)
    n_total = len(vagas)

    for vaga in vagas:
        skills_vaga = vaga.get("skills") or []
        grupos_atendidos = set()
        for s in skills_vaga:
            grupo = s.get("grupo_alternativo")
            if grupo and grupo not in grupos_atendidos:
                membros_grupo = [(m["categoria"], m["skill"]) for m in skills_vaga if m.get("grupo_alternativo") == grupo]
                if any(m in skills_cv for m in membros_grupo):
                    grupos_atendidos.add(grupo)

        for s in skills_vaga:
            chave = (s["categoria"], s["skill"])
            if chave in skills_cv:
                continue
            grupo = s.get("grupo_alternativo")
            if grupo and grupo in grupos_atendidos:
                continue
            soma_pesos[chave] += s["peso"]
            n_vagas_lacuna[chave] += 1

    if n_total == 0:
        return []
    return [
        {
            "categoria": chave[0], "skill": chave[1],
            "score_lacuna": total / n_total, "n_vagas": n_vagas_lacuna[chave],
        }
        for chave, total in soma_pesos.items()
    ]


# ---------------------------------------------------------------------------
# Ranking de mercado (cada skill conta individualmente, mesmo em grupo)
# ---------------------------------------------------------------------------

def ranking_skills(vagas: list[dict]) -> list[dict]:
    soma_pesos: dict[tuple[str, str], float] = defaultdict(float)
    vagas_com_skill: dict[tuple[str, str], set] = defaultdict(set)
    n_total = len(vagas)

    for vaga in vagas:
        for s in vaga.get("skills") or []:
            chave = (s["categoria"], s["skill"])
            soma_pesos[chave] += s["peso"]
            vagas_com_skill[chave].add(vaga["id"])

    if n_total == 0:
        return []

    resultado = []
    for chave, soma in soma_pesos.items():
        n_vagas = len(vagas_com_skill[chave])
        resultado.append({
            "categoria": chave[0], "skill": chave[1],
            "n_vagas": n_vagas,
            "percentual": n_vagas / n_total,
            "score": soma / n_total,
        })
    resultado.sort(key=lambda r: (-r["score"], r["skill"]))
    return resultado


def ranking_categorias(vagas: list[dict]) -> list[dict]:
    soma_pesos: dict[str, float] = defaultdict(float)
    vagas_com_categoria: dict[str, set] = defaultdict(set)
    n_total = len(vagas)

    for vaga in vagas:
        for s in vaga.get("skills") or []:
            soma_pesos[s["categoria"]] += s["peso"]
            vagas_com_categoria[s["categoria"]].add(vaga["id"])

    if n_total == 0:
        return []

    resultado = [
        {
            "categoria": categoria,
            "n_vagas": len(vagas_com_categoria[categoria]),
            "percentual": len(vagas_com_categoria[categoria]) / n_total,
            "score": soma / n_total,
        }
        for categoria, soma in soma_pesos.items()
    ]
    resultado.sort(key=lambda r: -r["score"])
    return resultado


# ---------------------------------------------------------------------------
# "Em alta" (seção 12)
# ---------------------------------------------------------------------------

def tendencia_skills(vagas: list[dict], data_referencia: date) -> dict:
    vagas_validas = [v for v in vagas if not v.get("data_estimada") and v.get("data")]

    def _parse(d):
        try:
            return date.fromisoformat(d)
        except (TypeError, ValueError):
            return None

    janela_recente = []
    janela_anterior = []
    for v in vagas_validas:
        d = _parse(v["data"])
        if d is None:
            continue
        dias = (data_referencia - d).days
        if 0 <= dias < 30:
            janela_recente.append(v)
        elif 30 <= dias < 60:
            janela_anterior.append(v)

    if len(janela_recente) < 10 or len(janela_anterior) < 10:
        return {"status": "dados insuficientes"}

    def _participacao(vagas_janela):
        contagem: dict[tuple[str, str], int] = defaultdict(int)
        for v in vagas_janela:
            for chave in {(s["categoria"], s["skill"]) for s in (v.get("skills") or [])}:
                contagem[chave] += 1
        n = len(vagas_janela)
        return contagem, n

    contagem_recente, n_recente = _participacao(janela_recente)
    contagem_anterior, n_anterior = _participacao(janela_anterior)

    tendencias = []
    for chave in set(contagem_recente) | set(contagem_anterior):
        total_ocorrencias = contagem_recente.get(chave, 0) + contagem_anterior.get(chave, 0)
        if total_ocorrencias < 5:
            continue
        p_recente = contagem_recente.get(chave, 0) / n_recente
        p_anterior = contagem_anterior.get(chave, 0) / n_anterior
        tendencias.append({
            "categoria": chave[0], "skill": chave[1],
            "participacao_recente": p_recente, "participacao_anterior": p_anterior,
            "variacao": p_recente - p_anterior,
        })
    tendencias.sort(key=lambda t: -t["variacao"])
    return {"status": "ok", "tendencias": tendencias}


# ---------------------------------------------------------------------------
# Coocorrência
# ---------------------------------------------------------------------------

def coocorrencia_skills(vagas: list[dict], top: int = 20) -> list[dict]:
    contagem: dict[tuple, int] = defaultdict(int)
    for vaga in vagas:
        chaves = sorted({(s["categoria"], s["skill"]) for s in (vaga.get("skills") or [])})
        for i in range(len(chaves)):
            for j in range(i + 1, len(chaves)):
                contagem[(chaves[i], chaves[j])] += 1
    pares = sorted(contagem.items(), key=lambda kv: -kv[1])[:top]
    return [{"skill_a": a[1], "skill_b": b[1], "n_vagas": n} for (a, b), n in pares]


# ---------------------------------------------------------------------------
# Distribuições
# ---------------------------------------------------------------------------

def distribuicao(vagas: list[dict], campo: str) -> dict:
    n = len(vagas)
    if n == 0:
        return {}
    contagem = Counter(v.get(campo) or "não informado" for v in vagas)
    return {chave: {"n": c, "percentual": c / n} for chave, c in contagem.items()}


def distribuicao_restricoes(vagas: list[dict]) -> dict:
    n = len(vagas)
    if n == 0:
        return {}
    contagem = Counter()
    for v in vagas:
        r = v.get("restricoes") or {}
        if r.get("cidadania"):
            contagem["exige cidadania"] += 1
        if r.get("residencia"):
            contagem["exige residência"] += 1
        if r.get("clearance"):
            contagem["exige clearance"] += 1
        if not any((r.get("cidadania"), r.get("residencia"), r.get("clearance"))):
            contagem["sem restrição"] += 1
    return {chave: {"n": c, "percentual": c / n} for chave, c in contagem.items()}


# ---------------------------------------------------------------------------
# Comparações
# ---------------------------------------------------------------------------

def comparar_br_int(vagas: list[dict], top: int = 20) -> list[dict]:
    br = [v for v in vagas if v.get("mercado") == "BR"]
    intl = [v for v in vagas if v.get("mercado") == "INT"]
    rank_br = {(r["categoria"], r["skill"]): r["percentual"] for r in ranking_skills(br)}
    rank_int = {(r["categoria"], r["skill"]): r["percentual"] for r in ranking_skills(intl)}

    diffs = []
    for chave in set(rank_br) | set(rank_int):
        p_br = rank_br.get(chave, 0.0)
        p_int = rank_int.get(chave, 0.0)
        diffs.append({"categoria": chave[0], "skill": chave[1], "br": p_br, "int": p_int, "diferenca": p_br - p_int})
    diffs.sort(key=lambda d: -abs(d["diferenca"]))
    return diffs[:top]


def comparar_familias(vagas: list[dict], top_skills: int = 10) -> dict:
    por_familia: dict[str, list] = defaultdict(list)
    for v in vagas:
        por_familia[v.get("familia_cargo") or "outro"].append(v)
    return {
        familia: {"n_vagas": len(lista), "top_skills": ranking_skills(lista)[:top_skills]}
        for familia, lista in por_familia.items()
    }


# ---------------------------------------------------------------------------
# Faixas salariais (sem converter moedas)
# ---------------------------------------------------------------------------

def faixas_salariais(vagas: list[dict]) -> list[dict]:
    grupos: dict[tuple, list] = defaultdict(list)
    for v in vagas:
        sal = v.get("salario")
        if not sal:
            continue
        valores = [x for x in (sal.get("min"), sal.get("max")) if x is not None]
        if not valores:
            continue
        representativo = sum(valores) / len(valores)
        grupos[(sal.get("moeda"), sal.get("periodo"))].append(representativo)

    resultado = []
    for (moeda, periodo), valores in grupos.items():
        resultado.append({
            "moeda": moeda, "periodo": periodo, "n": len(valores),
            "min": min(valores), "mediana": statistics.median(valores), "max": max(valores),
        })
    resultado.sort(key=lambda r: (r["moeda"] or "", r["periodo"] or ""))
    return resultado


# ---------------------------------------------------------------------------
# Qualidade dos dados
# ---------------------------------------------------------------------------

def qualidade_dados(vagas: list[dict]) -> dict:
    n = len(vagas)
    campos_nulos = Counter()
    for v in vagas:
        for campo, valor in v.items():
            if valor is None:
                campos_nulos[campo] += 1
    return {
        "n_vagas": n,
        "possivelmente_expiradas": sum(1 for v in vagas if v.get("possivelmente_expirada")),
        "datas_estimadas": sum(1 for v in vagas if v.get("data_estimada")),
        "anos_ambiguos": sum(1 for v in vagas if (v.get("anos_experiencia") or {}).get("ambiguo")),
        "campos_nulos_mais_frequentes": [{"campo": c, "n": qt} for c, qt in campos_nulos.most_common(10)],
    }


# ---------------------------------------------------------------------------
# Score de perfil (inspirado no SSI do LinkedIn — seção "Meu perfil")
# ---------------------------------------------------------------------------

CATEGORIA_SOFT_SKILLS = "Soft skills/relatórios"

_PESO_HARD_SKILLS = 0.55
_PESO_SOFT_SKILLS = 0.20
_PESO_COMPLETUDE = 0.25


def _cobertura_por_categoria(vagas: list[dict], skills_cv: set[tuple[str, str]], categoria: str) -> float | None:
    total = 0.0
    atendido = 0.0
    for vaga in vagas:
        for u in unidades_de_exigencia(vaga):
            if not any(m[0] == categoria for m in u["membros"]):
                continue
            total += u["peso"]
            if any(m in skills_cv for m in u["membros"]):
                atendido += u["peso"]
    if total == 0:
        return None
    return atendido / total


def _completude_perfil_profissional(perfil_profissional: dict) -> float:
    perfil_profissional = perfil_profissional or {}
    campos = [
        bool(perfil_profissional.get("headline")),
        bool(perfil_profissional.get("resumo")),
        bool(perfil_profissional.get("experiencias")),
        bool(perfil_profissional.get("educacao")),
        bool(perfil_profissional.get("skills_linkedin")),
        bool(perfil_profissional.get("certificacoes")),
    ]
    return sum(campos) / len(campos) * 100


def calcular_score_perfil(
    perfil_profissional: dict, skills_cv: set[tuple[str, str]], vagas: list[dict],
) -> dict:
    """Score 0-100 combinando cobertura de hard skills do mercado (55%),
    cobertura de soft skills (20%) e completude do perfil (25%) — mesma
    referência do SSI do LinkedIn: >= 50 é considerado bom."""
    cobertura_hard = cobertura_geral(vagas, skills_cv)
    hard_pct = (cobertura_hard or 0.0) * 100

    cobertura_soft = _cobertura_por_categoria(vagas, skills_cv, CATEGORIA_SOFT_SKILLS)
    soft_pct = (cobertura_soft or 0.0) * 100 if cobertura_soft is not None else None

    completude_pct = _completude_perfil_profissional(perfil_profissional)

    score = round(
        hard_pct * _PESO_HARD_SKILLS
        + (soft_pct or 0.0) * _PESO_SOFT_SKILLS
        + completude_pct * _PESO_COMPLETUDE
    )

    perfil_profissional = perfil_profissional or {}
    sugestoes = []
    if not perfil_profissional.get("headline"):
        sugestoes.append("Adicione um headline profissional (o que você faz + especialidade).")
    if not perfil_profissional.get("resumo"):
        sugestoes.append("Escreva um resumo/about destacando sua experiência.")
    if not perfil_profissional.get("experiencias"):
        sugestoes.append("Cadastre suas experiências profissionais.")
    if not perfil_profissional.get("skills_linkedin") and not perfil_profissional.get("certificacoes"):
        sugestoes.append("Importe ou liste suas skills/certificações autodeclaradas.")
    if hard_pct < 50:
        sugestoes.append(
            f"Sua cobertura de hard skills do mercado está em {hard_pct:.0f}% — veja as lacunas na aba Meu CV."
        )
    if cobertura_soft is not None and soft_pct < 50:
        sugestoes.append(
            "Poucas soft skills (comunicação, mentoria, relatórios) aparecem no seu CV — "
            "o mercado pede isso com frequência."
        )
    if not sugestoes:
        sugestoes.append("Perfil em bom estado — continue atualizando conforme surgem novas vagas.")

    return {
        "score": max(0, min(100, score)),
        "classificacao": "bom" if score >= 50 else "a melhorar",
        "hard_skills_pct": round(hard_pct),
        "soft_skills_pct": round(soft_pct) if soft_pct is not None else None,
        "completude_pct": round(completude_pct),
        "sugestoes": sugestoes,
    }
