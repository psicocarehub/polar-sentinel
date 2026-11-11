"""Polar Sentinel: L0 Filtro de privacidade (referencia).

Remove dados pessoais (PII) de documentos juridicos antes que qualquer texto
chegue ao modelo de linguagem. E a primeira fronteira de soberania e de
conformidade com a LGPD: nenhum CPF, CNPJ, nome ou endereco deveria ser
enviado a um modelo externo sem necessidade.

Estrategia em duas camadas:

    1.  Preferencialmente, um modelo de classificacao de tokens roda
        localmente (por exemplo openai/privacy-filter no Hugging Face), o que
        captura nomes, organizacoes e enderecos com contexto.
    2.  Como fallback robusto e sem dependencias, um conjunto de expressoes
        regulares cobre os formatos brasileiros mais comuns (CPF, CNPJ, RG,
        telefone, email, CEP, conta bancaria).

Uso recomendado:

    from polar_sentinel.reference.privacy_filter import filter_pii

    resultado = filter_pii(texto_do_documento)
    texto_limpo = resultado.text
    entidades = resultado.entities
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger("polar_sentinel.privacy_filter")

# Formatos brasileiros comuns. A ordem importa: padroes mais especificos
# (CNPJ, CPF) vem antes de padroes mais amplos para vencer a resolucao de
# sobreposicao por prioridade.
BRAZILIAN_PII_PATTERNS: List[Tuple[str, str]] = [
    ("cnpj", r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    ("cpf", r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("rg", r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[0-9Xx]\b"),
    ("cep", r"\b\d{5}-\d{3}\b"),
    ("phone", r"\b(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?\d{4,5}-\d{4}\b"),
    ("bank_account", r"\b(?:agencia|conta)\s*[:=]?\s*\d+[-/]?\d*\b"),
]


@dataclass
class PIIEntity:
    """Uma ocorrencia de dado pessoal encontrada e redigida."""

    type: str
    text: str
    start: int
    end: int
    redacted: str


@dataclass
class PrivacyFilterResult:
    """Resultado da filtragem de PII."""

    text: str
    entities: List[PIIEntity] = field(default_factory=list)
    model_used: str = "none"


def _resolve_overlaps(spans: List[PIIEntity]) -> List[PIIEntity]:
    """Mantem apenas spans nao sobrepostos, com prioridade por ordem de chegada.

    Como os padroes mais especificos sao avaliados primeiro, eles ganham de
    padroes mais amplos que cobririam a mesma regiao do texto.
    """
    spans = sorted(spans, key=lambda e: (e.start, -(e.end - e.start)))
    kept: List[PIIEntity] = []
    last_end = -1
    for span in spans:
        if span.start >= last_end:
            kept.append(span)
            last_end = span.end
    return kept


def _apply_redactions(text: str, spans: List[PIIEntity]) -> str:
    """Reconstroi o texto substituindo cada span pelo seu rotulo redigido.

    A reconstrucao e feita em uma unica passagem da direita para a esquerda,
    de modo que os offsets originais permanecem validos durante todo o
    processo. Esse e o ponto que a versao anterior errava.
    """
    out = text
    for span in sorted(spans, key=lambda e: e.start, reverse=True):
        out = out[: span.start] + span.redacted + out[span.end :]
    return out


def _regex_fallback_redact(text: str) -> Tuple[str, List[PIIEntity]]:
    """Redige PII brasileira via expressoes regulares, sem corromper offsets."""
    found: List[PIIEntity] = []
    for pii_type, pattern in BRAZILIAN_PII_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            found.append(
                PIIEntity(
                    type=pii_type,
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    redacted=f"[{pii_type.upper()}_REDACTED]",
                )
            )

    kept = _resolve_overlaps(found)
    redacted = _apply_redactions(text, kept)
    # Devolve em ordem de leitura para facilitar auditoria.
    return redacted, sorted(kept, key=lambda e: e.start)


def filter_pii(
    text: str,
    use_hf_model: bool = False,
    hf_model_name: str = "openai/privacy-filter",
    device: str = "cpu",
) -> PrivacyFilterResult:
    """Filtra PII do texto.

    Por padrao usa apenas o fallback determinístico em regex, que nao tem
    dependencias e e adequado para o harness. Passe use_hf_model=True para
    tentar primeiro o modelo de classificacao de tokens (requer o extra `ml`).

    Args:
        text: texto do documento (peticao, decisao, etc.).
        use_hf_model: tentar o modelo do Hugging Face antes do fallback.
        hf_model_name: nome do modelo de classificacao de tokens.
        device: "cpu" ou "cuda".

    Returns:
        PrivacyFilterResult com o texto redigido e as entidades encontradas.
    """
    if not text or not text.strip():
        return PrivacyFilterResult(text=text or "", entities=[], model_used="none")

    if use_hf_model:
        try:
            return _filter_with_model(text, hf_model_name, device)
        except Exception as exc:  # pragma: no cover - caminho opcional
            logger.warning("Modelo de privacidade indisponivel (%s). Usando regex.", exc)

    redacted, entities = _regex_fallback_redact(text)
    return PrivacyFilterResult(text=redacted, entities=entities, model_used="regex_fallback_br")


def _filter_with_model(text: str, model_name: str, device: str) -> PrivacyFilterResult:
    """Caminho opcional que usa um modelo de classificacao de tokens."""
    from transformers import pipeline  # importado sob demanda

    classifier = pipeline(
        "token-classification",
        model=model_name,
        aggregation_strategy="simple",
        device=0 if device == "cuda" else -1,
    )

    spans: List[PIIEntity] = []
    for entity in classifier(text):
        label = str(entity.get("entity_group", "pii")).lower()
        start, end = int(entity["start"]), int(entity["end"])
        spans.append(
            PIIEntity(
                type=label,
                text=text[start:end],
                start=start,
                end=end,
                redacted=f"[{label.upper()}_REDACTED]",
            )
        )

    kept = _resolve_overlaps(spans)
    redacted = _apply_redactions(text, kept)
    return PrivacyFilterResult(
        text=redacted,
        entities=sorted(kept, key=lambda e: e.start),
        model_used=model_name,
    )


if __name__ == "__main__":
    amostra = (
        "O autor, CPF 123.456.789-00, CNPJ 12.345.678/0001-90, email "
        "fulano@exemplo.com, telefone (11) 98765-4321, requer indenizacao."
    )
    resultado = filter_pii(amostra)
    print("Modelo:", resultado.model_used)
    print("Texto:", resultado.text)
    print("Entidades:", [(e.type, e.text) for e in resultado.entities])
