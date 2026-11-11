"""Polar Sentinel: testes da inspecao de .docx.

Os arquivos sao montados aqui, em XML, com as formas de esconder que o Word
oferece: propriedade oculto (no trecho e no estilo), letra branca, letra na cor
do sombreamento, fonte de 1 ponto, texto apagado com controle de alteracoes,
comentario, texto alternativo de imagem e codigo de campo.
"""

from __future__ import annotations

import io
import logging
import zipfile

import pytest

from polar_sentinel.attacks.reais import CASES as REAIS
from polar_sentinel.reference.docx_inspector import evaluate_docx, inspect_docx

logging.disable(logging.CRITICAL)

COMANDO = next(c.text for c in REAIS if c.id == "r-stj-sexta-turma")
NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
)
CORPO = (
    "<w:p><w:r><w:t>EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO.</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Requer a concessão da tutela de urgência e a procedência do pedido."
    "</w:t></w:r></w:p>"
)


def _docx(extra: str = "", estilos: str = "", comentarios: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document {NS}><w:body>{CORPO}{extra}</w:body></w:document>',
        )
        z.writestr("word/styles.xml", f'<?xml version="1.0"?><w:styles {NS}>{estilos}</w:styles>')
        if comentarios:
            z.writestr(
                "word/comments.xml",
                f'<?xml version="1.0"?><w:comments {NS}>{comentarios}</w:comments>',
            )
    return buf.getvalue()


def _run(props: str, texto: str = COMANDO) -> str:
    return f"<w:p><w:r><w:rPr>{props}</w:rPr><w:t>{texto}</w:t></w:r></w:p>"


@pytest.mark.parametrize(
    "props,motivo",
    [
        ("<w:vanish/>", "oculto"),
        ('<w:color w:val="FFFFFF"/>', "cor_do_fundo"),
        ('<w:color w:val="1F5F3A"/><w:shd w:val="clear" w:fill="1F5F3A"/>', "cor_do_fundo"),
        ('<w:color w:val="000000"/><w:highlight w:val="black"/>', "cor_do_fundo"),
        ('<w:sz w:val="2"/>', "fonte_minuscula"),
    ],
    ids=["oculto", "branco", "cor_do_sombreamento", "preto_no_realce_preto", "um_ponto"],
)
def test_trecho_escondido_e_sinalizado(props, motivo):
    veredito = evaluate_docx(_docx(_run(props)))
    assert veredito.flagged, veredito.reasons
    assert [t.motivo for t in veredito.inspection.hidden_spans] == [motivo]
    assert "acolher" not in veredito.inspection.visible_text


def test_oculto_pelo_estilo():
    estilo = (
        '<w:style w:type="character" w:styleId="Nota"><w:rPr><w:vanish/></w:rPr></w:style>'
        '<w:style w:type="character" w:styleId="NotaFilha"><w:basedOn w:val="Nota"/></w:style>'
    )
    veredito = evaluate_docx(_docx(_run('<w:rStyle w:val="NotaFilha"/>'), estilos=estilo))
    assert veredito.flagged, veredito.reasons


def test_texto_excluido_com_controle_de_alteracoes():
    excluido = (
        f'<w:p><w:del w:id="1" w:author="x"><w:r><w:delText>{COMANDO}</w:delText></w:r>'
        "</w:del></w:p>"
    )
    veredito = evaluate_docx(_docx(excluido))
    assert veredito.flagged, veredito.reasons
    assert veredito.inspection.hidden_spans[0].motivo == "texto_excluido"


def test_ordem_em_comentario():
    comentario = (
        f'<w:comment w:id="0" w:author="x"><w:p><w:r><w:t>{COMANDO}</w:t></w:r></w:p></w:comment>'
    )
    veredito = evaluate_docx(_docx(comentarios=comentario))
    assert "ordem_em_comentario" in veredito.reasons


def test_ordem_no_texto_alternativo_de_imagem():
    desenho = (
        f'<w:p><w:r><w:drawing><wp:inline><wp:docPr id="1" name="img" descr="{COMANDO}"/>'
        "</wp:inline></w:drawing></w:r></w:p>"
    )
    veredito = evaluate_docx(_docx(desenho))
    assert "ordem_em_texto_alternativo" in veredito.reasons


def test_branco_sobre_celula_escura_e_visivel():
    tabela = (
        '<w:tbl><w:tr><w:tc><w:tcPr><w:shd w:val="clear" w:fill="16243F"/></w:tcPr>'
        '<w:p><w:r><w:rPr><w:color w:val="FFFFFF"/></w:rPr>'
        "<w:t>EXEMPLO ADVOGADOS ASSOCIADOS</w:t></w:r></w:p>"
        "</w:tc></w:tr></w:tbl>"
    )
    veredito = evaluate_docx(_docx(tabela))
    assert not veredito.flagged, veredito.reasons
    assert not veredito.inspection.hidden_spans
    assert "EXEMPLO ADVOGADOS" in veredito.inspection.visible_text


def test_peticao_limpa_e_liberada():
    veredito = evaluate_docx(_docx())
    assert not veredito.flagged, veredito.reasons
    assert "tutela de urgência" in inspect_docx(_docx()).visible_text
