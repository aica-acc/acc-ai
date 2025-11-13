# -*- coding: utf-8 -*-
"""
banner_trend_analysis/service_banner_trend_analysis.py

- /banner/analyze 에서 사용할 LLM 기반 현수막 트렌드 분석 서비스
- 입력: p_name, user_theme, keywords(list[str])
- 출력: JSON 객체(dict) 형태의 3개 섹션
    {
        "similar_theme_banner_analysis": "...",
        "evidence_and_effects": "...",
        "strategy_for_our_festival": "..."
    }
"""

from __future__ import annotations

from typing import List, Optional, Dict
import os
import json

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
    - 출력은 반드시 JSON 문자열이어야 함
    - 각 필드는 일반 텍스트(마크다운 금지), 문단 여러 개 허용
    """
    kw_str = ", ".join(k for k in keywords if k) if keywords else ""

    return f"""
아래는 한 축제의 기본 정보와 사용자가 입력한 기획 의도입니다.

- 축제명: {p_name}
- 기획 의도: {user_theme}
- 키워드: {kw_str if kw_str else "(지정된 키워드 없음)"}

이 정보를 바탕으로, 현수막 트렌드 분석 보고서를 3개의 섹션으로 나누어 작성하세요.

요구하는 3개의 섹션은 다음과 같습니다.

1) similar_theme_banner_analysis
   - 이 축제와 유사한 주제/계절/타깃을 가진 다른 축제들의 현수막·배너에서 자주 보이는 패턴을 분석합니다.
   - 색상, 레이아웃, 카피 길이, 사진·일러스트 사용 방식 등을 항목별로 정리하되,
     실제 특정 축제 이름이나 도시 이름, 브랜드명은 언급하지 않습니다.
   - 서술할 때는 "~이다"처럼 단정적으로 말하기보다
     "일반적으로 ~하는 경우가 많다", "여러 사례에서 ~하는 경향이 관찰된다"와 같이
     경향과 패턴을 중심으로 표현합니다.
   - "여러 사례에서", "많은 축제들이"와 같은 일반적인 표현을 사용하여 설명하고,
     왜 이런 패턴이 자주 사용되는지 설득력 있게 서술합니다.
   - 이 섹션의 마지막에는
     "이 내용은 개별 축제의 실제 통계가 아니라, 여러 사례에서 반복적으로 관찰되는 일반적인 디자인 패턴을 정리한 것입니다."
     와 같은 취지의 한 문장을 반드시 포함하세요.

2) evidence_and_effects
   - 위에서 설명한 트렌드가 어떤 효과를 만들어내는지, 근거와 함께 설명합니다.
   - 예를 들어,
       · 온라인 홍보(영상, SNS)에서 높은 조회수와 공유를 유도하는 방식인지,
       · 현장에서 사람들의 체류 시간, 사진 촬영 빈도, 동선 유도에 어떤 영향을 줄 수 있는지,
     와 같이 "어떤 지표에 긍정적인 영향을 줄 수 있는지"를 설명합니다.
   - 단, 구체적인 숫자(예: 123%, 3.2배, 100만 회 조회)나
     실제로 존재할 것 같은 특정 지명, 채널명, 축제명, 연도는 만들어내지 마세요.
     논문 제목, 기관 이름, 연구자 이름 등 구체적인 출처도 새로 지어내지 마세요.
   - 대신 "높은 조회수로 이어지는 경우가 많다", "체류 시간이 길어지는 경향이 있다",
     "사진 촬영이 활발해지는 사례가 자주 보고된다"와 같은
     질적인 표현과 일반적인 경험 법칙 수준의 근거로 설명합니다.
   - 문장 전체의 톤은 "보통 ~하는 경향이 있다", "여러 사례에서 ~한 결과가 보고된다"와 같이
     가능성을 열어 두는 방향으로 작성하고, 단정적인 표현은 피합니다.
   - 이 섹션의 마지막에는
     "다만, 이는 다양한 사례에서 관찰된 일반적인 경향일 뿐, 모든 축제에 동일하게 적용되는 것은 아닙니다."
     와 같은 취지의 한 문장을 반드시 포함하세요.

3) strategy_for_our_festival
   - 위 두 섹션의 내용을 종합하여, 이번 축제({p_name})의 현수막을 어떻게 설계하면 좋을지 제안합니다.
   - 색상 팔레트, 이미지/일러스트 선택 방향, 메인 카피 길이와 톤, 정보 배치 방식(예: 핵심 정보 우선 배치) 등으로 나누어 구체적으로 작성합니다.
   - 각 제안 옆에는 "왜 그런지"와 "예상되는 효과"를 함께 설명하세요.
     예: "가족 관람객이 많기 때문에 ○○한 색 조합이 친근하게 느껴질 수 있으며,
          현장에서 사진 찍기 좋은 배경이 되어 SNS 확산에 도움이 될 수 있습니다."
   - 이 섹션을 읽으면, 발표자가
     "우리는 이런 트렌드와 효과를 참고해서, 현수막을 이런 방향으로 설계하기로 했다"
     라고 설명할 수 있어야 합니다.
   - 또한 이 섹션의 마지막에는
     "여기에서 제안하는 방향은 앞에서 정리한 일반적인 패턴과 경향을 바탕으로 한 권고안이며,
      실제 현장 조건과 예산, 이해관계자 요구에 따라 조정될 수 있습니다."
     와 같은 취지의 한 문장을 반드시 포함하세요.


출력 형식에 대한 매우 중요한 요구 사항:
- 출력은 반드시 JSON 객체 하나만 포함하는 순수 텍스트여야 합니다.
- JSON 객체의 키는 정확히 다음 세 개입니다.
    1) "similar_theme_banner_analysis"
    2) "evidence_and_effects"
    3) "strategy_for_our_festival"
- 예시 형태:
    {{
      "similar_theme_banner_analysis": "첫 번째 섹션 내용...",
      "evidence_and_effects": "두 번째 섹션 내용...",
      "strategy_for_our_festival": "세 번째 섹션 내용..."
    }}
- 각 값은 한국어 일반 문장으로 된 문자열이며, 필요하면 여러 문단으로 구성해도 됩니다.
- 값 내부에서는 마크다운 문법(예: #, ##, ###, -, *)를 사용하지 마세요.
- 값 내부에서 단락을 나눌 때는 빈 줄을 사용하세요.
- 모든 문장은 보고서 형식의 공손한 존댓말 어투로 작성합니다.
  끝맺음은 "~합니다", "~입니다"와 같은 형태로 통일하고,
  "~한다", "~이다"와 같은 서술체/반말 어투는 사용하지 마세요.
- 구체적인 숫자, 실제 도시/축제/브랜드/채널 이름은 만들지 말고,
  일반적인 표현과 논리적인 설명을 통해 "근거"와 "예상 효과"를 서술하세요.

""".strip()


def analyze_banner_trend_with_llm(
    p_name: str,
    user_theme: str,
    keywords: List[str],
    model: Optional[str] = None,
) -> Dict[str, str]:
    """
    LLM을 호출해 현수막 트렌드 분석 리포트를 생성.
    - 반환값: 3개 섹션을 가진 dict
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
    text = content.strip() if content else ""

    # LLM이 반환한 JSON 문자열 파싱
    try:
        data = json.loads(text)
    except Exception as e:
        raise RuntimeError(f"LLM JSON 파싱 실패: {type(e).__name__}: {e}")

    # 기대하는 키가 모두 있는지 검증
    expected_keys = {
        "similar_theme_banner_analysis",
        "evidence_and_effects",
        "strategy_for_our_festival",
    }
    missing = expected_keys - set(data.keys())
    if missing:
        raise RuntimeError(f"LLM 응답 JSON에 필요한 키가 없습니다: {', '.join(sorted(missing))}")

    # 모든 값을 문자열로 강제
    result: Dict[str, str] = {}
    for k in expected_keys:
        v = data.get(k, "")
        result[k] = str(v) if v is not None else ""

    return result
