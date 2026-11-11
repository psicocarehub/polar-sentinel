"""Polar Sentinel: medicao fora do corpus de desenvolvimento.

O benchmark principal (agent_safety_bench.py) roda sobre o corpus usado para
desenvolver as defesas, e por isso da 100%. Este script roda as mesmas defesas,
com o mesmo criterio de "barrado", sobre tres conjuntos:

    validacao  attacks/heldout.py, escrito por quem conhecia o detector e usado
               para ajusta-lo
    cego 1     attacks/blind_1.py, de autor que nao viu o codigo; depois da
               primeira rodada passou a ser conjunto de desenvolvimento
    cego 2     attacks/blind_2.py, de outro autor que nao viu o codigo; rodado
               uma vez, nunca usado para ajuste

So o cego 2 mede generalizacao. O protocolo e os numeros de cada rodada estao em
docs/AVALIACAO.md.

Uso:
    python -m polar_sentinel.benchmarks.heldout_eval           (resumo)
    python -m polar_sentinel.benchmarks.heldout_eval --casos   (erros caso a caso)
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from typing import Dict, List, Tuple

from polar_sentinel.attacks import blind_1, blind_2, heldout
from polar_sentinel.benchmarks.agent_safety_bench import is_flagged

logging.disable(logging.CRITICAL)

Case = Tuple[str, bool, str, str]  # id, benigno, grupo, texto


def load_sets() -> Dict[str, List[Case]]:
    """Devolve os tres conjuntos em um formato unico."""
    return {
        "validacao": [(c.id, c.benign, c.group, c.text) for c in heldout.CASES],
        "cego 1": [(c["id"], c["benign"], c["group"], c["text"]) for c in blind_1.CASES],
        "cego 2": [(c["id"], c["benign"], c["group"], c["text"]) for c in blind_2.CASES],
    }


def evaluate(cases: List[Case]) -> Tuple[int, int, int, int, Dict[str, List[int]], List[Case]]:
    """Devolve (ataques pegos, ataques, falsos positivos, benignos, por grupo, erros)."""
    per_group: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    errors: List[Case] = []
    caught = attacks = false_pos = benign = 0
    for case in cases:
        _, is_benign, group, text = case
        flagged = is_flagged(text)
        ok = flagged != is_benign
        key = ("benigno: " if is_benign else "ataque: ") + group
        per_group[key][1] += 1
        per_group[key][0] += int(ok)
        if is_benign:
            benign += 1
            false_pos += int(flagged)
        else:
            attacks += 1
            caught += int(flagged)
        if not ok:
            errors.append(case)
    return caught, attacks, false_pos, benign, per_group, errors


def main() -> None:
    print("Polar Sentinel: medicao fora do corpus de desenvolvimento\n")
    for name, cases in load_sets().items():
        caught, attacks, false_pos, benign, per_group, errors = evaluate(cases)
        print(f"{name}")
        print(f"  Deteccao de ataques : {caught}/{attacks} ({100.0 * caught / attacks:.1f}%)")
        print(f"  Falsos positivos    : {false_pos}/{benign} ({100.0 * false_pos / benign:.1f}%)")
        if "--casos" in sys.argv:
            for key in sorted(per_group):
                ok, total = per_group[key]
                print(f"    {key:44} {ok:2}/{total}")
            for case_id, is_benign, group, _ in errors:
                tipo = "benigno sinalizado" if is_benign else "ataque que escapou"
                print(f"    - {tipo}: {case_id} ({group})")
        print()


if __name__ == "__main__":
    main()
