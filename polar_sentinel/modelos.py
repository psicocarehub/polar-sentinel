"""Polar Sentinel: baixa os modelos de fala usados na leitura de audio e video.

    python -m polar_sentinel.modelos

O faster-whisper baixa o proprio modelo na primeira transcricao; este comando
o adianta. O Vosk (segundo transcritor, de outra familia) precisa do modelo
pequeno de portugues, que vai para ~/.cache/polar_sentinel (ou para a pasta em
POLAR_SENTINEL_MODELOS). Sem ele a leitura funciona, mas sem a comparacao
entre transcritores, e a certidao registra isso.
"""

from __future__ import annotations

import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

URL_VOSK = "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip"


def baixar_vosk(destino: Optional[Path] = None) -> Path:
    from polar_sentinel.reference.audio_inspector import MODELO_VOSK

    pasta = (destino or MODELO_VOSK.parent).expanduser()
    alvo = pasta / MODELO_VOSK.name
    if alvo.exists():
        return alvo
    pasta.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        arquivo = Path(tmp) / "vosk.zip"
        urllib.request.urlretrieve(URL_VOSK, arquivo)
        with zipfile.ZipFile(arquivo) as z:
            for nome in z.namelist():
                caminho = (pasta / nome).resolve()
                if not str(caminho).startswith(str(pasta.resolve())):
                    raise RuntimeError(f"caminho fora da pasta no zip: {nome}")
            z.extractall(pasta)
    return alvo


def baixar_whisper() -> str:
    from faster_whisper import WhisperModel

    from polar_sentinel.reference.audio_inspector import MODELO_WHISPER

    WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    return MODELO_WHISPER


def main(argv: Optional[List[str]] = None) -> int:
    del argv
    try:
        print(f"Whisper ({baixar_whisper()}): pronto.")
    except ImportError:
        print('faster-whisper nao instalado: pip install "polar-sentinel[midia]"')
        return 1
    print(f"Vosk: pronto em {baixar_vosk()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
