"""Polar Sentinel: falso positivo da inspecao de documento em arquivos reais.

Roda `evaluate_pdf` e `evaluate_docx` em pastas de documentos reais, que nao
foram escritos para o detector, e conta quantos seriam sinalizados. Cada
sinalizacao em documento legitimo e um falso positivo, e o que importa e a
taxa com intervalo de confianca.

Os documentos nao vem com o repositorio. Uso:
    python -m polar_sentinel.benchmarks.documentos_reais PASTA [PASTA ...] \
        [--max 300] [--saida relatorio.json]

O relatorio por arquivo (com os trechos) fica so na maquina de quem roda.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List


IMAGEM = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif")


def wilson(k: int, n: int, z: float = 1.96):
    """Intervalo de Wilson para k sucessos em n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margem = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (max(0.0, centro - margem), min(1.0, centro + margem))


def main() -> None:
    import logging

    from polar_sentinel.reference.docx_inspector import evaluate_docx
    from polar_sentinel.reference.pdf_inspector import evaluate_pdf
    from polar_sentinel.certidao import AUDIO, VIDEO
    from polar_sentinel.reference.audio_inspector import evaluate_audio
    from polar_sentinel.reference.imagem_inspector import evaluate_image
    from polar_sentinel.reference.video_inspector import evaluate_video

    sufixos = (".pdf", ".docx", *IMAGEM, *VIDEO, *AUDIO)

    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("pastas", nargs="+")
    parser.add_argument("--max", type=int, default=0, help="amostra por pasta (0 = todos)")
    parser.add_argument("--max-bytes", type=int, default=30_000_000)
    parser.add_argument("--saida", default="")
    parser.add_argument("--semente", type=int, default=20261111)
    parser.add_argument(
        "--excluir", default="", help="relatorio anterior: os arquivos dele ficam de fora"
    )
    args = parser.parse_args()

    random.seed(args.semente)
    vistos = set()
    if args.excluir:
        vistos = {a["arquivo"] for a in json.loads(Path(args.excluir).read_text())["arquivos"]}
    arquivos: List[Path] = []
    for pasta in args.pastas:
        achados = sorted(
            p
            for p in Path(pasta).rglob("*")
            if p.suffix.lower() in sufixos and str(p) not in vistos
        )
        achados = [p for p in achados if p.stat().st_size <= args.max_bytes]
        if args.max and len(achados) > args.max:
            achados = random.sample(achados, args.max)
        arquivos.extend(achados)

    linhas: List[Dict] = []
    motivos: Counter = Counter()
    atencoes: Counter = Counter()
    paginas = erros = 0
    inicio = time.time()
    for n, caminho in enumerate(arquivos, start=1):
        if n % 25 == 0:
            print(f"{n}/{len(arquivos)} arquivos, {paginas} paginas", file=sys.stderr, flush=True)
        t0 = time.time()
        try:
            sufixo = caminho.suffix.lower()
            if sufixo == ".docx":
                v = evaluate_docx(caminho)
                n_pag = 0
            elif sufixo in VIDEO:
                v = evaluate_video(caminho)
                n_pag = 0
            elif sufixo in AUDIO:
                v = evaluate_audio(caminho)
                n_pag = 0
            elif sufixo in IMAGEM:
                v = evaluate_image(caminho)
                n_pag = 0
            else:
                v = evaluate_pdf(caminho)
                n_pag = v.inspection.paginas
        except Exception as exc:  # noqa: BLE001 - arquivo corrompido conta como erro, nao como sinal
            erros += 1
            linhas.append({"arquivo": str(caminho), "erro": f"{type(exc).__name__}: {exc}"[:300]})
            continue
        paginas += n_pag
        motivos.update(v.reasons)
        atencoes.update(v.atencao)
        ocultos = [
            {
                "motivo": getattr(s, "reason", getattr(s, "motivo", "")),
                "texto": (getattr(s, "text", None) or getattr(s, "texto", ""))[:200],
            }
            for s in v.inspection.hidden_spans
        ][:10]
        linhas.append(
            {
                "arquivo": str(caminho),
                "sinalizado": v.flagged,
                "motivos": v.reasons,
                "atencao": v.atencao,
                "paginas": n_pag,
                "segundos": round(time.time() - t0, 2),
                "ocultos": ocultos,
            }
        )

    validos = [linha for linha in linhas if "erro" not in linha]
    sinalizados = sum(1 for linha in validos if linha["sinalizado"])
    com_atencao = sum(1 for linha in validos if linha["atencao"])
    baixo, alto = wilson(sinalizados, len(validos))
    resumo = {
        "arquivos": len(validos),
        "erros_de_leitura": erros,
        "paginas": paginas,
        "sinalizados": sinalizados,
        "taxa_falso_positivo": round(sinalizados / len(validos), 4) if validos else None,
        "intervalo_95": [round(baixo, 4), round(alto, 4)],
        "com_atencao": com_atencao,
        "motivos": dict(motivos),
        "atencao": dict(atencoes),
        "segundos_por_pagina": round((time.time() - inicio) / max(paginas, 1), 3),
    }
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    if args.saida:
        Path(args.saida).write_text(
            json.dumps({"resumo": resumo, "arquivos": linhas}, ensure_ascii=False, indent=2)
        )


if __name__ == "__main__":
    main()
