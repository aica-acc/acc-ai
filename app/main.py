"""
LangGraph 기반 포스터 하베스터 — Free/Trial Tier 대응 완성본

특징
- CSV/TSV → 지역 필터 → 축제별 이미지 검색/다운로드/저장 파이프라인을 LangGraph로 구성
- 무료/체험 플랜 대응: 전역 쿼리 카운트, 요청 간 레이트리밋, 429/5xx 지수백오프 재시도, 호스트별 요청 간격
- Pydantic(BaseModel) 결과 스키마 고정: 이후 파이프라인(리포트/DB 적재)에 동일 구조로 연결
- 폴더 구조: 홍보물/{연도}/{광역자치단체명}/{축제이름}/포스터/{파일명}

환경 변수(.env)
- BING_API_KEY=xxxx               # 또는 SERPAPI_API_KEY 중 하나 이상
- SERPAPI_API_KEY=yyyy
- MAX_QUERIES=180                 # 세션(실행) 내 최대 API 호출 수
- RATE_LIMIT_SEC=2.0              # API 호출 간 최소 대기(초)
- HOST_GAP_SEC=3.0                # 동일 호스트 연속요청 간격(초)
- RETRY_MAX=3                     # 429/5xx 재시도 횟수
- STRICT_MATCH=true               # 파일명 유사도 필터 엄격 모드
- MIN_WIDTH=600                   # 저장할 최소 폭(px) 추정(헤더 등으로 판단 불가 시 패스)
- MAX_PER_FESTIVAL=3              # 축제당 최대 저장 파일 수(기본 CLI 인자에도 있음)

설치(예시)
- requirements.txt
  langgraph>=0.2.40
  pydantic>=2.9
  python-dotenv>=1.0.1
  requests>=2.32.3
  pandas>=2.2.2
  tqdm>=4.66.5
  rapidfuzz>=3.9.7

실행 예시
python poster_harvester_graph_free_tier.py \
  --csv festivals_2025.csv \
  --region 전남,전북,광주 \
  --provider bing \
  --max-per-festival 3 \
  --output-root 홍보물
"""
from __future__ import annotations

import unicodedata
import argparse
import csv
import hashlib
import os
import re
import time
import random
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from tqdm import tqdm

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None

# === LangGraph ===
from langgraph.graph import StateGraph, END

# =============================
# 설정 (환경변수와 기본값)
# =============================
load_dotenv(override=False)
MAX_QUERIES = int(os.getenv("MAX_QUERIES", "180"))
RATE_LIMIT_SEC = float(os.getenv("RATE_LIMIT_SEC", "2.0"))
HOST_GAP_SEC = float(os.getenv("HOST_GAP_SEC", "3.0"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "3"))
STRICT_MATCH_ENV = os.getenv("STRICT_MATCH", "true").lower() in {"1", "true", "yes", "y"}
MIN_WIDTH = int(os.getenv("MIN_WIDTH", "0"))  # 단순 헤더로 추정 불가, 기본 0이면 미사용
DEFAULT_MAX_PER_FEST = int(os.getenv("MAX_PER_FESTIVAL", "3"))

# 전역 카운터/호스트 타임스탬프
QUERY_COUNT = 0
HOST_LAST_HIT: Dict[str, float] = {}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

# =============================
# Pydantic 표준 스키마
# =============================

class FestivalIn(BaseModel):
    region: str = Field(..., description="광역자치단체명")
    city: str = Field("", description="기초자치단체명")
    name: str = Field(..., description="축제명")
    type: str = Field("", description="축제 유형")
    start: str = Field("", description="시작일 YYYY-MM-DD")
    end: str = Field("", description="종료일 YYYY-MM-DD")

    @property
    def year(self) -> str:
        return (self.start[:4] if self.start else (self.end[:4] if self.end else "2025"))


class PosterFile(BaseModel):
    path: str
    url: Optional[str] = None
    sha1: Optional[str] = None
    width_guess: Optional[int] = None


class FestivalResult(BaseModel):
    festival: FestivalIn
    out_dir: str
    files: List[PosterFile] = []
    errors: List[str] = []


class HarvestSummary(BaseModel):
    provider: str
    regions: List[str]
    total_festivals: int
    total_files: int
    results: List[FestivalResult]
    query_count: int


# =============================
# 유틸
# =============================

def detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        sample = f.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",	;")
        return dialect.delimiter  # type: ignore
    except Exception:
        return "\t" if "\t" in sample.splitlines()[0] else ","


def read_rows(path: Path) -> List[Dict[str, str]]:
    if pd is not None:
        try:
            df = pd.read_csv(path, sep=None, engine="python", dtype=str)
        except Exception:
            df = pd.read_csv(path, sep=detect_delimiter(path), dtype=str)
        df = df.fillna("")
        return df.to_dict(orient="records")
    else:
        delim = detect_delimiter(path)
        rows: List[Dict[str, str]] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=delim)
            for r in reader:
                rows.append({k: (v or "") for k, v in r.items()})
        return rows

def slugify(name: str) -> str:
    # Windows 예약문자 제거 → 공백 연속은 '_'로 → 앞뒤 '_' 정리
    s = unicodedata.normalize("NFC", name)
    s = re.sub(r"[\\/:*?\"<>|]+", " ", s)  # 금지문자 → 공백
    s = re.sub(r"\s+", "_", s).strip("_")  # 공백 묶음 → '_'
    return s

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def title_sim(a: str, b: str) -> int:
    return int(fuzz.token_sort_ratio(a, b))

def host_of_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""

def wait_for_host_gap(host: str):
    now = time.time()
    last = HOST_LAST_HIT.get(host, 0.0)
    gap = now - last
    if gap < HOST_GAP_SEC:
        time.sleep(HOST_GAP_SEC - gap)
    HOST_LAST_HIT[host] = time.time()

from typing import Iterable

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

def count_existing_images(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)

def existing_index_start(dir_path: Path) -> int:
    """이미 저장된 포스터 개수 기반으로 다음 파일 인덱스(1-based)를 돌려줍니다."""
    return count_existing_images(dir_path) + 1

# =============================
# 안전 요청 (429/5xx 재시도 + 전역 레이트리밋)
# =============================

def safe_request(make_req):
    global QUERY_COUNT
    if QUERY_COUNT >= MAX_QUERIES:
        print(f"[STOP] 세션 최대 요청 수({MAX_QUERIES}) 도달 — 호출 중단")
        return None

    delay = RATE_LIMIT_SEC
    for attempt in range(RETRY_MAX):
        try:
            # 전역 호출 간격
            time.sleep(RATE_LIMIT_SEC)
            resp = make_req()
            if resp is None:
                raise requests.RequestException("Empty response from make_req")
            status = getattr(resp, "status_code", 0)
            if status == 429 or 500 <= status < 600:
                print(f"[WARN] HTTP {status} — 재시도 {attempt+1}/{RETRY_MAX} 대기 {delay:.1f}s")
                time.sleep(delay + random.uniform(0.2, 0.8))
                delay *= 1.8
                continue
            resp.raise_for_status()
            QUERY_COUNT += 1
            return resp
        except requests.RequestException as e:
            print(f"[RETRY] {e} — 재시도 {attempt+1}/{RETRY_MAX} 대기 {delay:.1f}s")
            time.sleep(delay + random.uniform(0.2, 0.8))
            delay *= 1.8
    return None

# =============================
# 이미지 검색 Provider
# =============================

class ImageSearchProvider:
    def search(self, query: str, count: int = 5, **kwargs) -> List[str]:
        raise NotImplementedError

class BingImageProvider(ImageSearchProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("BING_API_KEY")
        if not self.api_key:
            raise RuntimeError("BING_API_KEY 환경변수가 필요합니다.")
        self.endpoint = "https://api.bing.microsoft.com/v7.0/images/search"

    def search(self, query: str, count: int = 5, freshness: str = "Year", **kwargs) -> List[str]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {
            "q": query,
            "count": min(count, 50),
            "safeSearch": "Moderate",
            "imageType": "Photo",
            "mkt": "ko-KR",
            "freshness": freshness,
        }
        def _call():
            host = host_of_url(self.endpoint)
            wait_for_host_gap(host)
            return requests.get(self.endpoint, headers=headers, params=params, timeout=20)
        r = safe_request(_call)
        if not r:
            return []
        js = r.json()
        urls = [v.get("contentUrl") for v in js.get("value", []) if v.get("contentUrl")]
        return urls[:count]

class SerpApiImageProvider(ImageSearchProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        if not self.api_key:
            raise RuntimeError("SERPAPI_API_KEY 환경변수가 필요합니다.")
        self.endpoint = "https://serpapi.com/search.json"

    def search(self, query: str, count: int = 5, tbs: str = "qdr:y", force_tbs: Optional[str] = None, **kwargs) -> List[str]:
        params = {
            "engine": "google_images",
            "q": query,
            "google_domain": "google.co.kr",
            "gl": "kr",
            "hl": "ko",
            "ijn": "0",
            "api_key": self.api_key,
            "tbs": force_tbs if force_tbs is not None else tbs,
        }
        def _call():
            host = host_of_url(self.endpoint)
            wait_for_host_gap(host)
            return requests.get(self.endpoint, params=params, timeout=20)
        r = safe_request(_call)
        if not r:
            return []
        js = r.json()
        results = js.get("images_results", [])
        urls = [it.get("original") or it.get("thumbnail") for it in results if (it.get("original") or it.get("thumbnail"))]
        return urls[:count]

def build_provider(name: str) -> ImageSearchProvider:
    name = name.lower().strip()
    if name == "bing":
        return BingImageProvider()
    if name == "serpapi":
        return SerpApiImageProvider()
    raise ValueError(f"Unknown provider: {name}")

# =============================
# 다운로드/저장
# =============================

def guess_width_from_headers(resp: requests.Response) -> Optional[int]:
    # 많은 서버가 이미지 크기를 헤더에 주지 않음. 여기서는 생략/미사용 기본.
    return None

def download_image(url: str, session: requests.Session) -> Optional[bytes]:
    def _call():
        host = host_of_url(url)
        wait_for_host_gap(host)
        return session.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r = safe_request(_call)
    if not r:
        return None
    ct = (r.headers.get("Content-Type") or "").lower()
    data = r.content
    head = data[:12]
    if ("image" in ct) or head.startswith(b"\xff\xd8") or head.startswith(b"\x89PNG") or b"WEBP" in head:
        return data
    return None

def best_filename(base: str, idx: int, url: str, start: str) -> str:
    ext = os.path.splitext(url.split("?")[0].split("#")[0])[-1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    stamp = ""
    try:
        stamp = "_" + datetime.strptime(start[:10], "%Y-%m-%d").strftime("%Y%m%d") if start else ""
    except Exception:
        pass
    return f"{base}_poster_{idx:02d}{stamp}{ext}"

# =============================
# LangGraph 상태/노드
# =============================

class HarvestState(TypedDict):
    csv_path: str
    provider: str
    regions: List[str]
    output_root: str
    max_per: int
    sleep: float
    strict: bool
    rows: List[Dict[str, str]]
    festivals: List[FestivalIn]
    i: int
    results: List[FestivalResult]

def node_load_csv(state: HarvestState) -> HarvestState:
    rows = read_rows(Path(state["csv_path"]))
    return {"rows": rows}

def node_filter_regions(state: HarvestState) -> HarvestState:
    rows = state.get("rows", [])
    wanted = set(state.get("regions", []))
    fests: List[FestivalIn] = []
    for r in rows:
        region = (r.get("광역자치단체명") or r.get("region") or "").strip()
        city = (r.get("기초자치단체명") or r.get("city") or "").strip()
        name = (r.get("축제명") or r.get("name") or "").strip()
        type_ = (r.get("축제 유형") or r.get("type") or "").strip()
        start = (r.get("시작일") or r.get("start") or "").strip()
        end = (r.get("종료일") or r.get("end") or "").strip()
        if region and name and (not wanted or region in wanted):
            fests.append(FestivalIn(region=region, city=city, name=name, type=type_, start=start, end=end))
    return {"festivals": fests, "i": 0, "results": []}

def node_process_one(state: HarvestState) -> HarvestState:
    idx = state.get("i", 0)
    festivals: List[FestivalIn] = state.get("festivals", [])
    if idx >= len(festivals):
        return {}

    fest = festivals[idx]
    provider = build_provider(state["provider"])

    # --- 폴백용 쿼리 세트 ---
    base = [
        f"{fest.year} {fest.name} 포스터",
        f"{fest.year} {fest.region} {fest.name} 포스터",
    ]
    relaxed = [
        f"{fest.name} 포스터",
        f"{fest.region} {fest.name} 포스터",
        f"{fest.name} 포스터 이미지",
        f"{fest.name} poster",
        f"{fest.region} {fest.name} poster",
    ]

    # 저장 준비는 '실제 저장 직전'에만 폴더 생성 (빈 폴더 방지)
    out_dir = Path(state["output_root"]) / fest.year / slugify(fest.region) / slugify(fest.name) / "포스터"
    exist_cnt = count_existing_images(out_dir)
    if exist_cnt >= state["max_per"]:
        result = FestivalResult(festival=fest, out_dir=str(out_dir), files=[], errors=[])
        new_results = list(state.get("results", [])) + [result]
        return {"results": new_results, "i": idx + 1}

    session = requests.Session()
    seen: set[str] = set()
    saved: List[PosterFile] = []
    errors: List[str] = []

    def try_save_from_urls(urls: List[str], strict: bool, allow_thumbs: bool) -> None:
        nonlocal saved
        for u in urls:
            if len(saved) >= state["max_per"]:
                break
            time.sleep(max(0.0, state.get("sleep", 0.0)))

            data = download_image(u, session)
            if not data:
                continue

            h = sha1_bytes(data)
            if h in seen:
                continue

            # 유사도 검사(완화 가능)
            tail = slugify(Path(u.split("?")[0]).name)
            if strict and title_sim(fest.name, tail) < 20:
                # 파일명으로 구분 안가면 패스 (strict 모드에서만)
                continue

            # 폴더는 실제 저장 직전에 생성
            ensure_dir(out_dir)
            
            # 파일명 인덱스 계산
            start_idx = existing_index_start(out_dir)
            fname = best_filename(slugify(fest.name), start_idx + len(saved), u, fest.start)
            
            out_path = out_dir / fname
            try:
                with out_path.open("wb") as f:
                    f.write(data)
                saved.append(PosterFile(path=str(out_path), url=u, sha1=h, width_guess=None))
                seen.add(h)
            except Exception as e:
                errors.append(str(e))

    # 1) 1차(연도 포함) 시도
    urls = []
    for q in base:
        urls += provider.search(q, count=state["max_per"] * 3)
    urls = list(dict.fromkeys(urls))
    try_save_from_urls(urls, strict=state["strict"], allow_thumbs=False)

    # 2) 2차(연도 제거/키워드 변형)
    if len(saved) == 0:
        urls2 = []
        for q in relaxed:
            urls2 += provider.search(q, count=max(10, state["max_per"] * 5))
        urls2 = list(dict.fromkeys(urls2))
        try_save_from_urls(urls2, strict=False, allow_thumbs=True)

    # 3) 3차(기간 제한 해제, 더 많이 가져와서 한 장이라도)
    if len(saved) == 0:
        urls3 = []
        # tbs 제거(force_tbs=None) + 상한 확장
        for q in [*base, *relaxed]:
            urls3 += provider.search(q, count=30, force_tbs="")
        urls3 = list(dict.fromkeys(urls3))
        # 완전 관대하게: strict=False
        try_save_from_urls(urls3, strict=False, allow_thumbs=True)

    # 최종 보장: 그래도 없으면 가장 첫 URL을 강제로 1장 저장 시도
    # (위에서 구한 urls3가 없다면, relaxed→base 순으로 첫 URL 하나 더 시도)
    if len(saved) == 0:
        def first_or_empty(lst): return lst[0:1] if lst else []
        fallback_urls = first_or_empty(urls3 if 'urls3' in locals() else []) \
                        or first_or_empty(urls2 if 'urls2' in locals() else []) \
                        or first_or_empty(urls if 'urls' in locals() else [])
        try_save_from_urls(fallback_urls, strict=False, allow_thumbs=True)

    result = FestivalResult(festival=fest, out_dir=str(out_dir), files=saved, errors=errors)
    new_results = list(state.get("results", [])) + [result]
    return {"results": new_results, "i": idx + 1}

def node_router(state: HarvestState) -> str:
    i = state.get("i", 0)
    total = len(state.get("festivals", []))
    if i >= total:
        return END
    if i > total + 1:  # 혹시라도 잘못된 index 증가 방지
        return END
    return "process_one"

# =============================
# 그래프 빌드/런
# =============================

def build_graph() -> StateGraph:
    g = StateGraph(HarvestState)
    g.add_node("load_csv", node_load_csv)
    g.add_node("filter_regions", node_filter_regions)
    g.add_node("process_one", node_process_one)
    g.set_entry_point("load_csv")
    g.add_edge("load_csv", "filter_regions")
    g.add_conditional_edges("filter_regions", node_router, {"process_one": "process_one", END: END})
    g.add_conditional_edges("process_one", node_router, {"process_one": "process_one", END: END})
    return g

def run_pipeline(csv_path: str, regions: List[str], provider: str, output_root: str, max_per: int, sleep: float, strict: bool) -> HarvestSummary:
    # STRICT 우선순위: CLI 인자 → 환경변수
    real_strict = strict if strict is not None else STRICT_MATCH_ENV

    graph = build_graph().compile()
    init: HarvestState = {
        "csv_path": csv_path,
        "provider": provider,
        "regions": regions,
        "output_root": output_root,
        "max_per": max_per,
        "sleep": sleep,
        "strict": real_strict,
        "rows": [],
        "festivals": [],
        "i": 0,
        "results": [],
    }
    final_state: HarvestState = graph.invoke(
        init,
        config={"recursion_limit": 5000}  # 축제 수가 많아도 안전하게 여유
    )
    results: List[FestivalResult] = final_state.get("results", [])
    return HarvestSummary(
        provider=provider,
        regions=regions,
        total_festivals=len(results),
        total_files=sum(len(r.files) for r in results),
        results=results,
        query_count=QUERY_COUNT,
    )

# =============================
# CLI
# =============================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LangGraph Poster Harvester (Free/Trial Ready)")
    p.add_argument("--csv", required=True)
    p.add_argument("--region", required=True, help="쉼표 구분 여러 지역")
    p.add_argument("--provider", default="serpapi", choices=["bing", "serpapi"])
    p.add_argument("--max-per-festival", type=int, default=DEFAULT_MAX_PER_FEST)
    p.add_argument("--output-root", default="홍보물")
    p.add_argument("--sleep", type=float, default=0.5, help="노드 내 추가 대기(전역 RATE_LIMIT_SEC 외)")
    p.add_argument("--no-strict", action="store_true", help="이름 유사도 필터 완화")
    return p.parse_args()

def main():
    args = parse_args()
    regions = [r.strip() for r in args.region.split(",") if r.strip()]
    summary = run_pipeline(
        csv_path=args.csv,
        regions=regions,
        provider=args.provider,
        output_root=args.output_root,
        max_per=args.max_per_festival,
        sleep=args.sleep,
        strict=(not args.no_strict),
    )
    print(summary.model_dump_json(ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

    #ss