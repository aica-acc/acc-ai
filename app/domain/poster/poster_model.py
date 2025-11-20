from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- 1단계 (/analyze) ---
class PosterTheme(BaseModel):
    theme: str

class AnalysisSummary(BaseModel):
    title: str
    date: str
    location: str
    host: Optional[str] = None
    organizer: Optional[str] = None
    targetAudience: Optional[str] = None
    contactInfo: Optional[str] = None
    directions: Optional[str] = None
    programs: Optional[List[str]] = []
    events: Optional[List[str]] = []
    visualKeywords: Optional[List[str]] = []
    concept: Optional[str] = None
    summary: Optional[str] = None

class PosterTrendReport(BaseModel):
    status: str
    summary: Optional[str] = None
    top_creativity_example: Optional[Dict[str, Any]] = None

class StrategyReport(BaseModel):
    strategy_text: str
    proposed_content: Dict[str, Any]
    visual_reference_path: Optional[str] = None

# --- 2단계 (/generate-prompt) ---
class GeneratePromptRequest(BaseModel):
    theme: str
    analysis_summary: Dict[str, Any]
    poster_trend_report: Dict[str, Any]
    strategy_report: Dict[str, Any]

# --- 3단계 (/create-image) ---
class TextContent(BaseModel):
    title: str
    subtitle: Optional[str] = None
    main_copy: Optional[str] = None
    date_location: str
    programs: Optional[str] = None

class SelectedPromptData(BaseModel):
    style_name: str
    width: int = 1024
    height: int = 1792
    # 두 필드 다 받아주도록 설정 (호환성)
    visual_prompt: Optional[str] = None
    visual_prompt_for_background: Optional[str] = None
    suggested_text_style: str         
    text_content: Optional[TextContent] = None

class CreateImageRequest(BaseModel):
    # 단일 객체 -> 리스트 형태로 변경 (4개 한 번에 받음)
    prompt_options: List[SelectedPromptData]
    analysis_summary: Dict[str, Any]