# poster_background_prompt_builder.py
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
    - 필요하면 이 함수를 수정해서 프록시나 base_url 등을 붙이면 됨.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
        )
    return _client


# LLM에게 줄 '역할 설명' (메타 가이드라인만, 축제 내용은 전혀 넣지 않음)
_POSTER_SYSTEM_INSTRUCTIONS = """
당신은 축제 포스터 '배경 이미지'를 위한 프롬프트를 설계하는 전문 디자이너입니다.

역할:
- 입력으로 주어지는 축제 기획서 분석 JSON을 읽고,
  Dreamina 3.1과 같은 이미지 생성 모델에 전달할 포스터 '배경 전용' 프롬프트 한 문장을 작성합니다.
- 프롬프트는 한국어로만 작성합니다.

반드시 지켜야 할 규칙:
1. 이미지는 '포스터 배경'만 생성해야 합니다.
   - 이미지 안에 어떤 형태의 텍스트도 포함되면 안 됩니다.
   - 한글/영어/숫자/기호/로고/간판 글씨/워터마크/서명 등 모든 글자를 금지합니다.
2. 나중에 포스터 제목, 날짜, 장소 등을 올릴 수 있도록
   - 이미지 안에 비교적 깨끗하고 단순한 영역을 한 곳 이상 남기도록 묘사해야 합니다.
   - 그 영역의 위치(상단/하단/좌/우)를 특정 값으로 고정하지 말고,
     자연스러운 구도 안에서 '텍스트를 배치하기 좋은 여백'이 있다는 것을 묘사하세요.
3. 축제의 분위기, 주요 장면, 참가자, 환경, 색감, 조명, 구도, 계절감 등을
   - 입력 JSON의 정보를 바탕으로 자연스럽게 설명하되,
   - 포스터에 들어갈 제목/날짜/장소 등의 구체적인 문구 자체는 프롬프트에 포함하지 마세요.
4. 입력 JSON에 있는 내용만 활용하고, 존재하지 않는 정보는 과도하게 상상해서 추가하지 마세요.
   (예: 눈, 비, 특정 도시 이름, 특정 캐릭터 등은 JSON에 관련 단서가 있을 때만 사용)
5. Dreamina 가이드라인에 맞게:
   - 장면(무엇이, 어디서, 어떤 분위기인지)을 자연어 문장으로 설명하고,
   - 색감, 조명, 구도, 스타일 등은 짧고 명확한 표현으로 덧붙입니다.
6. 최종 출력은 오직 '프롬프트 문장 한 줄'만 포함해야 합니다.
   - 앞뒤에 설명, 불릿, 따옴표, JSON 형식, 주석 등을 절대 붙이지 마세요.
   - 줄바꿈 없이 하나의 문장 또는 긴 문단으로만 출력하세요.
"""


def build_poster_background_prompt_ko(
    analysis_payload: Dict[str, Any],
    *,
    model: str = "gpt-4.1-mini",
) -> str:
    """
    축제 기획서 분석 결과(analysis_payload)를 입력으로 받아,
    Dreamina 3.1용 포스터 배경 프롬프트(한국어 한 문장)를 생성한다.

    - 프롬프트 내용은 전부 LLM이 판단해서 작성한다.
    - 이 함수는 프롬프트 한 줄만 반환하며, 나머지(width, height, aspect_ratio 등)는
      호출하는 쪽에서 별도로 설정한다.
    """

    client = get_openai_client()

    # LLM에게 넘길 입력 텍스트:
    # - JSON 전체를 그대로 보여주고
    # - 우리가 원하는 조건을 한국어로 명확히 설명
    input_text = (
        "다음 JSON은 축제 기획서 분석 결과입니다.\n\n"
        "이 정보를 기반으로, 포스터 '배경 전용' 이미지를 생성하기 위한 프롬프트를 한국어로 한 문장 작성하세요.\n"
        "조건을 다시 정리합니다:\n"
        "1) 이미지는 포스터 배경만 생성하며, 이미지 안에는 텍스트, 글자, 숫자, 로고, 간판 글씨, 워터마크 등이 전혀 보이면 안 됩니다.\n"
        "2) 나중에 제목과 일정, 장소 등의 텍스트를 올릴 수 있도록, 이미지 안에 비교적 깨끗하고 단순한 여백 영역이 하나 이상 존재하도록 묘사하세요.\n"
        "3) 축제의 분위기, 주요 장면, 환경, 색감, 조명, 구도, 계절감 등을 이 JSON에서 유추할 수 있는 정보만 활용하여 자연스럽게 표현하세요.\n"
        "4) 포스터에 들어갈 실제 문구(제목, 날짜, 장소 이름 등)는 프롬프트에 쓰지 마세요.\n"
        "5) 출력은 프롬프트 문장 한 줄만 작성하고, 다른 설명이나 포맷은 포함하지 마세요.\n\n"
        f"축제 기획서 분석 JSON:\n{json.dumps(analysis_payload, ensure_ascii=False, indent=2)}"
    )

    response = client.responses.create(
        model=model,
        instructions=_POSTER_SYSTEM_INSTRUCTIONS,
        input=input_text,
    )

    # responses.create의 헬퍼: 전체 텍스트 결과
    prompt_ko = response.output_text.strip()
    return prompt_ko

def build_poster_background_dreamina_input(
    analysis_payload: Dict[str, Any],
    *,
    width: int = 1536,
    height: int = 2048,
    resolution: str = "2K",
    aspect_ratio: str = "3:4",
    use_pre_llm: bool = True,
    llm_model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """
    기획서 분석 결과(analysis_payload)를 기반으로

    1) OpenAI LLM으로 포스터 배경 프롬프트(prompt)를 만들고
    2) Dreamina 3.1에 바로 넣을 수 있는 input dict를 반환한다.

    - 텍스트/로고는 프롬프트 쪽에서 이미 금지 규칙을 포함하고 있음
    - width/height/aspect_ratio/resolution/use_pre_llm 은 호출 시 바꿀 수 있고,
      여기 값들은 기본값일 뿐 하드코딩 문구(텍스트)가 아님.
    """

    prompt_ko = build_poster_background_prompt_ko(
        analysis_payload=analysis_payload,
        model=llm_model,
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
