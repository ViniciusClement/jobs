"""Parser do contrato de dados da vaga (seções 6, 7, 8, 9, 10, 11 do prompt mestre)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date

from radar import limpeza
from radar import skills as skills_mod

# ---------------------------------------------------------------------------
# Cabeçalho e divisão de arquivos (seção 6)
# ---------------------------------------------------------------------------

_RE_SEPARADOR_CABECALHO = re.compile(r"^-{3,}\s*$")
_RE_SEPARADOR_VAGAS = re.compile(r"^={3,}\s*VAGA\s*={3,}$", re.IGNORECASE)


def parse_cabecalho(bloco: str) -> tuple[dict, str]:
    """Separa o cabeçalho opcional (Empresa | Local | URL | ...) do corpo bruto."""
    linhas = bloco.split("\n")
    idx_sep = None
    for i, linha in enumerate(linhas[:15]):
        if _RE_SEPARADOR_CABECALHO.match(linha.strip()):
            idx_sep = i
            break
    if idx_sep is None:
        return {}, bloco.strip("\n")

    texto_cabecalho = "\n".join(linhas[:idx_sep])
    corpo = "\n".join(linhas[idx_sep + 1:])
    campos = {}
    for parte in texto_cabecalho.split("|"):
        if ":" not in parte:
            continue
        chave, _, valor = parte.partition(":")
        campos[chave.strip().lower()] = valor.strip()
    return campos, corpo.strip("\n")


def dividir_arquivo(texto: str) -> list[str]:
    """Divide um .txt com várias vagas separadas por '=== VAGA ==='."""
    linhas = texto.split("\n")
    blocos: list[str] = []
    atual: list[str] = []
    for linha in linhas:
        if _RE_SEPARADOR_VAGAS.match(linha.strip()):
            if atual:
                blocos.append("\n".join(atual).strip("\n"))
                atual = []
            continue
        atual.append(linha)
    if atual:
        blocos.append("\n".join(atual).strip("\n"))
    return [b for b in blocos if b.strip()]


# ---------------------------------------------------------------------------
# Seções (seção 9)
# ---------------------------------------------------------------------------

_RE_PARENTETICO_FINAL = re.compile(r"\s*\([^)]*\)\s*$")


def _normalizar_cabecalho_linha(linha: str) -> str:
    t = linha.strip()
    t = _RE_PARENTETICO_FINAL.sub("", t)
    return t.lower().rstrip(":?!.").strip()


def detectar_cabecalho_secao(linha: str, secoes_config: dict) -> str | None:
    norm = _normalizar_cabecalho_linha(linha)
    if not norm or len(norm) > 90:
        return None
    for categoria, frases in secoes_config.items():
        for frase in frases:
            f = frase.strip().lower().rstrip(":?!.").strip()
            if norm == f:
                return categoria
    return None


def detectar_secoes(corpo: str, secoes_config: dict) -> dict[str, list[str]]:
    """Segmenta o corpo em seções. O cabeçalho da seção tem prioridade sobre
    pistas de linha (seção 9): uma vez identificada a seção, a classe das
    skills nela é definida pela seção, não pelo texto da linha."""
    secoes: dict[str, list[str]] = {cat: [] for cat in secoes_config}
    secoes["_sem_secao"] = []
    atual = "_sem_secao"
    for linha in corpo.split("\n"):
        categoria = detectar_cabecalho_secao(linha, secoes_config)
        if categoria:
            atual = categoria
            continue
        secoes[atual].append(linha)
    return secoes


# ---------------------------------------------------------------------------
# Título e família de cargo
# ---------------------------------------------------------------------------

_RE_LABEL_TITULO = re.compile(r"^(?:position|title|job\s*title|role|cargo|vaga)\s*:\s*(.+)$", re.IGNORECASE)


def extrair_titulo(texto: str, secoes_config: dict | None = None) -> tuple[str | None, str | None]:
    """Título da vaga. Prioridade:
    1) um rótulo explícito ("Position: X", "Title: X", "Cargo: X"...) em
       qualquer lugar nas primeiras linhas — sinal mais confiável que existe;
    2) a primeira linha não vazia que NÃO seja um cabeçalho de seção já
       conhecido (ex.: "About the job", "About Us" — comuns em texto colado
       do LinkedIn antes do título real, ou quando o título nem foi colado).
    Sem (1) e sem um cabeçalho reconhecido para pular, cai no comportamento
    simples: primeira linha não vazia (pode não ser um título de verdade —
    não há como inferir com segurança o que não está explícito no texto)."""
    linhas = texto.split("\n")

    for linha in linhas[:40]:
        linha_strip = linha.strip()
        m = _RE_LABEL_TITULO.match(linha_strip)
        if m and m.group(1).strip():
            titulo_bruto = linha_strip
            titulo = re.split(r"\s+[-–|]\s+", m.group(1).strip())[0].strip()
            return titulo or None, titulo_bruto

    for linha in linhas:
        linha_strip = linha.strip()
        if not linha_strip:
            continue
        if secoes_config and detectar_cabecalho_secao(linha_strip, secoes_config):
            continue
        titulo_bruto = linha_strip
        titulo = re.split(r"\s+[-–|]\s+", titulo_bruto)[0].strip()
        # Linha longa demais pra ser um título de verdade (quase certo que é
        # uma frase/parágrafo, ex.: texto colado sem o título real incluído)
        # — melhor null do que inventar um "título" que é só a 1ª frase.
        if len(titulo) > 100:
            return None, titulo_bruto
        return titulo or None, titulo_bruto

    return None, None


def detectar_familia_cargo(titulo: str | None, familias_config: dict) -> str:
    if not titulo:
        return "outro"
    l = titulo.lower()
    for familia, termos in familias_config.items():
        if any(t in l for t in termos):
            return familia
    return "outro"


# ---------------------------------------------------------------------------
# Empregador (direto / agência / anônimo) e setor do cliente
# ---------------------------------------------------------------------------

_FRASES_AGENCIA = [
    "on behalf of our client", "em nome de nosso cliente", "a leading company",
    "confidential client", "our client is", "recruiting on behalf of",
    "staffing agency", "nome do cliente não pode ser divulgado",
]
_FRASES_ANONIMA = [
    "empresa confidencial", "confidential company", "we are unable to disclose the name",
    "empresa não divulgada",
]


def detectar_empregador(corpo: str, empresa_cabecalho: str | None) -> tuple[str | None, str | None]:
    l = corpo.lower()
    if any(f in l for f in _FRASES_AGENCIA):
        return None, "agencia"
    if any(f in l for f in _FRASES_ANONIMA):
        return None, "anonimo"
    if empresa_cabecalho:
        return empresa_cabecalho, "direto"
    return None, None


def detectar_ignorada(corpo: str, empresa_cabecalho: str | None, filtros_config: dict) -> tuple[bool, str | None]:
    texto = f"{empresa_cabecalho or ''}\n{corpo}".lower()
    for termo in filtros_config.get("termos_setor_publico", []):
        if termo.lower() in texto:
            return True, f"empregador público (termo: '{termo}')"
    return False, None


def detectar_setor_cliente(corpo: str, filtros_config: dict) -> str | None:
    l = corpo.lower()
    for termo in filtros_config.get("termos_governo_contratada", []):
        if termo.lower() in l:
            return "governo_contratada"
    return None


# ---------------------------------------------------------------------------
# Restrições (seção 7)
# ---------------------------------------------------------------------------

_RESTRICAO_CIDADANIA = [
    (re.compile(r"u\.?s\.?\s*citizen|cidadania\s+americana|cidad[ãa]o\s+americana?", re.IGNORECASE), "US"),
    (re.compile(r"green\s*card", re.IGNORECASE), "US"),
]
_RESTRICAO_RESIDENCIA = [
    (re.compile(r"must\s+currently\s+live\s+in\s+the\s+u\.?s\.?|must\s+reside\s+in\s+the\s+united\s+states", re.IGNORECASE), "US"),
    (re.compile(r"deve\s+residir\s+no\s+brasil|residente\s+no\s+brasil", re.IGNORECASE), "BR"),
]
_RESTRICAO_CLEARANCE = [
    (re.compile(r"top\s+secret", re.IGNORECASE), "ts"),
    (re.compile(r"\bsecret\s+clearance\b", re.IGNORECASE), "secret"),
    (re.compile(r"public\s+trust", re.IGNORECASE), "public_trust"),
]


def extrair_restricoes(corpo: str) -> tuple[dict, str | None]:
    cidadania: list[str] = []
    residencia = None
    clearance = None
    clearance_obrigatorio = None
    evidencias: list[str] = []

    for linha in corpo.split("\n"):
        l = linha.strip()
        if not l:
            continue
        for rx, codigo in _RESTRICAO_CIDADANIA:
            if rx.search(l) and codigo not in cidadania:
                cidadania.append(codigo)
                evidencias.append(l[:200])
        for rx, codigo in _RESTRICAO_RESIDENCIA:
            if rx.search(l) and residencia is None:
                residencia = codigo
                evidencias.append(l[:200])
        for rx, codigo in _RESTRICAO_CLEARANCE:
            if rx.search(l) and clearance is None:
                clearance = codigo
                clearance_obrigatorio = not any(p in l.lower() for p in skills_mod.PALAVRAS_DIFERENCIAL)
                evidencias.append(l[:200])

    restricoes = {
        "cidadania": cidadania or None,
        "residencia": residencia,
        "clearance": clearance,
        "clearance_obrigatorio": clearance_obrigatorio,
        "outras": [],
    }
    evidencia = " | ".join(dict.fromkeys(evidencias)) or None
    return restricoes, evidencia


# ---------------------------------------------------------------------------
# Senioridade
# ---------------------------------------------------------------------------

_SENIORIDADE_PADROES = [
    (re.compile(r"\best[áa]gio\b|\bintern(?:ship)?\b|\btrainee\b", re.IGNORECASE), "estágio"),
    (re.compile(r"\bj[úu]nior\b|\bjr\.?\b", re.IGNORECASE), "júnior"),
    (re.compile(r"\bpleno\b|\bmid[ -]level\b", re.IGNORECASE), "pleno"),
    (re.compile(r"\bs[êe]nior\b|\bsr\.?\b", re.IGNORECASE), "sênior"),
    (re.compile(r"\bespecialista\b|\bspecialist\b|\bprincipal\b", re.IGNORECASE), "especialista"),
    (re.compile(r"\blead\b|\bl[íi]der\s+t[ée]cnico\b", re.IGNORECASE), "lead"),
]


def detectar_senioridade(titulo: str | None, corpo: str) -> tuple[str | None, str | None]:
    primeira_linha = corpo.split("\n")[0] if corpo else ""
    alvo = f"{titulo or ''} {primeira_linha}"
    for rx, categoria in _SENIORIDADE_PADROES:
        m = rx.search(alvo)
        if m:
            return categoria, m.group(0)
    return None, None


# ---------------------------------------------------------------------------
# Anos de experiência
# ---------------------------------------------------------------------------

_NUMEROS_EXTENSO = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "três": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}

_RE_ANOS_AMBIGUO = re.compile(r"(\d+)\s*years?\s*\+\s*additional\s*\(?(\d+)\)?", re.IGNORECASE)
_RE_ANOS_FAIXA = re.compile(r"(\d+)\s*(?:[-–—]|a)\s*(\d+)\+?\s*(?:years?|anos?)", re.IGNORECASE)
_RE_ANOS_MAIS = re.compile(r"(\d+)\+\s*(?:years?|anos?)", re.IGNORECASE)
_RE_ANOS_SIMPLES = re.compile(r"(\d+)\s*(?:years?|anos?)\s+(?:of\s+)?experi[eê]nc", re.IGNORECASE)
_RE_ANOS_EXTENSO = re.compile(
    r"\b(" + "|".join(sorted(_NUMEROS_EXTENSO, key=len, reverse=True)) + r")\s+years?\b", re.IGNORECASE
)


def extrair_anos_experiencia(corpo: str) -> dict | None:
    m = _RE_ANOS_AMBIGUO.search(corpo)
    if m:
        return {"min": None, "max": None, "texto": m.group(0), "ambiguo": True}
    m = _RE_ANOS_FAIXA.search(corpo)
    if m:
        return {"min": int(m.group(1)), "max": int(m.group(2)), "texto": m.group(0), "ambiguo": False}
    m = _RE_ANOS_MAIS.search(corpo)
    if m:
        return {"min": int(m.group(1)), "max": None, "texto": m.group(0), "ambiguo": False}
    m = _RE_ANOS_SIMPLES.search(corpo)
    if m:
        n = int(m.group(1))
        return {"min": n, "max": n, "texto": m.group(0), "ambiguo": False}
    m = _RE_ANOS_EXTENSO.search(corpo)
    if m:
        n = _NUMEROS_EXTENSO[m.group(1).lower()]
        return {"min": n, "max": n, "texto": m.group(0), "ambiguo": False}
    return None


# ---------------------------------------------------------------------------
# Salário
# ---------------------------------------------------------------------------

_RE_SALARIO_FAIXA_USD = re.compile(r"\$\s?([\d,]+)\s*[-–]\s*\$?\s?([\d,]+)")
_RE_SALARIO_UP_TO = re.compile(r"up to \$\s?([\d,]+)(k)?", re.IGNORECASE)
_RE_SALARIO_BRL = re.compile(r"R\$\s?([\d.,]+)\s*(?:a|à|-)\s*R?\$?\s?([\d.,]+)", re.IGNORECASE)


def _num_brl(s: str) -> float:
    s = s.strip()
    if "," in s and "." in s:
        return float(s.replace(".", "").replace(",", "."))
    if "." in s:
        partes = s.split(".")
        if len(partes[-1]) == 3:
            return int(s.replace(".", ""))
        return float(s)
    return float(s)


def _detectar_periodo_salario(corpo: str, pos: int) -> str:
    janela = corpo[pos:pos + 40].lower()
    if "year" in janela or "ano" in janela or "/yr" in janela:
        return "ano"
    if "month" in janela or "mês" in janela or "mes" in janela or "/mo" in janela:
        return "mes"
    if "hour" in janela or "hora" in janela or "/hr" in janela:
        return "hora"
    return "ano"


def extrair_salario(corpo: str) -> dict | None:
    m = _RE_SALARIO_FAIXA_USD.search(corpo)
    if m:
        return {
            "min": int(m.group(1).replace(",", "")),
            "max": int(m.group(2).replace(",", "")),
            "moeda": "USD",
            "periodo": _detectar_periodo_salario(corpo, m.end()),
            "texto": m.group(0),
        }
    m = _RE_SALARIO_UP_TO.search(corpo)
    if m:
        valor = int(m.group(1).replace(",", ""))
        if m.group(2):
            valor *= 1000
        return {
            "min": None, "max": valor, "moeda": "USD",
            "periodo": _detectar_periodo_salario(corpo, m.end()), "texto": m.group(0),
        }
    m = _RE_SALARIO_BRL.search(corpo)
    if m:
        return {
            "min": _num_brl(m.group(1)),
            "max": _num_brl(m.group(2)),
            "moeda": "BRL",
            "periodo": _detectar_periodo_salario(corpo, m.end()),
            "texto": m.group(0),
        }
    return None


# ---------------------------------------------------------------------------
# Contrato / vínculo
# ---------------------------------------------------------------------------

_PADROES_VINCULO = [
    (re.compile(r"part[ -]time|meio\s+per[ií]odo", re.IGNORECASE), "part_time"),
    (re.compile(r"full[ -]time|tempo\s+integral", re.IGNORECASE), "full_time"),
    (re.compile(r"direct\s+hire|contrata[çc][ãa]o\s+direta", re.IGNORECASE), "direct_hire"),
    (re.compile(r"\bpermanent\b|\befetivo\b", re.IGNORECASE), "permanent"),
    (re.compile(r"\bcontract\b|\btemporary\b|tempor[áa]rio", re.IGNORECASE), "contract"),
]


def detectar_contrato_vinculo(corpo: str) -> tuple[str | None, str | None]:
    contrato = None
    if re.search(r"\bclt\b", corpo, re.IGNORECASE):
        contrato = "CLT"
    elif re.search(r"\bpj\b|pessoa\s+jur[ií]dica", corpo, re.IGNORECASE):
        contrato = "PJ"

    tipo_vinculo = None
    for rx, valor in _PADROES_VINCULO:
        if rx.search(corpo):
            tipo_vinculo = valor
            break
    return contrato, tipo_vinculo


# ---------------------------------------------------------------------------
# Período de contrato / datas
# ---------------------------------------------------------------------------

_RE_PERIODO_ISO = re.compile(r"(\d{4})-(\d{2})\s*(?:a|to|[-–])\s*(\d{4})-(\d{2})")


def extrair_periodo_contrato(corpo: str, data_processamento: date) -> tuple[dict | None, bool]:
    m = _RE_PERIODO_ISO.search(corpo)
    if not m:
        return None, False
    inicio = f"{m.group(1)}-{m.group(2)}"
    fim = f"{m.group(3)}-{m.group(4)}"
    try:
        fim_date = date(int(m.group(3)), int(m.group(4)), 28)
    except ValueError:
        fim_date = None
    expirada = bool(fim_date and fim_date < data_processamento)
    return {"inicio": inicio, "fim": fim}, expirada


_RE_POSTED_DIAS = re.compile(r"posted\s+\d+\+?\s*days?\s+ago", re.IGNORECASE)
_RE_DATA_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def extrair_datas(corpo: str, data_cabecalho: str | None, data_processamento: date) -> tuple[str, bool, list[str]]:
    datas_no_texto = _RE_DATA_ISO.findall(corpo)
    if data_cabecalho:
        return data_cabecalho, False, datas_no_texto
    if _RE_POSTED_DIAS.search(corpo):
        return data_processamento.isoformat(), True, datas_no_texto
    if datas_no_texto:
        return datas_no_texto[0], False, datas_no_texto
    return data_processamento.isoformat(), True, datas_no_texto


# ---------------------------------------------------------------------------
# Idioma
# ---------------------------------------------------------------------------

_PALAVRAS_PT = {
    "de", "para", "com", "não", "voce", "você", "é", "são", "que", "uma", "este",
    "esta", "vaga", "empresa", "experiência", "ou", "em", "os", "as", "do", "da",
}
_PALAVRAS_EN = {
    "the", "and", "with", "you", "is", "are", "that", "this", "role", "company",
    "experience", "we", "our", "of", "to", "for",
}


def detectar_idioma(corpo: str) -> str:
    tokens = re.findall(r"[a-zà-öø-ÿ]+", corpo.lower())
    pt = sum(1 for t in tokens if t in _PALAVRAS_PT)
    en = sum(1 for t in tokens if t in _PALAVRAS_EN)
    return "pt" if pt >= en else "en"


# ---------------------------------------------------------------------------
# Modalidade
# ---------------------------------------------------------------------------

def detectar_modalidade(corpo: str, pistas_hashtag: list[str]) -> tuple[str | None, bool, str | None]:
    l = corpo.lower()
    explicita = None
    if re.search(r"\bremoto\b|\bremote\b", l):
        explicita = "remoto"
    elif re.search(r"h[íi]brido|hybrid", l):
        explicita = "híbrido"
    elif re.search(r"presencial|on-?site|in-office", l):
        explicita = "presencial"

    pista = pistas_hashtag[0] if pistas_hashtag else None
    conflito = bool(explicita and pista and explicita != pista)
    modalidade = explicita or pista

    escopo_remoto = None
    if modalidade == "remoto":
        if re.search(r"remote\s+worldwide|remoto\s+global|\banywhere\b", l):
            escopo_remoto = "global"
        elif re.search(r"remote\s+(?:within\s+)?(?:the\s+)?u\.?s\.?\b", l):
            escopo_remoto = "pais:US"
    return modalidade, conflito, escopo_remoto


# ---------------------------------------------------------------------------
# Contato do recrutador (fica só em data/vagas.json)
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_TELEFONE = re.compile(r"\(?\d{2,3}\)?[\s.-]\d{3,5}[\s.-]\d{4}")


def extrair_contato_recrutador(corpo: str) -> dict | None:
    emails = _RE_EMAIL.findall(corpo)
    telefones = _RE_TELEFONE.findall(corpo)
    if not emails and not telefones:
        return None
    return {"emails": emails, "telefones": telefones}


# ---------------------------------------------------------------------------
# Identidade (id / chave_dedup / slug)
# ---------------------------------------------------------------------------

def gerar_chave_dedup(url_normalizada: str | None, texto_limpo: str) -> str:
    if url_normalizada:
        return url_normalizada
    return "sha1:" + hashlib.sha1(texto_limpo.encode("utf-8")).hexdigest()


def gerar_id(chave_dedup: str) -> str:
    return "v-" + hashlib.sha1(chave_dedup.encode("utf-8")).hexdigest()[:8]


def gerar_slug(titulo: str | None, empresa: str | None) -> str:
    base = f"{titulo or 'vaga'}-{empresa or ''}".strip("-")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = base.lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    return base[:60].rstrip("-") or "vaga"


# ---------------------------------------------------------------------------
# Montagem completa da vaga
# ---------------------------------------------------------------------------

def montar_vaga(bloco_bruto: str, data_processamento: date, config: dict) -> dict:
    """config precisa ter as chaves: ruido, secoes, filtros, familias, skills_regras."""
    campos_cabecalho, corpo_bruto = parse_cabecalho(bloco_bruto)

    texto_limpo, pistas_hashtag = limpeza.normalizar_texto_com_ruido(corpo_bruto, config["ruido"])

    url_normalizada = limpeza.normalizar_url(campos_cabecalho.get("url"))

    titulo, titulo_bruto = extrair_titulo(texto_limpo, config["secoes"])
    familia_cargo = detectar_familia_cargo(titulo, config["familias"])

    empresa_cabecalho = campos_cabecalho.get("empresa") or None
    empresa, empregador_tipo = detectar_empregador(texto_limpo, empresa_cabecalho)

    ignorada, ignorada_motivo = detectar_ignorada(texto_limpo, empresa_cabecalho, config["filtros"])
    setor_cliente = None if ignorada else detectar_setor_cliente(texto_limpo, config["filtros"])

    locais = [campos_cabecalho["local"]] if campos_cabecalho.get("local") else []
    mercado = campos_cabecalho.get("mercado")
    mercado = mercado.upper() if mercado else None

    modalidade, modalidade_conflito, escopo_remoto = detectar_modalidade(texto_limpo, pistas_hashtag)
    restricoes, restricoes_evidencia = extrair_restricoes(texto_limpo)
    senioridade, senioridade_texto = detectar_senioridade(titulo, texto_limpo)
    anos_experiencia = extrair_anos_experiencia(texto_limpo)
    salario = extrair_salario(texto_limpo)
    contrato, tipo_vinculo = detectar_contrato_vinculo(texto_limpo)
    periodo_contrato, possivelmente_expirada = extrair_periodo_contrato(texto_limpo, data_processamento)

    data_cabecalho = campos_cabecalho.get("data") or None
    data, data_estimada, datas_no_texto = extrair_datas(texto_limpo, data_cabecalho, data_processamento)

    idioma = detectar_idioma(texto_limpo)
    origem = campos_cabecalho.get("origem") or None
    status = campos_cabecalho.get("status") or "novo"

    secoes = detectar_secoes(texto_limpo, config["secoes"])
    secoes_dict = {
        chave: ("\n".join(secoes.get(chave, [])).strip() or None)
        for chave in ("descricao", "responsabilidades", "requisitos", "diferenciais", "beneficios", "sobre_empresa")
    }

    skills_encontradas = skills_mod.detectar_skills(secoes, config["skills_regras"])

    chave_dedup = gerar_chave_dedup(url_normalizada, texto_limpo)
    vaga_id = gerar_id(chave_dedup)
    slug = gerar_slug(titulo, empresa)
    contato_recrutador = extrair_contato_recrutador(texto_limpo)

    return {
        "id": vaga_id,
        "chave_dedup": chave_dedup,
        "possivel_duplicata_de": None,
        "titulo": titulo,
        "titulo_bruto": titulo_bruto,
        "familia_cargo": familia_cargo,
        "empresa": empresa,
        "empregador_tipo": empregador_tipo,
        "setor_cliente": setor_cliente,
        "locais": locais,
        "pais": [],
        "mercado": mercado,
        "modalidade": modalidade,
        "modalidade_conflito": modalidade_conflito,
        "escopo_remoto": escopo_remoto,
        "restricoes": restricoes,
        "restricoes_evidencia": restricoes_evidencia,
        "senioridade": senioridade,
        "senioridade_texto": senioridade_texto,
        "anos_experiencia": anos_experiencia,
        "salario": salario,
        "contrato": contrato,
        "tipo_vinculo": tipo_vinculo,
        "periodo_contrato": periodo_contrato,
        "datas_no_texto": datas_no_texto,
        "possivelmente_expirada": possivelmente_expirada,
        "data": data,
        "data_estimada": data_estimada,
        "idioma": idioma,
        "ingles_nivel": None,
        "origem": origem,
        "url": url_normalizada,
        "status": status,
        "notas": None,
        "ignorada": ignorada,
        "ignorada_motivo": ignorada_motivo,
        "secoes": secoes_dict,
        "skills": skills_encontradas,
        "texto_bruto": texto_limpo,
        "contato_recrutador": contato_recrutador,
        "slug": slug,
    }
