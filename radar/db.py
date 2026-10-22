"""Persistência em SQLite — substitui data/vagas.json e os JSON mutáveis em
privado/ (perfil, elegibilidade, histórico). Os arquivos de configuração
editados à mão (data/skills.json, secoes.json, ruido.json, filtros.json,
familias.json, fontes.json) continuam em JSON: são taxonomia/configuração
versionável, não dados que o app grava.

Cada "dados"/"conteudo" guarda o dict inteiro como JSON — mantém a mesma
estrutura usada no resto do projeto (parser.montar_vaga etc.), só troca
onde ela é persistida. Colunas simples (id, chave_dedup...) existem só
para index/lookup rápido."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id TEXT PRIMARY KEY,
    chave_dedup TEXT UNIQUE NOT NULL,
    dados TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS perfil (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dados TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS perfil_profissional (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    dados TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS elegibilidade (
    vaga_id TEXT PRIMARY KEY,
    dados TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historico (
    data TEXT NOT NULL,
    recorte TEXT NOT NULL,
    dados TEXT NOT NULL,
    PRIMARY KEY (data, recorte)
);
"""

PERFIL_PADRAO = {
    "cidadanias": ["BR"], "residencia": "BR", "clearances": [],
    "aceita_relocacao": False, "idiomas": {"pt": "nativo", "en": "intermediario"},
}


def conectar(caminho_db: Path) -> sqlite3.Connection:
    caminho_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho_db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Vagas
# ---------------------------------------------------------------------------

def contar_vagas(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM vagas").fetchone()["n"]


def listar_vagas(conn: sqlite3.Connection) -> list[dict]:
    linhas = conn.execute("SELECT dados FROM vagas").fetchall()
    return [json.loads(l["dados"]) for l in linhas]


def obter_vaga(conn: sqlite3.Connection, vaga_id: str) -> dict | None:
    linha = conn.execute("SELECT dados FROM vagas WHERE id = ?", (vaga_id,)).fetchone()
    return json.loads(linha["dados"]) if linha else None


def salvar_vagas_em_lote(conn: sqlite3.Connection, vagas: list[dict]) -> None:
    # chave_dedup cai para o próprio id quando ausente (ex.: dicts mínimos de
    # teste) — vagas reais sempre trazem chave_dedup (parser.montar_vaga).
    conn.executemany(
        "INSERT INTO vagas (id, chave_dedup, dados) VALUES (:id, :chave_dedup, :dados) "
        "ON CONFLICT(id) DO UPDATE SET chave_dedup = excluded.chave_dedup, dados = excluded.dados",
        [
            {"id": v["id"], "chave_dedup": v.get("chave_dedup") or v["id"], "dados": json.dumps(v, ensure_ascii=False)}
            for v in vagas
        ],
    )
    conn.commit()


def substituir_todas_as_vagas(conn: sqlite3.Connection, vagas: list[dict]) -> None:
    """DELETE + reinsert — mesma semântica de 'sobrescrever tudo' que a
    escrita atômica de data/vagas.json tinha. Ok para o volume de uma vaga
    pessoal (centenas, não milhões, de registros)."""
    conn.execute("DELETE FROM vagas")
    if vagas:
        salvar_vagas_em_lote(conn, vagas)
    else:
        conn.commit()


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def obter_perfil(conn: sqlite3.Connection) -> dict | None:
    linha = conn.execute("SELECT dados FROM perfil WHERE id = 1").fetchone()
    return json.loads(linha["dados"]) if linha else None


def salvar_perfil(conn: sqlite3.Connection, perfil: dict) -> None:
    conn.execute(
        "INSERT INTO perfil (id, dados) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET dados = excluded.dados",
        (json.dumps(perfil, ensure_ascii=False),),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Perfil profissional (estilo LinkedIn — nome, headline, experiências...)
# ---------------------------------------------------------------------------

def obter_perfil_profissional(conn: sqlite3.Connection) -> dict | None:
    linha = conn.execute("SELECT dados FROM perfil_profissional WHERE id = 1").fetchone()
    return json.loads(linha["dados"]) if linha else None


def salvar_perfil_profissional(conn: sqlite3.Connection, perfil_profissional: dict) -> None:
    conn.execute(
        "INSERT INTO perfil_profissional (id, dados) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET dados = excluded.dados",
        (json.dumps(perfil_profissional, ensure_ascii=False),),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Elegibilidade
# ---------------------------------------------------------------------------

def obter_elegibilidade(conn: sqlite3.Connection) -> dict:
    linhas = conn.execute("SELECT vaga_id, dados FROM elegibilidade").fetchall()
    return {l["vaga_id"]: json.loads(l["dados"]) for l in linhas}


def salvar_elegibilidade(conn: sqlite3.Connection, elegibilidade: dict) -> None:
    conn.execute("DELETE FROM elegibilidade")
    if elegibilidade:
        conn.executemany(
            "INSERT INTO elegibilidade (vaga_id, dados) VALUES (?, ?)",
            [(vid, json.dumps(info, ensure_ascii=False)) for vid, info in elegibilidade.items()],
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Histórico (uma entrada por dia por recorte — sobrescreve a do mesmo dia)
# ---------------------------------------------------------------------------

def listar_historico(conn: sqlite3.Connection) -> list[dict]:
    linhas = conn.execute("SELECT dados FROM historico ORDER BY data").fetchall()
    return [json.loads(l["dados"]) for l in linhas]


def registrar_historico(conn: sqlite3.Connection, entrada: dict) -> None:
    conn.execute(
        "INSERT INTO historico (data, recorte, dados) VALUES (:data, :recorte, :dados) "
        "ON CONFLICT(data, recorte) DO UPDATE SET dados = excluded.dados",
        {"data": entrada["data"], "recorte": entrada["recorte"], "dados": json.dumps(entrada, ensure_ascii=False)},
    )
    conn.commit()
