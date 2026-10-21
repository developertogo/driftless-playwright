from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class FailureCode(str, Enum):
    NONE = "NONE"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    HANDOFF_TIMEOUT_2FA = "HANDOFF_TIMEOUT_2FA"
    CAPTCHA_BLOCKED = "CAPTCHA_BLOCKED"
    POLICY_GUARDRAIL_TRIPPED = "POLICY_GUARDRAIL_TRIPPED"
    UI_DRIFT_UNRECOVERABLE = "UI_DRIFT_UNRECOVERABLE"
    VERIFICATION_REJECTED = "VERIFICATION_REJECTED"
    NETWORK_MUTATION_FAILED = "NETWORK_MUTATION_FAILED"


class NetworkMutationRecord(BaseModel):
    url: str
    method: str = "POST"
    response_status: int = 200
    latency_ms: float = 0.0


class ElementSignature(BaseModel):
    tag: str
    text: str
    aria_role: Optional[str] = None
    attributes: dict[str, str] = Field(default_factory=dict)
    bbox_ratio: list[float] = Field(default_factory=list)  # [x_pct, y_pct, w_pct, h_pct]
    visual_patch_phash: Optional[str] = None
    visual_patch_path: Optional[str] = None


class PostCondition(BaseModel):
    url_contains: Optional[str] = None
    dom_text_visible: list[str] = Field(default_factory=list)
    network_path_contains: Optional[str] = None
    network_status_in: list[int] = Field(default_factory=lambda: [200, 201, 204])


class StepAnchor(BaseModel):
    step_id: str
    intent: str
    action_type: str  # "click", "fill", "select", "vault_inject"
    action_value: Optional[str] = None
    locators: list[str]  # Ranked waterfall: role -> css/testid -> relative xpath -> bbox
    signature: ElementSignature
    post_condition: PostCondition
    is_commit_step: bool = False


class Playbook(BaseModel):
    playbook_id: str
    merchant_id: str
    version: int = 1
    dom_fingerprint: str
    success_count: int = 0
    attempt_count: int = 0
    avg_latency_sec: float = 0.0
    steps: list[StepAnchor]


class ExecutionReceipt(BaseModel):
    run_id: str
    merchant_id: str
    workflow_type: str
    success: bool
    failure_code: FailureCode = FailureCode.NONE
    terminal_reward: float
    total_reward: float
    network_confirmed: bool = False
    dom_confirmed: bool = False
    visual_confirmed: bool = False
    verified: bool = False
    confirmation_text: Optional[str] = None
    healed_steps: list[str] = Field(default_factory=list)
    compiled_playbook_version: Optional[int] = None
    llm_tokens_used: int = 0
    duration_sec: float = 0.0
    trace_zip_path: Optional[str] = None
    screenshot_receipt_path: Optional[str] = None
    network_mutations: list[NetworkMutationRecord] = Field(default_factory=list)

    @property
    def reward_score(self) -> float:
        return self.total_reward


class RunReport(BaseModel):
    receipt: ExecutionReceipt
    step_history: list[dict[str, Any]] = Field(default_factory=list)
    playbook_used: Optional[str] = None
    playbook_version_used: Optional[int] = None
    tier_used: str = "deterministic"
