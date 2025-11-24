# -*- coding: utf-8 -*-
"""
app/service/run_all_ads_batch.py

버스 외부광고 + 지하철 스크린도어 + 현수막(banner) 전부를
한 번에 선택적으로 실행해서 editor/<run_id>/before_data, before_image 에 저장하는 배치 실행 모듈.

역할
- 공통 입력(포스터 이미지, 축제명/기간/장소)을 받아서
  bus / subway_platform / banner 각각의 run_*_to_editor(...) 함수를
  디렉터리를 스캔해서 자동으로 찾고,
  내가 선택한 타입만 골라 여러 개 한 번에 돌린다.

규칙
- 모듈 파일명:  app/service/***/make_xxx.py
- 실행 함수명:  run_xxx_to_editor(...)
- 타입 이름:    "xxx"   (target_types 에서 이 이름으로 사용)

예)
  app/service/bus/make_medium_bus_driveway.py  안에
      def run_medium_bus_driveway_to_editor(...):
  => 타입 이름: "medium_bus_driveway"

사용 예시 (CLI):
    python app/service/run_all_ads_batch.py
또는
    python -m app.service.run_all_ads_batch
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

# -------------------------------------------------------------
# 프로젝트 루트 sys.path 세팅 (직접 실행 대비)
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Runner 타입: run_xxx_to_editor(run_id, poster_image_url, festival_name_ko, ...) 시그니처
Runner = Callable[[int, str, str, str, str], Dict[str, Any]]

# 어떤 디렉터리에서 make_*.py 를 스캔할지 정의
# (필요하면 여기서 새 폴더만 추가하면 됨)
AD_MODULE_FOLDERS: List[tuple[str, str]] = [
    ("banner_khs", "app.service.banner_khs"),
    ("bus", "app.service.bus"),
    ("subway_platform", "app.service.subway_platform"),
]


# -------------------------------------------------------------
# 디렉터리 스캔해서 run_*_to_editor 자동 등록
# -------------------------------------------------------------
def _discover_ad_runners() -> Dict[str, Runner]:
    """
    app/service/<subdir>/make_*.py 파일들을 전부 뒤져서

      - 파일명: make_xxx.py
      - 모듈:  app.service.<subdir>.make_xxx
      - 함수:  run_xxx_to_editor

    를 자동으로 import + getattr 해서
    { "xxx": run_xxx_to_editor, ... } 형태의 dict 로 반환한다.
    """
    registry: Dict[str, Runner] = {}

    service_root = PROJECT_ROOT / "app" / "service"

    for subdir, pkg_base in AD_MODULE_FOLDERS:
        folder = service_root / subdir
        if not folder.is_dir():
            continue

        for path in folder.glob("make_*.py"):
            module_stem = path.stem  # e.g. "make_medium_bus_driveway"
            if module_stem == "__init__":
                continue

            # make_ 접두어 제거 → 타입 이름 / 함수 이름의 가운데 부분
            type_name = module_stem[len("make_") :]
            if not type_name:
                continue

            module_name = f"{pkg_base}.{module_stem}"
            func_name = f"run_{type_name}_to_editor"

            try:
                module = importlib.import_module(module_name)
                runner = getattr(module, func_name)
            except Exception as e:
                # 해당 모듈에 run_xxx_to_editor 가 없거나 import 실패하면 스킵
                print(
                    f"⚠️  스킵: {module_name}.{func_name} 가져오기 실패 ({e.__class__.__name__}: {e})"
                )
                continue

            # 정상적으로 runner 를 찾으면 레지스트리에 등록
            registry[type_name] = runner
            print(f"✅ runner 등록: {type_name}  ←  {module_name}.{func_name}")

    return registry


# 모듈 import 시점에 한 번만 스캔
ALL_AD_RUNNERS: Dict[str, Runner] = _discover_ad_runners()


def list_available_ad_types() -> List[str]:
    """
    현재 자동으로 발견된 모든 광고 타입 이름을 반환한다.
    (디버깅/확인용)
    """
    return sorted(ALL_AD_RUNNERS.keys())


# -------------------------------------------------------------
# 공통 배치 실행 함수
# -------------------------------------------------------------
def run_ads_batch_to_editor(
    run_id: int,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
    target_types: List[str] | None = None,
) -> Dict[str, Any]:
    """
    공통 입력으로 banner + bus + subway_platform 타입들을
    한 번에 여러 개 실행해서 editor/<run_id>/... 에 저장한다.

    입력:
        run_id               : editor/<run_id>/... 에 저장할 번호
        poster_image_url     : 포스터 이미지 경로/URL
        festival_name_ko     : 축제명 (한글)
        festival_period_ko   : 축제 기간 (한글/숫자)
        festival_location_ko : 축제 장소 (한글/영문)
        target_types         : 실행할 타입 이름 리스트
                               None 이면 ALL_AD_RUNNERS 의 모든 타입 실행

    타입 이름 규칙:
      - 파일: app/service/**/make_<type>.py
      - 함수: run_<type>_to_editor(...)
      - 여기서 <type> 문자열이 target_types 에서 사용하는 이름.

    반환:
        {
          "run_id": 10,
          "status": "success" | "partial_success" | "error",
          "results": {
            "medium_bus_driveway": {...},
            "screendoor_a_type_wall": {...},
            ...
          },
          "errors": {
            "streetlamp_banner": "runner not registered",
            ...
          }
        }
    """
    if not ALL_AD_RUNNERS:
        raise RuntimeError("등록된 광고 runner 가 없습니다. make_*.py 파일을 확인하세요.")

    if target_types is None:
        target_types = list(ALL_AD_RUNNERS.keys())

    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}

    print("=== Batch run start ===")
    print("run_id        :", run_id)
    print("target_types  :", target_types)
    print("available_all :", list_available_ad_types())
    print()

    for type_name in target_types:
        runner = ALL_AD_RUNNERS.get(type_name)
        if runner is None:
            msg = "runner not registered"
            errors[type_name] = msg
            print(f"⚠️ [{type_name}] {msg}")
            continue

        try:
            print(f"▶ [{type_name}] 생성 시작...")
            result = runner(
                run_id=run_id,
                poster_image_url=poster_image_url,
                festival_name_ko=festival_name_ko,
                festival_period_ko=festival_period_ko,
                festival_location_ko=festival_location_ko,
            )
            results[type_name] = result
            print(f"✅ [{type_name}] 생성 완료")
        except Exception as e:
            msg = f"{e.__class__.__name__}: {e}"
            errors[type_name] = msg
            print(f"❌ [{type_name}] 생성 실패: {msg}")

    if results and not errors:
        status = "success"
    elif results and errors:
        status = "partial_success"
    else:
        status = "error"

    print("=== Batch run end ===\n")

    return {
        "run_id": int(run_id),
        "status": status,
        "results": results,
        "errors": errors,
    }


# -------------------------------------------------------------
# CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    CLI 실행 예시.

    ✅ 콘솔에서:
        python app/service/run_all_ads_batch.py
    또는
        python -m app.service.run_all_ads_batch

    를 실행하면, 지정한 포스터/축제정보로
    등록된 banner + bus + subway_platform 타입을
    원하는 것만 골라서 한 번에 생성할 수 있다.
    """
    # 1) 여기 값만 네가 원하는 걸로 수정하면 됨
    run_id = 7  # editor/<run_id>/... 공통 번호

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\geoje.png"
    festival_name_ko = "거제몽돌해변축제"
    festival_period_ko = "2013.07.13 ~ 07.14"
    festival_location_ko = "학동흑진주몽돌해변"

    # 2) 어떤 타입들을 한 번에 돌릴지 선택
    #   - None: ALL_AD_RUNNERS 전체
    #   - 리스트: 내가 고른 것만
    #
    # 예시 1) 전부:
    # target_types = None
    #
    # 예시 2) 버스 1개 + 스크린도어 2개만:
    # target_types = [
    #     "medium_bus_driveway",
    #     "screendoor_a_type_wall",
    #     "screendoor_e_type_high",
    # ]
    #
    # 예시 3) 방금 스캔된 타입 전체를 보고 싶을 때:
    #   print(list_available_ad_types())
    #
    target_types = [
        "all_bus_drivewayT",
        # "bus_shelter",
        # "daewoo_bus_sidewalkT",
        # "general_bus_driveway",
        # "general_bus_getoff",
        # "general_bus_sidewalkT",
        # "hyundai_bus_sidewalkT",
        # "medium_bus_driveway",
        # "medium_bus_getoff",
        "medium_bus_sidewalkT",
        "road_banner",
        # "screendoor_a_type_high",
        # "screendoor_a_type_sticker",
        # "screendoor_a_type_wall",
        # "screendoor_b_type_sticker",
        # "screendoor_b_type_wall",
        # "screendoor_e_type_high",
        # "screendoor_e_type_wall",
        "streetlamp_banner",
    ]

    batch_result = run_ads_batch_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
        target_types=target_types,
    )

    print("===== Batch Result Summary =====")
    print("run_id :", batch_result["run_id"])
    print("status :", batch_result["status"])
    print("generated types :", list(batch_result["results"].keys()))
    if batch_result["errors"]:
        print("errors:")
        for t, msg in batch_result["errors"].items():
            print("  -", t, "=>", msg)


if __name__ == "__main__":
    main()
