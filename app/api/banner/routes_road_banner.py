# -*- coding: utf-8 -*-
"""
/road-banner/write  → (입력: 한글 축제 정보) → (출력: Seedream 입력 JSON 그대로)
/road-banner/create → (입력: Seedream 입력 JSON 그대로) → Seedream 호출 후 생성된 현수막 이미지 저장
"""

from __future__ import annotations

from fastapi import APIRouter, Body
from pydantic import BaseModel

from app.service.banner_khs.make_road_banner import (
    write_road_banner,
    create_road_banner,
)

router = APIRouter(prefix="/road-banner", tags=["Road Banner"])


# ---------------------------------------------------------
# 요청 DTO
# ---------------------------------------------------------
class RoadBannerRequest(BaseModel):
    poster_image_url: str
    festival_name_ko: str
    festival_period_ko: str
    festival_location_ko: str


# ---------------------------------------------------------
# 1) 프롬프트 + Seedream 입력 JSON 생성 API
# ---------------------------------------------------------
@router.post("/write")
def generate_road_banner_prompt(req: RoadBannerRequest):
    """
    입력:
    {
      "poster_image_url": "http://localhost:5000/static/banner/sample_mud.PNG",
      "festival_name_ko": "2025 보령머드축제",
      "festival_period_ko": "2025.08.15 ~ 2025.08.20",
      "festival_location_ko": "보령시 대천해수욕장 일대"
    }

    출력:
    {
      "size": "custom",
      "width": 4096,
      "height": 1024,
      "prompt": "...(영문 프롬프트)...",
      "max_images": 1,
      "aspect_ratio": "match_input_image",
      "enhance_prompt": true,
      "sequential_image_generation": "disabled",
      "image_input": [
        {
          "type": "image_url",
          "url": "http://localhost:5000/static/banner/sample_mud.PNG"
        }
      ]
    }
    """
    seedream_job = write_road_banner(
        poster_image_url=req.poster_image_url,
        festival_name_ko=req.festival_name_ko,
        festival_period_ko=req.festival_period_ko,
        festival_location_ko=req.festival_location_ko,
    )
    return seedream_job


# ---------------------------------------------------------
# 2) 이미지 생성 API (Seedream 입력 JSON 그대로 받기)
# ---------------------------------------------------------
@router.post("/create")
def create_road_banner_image(seedream_input: dict = Body(...)):
    """
    /road-banner/write 에서 받은 JSON을
    body 루트에 그대로 넣어서 호출하면 된다.

    예시 요청(body):

    {
      "size": "custom",
      "width": 4096,
      "height": 1024,
      "prompt": "...",
      "max_images": 1,
      "aspect_ratio": "match_input_image",
      "enhance_prompt": true,
      "sequential_image_generation": "disabled",
      "image_input": [
        {
          "type": "image_url",
          "url": "http://localhost:5000/static/banner/sample_mud.PNG"
        }
      ]
    }

    응답:
    {
      "status": "success",
      "image_path": "app/data/road_banner/road_banner_YYYYMMDD_HHMMSS.png",
      "image_filename": "road_banner_YYYYMMDD_HHMMSS.png",
      "prompt": "<사용된 프롬프트 문자열>"
    }
    """
    result = create_road_banner(seedream_input)
    return {
        "status": "success",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
    }
