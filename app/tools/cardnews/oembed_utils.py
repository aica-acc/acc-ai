import os
import re
from typing import List, Optional
import httpx

FACEBOOK_APP_TOKEN = os.getenv("FACEBOOK_APP_TOKEN")  # 없으면 None

async def fetch_oembed_html(post_url: str) -> Optional[str]:
    """
    Instagram oEmbed 공식 엔드포인트 호출.
    토큰이 없거나 실패하면 None 반환 (자동 폴백을 위함)
    """
    if not FACEBOOK_APP_TOKEN:
        return None

    base = "https://graph.facebook.com/v17.0/instagram_oembed"
    params = {
        "url": post_url,
        "access_token": FACEBOOK_APP_TOKEN
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(base, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("html")
    except Exception:
        pass
    return None

def extract_slide_images_from_html(html: str) -> List[str]:
    """
    oEmbed HTML에서 이미지 srcset을 파싱.
    인스타는 종종 srcset에 여러 해상도를 싣는데, 여기서는 문자열 전체를 후보로 수집.
    """
    if not html:
        return []
    # srcset="URL1 640w, URL2 1080w" 형태 → 가장 마지막(보통 가장 큰 해상도)만 사용
    raw = re.findall(r'srcset="([^"]+)"', html)
    urls: List[str] = []
    for rs in raw:
        parts = [p.strip().split(" ")[0] for p in rs.split(",") if p.strip()]
        if parts:
            urls.append(parts[-1])  # 가장 큰 해상도 후보를 선택
    # 중복 제거
    uniq = []
    for u in urls:
        if u not in uniq:
            uniq.append(u)
    return uniq
