import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger("driftless.merchant_tiering")


class MerchantAntiBotTier(str, Enum):
    TIER_1_STANDARD = "TIER_1_STANDARD"                  # Low/no anti-bot (direct Playwright, headless Chromium, standard residential egress)
    TIER_2_STEALTH_RESIDENTIAL = "TIER_2_STEALTH_RESIDENTIAL"  # Moderate anti-bot (Turnstile, Datadome, PerimeterX) -> stealth args, residential egress
    TIER_3_HEADFUL_HANDOFF = "TIER_3_HEADFUL_HANDOFF"    # Aggressive anti-bot / interactive challenges -> headful session, user-in-view handoff
    TIER_4_GRACEFUL_FALLBACK = "TIER_4_GRACEFUL_FALLBACK"  # Unsupported / phone-only / manual billers -> structured fallback package (no silent failure)


class BrowserExecutionConfig(BaseModel):
    headless: bool = True
    use_stealth: bool = False
    proxy_tier: str = "direct"  # "direct", "residential", "mobile"
    user_in_view_required: bool = False
    custom_args: List[str] = Field(default_factory=list)
    timeout_ms: int = 15000


class GracefulFallbackGuide(BaseModel):
    merchant_id: str
    merchant_name: str = ""
    portal_url: str
    reason: str
    action_type: str
    step_by_step_instructions: List[str]
    cancellation_phone_number: Optional[str] = None
    email_template: Optional[str] = None


class MerchantClassificationEngine:
    """
    Classifies merchants into anti-bot defense tiers and prescribes the exact execution stack,
    browser configuration, and network egress strategy. Also handles graceful fallbacks.
    """
    def __init__(self):
        # Known merchant database with anti-bot profiles
        self.catalog: Dict[str, Dict[str, Any]] = {
            "streampulse": {
                "name": "StreamPulse",
                "tier": MerchantAntiBotTier.TIER_1_STANDARD,
                "notes": "Standard SaaS billing portal with JSON APIs."
            },
            "netflix": {
                "name": "Netflix",
                "tier": MerchantAntiBotTier.TIER_2_STEALTH_RESIDENTIAL,
                "notes": "Moderate device fingerprinting; requires residential egress and stealth args."
            },
            "spotify": {
                "name": "Spotify",
                "tier": MerchantAntiBotTier.TIER_2_STEALTH_RESIDENTIAL,
                "notes": "Recaptcha v3 and behavioral analysis."
            },
            "gym_planet_fitness": {
                "name": "Planet Fitness",
                "tier": MerchantAntiBotTier.TIER_4_GRACEFUL_FALLBACK,
                "notes": "Requires in-person or certified mail cancellation.",
                "phone": "1-844-880-7180"
            },
            "newspaper_nyt": {
                "name": "The New York Times",
                "tier": MerchantAntiBotTier.TIER_3_HEADFUL_HANDOFF,
                "notes": "Aggressive bot walls & interactive retention chat; requires headful handoff."
            }
        }

    def classify(self, merchant_id: str) -> MerchantAntiBotTier:
        record = self.catalog.get(merchant_id.lower())
        if record:
            return record["tier"]
        # Default novel merchants to Tier 1 standard or Tier 2 stealth
        return MerchantAntiBotTier.TIER_1_STANDARD

    def get_browser_config(self, merchant_id: str) -> BrowserExecutionConfig:
        tier = self.classify(merchant_id)
        if tier == MerchantAntiBotTier.TIER_1_STANDARD:
            return BrowserExecutionConfig(
                headless=True,
                use_stealth=False,
                proxy_tier="direct",
                user_in_view_required=False,
                timeout_ms=15000
            )
        elif tier == MerchantAntiBotTier.TIER_2_STEALTH_RESIDENTIAL:
            return BrowserExecutionConfig(
                headless=True,
                use_stealth=True,
                proxy_tier="residential",
                user_in_view_required=False,
                custom_args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process"
                ],
                timeout_ms=30000
            )
        elif tier == MerchantAntiBotTier.TIER_3_HEADFUL_HANDOFF:
            return BrowserExecutionConfig(
                headless=False,
                use_stealth=True,
                proxy_tier="residential",
                user_in_view_required=True,
                custom_args=["--disable-blink-features=AutomationControlled"],
                timeout_ms=60000
            )
        else:
            # Tier 4 fallback
            return BrowserExecutionConfig(
                headless=True,
                use_stealth=False,
                proxy_tier="direct",
                user_in_view_required=False,
                timeout_ms=5000
            )

    def generate_graceful_fallback(
        self,
        merchant_id: str,
        action_type: str,
        portal_url: Optional[str] = None
    ) -> GracefulFallbackGuide:
        """
        Generates a non-silent fallback guide when a merchant cannot be automated directly.
        Ensures the consumer and banking partner receive an actionable, compliant path forward.
        """
        record = self.catalog.get(merchant_id.lower(), {})
        merchant_name = record.get("name", merchant_id.capitalize())
        phone = record.get("phone")

        instructions = [
            f"1. Log in to your {merchant_name} account at the merchant billing portal.",
            "2. Navigate to 'Account Settings' -> 'Subscription & Billing'.",
            f"3. Select '{action_type.replace('_', ' ').title()}'."
        ]
        if phone:
            instructions.append(f"Note: This merchant may require calling their support desk at {phone}.")

        return GracefulFallbackGuide(
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            portal_url=portal_url or f"https://www.{merchant_id}.com/account",
            reason="Merchant anti-bot policies or manual cancellation requirements prevent direct headless execution.",
            action_type=action_type,
            step_by_step_instructions=instructions,
            cancellation_phone_number=phone,
            email_template=(
                f"Subject: Request to {action_type.replace('_', ' ').lower()} my {merchant_name} account\n\n"
                f"Dear {merchant_name} Support Team,\n\n"
                f"Please process my request to {action_type.replace('_', ' ').lower()} my subscription effective immediately.\n"
                "Please confirm when completed and ensure no further recurring charges are billed to my card.\n\n"
                "Thank you."
            )
        )
