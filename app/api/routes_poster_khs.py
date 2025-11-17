# -*- coding: utf-8 -*-
# app/api/routes_poster_khs.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

print("[routes_poster_khs] KHS router loaded")  # 👈 디버깅용 로그

try:
    from app.service.poster_khs.poster_background_prompt_builder import (
        build_poster_background_prompt_ko,
        build_poster_background_dreamina_input,   # 👈 이거 꼭 있어야 함
    )
except Exception as e:
    print("[routes_poster_khs] import error:", e)
    build_poster_background_prompt_ko = None
    build_poster_background_dreamina_input = None


router = APIRouter(
    prefix="/poster",
    tags=["Poster(KHS)"],
)


def _json_ok(payload: dict) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(payload))


class PosterBackgroundPromptRequest(BaseModel):
    analysis_payload: Dict[str, Any]

    # 옵션들(안 보내면 기본값 사용)
    width: int = 1536
    height: int = 2048
    resolution: str = "2K"
    aspect_ratio: str = "3:4"
    use_pre_llm: bool = True

    llm_model: Optional[str] = None


@router.post("/prompt-background")
def create_poster_background_prompt_khs(req: PosterBackgroundPromptRequest):
    """
    [KHS] 기획서 분석 결과 → Dreamina 3.1용 포스터 배경 input JSON 생성
    """
    if build_poster_background_dreamina_input is None:
        raise HTTPException(
            status_code=501,
            detail="poster background dreamina input service not available (import 실패)",
        )

    try:
        job = build_poster_background_dreamina_input(
            analysis_payload=req.analysis_payload,
            width=req.width,
            height=req.height,
            resolution=req.resolution,
            aspect_ratio=req.aspect_ratio,
            use_pre_llm=req.use_pre_llm,
            llm_model=req.llm_model or "gpt-4.1-mini",
        )
        return _json_ok(job)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"poster background job build failed: {type(e).__name__}: {e}",
        )

