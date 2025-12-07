# write_youtube_trend.py
from dotenv import load_dotenv
load_dotenv()

import os
import glob
import ast
import json
import re
from typing import List, TypedDict, Any, Iterable
from langgraph.graph import StateGraph, START, END
from langchain.prompts import ChatPromptTemplate
from langchain.schema import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_community.tools import TavilySearchResults
from pydantic import BaseModel, Field
import requests
from serpapi import google_search
# ============================================
# 1) 경로 설정 (절대경로, 어디서 실행해도 안전)
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../data"))
REPORT_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../data/report"))

os.makedirs(REPORT_DIR, exist_ok=True)


# ============================================
# 2) LangGraph State 정의
# ============================================
class TopState(TypedDict):
    query: str
    information: str
    context: str
    web_query: List[str]
    web_context: List[dict]
    final_result: dict


# ============================================
# 3) LLM 설정
# ============================================
llm = ChatOpenAI(model="gpt-4o")


# ============================================
# 4) Node 1 — 분석 입력 처리
# ============================================
def analyze_input(state: TopState) -> TopState:
    analyze_template = """
    아래 [information]은 특정 '축제 키워드(예: 크리스마스, 빛축제, 여름축제 등)'를 기반으로 
    YouTube API로부터 수집한 텍스트 데이터입니다.

    당신의 역할은 **축제 홍보물 제작을 준비하는 팀을 위한 트렌드 분석가**입니다.
    이 데이터를 기반으로 현재 한국에서 관찰되는 **축제/시즌/감성/연출 트렌드 Top 5**를 도출하시오.

    [규칙]
    - 왜 지금 이 트렌드가 뜨는지(Why now)
    - Target segment (명시적 타깃층)
    - Differentiators (2~3개)
    - 분석문단에서 '(why now)' 같은 표기 쓰지 말고 자연스럽게 작성

    [information]
    {information}
    """

    prompt = ChatPromptTemplate.from_template(analyze_template)
    chain = prompt | llm | StrOutputParser()

    result = chain.invoke({
        "query": state["query"],
        "information": state["information"]
    })

    return {**state, "context": result}


# ============================================
# 5) Node 2 — Web Query 생성
# ============================================
def make_web_query(state: TopState) -> TopState:
    search_template = """
    다음 [context]의 주요 이슈 배경을 검색하기 위한 한국어 쿼리 5개를 리스트 형태로 작성하시오.
    아래 [example] 형식을 지키시오.

    [example]
    [도심형 축제 조명 연출 트렌드, 겨울 시즌 야간 콘텐츠 증가, 지역 축제 관광객 방문 패턴, SNS 기반 축제 홍보 전략, 계절 테마형 포토존 트렌드]

    [context]
    {context}
    """

    prompt = ChatPromptTemplate.from_template(search_template)
    chain = prompt | llm | StrOutputParser()

    raw = chain.invoke({"context": state["context"]})

    try:
        queries = ast.literal_eval(raw)
    except:
        queries = [raw]

    return {**state, "web_query": queries}


# ============================================
# 6) Node 3 — 웹 검색
# ============================================
def web_search(state: TopState) -> TopState:
    tavily = TavilySearchResults(max_results=2)
    results = []

    for q in state["web_query"]:
        res = tavily.invoke(q)
        results.append({
            "query": q,
            "urls": [x["url"] for x in res],
            "context": [x["content"] for x in res],
        })

    return {**state, "web_context": results}


# ============================================
# 7) Node 4 — 최종 트렌드 결과 생성 (Structured Output)
# ============================================
class TrendItem(BaseModel):
    trend: str
    subtitle: str
    analysis: str
    recommendations: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class TrendOutput(BaseModel):
    items: List[TrendItem]


structured_llm = llm.with_structured_output(TrendOutput)


example_for_final = """
[
  {
    "trend": "크리스마스 감성 소비의 영상화 트렌드",
    "subtitle": "미디어파사드·캐럴·홈데코 결합",
    "analysis": "명동·백화점 미디어파사드 조기 점등으로 야간 방문 증가...",
    "recommendations": ["10초 릴스 구간", "조명 연출 강화"],
    "sources": ["https://example.com"]
  }
]
"""


def make_final(state: TopState):
    prompt = ChatPromptTemplate.from_template("""
    다음 [context], [web_context] 정보를 바탕으로
    축제 트렌드 5개를 JSON 배열 형태로 생성하라.

    [context]
    {context}

    [web_context]
    {web_context}

    [example]
    {example}
    """)

    out: TrendOutput = (prompt | structured_llm).invoke({
        "context": state["context"],
        "web_context": state["web_context"],
        "example": example_for_final
    })

    final = [item.model_dump() for item in out.items]
    return {**state, "final_result": final}


# ============================================
# 8) 그래프 조립
# ============================================
graph = StateGraph(TopState)
graph.add_node("analyze_input", analyze_input)
graph.add_node("make_web_query", make_web_query)
graph.add_node("web_search", web_search)
graph.add_node("make_final", make_final)

graph.add_edge(START, "analyze_input")
graph.add_edge("analyze_input", "make_web_query")
graph.add_edge("make_web_query", "web_search")
graph.add_edge("web_search", "make_final")
graph.add_edge("make_final", END)

app = graph.compile()


# ============================================
# 9) 파일 저장 함수
# ============================================
def save_to_file(obj: Any, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


import os

def serpapi_find_image(trend: str) -> str | None:
    """Google 이미지 검색으로 첫 번째 고퀄 URL 가져오기"""
    try:
        params = {
            "engine": "google_images",
            "q": trend,
            "tbm": "isch",
            "google_domain":"google.co.kr",
            "hl":"ko",
            "gl":"kr",
            "ijn": "0",
            "api_key": os.getenv("SERPAPI_API_KEY")
        }

        search = google_search(params)
        results = search.get_dict()

        # 이미지 리스트 가져오기
        images_results = results.get("images_results")
        if not images_results:
            return None

        # 첫 번째 이미지 URL
        return images_results[0].get("original")
    except Exception as e:
        print("[SerpAPI 이미지 검색 오류]:", e)
        return None
    


IMAGES_DIR = os.path.join(DATA_DIR, "total_trend_images")
os.makedirs(IMAGES_DIR, exist_ok=True)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def download_image_fixed(url: str, idx: int) -> str | None:
    if not url:
        return None

    # 1) http → https 강제 변환
    if url.startswith("http://"):
        url = url.replace("http://", "https://")

    filename = f"image_{idx}.jpg"
    file_path = os.path.join(IMAGES_DIR, filename)

    try:
        # 2) 첫 번째 시도 (기본 요청)
        resp = requests.get(url, headers=HEADERS, timeout=120)
        if resp.status_code == 200:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path

        print(f"⚠️ 기본 요청 실패({resp.status_code}) → SSL 무시 요청 재시도")
    except Exception as e:
        print(f"⚠️ 기본 요청 오류: {e} → SSL 무시 재시도")

    # 3) fallback: SSL 검증 끄고 재시도
    try:
        resp = requests.get(url, headers=HEADERS, timeout=120, verify=False)
        if resp.status_code == 200:
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return file_path
    except Exception as e:
        print(f"❌ SSL 무시 fallback도 실패: {e}")

    return None



# ============================================
# 🔥 11) 최종 실행 함수 (여기만 외부에서 호출)
# ============================================
def run_youtube_trend(keyword: str = "크리스마스"):
    """
    YouTube 데이터 읽기 → LangGraph 실행 → 결과 저장 → dict 반환
    """
    print("start")
    # 1) 데이터 읽기
    file_list = glob.glob(os.path.join(DATA_DIR, "youtube*"))
    informations = []
    for file in file_list:
        with open(file, "r", encoding="utf-8") as f:
            informations.append(f.read())

    combined_info = "\n".join(informations)

    # 2) 그래프 실행
    print("start33")
    state = {
        "query": f"{keyword} 기반 유튜브 트렌드 분석",
        "information": combined_info,
    }

    result = app.invoke(state)
    # 테스트 용 확인 코드 이따 지우기 
    final = result["final_result"]
    print("== DEBUG result:", result)
    print("== DEBUG result keys:", result.keys())
    print("== DEBUG final:", result.get("final_result"))
    print("== DEBUG final type:", type(result.get("final_result")))
    print("DEBUG final:", final, type(final))

    # 2.5) 여기서 이미지 처리 붙인다!
    final_with_images = []

    for idx, item in enumerate(final, start=1):
        trend = item["trend"]
        print(f"\n🔎 트렌드 이미지 검색: {trend}")

        # SerpAPI 검색
        url = serpapi_find_image(trend)
        print(" → SerpAPI URL:", url)

        # 다운로드해서 image_1.jpg ~ image_5.jpg 로 저장
        saved_path = download_image_fixed(url, idx)
        print(" → 저장됨:", saved_path)

        # JSON 결과에도 로컬 이미지 경로 입력
        item["image"] = saved_path

        final_with_images.append(item)


      

    # ---------------------------------------------------
    # 3) JSON 파일 저장 (텍스트 + 이미지 로컬경로 포함)
    # ---------------------------------------------------
    output_path = os.path.join(REPORT_DIR, "youtube_trend_results.json")
    save_to_file(final_with_images, output_path)

    # ---------------------------------------------------
    # 4) 최종 반환
    # ---------------------------------------------------
    return final_with_images

