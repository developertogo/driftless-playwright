import pytest
import threading
import uvicorn
import time
from pathlib import Path
from playwright.async_api import async_playwright

from sandbox_portal.server import app
from sandbox_portal.mock_data import reset_mock_state
from driftless_playwright.action_agents import (
    DriftlessPlaywrightActionDispatcher,
    UserActionRequest,
    UserActionType
)
from driftless_playwright.observability import RunCaptureSession

SERVER_PORT = 8991
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


@pytest.mark.asyncio
async def test_action_agent_bill_audit():
    """Verify BillAuditActionAgent extracts and audits bill through unified dispatcher."""
    reset_mock_state()
    dispatcher = DriftlessPlaywrightActionDispatcher()

    request = UserActionRequest(
        request_id="req_audit_001",
        user_id="user_alex",
        merchant_id="streampulse",
        action_type=UserActionType.AUDIT_RECURRING_BILL,
        portal_url=f"{BASE_URL}/billing?version=v1",
        parameters={"historical_price": 19.99},
        enable_tracing=True
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        resp = await dispatcher.dispatch_action(request, browser)

        assert resp.success is True
        assert resp.action_type == UserActionType.AUDIT_RECURRING_BILL
        assert resp.audit_report is not None
        assert resp.audit_report.bill.monthly_amount == 22.99
        assert resp.audit_report.price_change_detected is True
        assert len(resp.observability_summary["spans"]) >= 2
        
        await browser.close()


@pytest.mark.asyncio
async def test_action_agent_swap_virtual_card():
    """Verify VirtualCardSwapActionAgent performs payment swap with observability spans."""
    reset_mock_state()
    dispatcher = DriftlessPlaywrightActionDispatcher()

    request = UserActionRequest(
        request_id="req_swap_002",
        user_id="user_alex",
        merchant_id="streampulse",
        action_type=UserActionType.SWAP_VIRTUAL_CARD,
        portal_url=f"{BASE_URL}/billing?version=v1",
        parameters={"card_token": "vault://card/virtual_4242"},
        enable_tracing=True
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        resp = await dispatcher.dispatch_action(request, browser)

        assert resp.success is True
        assert resp.action_type == UserActionType.SWAP_VIRTUAL_CARD
        assert resp.receipt is not None
        assert resp.receipt.network_confirmed is True
        assert "4242" in resp.user_facing_summary
        
        # Verify span timing observability
        summary = resp.observability_summary
        assert summary["total_spans"] >= 2
        assert summary["total_duration_sec"] > 0

        await browser.close()


@pytest.mark.asyncio
async def test_action_agent_cancel_with_trace_capture():
    """Verify SubscriptionCancelActionAgent generates Playwright trace archive."""
    reset_mock_state()
    dispatcher = DriftlessPlaywrightActionDispatcher()

    request = UserActionRequest(
        request_id="req_cancel_003",
        user_id="user_alex",
        merchant_id="streampulse",
        action_type=UserActionType.CANCEL_SUBSCRIPTION,
        portal_url=f"{BASE_URL}/billing?version=v1",
        enable_tracing=True
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        resp = await dispatcher.dispatch_action(request, browser)

        assert resp.success is True
        assert resp.action_type == UserActionType.CANCEL_SUBSCRIPTION
        assert resp.receipt is not None
        assert resp.receipt.success is True
        assert resp.receipt.terminal_reward == 10.0

        # Verify trace .zip was generated on disk
        trace_file = resp.receipt.trace_zip_path
        assert trace_file is not None
        assert Path(trace_file).exists()
        assert Path(trace_file).stat().st_size > 0

        await browser.close()


@pytest.mark.asyncio
async def test_action_agent_pause_subscription():
    """Verify SubscriptionPauseActionAgent freezes billing without deleting subscription."""
    reset_mock_state()
    dispatcher = DriftlessPlaywrightActionDispatcher()

    request = UserActionRequest(
        request_id="req_pause_004",
        user_id="user_alex",
        merchant_id="streampulse",
        action_type=UserActionType.PAUSE_SUBSCRIPTION,
        portal_url=f"{BASE_URL}/billing?version=v1",
        parameters={"pause_months": 2},
        enable_tracing=True
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        resp = await dispatcher.dispatch_action(request, browser)

        assert resp.success is True
        assert resp.action_type == UserActionType.PAUSE_SUBSCRIPTION
        assert resp.receipt is not None
        assert resp.receipt.success is True
        assert "paused" in resp.user_facing_summary.lower()
        assert "2 month" in resp.user_facing_summary

        await browser.close()
