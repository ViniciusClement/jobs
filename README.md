# Radar de Vagas

Aplicação local, em Python 3.10+ (só biblioteca padrão; `pypdf` é opcional,
só para ler CV em PDF), que acompanha vagas de **Red Team / Pentest /
Segurança Ofensiva** do mercado **privado** — Brasil e internacional — para
você entender o mercado e melhorar seu currículo. É um projeto pessoal de
estudo de carreira, pensado para rodar no Windows (mas funciona em qualquer
SO com Python 3.10+).

O projeto nasceu de um planejamento em 5 fases (núcleo, CV/análise,
coletor, painéis HTML, IA opcional) e depois ganhou uma rodada extra: os
dados passaram de arquivos JSON para um **banco SQLite local**
(`data/radar.db`), e ganhou uma **app web local** (Flask) para editar tudo
no navegador, além dos comandos de linha de comando.

## O que ela faz

1. Você popula vagas de três formas (ver "Como popular os dados" abaixo):
   colando texto (CLI ou navegador), via upload do coletor automático
   (Greenhouse/Lever/Ashby/SmartRecruiters), ou por `python run.py split`
   para e-mails de alerta com várias vagas.
2. O pipeline limpa o texto, extrai os campos (empresa, local, modalidade,
   salário, restrições, skills...) e detecta skills usando uma taxonomia
   editável — tudo fica salvo em `data/radar.db` (SQLite).
3. Vagas de órgão público são marcadas e ficam fora de toda estatística.
4. Compara as skills do mercado com as do seu CV, calcula cobertura e
   lacunas, e aponta um plano de estudo.
5. Dois jeitos de ver o resultado: a **app web local** (`python run.py
   servir`, com edição ao vivo) ou um **snapshot HTML estático**
   (`python run.py generate-html`, para publicar `docs/` no GitHub Pages).
6. Opcionalmente, pode gerar sugestões de reescrita do CV via IA (Claude
   API ou Ollama local) — desligado por padrão.

## Arquitetura

```
run.py              CLI (todos os subcomandos) e orquestração dos payloads
radar/
  limpeza.py         normalização de texto bruto (seção "Como funciona a limpeza")
  parser.py          cabeçalho/seções/campos/título/restrições/salário/datas
  skills.py          matcher de skills (taxonomia + grupos alternativos)
  cv.py              leitura de CV (PDF/DOCX/TXT/MD) e detecção de skills nele
  coletor.py         clientes HTTP dos 4 ATS (só os endpoints JSON públicos)
  analise.py         fórmulas de mercado/cobertura/elegibilidade (puro, sem I/O)
  db.py              camada SQLite (único lugar que fala SQL no projeto)
  html.py            template único (HTML+CSS+JS) dos dois painéis
  web.py             rotas Flask da app local (importa run.py, não duplica lógica)
  ia.py              sugestões de CV via Claude API/Ollama (opcional)
data/radar.db        SQLite: vagas + perfil + elegibilidade + histórico
data/*.json          taxonomia/configuração editável à mão (versionada no git)
cv/, vagas/, docs/   CV ativo; inbox/raw/processadas da CLI; snapshot público
```

Fluxo de dados: qualquer forma de entrada (CLI paste/split/collect, ou o
formulário "+ Adicionar vaga" da web) passa pelo mesmo
`radar.parser.montar_vaga()` e termina em `data/radar.db`. A partir daí,
tanto `python run.py generate-html` (snapshot estático) quanto as rotas
`/` e `/privado` da app Flask leem o banco e chamam as **mesmas** funções
`run.montar_payload_publico()`/`montar_payload_privado()` para montar o
JSON que o template único de `radar/html.py` renderiza — não há duas
implementações divergentes do painel.

`radar/web.py` não tem lógica de negócio própria: cada rota chama uma
função já testada de `run.py` (`carregar_vagas`, `salvar_vagas`,
`cmd_coletar`, `cmd_analisar`...). Isso significa que CLI e app web nunca
podem divergir no que fazem — só na forma de acionar.

## Segurança

Revisão feita antes do primeiro push (acima do que já era tratado desde a
Fase 1 — ver seção de privacidade): escapamento de saída, injeção, CSRF,
segredos e superfície de rede.

- **SQL injection:** `radar/db.py` é o único lugar que monta SQL no
  projeto, e toda query usa parâmetros (`?`/`:nome`) — nunca f-string/`%`
  dentro de uma query. Cobertura em `tests/test_db.py`.
- **XSS — encontrado e corrigido:** as páginas de formulário
  (`/adicionar`, `/perfil`, em `radar/web.py`) são HTML montado à mão (sem
  motor de template), e inicialmente interpolavam valores vindos do
  usuário (título de uma vaga colada, campos do perfil) sem escapar.
  Corrigido com `html.escape()` em todo valor dinâmico antes de embutir em
  HTML/atributo — com testes de regressão
  (`test_adicionar_vaga_com_titulo_malicioso_nao_gera_xss`,
  `test_pagina_perfil_com_valor_malicioso_nao_gera_xss`). O template
  principal (`radar/html.py`) já construía tudo via DOM (`textContent`),
  exceto um ponto que usava `innerHTML` com concatenação (risco baixo —
  só dados da taxonomia local, nunca texto colado) — trocado por DOM
  também, e a capacidade `html:` do helper interno foi removida.
- **CSRF (mitigação leve):** a app só escuta em `127.0.0.1`, mas qualquer
  aba aberta no mesmo navegador poderia tentar enviar um POST pra ela sem
  você querer. Um `before_request` em `radar/web.py` rejeita POSTs cuja
  `Origin`/`Referer` não seja o próprio host (403). Isso não é CSRF
  completo (não há token por formulário) — suficiente para o modelo de
  ameaça de uma ferramenta pessoal local, mas é uma limitação conhecida.
- **Segredos:** `ANTHROPIC_API_KEY` só é lida de variável de ambiente,
  nunca logada nem gravada em disco; não há segredo nenhum hardcoded no
  código (auditado com grep por padrões de chave/senha/token).
- **Rede:** `python run.py serve` só liga em `127.0.0.1` (nunca
  `0.0.0.0`) e roda com `debug=False` (sem o debugger do Werkzeug, que
  permite execução remota de código se exposto). O coletor usa
  `urllib` com timeout e User-Agent identificado contra só os 4 endpoints
  documentados — nenhuma URL é montada a partir de entrada do usuário sem
  validação de tipo de ATS.
- **Comandos externos:** o único `subprocess` do projeto (`paste`, fallback
  PowerShell `Get-Clipboard` no Windows) usa lista de argumentos fixa, sem
  `shell=True` nem concatenação de string — sem risco de injeção de
  comando.
- **Dados sensíveis x git:** ver "Publicando no GitHub Pages" abaixo —
  `data/radar.db` (vagas com contato de terceiros + perfil pessoal) e
  `privado/` estão no `.gitignore`; verificado com `git check-ignore`.

## Instalação e uso no Windows

1. Instale o [Python 3.10+](https://www.python.org/downloads/) (marque
   "Add python.exe to PATH" no instalador).
2. Baixe/clone este repositório para uma pasta, ex.: `C:\Users\você\radar-de-vagas`.
3. Abra o PowerShell ou o Prompt de Comando nessa pasta.
4. `pip install flask` (necessário só para `python run.py serve`, a app
   web; os comandos de CLI funcionam sem isso).
5. (Opcional, só se for usar CV em PDF) `pip install pypdf`.
6. (Opcional, só para o botão "Exportar perfil revisado (PDF)" em Meu
   perfil) `pip install weasyprint`.
7. Rode `python run.py serve` e abra `http://localhost:8000` no navegador
   — ou `python run.py` para confirmar que a CLI funciona.

Não precisa instalar nenhum servidor de banco de dados: o SQLite é um
único arquivo (`data/radar.db`), criado automaticamente na primeira vez
que qualquer comando precisar dele.

## Como popular os dados (vagas, perfil, CV, status)

Tudo isso pode ser feito de **duas formas** — CLI ou navegador (`python
run.py serve`) — e ambas gravam no mesmo banco, então pode misturar as duas
como preferir:

| O que | Pela CLI | Pelo navegador (`serve`) |
|---|---|---|
| Vaga nova (colada) | `python run.py paste` (lê a área de transferência) ou `python run.py split arquivo.txt` | aba **"+ Adicionar vaga"**: cola o texto num formulário |
| Vagas via coletor automático | `python run.py collect` (grava na inbox) + `python run.py process` | botão **"↻ Coletar vagas novas"** no painel privado |
| Perfil (cidadania, residência, clearances, idiomas) | editar `privado/perfil.json` manualmente (só na primeira vez — depois disso o banco manda) | aba **"Perfil"**: formulário com os mesmos campos |
| CV | solte um arquivo em `cv/` (PDF/DOCX/TXT/MD) | (sem upload pela web ainda — continue soltando o arquivo em `cv/`) |
| Status / notas de uma vaga | `python run.py status <id> <status> --note "..."` | formulário dentro de cada card, no painel privado |
| Recalcular elegibilidade/cobertura/lacunas | `python run.py analyze` | botão **"↻ Recalcular análise/CV"** no painel privado |

**Se você já tinha `data/vagas.json` e/ou `privado/perfil.json` de uma
versão anterior:** na primeira vez que qualquer comando ler os dados, eles
são **importados automaticamente** para `data/radar.db` — não precisa
migrar nada à mão. Depois da importação, esses arquivos antigos ficam sem
uso (o banco manda); pode deixá-los ou apagá-los, como preferir.

## Fluxo diário

**Opção 1 — app web local (recomendado para uso manual):**

```bash
python run.py serve
# abra http://localhost:8000 — "+ Adicionar vaga", "Perfil", botões de
# coletar/analisar e os painéis público/privado, tudo no navegador.
```

**Opção 2 — linha de comando (bom para automação/agendamento):**

```bash
# 1. Trazer vagas novas:
python run.py paste                 # cola da área de transferência (LinkedIn/Indeed/Gupy)
python run.py split alerta.txt     # ou divide um e-mail de alerta com várias vagas
python run.py collect                # ou coleta via API dos ATS configurados em data/fontes.json

# 2. Processar (se colar/coletar já não tiver processado):
python run.py process

# 3. Opcional: CV, elegibilidade e análise
python run.py analyze

# 4. Ver o resultado sem abrir a app web:
python run.py generate-html
# abra docs/index.html (público) e privado/index.html (privado) no navegador
```

`paste` já processa automaticamente depois de salvar na inbox. `collect`
só grava `.txt` na inbox — sempre rode `process` depois (ou use o botão
"Coletar vagas novas" da app web, que já processa).

## Formato do cabeçalho e do separador `=== VAGA ===`

Ao colar uma vaga manualmente, o cabeçalho é opcional:

```
Empresa: ... | Local: ... | URL: ... | Data: AAAA-MM-DD | Origem: linkedin|indeed|gupy|... | Mercado: BR|INT | Status: interessado
---
(texto bruto da vaga, começando pelo título)
```

Sem cabeçalho, o `.txt` pode conter só o texto bruto (o pipeline ainda
extrai o que conseguir do próprio texto). Um `.txt` pode conter **várias
vagas** separadas por uma linha exatamente assim:

```
=== VAGA ===
```

Se um `.txt` tiver várias vagas mas sem esse separador (ex.: um e-mail de
alerta com "Full job description" repetido), use
`python run.py split arquivo.txt` — ele mostra uma prévia dos cortes
antes de gravar (use `--dry-run` para só ver a prévia, sem gravar nada).

## Como funciona a limpeza (e os arquivos editáveis em `data/`)

Antes de qualquer extração, o texto colado passa por limpeza (seção 5 do
escopo original): corrige mojibake comum (`â€™` → `'`), remove `&nbsp;`/
entidades HTML, normaliza marcadores de lista, preserva texto+URL de links
markdown, extrai e remove hashtags de ATS (`#LI-Remote` → pista de
modalidade), remove ruído de interface, e separa palavras coladas
(`assessmentsSocial` → `assessments Social`) sem quebrar nomes CamelCase
conhecidos (`PowerShell`, `BloodHound`, `GitHub`...).

Arquivos editáveis (edite e rode `python run.py reprocess` depois):

- **`data/ruido.json`**: linhas exatas e regex de ruído de interface/ATS a
  remover (ex.: "Apply Now", "Posted 30+ Days Ago").
- **`data/secoes.json`**: frases de cabeçalho de seção reconhecidas, em
  PT/EN, por categoria (`descricao`, `responsabilidades`, `requisitos`,
  `diferenciais`, `beneficios`, `sobre_empresa`). O cabeçalho da seção tem
  prioridade sobre pistas de linha — ex.: um requisito dentro de
  "Diferenciais" continua sendo classificado como diferencial, mesmo que a
  linha contenha a palavra "required".
- **`data/filtros.json`**: termos que identificam setor público
  (`termos_setor_publico`, ver abaixo) e termos de contratada de governo
  (`termos_governo_contratada`).
- **`data/familias.json`**: palavras-chave de título para classificar
  `familia_cargo` (`red_team`, `pentest`, `appsec`, `gestao_vuln`, ou
  `outro` por padrão).

## Editando a taxonomia de skills (`data/skills.json`)

```json
{
  "Categoria": {
    "Nome da skill": {
      "sinonimos": ["variante 1", "variante 2"],
      "regex": ["padrão opcional em regex"],
      "case_sensitive": false
    }
  }
}
```

- `sinonimos` são sempre comparados sem diferenciar maiúsculas/minúsculas.
- `regex` (e o nome da skill, quando não há `sinonimos`/`regex`) respeitam
  `case_sensitive` — útil para siglas curtas ambíguas (`Go`, `C/C++`,
  `NIST`, `AWS`...), que precisam de contexto para não gerar falso
  positivo (ex.: "Go to market" não deve casar com a linguagem Go).
- Para testar um regex isoladamente antes de colar no JSON:
  ```bash
  python -c "import re; print(re.findall(r'SEU_REGEX', 'texto de teste'))"
  ```
- **Depois de editar `skills.json` (ou qualquer arquivo em `data/`), rode
  `python run.py reprocess`** para reaplicar as regras novas a todas as
  vagas já salvas, preservando `status`/`notas`.

### Grupos alternativos ("um destes")

Frases como "One or more of the following", "Must have (1) of", "ou
equivalente" ou "e/ou" fazem as skills citadas na mesma linha formarem um
**grupo alternativo**: para efeito de cobertura/match, o grupo vale como
**uma** exigência só, satisfeita se você tiver **qualquer um** dos membros
no CV. No painel HTML, esses grupos aparecem com o rótulo "um destes".

## Coletor automático (`data/fontes.json`)

Usa só os endpoints JSON públicos oficiais de 4 ATS — sem login, sem
raspar HTML:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
- Lever: `https://api.lever.co/v0/postings/{slug}?mode=json`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{slug}`
- SmartRecruiters: `https://api.smartrecruiters.com/v1/companies/{slug}/postings` (mais uma chamada por vaga, no endpoint de detalhe, para pegar a descrição completa)

**Slug:** abra a página de carreiras da empresa e olhe a URL —
`boards.greenhouse.io/{slug}`, `jobs.lever.co/{slug}`,
`jobs.ashbyhq.com/{slug}` ou `careers.smartrecruiters.com/{slug}` (para
SmartRecruiters o identificador da API pode usar outra capitalização; se
der 404, teste variações). Edite `data/fontes.json` e troque cada
`"slug": "TROCAR"` pelo slug real (ou remova a fonte). Ajuste também
`filtros.titulo_inclui`/`titulo_exclui`.

```bash
python run.py collect --dry-run   # só mostra o que seria coletado/arquivado
python run.py collect             # grava .txt em vagas/inbox/
python run.py process           # processa normalmente
```

- Dedup pela URL já existente no banco.
- Vaga que desaparece da API (e cujo status ainda é `novo`/`interessado` —
  status que você já mudou manualmente não é sobrescrito) vira
  `status: "arquivada"` com a nota "encerrada na fonte", sem apagar.
- Vaga de empregador do setor público continua sendo marcada `ignorada`
  pelo `process` normal.
- Boas maneiras: User-Agent identificado, timeout de 15s, pausa entre
  requisições, erro isolado por fonte.

**Agendando no Windows** (Agendador de Tarefas): crie uma tarefa que rode
periodicamente uma ação "Iniciar um programa" com `cmd.exe` e argumentos
`/c "cd /d C:\caminho\para\jobs && python run.py collect && python run.py process"`.

**Por que LinkedIn, Indeed e Gupy continuam manuais:** esses sites não têm
uma API JSON pública de uso livre como os 4 ATS acima — automatizar a
coleta exigiria raspar HTML autenticado ou contornar proteção
anti-automação, o que viola os termos de uso deles. Em vez disso: configure
alertas por e-mail nessas plataformas e use `python run.py paste` (lê a
área de transferência) ou `python run.py split` (quando o e-mail de
alerta traz várias vagas num só texto).

## Filtro de mercado privado

Vagas de **órgão público** (concurso, edital, administração pública,
`.gov.br`, autarquia etc. — lista editável em `data/filtros.json`) são
marcadas `ignorada=true` com o motivo, mas **não são apagadas**. Vagas
ignoradas ficam fora de toda estatística e nunca aparecem nos painéis HTML.

Isso é diferente de `setor_cliente: "governo_contratada"`: uma empresa
**privada** que presta serviço ao governo (defesa, contratada federal,
staffing, menção a clearance...) **não** é ignorada — ela é marcada com
esse campo, mas continua contando normalmente nas estatísticas.

## Restrições e elegibilidade (perfil)

Campos do perfil: `cidadanias` (lista), `residencia` (país), `clearances`
(lista), `aceita_relocacao` (bool), `idiomas.pt`/`idiomas.en`. Edite pela
aba **"Perfil"** da app web (`python run.py serve`), ou, se preferir
editar à mão antes do primeiro uso, crie `privado/perfil.json` nesse
formato — ele é importado automaticamente para o banco na primeira leitura:

```json
{
  "cidadanias": ["BR"],
  "residencia": "BR",
  "clearances": [],
  "aceita_relocacao": false,
  "idiomas": {"pt": "nativo", "en": "intermediario"}
}
```

O padrão (sem nenhum arquivo nem edição) já é `cidadanias: ["BR"]`,
`residencia: "BR"` — o que você informou — com os demais campos neutros.
A partir do perfil, `python run.py analyze` (ou o botão "Recalcular
análise/CV") calcula, por vaga, `elegivel = sim | nao | talvez` (com
motivos), guardado no banco — nunca no painel público.

## Status

Cada vaga tem um `status`: `novo | interessado | aplicado | entrevista |
oferta | recusado | arquivada`. Muda pela CLI:

```bash
python run.py status v-abc12345 interessado --note "boa vaga, aplicar essa semana"
```

ou direto no card da vaga, no painel privado da app web (`python run.py
servir` → `/privado`). O painel público nunca mostra status/notas. O
coletor automático também pode mudar o status para `arquivada` (vaga que
saiu da fonte), mas só se o status ainda for `novo`/`interessado` — uma
vez que você mudou manualmente, o coletor
não sobrescreve.

## IA opcional (sugestões de CV)

```bash
python run.py --ai
```

**Desligada por padrão** — sem nenhuma variável de ambiente configurada,
o resto do Radar de Vagas funciona 100% normalmente e esse comando só
avisa que a IA não está configurada. Para ligar, escolha um backend:

- **Claude API:** defina `ANTHROPIC_API_KEY` e `ANTHROPIC_MODEL` (o modelo
  nunca é fixado no código — você escolhe).
  ⚠️ **Aviso de privacidade:** com esse backend, trechos do seu CV (sem
  e-mail/telefone) são enviados a um serviço externo (a API da Anthropic).
- **Ollama local:** defina `OLLAMA_URL` (ex.: `http://localhost:11434`) e
  `OLLAMA_MODEL`. Nada sai da sua máquina.

O prompt enviado nunca leva texto bruto de vaga, contato de recrutador, nem
e-mail/telefone do seu CV — só o CV (com contato mascarado) e agregados de
mercado (títulos, famílias, skills). A IA é instruída a nunca inventar
experiência/certificação que não esteja no CV (o que falta vai para uma
seção "A desenvolver") e a nunca sugerir como contornar exigência de
cidadania, residência ou clearance. O resultado vai para
`privado/sugestoes-cv.md` — **revise sempre antes de usar**.

## Painéis (app web ao vivo ou snapshot estático)

Os dois painéis existem em duas versões, mesmo HTML/CSS/JS por baixo:

- **Ao vivo**, servidos por `python run.py serve` (lê o banco a cada
  request — é o que te dá os formulários de adicionar vaga/editar
  perfil/mudar status/coletar/analisar descritos acima).
- **Snapshot estático**, gerado por `python run.py generate-html` em
  `docs/index.html` + `privado/index.html` — **sem** os formulários de
  edição (só leitura), pensado para publicar `docs/` no GitHub Pages ou
  abrir via `file://` sem precisar rodar nada. Sem CDN: CSS, JS e os dados
  ficam todos embutidos no próprio arquivo.

Tema claro/escuro automático e responsivo nos dois casos.

- **`docs/index.html` (PÚBLICO):** painel de mercado (top skills,
  categorias, perfil das vagas — senioridade/modalidade/vínculo/família —,
  comparação BR × INT, comparação por família, faixas salariais com N,
  seletor de recorte BR/INT acessível/INT restrito/todos) + lista de vagas
  com busca e filtros
  (senioridade, modalidade, contrato, vínculo, família, skill, restrição).
  Chips de skill têm tooltip com a frase-evidência (máx. 200 caracteres,
  e-mail/telefone sempre mascarados). Grupos alternativos aparecem como
  "um destes". Vagas ignoradas nunca aparecem.
  - O recorte "INT acessível/restrito" no público usa um perfil genérico
    fixo no código (cidadania/residência BR, sem relocação) — **não** lê
    `privado/perfil.json`, propositalmente, para o público nunca depender
    de um arquivo privado.
- **Privado** (`/privado` ao vivo, ou `privado/index.html` estático): a
  mesma página + % de match por vaga, chips verde/vermelho por skill
  conforme seu CV, coluna/filtro de elegibilidade (sim/não/talvez, com
  motivo) e "só elegíveis", status/notas, e aba "Meu CV" (lacunas
  priorizadas, plano de estudo, evolução da cobertura).

`tests/test_html.py` verifica automaticamente (e, se houver navegador
headless disponível, abre as páginas de verdade) que `docs/index.html`
nunca contém texto bruto, e-mail/telefone, status/notas, conteúdo do
perfil nem trechos do CV.

## Meu perfil (score ao estilo SSI do LinkedIn)

A página `/perfil-profissional` (link "Meu perfil" no menu) é um perfil
estilo LinkedIn, pensado para evoluir junto com as vagas que você vai
cadastrando:

- **Importação:** exporte seu próprio perfil do LinkedIn em "Salvar como
  PDF" e importe pelo formulário da página (ou
  `python run.py import-linkedin caminho/Profile.pdf` pela CLI). O parser
  (`radar/linkedin_import.py`) extrai nome, headline, localização, resumo,
  experiências, formação, certificações e skills autodeclaradas.
- **Score de perfil (0–100):** 55% cobertura de hard skills do mercado
  (mesma lógica de `match_vaga`/unidade de exigência) + 20% cobertura de
  soft skills (categoria "Soft skills/relatórios") + 25% completude do
  perfil importado. Referência do próprio LinkedIn: **50+ é considerado
  bom** (`radar/analise.py:calcular_score_perfil`).
- **Melhorias sugeridas no currículo:** lista as skills mais exigidas
  pelas vagas cadastradas e ausentes do seu CV (mesmo cálculo de lacunas
  da aba "Meu CV"), priorizadas por quanto aparecem no mercado — para
  decidir o que vale a pena aprender ou só adicionar ao currículo.
- **Exportar perfil revisado (PDF):** botão que gera um PDF (via
  [weasyprint](https://weasyprint.org/), `pip install weasyprint`) com o
  perfil, score e as melhorias sugeridas — pensado para ser um retrato do
  "estado atual" do seu posicionamento, pronto pra guardar ou compartilhar.

### Publicando no GitHub Pages

Rode `python run.py generate-html` e aponte o GitHub Pages para a pasta
`docs/` (ou para a branch que a contém) — o snapshot estático, não a app
web (GitHub Pages não roda Python/Flask).

**O que É publicado:** só `docs/index.html`.

**O que NÃO é publicado** (confira com `git status` — nada disso deve
aparecer como rastreável, exceto `cv/README.md`):

- `privado/` inteira (CV, relatório, sugestões de IA, snapshot estático
  privado) — no `.gitignore`.
- `cv/*` — no `.gitignore`, exceto `cv/README.md`.
- **`data/radar.db`** (e `-wal`/`-shm`) — o banco SQLite, que guarda as
  vagas (texto bruto e contato de recrutador) **e** o perfil — no
  `.gitignore`. Os demais arquivos em `data/` (taxonomia: `skills.json`,
  `secoes.json`, `ruido.json`, `filtros.json`, `familias.json`,
  `fontes.json`) são configuração versionável normal, sem dado sensível.
- `vagas/` inteira (inbox/raw/processadas) — contém texto bruto das vagas
  (fica populada só se você usar o fluxo de CLI; pelo `serve`, os blocos
  colados vão direto para o banco).
- `tests/fixtures_reais/` — no `.gitignore`.

### Por que anúncios reais e contatos de recrutador não vão para o git

`data/radar.db` guarda o texto completo de anúncios de terceiros (e, às
vezes, e-mail/telefone de quem postou a vaga), além do seu perfil pessoal.
Versionar isso num repositório público seria redistribuir conteúdo de
terceiros sem permissão e expor dados de contato de pessoas que não deram
esse consentimento — por isso o banco está no `.gitignore`, e o painel
público (`docs/`) nunca inclui texto bruto nem contato, só dados agregados
de mercado (ver seção anterior e `tests/test_html.py`).

## Taxonomia de skills (visão geral)

`data/skills.json` já vem com a taxonomia inicial: Active Directory,
Cloud/Identidade, Web/API, AppSec/DevSecOps, Ferramentas de pentest, Gestão
de vulnerabilidades, Análise de código, C2 e infraestrutura, Evasão,
Engenharia social/Phishing/OSINT, Testes especializados, Malware dev,
Metodologias e frameworks, Linguagens, Certificações ofensivas,
Certificações gerais/gestão, e Soft skills/relatórios. Use
`python run.py terms` para descobrir termos frequentes que ainda não
estão na taxonomia (candidatos a novas skills).

## Testes

```bash
python -m unittest -v
```

- Os testes com anúncios reais em `tests/fixtures_reais/` (pasta vazia e
  ignorada pelo git) são pulados automaticamente — você pode colocar
  anúncios reais ali para testar contra casos de verdade, sem risco de
  versionar esse conteúdo.
- Os testes da app web (`tests/test_web.py`) são pulados automaticamente
  se o Flask não estiver instalado (`pip install flask`) — a app web é
  opcional, não bloqueia o resto da suíte.
- Os testes de HTML (`tests/test_html.py`) abrem as páginas de verdade num
  Chromium headless, se houver um disponível (via Selenium); senão,
  também pulam essa parte e dizem isso explicitamente.
