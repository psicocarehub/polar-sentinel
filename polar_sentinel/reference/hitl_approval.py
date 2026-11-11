"""Polar Sentinel: L4 Aprovacao humana (Human in the Loop).

Padrao de referencia para acoes irreversiveis com certificado digital
(ICP-Brasil) em ambiente judicial, por exemplo protocolar uma peticao, fazer
juntada ou dar ciencia.

Fluxo obrigatorio em tres etapas, que o agente nunca pode percorrer sozinho:

    1.  /preview     o sistema cria uma aprovacao pendente com o hash canonico
                     do payload e devolve um identificador e uma previa.
    2.  aprovacao    um humano, dono da acao, aprova ou rejeita na interface.
    3.  /commit      a acao so executa apos consumir a aprovacao, que e de uso
                     unico, dentro da janela de validade e com hash conferido.

Diferente de um exemplo apenas ilustrativo, este modulo implementa um cofre
de estado em memoria, com travas de atomicidade, para que o comportamento da
referencia seja real e testavel: sem aprovacao valida, a acao e bloqueada.

Em producao, este mesmo contrato e atendido por uma funcao no banco de dados
com SECURITY DEFINER e checagem de propriedade, que torna o consumo atomico e
audita cada transicao. A interface publica abaixo e identica.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

APPROVAL_TTL_SECONDS = 120  # janela curta de 2 minutos para dificultar replay


class ApprovalRequiredError(PermissionError):
    """Acao bloqueada: aprovacao humana obrigatoria nao consumida ou invalida."""


@dataclass(frozen=True)
class PendingApproval:
    """Referencia devolvida ao criar uma aprovacao pendente."""

    id: str
    action: str
    payload_hash: str
    expires_at: float


@dataclass
class _ApprovalState:
    """Estado interno do cofre de aprovacoes."""

    id: str
    action: str
    payload_hash: str
    user_id: str
    expires_at: float
    status: str = "pending"  # pending, approved, rejected
    consumed: bool = False


_STORE: Dict[str, _ApprovalState] = {}
_LOCK = threading.Lock()


def payload_hash(action: str, payload: Mapping[str, Any]) -> str:
    """Hash canonico SHA-256 de (action, payload).

    Usa sort_keys para determinismo. Binarios devem entrar como "<nome>_sha256",
    nunca como bytes crus. Este hash e a fonte unica de verdade para a nocao de
    "mesmo payload".
    """
    if not isinstance(action, str) or not action:
        raise ValueError("action deve ser uma string nao vazia")
    if not isinstance(payload, Mapping):
        raise TypeError("payload deve ser um mapping")

    canonical = json.dumps(
        {"action": action, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_bytes(blob: bytes) -> str:
    """SHA-256 de bytes, para fingerprint de PDFs e anexos sem vazar conteudo."""
    return hashlib.sha256(blob).hexdigest()


def create_pending_approval(
    *,
    action: str,
    payload: Mapping[str, Any],
    user_id: str,
    ttl_seconds: int = APPROVAL_TTL_SECONDS,
    now: Optional[float] = None,
) -> PendingApproval:
    """Cria uma aprovacao pendente e a registra no cofre de estado."""
    now = time.time() if now is None else now
    digest = payload_hash(action, payload)
    expires = now + ttl_seconds
    approval_id = f"appr_{int(now * 1000)}_{digest[:8]}"

    with _LOCK:
        _STORE[approval_id] = _ApprovalState(
            id=approval_id,
            action=action,
            payload_hash=digest,
            user_id=user_id,
            expires_at=expires,
        )

    return PendingApproval(
        id=approval_id,
        action=action,
        payload_hash=digest,
        expires_at=expires,
    )


def approve_pending(approval_id: str, *, user_id: str, now: Optional[float] = None) -> bool:
    """Aprova uma pendencia. So o dono da acao pode aprovar, antes de expirar.

    Retorna True se a transicao para 'approved' foi feita, False caso contrario.
    """
    now = time.time() if now is None else now
    with _LOCK:
        state = _STORE.get(approval_id)
        if state is None:
            return False
        if state.status != "pending":
            return False
        if state.user_id != user_id:
            return False
        if now > state.expires_at:
            return False
        state.status = "approved"
        return True


def reject_pending(approval_id: str, *, user_id: str) -> bool:
    """Rejeita uma pendencia. So o dono da acao pode rejeitar."""
    with _LOCK:
        state = _STORE.get(approval_id)
        if state is None or state.user_id != user_id:
            return False
        state.status = "rejected"
        return True


def consume_approval(
    approval_id: str,
    action: str,
    payload_hash: str,
    *,
    now: Optional[float] = None,
) -> bool:
    """Consome a aprovacao de forma atomica e de uso unico.

    Retorna True apenas se TODAS as condicoes valem:
        - a aprovacao existe;
        - o status e 'approved';
        - nao expirou;
        - ainda nao foi consumida;
        - a acao confere;
        - o hash do payload atual confere com o aprovado.

    Em caso afirmativo, marca como consumida e nunca mais pode ser reutilizada.
    """
    now = time.time() if now is None else now
    with _LOCK:
        state = _STORE.get(approval_id)
        if state is None:
            return False
        if state.consumed:
            return False
        if state.status != "approved":
            return False
        if now > state.expires_at:
            return False
        if state.action != action:
            return False
        if state.payload_hash != payload_hash:
            return False
        state.consumed = True
        return True


def reset_store() -> None:
    """Limpa o cofre de estado. Util para testes."""
    with _LOCK:
        _STORE.clear()


def require_consumed_approval(action: str):
    """Decorator de exemplo para endpoints de commit.

    O endpoint decorado exige um approval_id valido e o consome antes de
    executar. O hash do payload atual deve ser recomputado pelo chamador e
    passado em payload_sha; assim, um payload mutado apos a aprovacao falha.
    """

    def decorator(func):
        def wrapper(*args, approval_id: Optional[str] = None, payload_sha: str = "", **kwargs):
            if not approval_id:
                raise ApprovalRequiredError(f"approval_id obrigatorio para {action}")
            if not consume_approval(approval_id, action, payload_sha):
                raise ApprovalRequiredError(f"aprovacao humana nao consumida para {action}")
            return func(*args, **kwargs)

        return wrapper

    return decorator


if __name__ == "__main__":
    reset_store()
    payload = {"tribunal": "TRT-8", "pdf_sha256": "abc123"}
    digest = payload_hash("tribunal.protocolar", payload)

    pend = create_pending_approval(
        action="tribunal.protocolar", payload=payload, user_id="advogada_1"
    )
    print("Sem aprovacao, consumo retorna:", consume_approval(pend.id, "tribunal.protocolar", digest))
    print("Aprovacao pelo dono:", approve_pending(pend.id, user_id="advogada_1"))
    print("Consumo apos aprovar:", consume_approval(pend.id, "tribunal.protocolar", digest))
    print("Replay do mesmo consumo:", consume_approval(pend.id, "tribunal.protocolar", digest))
