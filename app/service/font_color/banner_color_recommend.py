# -*- coding: utf-8 -*-
"""
app/service/font_color/banner_color_recommend.py

배너(도로/가로등/버스 등) 이미지에서
텍스트(제목/기간/장소)에 쓸 색상만 추천하는 모듈.

- 입력
  - banner_type: "road_banner", "streetlamp_banner" 등 배너 종류 문자열
  - image_path: 배너 이미지 파일 경로 (로컬)
  - festival_*_placeholder: 자리수/구분용 텍스트 (현재는 길이나 종류에 따라
    색상을 다르게 줄 여지를 남겨두는 용도이며, 기본 로직에서는 직접 사용하지 않는다)

- 출력
  - {
      "festival_color_name_placeholder": "#RRGGBB",
      "festival_color_period_placeholder": "#RRGGBB",
      "festival_color_location_placeholder": "#RRGGBB"
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from PIL import Image, ImageStat


def _load_image(image_path: str) -> Image.Image:
    """이미지를 RGB로 로드."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"banner image not found: {p}")
    img = Image.open(p)
    return img.convert("RGB")


def _compute_luminance(img: Image.Image) -> float:
    """
    전체 밝기(luminance) 계산.
    Y = 0.299 R + 0.587 G + 0.114 B
    """
    stat = ImageStat.Stat(img)
    r, g, b = stat.mean[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b


def _pick_contrast_colors(luma: float) -> tuple[str, str, str]:
    """
    전체 밝기가 어두우면 → 밝은 텍스트
    전체 밝기가 밝으면 → 어두운 텍스트
    """
    # 임계값은 경험치로 130 근처에 둔다.
    if luma < 130:
        # 배경이 어두운 편 → 밝은 텍스트
        name_color = "#FFFFFF"   # 제목
        period_color = "#F5F5F5" # 기간
        location_color = "#EAEAEA"  # 장소
    else:
        # 배경이 밝은 편 → 어두운 텍스트
        name_color = "#000000"
        period_color = "#222222"
        location_color = "#333333"

    return name_color, period_color, location_color


def recommend_colors_for_banner(
    banner_type: str,
    image_path: str,
    festival_name_placeholder: str,
    festival_period_placeholder: str,
    festival_location_placeholder: str,
) -> Dict[str, str]:
    """
    배너 전체 밝기를 기준으로, 제목/기간/장소에 사용할 텍스트 색상을 추천한다.

    현재는 전체 평균 밝기 기준 단순 로직이며,
    나중에 banner_type 이나 placeholder 길이에 따라
    차별화된 색상 규칙을 추가할 수 있도록 인터페이스만 열어 둔다.
    """
    try:
        img = _load_image(image_path)
        # 연산량 줄이기 위해 축소본으로만 통계 계산
        img_thumb = img.copy()
        img_thumb.thumbnail((256, 256))
        luminance = _compute_luminance(img_thumb)
        name_color, period_color, location_color = _pick_contrast_colors(luminance)
    except Exception as e:
        # 분석 실패 시 기본값 (가독성 안전한 조합으로 폴백)
        print(f"[banner_color_recommend] failed to analyze image: {e}")
        name_color, period_color, location_color = "#000000", "#FFFFFF", "#FFFFFF"

    return {
        "festival_color_name_placeholder": name_color,
        "festival_color_period_placeholder": period_color,
        "festival_color_location_placeholder": location_color,
    }
