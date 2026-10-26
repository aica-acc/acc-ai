# -*- coding: utf-8 -*-
# app/api/routes_banner.py
from __future__ import annotations
from typing import Optional, Literal, Any, Dict, List
from pathlib import Path
import os, json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

# 프롬프트 생성 퍼사드(있을 경우)
try:
    from app.service.banner.make_prompt_from_analysis.service_make_prompt_from_analysis import (
        make_banner_prompt_service,
    )
except Exception:
    make_banner_prompt_service = None

# 🔹 기존 LLM 기반 텍스트 트렌드 분석 (원래 /banner/analyze에서 쓰던 거)
try:
    from app.service.banner.banner_trend_analysis.service_banner_trend_analysis import (
        analyze_banner_trend_with_llm,
    )
except Exception:
    analyze_banner_trend_with_llm = None

# 🔹 새로 추가: 배너 이미지 기준 관련/최신 축제 추천 서비스
try:
    from app.service.banner.banner_trend_analysis.service_banner_image_trend_analysis import (
        analyze_banner_image_trend,
    )
except Exception:
    analyze_banner_image_trend = None

# 프롬프트 동기화(한/영)
from app.service.banner.banner_prompt_update.service_banner_prompt_update import (
    ensure_prompt_synced_before_generation,
)

# 이미지 생성 퍼사드
from app.service.banner.make_banner_from_prompt.service_make_banner_from_prompt import (
    make_banner_from_prompt_service,
)

from app.core.config import BANNER_SAVE_DIR as _CFG_BANNER_SAVE_DIR

router = APIRouter(prefix="/banner", tags=["Banner"])

# -------------------- 공용 유틸 --------------------
def _default_save_dir() -> Path:
    return Path(os.getenv("BANNER_SAVE_DIR") or _CFG_BANNER_SAVE_DIR)

def _json_ok(payload: dict) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(
            payload,
            custom_encoder={Path: lambda p: p.as_posix()},
        )
    )

# -------------------- 스키마 --------------------
class BannerAnalyzeRequest(BaseModel):
    p_name: str
    user_theme: str
    keywords: list[str]

class PromptRequest(BaseModel):
    analysis_payload: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "custom"
    resolution: str = "2K"
    use_pre_llm: bool = True
    seed: Optional[int] = None
    # 경고 방지: schema 대신 prompt_schema 사용
    prompt_schema: Literal["basic", "extended"] = "basic"

class GenerationRequest(BaseModel):
    job: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    return_type: Literal["dict", "list", "string"] = "dict"
    save_dir: Optional[str] = None
    filename_prefix: Optional[str] = None

class GenerateFromAnalysisRequest(BaseModel):
    analysis_payload: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "custom"
    resolution: str = "2K"
    use_pre_llm: bool = True
    seed: Optional[int] = None
    prompt_schema: Literal["basic", "extended"] = "basic"
    return_type: Literal["dict", "list", "string"] = "dict"
    save_dir: Optional[str] = None
    filename_prefix: Optional[str] = None

# -------------------- 라우트 --------------------
@router.post("/prompts")
def create_prompt(req: PromptRequest):
    if make_banner_prompt_service is None:
        raise HTTPException(status_code=501, detail="prompt service not available")
    try:
        prompt_obj = make_banner_prompt_service(
            analysis_payload=req.analysis_payload,
            orientation=req.orientation,
            width=req.width,
            height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            use_pre_llm=req.use_pre_llm,
            seed=req.seed,
            schema=req.prompt_schema,
            strict=True,
        )
        return _json_ok(prompt_obj)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"banner prompt build failed: {type(e).__name__}: {e}",
        )

@router.post("/generations")
def create_generation(req: GenerationRequest):
    try:
        # 0) job이 문자열(JSON 텍스트)로 들어오는 상황 방어
        job_in = req.job
        if isinstance(job_in, str):
            try:
                job_in = json.loads(job_in)
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail="job must be an object (dict), not a JSON string.",
                )

        # 1) 한글 변경 → 영어 프롬포트 동기화
        job_synced = ensure_prompt_synced_before_generation(job_in)

        # 2) 저장 경로
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()

        # 3) 생성
        gen = make_banner_from_prompt_service(
            job_synced,
            orientation=req.orientation,
            save_dir=save_dir,
            filename_prefix=req.filename_prefix,
            return_type=req.return_type,
        )

        return _json_ok(gen)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"banner generation failed: {type(e).__name__}: {e}",
        )

@router.post("/generate-from-analysis")
def generate_from_analysis(req: GenerateFromAnalysisRequest):
    if make_banner_prompt_service is None:
        raise HTTPException(status_code=501, detail="prompt service not available")
    try:
        # 1) 프롬프트 생성
        prompt_obj = make_banner_prompt_service(
            analysis_payload=req.analysis_payload,
            orientation=req.orientation,
            width=req.width,
            height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            use_pre_llm=req.use_pre_llm,
            seed=req.seed,
            schema=req.prompt_schema,
            strict=True,
        )

        # 2) 한글 변경 감지(사용자가 prompt_ko를 수정했을 수 있음)
        job_synced = ensure_prompt_synced_before_generation(prompt_obj)

        # 3) 이미지 생성
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()
        gen = make_banner_from_prompt_service(
            job_synced,
            orientation=req.orientation,
            save_dir=save_dir,
            filename_prefix=req.filename_prefix,
            return_type=req.return_type,
        )

        return _json_ok({"ok": True, "prompt": prompt_obj, "generation": gen})
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"banner generate-from-analysis failed: {type(e).__name__}: {e}",
        )

# 🔹 기존: LLM 텍스트 리포트용 /banner/analyze (그대로 유지)
@router.post("/analyze")
def analyze_banner(req: BannerAnalyzeRequest):
    """
    현수막 텍스트 트렌드 분석 (LLM 기반)
    - 입력: p_name, user_theme, keywords
    - 출력: JSON 객체 (예: 3개 섹션)
      {
        "similar_theme_banner_analysis": "...",
        "evidence_and_effects": "...",
        "strategy_for_our_festival": "..."
      }
    """
    if analyze_banner_trend_with_llm is None:
        raise HTTPException(
            status_code=501,
            detail="banner trend LLM service not available (import 실패 또는 openai 미설치)",
        )

    try:
        trend = analyze_banner_trend_with_llm(
            p_name=req.p_name,
            user_theme=req.user_theme,
            keywords=req.keywords,
        )
        return _json_ok(trend)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"banner analyze failed: {type(e).__name__}: {e}",
        )

# 🔹 새로 추가: 배너 이미지 기준 관련/최신 축제 5개씩 추천
@router.post("/analyze-image")
def analyze_banner_image(req: BannerAnalyzeRequest):
    """
    배너/현수막 기준 관련/최신 축제 추천

    입력:
        - p_name: 축제명
        - user_theme: 축제 테마/기획 의도
        - keywords: 키워드 리스트

    출력(JSON):
        {
          "related_festivals": [ { festival_name, banner_image_url, ... } x 최대 5 ],
          "latest_festivals":  [ { festival_name, banner_image_url, ... } x 최대 5 ]
        }
    """
    if analyze_banner_image_trend is None:
        raise HTTPException(
            status_code=501,
            detail="banner image trend service not available (import 실패)",
        )

    try:
        trend = analyze_banner_image_trend(
            p_name=req.p_name,
            user_theme=req.user_theme,
            keywords=req.keywords,
            # top_k 기본값 5 (함수 내부 기본값 사용)
        )
        return _json_ok(trend)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"banner analyze-image failed: {type(e).__name__}: {e}",
        )
