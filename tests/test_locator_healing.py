import pytest
from driftless_playwright.schemas import StepAnchor, ElementSignature, PostCondition
from driftless_playwright.embeddings import nomic_cosine_similarity, get_embedding, cosine_similarity
from driftless_playwright.visual_diff import phash_similarity, compute_phash
from driftless_playwright.locator_waterfall import bbox_proximity


def test_semantic_embedding_similarity():
    """Verify semantic cosine similarity aligns cancel/end/terminate concepts."""
    sim_cancel_end = nomic_cosine_similarity("Cancel Membership", "End My Subscription")
    assert sim_cancel_end >= 0.80, f"Expected similarity >= 0.80, got {sim_cancel_end}"

    sim_identical = nomic_cosine_similarity("Cancel Membership", "Cancel Membership")
    assert sim_identical == 1.0

    sim_unrelated = nomic_cosine_similarity("Cancel Membership", "Upgrade to Platinum Annual Pass")
    assert sim_unrelated < 0.65, f"Expected unrelated similarity < 0.65, got {sim_unrelated}"


def test_visual_phash_similarity():
    """Verify perceptual hash similarity logic."""
    hash_a = "ffff0000ffff0000"
    hash_b = "ffff0000ffff0000"
    assert phash_similarity(hash_a, hash_b) == 1.0

    hash_c = "ffff00000000ffff"
    sim = phash_similarity(hash_a, hash_c)
    assert 0.0 <= sim <= 1.0
    assert phash_similarity(None, hash_b) == 0.0


def test_bbox_proximity():
    """Verify bounding box distance calculations."""
    box1 = [0.5, 0.5, 0.1, 0.05]
    box2 = [0.5, 0.5, 0.1, 0.05]
    assert bbox_proximity(box1, box2) == 1.0

    box_far = [0.1, 0.1, 0.1, 0.05]
    assert bbox_proximity(box1, box_far) < 0.8


def test_step_anchor_waterfall_ranking():
    """Verify StepAnchor initializes ranked waterfall properly."""
    step = StepAnchor(
        step_id="step_test",
        intent="Cancel Membership",
        action_type="click",
        locators=[
            "role=button[name='Cancel Membership'i]",
            "css=#cancel-membership-btn",
            "xpath=//button[contains(., 'Cancel Membership')]",
            "bbox=[0.72, 0.45]"
        ],
        signature=ElementSignature(
            tag="button",
            text="Cancel Membership",
            aria_role="button"
        ),
        post_condition=PostCondition(dom_text_visible=["Canceled"])
    )
    assert len(step.locators) == 4
    assert step.locators[0].startswith("role=")
    assert step.locators[1].startswith("css=")
    assert step.locators[2].startswith("xpath=")
    assert step.locators[3].startswith("bbox=")
