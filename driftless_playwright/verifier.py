import time
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Response
from driftless_playwright.schemas import ExecutionReceipt, FailureCode, PostCondition


class MutationRecord:
    def __init__(self, method: str, url: str, status: int, timestamp: float):
        self.method = method
        self.url = url
        self.status = status
        self.timestamp = timestamp


class VerificationJudge:
    """
    Reward calculator and multi-signal verification judge.
    Never trusts the LLM calling done(success=True) on its own.
    Inspects network mutations (200 OK), DOM confirmation badges, and absence of error banners.
    """
    def __init__(self, merchant_id: str, workflow_type: str = "cancel"):
        self.merchant_id = merchant_id
        self.workflow_type = workflow_type
        self.mutation_log: List[MutationRecord] = []
        self.step_rewards: List[float] = []
        self.dom_hashes_seen: set[str] = set()
        self.start_time = time.time()

    def attach_network_watcher(self, page: Page) -> None:
        """Attaches async listener tracking state-changing network responses."""
        async def _on_response(response: Response):
            req = response.request
            if req.method.upper() in ["POST", "PUT", "PATCH", "DELETE"]:
                self.mutation_log.append(
                    MutationRecord(
                        method=req.method.upper(),
                        url=response.url,
                        status=response.status,
                        timestamp=time.time()
                    )
                )
        page.on("response", _on_response)

    def calculate_step_reward(
        self,
        progressed_to_post_condition: bool,
        latency_sec: float,
        dom_validation_error: bool,
        dom_hash: Optional[str] = None
    ) -> float:
        """
        step_reward = (
            +1.0 * progressed_to_post_condition
            -0.2 * action_latency_penalty
            -0.5 * triggered_dom_validation_error
            -1.0 * repeated_dom_state_hash
        )
        """
        reward = 0.0
        if progressed_to_post_condition:
            reward += 1.0
        
        # Latency penalty: penalize latency over 1.0 second up to max -0.5
        if latency_sec > 1.0:
            reward -= min(0.5, 0.2 * (latency_sec - 1.0))

        if dom_validation_error:
            reward -= 0.5

        if dom_hash:
            if dom_hash in self.dom_hashes_seen:
                reward -= 1.0
            else:
                self.dom_hashes_seen.add(dom_hash)

        self.step_rewards.append(reward)
        return reward

    async def verify_terminal_state(
        self,
        page: Page,
        expected_mutation_path: str = "/api/subscription/cancel",
        expected_dom_texts: Optional[List[str]] = None
    ) -> tuple[bool, float, Dict[str, Any]]:
        """
        terminal_reward = (
            +10.0 if (network_mutation_200_ok and dom_confirmation_present and not error_banner_visible)
            else -10.0
        )
        """
        if expected_dom_texts is None:
            expected_dom_texts = ["Canceled", "Status: Canceled", "subscription has been canceled", "Successfully Canceled"]

        # 1. Check network mutations
        network_mutation_200_ok = False
        for record in self.mutation_log:
            if expected_mutation_path in record.url and record.status in [200, 201, 204]:
                network_mutation_200_ok = True
                break

        # 2. Check DOM confirmation text
        dom_confirmation_present = False
        matched_text = None
        for txt in expected_dom_texts:
            try:
                locator = page.get_by_text(txt, exact=False).first
                if await locator.is_visible(timeout=500):
                    dom_confirmation_present = True
                    matched_text = txt
                    break
            except Exception:
                pass

        # 3. Check error banners
        error_banner_visible = False
        error_selectors = [".alert-danger", ".error-banner", "[role='alert']", ".toast-error"]
        for sel in error_selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=300):
                    error_banner_visible = True
                    break
            except Exception:
                pass

        is_success = network_mutation_200_ok and dom_confirmation_present and (not error_banner_visible)
        terminal_reward = 10.0 if is_success else -10.0

        details = {
            "network_confirmed": network_mutation_200_ok,
            "dom_confirmed": dom_confirmation_present,
            "error_banner_visible": error_banner_visible,
            "confirmation_text": matched_text,
            "terminal_reward": terminal_reward,
            "mutations_count": len(self.mutation_log)
        }
        return is_success, terminal_reward, details

    def build_receipt(
        self,
        run_id: str,
        is_success: bool,
        terminal_reward: float,
        details: Dict[str, Any],
        healed_steps: List[str],
        compiled_version: Optional[int] = None,
        llm_tokens: int = 0,
        trace_path: Optional[str] = None,
        screenshot_path: Optional[str] = None,
        failure_code: FailureCode = FailureCode.NONE
    ) -> ExecutionReceipt:
        duration = time.time() - self.start_time
        tot_reward = sum(self.step_rewards) + terminal_reward
        from driftless_playwright.schemas import NetworkMutationRecord
        mutations = [
            NetworkMutationRecord(
                url=m.url,
                method=m.method,
                response_status=m.status
            )
            for m in self.mutation_log
        ]
        return ExecutionReceipt(
            run_id=run_id,
            merchant_id=self.merchant_id,
            workflow_type=self.workflow_type,
            success=is_success,
            failure_code=failure_code if not is_success else FailureCode.NONE,
            terminal_reward=terminal_reward,
            total_reward=round(tot_reward, 3),
            network_confirmed=details.get("network_confirmed", False),
            dom_confirmed=details.get("dom_confirmed", False),
            visual_confirmed=details.get("dom_confirmed", False),
            verified=is_success,
            network_mutations=mutations,
            confirmation_text=details.get("confirmation_text"),
            healed_steps=healed_steps,
            compiled_playbook_version=compiled_version,
            llm_tokens_used=llm_tokens,
            duration_sec=round(duration, 3),
            trace_zip_path=trace_path,
            screenshot_receipt_path=screenshot_path
        )

    # Alias for API compatibility
    build_execution_receipt = build_receipt
