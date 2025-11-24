# -*- coding: utf-8 -*-
"""
app/service/font_color/image_text_color_recommend.py

이미지 한 장을 보고 그 위에 올릴 텍스트 색상을 추천하는 공용 유틸.

- 입력
  - image_path: 텍스트가 올라갈 배경 이미지 경로 (로컬 파일)
  - slots: 필요한 텍스트 색상 개수 (예: 제목/기간/장소 = 3)

- 출력
  - 길이가 slots 인 HEX 색상 리스트 (예: ["#FFFFFF", "#F5F5F5", "#EAEAEA"])
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image, ImageStat


def _load_image(image_path: str) -> Image.Image:
    """이미지를 RGB로 로드."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"image not found: {p}")
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


def _pick_contrast_palette(luma: float, slots: int) -> List[str]:
    """
    배경 밝기에 따라 대비되는 텍스트 컬러 팔레트 선택.
    slots 개수만큼 잘라서 반환.
    """
    if slots <= 0:
        return []

    # 배경이 어두운 편 → 밝은 텍스트 팔레트
    if luma < 130:
        base = ["#FFFFFF", "#F5F5F5", "#EAEAEA", "#D8D8D8"]
    else:
        # 배경이 밝은 편 → 어두운 텍스트 팔레트
        base = ["#000000", "#222222", "#333333", "#444444"]

    if slots <= len(base):
        return base[:slots]

    # 부족하면 마지막 색을 반복해서 채운다.
    return base + [base[-1]] * (slots - len(base))


def recommend_text_colors_for_image(
    image_path: str,
    slots: int = 3,
) -> List[str]:
    """
    image_path 를 기반으로 전체 밝기를 보고,
    텍스트에 쓸 색상 slots개를 추천한다.

    예:
        colors = recommend_text_colors_for_image("banner.png", slots=3)
        name_color, period_color, location_color = colors
    """
    try:
        img = _load_image(image_path)
        # 연산량 줄이기 위해 축소본으로만 통계 계산
        img_thumb = img.copy()
        img_thumb.thumbnail((256, 256))
        luminance = _compute_luminance(img_thumb)
        colors = _pick_contrast_palette(luminance, slots)
    except Exception as e:
        # 분석 실패 시 가독성 안전한 기본 조합으로 폴백
        print(f"[image_text_color_recommend] failed to analyze image: {e}")
        if slots <= 0:
            return []
        # 기본: 제목은 진한 검정, 나머지는 흰색 계열
        base = ["#000000", "#FFFFFF", "#FFFFFF"]
        if slots <= len(base):
            return base[:slots]
        return base + [base[-1]] * (slots - len(base))

    return colors
