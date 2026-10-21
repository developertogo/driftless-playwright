"""
driftless_playwright.agents
Explicit definitions for the 3-tier self-healing agent stack:
1. Tier 1: Tier1SemanticAgent (nomic-embed-text + pHash Fast Healer, <100ms, 0 LLM tokens)
2. Tier 2: Tier2DOMAgent (Scoped browser-use Micro-Agent Bridge, use_vision=False)
3. Tier 3: Tier3VisionAgent (Set-of-Marks Multimodal Vision Agent with ROI cropping, use_vision=True)
"""

from typing import Optional, List, Dict, Any, Tuple
from playwright.async_api import Page, Locator
from driftless_playwright.schemas import StepAnchor
from driftless_playwright.locator_waterfall import LocatorResolver
from driftless_playwright.agent_bridge import ScopedAgentBridge, AgentBridgeResult
from driftless_playwright.guardrails import GuardrailsInterceptor


class Tier1SemanticAgent:
    """
    Tier 1 Agent: Fast Semantic (nomic-embed-text) + Visual Patch Repair.
    - Latency: <100ms
    - LLM Chat Tokens: 0
    - Logic: Scans visible interactive elements and scores via 768-dim cosine similarity,
             aria-role matching, pHash visual distance, and bounding box proximity.
    """
    def __init__(self, page: Page):
        self.page = page
        self.resolver = LocatorResolver(page)

    async def heal(self, step: StepAnchor, screenshot_bytes: Optional[bytes] = None) -> Optional[Tuple[Locator, str, float]]:
        return await self.resolver.tier1_semantic_healing(step, screenshot_bytes)


class Tier2DOMAgent:
    """
    Tier 2 Agent: Scoped browser-use Micro-Agent Bridge.
    - Model: qwen2.5vl:7b (resident in local Ollama or cloud frontier via OpenAI API)
    - Mode: use_vision=False (pure DOM and text grounding)
    - Guardrails: Active policy interceptor blocking annual upgrade traps and retention dark patterns.
    """
    def __init__(self, guardrails: Optional[GuardrailsInterceptor] = None):
        self.bridge = ScopedAgentBridge(guardrails or GuardrailsInterceptor())

    async def recover(self, page: Page, step: StepAnchor, workflow_type: str = "cancel") -> AgentBridgeResult:
        return await self.bridge.recover_step(
            page=page,
            step=step,
            workflow_type=workflow_type,
            force_tier3_vision=False
        )


class Tier3VisionAgent:
    """
    Tier 3 Agent: On-Demand Set-of-Marks (SoM) Vision Fallback Agent.
    - Model: qwen2.5vl:7b (same hot-loaded resident model, 0ms model swap)
    - Mode: use_vision=True (Set-of-Marks visual bounding boxes enabled)
    - Optimization: Bounding box ROI cropping to reduce vision token consumption: (W * H) / (28 * 28).
    """
    def __init__(self, guardrails: Optional[GuardrailsInterceptor] = None):
        self.bridge = ScopedAgentBridge(guardrails or GuardrailsInterceptor())

    async def recover(self, page: Page, step: StepAnchor, workflow_type: str = "cancel") -> AgentBridgeResult:
        return await self.bridge.recover_step(
            page=page,
            step=step,
            workflow_type=workflow_type,
            force_tier3_vision=True
        )
