from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional

import json

from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
    
def build_prompt_for_review(
    references: List[Dict[str, Any]],
    user_theme: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    target_category: str = "카드뉴스"
) -> Dict[str, str]:

    ref_summaries = []
    for ref in references:
        s = ref["score"]
        ref_summaries.append({
            "festival_name": ref.get("festival_name"),
            "category": ref.get("category"),
            "title": ref.get("title"),
            "total_score": s.get("total_score"),
            "clarity": {
                "score": s.get("clarity_score"),
                "desc": s.get("clarity_description"),
            },
            "color_harmony": {
                "score": s.get("color_harmony_score"),
                "desc": s.get("color_harmony_description"),
            },
            "balance": {
                "score": s.get("balance_score"),
                "desc": s.get("balance_description"),
            }
        })

    keywords_text = ", ".join(keywords or [])

    prompt = ChatPromptTemplate.from_template("""
너는 축제 홍보 카드뉴스 전문 디자이너다.

아래 레퍼런스의 스타일·색감·톤을 추출해서,
Text-to-Image 배경 생성을 위한 프롬프트를 만들어라.

단, 프롬프트는 "영문"으로 작성한다.

[기획 의도]
{user_theme}

[키워드]
{keywords_text}

[레퍼런스 요약]
{ref_summaries}

출력(JSON ONLY):
{{
  "visual_prompt": "<영문 프롬프트>",
  "style_name": "<한국어 스타일 이름>"
}}
    """)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
    msgs = prompt.format_messages(
        user_theme=user_theme or "기획의도 없음",
        keywords_text=keywords_text,
        ref_summaries=json.dumps(ref_summaries, ensure_ascii=False)
    )

    result = llm.invoke(msgs)
    try:
        data = json.loads(result.content)
    except:
        data = {"visual_prompt": result.content, "style_name": "자동"}

    return data
