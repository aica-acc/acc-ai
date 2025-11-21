# -*- coding: utf-8 -*-
"""
/road-banner/write    → (입력: 한글 축제 정보) → (출력: Seedream 입력 JSON 그대로)
/road-banner/create   → (입력: Seedream 입력 JSON 그대로) → Seedream 호출 후 생성된 현수막 이미지 저장
/road-banner/run      → (입력: 한글 축제 정보) → 내부에서 write + create까지 한 번에 실행
/road-banner/recommend → (입력: create/run 결과 JSON) → 폰트/색상 추천만 추가해서 반환
/road-banner/operate  → (입력: 한글 축제 정보) → run + recommend 를 한 번에 실행
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from replicate.exceptions import ModelError  # 필요 없으면 나중에 정리해도 됨

from app.service.banner_khs.make_road_banner import (
    write_road_banner,
    create_road_banner,
)
from app.service.font_color.banner_font_color_recommend import (
    recommend_fonts_and_colors_for_banner,
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
def generate_road_banner_prompt(req: RoadBannerRequest) -> Dict[str, Any]:
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
def create_road_banner_image(
    seedream_input: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    /road-banner/write 에서 받은 JSON을
    body 루트에 그대로 넣어서 호출하면 된다.
    """
    try:
        result = create_road_banner(seedream_input)
    except HTTPException:
        # 이미 위쪽 계층에서 HTTPException 을 던진 경우 그대로 전달
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"road banner generation failed: {e}",
        )

    return {
        "status": "success",
        "type": "road-banner",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        "width": result.get("width"),
        "height": result.get("height"),
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get("festival_base_name_placeholder", ""),
        "festival_base_period_placeholder": result.get(
            "festival_base_period_placeholder", ""
        ),
        "festival_base_location_placeholder": result.get(
            "festival_base_location_placeholder", ""
        ),
    }



# ---------------------------------------------------------
# 3) 한 번에 write + create까지 실행하는 RUN API
# ---------------------------------------------------------
@router.post("/run")
def run_road_banner_pipeline(req: RoadBannerRequest) -> Dict[str, Any]:
    """
    1) /road-banner/write 로 Seedream 입력 JSON을 만들고
    2) /road-banner/create 로 이미지를 생성하는 과정을 한 번에 수행.
    """
    # 1) write
    try:
        seedream_input = write_road_banner(
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
        result = create_road_banner(seedream_input)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"road banner generation failed: {e}",
        )

    # 🔹 seedream_input은 응답에 포함하지 않음 (내부에서만 사용)
    return {
        "status": "success",
        "type": "road-banner",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        "width": result.get("width"),
        "height": result.get("height"),
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get("festival_base_name_placeholder", ""),
        "festival_base_period_placeholder": result.get(
            "festival_base_period_placeholder", ""
        ),
        "festival_base_location_placeholder": result.get(
            "festival_base_location_placeholder", ""
        ),
    }





# ---------------------------------------------------------
# 4) 폰트/색상 추천만 하는 RECOMMEND API
#    - 입력: create / run 결과 JSON (그대로 Body에 넣으면 됨)
# ---------------------------------------------------------
@router.post("/recommend")
def recommend_road_banner_fonts_and_colors(
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    /road-banner/create 나 /road-banner/run 의 결과 JSON을 그대로 넣으면,
    그 정보를 이용해서 font-family / hex 색상을 추천해서
    같은 구조 + 추천 결과를 합쳐서 반환한다.
    """
    try:
        banner_type = str(payload.get("type") or "road-banner")
        image_path = str(payload["image_path"])
        image_filename = str(payload.get("image_filename", ""))

        festival_name_placeholder = str(
            payload.get("festival_name_placeholder", "")
        )
        festival_period_placeholder = str(
            payload.get("festival_period_placeholder", "")
        )
        festival_location_placeholder = str(
            payload.get("festival_location_placeholder", "")
        )

        festival_base_name_placeholder = str(
            payload.get("festival_base_name_placeholder", "")
        )
        festival_base_period_placeholder = str(
            payload.get("festival_base_period_placeholder", "")
        )
        festival_base_location_placeholder = str(
            payload.get("festival_base_location_placeholder", "")
        )

        # 🔹 width / height도 받아둔다 (없으면 None)
        width = payload.get("width")
        height = payload.get("height")

    except KeyError as e:
        raise HTTPException(
            status_code=400,
            detail=f"missing required field in recommend payload: {e}",
        )

    try:
        rec = recommend_fonts_and_colors_for_banner(
            banner_type=banner_type,
            image_path=image_path,
            festival_name_placeholder=festival_name_placeholder,
            festival_period_placeholder=festival_period_placeholder,
            festival_location_placeholder=festival_location_placeholder,
            festival_base_name_placeholder=festival_base_name_placeholder,
            festival_base_period_placeholder=festival_base_period_placeholder,
            festival_base_location_placeholder=festival_base_location_placeholder,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"font/color recommendation failed: {e}",
        )

    # 기존 payload + 추천 결과를 합쳐서 반환
    response: Dict[str, Any] = dict(payload)
    response.setdefault("type", banner_type)
    response.setdefault("image_path", image_path)
    response.setdefault("image_filename", image_filename)

    # 🔹 width / height 도 응답에 보장
    if width is not None:
        response.setdefault("width", width)
    if height is not None:
        response.setdefault("height", height)

    response.update(rec)
    return response



# ---------------------------------------------------------
# 5) 한 번에 run + recommend 까지 실행하는 OPERATE API
#    - 입력: 한글 축제 정보 (RoadBannerRequest)
#    - 내부:
#        1) run_road_banner_pipeline(req) 로 현수막 생성
#        2) recommend_fonts_and_colors_for_banner(...) 로 폰트/색상 추천
# ---------------------------------------------------------

@router.post("/operate")
def operate_road_banner(req: RoadBannerRequest) -> Dict[str, Any]:
    """
    /road-banner/run + /road-banner/recommend 를 한 번에 실행.
    최종 반환 JSON 구조는 /road-banner/recommend 결과와 완전히 동일하게 맞춘다.
    """
    # 1) run 실행 (write + create)
    base_result = run_road_banner_pipeline(req)

    # 혹시 모를 예전 버전 호환용: seedream_input 이 있어도 여기서 강제로 제거
    if isinstance(base_result, dict):
        base_result.pop("seedream_input", None)

    # 2) /road-banner/recommend 에 넣을 payload 로 사용
    #    → recommend_road_banner_fonts_and_colors 응답 구조 = /recommend와 동일
    return recommend_road_banner_fonts_and_colors(payload=base_result)


