from typing import Dict, Any, Optional
from playwright.async_api import Page


MOCK_VAULT_SECRETS = {
    "vault://cred/alex_streampulse": "SandboxAlexSecure2026!",
    "vault://card/virtual_4242": "4242424242424242",
}

MOCK_ACCOUNTS: Dict[str, Dict[str, Any]] = {
    "user_alex": {
        "email": "alex.chen@example.com",
        "password_vault_key": "vault://cred/alex_streampulse",
        "otp_secret_code": "482910",
        "subscription": {
            "merchant": "StreamPulse Ultra 4K",
            "monthly_price": 22.99,
            "status": "ACTIVE",
            "next_billing_date": "2026-11-01",
            "payment_method": "Visa •••• 1111",
        },
        "vaulted_replacement_card": {
            "card_token": "vault://card/virtual_4242",
            "last4": "4242",
            "exp": "08/29",
            "cvv": "884",
        },
    }
}


class SecretVault:
    """
    Zero-trust credential and payment card injector.
    Translates vault URIs (e.g. vault://cred/...) into real secrets directly
    inside the browser session, preventing plain secrets from leaking into LLM prompts or traces.
    """
    def __init__(self, secrets: Optional[Dict[str, str]] = None):
        self._secrets = dict(MOCK_VAULT_SECRETS)
        if secrets:
            self._secrets.update(secrets)

    def resolve(self, vault_key: str) -> str:
        """Resolves a vault URI to its plain secret."""
        if not vault_key.startswith("vault://"):
            return vault_key
        if vault_key not in self._secrets:
            raise KeyError(f"Vault secret not found for key: {vault_key}")
        return self._secrets[vault_key]

    def mask_text(self, text: str) -> str:
        """Replaces known plain secrets with safe masked placeholders."""
        masked = text
        for secret in self._secrets.values():
            if secret and secret in masked:
                masked = masked.replace(secret, "••••••••")
        return masked

    def get_sensitive_data_map(self) -> Dict[str, str]:
        """Provides a dictionary for browser-use sensitive_data parameter."""
        return {
            "alex.chen@example.com": "vault://cred/alex_email",
            "SandboxAlexSecure2026!": "vault://cred/alex_password",
            "4242424242424242": "vault://card/virtual_4242",
        }

    async def inject_card(self, page: Page, card_token: str = "vault://card/virtual_4242", exp: str = "08/29", cvv: str = "884") -> bool:
        """Injects payment card details into standard form fields."""
        card_num = self.resolve(card_token)
        try:
            # Try finding card input
            card_input = page.locator("input[name*='card'], input[id*='card'], input[autocomplete='cc-number'], input[placeholder*='Card']").first
            if await card_input.is_visible(timeout=1000):
                await card_input.fill(card_num)
            
            exp_input = page.locator("input[name*='exp'], input[id*='exp'], input[autocomplete='cc-exp']").first
            if await exp_input.is_visible(timeout=500):
                await exp_input.fill(exp)

            cvv_input = page.locator("input[name*='cvv'], input[name*='cvc'], input[autocomplete='cc-csc']").first
            if await cvv_input.is_visible(timeout=500):
                await cvv_input.fill(cvv)
            return True
        except Exception:
            return False
