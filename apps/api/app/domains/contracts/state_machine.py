"""Explicit contract state machine. No transition outside this table is permitted --
routers/services must call `assert_transition_allowed` before writing a new status.
See docs/business-rules.md#contract-state-machine."""

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED", "REJECTED"},
    "SUBMITTED": {"DOCUMENTS_PENDING", "UNDER_REVIEW", "REJECTED"},
    "DOCUMENTS_PENDING": {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED", "DOCUMENTS_PENDING"},
    "APPROVED": {"PAYMENT_PENDING", "REJECTED"},
    "PAYMENT_PENDING": {"PAID", "REJECTED"},
    "PAID": {"ACTIVATION_PENDING"},
    "ACTIVATION_PENDING": {"ACTIVE"},
    "ACTIVE": {"SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"},
    "SUSPENDED": {"ACTIVE", "CANCELLED"},
    "REJECTED": set(),
    "CANCELLED": set(),
    "EXPIRED": {"RENEWED", "CANCELLED"},
    # RENEWED was previously a dead end (empty set) -- a renewed contract could
    # never be renewed again the following year, nor suspended, cancelled, or
    # left to expire. A contract's term is expected to renew repeatedly over
    # its lifetime (energy contracts are typically 12/24-month terms), so
    # RENEWED gets the same onward transitions ACTIVE has -- it IS still an
    # in-force contract, "renewed" just describes how it got there.
    "RENEWED": {"SUSPENDED", "CANCELLED", "EXPIRED", "RENEWED"},
}

EVENT_FOR_TRANSITION: dict[tuple[str, str], str] = {
    ("DRAFT", "SUBMITTED"): "ContractSubmitted",
    ("UNDER_REVIEW", "APPROVED"): "ContractApproved",
    ("PAYMENT_PENDING", "PAID"): "PaymentConfirmed",
    ("ACTIVATION_PENDING", "ACTIVE"): "ContractActivated",
    ("ACTIVE", "CANCELLED"): "ContractCancelled",
    ("ACTIVE", "RENEWED"): "ContractRenewed",
    # Renewing a contract that is already in a RENEWED or EXPIRED state (a
    # later year's renewal, or reviving a lapsed contract) must trigger the
    # same recalculation as the first renewal -- same event name, so the
    # dispatcher's existing COMMISSION_TRIGGER_EVENTS handling needs no change.
    ("RENEWED", "RENEWED"): "ContractRenewed",
    ("EXPIRED", "RENEWED"): "ContractRenewed",
}


class InvalidTransitionError(Exception):
    pass


def assert_transition_allowed(from_status: str, to_status: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransitionError(f"Cannot transition contract from {from_status} to {to_status}")


def event_name_for(from_status: str, to_status: str) -> str | None:
    return EVENT_FOR_TRANSITION.get((from_status, to_status))
