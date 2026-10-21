from typing import Optional, Set, Dict, Any
from driftless_playwright.schemas import FailureCode


BLOCKED_KEYWORDS = [
    "upgrade",
    "annual plan",
    "buy now",
    "add-on",
    "reactivate",
    "switch to annual",
    "save 20%",
    "keep membership",
    "stay subscribed"
]


class GuardrailViolation(Exception):
    def __init__(self, message: str, failure_code: FailureCode = FailureCode.POLICY_GUARDRAIL_TRIPPED):
        super().__init__(message)
        self.failure_code = failure_code


class GuardrailsInterceptor:
    """
    Pre-action policy interceptor and idempotency guard.
    Blocks dark patterns, unwanted subscription upgrades, and duplicate mutation calls.
    """
    def __init__(self):
        self._successful_mutations: Set[str] = set()
        self._tripped_violations: list[str] = []

    def check_action_allowed(
        self,
        workflow_type: str,
        element_text: str,
        element_attrs: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validates whether clicking/acting on an element violates safety policies.
        When workflow_type == 'cancel', buttons that retain or upgrade subscriptions are strictly blocked.
        """
        combined_text = (element_text or "").strip().lower()
        if element_attrs:
            for k, v in element_attrs.items():
                if isinstance(v, str):
                    combined_text += " " + v.lower()

        if workflow_type.lower() in ["cancel", "subscription_cancel", "cancellation"]:
            for kw in BLOCKED_KEYWORDS:
                if kw in combined_text:
                    warning = f"Policy Guardrail Tripped: Action targeting '{element_text}' contains prohibited retention/upgrade keyword '{kw}'."
                    self._tripped_violations.append(warning)
                    return False, warning

        return True, None

    def record_mutation_success(self, endpoint: str) -> None:
        """Records an endpoint that has successfully executed a 200/201/204 mutation."""
        self._successful_mutations.add(endpoint.strip().rstrip("/"))

    def is_mutation_already_committed(self, endpoint: str) -> bool:
        """Returns True if the endpoint mutation has already succeeded."""
        cleaned = endpoint.strip().rstrip("/")
        for comm in self._successful_mutations:
            if cleaned.endswith(comm) or comm.endswith(cleaned):
                return True
        return False

    def can_execute_commit_step(self, endpoint: str) -> tuple[bool, Optional[str]]:
        """
        Idempotency Lock: If a commit step already triggered a 200 OK mutation,
        block duplicate clicks on retry and signal immediate jump to verification.
        """
        if self.is_mutation_already_committed(endpoint):
            msg = f"Idempotency Lock Active: Mutation on '{endpoint}' has already committed successfully (200 OK). Skipping duplicate invocation."
            return False, msg
        return True, None

    def reset(self) -> None:
        """Resets idempotency and violation tracking."""
        self._successful_mutations.clear()
        self._tripped_violations.clear()
