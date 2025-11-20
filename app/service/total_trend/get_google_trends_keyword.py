import json
from typing import Dict, List
from pytrends.request import TrendReq
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------
# PyTrends 기본 초기화
# ---------------------------------------------------------
_PT = TrendReq(
    hl="ko-KR",
    tz=540,
    retries=3,
    backoff_factor=0.1,
)

# ---------------------------------------------------------
# LLM 기반 연관 키워드 생성 (이미 네가 만든 함수 그대로 사용)
# ---------------------------------------------------------
import os
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import List

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

class KeywordList(BaseModel):
    keywords: List[str]

def expand_keywords_with_llm(keyword: str, festival_title: str, festival_start_date: str) -> List[str]:
    prompt = f"""
    메인 키워드: "{keyword}"
    축제명: "{festival_title}"
    축제 시작일: "{festival_start_date}"

    위의 정보를 기반으로, **검색 트렌드 분석에 사용할 연관 키워드 5개**를 생성하세요.
    단어는 한단어로만 생성하고 대중적인 키워드를 생성하시오. google trens에 검색될 만한 키워드를 
    사용해야합니다 또한 첫번재 키워드는 반드시 메인키워드를 넣으세오 
    ex) > [크리스마스, 산타, 트리, 연말, 눈]
    반드시 5개의 문자열을 생성해야 합니다.
    """

    res = client.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "키워드 확장 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=KeywordList  # 🔥 구조 강제!
    )

    parsed: KeywordList = res.choices[0].message.parsed
    return parsed.keywords



# ---------------------------------------------------------
# 특정 키워드의 관련검색어(top/rising) 20개 추출
# ---------------------------------------------------------
def get_google_related_keywords(keyword: str) -> Dict[str, List[str]]:
    try:
        _PT.build_payload(
            kw_list=[keyword],
            timeframe="today 3-m",
            geo="KR",
        )

        rq = _PT.related_queries()
        if not rq or keyword not in rq:
            return {"top": [], "rising": []}

        info = rq[keyword]

        top_df = info.get("top")
        rising_df = info.get("rising")

        top_list = top_df["query"].tolist() if isinstance(top_df, pd.DataFrame) else []
        rising_list = rising_df["query"].tolist() if isinstance(rising_df, pd.DataFrame) else []

        return {
            "top": top_list[:20],
            "rising": rising_list[:20]
        }

    except Exception as e:
        print(f"❗ Google 연관검색어 오류 ({keyword}):", e)
        return {"top": [], "rising": []}


# ---------------------------------------------------------
# LLM 연관키워드 5개 → Google 연관검색어 5세트 생성
# ---------------------------------------------------------
def get_google_related_from_llm(
    keyword: str,
    festival_title: str,
    festival_start_date: str
) -> Dict[str, Dict[str, List[str]]]:

    expanded_keywords = expand_keywords_with_llm(keyword, festival_title, festival_start_date)

    result = {}

    for kw in expanded_keywords:
        related = get_google_related_keywords(kw)
        result[kw] = related

    return result


