"""Polar Sentinel: medida em dados publicos reais.

Os conjuntos proprios (corpus, validacao e cegos) foram escritos para este
projeto. Este script mede as mesmas defesas em dados que existiam antes dele:

    ataques    escritos por pessoas em competicoes e coletados em uso real
               (LLMail-Inject, in-the-wild jailbreak prompts, deepset), mais
               dois conjuntos com injecoes em portugues (Weni, yanismiraoui)
    benignos   decisoes e ementas reais de tribunais brasileiros (STJ, TRT-13,
               TJSP, TJAL), modelos de peticao, e o NotInject, feito para pegar
               filtros que disparam com palavras-gatilho

Cada conjunto e dividido em duas metades pelo hash do texto, antes de qualquer
medida: "desenvolvimento", que pode ser lida para corrigir regras, e "teste",
que so recebe medida. O numero que vale e o da metade de teste.

Os dados nao sao redistribuidos aqui. Baixe com:
    python -m polar_sentinel.benchmarks.baixar_externos <pasta>

Uso (pede pyarrow):
    python -m polar_sentinel.benchmarks.external_eval <pasta>
    python -m polar_sentinel.benchmarks.external_eval <pasta> --parte desenvolvimento --erros 5
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from polar_sentinel.benchmarks.agent_safety_bench import is_flagged

logging.disable(logging.CRITICAL)

# Teto de casos por conjunto, para a medida rodar em minutos. A amostra e
# deterministica: os de menor hash.
MAX_POR_CONJUNTO = 2000


def _h(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def parte_de(texto: str) -> str:
    """Metade a que o texto pertence, fixada pelo hash."""
    return "desenvolvimento" if int(_h(texto)[:2], 16) % 2 == 0 else "teste"


def _ler(pasta: Path, prefixo: str, colunas: List[str]) -> Iterable[Dict[str, object]]:
    import pyarrow.parquet as pq

    for arq in sorted(pasta.glob(prefixo + "*.parquet")):
        tabela = pq.read_table(arq, columns=colunas)
        for linha in tabela.to_pylist():
            yield linha


def _textos(linhas: Iterable[Dict[str, object]], monta: Callable[[Dict[str, object]], Optional[str]]) -> List[str]:
    vistos = {}
    for linha in linhas:
        texto = monta(linha)
        if texto and texto.strip() and len(texto) >= 20:
            vistos.setdefault(_h(texto), texto)
    return [vistos[k] for k in sorted(vistos)[:MAX_POR_CONJUNTO]]


# nome, benigno, descricao, carregador
Conjunto = Tuple[str, bool, str, Callable[[Path], List[str]]]

CONJUNTOS: List[Conjunto] = [
    ("LLMail-Inject", False, "e-mails de ataque escritos por participantes de competicao (ingles)",
     lambda p: _textos(_ler(p, "microsoft__llmail-inject-challenge", ["subject", "body"]),
                       lambda r: f"{r['subject'] or ''}\n{r['body'] or ''}")),
    ("In-the-wild jailbreaks", False, "prompts de jailbreak coletados em Reddit e Discord (ingles)",
     lambda p: _textos(_ler(p, "TrustAIRLab__in-the-wild-jailbreak-prompts", ["prompt", "jailbreak"]),
                       lambda r: r["prompt"] if r["jailbreak"] else None)),
    ("deepset (ataques)", False, "injecoes rotuladas, em ingles e alemao",
     lambda p: _textos(_ler(p, "deepset__prompt-injections", ["text", "label"]),
                       lambda r: r["text"] if r["label"] == 1 else None)),
    ("Weni (portugues)", False, "injecoes em portugues",
     lambda p: _textos(_ler(p, "Weni__prompt-injections", ["text"]), lambda r: r["text"])),
    ("yanismiraoui (multilingue)", False, "injecoes curtas em varios idiomas",
     lambda p: _textos(_ler(p, "yanismiraoui__prompt_injections", ["prompt_injections"]),
                       lambda r: r["prompt_injections"])),
    ("STJ, acordaos inteiros", True, "decisoes reais do STJ, texto integral",
     lambda p: _textos(_ler(p, "walmeidadf__STJ-SumBR", ["documento"]), lambda r: r["documento"])),
    ("TRT-13, ementas", True, "ementas reais da Justica do Trabalho",
     lambda p: _textos(_ler(p, "zeraulalmeida__Jurisprudencia_TRT_13", ["ementa"]), lambda r: r["ementa"])),
    ("TJSP, ementas", True, "ementas reais do TJSP",
     lambda p: _textos(_ler(p, "celsowm__jurisprudencias_tjsp", ["ementa"]), lambda r: r["ementa"])),
    ("TJAL, ementas", True, "ementas reais do TJAL",
     lambda p: _textos(_ler(p, "joelniklaus__brazilian_court_decisions", ["ementa_text"]),
                       lambda r: r["ementa_text"])),
    ("Modelos de peticao", True, "modelos de peticao publicados na web",
     lambda p: _textos(_ler(p, "celsowm__modelos_peticoes", ["conteudo"]), lambda r: r["conteudo"])),
    ("NotInject", True, "frases inofensivas com palavras-gatilho (ingles e outros)",
     lambda p: _textos(_ler(p, "leolee99__NotInject", ["prompt"]), lambda r: r["prompt"])),
    ("deepset (benignos)", True, "perguntas comuns, em ingles e alemao",
     lambda p: _textos(_ler(p, "deepset__prompt-injections", ["text", "label"]),
                       lambda r: r["text"] if r["label"] == 0 else None)),
]


def medir(pasta: Path, parte: str = "teste") -> List[Tuple[str, bool, int, int, List[str]]]:
    """Devolve, por conjunto: (nome, benigno, sinalizados, total, textos em que errou)."""
    resultados = []
    for nome, benigno, _, carregar in CONJUNTOS:
        textos = [t for t in carregar(pasta) if parte == "tudo" or parte_de(t) == parte]
        sinalizados, erros = 0, []
        for texto in textos:
            marcado = is_flagged(texto)
            sinalizados += int(marcado)
            if marcado == benigno:
                erros.append(texto)
        resultados.append((nome, benigno, sinalizados, len(textos), erros))
    return resultados


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Mede as defesas em dados publicos reais.")
    parser.add_argument("pasta", type=Path, help="pasta com os parquet baixados")
    parser.add_argument("--parte", choices=["teste", "desenvolvimento", "tudo"], default="teste")
    parser.add_argument("--erros", type=int, default=0, help="quantos erros mostrar por conjunto")
    opts = parser.parse_args()
    parte, n_erros = opts.parte, opts.erros
    print(f"Polar Sentinel: medida em dados publicos reais (metade: {parte})\n")
    for nome, benigno, sinalizados, total, erros in medir(opts.pasta, parte):
        if not total:
            print(f"  {nome:28} sem dados na pasta")
            continue
        rotulo = "falsos positivos" if benigno else "ataques pegos   "
        print(f"  {nome:28} {rotulo} {sinalizados:5}/{total:<5} ({100.0 * sinalizados / total:5.1f}%)")
        for texto in erros[:n_erros]:
            print("      -", " ".join(texto.split())[:220])


if __name__ == "__main__":
    main()
