import logging
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from driftless_playwright.schemas import ExecutionReceipt, FailureCode, Playbook
from driftless_playwright.compiler import PlaybookCompiler

logger = logging.getLogger("driftless.eval_gates")


class EvalPromotionDecision(str, Enum):
    PROMOTED = "PROMOTED"        # Run is trusted, verified, and distilled into a deterministic Playbook
    QUARANTINED = "QUARANTINED"  # Run succeeded but requires additional corroborating runs or manual check
    REJECTED = "REJECTED"        # Run failed verification, tripped guardrails, or had ambiguous outcome


class EvalGateResult(BaseModel):
    decision: EvalPromotionDecision
    merchant_id: str
    reasons: List[str] = Field(default_factory=list)
    verification_score: float
    has_network_proof: bool
    has_dom_proof: bool
    guardrail_violations: int = 0
    compiled_playbook_path: Optional[str] = None


class PlaybookEvalGate:
    """
    Evaluates whether an agentic / self-healed execution trajectory is trusted
    enough to be promoted into a production deterministic Playbook (e.g. Playbook v2).
    
    Compliance Rule: Iris must NEVER report a cancellation it did not complete.
    """
    def __init__(
        self,
        min_reward_threshold: float = 8.0,
        compiler: Optional[PlaybookCompiler] = None
    ):
        self.min_reward_threshold = min_reward_threshold
        self.compiler = compiler or PlaybookCompiler()

    def evaluate_and_promote(
        self,
        receipt: ExecutionReceipt,
        base_playbook: Optional[Playbook] = None,
        healed_actions: Optional[List[Dict[str, Any]]] = None,
        guardrail_violations: int = 0
    ) -> EvalGateResult:
        reasons = []
        has_network_proof = False
        has_dom_proof = False

        # 1. Verification of Network Mutation (Primary Truth)
        for mut in receipt.network_mutations:
            if 200 <= mut.response_status < 300:
                has_network_proof = True
                break

        # 2. Verification of DOM confirmation
        if receipt.dom_confirmed:
            has_dom_proof = True

        # 3. Guardrail Check
        if guardrail_violations > 0:
            reasons.append(f"Guardrail intercepted {guardrail_violations} prohibited action(s)")

        if not has_network_proof and not has_dom_proof:
            reasons.append("Neither network mutation proof nor DOM confirmation was found.")
        elif not has_network_proof and has_dom_proof:
            reasons.append("DOM text appeared confirmed, but no network mutation response (200 OK) was detected.")

        if receipt.reward_score < self.min_reward_threshold:
            reasons.append(
                f"Reward score {receipt.reward_score:.2f} is below promotion threshold {self.min_reward_threshold}"
            )

        # 4. Strict Financial Verification Compliance
        # An action is only trusted if verification passed and zero guardrails were violated
        is_trusted = (
            receipt.verified and
            has_network_proof and
            has_dom_proof and
            guardrail_violations == 0 and
            receipt.reward_score >= self.min_reward_threshold
        )

        if not receipt.verified or (not has_network_proof and not has_dom_proof):
            decision = EvalPromotionDecision.REJECTED
        elif is_trusted:
            decision = EvalPromotionDecision.PROMOTED
            reasons.append("Run meets all verification, network mutation, and compliance criteria.")
        else:
            decision = EvalPromotionDecision.QUARANTINED
            reasons.append("Run succeeded partially; quarantined pending multi-run corroboration.")

        compiled_path_str: Optional[str] = None
        if decision == EvalPromotionDecision.PROMOTED and base_playbook and healed_actions:
            compiled_pb = self.compiler.compile_playbook(base_playbook, healed_actions)
            saved_path = self.compiler.save_playbook(compiled_pb)
            compiled_path_str = str(saved_path)
            logger.info(f"Promoted and compiled Playbook v{compiled_pb.version} for {compiled_pb.merchant_id}")

        return EvalGateResult(
            decision=decision,
            merchant_id=receipt.merchant_id,
            reasons=reasons,
            verification_score=receipt.reward_score,
            has_network_proof=has_network_proof,
            has_dom_proof=has_dom_proof,
            guardrail_violations=guardrail_violations,
            compiled_playbook_path=compiled_path_str
        )
