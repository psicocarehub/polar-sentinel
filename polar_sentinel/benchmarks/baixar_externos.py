"""Polar Sentinel: baixa os conjuntos publicos usados na medida externa.

Os dados nao sao redistribuidos neste repositorio: cada um tem a sua licenca e
fica no Hugging Face. Este script baixa os arquivos parquet para uma pasta
local, e benchmarks/external_eval.py le dali.

Uso:
    python -m polar_sentinel.benchmarks.baixar_externos <pasta>

So usa a biblioteca padrao. A leitura dos parquet, em external_eval.py, pede
pyarrow (pip install pyarrow).
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# (dataset, config, split, quantos arquivos parquet baixar)
FONTES = [
    # ataques escritos por pessoas ou coletados em uso real
    ("microsoft/llmail-inject-challenge", "default", "Phase1", 1),
    ("TrustAIRLab/in-the-wild-jailbreak-prompts", "jailbreak_2023_12_25", "train", 1),
    ("deepset/prompt-injections", "default", "train", 1),
    ("deepset/prompt-injections", "default", "test", 1),
    ("Weni/prompt-injections-1.0.0", "default", "train", 1),
    ("yanismiraoui/prompt_injections", "default", "train", 1),
    # benignos com palavras que parecem ataque
    ("leolee99/NotInject", "default", "NotInject_one", 1),
    ("leolee99/NotInject", "default", "NotInject_two", 1),
    ("leolee99/NotInject", "default", "NotInject_three", 1),
    # textos juridicos brasileiros reais
    ("walmeidadf/STJ-SumBR", "full", "test", 1),
    ("zeraulalmeida/Jurisprudencia_TRT_13", "default", "train", 1),
    ("celsowm/jurisprudencias_tjsp", "default", "train", 1),
    ("joelniklaus/brazilian_court_decisions", "default", "train", 1),
    ("celsowm/modelos_peticoes", "default", "train", 1),
]


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "polar-sentinel"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def baixar(destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for dataset, config, split, limite in FONTES:
        api = (f"https://huggingface.co/api/datasets/{dataset}/parquet/"
               f"{urllib.parse.quote(config)}/{urllib.parse.quote(split)}")
        try:
            urls = json.loads(_get(api))
        except Exception as exc:  # um conjunto fora do ar nao impede os outros
            print(f"FALHOU {dataset} [{config}/{split}]: {exc}")
            continue
        for i, url in enumerate(urls[:limite]):
            nome = f"{dataset.replace('/', '__')}__{config}__{split}__{i}.parquet"
            alvo = destino / nome
            if not alvo.exists():
                alvo.write_bytes(_get(url))
            print(f"{alvo.stat().st_size / 1e6:8.1f} MB  {nome}  ({len(urls)} arquivo(s) no split)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    baixar(Path(sys.argv[1]))
