import copy
from typing import Dict, Any

_INITIAL_MOCK_ACCOUNTS: Dict[str, Dict[str, Any]] = {
    "user_alex": {
        "email": "alex.chen@example.com",
        "password_vault_key": "vault://cred/alex_streampulse",
        "password_plain": "SandboxAlexSecure2026!",
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

CURRENT_ACCOUNTS: Dict[str, Dict[str, Any]] = copy.deepcopy(_INITIAL_MOCK_ACCOUNTS)


def reset_mock_state() -> None:
    """Resets all mock accounts to active initial state."""
    global CURRENT_ACCOUNTS
    CURRENT_ACCOUNTS = copy.deepcopy(_INITIAL_MOCK_ACCOUNTS)


def get_account(user_id: str = "user_alex") -> Dict[str, Any]:
    return CURRENT_ACCOUNTS.get(user_id, CURRENT_ACCOUNTS["user_alex"])
