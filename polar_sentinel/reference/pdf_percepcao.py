"""Polar Sentinel: o que a pessoa ve no PDF contra o que a maquina le.

A pagina e renderizada duas vezes: inteira e sem os objetos de texto. Para cada
caractere que a extracao entrega a IA, a diferenca entre as duas imagens, na
caixa do caractere, diz quanto ele muda o que aparece na tela. Daí saem medidas
fisicas, que um perito confere:

    contraste    razao de contraste de luminancia (WCAG) entre o caractere e o
                 fundo efetivamente desenhado atras dele: 1,0 e invisivel,
                 4,5 e o minimo recomendado para leitura
    tamanho_pt   tamanho da fonte em pontos
    modo         modo de renderizacao do texto (3 e 7 nao pintam nada)

Esse metodo nao depende de adivinhar o fundo. Texto branco sobre a pagina
branca, verde dentro da faixa verde do escritorio, texto atras de uma imagem,
recortado por um caminho de recorte, transparente ou fora da pagina: em todos
os casos o caractere e extraido e nao muda a imagem. Papel timbrado com texto
branco sobre faixa escura muda a imagem e segue como visivel.

Motivos, por caractere:

    fora_da_pagina         a caixa do caractere esta fora da area exibida
    fonte_minuscula        menos de 2 pontos
    camada_ocr             modo invisivel sobre uma imagem: e a camada de texto
                           de um documento digitalizado e segue como visivel
    ocr_divergente         camada de texto que nao confere com o que a imagem
                           embaixo mostra (conferida com o Tesseract, quando
                           instalado): o "OCR induzido a erro" da nota do CNJ
    modo_invisivel         modo invisivel sem imagem embaixo
    transparente           opacidade de preenchimento quase zero
    cor_do_fundo           contraste abaixo do limiar e cor igual a do fundo
    coberto_ou_recortado   contraste abaixo do limiar com cor diferente da do
                           fundo: ha um objeto por cima ou um recorte
    baixo_contraste        acima do limiar de invisivel, abaixo do de leitura,
                           que sobe quando a letra e pequena (3:1 abaixo de 4
                           pontos, 2:1 abaixo de 6, 1,6:1 acima); vai para o
                           texto visivel e tambem e relatado

Os limiares de contraste sao escolhas de engenharia, nao medidas com pessoas.
A calibracao com leitores reais e trabalho pendente e esta em docs/AVALIACAO.md.

Precisa de pypdfium2 e numpy (pip install "polar-sentinel[pdf]").
"""

from __future__ import annotations

import ctypes
import io
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# Resolucao de trabalho: 2 pixels por ponto (144 dpi).
ESCALA = 2.0
# Abaixo desta razao de contraste o caractere nao aparece para quem le.
LIMIAR_INVISIVEL = 1.25
# Letra grande aparece com menos contraste (marca d'agua cinza clara de 50 pontos
# e visivel): (tamanho a partir de, contraste minimo para aparecer).
VISIBILIDADE_POR_TAMANHO = ((24.0, 1.08), (12.0, 1.15))
# Abaixo desta, aparece mas mal se le.
LIMIAR_BAIXO_CONTRASTE = 1.6
# Abaixo deste tamanho, em pontos, ninguem le.
MIN_LEGIVEL_PT = 2.0
# Letra pequena precisa de mais contraste para ser lida: (tamanho ate, contraste minimo).
LEGIBILIDADE_POR_TAMANHO = ((4.0, 3.0), (6.0, 2.0))


def contraste_visivel(tamanho_pt: float) -> float:
    """Contraste abaixo do qual um texto deste tamanho nao aparece."""
    for desde, minimo in VISIBILIDADE_POR_TAMANHO:
        if tamanho_pt >= desde:
            return minimo
    return LIMIAR_INVISIVEL


def contraste_legivel(tamanho_pt: float) -> float:
    """Contraste minimo para um texto deste tamanho contar como legivel."""
    for ate, minimo in LEGIBILIDADE_POR_TAMANHO:
        if tamanho_pt < ate:
            return minimo
    return LIMIAR_BAIXO_CONTRASTE


# Diferenca de luminancia (0 a 1) a partir da qual um pixel conta como pintado.
_PIXEL_PINTADO = 0.03
# Opacidade (0 a 255) abaixo da qual o preenchimento e transparente.
_ALFA_MINIMO = 26
# Distancia de cor (0 a 1, por componente) para "mesma cor do fundo".
_MESMA_COR = 0.12

VISIVEIS = frozenset({"", "camada_ocr", "baixo_contraste"})
_MODOS_INVISIVEIS = {3, 7}


@dataclass
class Caractere:
    """Medidas de um caractere extraido."""

    texto: str
    motivo: str
    caixa: Tuple[float, float, float, float]
    contraste: float
    tamanho_pt: float
    cor_texto: Tuple[int, int, int, int]
    cor_fundo: Tuple[int, int, int]
    modo: int
    angulo: float


@dataclass
class PaginaPercebida:
    """Uma pagina com os caracteres medidos."""

    numero: int
    largura: float
    altura: float
    caracteres: List[Caractere] = field(default_factory=list)
    tem_imagem: bool = False
    # Leitura das imagens da pagina (reference/imagem_inspector.py), quando feita.
    imagem: Any = None


def _bytes_de(source: Union[str, Path, bytes, Any]) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    pos = source.tell() if hasattr(source, "tell") else None
    dados = source.read()
    if pos is not None and hasattr(source, "seek"):
        source.seek(pos)
    return dados


def _tabela_linear():
    import numpy as np

    c = np.arange(256) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _luminancia(rgb, tabela):
    """Luminancia relativa (WCAG) de uma imagem RGB de 8 bits."""
    return (
        0.2126 * tabela[rgb[..., 0]] + 0.7152 * tabela[rgb[..., 1]] + 0.0722 * tabela[rgb[..., 2]]
    )


def _razao(a: float, b: float) -> float:
    alto, baixo = max(a, b), min(a, b)
    return (alto + 0.05) / (baixo + 0.05)


def _para_dispositivo(
    page_raw, largura_px: int, altura_px: int, x: float, y: float
) -> Tuple[int, int]:
    import pypdfium2.raw as raw

    dx, dy = ctypes.c_int(), ctypes.c_int()
    raw.FPDF_PageToDevice(page_raw, 0, 0, largura_px, altura_px, 0, x, y, dx, dy)
    return dx.value, dy.value


def _objetos(page, tipo: int):
    return [o for o in page.get_objects(max_depth=15) if o.type == tipo]


def _limites(objeto) -> Tuple[float, float, float, float]:
    import pypdfium2.raw as raw

    esq, base, dir_, topo = (ctypes.c_float() for _ in range(4))
    raw.FPDFPageObj_GetBounds(objeto.raw, esq, base, dir_, topo)
    return esq.value, base.value, dir_.value, topo.value


def _renderizar(page):
    import numpy as np

    bitmap = page.render(scale=ESCALA, draw_annots=False, may_draw_forms=False, rev_byteorder=True)
    return np.array(bitmap.to_numpy()[..., :3], dtype=np.uint8)


def medir_pagina(page, numero: int, tabela) -> PaginaPercebida:
    """Mede cada caractere de uma pagina ja aberta no pdfium."""
    import numpy as np
    import pypdfium2.raw as raw

    largura, altura = page.get_size()
    texto_pagina = page.get_textpage()
    imagens = [_limites(o) for o in _objetos(page, raw.FPDF_PAGEOBJ_IMAGE)]
    cheia = _renderizar(page)
    for objeto in _objetos(page, raw.FPDF_PAGEOBJ_TEXT):
        raw.FPDFPageObj_SetIsActive(objeto.raw, False)
    fundo = _renderizar(page)
    lum_cheia = _luminancia(cheia, tabela)
    lum_fundo = _luminancia(fundo, tabela)
    alt_px, larg_px = lum_cheia.shape

    pagina = PaginaPercebida(numero, largura, altura, tem_imagem=bool(imagens))
    r_, g_, b_, a_ = (ctypes.c_uint() for _ in range(4))
    matriz = raw.FS_MATRIX()
    for i in range(texto_pagina.count_chars()):
        codigo = raw.FPDFText_GetUnicode(texto_pagina.raw, i)
        ch = chr(codigo) if codigo else ""
        if not ch:
            continue
        if not ch.strip() or raw.FPDFText_IsGenerated(texto_pagina.raw, i) == 1:
            pagina.caracteres.append(
                Caractere(
                    ch, "espaco", (0, 0, 0, 0), 0.0, 0.0, (0, 0, 0, 255), (255, 255, 255), 0, 0.0
                )
            )
            continue
        esq, base, dir_, topo = texto_pagina.get_charbox(i)
        # Tamanho efetivo: o Tf vezes a escala da matriz do caractere (texto e
        # pagina). Gerador que escreve fonte 1 com matriz 40 desenha letra de 40.
        raw.FPDFText_GetMatrix(texto_pagina.raw, i, matriz)
        escala = abs(matriz.a * matriz.d - matriz.b * matriz.c) ** 0.5 or 1.0
        tamanho = float(raw.FPDFText_GetFontSize(texto_pagina.raw, i)) * escala
        objeto = raw.FPDFText_GetTextObject(texto_pagina.raw, i)
        modo = int(raw.FPDFTextObj_GetTextRenderMode(objeto)) if objeto else 0
        raw.FPDFText_GetFillColor(texto_pagina.raw, i, r_, g_, b_, a_)
        cor_texto = (r_.value, g_.value, b_.value, a_.value)
        angulo = float(raw.FPDFText_GetCharAngle(texto_pagina.raw, i))

        x0, y0 = _para_dispositivo(page.raw, larg_px, alt_px, esq, topo)
        x1, y1 = _para_dispositivo(page.raw, larg_px, alt_px, dir_, base)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        dentro = x1 >= 0 and y1 >= 0 and x0 < larg_px and y0 < alt_px
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1 + 1, larg_px), min(y1 + 1, alt_px)

        contraste, cor_fundo = 1.0, (255, 255, 255)
        if dentro and x1 > x0 and y1 > y0:
            regiao_cheia = lum_cheia[y0:y1, x0:x1]
            regiao_fundo = lum_fundo[y0:y1, x0:x1]
            cor_fundo = tuple(int(v) for v in fundo[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0))
            diferenca = np.abs(regiao_cheia - regiao_fundo)
            pico = float(diferenca.max())
            if pico > _PIXEL_PINTADO:
                # O caractere foi pintado: o contraste e o da cor dele contra o
                # fundo que ficou atras do traco. Medir nos pixels da imagem
                # subestima letra pequena, cujo traco nao cobre um pixel inteiro.
                nucleo = diferenca >= pico * 0.5
                lum_atras = float(regiao_fundo[nucleo].mean())
                alfa = cor_texto[3] / 255
                lum_letra = (
                    alfa * float(_luminancia(np.array(cor_texto[:3], dtype=np.uint8), tabela))
                    + (1 - alfa) * lum_atras
                )
                contraste = _razao(lum_letra, lum_atras)

        centro = ((esq + dir_) / 2, (base + topo) / 2)
        sobre_imagem = any(a <= centro[0] <= c and b <= centro[1] <= d for a, b, c, d in imagens)
        if not dentro:
            motivo = "fora_da_pagina"
        elif 0 < tamanho < MIN_LEGIVEL_PT:
            motivo = "fonte_minuscula"
        elif modo in _MODOS_INVISIVEIS:
            motivo = "camada_ocr" if sobre_imagem else "modo_invisivel"
        elif contraste < contraste_visivel(tamanho):
            if cor_texto[3] < _ALFA_MINIMO:
                motivo = "transparente"
            elif all(abs(t - f) / 255 <= _MESMA_COR for t, f in zip(cor_texto[:3], cor_fundo)):
                motivo = "cor_do_fundo"
            else:
                motivo = "coberto_ou_recortado"
        elif contraste < contraste_legivel(tamanho):
            motivo = "baixo_contraste"
        else:
            motivo = ""
        pagina.caracteres.append(
            Caractere(
                ch,
                motivo,
                (esq, base, dir_, topo),
                round(contraste, 2),
                round(tamanho, 2),
                cor_texto,
                cor_fundo,
                modo,
                angulo,
            )
        )
    return pagina


_MIN_LETRAS_LINHA = 12
_SEMELHANCA_MINIMA = 0.5


def tesseract_disponivel() -> bool:
    import shutil

    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _palavras_ocr(
    imagem, escala: float, altura_pt: float
) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    """Roda o Tesseract na imagem e devolve palavras com caixa em pontos do PDF."""
    import subprocess

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(imagem).save(buf, format="PNG")
    saida = subprocess.run(
        ["tesseract", "-", "-", "-l", "por", "--psm", "3", "tsv"],
        input=buf.getvalue(),
        capture_output=True,
        timeout=120,
    ).stdout
    palavras = []
    for linha in saida.decode("utf-8", "replace").splitlines()[1:]:
        campos = linha.split("\t")
        if len(campos) < 12 or not campos[11].strip():
            continue
        x, y, w, h = (int(v) for v in campos[6:10])
        palavras.append(
            (
                campos[11],
                (
                    x / escala,
                    altura_pt - (y + h) / escala,
                    (x + w) / escala,
                    altura_pt - y / escala,
                ),
            )
        )
    return palavras


def _linhas_ocr(pagina: PaginaPercebida) -> List[List[int]]:
    """Indices dos caracteres da camada de OCR, agrupados por linha."""
    linhas: List[List[int]] = []
    atual: List[int] = []
    for i, c in enumerate(pagina.caracteres):
        if c.motivo == "camada_ocr":
            if atual and pagina.caracteres[atual[-1]].caixa[1] - c.caixa[3] > 0:
                linhas.append(atual)
                atual = []
            atual.append(i)
        elif c.texto in "\r\n" and atual:
            linhas.append(atual)
            atual = []
    if atual:
        linhas.append(atual)
    return linhas


def conferir_camada_ocr(page, pagina: PaginaPercebida, escala: float = 3.0) -> None:
    """Marca como ocr_divergente as linhas da camada de OCR que a imagem nao confirma."""
    import difflib
    import re

    import numpy as np
    import pypdfium2.raw as raw

    linhas = _linhas_ocr(pagina)
    if not linhas:
        return
    for objeto in _objetos(page, raw.FPDF_PAGEOBJ_TEXT):
        raw.FPDFPageObj_SetIsActive(objeto.raw, False)
    bitmap = page.render(scale=escala, draw_annots=False, may_draw_forms=False, rev_byteorder=True)
    imagem = np.array(bitmap.to_numpy()[..., :3], dtype=np.uint8)
    palavras = _palavras_ocr(imagem, escala, pagina.altura)

    def limpo(texto: str) -> str:
        from polar_sentinel.reference.injection_detector import fold

        return re.sub(r"[^a-z0-9]", "", fold(texto))

    for indices in linhas:
        cs = [pagina.caracteres[i] for i in indices]
        camada = limpo("".join(c.texto for c in cs))
        if sum(ch.isalpha() for ch in camada) < _MIN_LETRAS_LINHA:
            continue
        esq, base = min(c.caixa[0] for c in cs), min(c.caixa[1] for c in cs)
        dir_, topo = max(c.caixa[2] for c in cs), max(c.caixa[3] for c in cs)
        lidas = [
            p
            for p, (a, b, c, d) in palavras
            if a < dir_
            and c > esq
            and b < topo
            and d > base
            and min(d, topo) - max(b, base) > 0.5 * (topo - base)
        ]
        semelhanca = difflib.SequenceMatcher(None, camada, limpo("".join(lidas))).ratio()
        if semelhanca < _SEMELHANCA_MINIMA:
            for c in cs:
                c.motivo = "ocr_divergente"


def _hex(cor: Sequence[int]) -> str:
    return "#" + "".join(f"{int(v):02x}" for v in cor[:3])


def agrupar(pagina: PaginaPercebida) -> List[Dict[str, Any]]:
    """Junta caracteres seguidos com o mesmo motivo em trechos, com as medidas."""
    trechos: List[Dict[str, Any]] = []
    atual: Optional[Dict[str, Any]] = None
    for c in pagina.caracteres:
        if c.motivo == "espaco":
            if atual is not None:
                atual["texto"] += c.texto
            continue
        if c.motivo == "":
            atual = None
            continue
        if atual is None or atual["motivo"] != c.motivo:
            atual = {"motivo": c.motivo, "texto": "", "caracteres": []}
            trechos.append(atual)
        atual["texto"] += c.texto
        atual["caracteres"].append(c)
    saida = []
    for t in trechos:
        cs: List[Caractere] = t["caracteres"]
        caixa = (
            min(c.caixa[0] for c in cs),
            min(c.caixa[1] for c in cs),
            max(c.caixa[2] for c in cs),
            max(c.caixa[3] for c in cs),
        )
        saida.append(
            {
                "pagina": pagina.numero,
                "motivo": t["motivo"],
                "texto": " ".join(t["texto"].split()),
                "medidas": {
                    "contraste": round(statistics.median(c.contraste for c in cs), 2),
                    "tamanho_pt": round(statistics.median(c.tamanho_pt for c in cs), 2),
                    "cor_texto": _hex(statistics.mode(c.cor_texto for c in cs)),
                    "opacidade": round(statistics.median(c.cor_texto[3] for c in cs) / 255, 2),
                    "cor_fundo": _hex(statistics.mode(c.cor_fundo for c in cs)),
                    "modo": statistics.mode(c.modo for c in cs),
                    "rotacao_graus": round(statistics.median(c.angulo for c in cs) * 57.2958, 1),
                    "posicao_pt": [round(v, 1) for v in caixa],
                    "pagina_pt": [round(pagina.largura, 1), round(pagina.altura, 1)],
                },
            }
        )
    return saida


def texto_visivel(pagina: PaginaPercebida) -> str:
    return "".join(
        c.texto for c in pagina.caracteres if c.motivo in VISIVEIS or c.motivo == "espaco"
    )


def _escala_das_imagens(page) -> float:
    """Pixels por ponto que preservam a resolucao da imagem mais fina da pagina (2 a 4)."""
    import pypdfium2.raw as raw

    melhor = 2.0
    for objeto in _objetos(page, raw.FPDF_PAGEOBJ_IMAGE):
        largura_px, altura_px = ctypes.c_uint(), ctypes.c_uint()
        if not raw.FPDFImageObj_GetImagePixelSize(objeto.raw, largura_px, altura_px):
            continue
        esq, base, dir_, topo = _limites(objeto)
        if dir_ - esq > 50 and topo - base > 50:
            melhor = max(melhor, largura_px.value / (dir_ - esq), altura_px.value / (topo - base))
    return min(melhor, 4.0)


def ler_imagens_da_pagina(page, pagina: PaginaPercebida, escala: Optional[float] = None) -> None:
    """Le as imagens da pagina (sem o texto) com o inspetor de imagem.

    A pagina e desenhada na resolucao da imagem que ela traz (ate 288 dpi),
    para que letra miuda de um digitalizado de 300 dpi nao se perca.
    """
    import numpy as np
    import pypdfium2.raw as raw
    from PIL import Image

    from polar_sentinel.reference.imagem_inspector import inspecionar_imagem

    escala = escala or _escala_das_imagens(page)
    for objeto in _objetos(page, raw.FPDF_PAGEOBJ_TEXT):
        raw.FPDFPageObj_SetIsActive(objeto.raw, False)
    bitmap = page.render(scale=escala, draw_annots=False, may_draw_forms=False, rev_byteorder=True)
    imagem = Image.fromarray(np.array(bitmap.to_numpy()[..., :3], dtype=np.uint8))
    pagina.imagem = inspecionar_imagem(
        imagem, pt_por_px=1 / escala, pagina=pagina.numero, reducao=False
    )


def perceber_pdf(
    source: Union[str, Path, bytes, Any],
    conferir_ocr: Optional[bool] = None,
    ler_imagens: Optional[bool] = None,
) -> List[PaginaPercebida]:
    """Mede todas as paginas de um PDF.

    `conferir_ocr` confere a camada de texto das paginas digitalizadas com o
    Tesseract; `ler_imagens` le as imagens das paginas que tem imagem (o
    digitalizado sem camada de texto, a ordem apagada dentro de uma figura).
    Sem escolha, os dois rodam quando o Tesseract esta instalado.
    """
    import pypdfium2 as pdfium

    if conferir_ocr is None:
        conferir_ocr = tesseract_disponivel()
    if ler_imagens is None:
        ler_imagens = tesseract_disponivel()
    tabela = _tabela_linear()
    documento = pdfium.PdfDocument(io.BytesIO(_bytes_de(source)))
    try:
        paginas = []
        for i in range(len(documento)):
            page = documento[i]
            pagina = medir_pagina(page, i + 1, tabela)
            if conferir_ocr:
                conferir_camada_ocr(page, pagina)
            if ler_imagens and pagina.tem_imagem:
                ler_imagens_da_pagina(page, pagina)
            paginas.append(pagina)
        return paginas
    finally:
        documento.close()


def disponivel() -> bool:
    try:
        import numpy  # noqa: F401
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True
