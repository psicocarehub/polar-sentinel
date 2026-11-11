#!/usr/bin/env bash
# Gera paper/polar-sentinel.tex e .pdf a partir de paper/polar-sentinel.md (article, 11pt).
# Precisa de pandoc e tectonic (brew install pandoc tectonic).
set -euo pipefail
cd "$(dirname "$0")"
AUTOR="Marcio Andre de Souza Estevam"
ORCID="0009-0004-8551-3231"
python3 -I - polar-sentinel.md corpo.md meta.yaml "$AUTOR" "$ORCID" <<'PY'
import re
import sys

origem, corpo, meta, autor, orcid = sys.argv[1:6]
t = open(origem, encoding="utf-8").read()
t = re.sub(r"<!--.*?-->\n?", "", t, flags=re.S)
titulo = re.search(r"^# (.+)$", t, flags=re.M).group(1)
subtitulo = re.search(r"^\*(.+)\*$", t, flags=re.M).group(1)
resumo = re.search(r"^## Resumo\n+(.+?)\n(?=## )", t, flags=re.M | re.S).group(1).strip()
t = t[re.search(r"^## 1\. ", t, flags=re.M).start():]
# Referências numeradas viram lista sem marcador, uma por linha.
t = re.sub(r"^(\[\d+\] .+)$", r"\1\\", t, flags=re.M)
# URL solta vira link para poder quebrar na margem.
t = re.sub(r"(?<![<(])(https?://[^\s)\\]+)", r"<\1>", t)
open(corpo, "w", encoding="utf-8").write(t)


def y(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


autor += f" (ORCID [{orcid}](https://orcid.org/{orcid}))"
open(meta, "w", encoding="utf-8").write(
    f"title: {y(titulo)}\nsubtitle: {y(subtitulo)}\nauthor: {y(autor)}\n"
    f"date: {y('Novembro de 2026')}\nabstract: {y(resumo)}\n"
)
PY
pandoc corpo.md -f markdown-implicit_figures --metadata-file=meta.yaml --standalone --pdf-engine=xelatex \
  -V documentclass=article -V fontsize=11pt -V geometry:margin=1in -V linkcolor=blue -V urlcolor=blue -V lang=pt-BR \
  -V mainfont=texgyrepagella -V mainfontoptions="Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic" \
  -V mathfont=texgyrepagella-math.otf -V monofont=DejaVuSansMono.ttf -V monofontoptions="Scale=0.84" \
  -V header-includes="\\usepackage{xurl}" -o polar-sentinel.tex
tectonic --keep-logs polar-sentinel.tex >/dev/null 2>tectonic.err || { cat tectonic.err; exit 1; }
rm -f corpo.md meta.yaml
grep -E "Missing character|Overfull" polar-sentinel.log | sort | uniq -c | sort -rn | head || true
echo "$(pwd)/polar-sentinel.pdf"
