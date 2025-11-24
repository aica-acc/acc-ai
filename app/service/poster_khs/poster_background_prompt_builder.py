# app/service/poster_khs/poster_background_prompt_builder.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
from typing import Any, Dict, Optional

from openai import OpenAI

# 전역 클라이언트 (OPENAI_API_KEY는 환경변수에서 읽음)
_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """
    모듈 내부에서 사용할 OpenAI 클라이언트를 반환한다.
    - OPENAI_API_KEY는 환경변수로 설정되어 있다고 가정한다.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    return _client


# -------------------- 헬퍼: compact payload --------------------


def _norm(v: Any) -> str:
    return (str(v) if v is not None else "").strip()


def _build_compact_payload(analysis_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM에 넘길 '축제 핵심 정보'만 추린 축약 payload 생성.

    - festival_name: p_name > festival.title
    - theme: corrected_theme > original_theme > user_theme
    - date: festival.date
    - location: festival.location
    - keywords: analysis_payload.keywords
    - visual_keywords: festival.visual_keywords
    """
    festival = analysis_payload.get("festival") or {}
    analysis = analysis_payload.get("analysis") or {}

    p_name = _norm(analysis_payload.get("p_name"))
    festival_title = _norm(festival.get("title"))
    festival_name = p_name or festival_title

    user_theme = _norm(analysis_payload.get("user_theme"))
    corrected_theme = _norm(analysis.get("corrected_theme"))
    original_theme = _norm(analysis.get("original_theme"))
    theme = corrected_theme or original_theme or user_theme

    date = _norm(festival.get("date"))
    location = _norm(festival.get("location"))

    keywords = list(analysis_payload.get("keywords") or [])
    visual_keywords = list(festival.get("visual_keywords") or [])

    compact: Dict[str, Any] = {
        "festival_name": festival_name,
        "theme": theme,
        "date": date,
        "location": location,
        "keywords": keywords,
        "visual_keywords": visual_keywords,
    }
    return compact


# -------------------- 헬퍼: 스타일 지침 --------------------


def _style_instruction(style: str) -> str:
    """
    style 값에 따라 이미지 스타일 지침 문장을 돌려줌.
    허용 값:
      - "2d"       : 2D 일러스트 / 그래픽
      - "3d"       : 3D 렌더링 느낌
      - "photo"    : 실사 사진 느낌
      - "abstract" : 도형·색면 위주의 추상 배경
    그 외 값은 기본적으로 2D 일러스트로 취급.
    """
    s = (style or "").lower()

    if s == "3d":
        return (
            "이미지는 부드러운 3D 렌더링 스타일로, 입체적인 조명과 질감이 느껴지지만 과도하게 사실적이지 않게 표현합니다."
        )
    elif s == "photo":
        return (
            "이미지는 고해상도 실사 사진 느낌으로, 사실적인 조명과 질감, 자연스러운 구도를 사용합니다."
        )
    elif s == "abstract":
        return (
            "이미지는 구체적인 인물이나 건물을 최소화하고, 도형과 색면, 라인 위주의 추상적인 구성을 사용하여 분위기와 색감 위주로 표현합니다."
        )
    else:
        # 기본: 2D 일러스트
        return (
            "이미지는 2D 일러스트·그래픽 스타일로, 평면적인 색면과 단순한 형태를 사용하여 부드럽고 따뜻한 분위기를 표현합니다."
        )


# -------------------- LLM 시스템 인스트럭션 --------------------


_POSTER_SYSTEM_INSTRUCTIONS = """
당신은 축제 홍보를 위한 배경 이미지를 위한 프롬프트를 설계하는 전문 디자이너입니다.

역할:
- 입력으로 주어지는 축제 핵심 정보 JSON과 스타일 지침을 읽고,
  Dreamina 3.1과 같은 이미지 생성 모델에 전달할 '배경 전용' 프롬프트 한 문장을 작성합니다.
- 프롬프트는 한국어로만 작성합니다.

반드시 지켜야 할 규칙:
1. 이미지는 항상 '배경'만 생성해야 합니다.
   - 이미지 안에 어떤 형태의 텍스트도 포함되면 안 됩니다.
   - 한글/영어/숫자/기호/로고/간판 글씨/워터마크/서명 등 모든 글자를 금지합니다.

2. 나중에 축제명(title), 기간(date), 장소(location) 텍스트를 올릴 수 있도록
   - 이미지 안에 비교적 깨끗하고 단순한 영역을 한 곳 이상 남기도록 묘사해야 합니다.
   - 그 영역의 위치(상단/하단/좌/우)를 특정 값으로 고정하지 말고,
     자연스러운 구도 안에서 '텍스트를 배치하기 좋은 여백'이 있다는 것을 묘사하세요.

3. 축제의 분위기, 주요 장면, 참가자, 환경, 색감, 조명, 구도, 계절감 등을
   - 입력 JSON에 들어 있는 festival_name, theme, date, location, keywords, visual_keywords 정보를 바탕으로 자연스럽게 설명하되,
   - 축제명/기간/장소 문구 자체를 프롬프트에 그대로 적지 마세요.

4. 스타일(2D, 3D, 실사, 추상 등)은 입력 텍스트에 포함된 추가 지침(style_instruction)을 정확히 따르세요.

5. 입력 JSON에 있는 정보만 활용하고, 존재하지 않는 정보는 과도하게 상상해서 추가하지 마세요.
   (예: 눈, 비, 특정 도시 이름, 특정 캐릭터 등은 JSON에 관련 단서가 있을 때만 사용)

6. 최종 프롬프트 문장 안에는 아래 의미를 반드시 포함하세요.
   - 예: "텍스트나 글자가 전혀 없는 배경 이미지", "어떠한 글자나 로고도 없는 배경"과 같이,
     이미지에 글자·로고·숫자가 전혀 없어야 한다는 내용을 한국어로 명시적으로 적어야 합니다.

7. 최종 출력은 오직 '프롬프트 문장 한 줄'만 포함해야 합니다.
   - 앞뒤에 설명, 불릿, 따옴표, JSON 형식, 주석 등을 절대 붙이지 마세요.
   - 줄바꿈 없이 하나의 문장 또는 긴 문단으로만 출력하세요.
"""


# -------------------- 프롬프트 생성 --------------------


def build_poster_background_prompt_ko(
    analysis_payload: Dict[str, Any],
    *,
    model: str = "gpt-4.1-mini",
    style: str = "2d",
) -> str:
    """
    축제 기획서 분석 결과(analysis_payload)를 입력으로 받아,
    스타일 옵션에 맞는 배경 프롬프트(한국어 한 문장)를 생성한다.

    - style: "2d", "3d", "photo", "abstract" 등
    """

    client = get_openai_client()

    compact_payload = _build_compact_payload(analysis_payload)
    style_instruction = _style_instruction(style)

    input_text = (
        "다음 JSON은 축제의 핵심 정보입니다.\n\n"
        "이 정보를 기반으로, '배경 전용' 이미지를 생성하기 위한 프롬프트를 한국어로 한 문장 작성하세요.\n"
        "조건을 다시 정리합니다:\n"
        "1) 이미지는 텍스트나 글자가 전혀 없는 배경 이미지가 되어야 합니다.\n"
        "2) 나중에 축제명, 기간, 장소 텍스트를 올릴 수 있도록, 이미지 안에 비교적 깨끗하고 단순한 여백 영역이 하나 이상 존재하도록 묘사하세요.\n"
        "3) 아래 JSON에 있는 festival_name, theme, date, location, keywords, visual_keywords 정보만 활용하여 축제의 분위기와 장면을 자연스럽게 표현하세요.\n"
        "4) 축제명/기간/장소 문구 자체를 프롬프트에 그대로 적지 마세요.\n"
        f"5) 이미지 스타일은 다음 지침을 따르세요:\n{style_instruction}\n"
        "6) 출력은 프롬프트 문장 한 줄만 작성하고, 다른 설명이나 포맷은 포함하지 마세요.\n\n"
        f"축제 핵심 정보 JSON:\n{json.dumps(compact_payload, ensure_ascii=False, indent=2)}"
    )

    response = client.responses.create(
        model=model,
        instructions=_POSTER_SYSTEM_INSTRUCTIONS,
        input=input_text,
    )

    prompt_ko = response.output_text.strip()
    return prompt_ko


# -------------------- Dreamina input 빌더 --------------------


def build_poster_background_dreamina_input(
    analysis_payload: Dict[str, Any],
    *,
    width: int = 1536,
    height: int = 2048,
    resolution: str = "2K",
    aspect_ratio: str = "3:4",
    use_pre_llm: bool = False,
    llm_model: str = "gpt-4.1-mini",
    style: str = "2d",
) -> Dict[str, Any]:
    """
    기획서 분석 결과(analysis_payload)를 기반으로

    1) OpenAI LLM으로 배경 프롬프트(prompt)를 만들고
    2) Dreamina 3.1에 바로 넣을 수 있는 input dict를 반환한다.
    """

    prompt_ko = build_poster_background_prompt_ko(
        analysis_payload=analysis_payload,
        model=llm_model,
        style=style,
    )

    dreamina_input: Dict[str, Any] = {
        "width": width,
        "height": height,
        "prompt": prompt_ko,
        "resolution": resolution,
        "use_pre_llm": use_pre_llm,
        "aspect_ratio": aspect_ratio,
    }
    return dreamina_input
