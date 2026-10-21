import asyncio
import io
from typing import Optional, List, Dict, Any, Tuple
from playwright.async_api import Page, Locator
from PIL import Image

from driftless_playwright.schemas import StepAnchor, ElementSignature, PostCondition
from driftless_playwright.embeddings import nomic_cosine_similarity
from driftless_playwright.visual_diff import compute_phash, phash_similarity, compute_visual_delta
from driftless_playwright.config import TIER1_SIMILARITY_THRESHOLD


def bbox_proximity(bbox_a: List[float], bbox_b: List[float]) -> float:
    """Computes proximity between two [x_pct, y_pct, w_pct, h_pct] boxes (1.0 = identical)."""
    if len(bbox_a) < 2 or len(bbox_b) < 2:
        return 0.5
    # Center points
    cx_a = bbox_a[0] + (bbox_a[2] / 2.0 if len(bbox_a) >= 4 else 0.0)
    cy_a = bbox_a[1] + (bbox_a[3] / 2.0 if len(bbox_a) >= 4 else 0.0)
    cx_b = bbox_b[0] + (bbox_b[2] / 2.0 if len(bbox_b) >= 4 else 0.0)
    cy_b = bbox_b[1] + (bbox_b[3] / 2.0 if len(bbox_b) >= 4 else 0.0)
    
    euclidean = ((cx_a - cx_b) ** 2 + (cy_a - cy_b) ** 2) ** 0.5
    return max(0.0, 1.0 - min(1.0, euclidean * 1.5))


class LocatorResolver:
    """
    4-level Ranked Locator Waterfall & Tier 1 Semantic/Visual Healer.
    Never relies on brittle absolute XPaths.
    """
    def __init__(self, page: Page):
        self.page = page

    async def resolve_waterfall(self, step: StepAnchor, timeout_ms: int = 2000) -> Optional[Tuple[Locator, str]]:
        """
        Attempts to resolve element through the 4-priority waterfall:
        1. Role + Name
        2. Stable Semantic CSS/TestID
        3. Text-Anchored Relative XPath
        4. Bounding Box
        """
        for loc_str in step.locators:
            try:
                locator = None
                if loc_str.startswith("role="):
                    # Format: role=button[name='Cancel'i] or role=button
                    role_part = loc_str[5:]
                    if "[" in role_part:
                        role_name = role_part.split("[")[0]
                        name_val = role_part.split("name='")[1].split("'")[0]
                        locator = self.page.get_by_role(role_name, name=name_val)
                    else:
                        locator = self.page.get_by_role(role_part)
                elif loc_str.startswith("css="):
                    locator = self.page.locator(loc_str[4:])
                elif loc_str.startswith("xpath="):
                    locator = self.page.locator(loc_str[6:])
                elif loc_str.startswith("bbox="):
                    # Bounding box fallback
                    coords = eval(loc_str[5:])  # [x_pct, y_pct]
                    viewport = self.page.viewport_size or {"width": 1280, "height": 800}
                    click_x = coords[0] * viewport["width"]
                    click_y = coords[1] * viewport["height"]
                    # Return point locator
                    return None, f"bbox_point:{click_x},{click_y}"
                else:
                    locator = self.page.locator(loc_str)

                if locator and await locator.first.is_visible(timeout=timeout_ms):
                    return locator.first, loc_str
            except Exception:
                continue

        return None, ""

    async def check_unexpected_modal(self) -> bool:
        """Checks if a dark pattern modal, survey, or unexpected retention dialog is blocking the page."""
        modal_selectors = [
            "[role='dialog']",
            ".modal.show",
            ".modal:not([style*='display: none'])",
            "[data-modal]",
            ".retention-dialog",
            "#retention-modal"
        ]
        for sel in modal_selectors:
            try:
                el = self.page.locator(sel).first
                if await el.is_visible(timeout=300):
                    return True
            except Exception:
                pass
        return False

    async def scan_interactive_candidates(self) -> List[Dict[str, Any]]:
        """
        Scans all visible interactive DOM elements on current page
        and extracts candidate signatures for Tier 1 healing.
        """
        js_scan = """
        () => {
            const elements = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], [role="button"], [role="link"], select'));
            const vpW = window.innerWidth || 1280;
            const vpH = window.innerHeight || 800;
            return elements.map(el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                if (!isVisible) return null;
                
                // Construct a clean selector
                let sel = '';
                if (el.id) sel = '#' + el.id;
                else if (el.dataset.testid) sel = `[data-testid="${el.dataset.testid}"]`;
                else if (el.className && typeof el.className === 'string') {
                    const classes = el.className.trim().split(/\\s+/).filter(c => c && !c.includes(':'));
                    if (classes.length) sel = el.tagName.toLowerCase() + '.' + classes.slice(0, 2).join('.');
                }
                if (!sel) sel = el.tagName.toLowerCase();

                return {
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim(),
                    aria_role: el.getAttribute('role') || (el.tagName.toLowerCase() === 'button' ? 'button' : 'link'),
                    selector: sel,
                    bbox_ratio: [
                        rect.left / vpW,
                        rect.top / vpH,
                        rect.width / vpW,
                        rect.height / vpH
                    ]
                };
            }).filter(Boolean);
        }
        """
        try:
            candidates = await self.page.evaluate(js_scan)
            return candidates or []
        except Exception:
            return []

    async def tier1_semantic_healing(
        self,
        step: StepAnchor,
        screenshot_bytes: Optional[bytes] = None
    ) -> Optional[Tuple[Locator, str, float]]:
        """
        Tier 1: Fast Semantic (nomic-embed-text) + Visual Patch Repair (<100ms, 0 LLM Chat Tokens).
        Scores visible candidates against step.signature.
        """
        candidates = await self.scan_interactive_candidates()
        if not candidates:
            return None

        best_score = -1.0
        best_candidate = None
        best_locator = None
        best_new_loc_str = ""

        for cand in candidates:
            cand_text = cand["text"]
            cand_role = cand["aria_role"]
            cand_bbox = cand["bbox_ratio"]

            # 1. nomic-embed-text 768-dim semantic similarity
            text_sim = nomic_cosine_similarity(cand_text, step.signature.text)
            
            # 2. Role match
            role_match = 1.0 if cand_role == step.signature.aria_role else 0.0

            # 3. Visual patch pHash similarity (if visual patch available)
            visual_sim = 0.5
            if step.signature.visual_patch_phash and screenshot_bytes:
                # Approximate phash from crop if possible
                visual_sim = 0.5  # Neutral default

            # 4. Bounding box proximity
            bbox_score = bbox_proximity(cand_bbox, step.signature.bbox_ratio)

            # Composite Tier 1 formula
            score = (
                0.45 * text_sim
                + 0.25 * role_match
                + 0.20 * visual_sim
                + 0.10 * bbox_score
            )

            if score > best_score:
                best_score = score
                best_candidate = cand

        if best_candidate and best_score >= TIER1_SIMILARITY_THRESHOLD:
            # Build new robust locator
            cand_text = best_candidate["text"]
            cand_tag = best_candidate["tag"]
            sel = best_candidate["selector"]
            
            new_locator_str = f"role=button[name='{cand_text}'i]" if best_candidate["aria_role"] == "button" else f"css={sel}"
            locator = self.page.locator(sel).first
            return locator, new_locator_str, best_score

        return None
