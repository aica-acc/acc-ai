# app/api/routes_poster_khs.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Optional, List, Literal  # 이미 있으면 중복 안 되게

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

# 배경 프롬프트/입력 빌더
try:
    from app.service.poster_khs.poster_background_prompt_builder import (
        build_poster_background_prompt_ko,
        build_poster_background_dreamina_input,
    )
except Exception as e:  # pragma: no cover
    print("[routes_poster_khs] import error:", e)
    build_poster_background_prompt_ko = None
    build_poster_background_dreamina_input = None

# 🔹 새로 추가: 프롬프트 → 실제 이미지 생성 빌더
try:
    from app.service.poster_khs.poster_background_image_builder import (
        build_poster_background_image_from_prompt,
    )
except Exception as e:  # pragma: no cover
    print("[routes_poster_khs] import error (image_builder):", e)
    build_poster_background_image_from_prompt = None


# 최종 포스터(텍스트까지 합성)
try:
    from app.service.poster_khs.poster_image_builder import (
        build_final_poster_image,
    )
except Exception as e:  # pragma: no cover
    print("[routes_poster_khs] import error (poster_image_builder):", e)
    build_final_poster_image = None

router = APIRouter(prefix="/poster", tags=["Poster-KHS"])


# -------------------- 공용 유틸 --------------------


def _json_ok(payload: dict) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(payload),
    )


# -------------------- 스키마 --------------------


class PosterBackgroundPromptRequest(BaseModel):
    """
    기존 analysis_payload 전체를 넣고 싶은 경우용 (확장용).
    지금은 주로 simple 버전(/prompt-background-simple)을 쓸 예정.
    """
    analysis_payload: Dict[str, Any]

    style: str = "2d"  # "2d", "3d", "photo", "abstract"

    width: int = 1536
    height: int = 2048
    resolution: str = "2K"
    aspect_ratio: str = "3:4"
    use_pre_llm: bool = False
    llm_model: Optional[str] = None


PosterBackgroundPromptRequest.model_rebuild()


class PosterBackgroundSimpleRequest(BaseModel):
    """
    [KHS] 심플 버전:
    - title: 축제명 (한국어)
    - date: 기간 문자열
    - location: 장소
    - theme: 최종 테마(교정된 테마)
    - keywords: 키워드 리스트
    - visual_keywords: 시각적 키워드 리스트(선택)
    - style: "2d", "3d", "photo", "abstract"
    """
    title: str
    date: str
    location: str
    theme: str
    keywords: List[str] = []
    visual_keywords: List[str] = []

    style: str = "2d"  # "2d", "3d", "photo", "abstract"

    width: int = 1536
    height: int = 2048
    resolution: str = "2K"
    aspect_ratio: str = "3:4"
    use_pre_llm: bool = False
    llm_model: Optional[str] = None


PosterBackgroundSimpleRequest.model_rebuild()

class PosterBackgroundImageJob(BaseModel):
    """
    프롬프트를 받아 실제 포스터 배경 이미지를 생성하는 요청 스키마.

    - width, height, prompt, resolution, use_pre_llm, aspect_ratio 만 받는다.
    - save_dir, filename_prefix는 선택(안 주면 기본값 사용).
    """
    width: int = 1536
    height: int = 2048
    prompt: str

    resolution: str = "2K"
    use_pre_llm: bool = False
    aspect_ratio: str = "3:4"

    save_dir: Optional[str] = None
    filename_prefix: Optional[str] = None


PosterBackgroundImageJob.model_rebuild()


class PosterGenerationRequest(BaseModel):
    """
    [KHS] 한 번에 최종 포스터까지 만드는 요청

    1) title/date/location/theme/keywords/visual_keywords + style 을 받아서
    2) 배경 프롬프트 생성 → Dreamina로 배경 이미지 생성
    3) 그 위에 LLM 레이아웃으로 텍스트 얹어서 최종 포스터 생성
    """

    # 포스터 텍스트 정보
    title: str
    date: str
    location: str

    # 배경/컨셉 정보
    theme: str
    keywords: List[str] = []
    visual_keywords: List[str] = []

    # 배경 스타일 (배경/레이아웃 둘 다 참고용 메타)
    style: Literal["2d", "3d", "photo", "abstract"] = "2d"

    # Dreamina 입력용 (배경 이미지 사이즈 등)
    width: int = 1536
    height: int = 2048
    resolution: str = "2K"
    aspect_ratio: str = "3:4"
    use_pre_llm: bool = False

    # LLM 모델 (프롬프트 / 레이아웃 둘 다 이걸 사용)
    llm_model: str = "gpt-4.1-mini"

    # 선택: 배경 이미지 저장 위치/접두사
    bg_save_dir: Optional[str] = None
    bg_filename_prefix: Optional[str] = None

    # 선택: 최종 포스터 저장 위치/접두사
    final_save_dir: Optional[str] = None
    final_filename_prefix: Optional[str] = None


PosterGenerationRequest.model_rebuild()


# -------------------- 라우트 --------------------


@router.post("/prompt-background")
def create_poster_background_prompt_khs(req: PosterBackgroundPromptRequest):
    """
    [KHS] 기존 analysis_payload 전체를 받아서
    Dreamina 배경 input JSON을 반환하는 엔드포인트.
    (주 사용처는 /prompt-background-simple 이고, 이건 확장용)
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
            style=req.style,
        )
        return _json_ok(job)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"poster background job build failed: {type(e).__name__}: {e}",
        )


@router.post("/prompt-background-simple")
def create_poster_background_simple_khs(req: PosterBackgroundSimpleRequest):
    """
    [KHS] 심플 입력 → Dreamina 배경 input 생성

    입력:
        - title, date, location, theme, keywords, (옵션) visual_keywords, style
    출력:
        - Dreamina 3.1에 바로 넣을 수 있는 input JSON
          { width, height, prompt, resolution, use_pre_llm, aspect_ratio }
    """
    if build_poster_background_dreamina_input is None:
        raise HTTPException(
            status_code=501,
            detail="poster background dreamina input service not available (import 실패)",
        )

    # 1) 심플 입력을 기존 분석 payload 형식으로 변환
    analysis_payload: Dict[str, Any] = {
        "p_name": req.title,
        "user_theme": req.theme,
        "keywords": req.keywords,
        "festival": {
            "title": req.title,
            "date": req.date,
            "location": req.location,
            "theme": req.theme,
            "summary": "",
            "visual_keywords": req.visual_keywords,
        },
        "analysis": {
            "similarity": 1.0,
            "decision": "accept",
            "original_theme": req.theme,
            "corrected_theme": req.theme,
        },
    }

    try:
        job = build_poster_background_dreamina_input(
            analysis_payload=analysis_payload,
            width=req.width,
            height=req.height,
            resolution=req.resolution,
            aspect_ratio=req.aspect_ratio,
            use_pre_llm=req.use_pre_llm,
            llm_model=req.llm_model or "gpt-4.1-mini",
            style=req.style,
        )
        return _json_ok(job)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"poster background simple job build failed: {type(e).__name__}: {e}",
        )

@router.post("/background-image")
def create_poster_background_image_khs(req: PosterBackgroundImageJob):
    """
    [KHS] 배경 프롬프트 → 실제 포스터 배경 이미지 생성

    입력(JSON):
      {
        "width": 1536,
        "height": 2048,
        "prompt": "...",
        "resolution": "2K",
        "use_pre_llm": false,
        "aspect_ratio": "3:4"
      }

    출력(JSON):
      {
        "ok": true,
        "width": 1536,
        "height": 2048,
        "prompt": "...",
        "resolution": "2K",
        "use_pre_llm": false,
        "aspect_ratio": "3:4",
        "image_path": "C:/final_project/ACC/assets/posters/poster_bg_20251118_123045_xxxx.png",
        "image_filename": "poster_bg_20251118_123045_xxxx.png"
      }
    """
    if build_poster_background_image_from_prompt is None:
        raise HTTPException(
            status_code=501,
            detail="poster background image service not available (import 실패 또는 설정 오류)",
        )

    # 1) job dict 구성 (service에 그대로 넘길 형태)
    job = {
        "width": req.width,
        "height": req.height,
        "prompt": req.prompt,
        "resolution": req.resolution,
        "use_pre_llm": req.use_pre_llm,
        "aspect_ratio": req.aspect_ratio,
    }

    try:
        result = build_poster_background_image_from_prompt(
            job=job,
            save_dir=req.save_dir,
            filename_prefix=req.filename_prefix,
            # return_type 은 기본값 "dict" 사용
        )
        # result 는 dict 여야 한다.
        if not isinstance(result, dict):
            raise RuntimeError("image builder returned non-dict result.")

        return _json_ok(result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"poster background image generation failed: {type(e).__name__}: {e}",
        )


@router.post("/generation")
def generate_full_poster_khs(req: PosterGenerationRequest):
    """
    [KHS] 기획 정보 + 텍스트만 받아서
    1) 배경 프롬프트 생성
    2) Dreamina(Replicate)로 배경 이미지 생성
    3) LLM 레이아웃으로 텍스트 합성
    까지 한 번에 최종 포스터를 만들어주는 엔드포인트.

    입력(JSON):
      {
        "title": "2025 해변 불빛 축제",
        "date": "2025.08.15 ~ 2025.08.17",
        "location": "샘플 시티 해변공원",
        "theme": "가족이 함께 즐기는 야간 조명 축제",
        "keywords": ["가족", "야간", "빛"],
        "visual_keywords": ["lights", "ocean", "boardwalk", "warm palette", "photo zone"],
        "style": "2d",
        "width": 1536,
        "height": 2048,
        "resolution": "2K",
        "aspect_ratio": "3:4",
        "use_pre_llm": false,
        "llm_model": "gpt-4.1-mini"
      }

    출력(JSON) 예시 구조:
      {
        "ok": true,
        "prompt_job": { ... Dreamina input ... },
        "background": { ... 배경 생성 결과 ... },
        "final_poster": { ... 최종 포스터 + layout ... }
      }
    """
    if build_poster_background_dreamina_input is None:
        raise HTTPException(
            status_code=501,
            detail="poster background prompt service not available",
        )
    if build_poster_background_image_from_prompt is None:
        raise HTTPException(
            status_code=501,
            detail="poster background image service not available",
        )
    if build_final_poster_image is None:
        raise HTTPException(
            status_code=501,
            detail="poster final image service not available",
        )

    try:
        # 1) analysis_payload 비슷한 구조를 만든다 (프롬프트용)
        analysis_payload: Dict[str, Any] = {
            "p_name": req.title,
            "user_theme": req.theme,
            "keywords": req.keywords,
            "festival": {
                "title": req.title,
                "date": req.date,
                "location": req.location,
                "theme": req.theme,
                "summary": "",
                "visual_keywords": req.visual_keywords,
            },
            # analysis 필드는 최소만 둬도 됨 (LLM이 분위기만 참고)
            "analysis": {
                "similarity": None,
                "decision": None,
                "original_theme": req.theme,
                "corrected_theme": req.theme,
            },
        }

        # 2) LLM으로 Dreamina 3.1 input dict 생성 (프롬프트 포함)
        prompt_job = build_poster_background_dreamina_input(
            analysis_payload=analysis_payload,
            width=req.width,
            height=req.height,
            resolution=req.resolution,
            aspect_ratio=req.aspect_ratio,
            use_pre_llm=req.use_pre_llm,
            llm_model=req.llm_model,
        )
        # prompt_job 예:
        # {
        #   "width": 1536,
        #   "height": 2048,
        #   "prompt": "따뜻한 색조의 ...",
        #   "resolution": "2K",
        #   "use_pre_llm": false,
        #   "aspect_ratio": "3:4"
        # }

        # 3) Replicate(Dreamina)로 배경 이미지 생성
        bg_result = build_poster_background_image_from_prompt(
            job=prompt_job,
            save_dir=req.bg_save_dir,
            filename_prefix=req.bg_filename_prefix,
        )
        # bg_result 예:
        # {
        #   "ok": true,
        #   "width": 1536,
        #   "height": 2048,
        #   "prompt": "...",
        #   "resolution": "2K",
        #   "use_pre_llm": false,
        #   "aspect_ratio": "3:4",
        #   "image_path": "C:/.../poster_bg_20251118_133236.png",
        #   "image_filename": "poster_bg_20251118_133236.png"
        # }

        if not isinstance(bg_result, dict) or not bg_result.get("image_path"):
            raise RuntimeError("background image generation result is invalid")

        background_path = bg_result["image_path"]

        # 4) 배경 위에 텍스트(제목/기간/장소) 합성 → 최종 포스터
        final_result = build_final_poster_image(
            background_path=background_path,
            title=req.title,
            date=req.date,
            location=req.location,
            style=req.style,
            llm_model=req.llm_model,
            output_dir=req.final_save_dir,
            filename_prefix=req.final_filename_prefix,
        )

        return _json_ok(
            {
                "ok": True,
                "prompt_job": prompt_job,
                "background": bg_result,
                "final_poster": final_result,
            }
        )

    except HTTPException:
        # FastAPI의 HTTPException 은 그대로 다시 던진다.
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"poster generation failed: {type(e).__name__}: {e}",
        )