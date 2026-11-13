"""Polar Sentinel: o que um modelo le num video e a pessoa nao ve.

Audiencias gravadas e videos de prova chegam aos sistemas de IA como quadros
amostrados, legendas e transcricao. Este modulo procura:

    conteiner        metadados (titulo, comentario, descricao), capitulos,
                     faixas de legenda (lidas inteiras), anexos e faixas extras
    legenda          texto de legenda com ordem dirigida a IA, e legenda que
                     fica na tela por menos tempo do que se consegue ler
    quadro relampago trecho entre dois cortes mais curto que 0,25 segundo: um
                     modelo que amostra aquele quadro le o texto, a pessoa ve
                     um piscar. O quadro e lido com o inspetor de imagem
    texto apagado    quadros amostrados (um por segundo, sem repetir quadro
                     parecido) lidos com o inspetor de imagem: letra quase da
                     cor do fundo, letra pequena demais
    audio            cada faixa de audio vai para o inspetor de audio
                     (reference/audio_inspector.py), quando instalado

Os tempos vao nas medidas de cada trecho, para a certidao apontar o instante.
Precisa do ffmpeg e do ffprobe; a leitura de quadros precisa tambem do
Tesseract (veja reference/imagem_inspector.py).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from polar_sentinel.reference.imagem_inspector import TrechoImagem
from polar_sentinel.reference.pdf_estrutura import Achado

# Trecho entre cortes mais curto que isto e um quadro relampago.
RELAMPAGO_S = 0.25
# Legenda na tela por menos que isto nao da para ler.
LEGENDA_MINIMA_S = 0.3
# Sensibilidade do detector de cortes do ffmpeg (0 a 1).
_CORTE = 0.02
# Relampagos lidos no maximo (video com muito movimento gera muitos cortes).
MAX_RELAMPAGOS = 60
# Quadros lidos no maximo, alem dos relampagos.
MAX_QUADROS = 90
_ETIQUETAS_TECNICAS = {
    "major_brand",
    "minor_version",
    "compatible_brands",
    "encoder",
    "handler_name",
    "vendor_id",
    "language",
    "creation_time",
    "duration",
    "timecode",
    "rotate",
}


def disponivel() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _rodar(args: List[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout)


@dataclass
class VideoInspecao:
    visible_text: str
    hidden_spans: List[TrechoImagem] = field(default_factory=list)
    achados: List[Achado] = field(default_factory=list)
    motor: str = "video"
    paginas: Optional[int] = None
    duracao_s: float = 0.0
    audio: List[Any] = field(default_factory=list)
    limites: List[str] = field(default_factory=list)


def sondar(caminho: str) -> Dict[str, Any]:
    saida = _rodar(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-of",
            "json",
            caminho,
        ]
    ).stdout
    return json.loads(saida or b"{}")


def _texto_de_etiquetas(etiquetas: Dict[str, str]) -> str:
    return " ".join(
        str(v)
        for k, v in (etiquetas or {}).items()
        if k.lower() not in _ETIQUETAS_TECNICAS and str(v).strip()
    )


_SRT_TEMPO = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def _segundos(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / (10 ** len(ms))


def ler_legenda(caminho: str, indice: int) -> List[Dict[str, Any]]:
    """Le uma faixa de legenda como SRT: lista de {inicio, fim, texto}."""
    srt = _rodar(["ffmpeg", "-v", "error", "-i", caminho, "-map", f"0:{indice}", "-f", "srt", "-"])
    blocos = []
    for bloco in srt.stdout.decode("utf-8", "replace").split("\n\n"):
        m = _SRT_TEMPO.search(bloco)
        if not m:
            continue
        texto = " ".join(
            re.sub(r"<[^>]+>", "", linha).strip() for linha in bloco[m.end() :].splitlines()
        ).strip()
        if texto:
            blocos.append(
                {
                    "inicio": _segundos(*m.groups()[:4]),
                    "fim": _segundos(*m.groups()[4:]),
                    "texto": texto,
                }
            )
    return blocos


def cortes(caminho: str) -> List[float]:
    """Instantes de corte (mudanca brusca de quadro), pelo filtro de cena do ffmpeg."""
    saida = _rodar(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            caminho,
            "-map",
            "0:v:0",
            "-vf",
            f"select='gt(scene,{_CORTE})',showinfo",
            "-fps_mode",
            "vfr",
            "-f",
            "null",
            "-",
        ]
    ).stderr.decode("utf-8", "replace")
    return [float(t) for t in re.findall(r"pts_time:([0-9.]+)", saida)]


def quadro(caminho: str, instante: float):
    """Um quadro, como imagem do Pillow."""
    import io

    from PIL import Image

    png = _rodar(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{instante:.3f}",
            "-i",
            caminho,
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGB") if png else None


def _texto_so_no_corte(caminho: str, corte: float, duracao: float) -> str:
    """Texto lido no quadro do corte que nao esta 0,3 s antes nem 0,3 s depois.

    E o relampago: aparece num ou dois quadros e some. O detector de cortes nem
    sempre marca a volta, por isso a comparacao e com os vizinhos no tempo.
    """
    import difflib

    from polar_sentinel.reference.imagem_inspector import _compacto, inspecionar_imagem

    def ler(instante: float) -> List[str]:
        if not 0 <= instante <= duracao:
            return []
        imagem = quadro(caminho, instante)
        if imagem is None:
            return []
        lida = inspecionar_imagem(imagem, reducao=False)
        linhas = [*lida.visible_text.splitlines(), *(t.texto for t in lida.hidden_spans)]
        return [linha for linha in linhas if len(_compacto(linha)) >= 6]

    # O instante do corte cai na fronteira entre dois quadros; a busca do ffmpeg
    # pode parar num ou noutro, entao os dois lados sao lidos.
    no_corte = ler(max(corte - 0.005, 0)) + ler(corte + 0.001)
    if not no_corte:
        return ""
    vizinhas = [_compacto(linha) for linha in ler(corte - 0.3) + ler(corte + 0.3)]
    novas = [
        linha
        for linha in no_corte
        if max(
            (difflib.SequenceMatcher(None, _compacto(linha), v).ratio() for v in vizinhas),
            default=0.0,
        )
        < 0.6
    ]
    return " ".join(novas)


def _quadros_amostrados(caminho: str, duracao: float, pasta: Path) -> List[float]:
    passo = max(1.0, duracao / MAX_QUADROS)
    _rodar(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            caminho,
            "-map",
            "0:v:0",
            "-vf",
            f"fps=1/{passo:.3f}",
            "-q:v",
            "2",
            str(pasta / "q%05d.png"),
        ]
    )
    return [i * passo for i in range(len(list(pasta.glob("q*.png"))))]


def inspecionar_video(
    source: Union[str, Path],
    *,
    ler_quadros: Optional[bool] = None,
    ler_audio: Optional[bool] = None,
) -> VideoInspecao:
    """Le um video e separa o que a pessoa ve e ouve do que so o modelo recebe."""
    import numpy as np
    from PIL import Image

    from polar_sentinel.reference.imagem_inspector import disponivel as ocr_disponivel
    from polar_sentinel.reference.imagem_inspector import inspecionar_imagem

    caminho = str(source)
    limites: List[str] = []
    if ler_quadros is None:
        ler_quadros = ocr_disponivel()
        if not ler_quadros:
            limites.append("quadros não lidos: instale o Tesseract com o idioma por")
    info = sondar(caminho)
    formato = info.get("format", {})
    duracao = float(formato.get("duration") or 0)
    achados: List[Achado] = []
    trechos: List[TrechoImagem] = []
    visivel: List[str] = []

    texto = _texto_de_etiquetas(formato.get("tags", {}))
    if texto:
        achados.append(Achado("metadado", texto, None, {"origem": "conteiner"}))
    for capitulo in info.get("chapters", []):
        texto = _texto_de_etiquetas(capitulo.get("tags", {}))
        if texto:
            achados.append(
                Achado(
                    "metadado",
                    texto,
                    None,
                    {"origem": "capitulo", "inicio_s": float(capitulo.get("start_time", 0))},
                )
            )

    faixas_de_audio = []
    for faixa in info.get("streams", []):
        tipo, indice = faixa.get("codec_type"), faixa.get("index")
        texto = _texto_de_etiquetas(faixa.get("tags", {}))
        if texto:
            achados.append(Achado("metadado", texto, None, {"origem": f"faixa {indice} ({tipo})"}))
        disposicao = faixa.get("disposition", {})
        if tipo == "subtitle":
            blocos = ler_legenda(caminho, indice)
            achados.append(
                Achado(
                    "legenda",
                    " ".join(b["texto"] for b in blocos),
                    None,
                    {
                        "faixa": indice,
                        "padrao": bool(disposicao.get("default")),
                        "forcada": bool(disposicao.get("forced")),
                        "blocos": len(blocos),
                    },
                )
            )
            for b in blocos:
                if b["fim"] - b["inicio"] < LEGENDA_MINIMA_S:
                    trechos.append(
                        TrechoImagem(
                            b["texto"],
                            "legenda_relampago",
                            {
                                "inicio_s": round(b["inicio"], 3),
                                "duracao_ms": round((b["fim"] - b["inicio"]) * 1000),
                                "faixa": indice,
                            },
                        )
                    )
        elif tipo == "attachment":
            nome = (faixa.get("tags") or {}).get("filename", "")
            achados.append(Achado("arquivo_embutido", "", None, {"nome": nome, "faixa": indice}))
        elif tipo == "data":
            achados.append(Achado("faixa_de_dados", "", None, {"faixa": indice}))
        elif tipo == "audio":
            faixas_de_audio.append(indice)
    if len(faixas_de_audio) > 1:
        achados.append(Achado("faixa_de_audio_extra", "", None, {"faixas": faixas_de_audio}))

    tem_video = any(
        f.get("codec_type") == "video" and not (f.get("disposition") or {}).get("attached_pic")
        for f in info.get("streams", [])
    )
    if ler_quadros and tem_video:
        instantes = cortes(caminho)
        for corte in instantes[:MAX_RELAMPAGOS]:
            texto = _texto_so_no_corte(caminho, corte, duracao)
            if texto:
                seguinte = next((t for t in instantes if t > corte), duracao)
                trechos.append(
                    TrechoImagem(
                        texto,
                        "quadro_relampago",
                        {
                            "inicio_s": round(corte, 3),
                            "duracao_ms": round(min(seguinte - corte, RELAMPAGO_S) * 1000),
                        },
                    )
                )
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            anterior = None
            for i, instante in enumerate(_quadros_amostrados(caminho, duracao, pasta)):
                arquivo = pasta / f"q{i + 1:05d}.png"
                if not arquivo.exists():
                    continue
                imagem = Image.open(arquivo).convert("RGB")
                miniatura = np.asarray(imagem.convert("L").resize((64, 36)), dtype=float)
                if anterior is not None and np.abs(miniatura - anterior).mean() < 2.0:
                    continue  # quadro igual ao ultimo lido
                anterior = miniatura
                lida = inspecionar_imagem(imagem, reducao=False)
                if lida.visible_text.strip():
                    visivel.append(lida.visible_text)
                for t in lida.hidden_spans:
                    trechos.append(
                        TrechoImagem(
                            t.texto, t.motivo, {**t.medidas, "inicio_s": round(instante, 1)}
                        )
                    )

    audios = []
    if faixas_de_audio:
        from polar_sentinel.reference import audio_inspector

        if ler_audio is None:
            ler_audio = audio_inspector.disponivel()
            if not ler_audio:
                limites.append(
                    "áudio não transcrito: instale `polar-sentinel[midia]` (faster-whisper)"
                )
        if ler_audio:
            for indice in faixas_de_audio:
                audios.append(audio_inspector.inspecionar_audio(caminho, faixa=indice))
    for a in audios:
        if a.visible_text.strip():
            visivel.append(a.visible_text)
        trechos.extend(a.hidden_spans)
        achados.extend(a.achados)
        limites.extend(x for x in a.limites if x not in limites)

    # Cada fonte (legenda, quadro, faixa de audio) e uma fala ou texto a parte;
    # transcricao nao tem pontuacao, entao a fronteira ganha ponto final, para o
    # detector nao tomar a faixa seguinte como continuacao da frase.
    texto = "\n".join(v.rstrip() + ("" if v.rstrip()[-1:] in ".!?:;" else ".") for v in visivel)
    return VideoInspecao(texto, trechos, achados, duracao_s=duracao, audio=audios, limites=limites)


@dataclass
class VideoVeredito:
    flagged: bool
    reasons: List[str]
    inspection: VideoInspecao
    atencao: List[str] = field(default_factory=list)


def evaluate_video(source: Union[str, Path], stage: str = "entrada") -> VideoVeredito:
    """Decide se um video deve ser sinalizado."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator
    from polar_sentinel.reference.imagem_inspector import avaliar_trechos
    from polar_sentinel.reference.pdf_inspector import dirigido_a_ia, tem_ordem

    inspecao = inspecionar_video(source)
    reasons: List[str] = []
    atencao: List[str] = []
    if inspecao.visible_text.strip():
        orquestrador = create_judicial_orchestrator(include_provenance=False)
        resultado = orquestrador.run(
            inspecao.visible_text, context={"stage": stage, "source": "video"}
        )
        if resultado.blocked or resultado.score > orquestrador.risk_threshold:
            reasons.append("comando_no_conteudo_visivel_ou_audivel")
    avaliar_trechos(inspecao.hidden_spans, reasons, atencao, stage, onde="video")
    from polar_sentinel.reference.audio_inspector import INAUDIVEL_DB
    from polar_sentinel.reference.imagem_inspector import MIN_PALAVRAS_INVISIVEIS, _palavras_reais

    inaudivel = " ".join(
        t.texto
        for t in inspecao.hidden_spans
        if t.motivo.startswith("fala_") and t.medidas.get("abaixo_da_fala_db", 0) >= INAUDIVEL_DB
    )
    if _palavras_reais(inaudivel) >= MIN_PALAVRAS_INVISIVEIS:
        reasons.append("fala_inaudivel_transcrita")
    for achado in inspecao.achados:
        if achado.tipo == "metadado" and dirigido_a_ia(achado.texto, stage):
            reasons.append("comando_em_metadado")
        elif achado.tipo == "legenda" and achado.texto and tem_ordem(achado.texto, stage):
            reasons.append("ordem_em_legenda")
        elif achado.tipo in ("arquivo_embutido", "faixa_de_dados", "faixa_de_audio_extra"):
            atencao.append(achado.tipo)
    return VideoVeredito(
        bool(reasons), list(dict.fromkeys(reasons)), inspecao, list(dict.fromkeys(atencao))
    )
