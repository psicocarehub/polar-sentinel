"""Polar Sentinel: o que a transcricao entrega a IA e a pessoa nao ouve.

Audiencias, depoimentos e audios de WhatsApp chegam aos modelos como
transcricao. Uma ordem pode estar na fala que ninguem percebe ao ouvir: baixa
demais, acelerada demais, escondida sob musica ou ruido. Este modulo compara a
transcricao do audio como a pessoa o ouve com transcricoes de versoes
preparadas para revelar o que esta escondido:

    fala_em_volume_baixo   palavras que so aparecem com o volume normalizado
                           (compressor dinamico); medida: quanto abaixo da
                           fala principal, em dB
    fala_acelerada         palavras que so aparecem com o audio desacelerado
    fala_sob_ruido         palavras que so aparecem com a faixa de voz isolada
                           (passa-faixa de 300 a 3.400 Hz)
    fala_em_um_canal       palavras que so aparecem ouvindo um canal do estereo
    transcricao_divergente trecho em que dois transcritores de familias
                           diferentes (Whisper e Vosk) discordam muito: sinal
                           de perturbacao feita contra um modelo
    voz_sem_transcricao    trecho com voz e sem palavra transcrita (supressao)
    energia_ultrassonica   energia acima de 18 kHz no arquivo original; o
                           transcritor descarta, mas e anomalia em gravacao

O texto "audivel" e a transcricao do audio original pelo Whisper. Os limiares
sao escolhas de engenharia e a medida de audibilidade nao foi calibrada com
pessoas. Precisa do ffmpeg e de faster-whisper; o Vosk, com o modelo pequeno
em portugues, e opcional.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from polar_sentinel.reference.imagem_inspector import TrechoImagem
from polar_sentinel.reference.pdf_estrutura import Achado

TAXA = 16000
MODELO_WHISPER = os.environ.get("POLAR_SENTINEL_WHISPER", "base")
PASTA_MODELOS = Path(
    os.environ.get("POLAR_SENTINEL_MODELOS", Path.home() / ".cache" / "polar_sentinel")
)
MODELO_VOSK = PASTA_MODELOS / "vosk-model-small-pt-0.3"
# Fala mais de tantos dB abaixo da fala principal nao conta como ouvida.
ABAIXO_DA_FALA_DB = 20.0
# Fala revelada por uma versao preparada so conta se estiver ao menos tantos dB
# abaixo da fala principal; acima disso e a mesma fala transcrita de outro jeito.
MIN_ABAIXO_PREPARADA_DB = 10.0
# Fala transcrita, tantos dB abaixo da principal e com palavras bastantes,
# sinaliza mesmo sem ordem reconhecida: a pessoa nao ouve e o modelo le.
INAUDIVEL_DB = 25.0
# Palavras novas numa versao preparada, para contar como fala escondida.
_MIN_PALAVRAS_NOVAS = 3
_cache: Dict[str, Any] = {}


def disponivel() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return shutil.which("ffmpeg") is not None


SEM_VOSK = (
    "segundo transcritor (Vosk) ausente: a comparação entre transcritores não foi feita; "
    "instale com `python -m polar_sentinel.modelos`"
)
_avisados: set = set()


def _avisar_uma_vez(texto: str) -> None:
    if texto not in _avisados:
        _avisados.add(texto)
        logging.getLogger("polar_sentinel").warning(texto)


def _vosk_disponivel() -> bool:
    try:
        import vosk  # noqa: F401
    except ImportError:
        return False
    return MODELO_VOSK.exists()


@dataclass
class Palavra:
    texto: str
    inicio: float
    fim: float


@dataclass
class AudioInspecao:
    visible_text: str
    hidden_spans: List[TrechoImagem] = field(default_factory=list)
    achados: List[Achado] = field(default_factory=list)
    motor: str = "audio"
    paginas: Optional[int] = None
    duracao_s: float = 0.0
    # O que nao pode ser feito nesta maquina e por isso ficou de fora da leitura.
    limites: List[str] = field(default_factory=list)


def _ffmpeg_para_wav(
    origem: str, destino: str, filtros: str = "", faixa: Optional[int] = None, taxa: int = TAXA
) -> None:
    args = ["ffmpeg", "-v", "error", "-y", "-i", origem]
    args += ["-map", f"0:{faixa}"] if faixa is not None else ["-map", "0:a:0"]
    if filtros:
        args += ["-af", filtros]
    args += ["-ac", "1", "-ar", str(taxa), "-c:a", "pcm_s16le", destino]
    subprocess.run(args, capture_output=True, timeout=1800, check=True)


def _ler_wav(caminho: str):
    import numpy as np
    from scipy.io import wavfile

    taxa, dados = wavfile.read(caminho)
    return taxa, dados.astype(np.float32) / 32768.0


def _whisper():
    if "whisper" not in _cache:
        from faster_whisper import WhisperModel

        _cache["whisper"] = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    return _cache["whisper"]


def transcrever_whisper(wav: str, fator_tempo: float = 1.0) -> List[Palavra]:
    """Transcricao com tempos por palavra; `fator_tempo` corrige audio desacelerado."""
    import numpy as np

    taxa, sinal = _ler_wav(wav)
    if sinal.ndim > 1:
        sinal = sinal.mean(axis=1)
    if taxa != TAXA:
        raise ValueError(f"esperava audio a {TAXA} Hz, veio {taxa}")
    # Passa o sinal ja decodificado: o PyAV 19 quebrou a decodificacao propria
    # do faster-whisper 1.2 (argumento metadata_errors).
    segmentos, _ = _whisper().transcribe(
        np.ascontiguousarray(sinal, dtype=np.float32),
        language="pt",
        word_timestamps=True,
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    palavras = []
    for s in segmentos:
        for w in s.words or []:
            palavras.append(Palavra(w.word.strip(), w.start * fator_tempo, w.end * fator_tempo))
    return [p for p in palavras if p.texto]


def transcrever_vosk(wav: str) -> List[Palavra]:
    import json
    import wave

    from vosk import KaldiRecognizer, Model, SetLogLevel

    SetLogLevel(-1)
    if "vosk" not in _cache:
        _cache["vosk"] = Model(str(MODELO_VOSK))
    with wave.open(wav, "rb") as w:
        rec = KaldiRecognizer(_cache["vosk"], w.getframerate())
        rec.SetWords(True)
        resultados = []
        while True:
            bloco = w.readframes(4000)
            if not bloco:
                break
            if rec.AcceptWaveform(bloco):
                resultados.append(json.loads(rec.Result()))
        resultados.append(json.loads(rec.FinalResult()))
    return [
        Palavra(p["word"], p["start"], p["end"]) for r in resultados for p in r.get("result", [])
    ]


def _dobrar(texto: str) -> str:
    from polar_sentinel.reference.injection_detector import fold

    return re.sub(r"[^a-z0-9]", "", fold(texto))


def _novas(base: List[Palavra], outra: List[Palavra], folga: float = 1.0) -> List[List[Palavra]]:
    """Grupos de palavras de `outra` sem palavra igual em `base` no mesmo instante."""
    grupos: List[List[Palavra]] = []
    atual: List[Palavra] = []
    for p in outra:
        chave = _dobrar(p.texto)
        if len(chave) < 2:
            continue
        existe = any(
            _dobrar(b.texto) == chave and abs(b.inicio - p.inicio) <= folga + 1.5 for b in base
        )
        if existe:
            if len(atual) >= _MIN_PALAVRAS_NOVAS:
                grupos.append(atual)
            atual = []
        else:
            if atual and p.inicio - atual[-1].fim > 2.0:
                if len(atual) >= _MIN_PALAVRAS_NOVAS:
                    grupos.append(atual)
                atual = []
            atual.append(p)
    if len(atual) >= _MIN_PALAVRAS_NOVAS:
        grupos.append(atual)
    return grupos


def _consecutivas(escolhidas: List[Palavra], todas: List[Palavra]) -> List[List[Palavra]]:
    """Grupos de palavras escolhidas que vem uma depois da outra na transcricao."""
    marcadas = {id(p) for p in escolhidas}
    grupos, atual = [], []
    for p in todas:
        if id(p) in marcadas:
            atual.append(p)
        else:
            if len(atual) >= _MIN_PALAVRAS_NOVAS:
                grupos.append(atual)
            atual = []
    if len(atual) >= _MIN_PALAVRAS_NOVAS:
        grupos.append(atual)
    return grupos


def _nivel_db(sinal, taxa: int, inicio: float, fim: float) -> float:
    import numpy as np

    trecho = sinal[int(inicio * taxa) : max(int(fim * taxa), int(inicio * taxa) + 1)]
    rms = float(np.sqrt(np.mean(trecho**2))) if trecho.size else 0.0
    return 20 * np.log10(rms + 1e-9)


def _fala_principal_db(sinal, taxa: int, palavras: List[Palavra]) -> float:
    import numpy as np

    niveis = [_nivel_db(sinal, taxa, p.inicio, p.fim) for p in palavras if p.fim > p.inicio]
    return float(np.median(niveis)) if niveis else -20.0


def _voz_sem_transcricao(sinal, taxa: int, palavras: List[Palavra]) -> List[Tuple[float, float]]:
    """Trechos de 3 s ou mais com energia de voz e nenhuma palavra transcrita."""
    import numpy as np

    janela = int(0.5 * taxa)
    if sinal.size < janela:
        return []
    blocos = sinal[: sinal.size // janela * janela].reshape(-1, janela)
    rms = np.sqrt((blocos**2).mean(axis=1))
    piso = np.percentile(rms, 20)
    ativo = rms > max(piso * 4, 0.01)
    trechos, inicio = [], None
    for i, a in enumerate(list(ativo) + [False]):
        t = i * 0.5
        coberto = any(p.inicio - 0.5 <= t <= p.fim + 0.5 for p in palavras)
        if a and not coberto:
            inicio = t if inicio is None else inicio
        else:
            if inicio is not None and t - inicio >= 3.0:
                trechos.append((inicio, t))
            inicio = None
    return trechos


def _energia_ultrassonica(origem: str, faixa: Optional[int]) -> Optional[float]:
    """Fracao da energia acima de 18 kHz, quando o arquivo tem taxa para isso."""
    import numpy as np

    with tempfile.TemporaryDirectory() as tmp:
        destino = str(Path(tmp) / "nativo.wav")
        try:
            _ffmpeg_para_wav(origem, destino, faixa=faixa, taxa=48000)
        except subprocess.CalledProcessError:
            return None
        taxa, sinal = _ler_wav(destino)
    if sinal.size < taxa:
        return None
    espectro = np.abs(np.fft.rfft(sinal[: taxa * 60])) ** 2
    freqs = np.fft.rfftfreq(min(sinal.size, taxa * 60), 1 / taxa)
    total = espectro.sum() + 1e-12
    return float(espectro[freqs > 18000].sum() / total)


def _canais(origem: str, faixa: Optional[int]) -> int:
    seletor = f"{faixa}" if faixa is not None else "a:0"
    saida = (
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                seletor,
                "-show_entries",
                "stream=channels",
                "-of",
                "csv=p=0",
                origem,
            ],
            capture_output=True,
            timeout=60,
        )
        .stdout.decode()
        .strip()
        .splitlines()
    )
    try:
        return int(saida[0])
    except (IndexError, ValueError):
        return 1


def inspecionar_audio(
    source: Union[str, Path], *, faixa: Optional[int] = None, cruzar: Optional[bool] = None
) -> AudioInspecao:
    """Le o audio (arquivo de audio ou faixa de um video) e procura fala escondida."""
    origem = str(source)
    trechos: List[TrechoImagem] = []
    achados: List[Achado] = []
    limites: List[str] = []
    if cruzar is None:
        cruzar = _vosk_disponivel()
        if not cruzar:
            limites.append(SEM_VOSK)
            _avisar_uma_vez(SEM_VOSK)
    with tempfile.TemporaryDirectory() as tmp:
        pasta = Path(tmp)
        base = str(pasta / "base.wav")
        _ffmpeg_para_wav(origem, base, faixa=faixa)
        taxa, sinal = _ler_wav(base)
        duracao = sinal.size / taxa
        transcritas = transcrever_whisper(base)
        principal = _fala_principal_db(sinal, taxa, transcritas)
        conhecidas = list(transcritas)
        # Fala que o transcritor pega mas que fica muito abaixo da fala principal
        # (sussurro numa pausa) nao e o que a pessoa ouve.
        ouvidas, baixas = [], []
        for p in transcritas:
            abaixo = principal - _nivel_db(sinal, taxa, p.inicio, p.fim)
            (baixas if abaixo >= ABAIXO_DA_FALA_DB else ouvidas).append((p, abaixo))
        for grupo in _consecutivas([p for p, _ in baixas], transcritas):
            inicio, fim = grupo[0].inicio, grupo[-1].fim
            trechos.append(
                TrechoImagem(
                    " ".join(p.texto for p in grupo),
                    "fala_em_volume_baixo",
                    {
                        "inicio_s": round(float(inicio), 2),
                        "fim_s": round(float(fim), 2),
                        "abaixo_da_fala_db": round(
                            float(principal - _nivel_db(sinal, taxa, inicio, fim)), 1
                        ),
                    },
                )
            )
        ouvidas = [p for p, _ in ouvidas]

        preparadas = {
            "fala_em_volume_baixo": ("dynaudnorm=f=150:g=15:p=0.95:m=100,volume=1.5", 1.0),
            "fala_sob_ruido": ("highpass=f=300,lowpass=f=3400,dynaudnorm=f=150:g=15", 1.0),
            "fala_acelerada": ("atempo=0.5", 0.5),
        }
        for motivo, (filtros, fator) in preparadas.items():
            if motivo == "fala_acelerada" and duracao > 1200:
                continue  # desacelerar audiencias longas dobra o custo
            destino = str(pasta / f"{motivo}.wav")
            _ffmpeg_para_wav(origem, destino, filtros, faixa=faixa)
            for grupo in _novas(conhecidas, transcrever_whisper(destino, fator_tempo=fator)):
                inicio, fim = grupo[0].inicio, grupo[-1].fim
                nivel = _nivel_db(sinal, taxa, inicio, fim)
                conhecidas.extend(grupo)
                if principal - nivel < MIN_ABAIXO_PREPARADA_DB:
                    continue  # mesma fala, transcrita de outro jeito: nao e fala escondida
                trechos.append(
                    TrechoImagem(
                        " ".join(p.texto for p in grupo),
                        motivo,
                        {
                            "inicio_s": round(float(inicio), 2),
                            "fim_s": round(float(fim), 2),
                            "abaixo_da_fala_db": round(float(principal - nivel), 1),
                        },
                    )
                )

        for canal in (0, 1) if _canais(origem, faixa) == 2 else ():
            destino = str(pasta / f"canal{canal}.wav")
            _ffmpeg_para_wav(
                origem, destino, f"pan=mono|c0=c{canal},dynaudnorm=f=150:g=15", faixa=faixa
            )
            for grupo in _novas(conhecidas, transcrever_whisper(destino)):
                inicio, fim = grupo[0].inicio, grupo[-1].fim
                abaixo = principal - _nivel_db(sinal, taxa, inicio, fim)
                conhecidas.extend(grupo)
                if abaixo < MIN_ABAIXO_PREPARADA_DB:
                    continue
                trechos.append(
                    TrechoImagem(
                        " ".join(p.texto for p in grupo),
                        "fala_em_um_canal",
                        {
                            "inicio_s": round(float(inicio), 2),
                            "fim_s": round(float(fim), 2),
                            "abaixo_da_fala_db": round(float(abaixo), 1),
                            "canal": "esquerdo" if canal == 0 else "direito",
                        },
                    )
                )

        if cruzar:
            for grupo in _novas(transcrever_vosk(base), ouvidas):
                inicio, fim = grupo[0].inicio, grupo[-1].fim
                if len(grupo) >= 6 and not any(
                    t.medidas["inicio_s"] - 1 <= inicio <= t.medidas["fim_s"] + 1 for t in trechos
                ):
                    trechos.append(
                        TrechoImagem(
                            " ".join(p.texto for p in grupo),
                            "transcricao_divergente",
                            {"inicio_s": round(float(inicio), 2), "fim_s": round(float(fim), 2)},
                        )
                    )

        for inicio, fim in _voz_sem_transcricao(sinal, taxa, ouvidas):
            achados.append(
                Achado("voz_sem_transcricao", "", None, {"inicio_s": inicio, "fim_s": fim})
            )

    if faixa is None:
        from polar_sentinel.reference.video_inspector import _texto_de_etiquetas, sondar

        info = sondar(origem)
        texto = _texto_de_etiquetas(info.get("format", {}).get("tags", {}))
        if texto:
            achados.append(Achado("metadado", texto, None, {"origem": "conteiner"}))
        for capitulo in info.get("chapters", []):
            texto = _texto_de_etiquetas(capitulo.get("tags", {}))
            if texto:
                achados.append(Achado("metadado", texto, None, {"origem": "capitulo"}))

    ultra = _energia_ultrassonica(origem, faixa)
    if ultra is not None and ultra > 0.01:
        achados.append(Achado("energia_ultrassonica", "", None, {"fracao": round(ultra, 4)}))
    visivel = " ".join(p.texto for p in ouvidas)
    return AudioInspecao(visivel, trechos, achados, duracao_s=round(duracao, 1), limites=limites)


@dataclass
class AudioVeredito:
    flagged: bool
    reasons: List[str]
    inspection: AudioInspecao
    atencao: List[str] = field(default_factory=list)


def evaluate_audio(source: Union[str, Path], stage: str = "entrada") -> AudioVeredito:
    """Decide se um audio deve ser sinalizado."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator
    from polar_sentinel.reference.imagem_inspector import (
        MIN_PALAVRAS_INVISIVEIS,
        _palavras_reais,
        avaliar_trechos,
    )
    from polar_sentinel.reference.pdf_inspector import dirigido_a_ia

    inspecao = inspecionar_audio(source)
    reasons: List[str] = []
    atencao: List[str] = []
    if inspecao.visible_text.strip():
        orquestrador = create_judicial_orchestrator(include_provenance=False)
        resultado = orquestrador.run(
            inspecao.visible_text, context={"stage": stage, "source": "audio"}
        )
        if resultado.blocked or resultado.score > orquestrador.risk_threshold:
            reasons.append("comando_na_fala_audivel")
    avaliar_trechos(inspecao.hidden_spans, reasons, atencao, stage, onde="audio")
    inaudivel = " ".join(
        t.texto
        for t in inspecao.hidden_spans
        if t.motivo.startswith("fala_") and t.medidas.get("abaixo_da_fala_db", 0) >= INAUDIVEL_DB
    )
    if _palavras_reais(inaudivel) >= MIN_PALAVRAS_INVISIVEIS:
        reasons.append("fala_inaudivel_transcrita")
    for achado in inspecao.achados:
        if achado.tipo == "metadado":
            if dirigido_a_ia(achado.texto, stage):
                reasons.append("comando_em_metadado")
        else:
            atencao.append(achado.tipo)
    return AudioVeredito(
        bool(reasons), list(dict.fromkeys(reasons)), inspecao, list(dict.fromkeys(atencao))
    )
