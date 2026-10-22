"""Sugestões de CV via IA — OPCIONAL (seção 1 da Fase 5).

Desligada por padrão: sem ANTHROPIC_API_KEY/ANTHROPIC_MODEL nem OLLAMA_URL/
OLLAMA_MODEL configuradas, `sugerir()` levanta um erro claro e o resto do
Radar de Vagas continua funcionando normalmente — nada aqui é exigido.

Nunca fixamos o nome de um modelo no código (seção 2 de princípios): o
modelo da Claude API vem SÓ de ANTHROPIC_MODEL; não há um padrão embutido.

O prompt enviado ao backend NUNCA leva texto bruto de vaga, contato de
recrutador, nem e-mail/telefone do CV — só o CV (com contato mascarado) e
agregados (skills/lacunas/títulos)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from radar.html import mascarar_contato

TIMEOUT_CLAUDE = 60
TIMEOUT_OLLAMA = 120


def _limpar_cv_para_prompt(cv_texto: str) -> str:
    return mascarar_contato(cv_texto) or ""


def _resumir_lacunas(lacunas: list[dict]) -> str:
    linhas = [
        f"- {l['categoria']} / {l['skill']} (score_lacuna={l['score_lacuna']:.2f})"
        for l in sorted(lacunas, key=lambda x: -x["score_lacuna"])[:20]
    ]
    return "\n".join(linhas) or "(nenhuma lacuna identificada)"


def _resumir_vagas_para_prompt(vagas: list[dict]) -> str:
    """Só título, família e nomes de skill — nunca texto_bruto/contato_recrutador,
    mesmo que estejam presentes nos dicts recebidos (defesa em profundidade)."""
    linhas = []
    for v in vagas[:30]:
        skills = ", ".join(sorted({s["skill"] for s in (v.get("skills") or [])}))
        titulo = v.get("titulo") or "(sem título)"
        familia = v.get("familia_cargo") or "outro"
        linhas.append(f"- {titulo} [{familia}]: {skills or '(sem skills detectadas)'}")
    return "\n".join(linhas) or "(nenhuma vaga agregada disponível)"


def montar_prompt(cv_texto: str, lacunas: list[dict], vagas: list[dict]) -> str:
    cv_seguro = _limpar_cv_para_prompt(cv_texto)
    return f"""Você é um assistente de carreira para a área de Red Team / Pentest / \
Segurança Ofensiva. Ajude a melhorar o resumo profissional e os bullets de \
experiência do CV abaixo.

REGRAS OBRIGATÓRIAS (não negociáveis):
1. NUNCA invente experiência, certificação, resultado ou métrica que não \
esteja explicitamente no CV abaixo. Você pode reescrever e melhorar a \
redação do que já existe, mas não pode adicionar fatos novos. Qualquer \
skill listada em "Lacunas" que não apareça no CV deve ir para uma seção \
separada "A desenvolver" — nunca disfarçada como experiência existente.
2. NUNCA sugira formas de contornar exigência de cidadania, residência ou \
clearance de segurança mencionadas no mercado. Essas vagas estão fora do \
alcance por ora; não dê conselhos sobre como "resolver" isso.
3. Use só as skills e os títulos agregados de mercado abaixo. Não existe \
texto bruto de vaga nem contato de recrutador disponível para você — não \
assuma nada além do que está nesta mensagem.

=== CV (e-mail e telefone já removidos) ===
{cv_seguro}

=== Lacunas identificadas (skills de mercado ausentes do CV) ===
{_resumir_lacunas(lacunas)}

=== Vagas de mercado (título, família e skills agregadas, sem texto bruto) ===
{_resumir_vagas_para_prompt(vagas)}

Gere, em português:
1. Um resumo profissional (3-4 frases), baseado só no que está no CV.
2. Bullets de experiência reescritos (mantendo os fatos do CV, só melhorando a redação).
3. Uma seção "A desenvolver" com as lacunas mais relevantes, deixando claro que ainda não são experiência comprovada.
"""


def _chamar_claude(prompt: str) -> str:
    chave = os.environ.get("ANTHROPIC_API_KEY")
    if not chave:
        raise RuntimeError("ANTHROPIC_API_KEY não definida — backend Claude não configurado.")
    modelo = os.environ.get("ANTHROPIC_MODEL")
    if not modelo:
        raise RuntimeError(
            "ANTHROPIC_MODEL não definida. O modelo nunca é fixado no código: "
            "defina a variável de ambiente ANTHROPIC_MODEL com o modelo desejado."
        )
    corpo = json.dumps({
        "model": modelo, "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=corpo,
        headers={"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_CLAUDE) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Claude API retornou HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"falha de rede ao chamar a Claude API: {exc.reason}") from exc
    return "".join(bloco.get("text", "") for bloco in dados.get("content", []))


def _chamar_ollama(prompt: str) -> str:
    url_base = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    modelo = os.environ.get("OLLAMA_MODEL")
    if not modelo:
        raise RuntimeError("OLLAMA_MODEL não definida — defina o modelo local a usar no Ollama.")
    corpo = json.dumps({"model": modelo, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        f"{url_base.rstrip('/')}/api/generate", data=corpo, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_OLLAMA) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama retornou HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"falha de rede ao chamar o Ollama em {url_base}: {exc.reason}") from exc
    return dados.get("response", "")


def _selecionar_backend():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _chamar_claude
    if os.environ.get("OLLAMA_URL") or os.environ.get("OLLAMA_MODEL"):
        return _chamar_ollama
    raise RuntimeError(
        "IA desligada: nenhum backend configurado. Defina ANTHROPIC_API_KEY (+ ANTHROPIC_MODEL) "
        "para usar a API da Claude, ou OLLAMA_URL/OLLAMA_MODEL para usar um Ollama local. "
        "Sem isso o Radar de Vagas funciona normalmente — a IA é 100% opcional.\n"
        "Aviso de privacidade: o backend Claude envia trechos do seu CV a um serviço externo "
        "(a API da Anthropic); o Ollama local não envia nada para fora da sua máquina."
    )


def sugerir(cv_texto: str, lacunas: list[dict], vagas: list[dict], chamar_backend=None) -> str:
    """Gera sugestões de CV. `chamar_backend(prompt) -> str` é injetável para
    testes com mock, sem rede; por padrão escolhe Claude ou Ollama pelas
    variáveis de ambiente (veja _selecionar_backend)."""
    prompt = montar_prompt(cv_texto, lacunas, vagas)
    if chamar_backend is None:
        chamar_backend = _selecionar_backend()
    return chamar_backend(prompt)
