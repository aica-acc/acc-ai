# -*- coding: utf-8 -*-
# app/service/poster_khs/poster_image_builder.py
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Literal, Tuple

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont


# -------------------- OpenAI 클라이언트 --------------------
_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """OPENAI_API_KEY 를 사용해 전역 클라이언트를 하나만 만든다."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


# -------------------- 환경 기본값 --------------------
def _default_final_poster_dir() -> Path:
    """
    최종 포스터 이미지를 저장할 기본 경로.
    - POSTER_FINAL_SAVE_DIR 환경변수 우선
    - 없으면 C:/final_project/ACC/assets/posters/final 사용
    """
    return Path(
        os.getenv(
            "POSTER_FINAL_SAVE_DIR",
            "C:/final_project/ACC/assets/posters/final",
        )
    )


def _load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    POSTER_FONT_PATH 환경변수가 있으면 그 폰트를 사용하고,
    없으면 PIL 기본 폰트를 사용한다.
    """
    font_path = os.getenv("POSTER_FONT_PATH")
    if font_path and Path(font_path).is_file():
        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            pass
    # fallback
    return ImageFont.load_default()


def _parse_color(color_str: str, default: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """
    '#RRGGBB' 또는 '#RRGGBBAA' 형태의 색상 문자열을 RGBA 튜플로 변환.
    잘못된 형식이면 default 반환.
    """
    if not isinstance(color_str, str):
        return default

    s = color_str.strip()
    if not s.startswith("#"):
        return default

    s = s[1:]
    try:
        if len(s) == 6:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            a = 255
        elif len(s) == 8:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            a = int(s[6:8], 16)
        else:
            return default
        return (r, g, b, a)
    except Exception:
        return default


# -------------------- LLM 레이아웃 프롬프트 --------------------
_LAYOUT_SYSTEM_INSTRUCTIONS = """
당신은 포스터 타이포그래피를 설계하는 전문 디자이너입니다.

역할:
- 세로형 포스터 배경 위에 제목, 기간, 장소를 어떻게 배치할지 레이아웃을 JSON 형식으로 설계합니다.
- 실제 텍스트를 그리는 것이 아니라, 어디에 어떤 크기와 색으로 둘지 "설계 정보"만 제공합니다.

반드시 지켜야 할 규칙:
1. 출력은 반드시 순수 JSON 객체 한 개만 포함해야 합니다. (설명 문장, 주석, 코드블록 금지)
2. JSON의 최상위 구조는 다음 키를 포함해야 합니다:
   {
     "title": { ... },
     "date": { ... },
     "location": { ... }
   }
3. 각 항목(title/date/location)은 다음 필드를 가집니다:
   - x, y: 0.0 ~ 1.0 사이의 부동소수점 숫자 (캔버스 기준 비율 좌표)
   - anchor: "center" | "left" | "right" 중 하나
   - font_size_ratio: 0.02 ~ 0.18 범위의 숫자 (캔버스 높이에 대한 비율)
   - color: "#RRGGBB" 또는 "#RRGGBBAA" 형식
   - shadow_color: "#RRGGBB" 또는 "#RRGGBBAA" 형식 (없으면 null 이나 생략 가능)
   - max_width_ratio: 0.3 ~ 0.95 범위의 숫자 (캔버스 너비 비율, 줄바꿈 참고용)
   - bg_box: {
       "enabled": true/false,
       "padding_ratio": 0.0 ~ 0.2,
       "color": "#RRGGBBAA",
       "radius_ratio": 0.0 ~ 0.2
     }
4. title 은 가장 큰 글씨로, 보통 포스터 상단 1/3 영역에 배치합니다.
5. date 와 location 은 보통 하단이나 중단의 흰 여백 또는 단순한 영역에
   서로 가까운 위치에 들어가도록 설계합니다.
6. 스타일(style)이 "2d", "3d", "photo", "abstract" 중 무엇이냐에 따라
   어울리는 색상 대비와 배치(중앙 정렬, 좌측 정렬 등)를 적절히 선택합니다.
7. JSON 이외의 문자는 절대 출력하지 마세요. (설명 문장, '```', 텍스트 등 금지)
"""


def _build_layout_with_llm(
    *,
    title: str,
    date: str,
    location: str,
    style: str,
    width: int,
    height: int,
    model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """
    LLM에게 포스터 텍스트(title/date/location)의 레이아웃 JSON을 설계하게 한다.
    실제 이미지는 건드리지 않고, 배치 정보만 반환.
    """
    client = get_openai_client()

    user_desc = (
        "다음은 세로형 축제 포스터에 들어갈 텍스트 정보입니다.\n\n"
        f"- title: {title}\n"
        f"- date: {date}\n"
        f"- location: {location}\n\n"
        "포스터 배경은 이미 생성되어 있으며, 전체 캔버스의 크기는 "
        f"width={width}, height={height} 픽셀입니다.\n"
        f"배경 스타일(style)은 '{style}' 입니다. "
        "이 정보와 일반적인 포스터 디자인 관례를 기반으로, "
        "제목/기간/장소의 위치와 크기, 색상, 박스 사용 여부를 JSON 형식으로 설계해 주세요.\n"
        "반드시 JSON 객체만 출력해야 하며, 위에서 설명한 스키마를 따라야 합니다."
    )

    response = client.responses.create(
        model=model,
        instructions=_LAYOUT_SYSTEM_INSTRUCTIONS,
        input=user_desc,
    )

    layout_str = response.output_text.strip()
    layout: Dict[str, Any] = json.loads(layout_str)  # JSON 파싱 실패시 예외 발생
    return layout


# -------------------- 텍스트 렌더링 유틸 --------------------
def _draw_text_element(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    text: str,
    spec: Dict[str, Any],
) -> None:
    """
    단일 텍스트 요소(title/date/location)를 layout spec 에 맞게 그린다.
    - spec: LLM 이 만든 JSON 중 해당 키(title 등)의 값
    """
    W, H = img.size

    x_ratio = float(spec.get("x", 0.5))
    y_ratio = float(spec.get("y", 0.5))
    anchor = str(spec.get("anchor", "center"))
    font_size_ratio = float(spec.get("font_size_ratio", 0.08))
    max_width_ratio = float(spec.get("max_width_ratio", 0.9))

    font_size = max(8, int(H * font_size_ratio))
    font = _load_font(font_size)

    # 텍스트 크기 측정 (단일 줄 기준)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    # 좌표 계산 (비율 → 절대)
    cx = x_ratio * W
    cy = y_ratio * H

    if anchor == "left":
        x = cx
        y = cy - text_h / 2
    elif anchor == "right":
        x = cx - text_w
        y = cy - text_h / 2
    else:  # center
        x = cx - text_w / 2
        y = cy - text_h / 2

    # 배경 박스
    bg_box_spec = spec.get("bg_box") or {}
    if bg_box_spec.get("enabled"):
        padding_ratio = float(bg_box_spec.get("padding_ratio", 0.05))
        radius_ratio = float(bg_box_spec.get("radius_ratio", 0.03))
        box_color_str = bg_box_spec.get("color", "#00000080")

        pad = padding_ratio * font_size
        rx = radius_ratio * font_size

        box_x0 = x - pad
        box_y0 = y - pad
        box_x1 = x + text_w + pad
        box_y1 = y + text_h + pad

        box_color = _parse_color(box_color_str, (0, 0, 0, 160))
        draw.rounded_rectangle(
            [box_x0, box_y0, box_x1, box_y1],
            radius=rx,
            fill=box_color,
        )

    # 그림자 색상
    shadow_color_str = spec.get("shadow_color") or "#00000080"
    shadow_color = _parse_color(shadow_color_str, (0, 0, 0, 128))

    # 글자 색상
    text_color_str = spec.get("color") or "#FFFFFFFF"
    text_color = _parse_color(text_color_str, (255, 255, 255, 255))

    # 약간의 그림자(아래/오른쪽으로 1~2px 정도)
    shadow_offset = max(1, font_size // 20)
    draw.text(
        (x + shadow_offset, y + shadow_offset),
        text,
        font=font,
        fill=shadow_color,
    )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=text_color,
    )


# -------------------- 메인 진입점 --------------------
def build_final_poster_image(
    *,
    background_path: str | Path,
    title: str,
    date: str,
    location: str,
    style: Literal["2d", "3d", "photo", "abstract"] = "2d",
    llm_model: str = "gpt-4.1-mini",
    output_dir: Optional[str | Path] = None,
    filename_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """
    1) 이미 생성된 배경 이미지(background_path)를 불러오고
    2) LLM으로 제목/기간/장소의 배치 레이아웃을 설계한 뒤
    3) 실제로 텍스트를 그려 최종 포스터 PNG를 저장한다.

    Parameters
    ----------
    background_path : str | Path
        Dreamina 등으로 생성된 배경 이미지 파일 경로.
    title, date, location : str
        포스터에 들어갈 텍스트.
    style : "2d" | "3d" | "photo" | "abstract"
        배경 스타일 정보 (레이아웃/색상 선택 참고용 메타데이터).
    llm_model : str
        레이아웃 설계를 위해 사용할 OpenAI LLM 모델 이름.
    output_dir : str | Path | None
        최종 포스터 저장 폴더. None 이면 _default_final_poster_dir() 사용.
    filename_prefix : str | None
        파일명 접두사. None 이면 "poster_final" 사용.

    Returns
    -------
    dict
        {
          "ok": True,
          "background_path": "...",
          "poster_path": "...",
          "poster_filename": "...",
          "width": ...,
          "height": ...,
          "layout": { ... LLM 이 설계한 JSON ... }
        }
    """
    bg_path = Path(background_path)
    if not bg_path.is_file():
        raise FileNotFoundError(f"background image not found: {bg_path}")

    # 1) 배경 이미지 로드
    bg_img = Image.open(bg_path).convert("RGBA")
    W, H = bg_img.size

    # 2) LLM으로 레이아웃 설계
    layout = _build_layout_with_llm(
        title=title,
        date=date,
        location=location,
        style=style,
        width=W,
        height=H,
        model=llm_model,
    )

    # 3) 텍스트 합성
    canvas = bg_img.copy()
    draw = ImageDraw.Draw(canvas, "RGBA")

    if title:
        _draw_text_element(canvas, draw, title, layout.get("title", {}))
    if date:
        _draw_text_element(canvas, draw, date, layout.get("date", {}))
    if location:
        _draw_text_element(canvas, draw, location, layout.get("location", {}))

    # 4) 저장
    out_dir = Path(output_dir) if output_dir is not None else _default_final_poster_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = filename_prefix or "poster_final"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{prefix}_{ts}.png"
    out_path = out_dir / out_name

    canvas.save(out_path, format="PNG")

    return {
        "ok": True,
        "background_path": bg_path.as_posix(),
        "poster_path": out_path.as_posix(),
        "poster_filename": out_name,
        "width": W,
        "height": H,
        "layout": layout,
    }
