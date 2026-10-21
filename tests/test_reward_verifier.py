import pytest
from driftless_playwright.verifier import VerificationJudge, MutationRecord


def test_step_reward_calculation():
    judge = VerificationJudge(merchant_id="test_merchant", workflow_type="cancel")
    
    # Fast successful step
    r1 = judge.calculate_step_reward(progressed_to_post_condition=True, latency_sec=0.5, dom_validation_error=False, dom_hash="hash_1")
    assert r1 == 1.0

    # Slow step with latency penalty
    r2 = judge.calculate_step_reward(progressed_to_post_condition=True, latency_sec=2.5, dom_validation_error=False, dom_hash="hash_2")
    assert r2 < 1.0

    # Step with DOM validation error
    r3 = judge.calculate_step_reward(progressed_to_post_condition=False, latency_sec=0.2, dom_validation_error=True, dom_hash="hash_3")
    assert r3 == -0.5

    # Repeated DOM state hash penalty
    r4 = judge.calculate_step_reward(progressed_to_post_condition=True, latency_sec=0.1, dom_validation_error=False, dom_hash="hash_1")
    assert r4 == 0.0  # +1.0 - 1.0 (repeated)


def test_receipt_generation():
    judge = VerificationJudge(merchant_id="streampulse", workflow_type="cancel")
    judge.step_rewards = [1.0, 0.8]
    details = {
        "network_confirmed": True,
        "dom_confirmed": True,
        "confirmation_text": "Status: Canceled"
    }
    receipt = judge.build_receipt(
        run_id="run_test_123",
        is_success=True,
        terminal_reward=10.0,
        details=details,
        healed_steps=["step_click_cancel"],
        compiled_version=2,
        llm_tokens=0
    )
    assert receipt.success is True
    assert receipt.terminal_reward == 10.0
    assert receipt.total_reward == 11.8
    assert receipt.network_confirmed is True
    assert receipt.healed_steps == ["step_click_cancel"]
