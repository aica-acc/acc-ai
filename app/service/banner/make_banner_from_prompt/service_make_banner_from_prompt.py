# -*- coding: utf-8 -*-
# app/service/banner/make_banner_from_prompt/service_make_banner_from_prompt.py
from __future__ import annotations
from typing import Dict, Any, Optional, Literal, Union
from pathlib import Path

from .banner_builder import generate_banner_images_from_prompt

def make_banner_from_prompt_service(
    job: Dict[str, Any],
    *,
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    save_dir: Optional[Path] = None,
    filename_prefix: Optional[str] = None,
    return_type: Literal["dict", "list", "string"] = "dict",
) -> Union[dict, list, str]:
    """
    상위 퍼사드: 생성기 호출 래핑
    - width/height 등은 job 내부에서 처리됨
    """
    return generate_banner_images_from_prompt(
        job,
        orientation=orientation,
        save_dir=save_dir,
        filename_prefix=filename_prefix,
        return_type=return_type,
    )
