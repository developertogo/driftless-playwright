import pytest
import threading
import uvicorn
import time
from playwright.async_api import async_playwright

from sandbox_portal.server import app
from sandbox_portal.mock_data import reset_mock_state
from driftless_playwright import (
    Iris,
    IrisActionEngine,
    MerchantClassificationEngine,
    MerchantAntiBotTier,
    PlaybookEvalGate,
    EvalPromotionDecision,
    ExecutionReceipt,
    UserActionRequest,
    UserActionType,
    DriftlessPlaywrightActionDispatcher
)
from driftless_playwright.schemas import NetworkMutationRecord

SERVER_PORT = 8994
BASE_URL = f"http://127.0.0.1:{SERVER_PORT}"


@pytest.fixture(scope="module", autouse=True)
def run_portal():
    config = uvicorn.Config(app, host="127.0.0.1", port=SERVER_PORT, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.8)
    yield
    server.should_exit = True


def test_merchant_classification_and_tiering():
    classifier = MerchantClassificationEngine()
    
    # Tier 1 standard
    assert classifier.classify("streampulse") == MerchantAntiBotTier.TIER_1_STANDARD
    config_t1 = classifier.get_browser_config("streampulse")
    assert config_t1.headless is True
    assert config_t1.use_stealth is False

    # Tier 2 stealth residential
    assert classifier.classify("netflix") == MerchantAntiBotTier.TIER_2_STEALTH_RESIDENTIAL
    config_t2 = classifier.get_browser_config("netflix")
    assert config_t2.use_stealth is True
    assert config_t2.proxy_tier == "residential"

    # Tier 3 headful handoff
    assert classifier.classify("newspaper_nyt") == MerchantAntiBotTier.TIER_3_HEADFUL_HANDOFF
    config_t3 = classifier.get_browser_config("newspaper_nyt")
    assert config_t3.user_in_view_required is True

    # Tier 4 graceful fallback
    assert classifier.classify("gym_planet_fitness") == MerchantAntiBotTier.TIER_4_GRACEFUL_FALLBACK
    fallback = classifier.generate_graceful_fallback("gym_planet_fitness", "CANCEL_SUBSCRIPTION")
    assert fallback.merchant_id == "gym_planet_fitness"
    assert "Planet Fitness" in fallback.step_by_step_instructions[0]
    assert fallback.cancellation_phone_number is not None
    assert "Dear Planet Fitness Support Team" in fallback.email_template


def test_playbook_eval_gate_promotion_decision():
    gate = PlaybookEvalGate(min_reward_threshold=8.0)

    # 1. Trusted receipt -> PROMOTED
    trusted_receipt = ExecutionReceipt(
        run_id="run_promote_01",
        merchant_id="streampulse",
        workflow_type="cancel_subscription",
        success=True,
        terminal_reward=10.0,
        total_reward=10.0,
        verified=True,
        network_confirmed=True,
        dom_confirmed=True,
        visual_confirmed=True,
        network_mutations=[
            NetworkMutationRecord(
                url="http://127.0.0.1:8000/api/subscription/cancel",
                method="POST",
                response_status=200,
                latency_ms=120.0
            )
        ]
    )
    result = gate.evaluate_and_promote(receipt=trusted_receipt, guardrail_violations=0)
    assert result.decision == EvalPromotionDecision.PROMOTED
    assert result.has_network_proof is True
    assert result.has_dom_proof is True

    # 2. Guardrail tripped -> REJECTED
    result_guardrail = gate.evaluate_and_promote(receipt=trusted_receipt, guardrail_violations=1)
    assert result_guardrail.decision == EvalPromotionDecision.QUARANTINED or result_guardrail.decision == EvalPromotionDecision.REJECTED

    # 3. Failed verification receipt (never report cancellation it didn't complete) -> REJECTED
    unverified_receipt = ExecutionReceipt(
        run_id="run_unverified_02",
        merchant_id="streampulse",
        workflow_type="cancel_subscription",
        success=False,
        terminal_reward=0.0,
        total_reward=0.0,
        verified=False,
        network_confirmed=False,
        dom_confirmed=False
    )
    result_unverified = gate.evaluate_and_promote(receipt=unverified_receipt)
    assert result_unverified.decision == EvalPromotionDecision.REJECTED


@pytest.mark.asyncio
async def test_iris_action_engine_tier4_fallback():
    iris = IrisActionEngine()
    request = UserActionRequest(
        request_id="req_fallback_01",
        user_id="user_alex",
        merchant_id="gym_planet_fitness",
        action_type=UserActionType.CANCEL_SUBSCRIPTION
    )

    response = await iris.execute_action(request)
    assert response.success is False
    assert "Planet Fitness requires direct verification" in response.user_facing_summary
    assert response.observability_summary.get("fallback_generated") is True


@pytest.mark.asyncio
async def test_iris_action_engine_bill_savings_and_plan_change():
    reset_mock_state()

    iris = IrisActionEngine()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            # 1. Test Bill Savings
            savings_req = UserActionRequest(
                request_id="req_savings_01",
                merchant_id="streampulse",
                action_type=UserActionType.BILL_SAVINGS,
                portal_url=f"{BASE_URL}/billing?version=v1",
                parameters={"promo_code": "DRIFTLESS20", "discount_amount": 5.0}
            )
            resp_savings = await iris.execute_action(savings_req, browser=browser)
            assert resp_savings.success is True
            assert resp_savings.receipt is not None
            assert resp_savings.receipt.network_confirmed is True
            assert "Saved $5.00/mo" in resp_savings.user_facing_summary

            # 2. Test Plan Change (Downgrade to Basic)
            plan_req = UserActionRequest(
                request_id="req_plan_01",
                merchant_id="streampulse",
                action_type=UserActionType.CHANGE_PLAN,
                portal_url=f"{BASE_URL}/billing?version=v1",
                parameters={"target_plan": "Basic", "target_price": 9.99}
            )
            resp_plan = await iris.execute_action(plan_req, browser=browser)
            assert resp_plan.success is True
            assert resp_plan.receipt is not None
            assert "Basic" in resp_plan.receipt.confirmation_text
            assert "Successfully changed plan" in resp_plan.user_facing_summary
        finally:
            await browser.close()
