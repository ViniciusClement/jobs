"""Matcher de skills a partir da taxonomia em data/skills.json (seções 9, 10, 13, 14)."""

from __future__ import annotations

import json
import re
from pathlib import Path

PESOS = {"obrigatorio": 1.0, "mencionado": 0.6, "diferencial": 0.4}

SECOES_EXCLUIDAS = {"beneficios", "sobre_empresa"}

CLASSE_POR_SECAO = {
    "requisitos": "obrigatorio",
    "diferenciais": "diferencial",
    "responsabilidades": "mencionado",
    "descricao": "mencionado",
}

PALAVRAS_DIFERENCIAL = [
    "desejável", "desejavel", "nice to have", "a plus", "big plus", "plus",
    "preferred", "desired", "beneficial", "advantageous", "would be", "ideally",
]

PALAVRAS_OBRIGATORIO = [
    "obrigatório", "obrigatorio", "must have", "must", "required",
    "experiência com", "experiencia com", "are required",
]

GATILHOS_GRUPO = [
    r"one\s+or\s+more\s+of\s+the\s+following",
    r"must\s+have\s*\(?1\)?\s*of",
    r"any\s+of\s+the\s+following",
    r"\bany\s+of\b",
    r"\bou\s+equivalente\b",
    r"\be/ou\b",
]
_RE_GATILHOS_GRUPO = [re.compile(g, re.IGNORECASE) for g in GATILHOS_GRUPO]


def carregar_skills(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def compilar_regras(config_skills: dict) -> list[tuple[str, str, list[re.Pattern]]]:
    """Compila os padrões de cada skill. Sinônimos são sempre case-insensitive;
    regex explícitos e o nome-padrão (quando não há regex/sinônimo) respeitam
    'case_sensitive' — necessário para siglas curtas ambíguas (Go, C, NIST...)."""
    regras = []
    for categoria, skills in config_skills.items():
        for nome, cfg in skills.items():
            case_sensitive = cfg.get("case_sensitive", False)
            flags = 0 if case_sensitive else re.IGNORECASE
            regex_list = cfg.get("regex", [])
            sinonimos = cfg.get("sinonimos", [])
            patterns = [re.compile(r, flags) for r in regex_list]
            patterns += [re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE) for s in sinonimos]
            if not regex_list and not sinonimos:
                patterns.append(re.compile(r"\b" + re.escape(nome) + r"\b", flags))
            regras.append((categoria, nome, patterns))
    return regras


def classificar_linha_sem_cabecalho(linha: str) -> str:
    l = linha.lower()
    if any(p in l for p in PALAVRAS_DIFERENCIAL):
        return "diferencial"
    if any(p in l for p in PALAVRAS_OBRIGATORIO):
        return "obrigatorio"
    return "mencionado"


def _linha_eh_gatilho_grupo(linha: str) -> bool:
    return any(rx.search(linha) for rx in _RE_GATILHOS_GRUPO)


def detectar_skills(secoes: dict[str, list[str]], regras: list) -> list[dict]:
    """secoes: mapeamento secao -> lista de linhas (ver parser.detectar_secoes).
    'descricao'/'responsabilidades'/'requisitos'/'diferenciais' e '_sem_secao'
    são escaneadas; 'beneficios' e 'sobre_empresa' são excluídas (seção 9)."""
    encontrados: dict[tuple[str, str], dict] = {}
    grupo_contador = 0

    for secao_nome, linhas in secoes.items():
        if secao_nome in SECOES_EXCLUIDAS:
            continue
        for linha in linhas:
            if not linha.strip():
                continue

            if secao_nome == "_sem_secao":
                classe = classificar_linha_sem_cabecalho(linha)
            else:
                classe = CLASSE_POR_SECAO.get(secao_nome, "mencionado")
            peso = PESOS[classe]

            matches_na_linha = []
            for categoria, nome, patterns in regras:
                if any(p.search(linha) for p in patterns):
                    matches_na_linha.append((categoria, nome))

            if not matches_na_linha:
                continue

            grupo_id = None
            if _linha_eh_gatilho_grupo(linha):
                grupo_contador += 1
                grupo_id = f"g{grupo_contador}"

            evidencia = linha.strip()[:200]
            for categoria, nome in matches_na_linha:
                chave = (categoria, nome)
                existente = encontrados.get(chave)
                if existente is None or peso > existente["peso"]:
                    encontrados[chave] = {
                        "categoria": categoria,
                        "skill": nome,
                        "classe": classe,
                        "peso": peso,
                        "evidencia": evidencia,
                        "grupo_alternativo": grupo_id,
                    }
                elif grupo_id and existente.get("grupo_alternativo") is None:
                    existente["grupo_alternativo"] = grupo_id

    return list(encontrados.values())
