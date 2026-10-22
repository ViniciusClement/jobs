# PROMPT MESTRE: Radar de Vagas

> Como usar: cole este arquivo inteiro na primeira mensagem (e salve também como `CLAUDE.md` na raiz do repo "jobs", para o contexto persistir). O modelo executa SOMENTE a Fase 1 e para. Para avançar, envie "continuar fase N". Revise o resumo e rode os comandos antes de cada avanço.

---

## 0. Missão

Construa, na pasta conectada (repo "jobs"), uma aplicação local em Python 3.10+ (somente biblioteca padrão; pypdf opcional) chamada **"Radar de Vagas"**. Ela acompanha vagas de Red Team / Pentest / Segurança Ofensiva do **mercado PRIVADO**, **brasileiro e internacional**, para eu entender o mercado e melhorar meu currículo. É um projeto pessoal de estudo de carreira. Uso Windows. Sou brasileiro e resido no Brasil.

## 1. Protocolo de trabalho

- Faça SOMENTE a fase pedida (comece pela Fase 1). Ao terminar: rode os testes da fase e o pipeline, corrija o que falhar e PARE.
- Resumo obrigatório ao fim de cada fase: o que foi feito, decisões tomadas, suposições, pendências e como eu valido (comandos).
- Não faça commit nem push; eu faço.
- Se algo for ambíguo e mudar muito o resultado, pergunte antes. Caso contrário, escolha a opção mais simples e registre a suposição no resumo.
- Nunca afirme que verificou algo que não executou (ex.: navegador headless indisponível → diga isso).

## 2. Princípios técnicos

- pathlib, caminhos relativos ao `run.py`; escrita atômica de JSON (tmp + replace).
- `sys.stdout.reconfigure(encoding="utf-8")`. CLI com argparse e subcomandos. Mensagens em português.
- Pacote chama-se `radar/` (não `jobs/`).
- Campo não encontrado = `null`. Nunca inventar nem inferir sem evidência no texto.
- Leitura de arquivos: utf-8, fallback utf-8-sig e cp1252.
- Nunca fixar nome de modelo de IA no código. Nunca registrar o CV em logs.

## 3. Estrutura

```
run.py
radar/{parser,limpeza,skills,cv,analise,html,ia,coletor}.py
data/{skills.json,secoes.json,ruido.json,filtros.json,familias.json,fontes.json,vagas.json}
vagas/{inbox,raw,processadas}/
cv/ (README.md + CV ativo; cv/arquivo/ para versões antigas)
docs/ (PÚBLICO)
privado/ (PRIVADO)
tests/{fixtures,fixtures_reais}/
```

## 4. Separação público/privado

- `docs/` (pode ir ao GitHub Pages): só dados de mercado: metadados, skills e frase-evidência curta (máx. 200 caracteres, com e-mails e telefones mascarados). NÃO contém texto bruto das vagas, status, notas, contatos de recrutadores, elegibilidade, nem nada do CV ou do perfil.
- `privado/` (no .gitignore): CV, `perfil.json`, elegibilidade, `historico.json` (cobertura do CV), status/notas, relatórios, sugestões de IA.
- `data/vagas.json` guarda texto bruto e contatos; NUNCA é copiado para `docs/`.
- Dados pessoais de terceiros (e-mail/telefone de recrutadores) ficam só em `data/vagas.json`, no campo `contato_recrutador`.
- `.gitignore`: `cv/*` com exceção `!cv/README.md`; `privado/`; `.env`; `__pycache__/`; `tests/fixtures_reais/`.

## 5. Entrada suja: limpeza obrigatória antes de qualquer extração

O texto vem colado de LinkedIn, Indeed, Gupy, ATS etc. Normalizar:

- mojibake (ex.: "â€™" → "’"; tentar encode cp1252 → decode utf-8), `&nbsp;` e entidades HTML;
- glifos de lista (•, ◇, ◆, ▪, *, -, ›) → marcador único; links markdown `[texto](url)` → guardar texto e url;
- hashtags de ATS (`#LI-Remote`, `#LI-AC1`): remover do texto, mas usar como pista (ex.: `#LI-Remote` → remoto);
- ruído de interface e IDs soltos ("Apply", "Full job description", "time type", "Posted 30+ Days Ago", tokens alfanuméricos aleatórios sozinhos na linha): lista editável em `data/ruido.json`;
- palavras coladas (minúscula seguida de Maiúscula, ex.: "assessmentsSocial") e texto em linha única: separar antes do matcher;
- asterisco de rodapé em certificações ("OSCP*") não pode impedir o match.

URL: normalizar removendo parâmetros de rastreio (utm_*, tk etc.); no Indeed manter só o identificador da vaga (jk/fromjk).

## 6. Formato da vaga na inbox

```
Empresa: ... | Local: ... | URL: ... | Data: AAAA-MM-DD | Origem: linkedin|indeed|gupy|... | Mercado: BR|INT | Status: interessado
---
(texto bruto da vaga)
```

Cabeçalho opcional. Um `.txt` pode conter VÁRIAS vagas separadas por uma linha `=== VAGA ===` (ver subcomando `dividir`).

## 7. Contrato de dados (`data/vagas.json`)

`{"schema_version": 1, "vagas": [ ... ]}`. Cada vaga:

- **Identidade:** `id` ("v-" + 8 primeiros hex do sha1 da `chave_dedup`; estável); `chave_dedup` (URL normalizada se houver, senão hash do texto normalizado já limpo); `possivel_duplicata_de` (id|null).
- **Cargo:** `titulo` (limpo, sem local/modalidade/salário embutidos); `titulo_bruto`; `familia_cargo` (red_team|pentest|appsec|gestao_vuln|outro, regra editável em `data/familias.json`).
- **Empregador:** `empresa` (null se agência/anônima); `empregador_tipo` (direto|agencia|anonimo|null); `setor_cliente` (privado|governo_contratada|null).
- **Local:** `locais` (lista); `pais` (lista ISO-2); `mercado` (BR|INT|null); `modalidade` (remoto|híbrido|presencial|null); `modalidade_conflito` (bool; ex.: #LI-Remote com local presencial); `escopo_remoto` (global|pais:XX|regiao:XX|null).
- **Restrições:** `restricoes {cidadania: lista|null, residencia: ISO|null, clearance: "public_trust"|"secret"|"ts"|null, clearance_obrigatorio: bool|null, outras: lista}` + `restricoes_evidencia` (frase). Ex.: "must currently live in the U.S.", "US Citizen or Green Card", "Top Secret clearance".
- **Nível:** `senioridade` (estágio|júnior|pleno|sênior|especialista|lead|null) SÓ quando explícita no texto, mais `senioridade_texto` (original: "IC2", "mid to sr.", "Senior Associate"); não inferir por salário ou anos.
- **Experiência:** `anos_experiencia {min,max,texto,ambiguo}`: aceitar "3 – 10 years", "10+ years", numerais por extenso ("Three years"); somas como "3 years + additional (2)" → `ambiguo=true`, guardar candidatos, sem decidir.
- **Salário:** `salario {min,max,moeda,periodo(ano|mes|hora),texto}|null`: aceitar "$140,000-$180,000", "Up to $150k" (min null, max 150000), "R$ 8.000 a 12.000".
- **Vínculo:** `contrato` (CLT|PJ|outro|null) e `tipo_vinculo` (full_time|part_time|contract|direct_hire|permanent|null), campos independentes.
- **Tempo:** `periodo_contrato {inicio,fim}|null`; `datas_no_texto`; `possivelmente_expirada` (bool: fim do período < data de processamento); `data` (AAAA-MM-DD); `data_estimada` (bool; "Posted 30+ Days Ago" → estimada; data ausente → data de processamento).
- **Outros:** `idioma` (pt|en); `ingles_nivel`|null; `origem` (linkedin|indeed|gupy|greenhouse|lever|ashby|indicacao|outro|null); `url`; `status` (novo|interessado|aplicado|entrevista|oferta|recusado|arquivada); `notas`; `ignorada` (bool); `ignorada_motivo`.
- **Conteúdo:** `secoes {descricao, responsabilidades, requisitos, diferenciais, beneficios, sobre_empresa}`; `skills [{categoria, skill, classe, peso, evidencia, grupo_alternativo: id|null}]`; `texto_bruto`; `contato_recrutador`.
- Elegibilidade NÃO é gravada em `vagas.json`: é calculada em `privado/` a partir de `privado/perfil.json`.
- Slug de arquivo: minúsculo, sem acentos, `[a-z0-9-]`, máx. 60 caracteres. Ficha: `vagas/processadas/AAAA-MM-DD-slug.md` (sem e-mail/telefone de recrutador).

## 8. Só mercado privado

- Marcar `ignorada=true` (com motivo), sem apagar, quando o EMPREGADOR for órgão público: concurso, edital, "órgão público", estatutário, ".gov.br", "autarquia", "administração pública" etc. Lista editável em `data/filtros.json`.
- Empresa privada que presta serviço ao governo (defesa, contratadas federais, staffing) NÃO é ignorada: marcar `setor_cliente="governo_contratada"`.
- Vagas ignoradas ficam fora de toda estatística.

## 9. Seções e classes

- Cabeçalhos PT/EN reconhecidos por padrões editáveis em `data/secoes.json`, inclusive em forma de frase e sem dois-pontos. Devem funcionar: "Os desafios da função são:", "É muito importante que você tenha e/ou saiba:", "E quais são os benefícios?", "Key Responsibilities", "Required Skills & Experience", "Position Description", "Knowledge & Competencies", "Education & Qualifications", "Experience and Skills", "Desired Skills and Experience", "Job Summary", "Company Overview", "About Us", "Total Rewards", "Work Environment", "What's on offer".
- O cabeçalho da seção tem PRIORIDADE sobre pistas de linha. Ex.: em "Skills/Experience Preferred (not all required)", "required" não torna nada obrigatório.
- Sem cabeçalhos, classificar linha a linha. Diferencial: desejável, nice to have, plus, "a plus", "big plus", preferred, desired, beneficial, advantageous, "would be", ideally. Requisito: obrigatório, must, required, "experiência com", "are required". Senão: mencionado.
- Seções `sobre_empresa`, EEO, privacidade, pay transparency e benefícios NÃO entram na detecção de skills.

## 10. Grupos alternativos ("um de")

Frases como "One or more of the following", "Must have (1) of", "any of", "ou equivalente", "ex.: Python, PowerShell, Go, Bash", "e/ou" e listas de certificações aceitas formam um `grupo_alternativo` (id estável por vaga). O grupo vale como UMA exigência (peso da classe contado uma vez) e é atendido se QUALQUER membro estiver no CV.

## 11. Elegibilidade (privada)

`privado/perfil.json`: `{"cidadanias": ["BR"], "residencia": "BR", "clearances": [], "aceita_relocacao": false, "idiomas": {...}}`. Por vaga, calcular `elegivel = sim | nao | talvez` com motivos (ex.: "exige residência nos EUA"). Persistir só em `privado/elegibilidade.json`. Nada disso vai para `docs/`.

## 12. Fórmulas (usar exatamente estas)

- Peso da classe: obrigatório 1.0, mencionado 0.6, diferencial 0.4. Skill em várias seções: vale a classe de maior peso.
- `score_skill` = soma dos pesos da skill nas vagas ativas ÷ nº de vagas ativas (ranking de mercado conta cada skill individualmente, mesmo dentro de grupo).
- Unidade de exigência: cada skill fora de grupo é uma unidade; cada grupo alternativo é uma unidade.
- `match_vaga` (CV) = soma dos pesos das unidades atendidas ÷ soma dos pesos de todas as unidades da vaga.
- Lacuna numa vaga = skill ausente do CV cujo grupo (se houver) também não tem nenhum membro no CV. `score_lacuna` = soma dos pesos nas vagas onde é lacuna ÷ nº de vagas ativas.
- `cobertura_geral` = Σ pesos atendidos de todas as vagas ÷ Σ pesos totais de todas as vagas, no recorte.
- "Em alta": participação (% de vagas com a skill) nos últimos 30 dias vs. anterior, só para skills com ≥ 5 ocorrências e janelas com ≥ 10 vagas; senão "dados insuficientes". Vagas com `data_estimada` ficam fora de "em alta".
- Recortes de toda análise: BR; INT acessível (sem restrição de cidadania/residência incompatível com o perfil); INT restrito; todos. No privado, filtro adicional "só elegíveis".
- Divisão por zero (recorte vazio) deve ser tratada.

## 13. Falsos positivos e variantes (casos de teste obrigatórios)

- "Go to market", "go-getter", "let's go", "Go Phish" → NÃO é Go. "Golang", "Go (linguagem)", "experiência em Go", "Python, PowerShell, Go, Bash" → é Go.
- "C-level", "Vitamina C", "C suite" → NÃO é C. "C/C++", "linguagem C", "programação em C" → é C.
- "AD" isolado e "Rust" no sentido de ferrugem não casam sem contexto.
- "Computer Forensics", "Software Testing", "Cyber Security" na descrição da empresa → NÃO viram skill da vaga.
- Devem casar: "Mittre Attack"/"MITRE ATT&CK", "CheckMarkx"/"Checkmarx", "Spear Phishin"/"spear phishing", "Fuff"/"ffuf", "OSCP*", "Pentest+"/"PenTest+".

## 14. Taxonomia inicial (`data/skills.json`)

Formato: `{categoria: {skill: {"sinonimos": [...], "regex": [...], "case_sensitive": false}}}`. Categorias:

- **Active Directory:** Kerberos, ADCS, BloodHound, NTLM relay, Pass-the-Hash.
- **Cloud/Identidade:** Azure/Entra ID, AWS, GCP, Kubernetes, Docker.
- **Web/API:** OWASP Top 10, REST, SOAP, XSS, SSRF.
- **AppSec/DevSecOps:** SAST, DAST, SCA, SSDLC, CI/CD, Threat Modeling.
- **Ferramentas de pentest:** Burp Suite, Metasploit, Nmap, Wireshark, Kali Linux, Nessus.
- **Gestão de vulnerabilidades:** Qualys, Tenable, Rapid7, CTEM.
- **Análise de código:** Veracode, Checkmarx, AppScan, Fortify.
- **C2 e infraestrutura:** Cobalt Strike, Sliver, Havoc, Mythic, redirectors, OPSEC.
- **Evasão:** EDR/AV, AMSI, ETW, obfuscation.
- **Engenharia social/Phishing/OSINT.**
- **Testes especializados:** mobile, thick client, wireless, IoT, bypass físico.
- **Malware dev.**
- **Metodologias e frameworks:** MITRE ATT&CK, OSSTMM, PTES, TIBER-EU, NIST, ISO 27001, PCI DSS, FedRAMP, CREST, emulação de adversário, Purple Team, Rules of Engagement.
- **Linguagens:** Python, PowerShell, C#, C/C++, Go, Rust, Nim, Bash, JavaScript, PHP, Java.
- **Certificações ofensivas:** OSCP, OSEP, OSED, OSWE, OSWA, OSEE, CRTO, CRTP, CRTE, CRTA, PNPT, BSCP, GPEN, GXPN, GWAPT, CEPT, CMWAPT, eCPPT, eMAPT, LPT, Pentest+, CEH.
- **Certificações gerais/gestão:** CISSP, CISM, CISA, CCSP, CSSLP, CASP+, GCFA, CHFI, GCED.
- **Soft skills/relatórios:** report writing, mentoria, comunicação com não técnicos, CTFs.

---

# FASE 1 de 5: Núcleo (execute esta agora e PARE)

Construa a estrutura da seção 3 e implemente:

1. `radar/limpeza.py`: toda a seção 5.
2. `radar/parser.py`: todos os campos do contrato (seção 7) com as regras de null/não inferir; seções por `data/secoes.json` com prioridade do cabeçalho; classificação linha a linha; detecção de restrições, intermediário/agência, `setor_cliente`, `periodo_contrato`, `possivelmente_expirada`, salário, anos (inclusive por extenso), título limpo e `familia_cargo`.
3. `radar/skills.py`: matcher com `\b`, `case_sensitive` por skill, variantes/typos, frase-evidência, regra de maior peso, grupos alternativos e exclusão das seções de empresa/EEO/benefícios. Criar `data/skills.json` com a taxonomia da seção 14 (fácil de editar).
4. Pipeline `python run.py` / `run.py processar`: lê a inbox, limpa, filtra mercado privado, deduplica (URL normalizada; senão hash do texto limpo; difflib > 0.9 → `possivel_duplicata_de` + aviso; duplicata exata é descartada com aviso e não grava de novo), grava `data/vagas.json`, gera a ficha `.md` e move o `.txt` para `vagas/raw/`.
5. Subcomandos:
   - `colar` (tkinter; fallback powershell Get-Clipboard), salva na inbox e processa;
   - `dividir <arquivo> [--dry-run]`: divide um `.txt` com várias vagas em `.txt` separados na inbox, usando `=== VAGA ===` ou, na falta, heurísticas ("Full job description", blocos título+local); sempre mostra a prévia dos cortes e nunca junta vagas em silêncio;
   - `reprocessar` (refaz tudo a partir do texto bruto, preservando status/notas);
   - `status <id> <interessado|aplicado|entrevista|oferta|recusado|arquivada> [--nota "..."]`;
   - `termos`: termos e bigramas frequentes (stopwords PT/EN) fora da taxonomia, com contagem e exemplo de contexto;
   - `exportar`: `data/vagas.csv` em utf-8-sig, sem contatos nem texto bruto.
6. `tests/` (unittest): limpeza, cabeçalhos em frase, seções PT/EN, prioridade do cabeçalho, falsos positivos e variantes (seção 13), grupos alternativos, dedup (inclusive duplicata exata), classificação sem cabeçalho, filtro de setor público vs. `governo_contratada`, salário/anos/restrições, divisão de lote.
7. Fixtures: crie em `tests/fixtures/` vagas SINTÉTICAS curtas, escritas por você, sem texto de anúncios reais, reproduzindo cada padrão. Eu colocarei anúncios reais em `tests/fixtures_reais/` (ignorado pelo git); testes que dependem deles devem ser PULADOS (skip) se a pasta estiver vazia. Asserts mínimos para os reais, quando presentes:
   - **Riachuelo:** pt, remoto, BR; Python/PowerShell/Go/Bash em grupo alternativo; OSCP/OSEP/CRTO/CRTE/OSEE/GXPN como diferencial em grupo.
   - **LSEG:** id de requisição R0122063; locais Reino Unido e Bucareste; `data_estimada=true`.
   - **Oscar Associates:** texto colado separado corretamente; empresa null; agência; residência US; certificações em grupo, classe diferencial; "C/C++" detectado como C.
   - **DotWave:** clearance TS obrigatório; contract/part_time; período 2024-08 a 2025-04 e `possivelmente_expirada=true`; anos_min 10; grupo "Must have (1) of".
   - **Kratos (duas cópias idênticas):** salário 90000–120000 USD/ano; segunda cópia descartada como duplicata; "OSCP*" detectado; anos `ambiguo=true`; remoto via #LI-Remote.
   - **Consultoria de NY:** empresa null (anônimo); salário 140000–180000; `modalidade_conflito=true`; senioridade null.
   - **TestPros:** cidadania US; clearance public_trust; `governo_contratada`; mojibake corrigido; "Computer Forensics" NÃO vira skill; URL do Indeed normalizada.
   - **Converge:** `escopo_remoto` pais:US; OSCP obrigatório, OSWE diferencial; MITRE ATT&CK e OSSTMM detectados; `&nbsp;` removido.
   - **Zync:** título "Penetration Tester"; local New Jersey; híbrido; salário max 150000 e min null; cidadania US/Green Card; contato só em `contato_recrutador`; CREST detectado.
8. README provisório com a documentação mínima (uso, formato do cabeçalho, como editar skills e testar um regex).

Rode `python -m unittest` e `python run.py`; corrija o que falhar. **PARE e entregue o resumo da fase.**

---

# FASE 2 de 5: CV, elegibilidade e análise (só após eu enviar "continuar fase 2")

1. `radar/cv.py`:
   - Ler `cv/` (PDF via pypdf; DOCX via zipfile/xml; TXT; MD). Sem pypdf: mensagem clara pedindo `pip install pypdf`. Usar o arquivo de modificação mais recente de `cv/` (ignorar subpastas como `cv/arquivo/`) ou `--cv <arquivo>`. Mostrar no console QUAL arquivo foi usado.
   - Se o texto extraído for muito curto (ex.: < 500 caracteres, típico de PDF em imagem), avisar e NÃO calcular cobertura sobre um CV vazio.
   - Detectar skills do CV com o MESMO matcher das vagas. Nunca gravar telefone, e-mail ou links pessoais em nenhuma saída.
   - Criar `cv/README.md` e `cv/exemplo.md` (CV fictício e sintético).
2. `privado/perfil.json` criado a partir de modelo com valores de exemplo claramente marcados.
3. Elegibilidade (seção 11) em `privado/elegibilidade.json`.
4. `radar/analise.py` com as fórmulas EXATAS da seção 12:
   - ranking por skill (nº de vagas, %, score) e por categoria;
   - "em alta" (ou "dados insuficientes");
   - coocorrência: top pares de skills;
   - distribuições: senioridade, modalidade, contrato/vínculo, nível de inglês, origem, restrições;
   - recortes: BR, INT acessível, INT restrito, todos (+ "só elegíveis" no privado);
   - comparação BR × INT: skills com maior diferença de participação;
   - comparação por `familia_cargo` (Pentest × Red Team × AppSec × Gestão de vulnerabilidades);
   - faixas salariais por moeda e período (mín/mediana/máx), SEM converter moedas, mostrando o N usado;
   - seção "qualidade dos dados": possivelmente expiradas, datas estimadas, anos ambíguos, campos nulos mais frequentes;
   - `match_vaga`, `cobertura_geral` e lacunas por `score_lacuna`, com a nota: "se você já tem, escreva explicitamente no CV (ATS); se não, estude".
5. `privado/historico.json`: uma entrada por dia por recorte (data, nº de vagas ativas, cobertura_geral), sobrescrevendo a do mesmo dia.
6. `privado/relatorio-cv.md`: resumo, cobertura por recorte, top lacunas, plano de estudo por categoria (prioridade alta/média/baixa), palavras-chave para o CV e vagas elegíveis com maior match.
7. Testes das fórmulas com números calculados à mão (ex.: 4 vagas): skill em várias seções, grupo atendido por um só membro, grupo não atendido, vaga sem skills, recorte vazio, elegibilidade sim/não/talvez.

Rode testes e pipeline com `cv/exemplo.md`; confira os números do relatório contra os testes. **PARE e entregue o resumo.**

---

# FASE 3 de 5: Coletor automático (só após "continuar fase 3")

Implemente `python run.py coletar` em `radar/coletor.py` usando SOMENTE os endpoints JSON públicos oficiais dos ATS, sem login e sem raspar HTML:

- Greenhouse: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
- Lever: `https://api.lever.co/v0/postings/{slug}?mode=json`
- Ashby: `https://api.ashbyhq.com/posting-api/job-board/{slug}`
- SmartRecruiters: `https://api.smartrecruiters.com/v1/companies/{slug}/postings`

NÃO implemente coleta de LinkedIn, Indeed, Gupy ou site que proíba automação; esses continuam por `colar`/`dividir`. Antes de implementar, verifique os formatos atuais de resposta de cada API e trate campos ausentes.

1. `data/fontes.json`: `{"ats": [{"tipo","slug","mercado"}], "filtros": {"titulo_inclui": [...], "titulo_exclui": [...]}}`. Slugs de placeholder marcados "TROCAR"; não invente slugs reais.
2. Para cada vaga que passar nos filtros de título: converter HTML da descrição em texto limpo (preservando listas), gerar `.txt` na inbox com o cabeçalho da seção 6 (Origem, URL, Data) e deixar o pipeline normal processar. Quando a API informar local, remoto, departamento ou salário estruturado, preencher o cabeçalho; restrições de cidadania/residência continuam vindo do texto.
3. Dedup pela URL existente. Vaga que sumiu da API → status "arquivada" com nota "encerrada na fonte" (sem apagar). Vaga em empregador público é ignorada com motivo.
4. Boas maneiras: User-Agent identificado, timeout, pausa entre requisições, erro isolado por fonte, opção `--dry-run` sem gravar nada.
5. Testes com respostas JSON sintéticas em `tests/fixtures` (sem rede): cada ATS, campo ausente, resposta vazia, vaga que sumiu, filtro de título.
6. README: como descobrir o slug (URL da página de carreiras, ex.: `boards.greenhouse.io/{slug}`), como agendar `run.py coletar` no Agendador de Tarefas do Windows, e por que LinkedIn/Indeed/Gupy continuam manuais (alertas por e-mail + colar/dividir).

Rode testes e `coletar --dry-run`. **PARE e entregue o resumo.**

---

# FASE 4 de 5: HTML público e privado (só após "continuar fase 4")

Gere dois arquivos únicos, estáticos, sem CDN, com dados embutidos como JSON (escapar `</script>`), tema claro/escuro automático, responsivos, que abram via `file://` e no GitHub Pages.

1. **`docs/index.html` (PÚBLICO)**
   - *Painel:* totais, top 15 skills em barras CSS, categorias, "em alta" (ou "dados insuficientes"), distribuições, comparação BR × INT, comparação por família de cargo, faixas salariais com N, seletor de recorte (BR, INT acessível, INT restrito, todos).
   - *Vagas:* cards com título, empresa (ou "empresa não divulgada"), local, modalidade, senioridade, contrato/vínculo, data (selo "data estimada"), selo "possivelmente expirada", chips de restrição ("exige residência nos EUA", "clearance TS"), link; seções expansíveis (exceto texto bruto); chips de skill com tooltip da frase-evidência (máx. 200 caracteres, sem e-mails/telefones); grupos indicados como "um destes"; busca e filtros por senioridade/modalidade/contrato/mercado/família/skill/restrição.
   - NÃO contém texto bruto, status, notas, contatos, elegibilidade, nem dados do CV ou do perfil. Vagas ignoradas não aparecem.
2. **`privado/index.html`**: mesma página + match % nos cards, chips verde/vermelho conforme o CV, coluna e filtro de elegibilidade (sim/não/talvez, com motivo) e "só elegíveis", exibição de status e notas (alteração continua pelo CLI), aba "Meu CV" (lacunas priorizadas, plano de estudo, evolução da cobertura a partir de `privado/historico.json`).

Verificação EXECUTÁVEL (`tests/test_html.py`):
- extrair o JSON embutido dos dois HTML e fazer `json.loads`; garantir que `</script>` no conteúdo foi escapado;
- varrer `docs/` inteira e provar que NÃO contém: texto bruto das vagas, e-mails/telefones (regex), status/notas, conteúdo de `perfil.json`, trechos de `cv/exemplo.md`;
- garantir que não há URLs externas de scripts/estilos/fontes;
- teste com vaga sintética que tenha e-mail e telefone na frase-evidência: devem sair mascarados no público;
- se houver navegador headless, abrir os dois HTML e checar ausência de erros no console e funcionamento dos filtros; se não houver, dizer isso explicitamente.

Corrija o que falhar. **PARE e entregue o resumo.**

---

# FASE 5 de 5: IA opcional, README e fechamento (só após "continuar fase 5")

1. `radar/ia.py`: `sugerir(cv_texto, lacunas, vagas) -> str`, com backends Claude API (urllib; `ANTHROPIC_API_KEY`; modelo SOMENTE via `ANTHROPIC_MODEL`, erro claro em português se faltar) e Ollama (`OLLAMA_URL`, `OLLAMA_MODEL`). `run.py --ia` gera `privado/sugestoes-cv.md` com resumo profissional e bullets. O prompt enviado ao modelo deve:
   - proibir inventar experiência, certificações ou resultados: reescrever só o que está no CV e listar o resto como "a desenvolver";
   - não sugerir contornar exigências de cidadania, residência ou clearance (tratá-las como fora do alcance);
   - usar apenas skills e evidências agregadas (nunca texto bruto das vagas, contatos de recrutadores, nem telefone/e-mail do CV).
   Desligada por padrão; sem configuração, tudo funciona. Testar com backend simulado (mock), sem rede.
2. `README.md` em português: o que é; instalação e uso no Windows; fluxo diário (colar/dividir/coletar → processar → abrir HTML); formato do cabeçalho e do separador `=== VAGA ===`; como funciona a limpeza e como editar `ruido.json`, `secoes.json`, `filtros.json`, `familias.json`; como editar `skills.json` e testar um regex; reprocessar após editar skills; coletor e `fontes.json`; filtro de mercado privado (e a regra `governo_contratada`); restrições e elegibilidade (`perfil.json`); grupos alternativos; status; IA (aviso destacado: o backend Claude envia trechos do CV a um serviço externo); publicar `docs/` no GitHub Pages e O QUE NÃO é publicado (`privado/`, `cv/`, `data/`, `vagas/`, `tests/fixtures_reais/`); por que anúncios reais e contatos de recrutadores não devem ir para o git.
3. Revisão final: rodar TODOS os testes e o pipeline do zero (inbox limpa → vagas de exemplo); conferir que nada do CV, do perfil ou de contatos está em `docs/`; que `git status` não lista `privado/`, `cv/exemplo.md` nem `tests/fixtures_reais/` como rastreáveis (só `cv/README.md` em `cv/`); e que `data/vagas.json` não é copiado para `docs/`.

Entregue o **resumo final consolidado**: decisões das 5 fases, suposições, pendências e os comandos para eu validar tudo.
