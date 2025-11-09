from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class BannerPromptBase(BaseModel):
    banner_prompt_no: Optional[int] = None
    user_input_no: int
    visual_prompt: str
    style_name: str
    orientation: str = Field(..., description="방향 (horizontal | vertical)")

class BannerPromptHorizontal(BannerPromptBase):
    orientation: str = "horizontal"

class BannerPromptVertical(BannerPromptBase):
    orientation: str = "vertical"

class Banner(BaseModel):
    banner_no: Optional[int] = None
    promotion_no: int
    file_path_no: int
    create_at: datetime
    category: str
    orientation: str = Field(..., description="방향 (horizontal | vertical)")