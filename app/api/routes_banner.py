# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional, Literal, Any, Dict
from pathlib import Path
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.service.banner.make_prompt_from_analysis import make_banner_prompt_service
from app.service.banner.make_banner_from_prompt import make_banner_from_prompt_service

router = APIRouter(prefix="/banner", tags=["Banner"])

# -------------------- 유틸 --------------------
def _default_save_dir() -> Path:
    return Path(os.getenv("BANNER_SAVE_DIR", "C:/final_project/ACC/assets/banners"))

def _json_ok(payload: dict) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(
            payload,
            custom_encoder={Path: lambda p: p.as_posix()}
        )
    )

# -------------------- 스키마 --------------------
class PromptRequest(BaseModel):
    analysis_payload: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "custom"
    resolution: str = "2K"
    use_pre_llm: bool = True
    seed: Optional[int] = None
    # BaseModel의 schema 속성과 충돌 방지
    schema_mode: Literal["basic", "extended"] = "basic"

class GenerationRequest(BaseModel):
    job: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "custom"
    resolution: str = "2K"
    seed: Optional[int] = None
    use_pre_llm: bool = True
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
    schema_mode: Literal["basic", "extended"] = "basic"
    return_type: Literal["dict", "list", "string"] = "dict"
    save_dir: Optional[str] = None
    filename_prefix: Optional[str] = None

# -------------------- 라우트 --------------------
@router.post("/prompts")
def create_prompt(req: PromptRequest):
    try:
        prompt_obj = make_banner_prompt_service(
            analysis_payload=req.analysis_payload,
            orientation=req.orientation,
            width=req.width, height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            use_pre_llm=req.use_pre_llm,
            seed=req.seed,
            schema=req.schema_mode,
            strict=True,
        )
        return _json_ok(prompt_obj)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"banner prompt build failed: {type(e).__name__}: {e}")

@router.post("/generations")
def create_generation(req: GenerationRequest):
    try:
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()
        gen = make_banner_from_prompt_service(
            req.job,
            orientation=req.orientation,
            width=req.width, height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            seed=req.seed,
            use_pre_llm=req.use_pre_llm,
            return_type=req.return_type,
            save_dir=save_dir,
            filename_prefix=req.filename_prefix,
        )
        # 여기서 gen(dict)일 경우 file_path / file_name은 이미 문자열 상태
        return _json_ok(gen if isinstance(gen, dict) else {"ok": True, "result": gen})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"banner generation failed: {type(e).__name__}: {e}")

@router.post("/generate-from-analysis")
def generate_from_analysis(req: GenerateFromAnalysisRequest):
    try:
        # 1) 프롬프트 생성
        prompt_obj = make_banner_prompt_service(
            analysis_payload=req.analysis_payload,
            orientation=req.orientation,
            width=req.width, height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            use_pre_llm=req.use_pre_llm,
            seed=req.seed,
            schema=req.schema_mode,
            strict=True,
        )
        # 2) 이미지 생성
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()
        gen = make_banner_from_prompt_service(
            prompt_obj,
            orientation=req.orientation,
            width=req.width, height=req.height,
            aspect_ratio=req.aspect_ratio,
            resolution=req.resolution,
            seed=req.seed,
            use_pre_llm=req.use_pre_llm,
            return_type=req.return_type,
            save_dir=save_dir,
            filename_prefix=req.filename_prefix,
        )
        return _json_ok({"ok": True, "prompt": prompt_obj, "generation": gen})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"banner generate-from-analysis failed: {type(e).__name__}: {e}")
