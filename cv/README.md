# cv/

Coloque aqui o seu CV ativo (PDF, DOCX, TXT ou MD). O arquivo de modificação
mais recente dentro de `cv/` (ignorando `cv/arquivo/`) é o usado por
`python run.py analisar`. Para forçar um arquivo específico, use
`python run.py analisar --cv caminho/para/arquivo.pdf`.

- **PDF:** requer `pip install pypdf` (opcional). Sem a biblioteca, o erro
  explica como instalar.
- **DOCX:** lido via `zipfile`/XML, sem dependências externas.
- **TXT/MD:** lidos diretamente (utf-8, com fallback utf-8-sig/cp1252).

Se o texto extraído tiver menos de 500 caracteres (típico de PDF em
imagem, sem OCR), um aviso é mostrado e a cobertura **não** é calculada.

`cv/exemplo.md` é um CV fictício/sintético só para testar o pipeline —
substitua pelo seu CV real para uso de verdade.

Versões antigas do CV podem ficar em `cv/arquivo/`.

Esta pasta é ignorada pelo git (`.gitignore`), exceto este `README.md`.
