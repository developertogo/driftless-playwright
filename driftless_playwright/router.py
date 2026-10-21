import asyncio
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from playwright.async_api import Page, BrowserContext

from driftless_playwright.schemas import Playbook, StepAnchor, ExecutionReceipt, FailureCode
from driftless_playwright.locator_waterfall import LocatorResolver
from driftless_playwright.agent_bridge import ScopedAgentBridge, AgentBridgeResult
from driftless_playwright.guardrails import GuardrailsInterceptor
from driftless_playwright.verifier import VerificationJudge
from driftless_playwright.vault import SecretVault
from driftless_playwright.compiler import PlaybookCompiler
from driftless_playwright.visual_diff import compute_visual_delta
from driftless_playwright.config import PLAYBOOKS_DIR


class PlaybookRouter:
    """
    Contextual Bandit Playbook Router.
    Selects the optimal version of a merchant playbook based on historical success rate,
    latency penalty, and matching DOM fingerprint.
    """
    def __init__(self, playbooks_dir: Path = PLAYBOOKS_DIR):
        self.playbooks_dir = playbooks_dir

    def calculate_strategy_score(self, playbook: Playbook) -> float:
        """strategy_score = (playbook.success_count / max(1, playbook.attempt_count)) - (0.05 * playbook.avg_latency_sec)"""
        attempts = max(1, playbook.attempt_count)
        win_rate = playbook.success_count / attempts
        return win_rate - (0.05 * playbook.avg_latency_sec)

    def load_available_playbooks(self, merchant_id: str) -> List[Playbook]:
        """Loads all stored Playbook JSONs for a merchant."""
        playbooks: List[Playbook] = []
        for p in self.playbooks_dir.glob(f"{merchant_id}_v*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = f.read()
                    playbooks.append(Playbook.model_validate_json(data))
            except Exception:
                pass
        return sorted(playbooks, key=lambda x: x.version, reverse=True)

    def select_playbook(self, merchant_id: str, dom_fingerprint: Optional[str] = None) -> Optional[Playbook]:
        """Selects the playbook with highest strategy score matching or defaulting."""
        candidates = self.load_available_playbooks(merchant_id)
        if not candidates:
            return None

        # Filter by fingerprint if provided
        matching = [p for p in candidates if dom_fingerprint and p.dom_fingerprint == dom_fingerprint]
        pool = matching if matching else candidates

        best = max(pool, key=self.calculate_strategy_score)
        return best


class ResilientStepOrchestrator:
    """
    Executes multi-step browser workflows using the deterministic fast path,
    tripwire detection, 3-tier live self-healing pipeline, and multi-signal verification.
    """
    def __init__(
        self,
        page: Page,
        judge: VerificationJudge,
        guardrails: Optional[GuardrailsInterceptor] = None,
        vault: Optional[SecretVault] = None
    ):
        self.page = page
        self.judge = judge
        self.guardrails = guardrails or GuardrailsInterceptor()
        self.vault = vault or SecretVault()
        self.resolver = LocatorResolver(page)
        self.agent_bridge = ScopedAgentBridge(self.guardrails)
        self.compiler = PlaybookCompiler()

    async def execute_playbook(
        self,
        playbook: Playbook,
        run_id: str,
        workflow_type: str = "cancel"
    ) -> ExecutionReceipt:
        """
        Executes a Playbook with deterministic fast path (0 LLM tokens)
        and live fallback to Tier 1, Tier 2, or Tier 3 upon UI drift.
        """
        self.judge.attach_network_watcher(self.page)
        healed_step_ids: List[str] = []
        synthesized_actions: List[Dict[str, Any]] = []
        total_tokens_used = 0
        overall_success = True
        compiled_version = None

        for idx, step in enumerate(playbook.steps):
            t_start = time.time()
            
            # Pre-action screenshot
            screenshot_before = await self.page.screenshot()
            
            # Tripwire: Check unexpected retention modal or dialog
            has_unexpected_modal = await self.resolver.check_unexpected_modal()
            
            # Attempt Waterfall Locator resolution
            locator, loc_str = await self.resolver.resolve_waterfall(step, timeout_ms=1200)
            
            # Modal is unexpected only if the resolved locator is NOT inside the modal dialog
            is_loc_inside_modal = False
            if locator and has_unexpected_modal:
                try:
                    is_loc_inside_modal = await locator.evaluate(
                        "el => !!el.closest('[role=\"dialog\"], .modal, #retention-modal')"
                    )
                except Exception:
                    pass

            needs_self_healing = (locator is None) or (has_unexpected_modal and not is_loc_inside_modal)
            tier_used = "deterministic"

            if needs_self_healing:
                print(f"[Orchestrator] ⚠️ UI Drift detected on step '{step.step_id}' ('{step.intent}')!")
                
                # --- Tier 1: Fast Semantic (nomic-embed-text) + Visual Patch Repair (<100ms, 0 tokens) ---
                t1_res = await self.resolver.tier1_semantic_healing(step, screenshot_before)
                if t1_res and not has_unexpected_modal:
                    locator, new_loc_str, score = t1_res
                    print(f"[Orchestrator] 🩺 Tier 1 Healed! Match confidence: {score:.2f} -> {new_loc_str}")
                    step.locators.insert(0, new_loc_str)
                    healed_step_ids.append(step.step_id)
                    tier_used = "tier1_semantic"
                else:
                    # --- Tier 2: Scoped Micro-Agent Bridge (qwen2.5vl:7b, use_vision=False) ---
                    print(f"[Orchestrator] 🤖 Escalating to Tier 2 Scoped Agent Bridge...")
                    bridge_res = await self.agent_bridge.recover_step(
                        page=self.page,
                        step=step,
                        workflow_type=workflow_type,
                        force_tier3_vision=False
                    )

                    if not bridge_res.success:
                        # --- Tier 3: Set-of-Marks Vision Fallback (use_vision=True) ---
                        print(f"[Orchestrator] 👁️ Tier 2 stalled. Escalating to Tier 3 Set-of-Marks Vision Fallback...")
                        bridge_res = await self.agent_bridge.recover_step(
                            page=self.page,
                            step=step,
                            workflow_type=workflow_type,
                            force_tier3_vision=True
                        )

                    if bridge_res.success:
                        print(f"[Orchestrator] ✅ {bridge_res.tier} successfully bridged past drift!")
                        total_tokens_used += bridge_res.tokens_used
                        healed_step_ids.append(step.step_id)
                        synthesized_actions.extend(bridge_res.healed_actions)
                        tier_used = bridge_res.tier
                        # Agent already performed necessary actions to satisfy post_condition
                        self.judge.calculate_step_reward(
                            progressed_to_post_condition=True,
                            latency_sec=time.time() - t_start,
                            dom_validation_error=False
                        )
                        continue
                    else:
                        print(f"[Orchestrator] ❌ All self-healing tiers exhausted: {bridge_res.error}")
                        overall_success = False
                        break

            # If not already executed by agent bridge, execute action on resolved locator
            if locator:
                # Check guardrails
                try:
                    el_text = (await locator.inner_text()).strip()
                except Exception:
                    el_text = ""

                allowed, warning = self.guardrails.check_action_allowed(workflow_type, el_text)
                if not allowed:
                    print(f"[Orchestrator] 🛑 Guardrail blocked action: {warning}")
                    overall_success = False
                    break

                # Idempotency check for commit step
                if step.is_commit_step:
                    can_commit, idemp_msg = self.guardrails.can_execute_commit_step("/api/subscription/cancel")
                    if not can_commit:
                        print(f"[Orchestrator] 🔒 {idemp_msg}")
                        continue

                # Execute action
                if step.action_type == "click":
                    await locator.click()
                elif step.action_type == "fill":
                    val = step.action_value or ""
                    if val.startswith("vault://"):
                        val = self.vault.resolve(val)
                    await locator.fill(val)
                elif step.action_type == "vault_inject":
                    val = self.vault.resolve(step.action_value or "vault://card/virtual_4242")
                    await locator.fill(val)

                await self.page.wait_for_load_state("networkidle", timeout=2000)

            # Post-check tripwire
            screenshot_after = await self.page.screenshot()
            vis_delta = compute_visual_delta(screenshot_before, screenshot_after)
            did_ui_respond = vis_delta > 0.01

            # Check post condition
            post_met = True
            if step.post_condition.dom_text_visible:
                post_met = False
                for txt in step.post_condition.dom_text_visible:
                    try:
                        if await self.page.get_by_text(txt, exact=False).first.is_visible(timeout=500):
                            post_met = True
                            break
                    except Exception:
                        pass

            step_latency = time.time() - t_start
            self.judge.calculate_step_reward(
                progressed_to_post_condition=post_met,
                latency_sec=step_latency,
                dom_validation_error=not did_ui_respond
            )

        # Terminal State Multi-Signal Verification Judge
        is_verified, term_reward, details = await self.judge.verify_terminal_state(self.page)
        
        # If healed steps occurred and verification was verified, distill and compile Playbook v+1!
        if synthesized_actions and is_verified:
            try:
                compiled_pb = self.compiler.compile_playbook(playbook, synthesized_actions)
                self.compiler.save_playbook(compiled_pb)
                compiled_version = compiled_pb.version
                print(f"[Orchestrator] 📦 Closed-Loop Experience Distillation: Compiled and saved {compiled_pb.playbook_id} (version {compiled_version})!")
            except Exception as e:
                print(f"[Orchestrator] Warning during compilation: {e}")

        receipt = self.judge.build_receipt(
            run_id=run_id,
            is_success=is_verified,
            terminal_reward=term_reward,
            details=details,
            healed_steps=healed_step_ids,
            compiled_version=compiled_version,
            llm_tokens=total_tokens_used,
            failure_code=FailureCode.NONE if is_verified else FailureCode.VERIFICATION_REJECTED
        )

        return receipt
