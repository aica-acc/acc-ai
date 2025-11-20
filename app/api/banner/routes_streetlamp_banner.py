# -*- coding: utf-8 -*-
"""
/streetlamp-banner/write  → (입력: 한글 축제 정보) → (출력: Seedream 입력 JSON 그대로)
/streetlamp-banner/create → (입력: Seedream 입력 JSON 그대로) → Seedream 호출 후 생성된 현수막 이미지 저장
/streetlamp-banner/run    → (입력: 한글 축제 정보) → 내부에서 write + create까지 한 번에 실행
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from replicate.exceptions import ModelError

from app.service.banner_khs.make_streetlamp_banner import (
    write_streetlamp_banner,
    create_streetlamp_banner,
)

router = APIRouter(prefix="/streetlamp-banner", tags=["Streetlamp Banner"])


# ---------------------------------------------------------
# 요청 DTO
# ---------------------------------------------------------
class StreetlampBannerRequest(BaseModel):
    poster_image_url: str
    festival_name_ko: str
    festival_period_ko: str
    festival_location_ko: str


# ---------------------------------------------------------
# 1) 프롬프트 + Seedream 입력 JSON 생성 API
# ---------------------------------------------------------
@router.post("/write")
def generate_streetlamp_banner_prompt(req: StreetlampBannerRequest) -> Dict[str, Any]:
    seedream_job = write_streetlamp_banner(
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
def create_streetlamp_banner_image(
    seedream_input: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    /streetlamp-banner/write 에서 받은 JSON을
    body 루트에 그대로 넣어서 호출하면 된다.
    """
    try:
        result = create_streetlamp_banner(seedream_input)
    except HTTPException:
        # 이미 위쪽 계층에서 HTTPException 을 던진 경우 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"streetlamp banner generation failed: {e}",
        )

    return {
        "status": "success",
        "type": "streetlamp-banner",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get("festival_base_name_placeholder", ""),
        "festival_base_period_placeholder": result.get("festival_base_period_placeholder", ""),
        "festival_base_location_placeholder": result.get("festival_base_location_placeholder", ""),
    }


# ---------------------------------------------------------
# 3) 한 번에 write + create까지 실행하는 RUN API
# ---------------------------------------------------------
@router.post("/run")
def run_streetlamp_banner_pipeline(req: StreetlampBannerRequest) -> Dict[str, Any]:
    """
    1) /streetlamp-banner/write 로 Seedream 입력 JSON을 만들고
    2) /streetlamp-banner/create 로 이미지를 생성하는 과정을 한 번에 수행.
    """
    # 1) write
    try:
        seedream_input = write_streetlamp_banner(
            poster_image_url=req.poster_image_url,
            festival_name_ko=req.festival_name_ko,
            festival_period_ko=req.festival_period_ko,
            festival_location_ko=req.festival_location_ko,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"failed to build Seedream input: {e}",
        )

    # 2) create
    try:
        result = create_streetlamp_banner(seedream_input)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"streetlamp banner generation failed: {e}",
        )

    return {
        "status": "success",
        "type": "streetlamp-banner",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        # 🔹 run 은 seedream_input 도 같이 돌려줌 (디버깅/재생성용)
        "seedream_input": seedream_input,
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get("festival_base_name_placeholder", ""),
        "festival_base_period_placeholder": result.get("festival_base_period_placeholder", ""),
        "festival_base_location_placeholder": result.get("festival_base_location_placeholder", ""),
    }
