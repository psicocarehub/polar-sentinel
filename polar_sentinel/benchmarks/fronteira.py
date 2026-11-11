"""Polar Sentinel: onde fica a fronteira de evasao, em contraste e tamanho.

Todo detector aberto perde para um atacante que se adapta a ele. A pergunta
que interessa para o processo e outra: quanto o comando precisa ficar visivel
para escapar? Este script escreve os dez comandos reais numa grade de
contraste (cinza sobre branco) e tamanho de fonte e marca, em cada celula,
quantos foram sinalizados. A celula escapa quando nenhum e sinalizado.

A grade mede o detector, nao a leitura humana: o limite de legibilidade que a
inspecao usa e uma escolha de engenharia que ainda precisa ser calibrada com
pessoas. O que a tabela mostra e em que faixa fisica o atacante precisa ficar.

Uso (pede reportlab, pypdf, pypdfium2 e numpy):
    python -m polar_sentinel.benchmarks.fronteira
"""

from __future__ import annotations

import io
import logging

CONTRASTES = (1.05, 1.15, 1.25, 1.4, 1.6, 2.0, 2.5, 3.0, 4.5)
TAMANHOS = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def _cinza_para_contraste(alvo: float) -> float:
    """Nivel de cinza (0 a 1) cujo contraste contra o branco e `alvo`."""
    lum = 1.05 / alvo - 0.05
    return lum * 12.92 if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055


def _pdf(texto: str, cinza: float, tamanho: float) -> bytes:
    from reportlab.lib.colors import Color
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 11)
    c.drawString(50, 760, "Requer a procedência do pedido e a condenação da ré.")
    c.setFillColor(Color(cinza, cinza, cinza))
    c.setFont("Helvetica", tamanho)
    c.drawString(50, 300, texto)
    c.save()
    return buf.getvalue()


def main() -> None:
    from polar_sentinel.attacks.reais import CASES
    from polar_sentinel.reference.pdf_inspector import evaluate_pdf

    logging.disable(logging.CRITICAL)
    comandos = [c.text for c in CASES if c.group == "judiciario_brasileiro"]
    print(
        "Comandos reais sinalizados, de",
        len(comandos),
        "(linhas: tamanho em pontos; colunas: contraste)",
    )
    print("pt    " + " ".join(f"{c:>5}" for c in CONTRASTES))
    for tamanho in TAMANHOS:
        celulas = []
        for contraste in CONTRASTES:
            cinza = _cinza_para_contraste(contraste)
            pegos = sum(
                evaluate_pdf(_pdf(t, cinza, tamanho), motor="renderizacao").flagged
                for t in comandos
            )
            celulas.append(f"{pegos:>5}")
        print(f"{tamanho:<5} " + " ".join(celulas))


if __name__ == "__main__":
    main()
