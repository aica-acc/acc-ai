# -*- coding: utf-8 -*-
"""
service_make_banner_from_prompt.py

퍼사드(얇은 래퍼):
- 컨트롤러/백엔드에서 쓰기 쉬운 진입점
- KO 변경 감지 & EN 동기화는 '필수'로 수행 (코어에서 강제)
- save_dir를 넘기면 파일 저장 + 'artifact_paths' 포함한 dict를 받을 수 있음
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Literal, Union, List
from pathlib import Path

from .banner_builder import generate_banner_images_from_prompt

__all__ = [
    "make_banner_from_prompt_service",
    "make_horizontal_banner_from_prompt_service",
    "make_vertical_banner_from_prompt_service",
]

def make_banner_from_prompt_service(
    job: Dict[str, Any],
    *,
    orientation: Optional[Literal["horizontal", "vertical"]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    seed: Optional[int] = None,
    use_pre_llm: Optional[bool] = None,
    # KO-sync는 코어에서 필수 강제 수행
    rolling_baseline: bool = True,
    return_type: Literal["dict", "list", "string"] = "list",
    strict: bool = True,
    model: Optional[str] = None,
    # 파일 저장 옵션
    save_dir: Optional[Union[str, Path]] = None,
    filename_prefix: Optional[str] = None,
) -> Union[List[str], Dict[str, Any], str]:
    return generate_banner_images_from_prompt(
        job,
        orientation=orientation,
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        seed=seed,
        use_pre_llm=use_pre_llm,
        rolling_baseline=rolling_baseline,
        return_type=return_type,
        strict=strict,
        model=model,
        save_dir=save_dir,
        filename_prefix=filename_prefix,
    )

def make_horizontal_banner_from_prompt_service(job: Dict[str, Any], **kwargs) -> Union[List[str], Dict[str, Any], str]:
    kwargs.setdefault("orientation", "horizontal")
    return make_banner_from_prompt_service(job, **kwargs)

def make_vertical_banner_from_prompt_service(job: Dict[str, Any], **kwargs) -> Union[List[str], Dict[str, Any], str]:
    kwargs.setdefault("orientation", "vertical")
    return make_banner_from_prompt_service(job, **kwargs)
