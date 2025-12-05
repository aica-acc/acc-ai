from pydantic import BaseModel
from typing import Dict, Any, List


class MascotPromptRequest(BaseModel):
    member_no: str
    project_no: int
    metadata: Dict[str, Any]
    user_input: Dict[str, Any]


class MascotPromptOption(BaseModel):
    style_name: str
    visual_prompt: str


class MascotPromptResponse(BaseModel):
    prompt_options: List[MascotPromptOption]


class MascotImageGenerateRequest(BaseModel):
    member_no: str
    project_no: int
    promotion_type: str = "mascot"
    prompt: MascotPromptOption
    is_main: bool = True


class GeneratePromptRequest(BaseModel):
    metadata: Dict[str, Any]
    analysis_summary: Dict[str, Any]
    poster_trend_report: Dict[str, Any]
    strategy_report: Dict[str, Any]
    theme: str
