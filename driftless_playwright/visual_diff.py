import io
from typing import Optional, Union, Tuple, List
from PIL import Image
import imagehash
import numpy as np


def compute_phash(image_input: Union[bytes, str, Image.Image]) -> str:
    """Computes a 64-bit perceptual hash (pHash) for an image or element crop."""
    if isinstance(image_input, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image_input)).convert("RGB")
    elif isinstance(image_input, str):
        img = Image.open(image_input).convert("RGB")
    elif isinstance(image_input, Image.Image):
        img = image_input.convert("RGB")
    else:
        raise ValueError(f"Unsupported image type: {type(image_input)}")
    
    return str(imagehash.phash(img))


def phash_similarity(hash_a: Optional[str], hash_b: Optional[str]) -> float:
    """
    Computes perceptual hash similarity between 0.0 and 1.0 based on Hamming distance.
    Max distance for standard 64-bit pHash is 64.
    """
    if not hash_a or not hash_b:
        return 0.0
    try:
        h1 = imagehash.hex_to_hash(hash_a)
        h2 = imagehash.hex_to_hash(hash_b)
        dist = h1 - h2  # Hamming distance
        return max(0.0, 1.0 - (dist / 64.0))
    except Exception:
        return 0.0


def crop_roi(
    image_input: Union[bytes, Image.Image],
    bbox_ratio: List[float]  # [x_pct, y_pct, w_pct, h_pct]
) -> Tuple[Image.Image, int]:
    """
    Crops Region of Interest (ROI) from an image given normalized bounding box ratios.
    Returns the cropped PIL Image and the estimated vision token count:
    (crop_width * crop_height) / (28 * 28)
    """
    if isinstance(image_input, (bytes, bytearray)):
        img = Image.open(io.BytesIO(image_input)).convert("RGB")
    else:
        img = image_input.convert("RGB")
    
    width, height = img.size
    if len(bbox_ratio) >= 4:
        x_pct, y_pct, w_pct, h_pct = bbox_ratio[:4]
        left = int(x_pct * width)
        top = int(y_pct * height)
        right = int((x_pct + w_pct) * width)
        bottom = int((y_pct + h_pct) * height)
        # Clamp bounds
        left = max(0, min(width - 1, left))
        top = max(0, min(height - 1, top))
        right = max(left + 1, min(width, right))
        bottom = max(top + 1, min(height, bottom))
        cropped = img.crop((left, top, right, bottom))
    else:
        cropped = img

    crop_w, crop_h = cropped.size
    vision_tokens = max(1, int((crop_w * crop_h) / (28 * 28)))
    return cropped, vision_tokens


def compute_visual_delta(img_a_input: Union[bytes, str], img_b_input: Union[bytes, str]) -> float:
    """
    Computes visual delta (1.0 - structural similarity) between two screenshots.
    Returns a float between 0.0 (identical) and 1.0 (completely distinct).
    """
    def _to_gray_array(inp: Union[bytes, str]) -> np.ndarray:
        if isinstance(inp, (bytes, bytearray)):
            im = Image.open(io.BytesIO(inp)).convert("L")
        else:
            im = Image.open(inp).convert("L")
        # Resize to fixed resolution for stable comparison
        im = im.resize((256, 256))
        return np.array(im, dtype=np.float32)

    try:
        arr1 = _to_gray_array(img_a_input)
        arr2 = _to_gray_array(img_b_input)
        
        # Simple fast SSIM approximation
        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2
        
        mu1 = arr1.mean()
        mu2 = arr2.mean()
        sigma1_sq = ((arr1 - mu1) ** 2).mean()
        sigma2_sq = ((arr2 - mu2) ** 2).mean()
        sigma12 = ((arr1 - mu1) * (arr2 - mu2)).mean()
        
        ssim = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / (
            (mu1**2 + mu2**2 + c1) * (sigma1_sq + sigma2_sq + c2)
        )
        return float(max(0.0, min(1.0, 1.0 - ssim)))
    except Exception:
        return 0.0
