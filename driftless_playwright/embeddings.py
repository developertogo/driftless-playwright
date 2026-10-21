import hashlib
import math
import numpy as np
import httpx
from typing import List, Optional
from driftless_playwright.config import EMBEDDING_BASE_URL, EMBEDDING_MODEL

_EMBED_DIM = 768
_CACHE: dict[str, List[float]] = {}


def _token_hash_embedding(text: str, dim: int = _EMBED_DIM) -> List[float]:
    """
    Deterministic 768-dim float32 embedding generator based on semantic concept clusters
    and token/character n-grams. Provides normalized, semantically consistent fallback
    when local Ollama is offline or in CI environments.
    """
    cleaned = text.strip().lower()
    if not cleaned:
        vec = [0.0] * dim
        vec[0] = 1.0
        return vec

    # Concept clusters mapping semantic intents to aligned dimension bands
    concept_clusters = {
        # Action: Cancellation / Termination / Exit
        "cancel": (40, 60),
        "end": (40, 60),
        "terminate": (40, 60),
        "stop": (40, 60),
        "exit": (40, 60),
        "close": (40, 60),
        # Target: Subscription / Membership / Plan
        "subscription": (100, 120),
        "membership": (100, 120),
        "plan": (100, 120),
        "service": (100, 120),
        # Action: Confirmation / Affirmation
        "confirm": (200, 220),
        "yes": (200, 220),
        "continue": (200, 220),
        "finish": (200, 220),
        "proceed": (200, 220),
        # Domain: Billing / Payment / Account
        "billing": (300, 320),
        "payment": (300, 320),
        "invoice": (300, 320),
        "card": (300, 320),
        # Trap / Retention: Upgrade / Annual / Stay
        "upgrade": (450, 480),
        "annual": (450, 480),
        "keep": (500, 520),
        "stay": (500, 520),
        "save": (500, 520),
    }

    vec = np.zeros(dim, dtype=np.float32)
    words = [w.strip(".,!-?()[]") for w in cleaned.split() if w.strip(".,!-?()[]")]

    for word in words:
        # Check if word or stem matches a semantic cluster
        matched_cluster = None
        for kw, span in concept_clusters.items():
            if kw in word:
                matched_cluster = span
                break
        
        if matched_cluster:
            start_idx, end_idx = matched_cluster
            for idx in range(start_idx, end_idx):
                vec[idx] += 3.0
        else:
            # Deterministic hash scattering for other tokens
            h = hashlib.sha256(word.encode("utf-8")).digest()
            slot = int.from_bytes(h[:4], "big") % dim
            sign = 1.0 if (h[4] % 2 == 0) else -1.0
            vec[slot] += sign * 0.5

    norm = np.linalg.norm(vec)
    if norm > 1e-9:
        vec = vec / norm
    else:
        vec[0] = 1.0
    return vec.tolist()


def get_embedding(text: str, base_url: str = EMBEDDING_BASE_URL, model: str = EMBEDDING_MODEL) -> List[float]:
    """
    Fetch 768-dim float32 embedding from Ollama or fallback to deterministic token hash.
    """
    cache_key = f"{model}:{text}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    try:
        url = f"{base_url.rstrip('/')}/api/embeddings"
        with httpx.Client(timeout=0.6) as client:
            resp = client.post(url, json={"model": model, "prompt": text})
            if resp.status_code == 200:
                data = resp.json()
                emb = data.get("embedding")
                if emb and len(emb) == _EMBED_DIM:
                    _CACHE[cache_key] = emb
                    return emb
    except Exception:
        pass

    # Deterministic fallback
    emb = _token_hash_embedding(text, _EMBED_DIM)
    _CACHE[cache_key] = emb
    return emb


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def nomic_cosine_similarity(text_a: str, text_b: str) -> float:
    """Computes semantic cosine similarity between two text strings."""
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    if text_a.strip().lower() == text_b.strip().lower():
        return 1.0
    
    emb_a = get_embedding(text_a)
    emb_b = get_embedding(text_b)
    return cosine_similarity(emb_a, emb_b)
