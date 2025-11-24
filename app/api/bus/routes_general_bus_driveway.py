# -*- coding: utf-8 -*-
"""
/general-bus-driveway/write    → (입력: 한글 축제 정보) → (출력: Seedream 입력 JSON 그대로)
/general-bus-driveway/create   → (입력: Seedream 입력 JSON 그대로) → Seedream 호출 후 생성된 버스 차도면 광고 이미지 저장
/general-bus-driveway/run      → (입력: 한글 축제 정보) → 내부에서 write + create까지 한 번에 실행
/general-bus-driveway/recommend → (입력: create/run 결과 JSON) → 폰트/색상 추천만 추가해서 반환
/general-bus-driveway/operate  → (입력: 한글 축제 정보) → run + recommend 를 한 번에 실행
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from replicate.exceptions import ModelError  # 필요 없으면 나중에 정리해도 됨

from app.service.bus.make_general_bus_driveway import (
    write_general_bus_driveway,
    create_general_bus_driveway,
)
from app.service.font_color.bus_font_color_recommend import (
    recommend_fonts_and_colors_for_bus,
)

router = APIRouter(prefix="/general-bus-driveway", tags=["General Bus Driveway"])


# ---------------------------------------------------------
# 요청 DTO
# ---------------------------------------------------------
class GeneralBusDrivewayRequest(BaseModel):
    poster_image_url: str
    festival_name_ko: str
    festival_period_ko: str
    festival_location_ko: str


# ---------------------------------------------------------
# 1) 프롬프트 + Seedream 입력 JSON 생성 API
# ---------------------------------------------------------
@router.post("/write")
def generate_general_bus_driveway_prompt(
    req: GeneralBusDrivewayRequest,
) -> Dict[str, Any]:
    """
    참고용 포스터 + 한글 축제 정보를 입력받아
    General-bus-driveway(3.7:1) 버스 외부 광고용 Seedream 입력 JSON을 생성한다.
    """
    try:
        seedream_job = write_general_bus_driveway(
            poster_image_url=req.poster_image_url,
            festival_name_ko=req.festival_name_ko,
            festival_period_ko=req.festival_period_ko,
            festival_location_ko=req.festival_location_ko,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"failed to build general bus driveway prompt: {e}",
        )

    return seedream_job


# ---------------------------------------------------------
# 2) Seedream JSON → 이미지 생성 API
# ---------------------------------------------------------
@router.post("/create")
def create_general_bus_driveway_image(
    seedream_input: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    /general-bus-driveway/write 결과(JSON)를 그대로 받아
    Replicate(Seedream)를 호출해서 이미지를 생성하고 로컬에 저장한다.
    """
    try:
        result = create_general_bus_driveway(seedream_input)
    except HTTPException:
        raise
    except ModelError as e:
        # Replicate 모델 에러는 502 정도로 래핑
        raise HTTPException(
            status_code=502,
            detail=f"general bus driveway model error: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"general bus driveway generation failed: {e}",
        )

    return {
        "status": "success",
        "type": "general-bus-driveway",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        "width": result.get("width"),
        "height": result.get("height"),
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get(
            "festival_base_name_placeholder", ""
        ),
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
def run_general_bus_driveway_pipeline(
    req: GeneralBusDrivewayRequest,
) -> Dict[str, Any]:
    """
    1) /general-bus-driveway/write 로 Seedream 입력 JSON을 만들고
    2) /general-bus-driveway/create 로 이미지를 생성하는 과정을 한 번에 수행.
    """
    # 1) write
    try:
        seedream_input = write_general_bus_driveway(
            poster_image_url=req.poster_image_url,
            festival_name_ko=req.festival_name_ko,
            festival_period_ko=req.festival_period_ko,
            festival_location_ko=req.festival_location_ko,
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"failed to build general bus driveway prompt: {e}",
        )

    # 2) create
    try:
        result = create_general_bus_driveway(seedream_input)
    except HTTPException:
        raise
    except ModelError as e:
        raise HTTPException(
            status_code=502,
            detail=f"general bus driveway model error: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"general bus driveway generation failed: {e}",
        )

    return {
        "status": "success",
        "type": "general-bus-driveway",
        "image_path": result["image_path"],
        "image_filename": result["image_filename"],
        "prompt": result["prompt"],
        "width": result.get("width"),
        "height": result.get("height"),
        "festival_name_placeholder": result.get("festival_name_placeholder", ""),
        "festival_period_placeholder": result.get("festival_period_placeholder", ""),
        "festival_location_placeholder": result.get("festival_location_placeholder", ""),
        "festival_base_name_placeholder": result.get(
            "festival_base_name_placeholder", ""
        ),
        "festival_base_period_placeholder": result.get(
            "festival_base_period_placeholder", ""
        ),
        "festival_base_location_placeholder": result.get(
            "festival_base_location_placeholder", ""
        ),
    }


# ---------------------------------------------------------
# 4) 폰트/색상 추천 API
# ---------------------------------------------------------
@router.post("/recommend")
def recommend_general_bus_driveway_fonts_and_colors(
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """
    /general-bus-driveway/create 나 /general-bus-driveway/run 의 결과 JSON을 그대로 넣으면,
    그 정보를 이용해서 font-family / hex 색상을 추천해서
    같은 구조 + 추천 결과를 합쳐서 반환한다.
    """
    try:
        bus_type = str(payload.get("type") or "general-bus-driveway")
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
        rec = recommend_fonts_and_colors_for_bus(
            bus_type=bus_type,
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
    response.setdefault("type", bus_type)
    response.setdefault("image_path", image_path)
    response.setdefault("image_filename", image_filename)

    # 🔹 width / height 도 응답에 보장
    if width is not None:
        response.setdefault("width", width)
    if height is not None:
        response.setdefault("height", height)

    # 폰트/색상 추천 결과 추가
    response.update(rec)
    return response


# ---------------------------------------------------------
# 5) 한 번에 run + recommend 까지 실행하는 OPERATE API
# ---------------------------------------------------------
@router.post("/operate")
def operate_general_bus_driveway(
    req: GeneralBusDrivewayRequest,
) -> Dict[str, Any]:
    """
    /general-bus-driveway/run + /general-bus-driveway/recommend 를 한 번에 실행.
    최종 반환 JSON 구조는 /general-bus-driveway/recommend 결과와 완전히 동일하게 맞춘다.
    """
    # 1) run 실행 (write + create)
    base_result = run_general_bus_driveway_pipeline(req)

    # 혹시 모를 예전 버전 호환용: seedream_input 이 있어도 여기서 강제로 제거
    if isinstance(base_result, dict):
        base_result.pop("seedream_input", None)

    # 2) /general-bus-driveway/recommend 에 넣을 payload 로 사용
    #    → recommend_general_bus_driveway_fonts_and_colors 응답 구조 = /recommend와 동일
    return recommend_general_bus_driveway_fonts_and_colors(payload=base_result)
