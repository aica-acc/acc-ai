# -*- coding: utf-8 -*-
"""
service_make_prompt_from_analysis.py

- 컨트롤러/서비스에서 간단히 호출할 수 있는 퍼사드
- 입력: FestivalService.analyze(...)가 반환한 dict
- 출력: 요청한 스키마(기본 basic)로 딱 맞춘 dict
- width/height 생략 시 orientation에 따른 기본값 자동 적용 (실제 처리는 빌더)
"""

from __future__ import annotations
from typing import Optional, Dict, Any, Literal
from math import gcd

# 동일 폴더 내 빌더
from .banner_prompt_builder import generate_banner_prompt_from_analysis

__all__ = [
    "aspect_from_wh",
    "make_banner_prompt_service",
    "make_horizontal_banner_prompt_service",
    "make_vertical_banner_prompt_service",
]

# ---------------------- 내부 유틸 ----------------------
def aspect_from_wh(width: int, height: int) -> str:
    """3024x544 → '189:34' 형태의 비율 문자열로 변환"""
    if width <= 0 or height <= 0:
        raise ValueError("width/height must be positive integers.")
    g = gcd(width, height) or 1
    return f"{width // g}:{height // g}"

# 요청 스키마(네가 지정한 키들만)
_BASIC_KEYS = (
    "width",
    "height",
    "aspect_ratio",
    "resolution",
    "use_pre_llm",
    "prompt_original",
    "prompt",
    "prompt_ko_original",
    "prompt_ko",
    "prompt_ko_baseline",
)

def _to_basic_schema(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    요청 스키마로 축소:
    {
      "width","height","aspect_ratio","resolution","use_pre_llm",
      "prompt_original","prompt","prompt_ko_original","prompt_ko","prompt_ko_baseline"
    }
    """
    return {k: result.get(k) for k in _BASIC_KEYS}

# ---------------------- 퍼사드 ----------------------
def make_banner_prompt_service(
    analysis_payload: Dict[str, Any],
    *,
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    width: Optional[int] = None,
    height: Optional[int] = None,
    aspect_ratio: str = "custom",
    resolution: str = "2K",
    use_pre_llm: bool = True,
    seed: Optional[int] = None,
    llm_model: Optional[str] = None,
    strict: bool = True,
    # ✅ 기본을 "basic"으로 — 네가 요구한 스키마 그대로 나가게 함
    schema: Literal["basic", "extended"] = "basic",
) -> Dict[str, Any]:
    """
    분석 payload(dict) → Dreamina 3.1 배너 프롬프트 JSON(dict)

    Args:
        analysis_payload: FestivalService.analyze(...) 결과 dict
        orientation     : "horizontal" | "vertical"
        width, height   : None이면 orientation 기본값 자동 적용 (빌더 처리)
        aspect_ratio    : 기본 'custom'
        resolution      : 예) '2K'
        use_pre_llm     : True면 LLM 사용(키 없으면 자동 폴백)
        seed            : 정수 또는 None
        llm_model       : 특정 모델 강제 시 지정
        strict          : 필수값 부족 시 예외(권장 True)
        schema          : "basic"(기본) | "extended"

    Returns:
        dict: schema에 맞춘 프롬프트 JSON
    """
    result = generate_banner_prompt_from_analysis(
        analysis_payload,
        width=width,
        height=height,
        orientation=orientation,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        use_pre_llm=use_pre_llm,
        seed=seed,
        llm_model=llm_model,
        strict=strict
    )
    return _to_basic_schema(result) if schema == "basic" else result

def make_horizontal_banner_prompt_service(
    analysis_payload: Dict[str, Any],
    *,
    width: Optional[int] = None,   # None이면 3024
    height: Optional[int] = None,  # None이면 544
    aspect_ratio: str = "custom",
    resolution: str = "2K",
    use_pre_llm: bool = True,
    seed: Optional[int] = None,
    llm_model: Optional[str] = None,
    strict: bool = True,
    schema: Literal["basic", "extended"] = "basic",
) -> Dict[str, Any]:
    """가로 배너(기본 3024×544) 프롬프트 생성 퍼사드"""
    return make_banner_prompt_service(
        analysis_payload,
        orientation="horizontal",
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        use_pre_llm=use_pre_llm,
        seed=seed,
        llm_model=llm_model,
        strict=strict,
        schema=schema,
    )

def make_vertical_banner_prompt_service(
    analysis_payload: Dict[str, Any],
    *,
    width: Optional[int] = None,   # None이면 1008
    height: Optional[int] = None,  # None이면 3024
    aspect_ratio: str = "custom",
    resolution: str = "2K",
    use_pre_llm: bool = True,
    seed: Optional[int] = None,
    llm_model: Optional[str] = None,
    strict: bool = True,
    schema: Literal["basic", "extended"] = "basic",
) -> Dict[str, Any]:
    """세로 배너(기본 1008×3024) 프롬프트 생성 퍼사드"""
    return make_banner_prompt_service(
        analysis_payload,
        orientation="vertical",
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        use_pre_llm=use_pre_llm,
        seed=seed,
        llm_model=llm_model,
        strict=strict,
        schema=schema,
    )
