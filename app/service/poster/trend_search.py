# trend_search.py (v17: 모든 '외부 실시간 트렌드' 수집기)

import os
import json
import requests
import datetime
from dotenv import load_dotenv
from pytrends.request import TrendReq

# --- API 키 설정 ---
load_dotenv()

# [v17] 네이버 API 키 로드 (pdf_tools.py에서 이관)
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
    print("[trend_search] 경고: .env 파일에 NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다.")
    print("    (네이버 실시간 트렌드 분석이 불가능합니다)")

# ----------------------------------------------------
# 기능 1: Google 트렌드 분석기 (pdf_tools.py에서 이관)
# ----------------------------------------------------
def get_google_trends(keywords_list):
    """
    (v17) 키워드 리스트를 받아서, Google 트렌드 데이터를 딕셔너리로 반환합니다.
    (pytrends는 비공식 API라 429 에러가 발생할 수 있습니다.)
    """
    print(f"  [trend_search] 1. Google 트렌드 분석 시작: {keywords_list}")
    
    if not keywords_list:
        return {"error": "분석할 키워드가 없습니다."}
        
    try:
        pytrends = TrendReq(hl='ko-KR', tz=540)
        pytrends.build_payload(keywords_list[:5], cat=0, timeframe='today 12-m', geo='KR')
        
        related_queries_dict = pytrends.related_queries()
        
        top_related = {}
        for kw in keywords_list[:5]:
            top_queries = related_queries_dict.get(kw, {}).get('top')
            if top_queries is not None and not top_queries.empty:
                top_related[kw] = top_queries['query'].head(5).tolist()
            else:
                top_related[kw] = []

        return {
            "analyzed_keywords": keywords_list[:5],
            "top_related_queries": top_related
        }

    except Exception as e:
        print(f" Google 트렌드 분석 중 오류 발생: {e}")
        return {"error": f"트렌드 분석 오류: {e}"}

# ----------------------------------------------------
# 기능 2: Naver 데이터랩 분석기 (검색량) (v15)
# ----------------------------------------------------
def get_naver_datalab_trend(keyword):
    """
    (v17) 네이버 데이터랩 API를 호출하여
    지난 3개월간의 '검색량 트렌드'를 JSON으로 반환합니다.
    """
    print(f"  [trend_search] 2. Naver 데이터랩 (검색량) 분석 시작: {keyword}")

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "네이버 API 키가 .env에 설정되지 않았습니다."}
    if not keyword:
        return {"error": "분석할 키워드가 없습니다."}

    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    today = datetime.date.today()
    three_months_ago = today - datetime.timedelta(days=90)
    
    body = {
        "startDate": three_months_ago.strftime("%Y-%m-%d"),
        "endDate": today.strftime("%Y-%m-%d"),
        "timeUnit": "week",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(body), timeout=120)
        response.raise_for_status()
        data = response.json()
        print(f"    - Naver 데이터랩 분석 완료.")
        return data
    except Exception as e:
        print(f" Naver 데이터랩 API 호출 중 오류 발생: {e}")
        return {"error": f"Naver API (DataLab) 오류: {e}"}

# ----------------------------------------------------
# 기능 3: Naver 검색 분석기 (관련 내용) (v16)
# ----------------------------------------------------
def get_naver_search_content(query, display=5):
    """
    (v17) 네이버 검색 API(블로그, 뉴스)를 호출하여
    '관련 내용'(요약글) 리스트를 반환합니다.
    """
    print(f"  [trend_search] 3. Naver 검색 (관련 내용) 분석 시작: {query}")

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "네이버 API 키가 .env에 설정되지 않았습니다."}
    
    results = []
    
    # --- 1. 블로그 검색 ---
    try:
        blog_url = f"https://openapi.naver.com/v1/search/blog.json?query={query}&display={display}&sort=sim"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        response = requests.get(blog_url, headers=headers, timeout=120)
        response.raise_for_status()
        for item in response.json().get("items", []):
            results.append({
                "source": "blog",
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "snippet": item.get("description", "").replace("<b>", "").replace("</b>", "")
            })
    except Exception as e:
        print(f" Naver 블로그 검색 API 오류: {e}")
        results.append({"source": "blog", "error": str(e)})

    # --- 2. 뉴스 검색 ---
    try:
        news_url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display={display}&sort=sim"
        headers = {
            "X-Naver-Client-Id": NAVER_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
        }
        response = requests.get(news_url, headers=headers, timeout=120)
        response.raise_for_status()
        for item in response.json().get("items", []):
            results.append({
                "source": "news",
                "title": item.get("title", "").replace("<b>", "").replace("</b>", ""),
                "snippet": item.get("description", "").replace("<b>", "").replace("</b>", "")
            })
    except Exception as e:
        print(f" Naver 뉴스 검색 API 오류: {e}")
        results.append({"source": "news", "error": str(e)})

    print(f"    - Naver 검색 (관련 내용) 분석 완료. (총 {len(results)}건)")
    return results