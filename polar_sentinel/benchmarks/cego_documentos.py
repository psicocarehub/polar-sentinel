"""Polar Sentinel: conjunto cego de documentos e midias (PDF, .docx, imagem, video, audio).

O conjunto foi escrito por quem nao leu o codigo do detector: ataques com
formas de esconder escolhidas pelo autor e documentos legitimos feitos para
confundir. Fica fora do repositorio, com um `rotulos.csv` (arquivo, rotulo,
tecnica, descricao). Rodar uma vez, reportar o resultado e nao ajustar regra
olhando para ele; depois disso ele vira conjunto de desenvolvimento.

Uso:
    python -m polar_sentinel.benchmarks.cego_documentos PASTA
"""

from __future__ import annotations

import argparse
import csv
import logging
from collections import defaultdict
from pathlib import Path

from polar_sentinel.benchmarks.documentos_reais import wilson


def main() -> None:
    from polar_sentinel.certidao import AUDIO, VIDEO
    from polar_sentinel.reference.audio_inspector import evaluate_audio
    from polar_sentinel.reference.docx_inspector import evaluate_docx
    from polar_sentinel.reference.video_inspector import evaluate_video
    from polar_sentinel.reference.imagem_inspector import evaluate_image
    from polar_sentinel.reference.pdf_inspector import evaluate_pdf

    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser()
    parser.add_argument("pasta")
    args = parser.parse_args()
    pasta = Path(args.pasta)

    por_rotulo = defaultdict(lambda: [0, 0])
    por_tecnica = defaultdict(lambda: [0, 0])
    linhas = []
    with open(pasta / "rotulos.csv", newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            caminho = pasta / linha["arquivo"]
            try:
                sufixo = caminho.suffix.lower()
                if sufixo == ".docx":
                    v = evaluate_docx(caminho)
                elif sufixo == ".pdf":
                    v = evaluate_pdf(caminho)
                elif sufixo in VIDEO:
                    v = evaluate_video(caminho)
                elif sufixo in AUDIO:
                    v = evaluate_audio(caminho)
                else:
                    v = evaluate_image(caminho)
                sinal, motivos, atencao = v.flagged, v.reasons, v.atencao
            except Exception as exc:  # noqa: BLE001
                sinal, motivos, atencao = False, [f"erro: {type(exc).__name__}"], []
            rotulo = linha["rotulo"]
            acerto = sinal if rotulo == "ataque" else not sinal
            por_rotulo[rotulo][0] += int(sinal)
            por_rotulo[rotulo][1] += 1
            por_tecnica[(rotulo, linha["tecnica"])][0] += int(acerto)
            por_tecnica[(rotulo, linha["tecnica"])][1] += 1
            linhas.append((rotulo, linha["tecnica"], linha["arquivo"], sinal, motivos, atencao))

    for rotulo, (sinalizados, total) in sorted(por_rotulo.items()):
        baixo, alto = wilson(sinalizados, total)
        print(
            f"{rotulo}: {sinalizados}/{total} sinalizados ({sinalizados / total:.1%}; "
            f"intervalo de 95%: {baixo:.1%} a {alto:.1%})"
        )
    print("\nAcertos por tecnica:")
    for (rotulo, tecnica), (acertos, total) in sorted(por_tecnica.items()):
        print(f"  {rotulo:<9} {tecnica:<40} {acertos}/{total}")
    print("\nErros:")
    for rotulo, tecnica, arquivo, sinal, motivos, atencao in linhas:
        if (rotulo == "ataque") != sinal:
            print(f"  {rotulo:<9} {arquivo:<45} {tecnica:<30} motivos={motivos} atencao={atencao}")


if __name__ == "__main__":
    main()
