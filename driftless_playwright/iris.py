import logging
import asyncio
from typing import Optional, Dict, Any, List
from playwright.async_api import Browser, async_playwright

from driftless_playwright.action_agents import (
    DriftlessPlaywrightActionDispatcher,
    UserActionRequest,
    UserActionResponse,
    UserActionType
)
from driftless_playwright.merchant_tiering import (
    MerchantClassificationEngine,
    MerchantAntiBotTier,
    BrowserExecutionConfig,
    GracefulFallbackGuide
)
from driftless_playwright.eval_gates import (
    PlaybookEvalGate,
    EvalGateResult,
    EvalPromotionDecision
)
from driftless_playwright.observability import RunCaptureSession
from driftless_playwright.telemetry import TelemetryFlightRecorder

logger = logging.getLogger("driftless.iris")


class IrisActionEngine:
    """
    IRIS: Driftless-Playwright's Flagship Agentic Action Capability.
    
    Executes live merchant actions (cancellations, virtual card switching, bill savings,
    pausing, plan changes) on behalf of banking consumers directly inside their banking app.
    
    Key Capabilities:
    1. Owns the oscillation between agentic execution on novel merchants and deterministic playbooks.
    2. Enforces Eval Gates ensuring Iris NEVER reports a completed action without verifiable proof.
    3. Merchant classification & tiering against anti-bot defenses (with non-silent graceful fallbacks).
    4. Headful browser session-handoff preserving user authentication.
    5. Full OpenTelemetry run capture, Playwright .zip tracing, and flight-recorder metrics.
    """
    def __init__(
        self,
        classifier: Optional[MerchantClassificationEngine] = None,
        dispatcher: Optional[DriftlessPlaywrightActionDispatcher] = None,
        eval_gate: Optional[PlaybookEvalGate] = None
    ):
        self.classifier = classifier or MerchantClassificationEngine()
        self.dispatcher = dispatcher or DriftlessPlaywrightActionDispatcher()
        self.eval_gate = eval_gate or PlaybookEvalGate()
        self.flight_recorder = TelemetryFlightRecorder.get_instance()

    def classify_merchant(self, merchant_id: str) -> MerchantAntiBotTier:
        """Determines anti-bot defense tier and execution strategy."""
        return self.classifier.classify(merchant_id)

    def get_browser_config(self, merchant_id: str) -> BrowserExecutionConfig:
        """Determines browser launch parameters, stealth plugins, and proxies per merchant tier."""
        return self.classifier.get_browser_config(merchant_id)

    async def execute_action(
        self,
        request: UserActionRequest,
        browser: Optional[Browser] = None
    ) -> UserActionResponse:
        """
        Executes a user-requested action across merchant web experiences.
        """
        tier = self.classify_merchant(request.merchant_id)
        logger.info(f"[Iris] Executing {request.action_type.value} for {request.merchant_id} under {tier.value}")

        # If merchant requires manual / out-of-band handling (Tier 4), generate a graceful fallback
        if tier == MerchantAntiBotTier.TIER_4_GRACEFUL_FALLBACK:
            fallback = self.classifier.generate_graceful_fallback(
                merchant_id=request.merchant_id,
                action_type=request.action_type.value,
                portal_url=request.portal_url
            )
            display_name = fallback.merchant_name or fallback.merchant_id.title()
            return UserActionResponse(
                request_id=request.request_id,
                action_type=request.action_type,
                success=False,
                observability_summary={"tier": tier.value, "fallback_generated": True},
                user_facing_summary=(
                    f"{display_name} requires direct verification: {fallback.reason} "
                    f"Follow instructions: {fallback.step_by_step_instructions[0]}"
                )
            )

        config = self.get_browser_config(request.merchant_id)

        # Execute using provided browser or launch according to tier configuration
        if browser:
            return await self.dispatcher.dispatch_action(
                request=request,
                browser=browser,
                headless=config.headless
            )
        else:
            async with async_playwright() as p:
                launch_args = list(config.custom_args)
                b = await p.chromium.launch(
                    headless=config.headless,
                    args=launch_args
                )
                try:
                    return await self.dispatcher.dispatch_action(
                        request=request,
                        browser=b,
                        headless=config.headless
                    )
                finally:
                    await b.close()

    def evaluate_run_for_promotion(
        self,
        response: UserActionResponse,
        base_playbook: Optional[Any] = None,
        healed_actions: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[EvalGateResult]:
        """
        Eval Gate: Decides if an agentic trajectory is trusted enough to become
        a deterministic instruction set (Playbook v2).
        """
        if not response.receipt:
            return None
        return self.eval_gate.evaluate_and_promote(
            receipt=response.receipt,
            base_playbook=base_playbook,
            healed_actions=healed_actions
        )


# Global Iris singleton for direct imports
Iris = IrisActionEngine
