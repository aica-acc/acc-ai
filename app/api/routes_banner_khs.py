# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from app.service.banner_khs.banner_horizontal_builder import (
    generate_horizontal_banner,
)

router = APIRouter(
    prefix="/banner",
    tags=["banner-horizontal-khs"],
)


class BannerHorizontalCreateRequest(BaseModel):
    poster_image_url: HttpUrl
    festival_name_ko: str
    festival_period_ko: str
    festival_location_ko: str


class BannerHorizontalCreateResponse(BaseModel):
    image_path: str
    image_filename: str
    prompt: str
    seedream_input: Dict[str, Any]


@router.post(
    "/create-horizontal",
    response_model=BannerHorizontalCreateResponse,
    summary="가로형(4:1) 현수막 생성",
)
def create_horizontal_banner(
    req: BannerHorizontalCreateRequest,
) -> BannerHorizontalCreateResponse:
    try:
        result = generate_horizontal_banner(
            poster_image_url=str(req.poster_image_url),
            festival_name_ko=req.festival_name_ko,
            festival_period_ko=req.festival_period_ko,
            festival_location_ko=req.festival_location_ko,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"horizontal banner generation failed: {e}",
        )

    return BannerHorizontalCreateResponse(
        image_path=result["image_path"],
        image_filename=result["image_filename"],
        prompt=result["prompt"],
        seedream_input=result["seedream_input"],
    )
