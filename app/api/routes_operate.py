# -*- coding: utf-8 -*-
"""
app/api/routes_operate.py

한 번의 요청으로 여러 배너(/road-banner/operate, /streetlamp-banner/operate 등)를
동시에 실행하고, 결과 JSON + 이미지를 editor 디렉터리 구조에 저장하는 라우터.

입력 JSON 예시:

{
  "poster_image_url": "http://localhost:5000/static/banner/busan.png",
  "festival_name_ko": "제12회 해운대 빛축제",
  "festival_period_ko": "2025.11.29 ~ 2026.01.18",
  "festival_location_ko": "해운대해수욕장 구남로 일원",
  "type": ["road_banner", "streetlamp_banner"]
}

동작:

- run_id = data/editor 폴더 안의 숫자 폴더 최대값 + 1 (없으면 1부터)
- data/editor/{run_id}/before_data
- data/editor/{run_id}/before_image

- type 에 따라:
    "road_banner"       → /road-banner/operate 와 동일 로직 실행
    "streetlamp_banner" → /streetlamp-banner/operate 와 동일 로직 실행

- 각 결과는
    before_data/road_banner.json
    before_data/streetlamp_banner.json
  으로 저장되며, JSON 맨 위에 "run_id": <run_id> 가 추가된다.

- 이미지 파일은 결과 JSON의 image_path 에 있는 파일을
  before_image/원래파일명 으로 복사한다.
"""

from __future__ import annotations

import os
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 기존 라우터에서 쓰던 DTO + operate 함수 재사용
from app.api.routes_road_banner import (  # type: ignore
    RoadBannerRequest,
    operate_road_banner,
)
from app.api.routes_streetlamp_banner import (  # type: ignore
    StreetlampBannerRequest,
    operate_streetlamp_banner,
)

# ---------------------------------------------------------
# 설정: editor 루트 디렉토리
# ---------------------------------------------------------

EDITOR_ROOT = Path(os.getenv("EDITOR_ROOT", "data/editor"))


class MultiOperateRequest(BaseModel):
    poster_image_url: str
    festival_name_ko: str
    festival_period_ko: str
    festival_location_ko: str
    # 예: ["road_banner", "streetlamp_banner"]
    # None 또는 [] 인 경우 → 지원하는 모든 배너 타입 실행
    type: List[str] | None = None


router = APIRouter(tags=["Operate"])


# ---------------------------------------------------------
# run_id 계산 + 디렉토리 생성
# ---------------------------------------------------------

def _get_next_run_id() -> int:
    """
    data/editor 밑의 숫자 폴더들을 보고 다음 run_id를 계산한다.
    (아무 폴더도 없으면 1부터 시작)
    """
    EDITOR_ROOT.mkdir(parents=True, exist_ok=True)

    ids: list[int] = []
    for p in EDITOR_ROOT.iterdir():
        if p.is_dir() and p.name.isdigit():
            try:
                ids.append(int(p.name))
            except ValueError:
                continue

    if not ids:
        return 1
    return max(ids) + 1


def _ensure_run_dirs(run_id: int) -> tuple[Path, Path]:
    """
    data/editor/{run_id}/before_data, before_image 디렉토리 생성
    """
    base_dir = EDITOR_ROOT / str(run_id)
    before_data_dir = base_dir / "before_data"
    before_image_dir = base_dir / "before_image"

    before_data_dir.mkdir(parents=True, exist_ok=True)
    before_image_dir.mkdir(parents=True, exist_ok=True)

    return before_data_dir, before_image_dir


# ---------------------------------------------------------
# 결과 JSON + 이미지 저장
# ---------------------------------------------------------

def _save_banner_result(
    run_id: int,
    banner_type_key: str,          # "road_banner" / "streetlamp_banner" (파일명용)
    result: Dict[str, Any],        # /road-banner/operate 결과 JSON 그대로
    before_data_dir: Path,
    before_image_dir: Path,
) -> None:
    """
    - result dict 맨 위에 "run_id": <run_id> 를 추가
    - before_data/{banner_type_key}.json 으로 저장
    - result["image_path"] 파일을 before_image/원래파일명 으로 복사
    """
    if "image_path" not in result:
        raise HTTPException(
            status_code=500,
            detail=f"{banner_type_key} 결과에 image_path가 없습니다.",
        )

    # run_id를 맨 앞에 추가 (dict 삽입 순서 보장)
    data = {"run_id": run_id, **result}

    json_path = before_data_dir / f"{banner_type_key}.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    # 이미지 복사
    src_image = Path(str(result["image_path"]))
    if not src_image.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"{banner_type_key} 이미지 파일을 찾을 수 없습니다: {src_image}",
        )

    dst_image = before_image_dir / src_image.name
    shutil.copy2(src_image, dst_image)


# ---------------------------------------------------------
# 각 배너 실행 래퍼
#   - 입력: MultiOperateRequest에서 공통 필드만 dict로 꺼낸 payload
#   - 출력: 기존 /road-banner/operate, /streetlamp-banner/operate 의 응답 JSON
# ---------------------------------------------------------

def _exec_road_banner(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    /road-banner/operate 와 완전히 같은 로직 실행.
    RoadBannerRequest 객체를 만들어서 operate_road_banner 를 직접 호출.
    """
    req = RoadBannerRequest(**payload)
    return operate_road_banner(req)


def _exec_streetlamp_banner(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    /streetlamp-banner/operate 와 완전히 같은 로직 실행.
    """
    req = StreetlampBannerRequest(**payload)
    return operate_streetlamp_banner(req)


# 앞으로 타입이 늘어나면 여기 dict만 확장하면 됨
SUPPORTED_BANNERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    # 입력 JSON의 type 값 → 실행 함수
    "road_banner": _exec_road_banner,
    "streetlamp_banner": _exec_streetlamp_banner,
}


# ---------------------------------------------------------
# /operate 엔드포인트
# ---------------------------------------------------------

@router.post("/operate")
def operate(req: MultiOperateRequest) -> Dict[str, Any]:
    """
    예)
    POST /operate
    {
      "poster_image_url": "...",
      "festival_name_ko": "...",
      "festival_period_ko": "...",
      "festival_location_ko": "...",
      "type": ["road_banner", "streetlamp_banner"]
    }

    동작:
    - run_id 계산
    - type 에 지정된 각 배너 타입에 대해:
        * 기존 /road-banner/operate, /streetlamp-banner/operate 와 동일 로직 실행
        * 결과 JSON에 run_id 를 추가해서 before_data에 저장
        * 결과 이미지 파일을 before_image에 복사
    """
    # 1) run_id 결정 + 폴더 생성
    run_id = _get_next_run_id()
    before_data_dir, before_image_dir = _ensure_run_dirs(run_id)

    # 2) 공통 payload (type은 서비스 함수에 넘기지 않음)
    payload: Dict[str, Any] = req.dict(exclude={"type"})

    # 3) 어떤 타입들을 실행할지 결정
    if req.type is None or len(req.type) == 0:
        requested_types = list(SUPPORTED_BANNERS.keys())
    else:
        requested_types = req.type

    executed: list[str] = []

    for banner_type_key in requested_types:
        executor = SUPPORTED_BANNERS.get(banner_type_key)
        if executor is None:
            raise HTTPException(
                status_code=400,
                detail=f"지원하지 않는 type 값입니다: {banner_type_key}",
            )

        # 기존 operate_* 와 동일한 결과 JSON
        result = executor(payload)

        # JSON + 이미지 저장
        _save_banner_result(
            run_id=run_id,
            banner_type_key=banner_type_key,
            result=result,
            before_data_dir=before_data_dir,
            before_image_dir=before_image_dir,
        )

        executed.append(banner_type_key)

    # 응답은 어디에 저장됐는지만 간단히 알려주면 충분
    return {
        "run_id": run_id,
        "executed": executed,
        "before_data_dir": str(before_data_dir),
        "before_image_dir": str(before_image_dir),
    }
