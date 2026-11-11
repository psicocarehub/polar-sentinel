#!/usr/bin/env bash
# Monta o site estático da demonstração em uma pasta (padrão: _site).
# Usado pela publicação no GitHub Pages e para testar localmente.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
DESTINO="${1:-$RAIZ/_site}"
PYTHON="${PYTHON:-python3}"

rm -rf "$DESTINO"
mkdir -p "$DESTINO/exemplos"
cp "$RAIZ/demo_web/index.html" "$RAIZ/demo_web/app.py" "$DESTINO/"
cp "$RAIZ"/demo_web/exemplos/*.pdf "$DESTINO/exemplos/"
"$PYTHON" -m pip wheel "$RAIZ" --no-deps --quiet -w "$DESTINO"
touch "$DESTINO/.nojekyll"

"$PYTHON" - "$DESTINO" <<'PY'
import json, pathlib, sys
destino = pathlib.Path(sys.argv[1])
roda = next(destino.glob("polar_sentinel-*.whl")).name
exemplos = sorted(p.name for p in (destino / "exemplos").glob("*.pdf"))
(destino / "pacote.json").write_text(json.dumps({"roda": roda, "exemplos": exemplos}, indent=2))
print(f"site em {destino}: {roda}, {len(exemplos)} exemplos")
PY
