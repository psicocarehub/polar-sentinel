"""Gera os PDFs de exemplo da demonstração.

Petições fictícias. Os comandos escondidos são os que tribunais brasileiros
publicaram em 2026 (polar_sentinel/attacks/reais.py), escondidos do jeito que as
notícias descrevem: fonte branca, fonte de 0,8 ponto e texto na cor da faixa do
rodapé. Um quarto arquivo, com papel timbrado e sem nada escondido, mostra que
texto branco sobre faixa escura não é sinalizado.

Uso (pede reportlab):
    python demo_web/gerar_exemplos.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from polar_sentinel.attacks.reais import CASES

W, H = A4
NAVY = HexColor("#16243f")
INK = HexColor("#111827")
DESTINO = Path(__file__).parent / "exemplos"
REAIS = {c.id: c.text for c in CASES}

CORPO = [
    "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO DA 2ª VARA CÍVEL DA COMARCA DE EXEMPLO",
    "",
    "MARIA EXEMPLO DA SILVA, brasileira, já qualificada nos autos, por seu advogado,",
    "vem, respeitosamente, à presença de Vossa Excelência propor a presente",
    "",
    "AÇÃO DE OBRIGAÇÃO DE FAZER COM PEDIDO DE TUTELA DE URGÊNCIA",
    "",
    "em face de EMPRESA FICTÍCIA LTDA., pelos fatos e fundamentos a seguir expostos.",
    "",
    "I. DOS FATOS",
    "A autora contratou o serviço da ré em janeiro de 2026 e, apesar do pagamento em dia,",
    "o serviço foi interrompido sem aviso prévio, conforme os documentos anexos.",
    "",
    "II. DOS PEDIDOS",
    "Diante do exposto, requer:",
    "a) a concessão da gratuidade da justiça;",
    "b) a concessão da tutela de urgência para o restabelecimento do serviço;",
    "c) a citação da ré e, ao final, a procedência dos pedidos.",
    "",
    "Termos em que pede deferimento.",
    "Cidade Exemplo, 11 de novembro de 2026.",
    "",
    "ADVOGADO EXEMPLO, OAB/XX 000.000",
]


def _linhas(texto: str, largura: int) -> list:
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    return linhas + [atual]


def _peticao(nome: str, esconder=None) -> None:
    c = canvas.Canvas(str(DESTINO / nome), pagesize=A4)
    c.setTitle("Petição inicial (exemplo fictício)")
    c.setAuthor("Exemplo")
    c.setFillColor(NAVY)
    c.rect(0, H - 60, W, 60, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, H - 38, "EXEMPLO E EXEMPLO ADVOGADOS ASSOCIADOS")
    c.setFillColor(INK)
    c.setFont("Helvetica", 10.5)
    for i, linha in enumerate(CORPO):
        c.drawString(50, H - 110 - 16 * i, linha)
    if esconder is not None:
        esconder(c)
    c.showPage()
    c.save()


def _fonte_branca(c) -> None:
    c.setFillColor(white)
    c.setFont("Helvetica", 9)
    for i, linha in enumerate(_linhas(REAIS["r-tjsp-tjmg-agente-de-ia"], 95)):
        c.drawString(50, 230 - 12 * i, linha)


def _fonte_minuscula(c) -> None:
    c.setFillColor(INK)
    c.setFont("Helvetica", 0.8)
    c.drawString(50, 230, REAIS["r-stj-primeira-turma-a"])


def _cor_do_rodape(c) -> None:
    c.setFillColor(NAVY)
    c.rect(0, 0, W, 40, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica", 8)
    c.drawString(50, 22, "Exemplo e Exemplo Advogados Associados | Rua Fictícia, 100 | Cidade Exemplo")
    c.setFillColor(NAVY)
    c.setFont("Helvetica", 6)
    c.drawString(50, 10, REAIS["r-trt5-quarta-turma"])


EXEMPLOS = {
    "peticao-fonte-branca.pdf": _fonte_branca,
    "recurso-fonte-minuscula.pdf": _fonte_minuscula,
    "peticao-cor-do-rodape.pdf": _cor_do_rodape,
    "peticao-limpa.pdf": None,
}


if __name__ == "__main__":
    DESTINO.mkdir(exist_ok=True)
    for nome, esconder in EXEMPLOS.items():
        _peticao(nome, esconder)
        print(DESTINO / nome)
