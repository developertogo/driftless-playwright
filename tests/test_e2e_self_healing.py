import asyncio
import json
import threading
import uvicorn
import pytest
from pathlib import Path
from playwright.async_api import async_playwright

from sandbox_portal.server import app
from sandbox_portal.mock_data import reset_mock_state
from driftless_playwright.schemas import Playbook
from driftless_playwright.router import ResilientStepOrchestrator, PlaybookRouter
from driftless_playwright.verifier import VerificationJudge
from driftless_playwright.guardrails import GuardrailsInterceptor
from driftless_playwright.handoff import SessionHandoffManager
from driftless_playwright.config import PLAYBOOKS_DIR

SERVER_PORT = 8899
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"


@pytest.fixture(scope="module", autouse=True)
def run_sandbox_server():
    """Runs FastAPI mock portal on a dedicated port in background thread."""
    config = uvicorn.Config(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import time
    time.sleep(0.8)
    yield
    server.should_exit = True


@pytest.mark.asyncio
async def test_act1_baseline_v1_fast_path():
    """Act 1: Baseline deterministic fast path (0 LLM tokens, ~1.8s)."""
    reset_mock_state()
    pb_path = PLAYBOOKS_DIR / "merchant_billing_v1.json"
    with open(pb_path, "r", encoding="utf-8") as f:
        playbook = Playbook.model_validate_json(f.read())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{SERVER_URL}/billing?version=v1")

        judge = VerificationJudge(merchant_id="streampulse", workflow_type="cancel")
        orchestrator = ResilientStepOrchestrator(page, judge)

        receipt = await orchestrator.execute_playbook(playbook, run_id="test_act1_run")
        assert receipt.success is True
        assert receipt.terminal_reward == 10.0
        assert receipt.network_confirmed is True
        assert receipt.dom_confirmed is True
        assert receipt.llm_tokens_used == 0
        assert len(receipt.healed_steps) == 0

        await browser.close()


@pytest.mark.asyncio
async def test_act2_tier1_semantic_healing():
    """Act 2: Cosmetic UI drift healed by Tier 1 (nomic-embed-text) in <100ms."""
    reset_mock_state()
    pb_path = PLAYBOOKS_DIR / "merchant_billing_v1.json"
    with open(pb_path, "r", encoding="utf-8") as f:
        playbook = Playbook.model_validate_json(f.read())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # v2_minor has 'End My Subscription' instead of 'Cancel Membership'
        await page.goto(f"{SERVER_URL}/billing?version=v2_minor")

        judge = VerificationJudge(merchant_id="streampulse", workflow_type="cancel")
        orchestrator = ResilientStepOrchestrator(page, judge)

        receipt = await orchestrator.execute_playbook(playbook, run_id="test_act2_run")
        assert receipt.success is True
        assert receipt.terminal_reward == 10.0
        assert receipt.network_confirmed is True
        assert receipt.dom_confirmed is True
        assert receipt.llm_tokens_used == 0
        assert "step_click_cancel" in receipt.healed_steps

        await browser.close()


@pytest.mark.asyncio
async def test_act3_and_act4_tier2_healing_and_distillation():
    """Act 3: Dark pattern retention trap healed by Tier 2 and compiled into v2."""
    reset_mock_state()
    pb_path = PLAYBOOKS_DIR / "merchant_billing_v1.json"
    with open(pb_path, "r", encoding="utf-8") as f:
        playbook = Playbook.model_validate_json(f.read())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # v2_dark_pattern has modal survey + upgrade trap button
        await page.goto(f"{SERVER_URL}/billing?version=v2_dark_pattern")

        judge = VerificationJudge(merchant_id="streampulse", workflow_type="cancel")
        orchestrator = ResilientStepOrchestrator(page, judge)

        receipt = await orchestrator.execute_playbook(playbook, run_id="test_act3_run")
        assert receipt.success is True
        assert receipt.terminal_reward == 10.0
        assert receipt.network_confirmed is True
        assert receipt.dom_confirmed is True
        assert receipt.compiled_playbook_version == 2

        # Check compiled playbook exists on disk
        v2_path = PLAYBOOKS_DIR / "streampulse_v2.json"
        assert v2_path.exists()
        with open(v2_path, "r", encoding="utf-8") as f:
            v2_pb = Playbook.model_validate_json(f.read())
            assert v2_pb.version == 2
            assert len(v2_pb.steps) >= len(playbook.steps)

        # Act 4: Run compiled v2 playbook deterministically on repeated v2_dark_pattern UI (0 tokens)
        reset_mock_state()
        await page.goto(f"{SERVER_URL}/billing?version=v2_dark_pattern")
        
        judge4 = VerificationJudge(merchant_id="streampulse", workflow_type="cancel")
        orchestrator4 = ResilientStepOrchestrator(page, judge4)
        receipt4 = await orchestrator4.execute_playbook(v2_pb, run_id="test_act4_run")
        assert receipt4.success is True
        assert receipt4.terminal_reward == 10.0
        assert receipt4.network_confirmed is True
        assert receipt4.llm_tokens_used == 0

        await browser.close()


@pytest.mark.asyncio
async def test_2fa_and_captcha_handoff():
    """Verify 2FA OTP handoff and CAPTCHA tripwire handlers."""
    reset_mock_state()
    handoff = SessionHandoffManager(user_id="user_alex", merchant_id="streampulse")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. Test 2FA handoff
        await page.goto(f"{SERVER_URL}/billing?version=v1&user_2fa=true")
        handled_2fa = await handoff.detect_and_handle_2fa(page, run_id="run_2fa_test", auto_sandbox_otp="482910")
        assert handled_2fa is True

        # 2. Test CAPTCHA tripwire
        await page.goto(f"{SERVER_URL}/billing?version=v1&captcha=true")
        handled_captcha = await handoff.detect_and_handle_captcha(page)
        assert handled_captcha is True

        await browser.close()
