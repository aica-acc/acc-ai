# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional, Literal, Any, Dict, Union
from pathlib import Path

from .banner_builder import generate_banner_images_from_prompt

__all__ = [
    "make_banner_from_prompt_service",
]

def make_banner_from_prompt_service(
    job: Dict[str, Any],
    *,
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    width: Optional[int] = None,
    height: Optional[int] = None,
    aspect_ratio: str = "custom",  # job에 기본 내장되긴 하지만 파이프라인 호환
    resolution: str = "2K",
    seed: Optional[int] = None,
    use_pre_llm: bool = True,
    return_type: Literal["dict", "list", "string"] = "dict",
    save_dir: Optional[Path] = None,
    filename_prefix: Optional[str] = None,
) -> Union[dict, list, str]:
    """
    Facade: 컨트롤러에서 호출.
    - 필요한 파라미터를 그대로 banner_builder에 전달
    - aspect_ratio는 job.get('aspect_ratio', 'custom')가 기본이라 별도 사용 X
    """
    # job에 aspect_ratio를 주입(없으면 'custom')
    job = dict(job)
    job.setdefault("aspect_ratio", aspect_ratio)

    return generate_banner_images_from_prompt(
        job,
        orientation=orientation,
        width=width,
        height=height,
        resolution=resolution,
        use_pre_llm=use_pre_llm,
        seed=seed,
        save_dir=save_dir,
        filename_prefix=filename_prefix,
        return_type=return_type,
    )
