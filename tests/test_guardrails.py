import pytest
from driftless_playwright.guardrails import GuardrailsInterceptor, BLOCKED_KEYWORDS


def test_guardrails_blocks_dark_pattern_upgrades():
    guard = GuardrailsInterceptor()
    
    # Test blocked trap keywords during cancellation
    trap_buttons = [
        "Switch to Annual Billing ($199/yr) & Save 20%!",
        "Upgrade to Premium",
        "Keep Membership",
        "Reactivate Plan Now",
        "Stay Subscribed and Save"
    ]
    
    for btn_text in trap_buttons:
        allowed, warning = guard.check_action_allowed("cancel", btn_text)
        assert not allowed, f"Should have blocked: {btn_text}"
        assert "Policy Guardrail Tripped" in warning

    # Test allowed cancellation buttons
    allowed_buttons = [
        "Confirm Cancellation",
        "No thanks, finish cancellation",
        "End My Subscription",
        "Yes, proceed with cancel"
    ]
    for btn_text in allowed_buttons:
        allowed, warning = guard.check_action_allowed("cancel", btn_text)
        assert allowed, f"Should have allowed: {btn_text}"
        assert warning is None


def test_guardrails_idempotency_lock():
    guard = GuardrailsInterceptor()
    endpoint = "/api/subscription/cancel"
    
    # First attempt: allowed
    can_commit, msg = guard.can_execute_commit_step(endpoint)
    assert can_commit is True

    # Record commit mutation success
    guard.record_mutation_success(endpoint)

    # Second attempt: blocked by idempotency lock
    can_commit, msg = guard.can_execute_commit_step(endpoint)
    assert can_commit is False
    assert "Idempotency Lock Active" in msg
