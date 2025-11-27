import os
import replicate
from typing import Any

from app.service.cardnews.replicate_prompt_optimizer import optimize_for_replicate

REPLICATE_MODEL = "black-forest-labs/flux-1.1-pro"

def generate_image_from_prompt(visual_prompt: str) -> str:
    """
    visual_prompt → replicate 최적화 → 이미지 생성 → URL 반환 (안정형)
    """
    params = optimize_for_replicate(visual_prompt)

    client = replicate.Client(api_token=os.getenv("REPLICATE_API_TOKEN"))

    output: Any = client.run(
        REPLICATE_MODEL,
        input={
            "prompt": params["prompt"],
            "negative_prompt": params["negative_prompt"],
            "width": params["width"],
            "height": params["height"],
            "output_format": "png",
        },
    )
 
    # 👇 최신 Replicate SDK 대응 (3종류 모두 지원)
    if isinstance(output, list):
        return output[0]

    if hasattr(output, "url"):
        return output.url

    if isinstance(output, dict) and "url" in output:
        return output["url"]

    raise RuntimeError(f"Unexpected Replicate output format: {output}")
