# app/api/routes_banner.py
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
# 🔴 추가: 한글 변경 감지+영문 동기화 퍼사드 임포트
# app/api/routes_banner.py
from app.service.banner.banner_prompt_update.service_banner_prompt_update import (
    ensure_prompt_synced_before_generation,
)


router = APIRouter(prefix="/banner", tags=["Banner"])

# -------------------- 공용 유틸 --------------------
def _default_save_dir() -> Path:
    return Path(os.getenv("BANNER_SAVE_DIR", "C:/final_project/ACC/assets/banners"))

def _json_ok(payload: dict) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(payload, custom_encoder={Path: lambda p: p.as_posix()}))

def _format_paths(
    paths: list[str],
    *,
    mode: Literal["string_first", "string_join", "list"] = "string_first"
):
    if mode == "list":
        return [str(p) for p in paths]
    if mode == "string_join":
        return ";".join(str(p) for p in paths)
    return (str(paths[0]) if paths else "")

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
    schema: Literal["basic", "extended"] = "basic"

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
    path_format: Literal["string_first", "string_join", "list"] = "string_first"

class GenerateFromAnalysisRequest(BaseModel):
    analysis_payload: Dict[str, Any]
    orientation: Literal["horizontal", "vertical"] = "horizontal"
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: str = "custom"
    resolution: str = "2K"
    use_pre_llm: bool = True
    seed: Optional[int] = None
    schema: Literal["basic", "extended"] = "basic"
    return_type: Literal["dict", "list", "string"] = "dict"
    save_dir: Optional[str] = None
    filename_prefix: Optional[str] = None
    path_format: Literal["string_first", "string_join", "list"] = "string_first"

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
            schema=req.schema,
            strict=True,
        )
        return _json_ok(prompt_obj)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"banner prompt build failed: {type(e).__name__}: {e}")

@router.post("/generations")
def create_generation(req: GenerationRequest):
    try:
        # ✅ 1) 한글 변경 감지 + 영문 prompt 동기화(항상 수행)
        synced_job, changed, reason = ensure_prompt_synced_before_generation(req.job)

        # ✅ 2) 이미지 생성
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()
        gen = make_banner_from_prompt_service(
            synced_job,
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

        # ✅ 3) 직렬화/경로 형식 변환 + 동기화 결과 주석
        if isinstance(gen, dict):
            if "images" in gen: gen["images"] = [str(u) for u in gen.get("images", [])]
            raw = gen.get("file_path", "")
            if isinstance(raw, list):  # 안전 처리
                gen["file_path"] = _format_paths([str(p) for p in raw], mode=req.path_format)
            else:
                gen["file_path"] = str(raw)
            if "inputs" in gen and isinstance(gen["inputs"], dict):
                gen["inputs"] = {str(k): (v.as_posix() if isinstance(v, Path) else v) for k, v in gen["inputs"].items()}
            gen.pop("artifact_paths", None)

            # 🔎 동기화 메타 포함(디버깅/확인용)
            gen["sync"] = {"changed": changed, "reason": reason}

        return _json_ok(gen)
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
            schema=req.schema,
            strict=True,
        )

        # 2) (선택) 프론트에서 곧바로 ko 수정 후 보낼 수 있으니, 동일 규칙으로 동기화 수행
        synced_job, changed, reason = ensure_prompt_synced_before_generation(prompt_obj)

        # 3) 이미지 생성
        save_dir = Path(req.save_dir) if req.save_dir else _default_save_dir()
        gen = make_banner_from_prompt_service(
            synced_job,
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

        if isinstance(gen, dict):
            if "images" in gen: gen["images"] = [str(u) for u in gen.get("images", [])]
            raw = gen.get("file_path", "")
            gen["file_path"] = str(raw)
            if "inputs" in gen and isinstance(gen["inputs"], dict):
                gen["inputs"] = {str(k): (v.as_posix() if isinstance(v, Path) else v) for k, v in gen["inputs"].items()}
            gen.pop("artifact_paths", None)
            gen["sync"] = {"changed": changed, "reason": reason}

        return _json_ok({"ok": True, "prompt": synced_job, "generation": gen})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"banner generate-from-analysis failed: {type(e).__name__}: {e}")
