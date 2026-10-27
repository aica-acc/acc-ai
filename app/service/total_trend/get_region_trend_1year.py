import os
import json
import requests
import datetime
import random
import math
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from typing import List, Optional

from app.service.total_trend.trend_inputs import festival_terms, search_window

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# [수정 1] AI에게 요청할 데이터 모델에서 'trend_data' 제거
# (trend_data는 AI가 아니라 우리가 계산해서 넣을 것이므로 뺍니다)
class KeywordDetail(BaseModel):
    keyword: str
    description: str  
    score: int

class RegionAnalysisResult(BaseModel):
    word_cloud: List[KeywordDetail] 
    family: List[KeywordDetail]
    couple: List[KeywordDetail]
    healing: List[KeywordDetail]
    search_keywords: List[str]

# 1. LLM 분석 함수
def analyze_region_with_llm(keyword: str, host_name: str) -> RegionAnalysisResult:
    prompt = f"""
    주최 지역 '{host_name}'과 축제 '{keyword}'를 분석하세요.

    [미션 1: 워드클라우드 - 20개]
    - '{host_name}'와 '{keyword}'의 분위기, 특산물, 감성 단어 20개.
    - 점수(1~10).

    [미션 2: 타깃별 코스 (각 4개)]
    - family, couple, healing 타깃 맞춤 장소.

    [미션 3: 검색 키워드]
    - 네이버 데이터랩 조회용 대표 키워드 5개.

    JSON 형식을 준수하세요.
    """
    try:
        res = client.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "지역 축제 트렌드 분석가입니다."},
                {"role": "user", "content": prompt}
            ],
            response_format=RegionAnalysisResult
        )
        return res.choices[0].message.parsed
    except Exception as e:
        print(f"❌ LLM Error: {e}")
        # 에러 시 더미 데이터 반환
        dummy = KeywordDetail(keyword=f"{host_name}", description="분석 데이터 없음", score=5)
        return RegionAnalysisResult(
            word_cloud=[dummy], family=[dummy], couple=[dummy], healing=[dummy], 
            search_keywords=[f"{host_name} 여행"]
        )

# 2. 데이터 부족 시 '시뮬레이션 데이터' 생성 (Fallback)
def generate_fallback_trend(start_date_str: str):
    print("⚠️ 네이버 데이터 부족 -> 시뮬레이션 데이터 생성 (Fallback Logic 가동)")
    
    try:
        if start_date_str:
            base_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        else:
            base_date = datetime.date.today()
    except:
        base_date = datetime.date.today()

    weekly_data = []
    # 1년치 (52주) 생성
    for i in range(-26, 26): 
        current_date = base_date + datetime.timedelta(weeks=i)
        
        # 종모양(Gaussian) 곡선 생성
        peak_factor = math.exp(-(i**2) / 10) 
        
        # 1) 축제 관심도 (0~100)
        festival_value = 5 + (peak_factor * 85) + random.randint(-3, 3)
        
        # 2) 지역 관심도 (항상 어느정도 있음 + 축제때 약간 상승)
        region_value = 30 + (peak_factor * 15) + random.randint(-5, 5)

        weekly_data.append({
            "period": current_date.strftime("%Y-%m-%d"),
            "festival": round(max(0, festival_value), 1),
            "region": round(max(0, region_value), 1)
        })
    
    return weekly_data

# 3. [수정 2] 키워드별 미니 트렌드 생성 (Python 함수로 처리)
def generate_keyword_mini_trend(score: int):
    trends = []
    for i in range(7):
        # 점수가 높을수록 검색량도 높게 시뮬레이션
        val = (score * 8) + random.randint(10, 30)
        if i > 3: val -= random.randint(0, 10)
        trends.append({"day": f"D-{6-i}", "value": val})
    return trends

# 4. 메인 함수
def get_region_trend_1year(keyword: str, host_name: str, festival_start_date: str, title: str = ""):
    """
    host_name 은 지역(시·군) 이름 (trend_inputs.resolve_region_name 으로 정리된 값).
    반환의 simulated 가 True 면 region_weekly 는 실제 검색량이 아니라 예시 곡선이다.
    """
    print(f"\n[RegionTrend] 분석 요청: {host_name} vs {keyword} (Date: {festival_start_date})")
    terms = festival_terms(keyword, title) or [host_name]

    # (1) AI 분석 수행 (여기서는 trend_data 없이 순수 텍스트 정보만 가져옴)
    ai_result = analyze_region_with_llm(", ".join(terms), host_name)

    # (2) 네이버 데이터랩 요청 (지난 축제면 그 축제 시점 기준 1년)
    url = "https://openapi.naver.com/v1/datalab/search"
    start_date, end_date = search_window(festival_start_date)

    # 검색어 그룹 설정
    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "week",
        "keywordGroups": [
            {"groupName": "festival", "keywords": terms},
            {"groupName": "region", "keywords": [f"{host_name} 여행", f"{host_name} 가볼만한곳"]}
        ]
    }

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json; charset=utf-8"
    }

    weekly_data = []
    simulated, simulated_reason = False, None

    try:
        res = requests.post(url, headers=headers, data=json.dumps(body).encode("utf-8"), timeout=120)
        data = res.json()
        
        # 데이터 유효성 체크
        if "results" in data and len(data["results"]) >= 2:
            f_data = data["results"][0]["data"] # festival
            r_data = data["results"][1]["data"] # region
            
            total_f_val = sum([d["ratio"] for d in f_data])
            
            # 검색량이 너무 적으면(거의 0이면) 시뮬레이션으로 전환
            if total_f_val < 5: 
                print("📉 실제 검색량 매우 적음 -> 시뮬레이션 데이터 사용")
                raise Exception("Low Data Volume")

            # 날짜 매핑 병합
            date_map = {}
            for item in f_data: date_map[item["period"]] = {"festival": item["ratio"], "region": 0}
            for item in r_data:
                if item["period"] in date_map:
                    date_map[item["period"]]["region"] = item["ratio"]
                else:
                    date_map[item["period"]] = {"festival": 0, "region": item["ratio"]}
            
            for date in sorted(date_map.keys()):
                weekly_data.append({
                    "period": date,
                    "festival": date_map[date]["festival"],
                    "region": date_map[date]["region"]
                })
                
        else:
            raise Exception("No Data from Naver")

    except Exception as e:
        # 실제 데이터가 없으면 예시 곡선으로 대체하되, 예시임을 반드시 함께 돌려준다
        simulated = True
        simulated_reason = "검색량이 너무 적음" if str(e) == "Low Data Volume" else f"네이버 데이터랩 조회 실패: {e}"
        weekly_data = generate_fallback_trend(festival_start_date)

    # (3) [수정 3] AI 결과에 'trend_data' 수동 주입
    enriched_word_cloud = []
    if ai_result.word_cloud:
        for item in ai_result.word_cloud:
            item_dict = item.model_dump()
            # 여기서 trend_data를 생성해서 넣어줌 (AI가 아니라 코드가 함)
            item_dict['trend_data'] = generate_keyword_mini_trend(item.score)
            enriched_word_cloud.append(item_dict)

    return {
        "region_weekly": weekly_data,
        "simulated": simulated,
        "simulated_reason": simulated_reason,
        "search_terms": {"festival": terms, "region": [f"{host_name} 여행", f"{host_name} 가볼만한곳"]},
        "search_window": [start_date.isoformat(), end_date.isoformat()],
        "word_cloud": enriched_word_cloud,
        "family": [k.model_dump() for k in ai_result.family],
        "couple": [k.model_dump() for k in ai_result.couple],
        "healing": [k.model_dump() for k in ai_result.healing]
    }