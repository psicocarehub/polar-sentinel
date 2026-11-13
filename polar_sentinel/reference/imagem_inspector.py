"""Polar Sentinel: o que um modelo le numa imagem e a pessoa nao ve.

Modelos que leem imagem (e PDF digitalizado vira imagem) leem texto que passa
despercebido: letras quase da cor do papel, letras pequenas demais, texto que
so aparece quando o sistema reduz a imagem antes de entrega-la ao modelo, e
texto nos metadados. Este modulo procura os quatro.

Como funciona:

    leitura normal      o Tesseract le a imagem ampliada duas vezes; cada
                        palavra ganha medidas na imagem original
    leitura amplificada o fundo do papel e estimado por mediana local; o que
                        fica um pouco mais escuro que ele, longe do texto
                        forte, vira preto e e lido de novo. Acha letra quase
                        da cor do papel
    transparencia       imagem com canal alfa e lida tambem como um sistema que
                        so descarta a transparencia; texto que so aparece assim
                        estava nos pixels transparentes
    reducao             a imagem e reduzida sem suavizacao (vizinho mais
                        proximo e bilinear, como em bibliotecas de visao) para
                        tamanhos comuns de entrada de modelo; palavra que so
                        aparece reduzida e o ataque de escala
    metadados           descricao, comentario, autor, XMP, blocos de texto do PNG

Medidas de cada palavra: contraste WCAG entre os pixels da letra e o papel em
volta, na imagem original, e altura em pontos no tamanho de exibicao. Os
limiares sao os mesmos do PDF (reference/pdf_percepcao.py).

Limite: o leitor e o Tesseract. Um modelo de visao le texto distorcido ou
muito apagado que o Tesseract nao le; o que ele nao le, este modulo nao acha.
Precisa de Pillow, numpy e do binario tesseract com o idioma por.
"""

from __future__ import annotations

import io
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from polar_sentinel.reference.pdf_estrutura import Achado

# Diferenca (0 a 1) acima da qual um pixel conta como tinta forte, ja visivel.
_TINTA_FORTE = 0.08
# Menor diferenca que a leitura amplificada considera, acima do ruido do papel.
_TINTA_FRACA = 0.006
# Confianca minima do Tesseract para uma palavra contar.
_CONFIANCA = 40
# Tamanhos (lado maior) para onde sistemas costumam reduzir a imagem.
TAMANHOS_DE_MODELO = (336, 384, 448, 512, 672, 768, 896, 1024)
METODOS_DE_REDUCAO = ("vizinho", "vizinho_canto", "bilinear")
# Fracao de pixels que so a reducao sem suavizacao mostra, a partir da qual a
# reducao e lida (veja _reducoes_suspeitas).
SINAL_DE_ESCALA = 0.0002
# Pontos por pixel quando a imagem e exibida a 96 dpi.
PT_POR_PX = 0.75
_PALAVRA = re.compile(r"[^\W\d_]{3,}")


@dataclass
class Palavra:
    texto: str
    caixa: Tuple[int, int, int, int]  # x0, y0, x1, y1 na imagem original
    linha: Tuple[int, ...]
    confianca: float


@dataclass
class TrechoImagem:
    """Um trecho que o modelo le e a pessoa nao ve."""

    texto: str
    motivo: str
    medidas: Dict[str, Any] = field(default_factory=dict)
    page: Optional[int] = None

    @property
    def text(self) -> str:
        return self.texto

    @property
    def reason(self) -> str:
        return self.motivo


@dataclass
class ImagemInspecao:
    visible_text: str
    hidden_spans: List[TrechoImagem] = field(default_factory=list)
    achados: List[Achado] = field(default_factory=list)
    motor: str = "imagem"
    paginas: int = 1


def disponivel() -> bool:
    from polar_sentinel.reference.pdf_percepcao import tesseract_disponivel

    try:
        import numpy  # noqa: F401
    except ImportError:
        return False
    return tesseract_disponivel()


def _abrir(source: Union[str, Path, bytes, Any]):
    from PIL import Image, ImageOps

    if isinstance(source, (str, Path)):
        img = Image.open(source)
    elif isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    elif hasattr(source, "convert"):
        img = source
    else:
        img = Image.open(source)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001 - EXIF malformado nao impede a leitura
        pass
    return img


def _ocr(imagem, escala: float, psm: str = "11") -> List[Palavra]:
    """Le uma imagem em tons de cinza; caixas devolvidas na escala original."""
    buf = io.BytesIO()
    imagem.save(buf, format="PNG")
    saida = subprocess.run(
        ["tesseract", "-", "-", "-l", "por", "--psm", psm, "tsv"],
        input=buf.getvalue(),
        capture_output=True,
        timeout=180,
    ).stdout.decode("utf-8", "replace")
    palavras = []
    for linha in saida.splitlines()[1:]:
        campos = linha.split("\t")
        if len(campos) < 12 or not campos[11].strip():
            continue
        try:
            confianca = float(campos[10])
        except ValueError:
            continue
        if confianca < _CONFIANCA:
            continue
        x, y, w, h = (int(v) for v in campos[6:10])
        caixa = (int(x / escala), int(y / escala), int((x + w) / escala), int((y + h) / escala))
        palavras.append(Palavra(campos[11], caixa, tuple(int(v) for v in campos[2:5]), confianca))
    return palavras


def _residuo(imagem):
    """Quanto cada pixel difere do papel em volta (0 a 1), mais claro ou mais escuro.

    Em imagem colorida, vale a maior diferenca entre os canais: amarelo claro
    sobre branco quase nao muda a luminancia, mas muda o azul.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    largura, altura = imagem.size
    meia = imagem.resize((max(largura // 2, 1), max(altura // 2, 1)), Image.BOX)
    papel = meia.filter(ImageFilter.MedianFilter(11)).resize((largura, altura), Image.BILINEAR)
    suave = imagem.filter(ImageFilter.GaussianBlur(1.0))
    diferenca = np.abs(np.asarray(papel, dtype=float) - np.asarray(suave, dtype=float)) / 255
    return diferenca.max(axis=2) if diferenca.ndim == 3 else diferenca


def _limiar_fraco(residuo) -> float:
    """Acima do ruido do papel: mediana mais seis desvios, com piso de 1,5 nivel de cinza."""
    import numpy as np

    amostra = residuo[::4, ::4]
    mediana = float(np.median(amostra))
    desvio = float(np.median(np.abs(amostra - mediana))) * 1.4826
    return max(_TINTA_FRACA, mediana + 6 * desvio)


def _linear(v):
    import numpy as np

    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _medir(palavra: Palavra, lum, residuo, pt_por_px: float) -> Dict[str, Any]:
    """Contraste entre a tinta e o papel em volta, e altura em pontos."""
    x0, y0, x1, y1 = palavra.caixa
    regiao_res = residuo[y0 : y1 + 1, x0 : x1 + 1]
    regiao_lum = lum[y0 : y1 + 1, x0 : x1 + 1]
    contraste = 1.0
    if regiao_res.size and regiao_res.max() > 0.004:
        tinta = regiao_res >= regiao_res.max() * 0.5
        papel = regiao_res < regiao_res.max() * 0.15
        if tinta.any() and papel.any():
            claro = float(_linear(regiao_lum[papel]).mean())
            escuro = float(_linear(regiao_lum[tinta]).mean())
            contraste = (max(claro, escuro) + 0.05) / (min(claro, escuro) + 0.05)
    return {
        "contraste": round(contraste, 2),
        "tamanho_pt": round((y1 - y0) * pt_por_px, 1),
        "regiao_px": [x0, y0, x1, y1],
    }


def _linhas(palavras: Sequence[Palavra]) -> List[List[Palavra]]:
    grupos: Dict[Tuple[int, ...], List[Palavra]] = {}
    for p in palavras:
        grupos.setdefault(p.linha, []).append(p)
    return list(grupos.values())


def _reduzir(cinza, lado: int, metodo: str):
    """Reducao sem suavizacao, como cv2.INTER_NEAREST e cv2.INTER_LINEAR."""
    import numpy as np
    from PIL import Image

    largura, altura = cinza.size
    fator = lado / max(largura, altura)
    nl, na = max(int(round(largura * fator)), 1), max(int(round(altura * fator)), 1)
    a = np.asarray(cinza, dtype=float)
    xs = (np.arange(nl) + 0.5) / fator - 0.5
    ys = (np.arange(na) + 0.5) / fator - 0.5
    if metodo == "vizinho":  # centro do pixel (Pillow, torch "nearest-exact")
        xi = np.clip(np.floor((np.arange(nl) + 0.5) / fator).astype(int), 0, largura - 1)
        yi = np.clip(np.floor((np.arange(na) + 0.5) / fator).astype(int), 0, altura - 1)
        saida = a[np.ix_(yi, xi)]
    elif metodo == "vizinho_canto":  # canto do pixel (cv2.INTER_NEAREST, torch "nearest")
        xi = np.clip(np.floor(np.arange(nl) / fator).astype(int), 0, largura - 1)
        yi = np.clip(np.floor(np.arange(na) / fator).astype(int), 0, altura - 1)
        saida = a[np.ix_(yi, xi)]
    else:
        x0 = np.clip(np.floor(xs).astype(int), 0, largura - 1)
        y0 = np.clip(np.floor(ys).astype(int), 0, altura - 1)
        x1, y1 = np.clip(x0 + 1, 0, largura - 1), np.clip(y0 + 1, 0, altura - 1)
        fx, fy = np.clip(xs - x0, 0, 1), np.clip(ys - y0, 0, 1)
        topo = a[np.ix_(y0, x0)] * (1 - fx) + a[np.ix_(y0, x1)] * fx
        base = a[np.ix_(y1, x0)] * (1 - fx) + a[np.ix_(y1, x1)] * fx
        saida = topo * (1 - fy[:, None]) + base * fy[:, None]
    return Image.fromarray(np.clip(saida, 0, 255).astype(np.uint8))


def _compacto(texto: str) -> str:
    from polar_sentinel.reference.injection_detector import fold

    return re.sub(r"[^a-z]", "", fold(texto))


def _reducoes_suspeitas(cinza) -> List[Tuple[int, str, float, Any]]:
    """Reducoes sem suavizacao que mostram algo onde a reducao por media e lisa.

    Numa imagem comum, reduzir sem suavizar so muda as bordas (serrilhado). No
    ataque de escala, a reducao desenha um texto onde a imagem reduzida por
    media nao tem borda nenhuma. O sinal e a fracao de pixels que diferem mais
    de 48 niveis da reducao por media, longe das bordas dela. Nas imagens
    legitimas do conjunto de teste ficou abaixo de 0,00001; nos ataques, acima
    de 0,00005.
    """
    import numpy as np
    from PIL import Image, ImageFilter

    largura, altura = cinza.size
    saida = []
    for lado in TAMANHOS_DE_MODELO:
        if lado >= max(largura, altura) * 0.9:
            continue
        fator = lado / max(largura, altura)
        tamanho = (max(int(round(largura * fator)), 1), max(int(round(altura * fator)), 1))
        media = cinza.resize(tamanho, Image.BOX)
        borda = np.asarray(
            media.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5)), dtype=float
        )
        media = np.asarray(media, dtype=float)
        for metodo in METODOS_DE_REDUCAO:
            reduzida = _reduzir(cinza, lado, metodo)
            diferenca = np.abs(np.asarray(reduzida, dtype=float) - media)
            sinal = float(((diferenca > 48) & (diferenca > 3 * borda)).mean())
            if sinal > SINAL_DE_ESCALA:
                saida.append((lado, metodo, sinal, reduzida))
    return sorted(saida, key=lambda r: -r[2])


def _linhas_novas(lidas: Sequence[Palavra], conhecidas: List[str]) -> List[str]:
    """Linhas que nao correspondem a nenhuma linha lida na imagem original.

    A leitura de uma imagem reduzida erra letras e junta palavras; isso nao e
    texto novo. Uma linha so conta como nova se nenhuma linha original se
    parece com ela (semelhanca abaixo de 0,5, sem espacos) e se ela parece
    texto de verdade.
    """
    import difflib

    from polar_sentinel.reference.pdf_inspector import parece_texto

    novas = []
    for linha in _linhas(lidas):
        texto = " ".join(p.texto for p in linha)
        compacto = _compacto(texto)
        if len(compacto) < 12 or not parece_texto(texto):
            continue
        melhor = max(
            (difflib.SequenceMatcher(None, compacto, c).ratio() for c in conhecidas), default=0.0
        )
        if melhor < 0.5:
            novas.append(texto)
            conhecidas.append(compacto)
    return novas


def metadados_da_imagem(img) -> List[Achado]:
    """Texto guardado no arquivo da imagem: EXIF, XMP, comentarios, blocos do PNG."""
    achados: List[Achado] = []
    for chave, valor in (img.info or {}).items():
        if chave in ("icc_profile", "exif", "dpi", "gamma", "transparency", "duration", "loop"):
            continue
        if isinstance(valor, bytes):
            valor = valor.decode("utf-8", "replace")
        if isinstance(valor, str) and valor.strip():
            texto = " ".join(re.sub(r"<[^>]+>", " ", valor).split())
            if texto:
                achados.append(Achado("metadado", texto, None, {"origem": str(chave)}))
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        exif = {}
    for tag in (270, 315, 33432, 37510, 40091, 40092, 40093, 40094, 40095):
        valor = exif.get(tag) if exif else None
        if valor is None and exif:
            try:
                valor = exif.get_ifd(0x8769).get(tag)
            except Exception:  # noqa: BLE001
                valor = None
        if valor is None:
            continue
        if isinstance(valor, (bytes, tuple)):
            dados = bytes(valor)
            if tag >= 40091:
                texto = dados.decode("utf-16-le", "replace")
            elif dados[:8] == b"UNICODE\x00":  # UserComment em UTF-16
                corpo = dados[8:]
                ordem = "utf-16-le" if corpo[1:2] == b"\x00" else "utf-16-be"
                texto = corpo.decode(ordem, "replace")
            elif dados[:5] == b"ASCII":
                texto = dados[8:].decode("utf-8", "replace")
            else:
                texto = dados.decode("utf-8", "replace")
        else:
            texto = str(valor)
        texto = " ".join(texto.replace("\x00", " ").replace("ASCII", " ").split())
        if texto:
            achados.append(Achado("metadado", texto, None, {"origem": f"exif {tag}"}))
    return achados


def inspecionar_imagem(
    source: Union[str, Path, bytes, Any],
    *,
    pt_por_px: float = PT_POR_PX,
    pagina: Optional[int] = None,
    reducao: bool = True,
) -> ImagemInspecao:
    """Le uma imagem e separa o que a pessoa ve do que so o modelo le.

    `pt_por_px` converte pixel em ponto no tamanho de exibicao (0,75 a 96 dpi;
    para imagem dentro de PDF, a razao entre o tamanho na pagina e os pixels).
    `reducao` testa o ataque de escala; desligue para paginas de PDF.
    """
    import numpy as np
    from PIL import Image

    from polar_sentinel.reference.pdf_inspector import parece_texto
    from polar_sentinel.reference.pdf_percepcao import contraste_legivel, contraste_visivel

    img = _abrir(source)
    achados = metadados_da_imagem(img)
    sem_alfa = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        # A pessoa ve a imagem sobre o papel branco; um sistema que so descarta
        # a transparencia ve as cores escondidas nos pixels transparentes.
        rgba = img.convert("RGBA")
        sem_alfa = rgba.convert("RGB").convert("L")
        img = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    cinza = img.convert("L")
    largura, altura = cinza.size
    lum = np.asarray(cinza, dtype=float) / 255
    residuo = _residuo(img.convert("RGB"))

    fator = 2.0 if max(largura, altura) <= 2600 else 1.0
    ampliada = cinza.resize((int(largura * fator), int(altura * fator)), Image.LANCZOS)
    normais = _ocr(ampliada, fator, psm="3")

    forte = Image.fromarray(np.where(residuo > _TINTA_FORTE, 255, 0).astype(np.uint8))
    from PIL import ImageFilter

    forte = np.asarray(forte.filter(ImageFilter.MaxFilter(7))) > 0
    fraco = (residuo > _limiar_fraco(residuo)) & ~forte
    fracas: List[Palavra] = []
    if fraco.mean() > 0.0005:
        vista = Image.fromarray(np.where(fraco, 0, 255).astype(np.uint8))
        vista = vista.filter(ImageFilter.MedianFilter(3))
        if fator > 1:
            vista = vista.resize((int(largura * fator), int(altura * fator)), Image.LANCZOS)
        vista = vista.filter(ImageFilter.GaussianBlur(1.5 if fator > 1 else 0.8))
        fracas = _ocr(vista, fator, psm="11")

    visivel: List[str] = []
    trechos: List[TrechoImagem] = []
    for grupo, origem in ((_linhas(normais), "normal"), (_linhas(fracas), "amplificada")):
        for linha in grupo:
            medidas = [_medir(p, lum, residuo, pt_por_px) for p in linha]
            texto = " ".join(p.texto for p in linha)
            contraste = float(np.median([m["contraste"] for m in medidas]))
            tamanho = float(np.median([m["tamanho_pt"] for m in medidas]))
            if tamanho < 2.0:
                motivo = "fonte_minuscula"
            elif contraste < contraste_visivel(tamanho):
                motivo = "cor_do_fundo"
            elif contraste < contraste_legivel(tamanho):
                motivo = "baixo_contraste"
            else:
                motivo = ""
            if origem == "amplificada" and not motivo:
                continue  # ja lido na leitura normal
            if motivo and not parece_texto(texto):
                continue  # ruido do papel lido como letras soltas
            if motivo in ("", "baixo_contraste"):
                visivel.append(texto)
            if motivo:
                x0 = min(m["regiao_px"][0] for m in medidas)
                y0 = min(m["regiao_px"][1] for m in medidas)
                x1 = max(m["regiao_px"][2] for m in medidas)
                y1 = max(m["regiao_px"][3] for m in medidas)
                trechos.append(
                    TrechoImagem(
                        texto,
                        motivo,
                        {
                            "contraste": round(contraste, 2),
                            "tamanho_pt": round(tamanho, 1),
                            "regiao_px": [x0, y0, x1, y1],
                            "imagem_px": [largura, altura],
                            "leitura": origem,
                        },
                        pagina,
                    )
                )

    conhecidos = [
        _compacto(" ".join(p.texto for p in linha)) for linha in _linhas([*normais, *fracas])
    ]
    if sem_alfa is not None:
        lidas = _ocr(sem_alfa.resize((largura * 2, altura * 2), Image.LANCZOS), 2.0, "3")
        for texto in _linhas_novas(lidas, conhecidos):
            medidas = {"imagem_px": [largura, altura]}
            trechos.append(TrechoImagem(texto, "so_sem_transparencia", medidas, pagina))

    if reducao:
        for lado, metodo, sinal, reduzida in _reducoes_suspeitas(cinza)[:3]:
            ampliada2 = reduzida.resize((reduzida.width * 2, reduzida.height * 2), Image.LANCZOS)
            for texto in _linhas_novas(_ocr(ampliada2, 2.0, "3"), conhecidos):
                medidas = {
                    "lado_px": lado,
                    "metodo": metodo,
                    "imagem_px": [largura, altura],
                    "pixels_so_na_reducao": round(sinal, 5),
                }
                trechos.append(TrechoImagem(texto, "so_apos_reducao", medidas, pagina))

    return ImagemInspecao("\n".join(visivel), trechos, achados, paginas=1)


@dataclass
class ImagemVeredito:
    flagged: bool
    reasons: List[str]
    inspection: ImagemInspecao
    atencao: List[str] = field(default_factory=list)


# Motivos de imagem em que a pessoa nao ve o texto e o modelo le.
INVISIVEL_EM_IMAGEM = frozenset(
    {
        "cor_do_fundo",
        "so_apos_reducao",
        "so_sem_transparencia",
        "imagem_cor_do_fundo",
        "imagem_so_apos_reducao",
        "imagem_so_sem_transparencia",
    }
)
# Palavras de verdade, no total, para texto invisivel contar sem ordem reconhecida.
MIN_PALAVRAS_INVISIVEIS = 6


def _palavras_reais(texto: str) -> int:
    """Palavras de tres letras ou mais, com vogal, so de letras."""
    palavras = re.findall(r"[^\W\d_]{3,}", texto)
    return len([p for p in palavras if re.search(r"[aeiouáéíóúâêôãõ]", p, re.I)])


# Sinais que so contam quando trazem ordem. Dois transcritores discordam em
# quase metade das gravacoes publicas reais (12 de 25), entao a discordancia
# sozinha nao merece atencao.
SO_COM_ORDEM = {"transcricao_divergente"}


def avaliar_trechos(
    trechos, reasons: List[str], atencao: List[str], stage: str, onde: str = "imagem"
) -> None:
    """Regras comuns a imagem, video e audio: ordem em trecho oculto sinaliza."""
    from polar_sentinel.reference.pdf_inspector import _MIN_LETTERS, parece_texto, tem_ordem

    por_motivo: Dict[str, List[str]] = {}
    for t in trechos:
        por_motivo.setdefault(t.motivo, []).append(t.texto)
    for motivo, partes in por_motivo.items():
        texto = " ".join(partes)
        letras = sum(ch.isalpha() for ch in texto)
        if tem_ordem(texto, stage):
            reasons.append(f"ordem_oculta_em_{onde} ({motivo})")
        elif motivo in INVISIVEL_EM_IMAGEM and _palavras_reais(texto) >= MIN_PALAVRAS_INVISIVEIS:
            # Numa imagem, texto que a pessoa nao ve e o modelo le nao tem uso
            # legitimo conhecido (ao contrario do PDF, com camada de OCR e texto
            # de acessibilidade). Sinaliza mesmo quando a leitura sai truncada
            # demais para reconhecer a ordem.
            reasons.append(f"texto_invisivel_legivel_por_maquina ({motivo})")
        elif (
            letras >= _MIN_LETTERS
            and parece_texto(texto)
            and not motivo.endswith("baixo_contraste")
            and motivo not in SO_COM_ORDEM
        ):
            atencao.append(f"conteudo_oculto_em_{onde}_sem_ordem ({motivo})")


def evaluate_image(source: Union[str, Path, bytes, Any], stage: str = "entrada") -> ImagemVeredito:
    """Decide se uma imagem deve ser sinalizada."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator
    from polar_sentinel.reference.pdf_inspector import dirigido_a_ia

    inspecao = inspecionar_imagem(source)
    reasons: List[str] = []
    atencao: List[str] = []
    orquestrador = create_judicial_orchestrator(include_provenance=False)
    if inspecao.visible_text.strip():
        resultado = orquestrador.run(
            inspecao.visible_text, context={"stage": stage, "source": "imagem"}
        )
        if resultado.blocked or resultado.score > orquestrador.risk_threshold:
            reasons.append("comando_no_texto_visivel")
    avaliar_trechos(inspecao.hidden_spans, reasons, atencao, stage)
    for achado in inspecao.achados:
        if achado.tipo == "metadado" and dirigido_a_ia(achado.texto, stage):
            reasons.append("comando_em_metadado")
    return ImagemVeredito(
        bool(reasons), list(dict.fromkeys(reasons)), inspecao, list(dict.fromkeys(atencao))
    )
