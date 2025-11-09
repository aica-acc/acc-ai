from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class CardNews:
    title: str
    category: str                 # 지도 / 부스소개 / 행사일정 / 축제개요
    image_url: str                # 다운로드할 썸네일/이미지 URL
    source_url: str               # 인스타 post URL
    saved_path: Optional[str] = None
    slide_index: int = 0
    slide_count: int = 1
    created_at: datetime = datetime.now()
