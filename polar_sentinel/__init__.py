"""Polar Sentinel.

Camada aberta de defesa em profundidade para uso seguro e soberano de
inteligencia artificial no Judiciario brasileiro.

A arquitetura tem cinco linhas de defesa:

    L1  Sanitizacao deterministica (zero trust de documento)
    L2  Deteccao adversarial (ensemble de detectores)
    L3  Vinculacao a evidencias e proveniencia (anti RAG poisoning)
    L4  Governanca da saida (least agency + aprovacao humana)
    L5  Observabilidade e trilha auditavel

API rapida:

    from polar_sentinel import sanitize_ingested_text, filter_pii
    from polar_sentinel import SentinelPipeline, create_judicial_orchestrator

Alinhado a Resolucao CNJ 615/2025 e a Manifestacao Tecnica CNIAJ 1/2026.
"""

from __future__ import annotations

__version__ = "0.4.1"

from polar_sentinel.reference.sanitizer import (
    sanitize_ingested_text,
    sanitize_with_audit,
)
from polar_sentinel.reference.injection_detector import detect_suspicious_patterns
from polar_sentinel.reference.privacy_filter import filter_pii
from polar_sentinel.reference.provenance import check_provenance, add_provenance
from polar_sentinel.reference.hitl_approval import (
    ApprovalRequiredError,
    create_pending_approval,
    approve_pending,
    consume_approval,
    payload_hash,
)
from polar_sentinel.harness.orchestration import (
    DefenseOrchestrator,
    create_judicial_orchestrator,
)
from polar_sentinel.harness.sentinel_pipeline import SentinelPipeline

__all__ = [
    "__version__",
    "sanitize_ingested_text",
    "sanitize_with_audit",
    "detect_suspicious_patterns",
    "filter_pii",
    "check_provenance",
    "add_provenance",
    "ApprovalRequiredError",
    "create_pending_approval",
    "approve_pending",
    "consume_approval",
    "payload_hash",
    "DefenseOrchestrator",
    "create_judicial_orchestrator",
    "SentinelPipeline",
]
