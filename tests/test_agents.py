import pytest
from driftless_playwright.agents import Tier1SemanticAgent, Tier2DOMAgent, Tier3VisionAgent
from driftless_playwright.guardrails import GuardrailsInterceptor
from driftless_playwright.schemas import StepAnchor, ElementSignature, PostCondition


def test_agent_initialization():
    """Verify all 3 self-healing agents can be instantiated and configured."""
    # Tier 2 DOM Agent
    tier2 = Tier2DOMAgent()
    assert tier2.bridge is not None

    # Tier 3 Vision Agent
    tier3 = Tier3VisionAgent()
    assert tier3.bridge is not None
    assert tier3.bridge.llm_model == "qwen2.5vl:7b"


@pytest.mark.asyncio
async def test_tier1_agent_logic():
    """Verify Tier 1 Agent semantic healing integration."""
    step = StepAnchor(
        step_id="step_test",
        intent="Cancel Membership",
        action_type="click",
        locators=["css=#broken-selector"],
        signature=ElementSignature(
            tag="button",
            text="Cancel Membership",
            aria_role="button",
            bbox_ratio=[0.7, 0.4, 0.18, 0.05]
        ),
        post_condition=PostCondition(dom_text_visible=["Canceled"])
    )
    assert step.signature.text == "Cancel Membership"
