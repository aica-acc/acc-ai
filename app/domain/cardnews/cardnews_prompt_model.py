from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class CardnewsReference(BaseModel):
    category: str
    festival_name: str
    region: str
    year: int
    file_path: str
    source_url: Optional[str]
    title: Optional[str]
    score: Dict[str, Any]


class PromptRequest(BaseModel):
    references: List[CardnewsReference]
    user_theme: Optional[str] = None
    keywords: Optional[List[str]] = None
    target_category: str = "카드뉴스"


class PromptResponse(BaseModel):
    # visual_prompt는 "텍스트 없는 배경 프롬프트"
    visual_prompt: str
    style_name: str


class ReplicateImageRequest(BaseModel):
    visual_prompt: str
    width: int = 1080
    height: int = 1350


class ReplicateImageResponse(BaseModel):
    image_url: str


# 카드뉴스에 실제로 들어갈 텍스트/표 컨텐츠
class TableCell(BaseModel):
    value: str


class TableRow(BaseModel):
    cells: List[TableCell]


class TableData(BaseModel):
    headers: List[str]
    rows: List[TableRow]


class CardnewsContent(BaseModel):
    festival_name: str
    title: str                       # 상단 메인 타이틀
    subtitle: Optional[str] = None   # 서브 문구
    description: Optional[str] = None  # 본문/설명
    schedule_table: Optional[TableData] = None  # 일정 표
    footer_text: Optional[str] = None  # 하단 안내/CTA 문구
