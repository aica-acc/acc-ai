# -*- coding: utf-8 -*-
"""
app/service/banner_khs/make_streetlamp_banner.py

가로등(1:3) 세로 현수막용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 모듈.

역할
- 참고용 포스터 이미지(URL)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 한글 자리수에 맞춘 플레이스홀더 텍스트(라틴 알파벳 시퀀스)를 사용해서
     1:3 세로 가로등 현수막 프롬프트를 조립한다. (write_streetlamp_banner)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_streetlamp_banner)

전제 환경변수
- OPENAI_API_KEY               : OpenAI API 키
- BANNER_LLM_MODEL             : (선택) 기본값 "gpt-4o-mini"
- STREETLAMP_BANNER_MODEL      : (선택) 기본값 "bytedance/seedream-4"
- STREETLAMP_BANNER_SAVE_DIR   : (선택) 기본값 "app/data/streetlamp_banner"
"""

from __future__ import annotations

import os
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import requests
import replicate
from replicate.exceptions import ModelError

# 기존 road_banner 유틸 재사용
from app.service.banner_khs.make_road_banner import (
    _build_placeholder_from_hangul,
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _extract_poster_url_from_input,
    _save_image_from_file_output,
)

# -------------------------------------------------------------
# 1) 영어 씬 묘사 + 플레이스홀더 텍스트 → 세로 가로등 현수막 프롬프트
# -------------------------------------------------------------
def _build_streetlamp_banner_prompt_en(
    name_text: str,
    period_text: str,
    location_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)
    name_text = _norm(name_text)
    period_text = _norm(period_text)
    location_text = _norm(location_text)

    prompt = (
        f"Tall 1:3 vertical illustration of {base_scene_en}, "
        "using the attached poster image only as reference for bright colors, lighting and atmosphere "
        f"but creating a completely new scene with {details_phrase_en}. "
        "Design this image as a clean standalone 1:3 vertical festival banner artwork, "
        "not shown hanging on any streetlamp, pole, wire, wall, or building, and with no surrounding street or environment. "
        "Leave small safe margins at the very top and bottom so that no important text is cut off when the banner is printed or trimmed. "

        "In the upper central area of the banner, place exactly three horizontal lines of text, all perfectly center-aligned. "
        "Arrange them so that the middle title line has generous vertical spacing above and below it, "
        "clearly separated from the other two lines, while the top and bottom lines stay relatively close together as a compact pair, "
        "so that the period and location do not feel far apart from each other. "

        f"On the middle line, write \"{name_text}\" in extremely large, ultra-bold sans-serif letters, "
        "the largest text in the entire image and clearly readable from a very long distance. "
        f"On the top line, above the title, write \"{period_text}\" in smaller bold sans-serif letters. "
        f"On the bottom line, below the title, write \"{location_text}\" in a size slightly smaller than the top line. "
        "All three lines must be drawn in the foremost visual layer, clearly on top of every background element, "
        "character, object, and effect in the scene, and nothing may overlap, cover, or cut through any part of the letters. "
        "Draw exactly these three lines of text once each. Do not draw any second copy, shadow copy, reflection, "
        "mirrored copy, outline-only copy, blurred copy, or partial copy of any of this text anywhere else in the image, "
        "including on the ground, sky, buildings, decorations, or interface elements. "
        "Do not add any other text at all: no extra words, labels, dates, numbers, logos, watermarks, or UI elements "
        "beyond these three lines. "
        "Do not place the text on any separate banner, signboard, panel, box, frame, ribbon, or physical board; "
        "draw only clean floating letters directly over the background. "
        "The quotation marks in this prompt are for instruction only; do not draw quotation marks in the final image."
    )



    return prompt.strip()


# -------------------------------------------------------------
# 2) write_streetlamp_banner: Seedream 입력 JSON 생성 (+ 플레이스홀더 포함)
# -------------------------------------------------------------
def write_streetlamp_banner(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    가로등(1:3) 세로 현수막용 Seedream 입력 JSON을 생성한다.

    입력:
        poster_image_url    : 참고용 포스터 이미지 URL
        festival_name_ko    : 축제명 (한글)
        festival_period_ko  : 축제 기간 (한글 또는 숫자/영문)
        festival_location_ko: 축제 장소 (한글 또는 영문)
    """

    # 1) 한글 축제 정보 → 영어 번역 (씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 2) 자리수 맞춘 플레이스홀더 + 원본 한글 텍스트 보존
    placeholders: Dict[str, str] = {
        # 축제명: A부터 시작하는 시퀀스
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        # 축제기간: 숫자/기호는 그대로, 한글만 C부터 시작하는 시퀀스
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        # 축제장소: B부터 시작하는 시퀀스
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "B"
        ),
        # 🔹 원본 한글 텍스트도 그대로 같이 넣어줌 (나중에 폰트/색상 추천용)
        "festival_base_name_placeholder": str(festival_name_ko or ""),
        "festival_base_period_placeholder": str(festival_period_ko or ""),
        "festival_base_location_placeholder": str(festival_location_ko or ""),
    }

    # 3) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립 (세로용)
    prompt = _build_streetlamp_banner_prompt_en(
        name_text=placeholders["festival_name_placeholder"],
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    #   - 1:3 비율 예시: width=1024, height=3072
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": 1024,
        "height": 3072,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "match_input_image",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        "image_input": [
            {
                "type": "image_url",
                "url": poster_image_url,
            }
        ],
    }

    # 🔹 플레이스홀더 + 원본 한글도 같이 포함
    seedream_input.update(placeholders)

    return seedream_input


# -------------------------------------------------------------
# 3) create_streetlamp_banner: Seedream JSON → Replicate 호출 → 이미지 저장
#     + 플레이스홀더까지 같이 반환
# -------------------------------------------------------------
def create_streetlamp_banner(seedream_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    /streetlamp-banner/write 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL을 추출하고,
    2) 그 이미지를 다운로드해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4)에 prompt + image_input과 함께 전달해
       실제 1:3 세로 가로등 현수막 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.
    """

    # 🔹 입력 JSON에서 플레이스홀더 + 원본 한글 그대로 꺼냄
    festival_name_placeholder = str(seedream_input.get("festival_name_placeholder", ""))
    festival_period_placeholder = str(
        seedream_input.get("festival_period_placeholder", "")
    )
    festival_location_placeholder = str(
        seedream_input.get("festival_location_placeholder", "")
    )

    festival_base_name_placeholder = str(
        seedream_input.get("festival_base_name_placeholder", "")
    )
    festival_base_period_placeholder = str(
        seedream_input.get("festival_base_period_placeholder", "")
    )
    festival_base_location_placeholder = str(
        seedream_input.get("festival_base_location_placeholder", "")
    )

    # 1) 포스터 URL 추출
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL이 없습니다.")

    # 2) 포스터 이미지 다운로드 → 파일 객체
    resp = requests.get(poster_url, timeout=30)
    resp.raise_for_status()
    img_bytes = resp.content
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", 1024))
    height = int(seedream_input.get("height", 3072))
    max_images = int(seedream_input.get("max_images", 1))
    aspect_ratio = seedream_input.get("aspect_ratio", "match_input_image")
    enhance_prompt = bool(seedream_input.get("enhance_prompt", True))
    sequential_image_generation = seedream_input.get(
        "sequential_image_generation", "disabled"
    )

    replicate_input = {
        "size": size,
        "width": width,
        "height": height,
        "prompt": prompt,
        "max_images": max_images,
        "image_input": [image_file],  # Replicate에는 실제 파일 객체로 전달
        "aspect_ratio": aspect_ratio,
        "enhance_prompt": enhance_prompt,
        "sequential_image_generation": sequential_image_generation,
    }

    model_name = os.getenv("STREETLAMP_BANNER_MODEL", "bytedance/seedream-4")

    # 🔁 Seedream / Replicate 일시 오류(PA 등)에 대비한 재시도 로직
    output = None
    last_err: Exception | None = None

    for attempt in range(3):  # 최대 3번까지 시도
        try:
            output = replicate.run(model_name, input=replicate_input)
            break  # 성공하면 루프 탈출
        except ModelError as e:
            msg = str(e)
            # Prediction interrupted; please retry (code: PA) 같은 일시 오류만 재시도
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            # 그 외 ModelError는 그대로 넘김
            raise RuntimeError(
                f"Seedream model error during streetlamp banner generation: {e}"
            )
        except Exception as e:
            # 네트워크 등 다른 예외는 바로 실패
            raise RuntimeError(
                f"Unexpected error during streetlamp banner generation: {e}"
            )

    # 3번 모두 실패한 경우
    if output is None:
        raise RuntimeError(
            f"Seedream model error during streetlamp banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    save_base = Path(
        os.getenv("STREETLAMP_BANNER_SAVE_DIR", "app/data/streetlamp_banner")
    ).resolve()
    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix="streetlamp_banner_"
    )

    # 🔹 여기서 플레이스홀더 + 원본 한글까지 같이 반환
    return {
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "festival_name_placeholder": festival_name_placeholder,
        "festival_period_placeholder": festival_period_placeholder,
        "festival_location_placeholder": festival_location_placeholder,
        "festival_base_name_placeholder": festival_base_name_placeholder,
        "festival_base_period_placeholder": festival_base_period_placeholder,
        "festival_base_location_placeholder": festival_base_location_placeholder,
    }
