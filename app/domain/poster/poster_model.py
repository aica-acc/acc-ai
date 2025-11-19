from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- 1단계 (/analyze) ---
class PosterTheme(BaseModel):
    theme: str = Field(..., description="테마")

class AnalysisSummary(BaseModel):
    # ... (생략) ...
    title: str
    date: str
    location: str
    # ... (나머지 필드) ...

class PosterTrendReport(BaseModel):
    status: str
    summary: Optional[str] = None
    top_creativity_example: Optional[Dict[str, Any]] = None

class StrategyReport(BaseModel):
    strategy_text: str
    proposed_content: Dict[str, Any]
    visual_reference_path: Optional[str] = None

# --- 2단계 (/generate-prompt) ---
# 🚨 [중요] 상속 제거된 상태 가정 (422 근본 원인 해결)
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
    visual_prompt: str
    suggested_text_style: str
    text_content: TextContent

class CreateImageRequest(BaseModel):
    selected_prompt: SelectedPromptData
    analysis_summary: Dict[str, Any]