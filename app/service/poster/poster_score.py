# -*- coding: utf-8 -*-
"""
🎨 축제 포스터 자동 품질 평가 (LangGraph + 멀티스레드 + 진행률 표시)
- 평가항목: 예술성, 주제적합성, 가독성, 독창성
- 한국어 설명 포함 CSV
- 진행률(%) 및 남은 시간(ETA) 표시
"""

import os
import csv
import time
import json
import base64
import mimetypes
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# === ⚙️ 환경 설정 ===
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ROOT_DIR = Path(r"C:\final_project\ACC\acc-ai\홍보물") 
YEAR = 2025
REGIONS = ["경남", "경북", "대구","대전", "부산", "울산", "인천", "제주", "충남", "충북"]
OUTPUT_CSV = Path(r"C:\final_project\ACC\acc-ai\app\service\poster\poster_scores_korean_progress.csv") #
VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_WORKERS = 8
LOCK = threading.Lock()

# === 📦 상태 정의 ===
class PosterState(BaseModel):
    id: str
    year: int
    region: str
    festival_name: str
    poster_path: str
    scores: dict = Field(default_factory=dict)

# === 🧠 평가 프롬프트 (한국어 버전) ===
EVAL_PROMPT = """
당신은 시각디자인 평가 전문가입니다.
제공된 축제 포스터 이미지를 다음 4가지 기준으로 평가하세요.
각 항목별로 **1~10점**을 매기고, 각 점수에 대한 **간결한 한국어 설명(2~3문장)**을 작성하세요.

---

🎨 **1. 예술성 (Aesthetic Predictors / LAION, 2022)**
- 색채 구성: 명도·채도 대비, 색상 조화
- 구도 균형: 중심 배치, 시각적 안정감
- 조형 완성도: 일러스트/사진의 통일감, 형태 리듬감

🧠 **2. 주제적합성 (CLIPScore / Allen AI, 2021)**
- 시각–텍스트 일치: 제목·로고·이미지 간 의미적 연결
- 콘셉트 일관성: 행사의 핵심 테마와 시각 표현의 조화
- 언어–시각 매칭: 텍스트와 이미지의 시멘틱 유사성

👁️ **3. 가독성 (Readability Index / MIT Media Lab, 2019)**
- 텍스트 대비: 배경과 글자 색의 대비, 판독성
- 정보 구조: 제목–날짜–장소 등 계층적 구성
- 시선 흐름: 시각적 플로우의 자연스러움

💡 **4. 독창성 (Creativity via Novelty Metrics / Stanford, 2020)**
- 형식적 참신성: 기존 문법에서의 변주 여부
- 시각 패턴 다양성: 구성·색상·모티프의 창의성
- 표현의 독자성: 전반적 연출의 새로움

---

응답은 반드시 다음 JSON 형식으로 출력하세요:
{
  "Aesthetic": {"score": <float>, "desc": "<한국어 설명>"},
  "Thematic": {"score": <float>, "desc": "<한국어 설명>"},
  "Readability": {"score": <float>, "desc": "<한국어 설명>"},
  "Creativity": {"score": <float>, "desc": "<한국어 설명>"}
}
"""

# ===  이미지 → Data URI ===
def to_data_uri(image_path: str) -> str:
    mime, _ = mimetypes.guess_type(image_path)
    if not mime:
        mime = "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# ===  LangGraph 평가 노드 ===
def evaluate_poster(state: PosterState):
    data_uri = to_data_uri(state.poster_path)
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="gpt-4.1-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "당신은 시각디자인 평가 전문가입니다."},
                    {"role": "user", "content": [
                        {"type": "text", "text": EVAL_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_uri,
                                "detail": "high"
                            }
                        }
                    ]}
                ]
            )
            content = resp.choices[0].message.content
            state.scores = json.loads(content)
            return state
        except Exception as e:
            print(f" {state.poster_path} 평가 실패 (시도 {attempt+1}/3): {e}")
            time.sleep(1.5)
    return None

# === LangGraph 구성 ===
workflow = StateGraph(PosterState)
workflow.add_node("evaluate_poster", evaluate_poster)
workflow.add_edge(START, "evaluate_poster")
workflow.add_edge("evaluate_poster", END)
app: CompiledStateGraph = workflow.compile()

# === CSV 초기화 ===
if not OUTPUT_CSV.exists():
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ID", "YEAR", "REGION", "FESTIVAL_NAME", "IMAGE_PATH",
            "Aesthetic", "Aesthetic_Description",
            "Thematic", "Thematic_Description",
            "Readability", "Readability_Description",
            "Creativity", "Creativity_Description"
        ])

# === 포스터 처리 함수 ===
def process_poster(region, fest_dir, img_path, counter):
    state = PosterState(
        id=f"{region}_{counter}",
        year=YEAR,
        region=region,
        festival_name=fest_dir.name,
        poster_path=str(img_path)
    )
    result = app.invoke(state)
    
    #  LangGraph가 dict를 반환하는 경우도 커버
    if not result:
        return None

    scores = result.scores if hasattr(result, "scores") else result.get("scores", None)
    if not scores:
        return None
    sc = scores

    with LOCK, OUTPUT_CSV.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            result.id if hasattr(result, "id") else result.get("id"),
            result.year if hasattr(result, "year") else result.get("year"),
            result.region if hasattr(result, "region") else result.get("region"),
            result.festival_name if hasattr(result, "festival_name") else result.get("festival_name"),
            result.poster_path if hasattr(result, "poster_path") else result.get("poster_path"),
            sc["Aesthetic"]["score"], sc["Aesthetic"]["desc"],
            sc["Thematic"]["score"], sc["Thematic"]["desc"],
            sc["Readability"]["score"], sc["Readability"]["desc"],
            sc["Creativity"]["score"], sc["Creativity"]["desc"]
        ])
    return result.poster_path if hasattr(result, "poster_path") else result.get("poster_path")

# ===  실행 ===
def main():
    tasks = []
    counter = 1

    # 전체 이미지 목록 수집
    for region in REGIONS:
        base = ROOT_DIR / str(YEAR) / region
        if not base.exists():
            continue
        for fest_dir in base.iterdir():
            poster_dir = fest_dir / "포스터"
            if not poster_dir.exists():
                continue
            for img_path in poster_dir.iterdir():
                if img_path.suffix.lower() not in VALID_EXTS:
                    continue
                tasks.append((region, fest_dir, img_path, counter))
                counter += 1

    total = len(tasks)
    print(f"\n 총 {total}개 포스터 평가 시작 (스레드 {MAX_WORKERS}개)\n")

    start_time = time.time()
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_poster, *t) for t in tasks]
        for future in as_completed(futures):
            result = future.result()
            completed += 1
            elapsed = time.time() - start_time
            avg_time = elapsed / completed
            remaining = (total - completed) * avg_time
            progress = (completed / total) * 100
            print(f" {completed}/{total} ({progress:.1f}%) 완료 | 남은 예상시간: {remaining/60:.1f}분")

    print("\n 모든 지역 포스터 평가 완료!")
    print(f" 결과 CSV: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
