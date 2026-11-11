"""Polar Sentinel: orquestrador de defesas.

Encadeia as camadas de defesa de forma flexivel e auditavel. Cada camada
recebe o texto corrente e um contexto, e devolve um resultado normalizado com:

    text      texto possivelmente transformado (por exemplo apos redacao)
    score     risco atribuido pela camada, de 0 a 1
    blocked   verdadeiro quando a camada decide barrar por conta propria
    metadata  detalhes para a trilha de auditoria

O orquestrador agrega os scores, monta a trilha por camada e pode operar em
modo "fail fast" (para na primeira camada que bloqueia) ou em modo de relatorio
completo (executa todas as camadas e consolida o resultado).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

LayerFn = Callable[[str, Dict[str, Any]], Any]


@dataclass
class LayerResult:
    """Resultado de uma camada dentro da orquestracao."""

    layer: str
    input_preview: str
    output_preview: str
    score: float = 0.0
    blocked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestrationResult:
    """Resultado consolidado da orquestracao."""

    final_text: str
    layers: List[LayerResult]
    blocked: bool
    reason: Optional[str] = None
    score: float = 0.0


def _normalize(result: Any, current_text: str) -> Tuple[str, float, bool, Dict[str, Any]]:
    """Normaliza o retorno heterogeneo de uma camada para (text, score, blocked, meta).

    Aceita:
        - dict com chaves text, score, blocked, metadata;
        - tupla (score, razoes), como a do detector L2;
        - objeto com atributo .text (por exemplo um resultado de dataclass);
        - qualquer outro valor, tratado como texto.
    """
    if isinstance(result, dict):
        text = result.get("text", current_text)
        score = float(result.get("score", 0.0))
        blocked = bool(result.get("blocked", False))
        meta = result.get("metadata", {k: v for k, v in result.items() if k != "text"})
        return text, score, blocked, meta

    if isinstance(result, tuple) and len(result) == 2:
        score, reasons = result
        return current_text, float(score), False, {"reasons": reasons}

    if hasattr(result, "text"):
        text = getattr(result, "text")
        score = float(getattr(result, "score", 0.0))
        meta = {"entities": getattr(result, "entities", [])}
        return text, score, False, meta

    return str(result), 0.0, False, {}


class DefenseOrchestrator:
    """Orquestrador de defesas em profundidade.

    Permite montar pipelines como:
        Privacidade  ->  Sanitizacao  ->  Deteccao  ->  Proveniencia
    """

    def __init__(self, fail_fast: bool = True, risk_threshold: float = 0.4):
        self.layers: List[Tuple[str, LayerFn]] = []
        self.fail_fast = fail_fast
        self.risk_threshold = risk_threshold

    def add_layer(self, name: str, fn: LayerFn) -> "DefenseOrchestrator":
        self.layers.append((name, fn))
        return self

    def remove_layer(self, name: str) -> "DefenseOrchestrator":
        self.layers = [(n, f) for n, f in self.layers if n != name]
        return self

    def run(self, text: str, context: Optional[Dict[str, Any]] = None) -> OrchestrationResult:
        """Executa as camadas na ordem registrada e consolida o resultado."""
        context = context or {}
        current_text = text
        results: List[LayerResult] = []
        total_score = 0.0
        blocked = False
        reason: Optional[str] = None

        for name, layer_fn in self.layers:
            try:
                raw = layer_fn(current_text, context)
                new_text, score, layer_blocked, meta = _normalize(raw, current_text)
            except Exception as exc:  # uma camada que falha bloqueia por seguranca
                results.append(
                    LayerResult(
                        layer=name,
                        input_preview=current_text[:200],
                        output_preview="ERRO",
                        score=1.0,
                        blocked=True,
                        metadata={"error": str(exc)},
                    )
                )
                blocked = True
                reason = f"erro_em_{name}"
                if self.fail_fast:
                    break
                continue

            total_score = max(total_score, score)
            over_threshold = score > self.risk_threshold
            this_blocked = layer_blocked or over_threshold

            results.append(
                LayerResult(
                    layer=name,
                    input_preview=current_text[:200],
                    output_preview=new_text[:200],
                    score=round(score, 3),
                    blocked=this_blocked,
                    metadata=meta,
                )
            )
            current_text = new_text

            if this_blocked:
                blocked = True
                reason = f"bloqueado_por_{name}_score_{score:.2f}"
                if self.fail_fast:
                    break

        return OrchestrationResult(
            final_text=current_text,
            layers=results,
            blocked=blocked,
            reason=reason,
            score=round(total_score, 3),
        )


def create_judicial_orchestrator(
    include_privacy: bool = True,
    include_sanitize: bool = True,
    include_detection: bool = True,
    include_provenance: bool = False,
    fail_fast: bool = False,
) -> DefenseOrchestrator:
    """Monta a orquestracao recomendada para documentos judiciais.

    Por padrao roda Privacidade, Sanitizacao e Deteccao em modo de relatorio
    completo (fail_fast=False), para que todas as camadas contribuam com a
    trilha de auditoria. A proveniencia fica opcional porque depende de
    contexto de fonte por trecho.
    """
    from polar_sentinel.reference.privacy_filter import filter_pii
    from polar_sentinel.reference.sanitizer import sanitize_with_audit
    from polar_sentinel.reference.injection_detector import detect_suspicious_patterns
    from polar_sentinel.reference.provenance import check_provenance

    orch = DefenseOrchestrator(fail_fast=fail_fast)

    if include_privacy:

        def _privacy(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
            res = filter_pii(text)
            # Dado pessoal e redigido aqui e registrado na trilha. Ele nao e sinal
            # de ataque: toda peticao qualifica as partes. Por isso nao soma risco.
            return {
                "text": res.text,
                "score": 0.0,
                "metadata": {
                    "entities": len(res.entities),
                    "types": sorted({e.type for e in res.entities}),
                    "model": res.model_used,
                },
            }

        orch.add_layer("privacidade", _privacy)

    if include_sanitize:

        def _sanitize(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
            res = sanitize_with_audit(text, source=ctx.get("source", "judicial"))
            score = 0.0
            if res.suspicious:
                score = 0.6
            elif res.hidden_text.strip():
                score = 0.15
            # O que estava escondido segue para a deteccao, que decide pelo conteudo.
            ctx["_hidden_text"] = res.hidden_text
            return {
                "text": res.text,
                "score": score,
                "metadata": {
                    "removed": [(e.kind, e.count) for e in res.entries],
                    "suspicious": res.suspicious,
                    "hidden_chars": len(res.hidden_text),
                },
            }

        orch.add_layer("sanitizacao", _sanitize)

    if include_detection:

        def _detect(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
            stage = ctx.get("stage", "entrada")
            score, reasons = detect_suspicious_patterns(text, stage=stage)
            hidden = ctx.get("_hidden_text") or ""
            if hidden.strip():
                # Texto visivel inocente com ordem no canal oculto e o ataque tipico.
                hidden_score, hidden_reasons = detect_suspicious_patterns(hidden, stage=stage)
                if hidden_score > 0.2:
                    score = min(1.0, round(max(score, hidden_score) + 0.2, 3))
                    reasons = [r for r in reasons if r != "nenhum_padrao_suspeito"]
                    reasons += ["comando_em_canal_oculto"] + hidden_reasons
            return {"text": text, "score": score, "metadata": {"reasons": reasons}}

        orch.add_layer("deteccao", _detect)

    if include_provenance:

        def _provenance(text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
            chunk = {"text": text, "source": ctx.get("source", "desconhecido")}
            ok, msg = check_provenance(chunk, ctx.get("expected_sources"))
            return {
                "text": text,
                "score": 0.0 if ok else 0.6,
                "blocked": not ok,
                "metadata": {"provenance": msg},
            }

        orch.add_layer("proveniencia", _provenance)

    return orch
