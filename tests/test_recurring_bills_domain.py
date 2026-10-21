import pytest
import threading
import uvicorn
import time
from playwright.async_api import async_playwright

from sandbox_portal.server import app
from sandbox_portal.mock_data import reset_mock_state
from driftless_playwright.recurring_bills import (
    RecurringBillDescriptor,
    BillAuditReport,
    RecurringBillAnalyzer
)
from driftless_playwright.vault import SecretVault

TEST_PORT = 8990
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture(scope="module", autouse=True)
def run_portal():
    config = uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    time.sleep(0.8)
    yield
    server.should_exit = True


@pytest.mark.asyncio
async def test_pillar1_identify_recurring_bill():
    """Driftless-Playwright Pillar 1: Identify recurring subscription from digital banking portal."""
    reset_mock_state()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{BASE_URL}/billing?version=v1")

        bill = await RecurringBillAnalyzer.identify_recurring_bill(page, merchant_id="streampulse")
        
        assert bill.merchant_id == "streampulse"
        assert bill.merchant_name == "StreamPulse Ultra 4K"
        assert bill.monthly_amount == 22.99
        assert bill.billing_cadence == "monthly"
        assert bill.next_billing_date == "2026-11-01"
        assert bill.is_active is True

        await browser.close()


def test_pillar2_understand_and_audit_bill():
    """Driftless-Playwright Pillar 2: Understand subscription costs, price hikes, and retention traps."""
    bill = RecurringBillDescriptor(
        merchant_id="streampulse",
        merchant_name="StreamPulse Ultra 4K",
        plan_name="Ultra 4K Stream",
        monthly_amount=22.99,
        billing_cadence="monthly",
        next_billing_date="2026-11-01",
        current_payment_method="Visa •••• 1111"
    )

    # Audit bill with historical price comparison ($19.99 -> $22.99)
    audit = RecurringBillAnalyzer.audit_bill(bill, historical_price=19.99)
    
    assert audit.price_change_detected is True
    assert audit.retention_risk_level == "HIGH"
    assert audit.suggested_action == "SWAP_CARD"
    assert "increased by +$3.00/mo" in audit.dark_patterns_detected[0]
    assert "StreamPulse Ultra 4K is billing $22.99/month" in audit.summary_for_bank_user


@pytest.mark.asyncio
async def test_pillar3_manage_virtual_card_swap():
    """Driftless-Playwright Pillar 3: Manage bill via 1-Click Driftless-Playwright Virtual Card Swap."""
    reset_mock_state()
    vault = SecretVault()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{BASE_URL}/billing?version=v1")

        # 1. Click 'Swap to Virtual Card' button
        swap_btn = page.locator("#btn-update-payment")
        assert await swap_btn.is_visible()
        await swap_btn.click()

        # 2. Inject vaulted replacement card from zero-trust vault
        card_num = vault.resolve("vault://card/virtual_4242")
        await page.locator("#card-number-input").fill(card_num)
        await page.locator("#card-exp-input").fill("08/29")
        await page.locator("#card-cvv-input").fill("884")

        # 3. Submit card update
        await page.locator("#btn-submit-payment").click()
        await page.wait_for_load_state("networkidle", timeout=1500)

        # 4. Verify DOM reflects Driftless-Playwright Virtual Card
        disp = page.locator("#current-payment-display")
        updated_text = await disp.inner_text()
        assert "Driftless-Playwright Virtual Card" in updated_text

        await browser.close()
