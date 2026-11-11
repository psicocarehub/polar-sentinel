"""Polar Sentinel: inspecao de PDF (texto que o leitor humano nao ve).

Em todos os casos brasileiros conhecidos de 2026, o comando estava escondido
pela FORMA: fonte branca sobre fundo branco, fonte de menos de 1 ponto, texto
na cor da faixa do rodape. A extracao de texto comum joga fora a cor e o
tamanho, e o comando chega ao modelo misturado ao texto legitimo. Este modulo
le o conteudo da pagina e separa o que esta visivel do que esta oculto.

Um trecho conta como oculto quando:

    cor_do_fundo      a cor do texto e praticamente a cor do que esta atras dele
                      (a pagina branca, ou um retangulo pintado antes)
    fonte_minuscula   o tamanho efetivo da fonte e menor que 2 pontos
    fora_da_pagina    o texto esta posicionado fora da area da pagina

Texto branco sobre faixa escura (papel timbrado) nao e oculto: o fundo naquele
ponto e a faixa. Camada de texto invisivel de OCR (modo de renderizacao 3) e o
proprio texto de um documento digitalizado e segue como texto visivel.

A decisao fica em `evaluate_pdf`: fonte minuscula com texto de verdade sempre
sinaliza; texto na cor do fundo ou fora da pagina sinaliza quando traz uma
ordem (imperativo, mencao a IA ou qualquer sinal do detector). O trecho oculto
e devolvido para ser registrado nos autos, nunca descartado.

Limites: fundo feito de imagem nao e visto (texto branco sobre foto escura
parece oculto, por isso a exigencia de ordem); texto escondido atras de outro
objeto e texto em anotacoes ou formularios nao sao analisados.

Precisa de pypdf (pip install pypdf).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from polar_sentinel.reference.injection_detector import (
    _AI_TERM,
    _IMPERATIVE,
    detect_suspicious_patterns,
    fold,
)

Color = Tuple[float, float, float]

_WHITE: Color = (1.0, 1.0, 1.0)
_BLACK: Color = (0.0, 0.0, 0.0)

# Diferenca maxima, por componente, para duas cores contarem como a mesma.
_SAME_COLOR = 0.1
# Abaixo deste tamanho efetivo, em pontos, ninguem le.
_MIN_READABLE_PT = 2.0
# Letras a partir das quais um trecho em fonte minuscula deixa de ser residuo.
_MIN_LETTERS = 12

_FILL_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_NO_FILL_OPS = {b"n", b"S", b"s"}

_ORDER_RE = re.compile(
    r"\b(?:" + _IMPERATIVE + r")\b|\b(?:" + _AI_TERM + r")|\b(?:chat|gpt|chatgpt|inteligencia artificial)\b"
)


@dataclass
class HiddenSpan:
    """Um trecho de texto que nao aparece para quem le a pagina."""

    page: int
    text: str
    reason: str


@dataclass
class PdfInspection:
    """Texto visivel, trechos ocultos e metadados de um PDF."""

    visible_text: str
    hidden_spans: List[HiddenSpan] = field(default_factory=list)
    metadata_text: str = ""

    @property
    def hidden_text(self) -> str:
        return " ".join(s.text.strip() for s in self.hidden_spans if s.text.strip())


@dataclass
class PdfVerdict:
    """Decisao sobre um PDF, com os motivos e o que estava oculto."""

    flagged: bool
    reasons: List[str]
    inspection: PdfInspection


def _to_rgb(values: Sequence[Any]) -> Optional[Color]:
    try:
        nums = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    if len(nums) == 1:
        return (nums[0], nums[0], nums[0])
    if len(nums) == 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 4:
        c, m, y, k = nums
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _same(a: Color, b: Color) -> bool:
    return all(abs(x - y) <= _SAME_COLOR for x, y in zip(a, b))


def _scale(matrix: Sequence[float]) -> float:
    return abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) ** 0.5


def _apply(matrix: Sequence[float], x: float, y: float) -> Tuple[float, float]:
    return (matrix[0] * x + matrix[2] * y + matrix[4], matrix[1] * x + matrix[3] * y + matrix[5])


class _PageState:
    """Estado grafico minimo para saber cor, tamanho e fundo de cada trecho."""

    def __init__(self, number: int, width: float, height: float) -> None:
        self.number = number
        self.width = width
        self.height = height
        self.fill: Color = _BLACK
        self.stack: List[Color] = []
        self.pending: List[Tuple[float, float, float, float]] = []
        self.rects: List[Tuple[Tuple[float, float, float, float], Color]] = []
        self.visible: List[str] = []
        self.hidden: List[HiddenSpan] = []

    def on_operator(self, operator: bytes, args: Sequence[Any], cm: Sequence[float], tm: Sequence[float]) -> None:
        if operator == b"q":
            self.stack.append(self.fill)
        elif operator == b"Q":
            if self.stack:
                self.fill = self.stack.pop()
        elif operator in (b"g", b"rg", b"k", b"sc", b"scn"):
            color = _to_rgb(args)
            if color is not None:
                self.fill = color
        elif operator == b"re" and len(args) == 4:
            try:
                x, y, w, h = (float(a) for a in args)
            except (TypeError, ValueError):
                return
            x0, y0 = _apply(cm, x, y)
            x1, y1 = _apply(cm, x + w, y + h)
            self.pending.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        elif operator in _FILL_OPS:
            self.rects.extend((bbox, self.fill) for bbox in self.pending)
            self.pending = []
        elif operator in _NO_FILL_OPS:
            self.pending = []

    def _background(self, x: float, y: float) -> Color:
        for (x0, y0, x1, y1), color in reversed(self.rects):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return color
        return _WHITE

    def on_text(self, text: str, cm: Sequence[float], tm: Sequence[float], font: Any, size: float) -> None:
        if not text.strip():
            self.visible.append(text)
            return
        x, y = _apply(cm, tm[4], tm[5])
        effective = float(size) * _scale(tm) * _scale(cm)
        reason = ""
        if effective < _MIN_READABLE_PT:
            reason = "fonte_minuscula"
        elif x < -1 or y < -1 or x > self.width + 1 or y > self.height + 1:
            reason = "fora_da_pagina"
        elif _same(self.fill, self._background(x, y)):
            reason = "cor_do_fundo"
        if reason:
            self.hidden.append(HiddenSpan(self.number, text, reason))
        else:
            self.visible.append(text)


def inspect_pdf(source: Union[str, Path, Any]) -> PdfInspection:
    """Le um PDF e separa o texto visivel do texto oculto."""
    from pypdf import PdfReader

    reader = PdfReader(str(source) if isinstance(source, (str, Path)) else source)
    visible: List[str] = []
    hidden: List[HiddenSpan] = []
    for number, page in enumerate(reader.pages, start=1):
        box = page.mediabox
        state = _PageState(number, float(box.width), float(box.height))
        page.extract_text(visitor_operand_before=state.on_operator, visitor_text=state.on_text)
        visible.append("".join(state.visible))
        hidden.extend(state.hidden)
    metadata = " ".join(str(v) for v in (reader.metadata or {}).values() if v)
    return PdfInspection(visible_text="\n".join(visible), hidden_spans=hidden, metadata_text=metadata)


def evaluate_pdf(source: Union[str, Path, Any], stage: str = "entrada") -> PdfVerdict:
    """Decide se um PDF deve ser sinalizado, olhando texto visivel, oculto e metadados."""
    from polar_sentinel.harness.orchestration import create_judicial_orchestrator

    inspection = inspect_pdf(source)
    reasons: List[str] = []

    orchestrator = create_judicial_orchestrator(include_provenance=False)
    result = orchestrator.run(inspection.visible_text, context={"stage": stage, "source": "pdf"})
    if result.blocked or result.score > orchestrator.risk_threshold:
        reasons.append("comando_no_texto_visivel")

    if inspection.metadata_text and detect_suspicious_patterns(inspection.metadata_text, stage)[0] > 0.4:
        reasons.append("comando_em_metadado")

    by_reason = {}
    for span in inspection.hidden_spans:
        by_reason.setdefault(span.reason, []).append(span.text)
    for reason, parts in by_reason.items():
        text = " ".join(p.strip() for p in parts)
        letters = sum(ch.isalpha() for ch in text)
        has_order = bool(_ORDER_RE.search(fold(text))) or detect_suspicious_patterns(text, stage)[0] > 0.2
        if reason == "fonte_minuscula" and letters >= _MIN_LETTERS:
            reasons.append("texto_em_fonte_minuscula")
        elif has_order:
            reasons.append(f"ordem_em_texto_oculto ({reason})")

    return PdfVerdict(flagged=bool(reasons), reasons=reasons, inspection=inspection)
