import os
import io
import json
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from typing import List, Dict

import httpx
from PIL import Image
from dotenv import load_dotenv

from .oembed_utils import fetch_oembed_html, extract_slide_images_from_html

load_dotenv()  # .env 로드
SERP_API_KEY = os.getenv("SERPAPI_API_KEY")

# 프로젝트 루트 기준 data/카드뉴스
BASE_DIR = (Path(__file__).resolve().parents[2] / "data" / "카드뉴스").resolve()

# --------------- 유틸 ---------------
def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def safe_filename(url: str) -> str:
    return sha256(url.encode("utf-8")).hexdigest()[:16] + ".jpg"

def save_thumbnail(image_bytes: bytes, save_path: Path, max_w=300):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    if w > max_w:
        ratio = max_w / float(w)
        img = img.resize((max_w, int(h * ratio)))
    save_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(save_path, format="JPEG", quality=70, optimize=True)

# --------------- SerpApi ---------------
async def fetch_cardnews_images(keyword: str) -> List[Dict]:
    """
    SerpApi Google Images로 검색.
    반환: [{thumbnail, link(source), title}, ...]
    """
    if not SERP_API_KEY:
        raise RuntimeError("SERP_API_KEY not set")

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_images",
        "q": keyword,
        "hl": "ko",
        "api_key": SERP_API_KEY
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        out = []
        for img in data.get("images_results", []):
            out.append({
                "thumbnail": img.get("thumbnail"),
                "source": img.get("link"),
                "title": img.get("title","")
            })
        return out

# --------------- 메인 파이프라인 ---------------
async def download_cardnews_images(
    category: str,
    query: str,
    festival_name: str,
    region: str,
    year: int,
    limit_images: int | None = None
) -> List[Dict]:
    """
    1) SerpApi로 대표 썸네일 + post_url 확보
    2) oEmbed 가능하면 동일 post의 슬라이드 이미지 전부 확보
    3) 실패시 SerpApi 썸네일 1장만 저장
    4) JSON 메타 저장 (DB 이관 전용)
    """
    # 디렉터리 준비
    cat_dir = (BASE_DIR / category).resolve()
    json_dir = (BASE_DIR / "json").resolve()
    ensure_dir(cat_dir); ensure_dir(json_dir)

    # 1. 검색
    items = await fetch_cardnews_images(query)

    # 전체 레코드
    records: List[Dict] = []
    # 이미지 총량 제한 제어
    remaining = limit_images if isinstance(limit_images, int) and limit_images > 0 else None

    async with httpx.AsyncClient(timeout=20.0) as client:
        for idx, it in enumerate(items):
            post_url = it.get("source")
            title = it.get("title","")

            # 2. oEmbed 시도
            slide_urls: List[str] = []
            html = await fetch_oembed_html(post_url)
            if html:
                slide_urls = extract_slide_images_from_html(html)

            # 3. 실패시 SerpApi 썸네일 폴백
            candidates = slide_urls if slide_urls else [it.get("thumbnail")]

            for i, img_url in enumerate(candidates):
                if not img_url:
                    continue
                if remaining is not None and remaining <= 0:
                    break

                # 다운로드 & 썸네일화
                try:
                    resp = await client.get(img_url, follow_redirects=True)
                    if resp.status_code != 200:
                        continue
                    fname = safe_filename(img_url)
                    fpath = (cat_dir / fname).resolve()
                    save_thumbnail(resp.content, fpath, max_w=300)

                    meta = {
                        # file_path 테이블 스키마 기반
                        "file_path_no": None,                         # AUTO_INCREMENT (PK)
                        "entity_type": "CARDNEWS",                    # NOT NULL
                        "entity_no": idx,                             # NOT NULL(임시 인덱스)
                        "file_path": str(fpath),                      # NOT NULL
                        "source_type": "INSTAGRAM",                   # NOT NULL
                        "year": int(year),                            # NOT NULL
                        "region": str(region),                        # NOT NULL
                        "festival_name": str(festival_name),          # NOT NULL
                        "file_name": fname,                           # NOT NULL
                        "extension_name": "jpg",                      # NOT NULL
                        "create_at": datetime.now().strftime("%Y-%m-%d"),  # NOT NULL
                        "delete_at": None,                            # NULL
                        "is_delete": 0,                               # NOT NULL
                        # 확장 필드(분석·추적)
                        "source_url": post_url,
                        "title": title,
                        "slide_index": i,
                        "slide_count": len(candidates)
                    }
                    records.append(meta)
                    if remaining is not None:
                        remaining -= 1

                except Exception as e:
                    print(f"❌ 이미지 다운로드 실패: {img_url} | {e}")

            if remaining is not None and remaining <= 0:
                break

    # 4. JSON 저장 (축제명_카테고리.json)
    json_path = (json_dir / f"{festival_name}_{category}.json").resolve()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"✅ {category} 수집 완료: {len(records)}개 → {json_path}")
    return records
