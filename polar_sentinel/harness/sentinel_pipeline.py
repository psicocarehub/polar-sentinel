"""Polar Sentinel: pipeline principal.

Combina o orquestrador de defesas com o portao de aprovacao humana e, quando
configurado, com um adapter de modelo. Funciona com qualquer API: o pipeline
nunca amarra o usuario a um modelo especifico.

Exemplo:

    from polar_sentinel.harness.adapters import OpenAICompatibleAdapter
    from polar_sentinel.harness.sentinel_pipeline import SentinelPipeline

    adapter = OpenAICompatibleAdapter(base_url="https://sua-api/v1", model="seu-modelo")
    pipeline = SentinelPipeline(adapter=adapter)

    resultado = pipeline.analyze_and_protect(texto, action="tribunal.protocolar")
    print(resultado["status"], resultado["risk_score"])
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from polar_sentinel.reference.privacy_filter import filter_pii
from polar_sentinel.reference.hitl_approval import create_pending_approval, payload_hash
from polar_sentinel.harness.adapters import BaseAdapter
from polar_sentinel.harness.orchestration import DefenseOrchestrator, create_judicial_orchestrator

# Acima deste risco, a revisao humana passa a ser obrigatoria.
HITL_RISK_THRESHOLD = 0.35

# Acoes que sempre exigem revisao humana por envolverem certificado digital.
CRITICAL_ACTIONS = ("protocolar", "juntada", "ciencia", "assinar")


class SentinelPipeline:
    """Pipeline orquestrado de alto nivel."""

    def __init__(
        self,
        adapter: Optional[BaseAdapter] = None,
        use_orchestrator: bool = True,
        custom_orchestrator: Optional[DefenseOrchestrator] = None,
    ):
        self.adapter = adapter
        if custom_orchestrator is not None:
            self.orchestrator: Optional[DefenseOrchestrator] = custom_orchestrator
        elif use_orchestrator:
            self.orchestrator = create_judicial_orchestrator()
        else:
            self.orchestrator = None

    def analyze_and_protect(
        self,
        document_text: str,
        action: str = "tribunal.analyze",
        user_id: str = "anonimo",
        require_hitl: bool = True,
        **adapter_kwargs: Any,
    ) -> Dict[str, Any]:
        """Executa o pipeline completo e devolve um resultado serializavel."""
        context = {"action": action, "user_id": user_id, "source": "judicial_document"}

        if self.orchestrator is not None:
            orch = self.orchestrator.run(document_text, context=context)
            final_text = orch.final_text
            risk_score = orch.score
            blocked_by_orchestration = orch.blocked
            layer_details = [
                {
                    "layer": layer.layer,
                    "score": layer.score,
                    "blocked": layer.blocked,
                    "metadata": layer.metadata,
                }
                for layer in orch.layers
            ]
        else:
            privacy = filter_pii(document_text)
            final_text = privacy.text
            risk_score = min(0.15 * len(privacy.entities), 0.6)
            blocked_by_orchestration = False
            layer_details = [{"layer": "privacidade", "entities": len(privacy.entities)}]

        is_critical = any(token in action.lower() for token in CRITICAL_ACTIONS)
        hitl_required = require_hitl and (
            risk_score > HITL_RISK_THRESHOLD or is_critical or blocked_by_orchestration
        )

        approval_id = None
        if hitl_required:
            approval = create_pending_approval(
                action=action,
                payload={"text_sha256": payload_hash(action, {"text": final_text})},
                user_id=user_id,
            )
            approval_id = approval.id

        # O modelo so e chamado quando nao ha gate humano pendente.
        model_response = None
        if self.adapter is not None and not hitl_required:
            try:
                model_response = self.adapter.generate(final_text, **adapter_kwargs)
            except Exception as exc:
                model_response = f"[erro do adapter] {exc}"

        status = "PROTEGIDO" if hitl_required else "ANALISADO"
        if risk_score > 0.6:
            status = "ALTO_RISCO_" + status

        return {
            "final_text": final_text,
            "privacy_filtered": True,
            "sanitized": True,
            "risk_score": round(risk_score, 3),
            "hitl_required": hitl_required,
            "approval_id": approval_id,
            "status": status,
            "layer_details": layer_details,
            "model_response": model_response,
        }
