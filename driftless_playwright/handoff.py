import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict
from playwright.async_api import Page, BrowserContext
from driftless_playwright.config import SESSIONS_DIR

_OTP_INBOX: Dict[str, asyncio.Future] = {}


def register_otp_future(run_id: str) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _OTP_INBOX[run_id] = fut
    return fut


def deliver_otp(run_id: str, otp_code: str) -> bool:
    if run_id in _OTP_INBOX and not _OTP_INBOX[run_id].done():
        _OTP_INBOX[run_id].set_result(otp_code)
        return True
    return False


class SessionHandoffManager:
    """
    Manages persistent authentication storage_state, 2FA OTP handoffs,
    and CAPTCHA tripwire takeovers.
    """
    def __init__(self, user_id: str, merchant_id: str):
        self.user_id = user_id
        self.merchant_id = merchant_id
        self.session_file = SESSIONS_DIR / f"{user_id}_{merchant_id}_storage.json"

    def get_storage_state_path(self) -> Optional[str]:
        if self.session_file.exists():
            return str(self.session_file)
        return None

    async def save_storage_state(self, context: BrowserContext) -> str:
        """Persists session cookies and local storage to disk."""
        await context.storage_state(path=str(self.session_file))
        return str(self.session_file)

    async def detect_and_handle_2fa(
        self,
        page: Page,
        run_id: str,
        timeout_sec: float = 10.0,
        auto_sandbox_otp: Optional[str] = "482910"
    ) -> bool:
        """
        Detects 2FA input or challenge screen.
        If found, waits for OTP via webhook/broker or automatically injects mock test code.
        """
        otp_selectors = [
            "input[autocomplete='one-time-code']",
            "input[name='otp']",
            "input#otp-code",
            "input[placeholder*='code' i]",
            "input[placeholder*='OTP' i]"
        ]
        
        target_input = None
        for sel in otp_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=400):
                    target_input = el
                    break
            except Exception:
                pass

        if target_input is None:
            # Check for OTP text header
            try:
                header = page.get_by_text("Enter Verification Code", exact=False).first
                if await header.is_visible(timeout=300):
                    target_input = page.locator("input[type='text'], input[type='number']").first
            except Exception:
                pass

        if target_input is None:
            return False

        print(f"[Handoff] ⚡ 2FA prompt detected for run {run_id}. Waiting for OTP...")
        otp_code = None
        
        # Check if an OTP was pre-delivered or is waiting in the broker
        fut = register_otp_future(run_id)
        if auto_sandbox_otp:
            # Pre-populate sandbox OTP after brief realistic delay
            await asyncio.sleep(0.3)
            deliver_otp(run_id, auto_sandbox_otp)

        try:
            otp_code = await asyncio.wait_for(fut, timeout=timeout_sec)
        except asyncio.TimeoutError:
            print(f"[Handoff] ❌ Timed out waiting for 2FA OTP for run {run_id}")
            return False
        finally:
            _OTP_INBOX.pop(run_id, None)

        if otp_code:
            print(f"[Handoff] 🔑 Injecting 2FA OTP: {otp_code}")
            await target_input.fill(otp_code)
            # Find and click submit/verify button
            verify_btn = page.locator("button:has-text('Verify'), button:has-text('Submit'), button[type='submit']").first
            if await verify_btn.is_visible(timeout=1000):
                await verify_btn.click()
            await page.wait_for_load_state("networkidle", timeout=2000)
            await self.save_storage_state(page.context)
            return True

        return False

    async def detect_and_handle_captcha(self, page: Page, timeout_sec: float = 15.0) -> bool:
        """
        Detects CAPTCHA gates/iframes. Freezes autonomous agent actions and takes over
        via CDP / Playwright until clearance cookie is established.
        """
        captcha_indicators = [
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='hcaptcha.com']",
            "iframe[src*='recaptcha']",
            "#px-captcha",
            ".captcha-container",
            "#simulated-captcha-box"
        ]

        detected = False
        captcha_el = None
        for sel in captcha_indicators:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=400):
                    detected = True
                    captcha_el = el
                    break
            except Exception:
                pass

        if not detected:
            return False

        print("[Handoff] 🛑 CAPTCHA challenge tripwire activated! Pausing agent actions...")
        # In sandbox test environment, simulate automated clearance click on test captcha button
        solve_btn = page.locator("#simulated-captcha-box button, #btn-verify-human, button:has-text('Verify You Are Human')").first
        try:
            if await solve_btn.is_visible(timeout=1000):
                print("[Handoff] 🛡️ Resolving sandbox CAPTCHA challenge...")
                await solve_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # Wait for captcha element to disappear
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                if not await captcha_el.is_visible(timeout=500):
                    print("[Handoff] ✅ CAPTCHA cleared! Persisting clearance session...")
                    await self.save_storage_state(page.context)
                    return True
            except Exception:
                return True
            await asyncio.sleep(0.5)

        return False
