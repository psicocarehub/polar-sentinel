#!/usr/bin/env python3
"""Executor do harness do Polar Sentinel.

Roda a suite de testes de seguranca judicial.

Uso:
    python -m polar_sentinel.harness.run_harness

Ou via pytest, a partir da raiz do projeto:
    python -m pytest polar_sentinel -o addopts="" -q
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    print("=== Polar Sentinel: harness de seguranca judicial ===\n")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(PACKAGE_ROOT), "-o", "addopts=", "-q"],
        cwd=str(PACKAGE_ROOT.parent),
    )
    if result.returncode == 0:
        print("\nHarness passou. As defesas de referencia estao ativas.")
    else:
        print("\nHarness falhou. Verifique as camadas L1 a L4.")
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
