"""driftless-playwright core package."""
from driftless_playwright.schemas import Playbook, StepAnchor, ExecutionReceipt, FailureCode, NetworkMutationRecord
from driftless_playwright.router import ResilientStepOrchestrator, PlaybookRouter
from driftless_playwright.locator_waterfall import LocatorResolver
from driftless_playwright.guardrails import GuardrailsInterceptor
from driftless_playwright.verifier import VerificationJudge
from driftless_playwright.compiler import PlaybookCompiler
from driftless_playwright.agents import Tier1SemanticAgent, Tier2DOMAgent, Tier3VisionAgent
from driftless_playwright.recurring_bills import RecurringBillDescriptor, BillAuditReport, RecurringBillAnalyzer
from driftless_playwright.observability import RunCaptureSession, ExecutionSpan
from driftless_playwright.action_agents import (
    UserActionType,
    UserActionRequest,
    UserActionResponse,
    SubscriptionCancelActionAgent,
    VirtualCardSwapActionAgent,
    BillAuditActionAgent,
    SubscriptionPauseActionAgent,
    BillSavingsActionAgent,
    PlanChangeActionAgent,
    DriftlessPlaywrightActionDispatcher
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
from driftless_playwright.iris import Iris, IrisActionEngine

__all__ = [
    # Core Schemas & Execution
    "Playbook",
    "StepAnchor",
    "ExecutionReceipt",
    "FailureCode",
    "NetworkMutationRecord",
    "ResilientStepOrchestrator",
    "PlaybookRouter",
    "LocatorResolver",
    "GuardrailsInterceptor",
    "VerificationJudge",
    "PlaybookCompiler",
    # Agents
    "Tier1SemanticAgent",
    "Tier2DOMAgent",
    "Tier3VisionAgent",
    # Driftless-Playwright Domain & Observability
    "RecurringBillDescriptor",
    "BillAuditReport",
    "RecurringBillAnalyzer",
    "RunCaptureSession",
    "ExecutionSpan",
    # User Action Agents
    "UserActionType",
    "UserActionRequest",
    "UserActionResponse",
    "SubscriptionCancelActionAgent",
    "VirtualCardSwapActionAgent",
    "BillAuditActionAgent",
    "SubscriptionPauseActionAgent",
    "BillSavingsActionAgent",
    "PlanChangeActionAgent",
    "DriftlessPlaywrightActionDispatcher",
    # Iris Engine, Anti-Bot Tiering & Eval Gates
    "Iris",
    "IrisActionEngine",
    "MerchantClassificationEngine",
    "MerchantAntiBotTier",
    "BrowserExecutionConfig",
    "GracefulFallbackGuide",
    "PlaybookEvalGate",
    "EvalGateResult",
    "EvalPromotionDecision"
]
