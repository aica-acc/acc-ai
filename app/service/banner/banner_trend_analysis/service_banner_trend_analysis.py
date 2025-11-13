# -*- coding: utf-8 -*-
"""
banner_trend_analysis/service_banner_trend_analysis.py

- /banner/analyze 에서 사용할 LLM 기반 현수막 트렌드 분석 서비스
- 입력: p_name, user_theme, keywords(list[str])
- 출력: 3단락 Markdown 텍스트 (문장 내용은 LLM이 모두 작성)
"""

from __future__ import annotations

from typing import List, Optional
import os

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # openai 패키지 없는 환경 방어용


SYSTEM_MSG = (
    "당신은 지역 축제와 야외 이벤트의 현수막/배너를 기획·자문하는 시각디자인 컨설턴트입니다. "
    "항상 한국어로 답변하세요."
)


def build_banner_trend_prompt(
    p_name: str,
    user_theme: str,
    keywords: List[str],
) -> str:
    """
    LLM에 줄 프롬프트 텍스트.
    - 마크다운(###, -, *) 금지
    - 1/2/3 번으로 시작하는 일반 텍스트 단락을 생성하도록 안내
    """
    kw_str = ", ".join(k for k in keywords if k) if keywords else ""

    return f"""
아래는 한 축제의 기본 정보와 사용자가 입력한 기획 의도입니다.

- 축제명: {p_name}
- 기획 의도: {user_theme}
- 키워드: {kw_str if kw_str else "(지정된 키워드 없음)"}

위 정보를 바탕으로, 다음 형식을 가진 한국어 보고서를 작성하세요.

1. 첫 번째 단락 제목: "1. 유사 축제 현수막 트렌드"
   - 이 축제와 유사한 주제/계절/타깃을 가진 다른 축제들의 현수막·배너에서 자주 보이는 패턴을 정리하세요.
   - 색상, 레이아웃, 카피 길이, 사진·일러스트 사용 방식 등을 항목별로 설명하세요.
   - 구체적인 수치(%, 상위 N개 등)나 특정 축제/도시 이름을 꾸며내지 말고,
     "여러 사례에서", "많은 축제들이"와 같은 일반적인 표현으로 근거를 제시하세요.

2. 두 번째 단락 제목: "2. 이러한 트렌드가 만들어낸 효과"
   - 위에서 설명한 패턴들이 관람객 인지도, 정보 전달력, 사진 찍기 좋은 포인트 제공 등에
     어떤 긍정적/부정적 효과를 주는지 설명하세요.
   - 가짜 통계나 실제로 존재할 것 같은 숫자/지명은 쓰지 말고,
     질적인 표현 위주의 근거를 서술하세요.

3. 세 번째 단락 제목: "3. 이번 축제를 위한 현수막 방향 제안"
   - 위 축제 정보를 충분히 반영하여,
     색상·사진/일러스트 선택·메인 카피 길이·정보 배치 방식 등으로 나누어 구체적으로 제안하세요.
   - 각 제안 옆에는 '왜 그런지' 간단한 이유를 붙이세요.

출력 형식에 대한 요구 사항:
- 전체 결과를 하나의 일반 텍스트로 작성합니다.
- 마크다운 문법(예: #, ##, ###, -, *, 글머리 기호 등)을 사용하지 마세요.
- 각 단락은 다음과 같이 시작해야 합니다.
  - 첫 줄: "1. 유사 축제 현수막 트렌드"
  - 두 번째 단락 첫 줄: "2. 이러한 트렌드가 만들어낸 효과"
  - 세 번째 단락 첫 줄: "3. 이번 축제를 위한 현수막 방향 제안"
- 각 단락 사이에는 빈 줄을 한 줄 넣어 단락을 분리하세요.
- 번호 외에는 특수한 서식 없이, 일반 문장으로만 구성하세요.
- 모든 내용은 한국어로 작성합니다.
- 숫자나 실제 지명·축제명을 새로 만들어내지 말고, 일반적인 표현으로 근거를 설명합니다.
""".strip()

def analyze_banner_trend_with_llm(
    p_name: str,
    user_theme: str,
    keywords: List[str],
    model: Optional[str] = None,
) -> str:
    """
    LLM을 호출해 현수막 트렌드 분석 리포트를 생성.
    - 하드코딩된 결과 문장 없음
    - 실패 시 RuntimeError를 발생시켜 상위에서 HTTPException 처리
    """
    if OpenAI is None:
        raise RuntimeError("openai 패키지가 없습니다. `pip install openai` 후 다시 시도하세요.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

    client = OpenAI(api_key=api_key)

    model_name = model or os.getenv("OPENAI_TREND_MODEL")
    if not model_name:
        raise RuntimeError(
            "LLM 모델 이름이 지정되지 않았습니다. "
            "환경변수 OPENAI_TREND_MODEL 에 사용할 모델 이름을 설정하세요."
        )

    prompt = build_banner_trend_prompt(p_name=p_name, user_theme=user_theme, keywords=keywords)

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
    )

    content = resp.choices[0].message.content if resp.choices else ""
    return content.strip() if content else ""
