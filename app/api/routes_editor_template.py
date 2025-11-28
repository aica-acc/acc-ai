from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Callable

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

# -----------------------------
# 외부 파이프라인 함수들 import
# -----------------------------
from app.service.banner_khs.make_road_banner import (  # type: ignore
    _build_placeholder_from_hangul,
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _extract_poster_url_from_input,
    _save_image_from_file_output,
    _download_image_bytes,
    run_road_banner_to_editor,
)
from app.service.subway.make_subway_inner import run_subway_inner_to_editor
from app.service.subway.make_subway_light import run_subway_light_to_editor
from app.service.bus.make_bus_road import run_bus_road_to_editor
from app.service.bus.make_bus_shelter import run_bus_shelter_to_editor
from app.service.banner_khs.make_streetlamp_banner import run_streetlamp_banner_to_editor

from app.service.editor.make_before_edtior import run as run_before_editor
from app.service.editor.mkake_after_editor import build_total_layout

# ============================================================
# 0. 공통 설정 / 상수
# ============================================================

router = APIRouter(prefix="/editor", tags=["Editor Build"])

# 프로젝트 루트
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

# .env 로드
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Editor 데이터 루트
EDITOR_ROOT_DIR = r"C:\final_project\ACC\acc-ai\app\data\editor"
OUTPUT_ROOT_DIR = r"./output_editor"
LAYOUT_TEMPLATES_DIR = Path(EDITOR_ROOT_DIR) / "layout_templates"

# FastAPI 에서 mount 한 static URL prefix
STATIC_BASE_URL = "http://127.0.0.1:5000/static/editor"

logger = logging.getLogger(__name__)

# OpenAI 클라이언트 (필요시 사용)
_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    """환경변수 OPENAI_API_KEY 를 사용해 전역 OpenAI 클라이언트를 하나만 만든다."""
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


# (참고용) 각 매체 고정 스펙 - 필요하면 하위 함수에서 사용
BANNER_TYPE = "road_banner"
BANNER_PRO_NAME = "도로용 현수막"
BANNER_WIDTH = 4096
BANNER_HEIGHT = 1024

BUS_ROAD_TYPE = "bus_road"
BUS_ROAD_PRO_NAME = "버스 차도용"
BUS_ROAD_WIDTH = 3788
BUS_ROAD_HEIGHT = 1024

BUS_SHELTER_TYPE = "bus_shelter"
BUS_SHELTER_PRO_NAME = "버스 쉘터"
BUS_SHELTER_WIDTH = 1024
BUS_SHELTER_HEIGHT = 1906

SUBWAY_INNER_TYPE = "subway_inner"
SUBWAY_INNER_PRO_NAME = "지하철 차내액자"
SUBWAY_INNER_WIDTH_PX = 1446
SUBWAY_INNER_HEIGHT_PX = 1024

SUBWAY_LIGHT_TYPE = "subway_light"
SUBWAY_LIGHT_PRO_NAME = "지하철 조명광고"
SUBWAY_LIGHT_WIDTH_PX = 1500
SUBWAY_LIGHT_HEIGHT_PX = 1620


# ============================================================
# 1. Pydantic 모델 (요청/응답 DTO)
# ============================================================

class PosterIn(BaseModel):
    posterImageUrl: str
    title: str
    festivalStartDate: datetime   # "2025-11-03" 같은 문자열도 자동 파싱됨
    festivalEndDate: datetime
    location: str
    types: List[str]


class EditorBuildRequest(BaseModel):
    pNo: int
    posters: List[PosterIn]

class PythonBuildResponse(BaseModel):
    status : str
    pNo: int
    filePath: str


# ============================================================
# 2. 유틸 함수들
# ============================================================

# 타입 문자열 -> 파이프라인 함수 매핑
TYPE_PIPELINE_MAP: Dict[str, Callable[..., Any]] = {
    "road_banner": run_road_banner_to_editor,
    "streetlamp_banner": run_streetlamp_banner_to_editor,
    "subway_inner": run_subway_inner_to_editor,
    "subway_light": run_subway_light_to_editor,
    "bus_road": run_bus_road_to_editor,
    "bus_shelter": run_bus_shelter_to_editor,

    # 백엔드에서 다른 이름으로 보낼 경우 여기서 매핑
    # "all_bus_drivewayT": run_bus_road_to_editor,
}


def _format_period_ko(start_dt: datetime | date, end_dt: datetime | date) -> str:
    """
    시작/종료일을 'YYYY.MM.DD ~ YYYY.MM.DD' 형식으로 변환.
    예) 2025-11-03, 2025-11-06 → '2025.11.03 ~ 2025.11.06'
    """
    if isinstance(start_dt, datetime):
        start_dt = start_dt.date()
    if isinstance(end_dt, datetime):
        end_dt = end_dt.date()

    return f"{start_dt:%Y.%m.%d} ~ {end_dt:%Y.%m.%d}"


def _get_next_run_id() -> int:
    """
    data/editor 폴더 안의 숫자 폴더 중 가장 큰 값 + 1 을 run_id 로 사용.
    ex) .../editor/1, 2, 5 → 다음 run_id = 6
    """
    editor_root = Path(EDITOR_ROOT_DIR)
    editor_root.mkdir(parents=True, exist_ok=True)

    max_id = 0
    for child in editor_root.iterdir():
        if child.is_dir() and child.name.isdigit():
            max_id = max(max_id, int(child.name))

    return max_id + 1


def _local_path_to_static_url(path: str | Path) -> str:
    """
    EDITOR_ROOT_DIR 기준 상대 경로를 STATIC_BASE_URL 뒤에 붙여서 URL 로 변환.
    예)
      EDITOR_ROOT_DIR = C:/.../editor
      path            = C:/.../editor/3/total.json
      결과:
      http://127.0.0.1:5000/static/editor/3/total.json
    """
    path = Path(path).resolve()
    root = Path(EDITOR_ROOT_DIR).resolve()

    rel = path.relative_to(root)
    return f"{STATIC_BASE_URL}/{rel.as_posix()}"


# ============================================================
# 3. 메인 라우트: /editor/build
# ============================================================

@router.post("/build", response_model=PythonBuildResponse)
def build_editor_templates(payload: EditorBuildRequest):
    """
    Spring 에서 /editor/build 로 POST 요청을 보내는 엔드포인트.

    1) run_id 계산 (editor 폴더 max + 1)
    2) 각 poster별로 festival_period_ko 만들고, types 돌면서 대응 함수 실행
    3) inpainting 전/후 파이프라인 실행 (run_before_editor, build_total_layout)
    4) 생성된 total.json 등 레이아웃 파일 경로들을 static URL로 변환하여 반환

    ➜ Java (EditorBuildServiceImpl) 에서는 이 응답을 받아 DB에 filePath 저장.
    """
    try:
        # --------------------------------------------------
        # 1. run_id 생성
        # --------------------------------------------------
        run_id = _get_next_run_id()
        logger.info(
            f"[editor.build] start, pNo={payload.pNo}, "
            f"run_id={run_id}, posters={len(payload.posters)}"
        )

        # --------------------------------------------------
        # 2. 포스터별로 타입에 맞는 생성 함수 실행
        # --------------------------------------------------
        for poster in payload.posters:
            festival_name_ko = poster.title
            festival_location_ko = poster.location
            festival_period_ko = _format_period_ko(
                poster.festivalStartDate,
                poster.festivalEndDate,
            )
            poster_image_url = poster.posterImageUrl

            logger.info(
                f"[editor.build] poster title={festival_name_ko}, "
                f"period={festival_period_ko}, "
                f"location={festival_location_ko}, "
                f"types={poster.types}"
            )

            # types 기준으로 해당 파이프라인 실행
            for t in poster.types:
                fn = TYPE_PIPELINE_MAP.get(t)
                if not fn:
                    logger.warning(
                        f"[editor.build] unknown type '{t}' "
                        f"- skip (poster: {festival_name_ko})"
                    )
                    continue

                logger.info(f"[editor.build] run type={t} → {fn.__name__}")
                fn(
                    run_id=run_id,
                    poster_image_url=poster_image_url,
                    festival_name_ko=festival_name_ko,
                    festival_period_ko=festival_period_ko,
                    festival_location_ko=festival_location_ko,
                )

        # --------------------------------------------------
        # 3. before-editor 파이프라인 (OCR / inpainting 준비 등)
        # --------------------------------------------------
        logger.info(f"[editor.build] run before-editor pipeline, run_id={run_id}")
        # make_before_edtior.run 시그니처에 맞추어 호출
        run_before_editor(run_id=run_id)

        # --------------------------------------------------
        # 4. after-editor 파이프라인 (total.json 합치기)
        # --------------------------------------------------
        logger.info(f"[editor.build] build total layout, run_id={run_id}")
        built = build_total_layout(run_id=run_id)
            
        # --------------------------------------------------
        # 5. 응답 결과 구성 (PythonBuildResponse)
        # --------------------------------------------------
        # 5. 절대경로 string만 반환하도록 results에 1개만 넣어 감쌈

        resp = PythonBuildResponse(
                status="success",
                pNo=payload.pNo,
                filePath=built
         )
        


        

        logger.info(f"[editor.build] DONE, run_id={run_id}, returning 1 absolute path")
        return resp
    
        
    except Exception as e:
        logger.exception("[editor.build] ERROR")
        raise HTTPException(status_code=500, detail=f"Editor build failed: {e}")
