from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Callable, Optional, Tuple

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

import base64
import requests 
from google import genai
from google.genai import types
import subprocess # FFmpeg 호출을 위한 subprocess 모듈 추가

import time
import io
import shutil
from google.genai import types
from PIL import Image





# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
...
FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
...
PROMOTION_CODE = "M000001"  # 고정값

PROJECT_ROOT = os.getenv("PROJECT_ROOT")
if not PROJECT_ROOT:
    raise ValueError("PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")
PROJECT_ROOT = Path(PROJECT_ROOT).resolve()

# 인트로 자막용 한글 폰트 (예: app/fonts/Jalnan2TTF.ttf)
INTRO_FONT_PATH = PROJECT_ROOT / "app" / "fonts" / "Jalnan2TTF.ttf"
if not INTRO_FONT_PATH.exists():
    raise FileNotFoundError(f"인트로 자막용 폰트 파일을 찾을 수 없습니다: {INTRO_FONT_PATH}")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 가 .env에 설정되어 있지 않습니다.")

FRONT_PROJECT_ROOT = os.getenv("FRONT_PROJECT_ROOT")
if not FRONT_PROJECT_ROOT:
    raise ValueError("FRONT_PROJECT_ROOT 가 .env에 설정되어 있지 않습니다.")

api_key = os.getenv("GEMINI_API_KEY")
veo_client = genai.Client(api_key=GEMINI_API_KEY)
openai_client = OpenAI()

#이건 바꿔야함 
test_layout_image_url = "data/promotion/M000001/25/poster/good_2.jpg"
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
# 환경설정 모델들
VEO_MODEL = "veo-3.1-generate-preview"
MODEL = "veo-3.1-generate-preview" # Veo 3.1 모델 이름
# ============================================================
# 0. 환경설정 및 PATH
# ============================================================

router = APIRouter(prefix="/editor", tags=["Editor Build"])

# ▶ PROJECT_ROOT 환경변수 기반으로 동적 설정

DATA_ROOT = PROJECT_ROOT / "app" / "data"

env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Editor 폴더
EDITOR_ROOT_DIR = PROJECT_ROOT / "app" / "data" / "editor"
LAYOUT_TEMPLATES_DIR = EDITOR_ROOT_DIR / "layout_templates"

# Static URL prefix
STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", "http://127.0.0.1:5000/static/editor")

logger = logging.getLogger(__name__)

_client: OpenAI | None = None





# --------------------------------------------------
# 공통 설정
# --------------------------------------------------






def get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# ============================================================
# 1. 타입별 파이프라인 함수들 IMPORT (예시 경로)
# ============================================================

# === Base Banner / Poster Types (6종 + 로고 2종) ===
from app.service.banner_khs.make_road_banner import run_road_banner_to_editor
from app.service.bus.make_bus_shelter import run_bus_shelter_to_editor
from app.service.subway.make_subway_light import run_subway_light_to_editor
from app.service.bus.make_bus_road import run_bus_road_to_editor
from app.service.banner_khs.make_streetlamp_banner import run_streetlamp_banner_to_editor
from app.service.subway.make_subway_inner import run_subway_inner_to_editor

# === Logo (예시 import 경로 — 수정필요) ===
# TODO: actual path later
from app.service.logo.make_logo_illustration import run_logo_illustration_to_editor
from app.service.logo.make_logo_typography import run_logo_typography_to_editor

# === Poster 파생 (예시 import 경로) ===
from app.service.leaflet.make_leaflet_image import run_leaflet_to_editor
from app.service.video.make_poster_video import run_poster_video_to_editor

# === Mascot 파생 (예시 import 경로) ===
from app.service.sign.make_sign_parking import run_sign_parking_to_editor
from app.service.sign.make_sign_welcome import run_sign_welcome_to_editor
from app.service.sign.make_sign_toilet import run_sign_toilet_to_editor
from app.service.video.make_mascot_video import run_mascot_video_to_editor
from app.service.goods.make_goods_emoticon import run_goods_emoticon_to_editor
from app.service.goods.make_goods_key_ring import run_goods_key_ring_to_editor
from app.service.goods.make_goods_sticker import run_goods_sticker_to_editor

# # === ETC 비디오 (예시 import 경로) ===
from app.service.video.make_etc_video import run_etc_video_to_editor

# === news는 pass 예정 ===
# from app.service.etc.make_news import run_news_to_editor


# ============================================================
# 2. Pydantic 모델
# ============================================================

class PosterIn(BaseModel):
    posterImageUrl: str
    mascotImageUrl : str
    title: str
    festivalStartDate: datetime
    festivalEndDate: datetime
    location: str
    types: List[str]
    programName: List[str]  # mascot_video, etc, cardnews 용
    conceptDescription: str


class EditorBuildRequest(BaseModel):
    pNo: int
    posters: List[PosterIn]


class PythonBuildResponse(BaseModel):
    status: str
    pNo: int
    filePath: str
    dbFilePath: List[str] = []
    dbFileType: List[str] = []


# ============================================================
# 3. 파이프라인 그룹 정의
# ============================================================

# --- Fabric 수정 가능한 6종 ---
POHS_TYPES = {
    "road_banner",
    "bus_shelter",
    "subway_light",
    "bus_road",
    "streetlamp_banner",
    "subway_inner",
}

# --- Fabric 수정 불가능 (image-only) ---
LOGO_TYPES = {
    "logo_illustration",
    "logo_typography",
}

MSHS_TYPES = {
    "sign_parking",
    "sign_welcome",
    "sign_toilet",
    "goods_sticker",
    "goods_key_ring",
    "goods_emoticon",
}

MASCOT_VIDEO_TYPES = {"mascot_video"}
POSTER_VIDEO_TYPES = {"poster_video"}
CARDNEWS_TYPES = {"poster_cardnews"}
ETC_VIDEO_TYPES = {"etc_video"}
NEWS_TYPES = {"news"}  # pass
LEAFLET_TYPES = {"leaflet"}  # pass


# ============================================================
# 4. 매핑 테이블
# ============================================================

TYPE_PIPELINE_MAP = {
    # 수정 가능한 6종
    "road_banner": run_road_banner_to_editor,
    "bus_shelter": run_bus_shelter_to_editor,
    "subway_light": run_subway_light_to_editor,
    "bus_road": run_bus_road_to_editor,
    "streetlamp_banner": run_streetlamp_banner_to_editor,
    "subway_inner": run_subway_inner_to_editor,

    # 로고 2종
    "logo_illustration": run_logo_illustration_to_editor,
    "logo_typography": run_logo_typography_to_editor,

    # Poster 파생
    # "poster_cardnews": run_poster_cardnews_to_editor,
    "leaflet": run_leaflet_to_editor,
    "poster_video": run_poster_video_to_editor,
    # "live_poster": run_live_poster_to_editor,

    # Mascot 파생
    "sign_parking": run_sign_parking_to_editor,
    "sign_welcome": run_sign_welcome_to_editor,
    "sign_toilet": run_sign_toilet_to_editor,
    "goods_sticker": run_goods_sticker_to_editor,
    "goods_key_ring": run_goods_key_ring_to_editor,
    "goods_emoticon": run_goods_emoticon_to_editor,
    "mascot_video": run_mascot_video_to_editor,

    # etc
    "etc_video": run_etc_video_to_editor,
    # "news": run_news_to_editor
}


# ============================================================
# 5. 유틸 함수
# ============================================================

def _format_period_ko(start_dt, end_dt) -> str:
    if isinstance(start_dt, datetime):
        start_dt = start_dt.date()
    if isinstance(end_dt, datetime):
        end_dt = end_dt.date()
    return f"{start_dt:%Y.%m.%d} ~ {end_dt:%Y.%m.%d}"


def _get_next_run_id() -> int:
    editor_root = Path(EDITOR_ROOT_DIR)
    editor_root.mkdir(parents=True, exist_ok=True)

    max_id = 0
    for child in editor_root.iterdir():
        if child.is_dir() and child.name.isdigit():
            max_id = max(max_id, int(child.name))
    return max_id + 1


def _local_path_to_static_url(path) -> str:
    path = Path(path).resolve()
    root = Path(EDITOR_ROOT_DIR).resolve()
    rel = path.relative_to(root)
    return f"{STATIC_BASE_URL}/{rel.as_posix()}"

def append_extra_items_to_total(total_json_path: str, extra_items: List[dict]) -> str:
    """
    build_total_layout(...) 이 리턴한 total.json 경로에
    extra_items를 append 한다.
    total.json 루트가 list 인 경우와 dict+items 인 경우 모두 지원.
    """
    total_path = Path(total_json_path)

    if not total_path.exists():
        logger.error("[editor.build] total.json not found: %s", total_path)
        return total_json_path

    with total_path.open("r", encoding="utf-8") as f:
        total_data = json.load(f)

    logger.info("[editor.build] total.json root type=%s", type(total_data).__name__)

    # 1) 루트가 리스트인 경우: 그냥 뒤에 붙이기
    if isinstance(total_data, list):
        total_data.extend(extra_items)

    # 2) 루트가 dict + items 인 경우
    elif isinstance(total_data, dict):
        items = total_data.get("items", [])
        items.extend(extra_items)
        total_data["items"] = items

    else:
        logger.warning(
            "[editor.build] unexpected total.json root type: %s, skip merge",
            type(total_data).__name__,
        )
        return total_json_path

    with total_path.open("w", encoding="utf-8") as f:
        json.dump(total_data, f, ensure_ascii=False, indent=2)

    return str(total_path)



# ============================================================
# 6. 메인 빌드 로직
# ============================================================

@router.post("/build", response_model=PythonBuildResponse)
def build_editor_templates(payload: EditorBuildRequest):
    logger.info("##### [editor.build] ENTER v3 #####")
    try:
        # 1) run id 생성
        run_id = _get_next_run_id()
        logger.info(f"[editor.build] start pNo={payload.pNo}, run_id={run_id}")

        db_file_paths = []
        db_file_types = []
        extra_items = []

        payload_data = payload.posters[0]

        # 기본 필드
        festival_name_ko = payload_data.title
        festival_period_ko = _format_period_ko(payload_data.festivalStartDate,
                                               payload_data.festivalEndDate)
        festival_location_ko = payload_data.location
        poster_image_url = payload_data.posterImageUrl
        mascot_image_url = getattr(payload_data, "mascotImageUrl", None)
        concept_description = payload_data.conceptDescription
        program_name = payload_data.programName

        t_list = payload_data.types

        logger.info(f"[editor.build] types={t_list}")

        # 2) 타입별 파이프라인 실행
        for t in t_list:

            if t == "news":
                logger.info("[editor.build] news → pass")
                continue

            fn = TYPE_PIPELINE_MAP.get(t)
            if not fn:
                logger.warning(f"[editor.build] unknown type {t}")
                continue

            result = None

            # --- POHS: 수정 가능한 6종 ---
            if t in POHS_TYPES:
                result = fn(
                    run_id= run_id,
                    poster_image_url=poster_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko
                )

            # --- LOGO (수정 불가능) ---
            elif t in LOGO_TYPES:
                result = fn(
                    p_no=payload.pNo,
                    poster_image_url=poster_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko
                )

            # --- Mascot 파생 ---
            elif t in MSHS_TYPES:
                result = fn(
                    p_no=payload.pNo,
                    mascot_image_url=mascot_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko
                )

            # --- LIVE ---
            elif t in LEAFLET_TYPES:
                result = fn(
                    project_id=payload.pNo,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                    program_name=program_name,
                    concept_description=concept_description,
                    poster_image_url=poster_image_url,
                    layout_ref_image_url=test_layout_image_url
                )

            # --- Mascot Video ---
            elif t in MASCOT_VIDEO_TYPES:
                result = fn(
                    project_id=payload.pNo,
                    mascot_image_url=mascot_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                    program_name=program_name,
                    concept_description=concept_description
                )

            # --- Poster Video ---
            elif t in POSTER_VIDEO_TYPES:
                result = fn(
                    project_id=payload.pNo,
                    poster_image_url=poster_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                    concept_description=concept_description
                )

            # --- Poster Cardnews ---
            elif t in CARDNEWS_TYPES:
                result = fn(
                    project_id=payload.pNo,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                    program_name=program_name,
                    concept_description=concept_description
                )

            # --- ETC VIDEO ---
            elif t in ETC_VIDEO_TYPES:
                result = fn(
                    project_id=payload.pNo,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                    program_name=program_name,
                    concept_description=concept_description
                )

            # 결과 처리
            if not result:
                continue

            if t not in POHS_TYPES:
                db_file_type = result.get("db_file_type")
                db_file_path = result.get("db_file_path")
                if db_file_path:
                    db_file_paths.append(db_file_path)
                    db_file_types.append(db_file_type)
                
                extra_items.append({
                    "type": result.get("db_file_type"),      # == {db_file_type}
                    "category": result.get("type_ko"),  # == 타입 한글명
                    "canvasData": {
                        "objects": [
                            {
                                "type": result.get("type"),  # == {type}
                                "url": result.get("db_file_path"),  # == {db_file_path}
                            }
                        ]
                    }
                })
                logger.info(f"[editor.build] extra_items count={len(extra_items)}")
                logger.info(f"[editor.build] extra_items sample={extra_items[:2]}")
        # -------------------------------------------------------
        # 3) before-editor (텍스트 제거 / OCR 템플릿 준비)
        # -------------------------------------------------------
        from app.service.editor.make_before_edtior import run as run_before_editor
        run_before_editor(run_id=run_id)

        # -------------------------------------------------------
        # 4) total.json 생성 (템플릿 + 파생물 append)
        # -------------------------------------------------------
        from app.service.editor.mkake_after_editor import build_total_layout
        built_total = build_total_layout(run_id=run_id)

        # -------------------------------------------------------
        # 5) 비-POHS extra_items를 total.json에 append
        # -------------------------------------------------------
        logger.info("[editor.build] extra_items count=%d", len(extra_items))
        built_total = append_extra_items_to_total(
            total_json_path=built_total,
            extra_items=extra_items,
        )
        print("test111")
        print(extra_items)
        logger.info(
            "[editor.build] RAW_RESPONSE pNo=%s, db_file_paths=%s, db_file_types=%s",
            payload.pNo,
            db_file_paths,
            db_file_types,
        )


        resp = PythonBuildResponse(
            status="success",
            pNo=payload.pNo,
            filePath=built_total,
            dbFilePath=db_file_paths,
            dbFileType=db_file_types
        )
        logger.info(
            "[editor.build] RESPONSE pNo=%s, dbFilePath=%s, dbFileType=%s",
            resp.pNo,
            resp.dbFilePath,
            resp.dbFileType,
        )
        print("resp")
        print(resp)
        return resp
        

    except Exception as e:
        logger.exception("[editor.build] ERROR")
        raise HTTPException(status_code=500, detail=f"Editor build failed: {e}")

