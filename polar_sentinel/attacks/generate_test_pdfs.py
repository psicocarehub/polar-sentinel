"""Polar Sentinel: gerador de PDFs maliciosos de teste.

Materializa o corpus de ataques (attacks/corpus.py) como arquivos PDF reais,
para que as defesas possam ser exercitadas de ponta a ponta: extracao de texto,
inspecao de metadados, deteccao de estruturas ativas e sanitizacao.

Cada PDF tem a aparencia de uma peca legitima. O vetor de ataque e embutido de
acordo com a tecnica do caso:

    plain         comando visivel no corpo (alvo da deteccao adversarial)
    raw_text      comando com artefatos no texto (largura zero, tag chars,
                  comentario HTML, ANSI), visivel na camada de texto
    white_on_white texto branco sobre fundo branco, invisivel ao leitor
    tiny_font     comando em fonte de 0,1 pt
    offpage       comando posicionado fora da area visivel da pagina
    zero_width    comando com caracteres de largura zero intercalados
    metadata      comando no titulo, autor e palavras chave do PDF
    openaction    PDF com JavaScript de abertura automatica embutido

IMPORTANTE: estes arquivos sao artefatos de teste defensivo. Nao sao provas de
conceito funcionais contra sistemas de terceiros e usam apenas dados ficticios.

Uso:
    pip install reportlab pypdf
    python -m polar_sentinel.attacks.generate_test_pdfs
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter

from polar_sentinel.attacks.corpus import CASES, AttackCase

PAGE_W, PAGE_H = A4
NAVY = HexColor("#16243f")
BLUE = HexColor("#2f6fed")
GREY = HexColor("#6b7280")

SAMPLES_DIR = Path(__file__).parent / "samples"

_LEGIT_BODY = [
    "EXCELENTISSIMO SENHOR DOUTOR JUIZ DE DIREITO.",
    "",
    "Requerente: Empresa ABC Ltda.",
    "Requerido: Empresa XYZ Ltda.",
    "",
    "Trata-se de acao em que a parte requer o deferimento da medida com base",
    "na documentacao anexa e na jurisprudencia pacifica dos tribunais.",
    "",
    "Termos em que pede deferimento.",
]


def _draw_letterhead(c: canvas.Canvas, case: AttackCase) -> None:
    """Desenha o cabecalho institucional e o corpo legitimo visivel."""
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - 2.2 * cm, PAGE_W, 2.2 * cm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, PAGE_H - 1.5 * cm, "Documento de teste  Polar Sentinel")

    c.setFillColor(GREY)
    c.setFont("Helvetica", 8)
    c.drawString(2 * cm, PAGE_H - 2.7 * cm, f"Caso: {case.id}  |  Categoria: {case.category}  |  Severidade: {case.severity}")
    c.drawString(2 * cm, PAGE_H - 3.1 * cm, "Artefato defensivo. Dados ficticios. Sem prova de conceito funcional.")

    c.setFillColor(HexColor("#111827"))
    c.setFont("Helvetica", 11)
    y = PAGE_H - 4.4 * cm
    for line in _LEGIT_BODY:
        c.drawString(2 * cm, y, line)
        y -= 0.6 * cm


def _footer(c: canvas.Canvas, case: AttackCase) -> None:
    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(2 * cm, 1.2 * cm, f"Vetor embutido: {case.name}. Defesa esperada: {case.defense}")


def _render_body_pdf(case: AttackCase) -> bytes:
    """Gera o PDF base com o vetor embutido conforme a tecnica do caso."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_letterhead(c, case)
    technique = case.pdf_technique or "plain"

    if technique == "white_on_white":
        c.setFillColor(white)
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, PAGE_H - 11 * cm, case.payload)

    elif technique == "tiny_font":
        c.setFillColor(HexColor("#111827"))
        c.setFont("Helvetica", 0.1)
        c.drawString(2 * cm, PAGE_H - 11 * cm, case.payload)

    elif technique == "offpage":
        c.setFillColor(HexColor("#111827"))
        c.setFont("Helvetica", 9)
        # Coordenada fora da area visivel da pagina.
        c.drawString(2 * cm, -50, case.payload)

    elif technique in ("plain", "raw_text", "zero_width"):
        c.setFillColor(HexColor("#111827"))
        c.setFont("Helvetica", 9)
        # Quebra o payload em linhas para caber na pagina.
        y = PAGE_H - 11 * cm
        for chunk in _wrap(case.payload, 95):
            c.drawString(2 * cm, y, chunk)
            y -= 0.5 * cm

    elif technique in ("metadata", "openaction"):
        # O corpo permanece limpo. O vetor entra via metadado ou acao.
        c.setFillColor(GREY)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(2 * cm, PAGE_H - 11 * cm, "(o vetor deste caso nao esta no corpo visivel)")

    _footer(c, case)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def _wrap(text: str, width: int) -> List[str]:
    """Quebra texto simples em linhas de no maximo `width` caracteres."""
    out: List[str] = []
    for raw_line in text.splitlines() or [text]:
        line = raw_line
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            cut = cut if cut > 0 else width
            out.append(line[:cut])
            line = line[cut:].lstrip()
        out.append(line)
    return out


def _apply_pdf_layer(case: AttackCase, body: bytes) -> bytes:
    """Aplica metadados e acoes de PDF.

    Como as fontes de PDF nao renderizam caracteres de planos suplementares
    (por exemplo tag characters) nem todos os scripts, o metadado e usado como
    canal canonical e legivel por maquina: para todo caso de ataque, os bytes
    exatos do payload sao gravados em /Keywords. Assim, cada PDF carrega o seu
    vetor independentemente da fonte. A renderizacao visivel especifica da
    tecnica e preservada por cima disso.

    O caso `doc-metadata` e o unico em que o corpo permanece limpo de proposito,
    para ilustrar a injecao exclusivamente por metadado.
    """
    technique = case.pdf_technique or "plain"

    reader = PdfReader(io.BytesIO(body))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    if case.benign:
        writer.add_metadata(
            {"/Title": "Peca processual", "/Subject": "documento de teste Polar Sentinel"}
        )
    else:
        writer.add_metadata(
            {
                "/Title": case.payload if technique == "metadata" else "Peca processual",
                "/Author": "instrucao oculta no autor" if technique == "metadata" else "Empresa ABC Ltda",
                "/Keywords": case.payload,
                "/Subject": "documento de teste Polar Sentinel",
            }
        )

    if technique == "openaction":
        # JavaScript de abertura automatica, descartado pela conversao a texto plano.
        try:
            writer.add_js("app.alert('instrucao automatica embutida no PDF');")
        except Exception:
            pass

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out.read()


def generate_one(case: AttackCase, out_dir: Path) -> Path:
    """Gera um PDF para um caso e devolve o caminho."""
    body = _render_body_pdf(case)
    final = _apply_pdf_layer(case, body)
    path = out_dir / f"{case.id}.pdf"
    path.write_bytes(final)
    return path


def generate_all(out_dir: Path = SAMPLES_DIR) -> List[Path]:
    """Gera um PDF para cada caso do corpus com tecnica de PDF definida."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for case in CASES:
        if not case.pdf_technique:
            continue
        paths.append(generate_one(case, out_dir))
    _write_index(out_dir, paths)
    return paths


def _write_index(out_dir: Path, paths: List[Path]) -> None:
    """Escreve um indice legivel dos PDFs gerados."""
    lines = [
        "# PDFs de teste do Polar Sentinel",
        "",
        "Arquivos gerados por `python -m polar_sentinel.attacks.generate_test_pdfs`.",
        "Cada PDF parece uma peca legitima e embute um vetor de ataque.",
        "Sao artefatos defensivos, com dados ficticios e sem prova de conceito funcional.",
        "",
        "| Arquivo | Caso | Categoria | Severidade | Tecnica | Defesa esperada |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    by_path = {p.name: p for p in paths}
    for case in CASES:
        name = f"{case.id}.pdf"
        if name in by_path:
            lines.append(
                f"| `{name}` | {case.name} | {case.category} | {case.severity} "
                f"| {case.pdf_technique} | {case.defense} |"
            )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    generated = generate_all()
    print(f"Gerados {len(generated)} PDFs em {SAMPLES_DIR}")
    for path in generated:
        print(f"  {path.name}")
