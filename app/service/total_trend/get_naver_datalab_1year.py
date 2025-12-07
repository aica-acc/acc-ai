import os
import json
import requests
import datetime
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import List


load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


# ================================================================
# 1) LLM 키워드 확장
# ================================================================
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


# ================================================================
# 2) NAVER DATALAB – 1년치 검색량 분석
# ================================================================
def get_naver_datalab_1year(keyword: str, festival_title: str, festival_start_date: str):
    """
    네이버 DataLab 1년치 검색량 (주 단위).
    3개 파라미터 모두 반영된 버전.
    """
    print(f"\n[NaverDataLab] 1년 분석 시작: {keyword}, {festival_title}, {festival_start_date}")

    # -----------------------------
    # 1) LLM 기반 키워드 확장
    # -----------------------------
    expanded_keywords = expand_keywords_with_llm(keyword, festival_title, festival_start_date)

    url = "https://openapi.naver.com/v1/datalab/search"

    today = datetime.date.today()
    one_year_ago = today - datetime.timedelta(days=360)

    # -----------------------------
    # 2) DataLab Request Body
    # -----------------------------
    body = {
        "startDate": one_year_ago.strftime("%Y-%m-%d"),
        "endDate": today.strftime("%Y-%m-%d"),
        "timeUnit": "week",
        "keywordGroups": [
            {
                "groupName": keyword,
                "keywords": expanded_keywords
            }
        ]
    }

    json_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json; charset=utf-8"
    }

    # -----------------------------
    # 3) Request → Response
    # -----------------------------
    try:
        res = requests.post(url, headers=headers, data=json_bytes, timeout=120)
        res.encoding = "utf-8"

        data = res.json()

        # 네이버 API 에러 핸들링
        if "error" in data or "errorCode" in data:
            return {"error": data}

        # 주간 트렌드 데이터 변환
        weekly_data = []
        for item in data["results"][0]["data"]:
            weekly_data.append({
                "period": item["period"],
                "ratio": item["ratio"]
            })

        print("✔ Naver DataLab 1년 분석 완료")

        # 최종 반환 구조
        return {
            "naver_weekly": weekly_data,
        }

    except Exception as e:
        return {"error": f"Naver DataLab 오류: {e}"}





