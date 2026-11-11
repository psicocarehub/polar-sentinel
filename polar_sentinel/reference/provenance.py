"""Polar Sentinel: L3 Proveniencia e vinculacao a evidencias (referencia).

Verificacao de origem e integridade de trechos consultados, util contra o
envenenamento de bases de recuperacao (RAG poisoning) com jurisprudencia falsa
ou documentos adulterados.

A ideia central e simples e auditavel:

    1.  Cada trecho carrega a sua origem e, idealmente, o hash do conteudo
        original. Se o hash nao confere, o trecho foi adulterado.
    2.  A origem e confrontada com a lista de fontes confiaveis esperadas. Um
        trecho que nao vem de um acervo oficial verificado e tratado como nao
        confiavel, em vez de chegar ao usuario com aparencia de autoridade.

Esta e uma referencia conceitual. Em producao, a vinculacao usa assinaturas
por trecho e a separacao entre o acervo oficial somente leitura e o corpus de
trabalho de cada organizacao.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Marcadores de origem de fontes oficiais reconhecidas.
TRUSTED_SOURCES = {"stf", "stj", "tst", "cnj", "dou", "trf", "tjsp", "tj", "trt", "tse", "lexml"}


@dataclass
class ProvenanceVerdict:
    """Resultado estruturado da verificacao de proveniencia."""

    trusted: bool
    reason: str
    source: str = ""


def _verify(chunk: Dict, expected_sources: Optional[List[str]] = None) -> ProvenanceVerdict:
    source = (chunk.get("source") or "").lower()
    text = chunk.get("text", "")
    provided_hash = chunk.get("sha256")

    if not text:
        return ProvenanceVerdict(False, "trecho_vazio", source)

    computed = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if provided_hash and provided_hash != computed:
        return ProvenanceVerdict(False, "hash_mismatch_trecho_adulterado", source)

    if expected_sources:
        for expected in expected_sources:
            if expected.lower() in source:
                return ProvenanceVerdict(True, "fonte_esperada_confirmada", source)
        return ProvenanceVerdict(False, "fonte_fora_da_lista_esperada", source)

    if any(token in source for token in TRUSTED_SOURCES):
        return ProvenanceVerdict(True, "fonte_oficial_reconhecida", source)

    return ProvenanceVerdict(False, "fonte_nao_confiavel_ou_desconhecida", source)


def check_provenance(
    chunk: Dict, expected_sources: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Verifica um trecho e devolve (e_confiavel, motivo).

    chunk esperado:
        {
            "text": "...",
            "source": "dou_2026_xxx.pdf" ou uma url,
            "sha256": "hash do conteudo original"  (opcional)
        }
    """
    verdict = _verify(chunk, expected_sources)
    return verdict.trusted, verdict.reason


def verify(chunk: Dict, expected_sources: Optional[List[str]] = None) -> ProvenanceVerdict:
    """Variante que devolve o veredito estruturado completo."""
    return _verify(chunk, expected_sources)


def add_provenance(chunk_text: str, source: str) -> Dict:
    """Cria um trecho com metadados de proveniencia (origem e hash)."""
    return {
        "text": chunk_text,
        "source": source,
        "sha256": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
    }


if __name__ == "__main__":
    bom = add_provenance("Sumula 7 do STJ ...", "stj_jurisprudencia.json")
    print(check_provenance(bom, expected_sources=["stj"]))

    envenenado = {"text": "Sumula 999 inexistente", "source": "blog_aleatorio.html"}
    print(check_provenance(envenenado, expected_sources=["stj", "stf"]))
