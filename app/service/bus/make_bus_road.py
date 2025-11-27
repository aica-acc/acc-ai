# -*- coding: utf-8 -*-
"""
app/service/bus/make_bus_road.py

버스 차도용(3.7:1) 가로 광고판용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 축제 회차/한글명/영문명/기간/장소를 이용해 3.7:1 버스 차도용 광고 프롬프트를 조립한다. (write_bus_road)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_bus_road)
  5) run_bus_road_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  6) python make_bus_road.py 로 단독 실행할 수 있다.

결과 JSON 형태 (editor용 최소 정보):

{
  "type": "bus_road",
  "pro_name": "버스 차도용",
  "festival_name_ko": "담양산타축제",
  "festival_count": "제7회",
  "festival_name_en": "damyang santa festival",
  "festival_period_ko": "2025.12.24 ~ 12.25",
  "festival_location_ko": "담양군 메타랜드 일원",
  "width": 3788,
  "height": 1024
}

※ 축제명에 회차가 없으면 festival_count는 강제로 "제 1회" 로 설정된다.

전제 환경변수
- OPENAI_API_KEY           : OpenAI API 키
- BANNER_LLM_MODEL         : (선택) 배너/버스용 LLM, 기본값 "gpt-4o-mini"
- BUS_ROAD_MODEL           : (선택) 기본값 "bytedance/seedream-4"
- BUS_ROAD_SAVE_DIR        : (선택) 직접 create_bus_road 를 쓸 때 저장 경로
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Tuple

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError

# -------------------------------------------------------------
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

# 버스 차도용 고정 스펙
BUS_ROAD_TYPE = "bus_road"
BUS_ROAD_PRO_NAME = "버스 차도용"
BUS_ROAD_WIDTH = 3788
BUS_ROAD_HEIGHT = 1024

# .env 로딩
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -------------------------------------------------------------
# 기존 road_banner 유틸 재사용
# -------------------------------------------------------------
from app.service.banner_khs.make_road_banner import (  # type: ignore
    _build_placeholder_from_hangul,
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _extract_poster_url_from_input,
    _save_image_from_file_output,
    _download_image_bytes,
)


# -------------------------------------------------------------
# 1) 한글 축제명에서 회차/축제명 분리
# -------------------------------------------------------------
def _split_festival_count_and_name(full_name_ko: str) -> Tuple[str, str]:
    """
    입력: "제7회 담양산타축제", "제 7회 담양산타축제", "담양산타축제" 등

    반환:
      (festival_count, festival_name_ko)

    규칙:
    - "제숫자회" 또는 "제 숫자 회" 패턴이 앞에 있으면:
        → festival_count: 공백 제거해서 "제7회" 형태로 정규화
        → festival_name_ko: 나머지 뒷부분 (양쪽 공백 제거)
    - 그런 패턴이 없으면:
        → festival_count: "제 1회"
        → festival_name_ko: 원본 전체(strip)
    """
    text = str(full_name_ko or "").strip()
    if not text:
        return "제 1회", ""

    m = re.match(r"^\s*(제\s*\d+\s*회)\s*(.*)$", text)
    if not m:
        return "제 1회", text

    raw_count = m.group(1)  # "제7회" or "제 7회"
    rest_name = m.group(2)  # 나머지 이름 부분

    # 내부 공백 제거해서 "제7회" 형태로 정규화
    normalized_count = re.sub(r"\s+", "", raw_count)

    name_ko = rest_name.strip() if rest_name.strip() else text
    return normalized_count, name_ko


# -------------------------------------------------------------
# 2) 버스 차도용 프롬프트 조립 (단순 배경 + 중앙 정렬 텍스트)
# -------------------------------------------------------------
def _build_bus_road_prompt_en(
    count_text: str,
    name_en_text: str,
    name_ko_text: str,
    period_text: str,
    location_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    절대 중앙 꾸밈 금지 + 양쪽 사이드만 꾸밈 + 자연스럽게 연결된 배경을 강제하는 3.7:1 버스 광고 프롬프트
    """

    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    count_text      = _norm(count_text)
    name_en_text    = _norm(name_en_text)
    name_ko_text    = _norm(name_ko_text)
    period_text     = _norm(period_text)
    location_text   = _norm(location_text)
    base_scene_en   = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)

    prompt = (
        f"Ultra-wide 3.7:1 festival poster-style illustration of {base_scene_en}, "
        "using the attached poster only for reference to overall color palette and mood, "
        "but creating a completely new composition. "

        # ⭐ 가장 중요한 규칙 (중앙부분 금지구역)
        "The CENTRAL REGION of the canvas must remain a CLEAN, EMPTY, UNDECORATED area "
        "with only a smooth, naturally blended continuation of the left and right backgrounds. "
        "Do NOT place any rockets, characters, symbols, objects, patterns, shapes, or decorations "
        "in the central region. Absolutely nothing except the text may appear there. "

        # ⭐ 배경 스타일: 양쪽 사이드 배경 + 자연스럽게 중앙으로 페이드
        "On the far left and far right sides, place the key decorative festival elements inspired by "
        f"{details_phrase_en}, such as rockets, mascots, or symbolic objects. "
        "These side elements must stay strictly within the outer 20–25% of each side. "
        "The background must seamlessly blend toward the center, becoming simple and unobtrusive near the text area, "
        "but it does NOT have to be white—just clean and softly merged into the middle. "

        # ⭐ 텍스트 블록 위치
        "Place a single block of festival text exactly in the horizontal center of the canvas, "
        "center-aligned, with generous empty margins on both sides. "

        f"Top line: \"{count_text}\" small and bold. "
        f"Next line: \"{name_en_text}\" medium-large bold subtitle. "
        f"Main title line: \"{name_ko_text}\" extremely large and heavy, the MOST dominant text. "
        f"Next line: \"{period_text}\" smaller bold line. "
        f"Final line: \"{location_text}\" slightly smaller, placed close beneath the period line. "

        # 텍스트 규칙
        "All text must be drawn in the very front layer, with NO object overlapping or touching the letters. "
        "Draw each quoted string exactly once and do not add any other text of any kind. "
        "Do not place the text inside a box, label, banner, frame, ribbon, or signboard; "
        "the letters must float cleanly over the simple center background. "

        "Do not draw quotation marks."
    )

    return prompt.strip()









# -------------------------------------------------------------
# 3) write_bus_road: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_bus_road(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    버스 차도용(3.7:1, 3788x1024) 가로 광고판용 Seedream 입력 JSON을 생성한다.

    - festival_name_ko: "제7회 담양산타축제" 또는 "담양산타축제" 등
      → 내부에서 회차/축제명을 분리해 사용한다.
    """

    # 1) 회차 / 축제명 분리 (없으면 festival_count = "제 1회")
    festival_count, pure_name_ko = _split_festival_count_and_name(festival_name_ko)

    # 2) 한글 축제 정보 → 영어 번역 (씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=pure_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 3) 자리수 맞춘 플레이스홀더 (프롬프트용)
    placeholders: Dict[str, str] = {
        "festival_count_placeholder": _build_placeholder_from_hangul(
            festival_count, "A"
        ),
        "festival_name_ko_placeholder": _build_placeholder_from_hangul(
            pure_name_ko, "B"
        ),
        # 영어명은 한글이 없으므로 그대로 사용
        "festival_name_en_placeholder": str(name_en or ""),
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "D"
        ),
        # 원문 백업
        "festival_base_count_placeholder": str(festival_count or ""),
        "festival_base_name_ko_placeholder": str(pure_name_ko or ""),
        "festival_base_name_en_placeholder": str(name_en or ""),
        "festival_base_period_placeholder": str(festival_period_ko or ""),
        "festival_base_location_placeholder": str(festival_location_ko or ""),
    }

    # 4) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 5) 최종 프롬프트 조립 (단순 배경 + 중앙 정렬 텍스트)
    prompt = _build_bus_road_prompt_en(
        count_text=placeholders["festival_count_placeholder"],
        name_en_text=placeholders["festival_name_en_placeholder"],
        name_ko_text=placeholders["festival_name_ko_placeholder"],
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 6) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": BUS_ROAD_WIDTH,
        "height": BUS_ROAD_HEIGHT,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "match_input_image",
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        "image_input": [
            {
                "type": "image_url",
                "url": poster_image_url,
            }
        ],
        # 결과 조립용으로 필요한 원본 정보도 같이 넣어둔다
        "festival_count": festival_count,
        "festival_name_ko_pure": pure_name_ko,
        "festival_name_en": name_en,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
    }

    seedream_input.update(placeholders)
    return seedream_input


# -------------------------------------------------------------
# 4) 버스 차도용 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_bus_road_save_dir() -> Path:
    """
    BUS_ROAD_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/bus_road 사용
    """
    env_dir = os.getenv("BUS_ROAD_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "bus_road"


# -------------------------------------------------------------
# 5) create_bus_road: Seedream JSON → Replicate 호출 → 이미지 저장
# -------------------------------------------------------------
def create_bus_road(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "bus_road_",
) -> Dict[str, Any]:
    """
    write_bus_road(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4 또는 BUS_ROAD_MODEL)에
       prompt + image_input과 함께 전달해
       실제 3.7:1 버스 차도용 광고 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.

    save_dir 가 주어지면 해당 디렉터리에 바로 저장하고,
    None 이면 BUS_ROAD_SAVE_DIR / app/data/bus_road 기본 경로를 사용한다.
    """

    # 1) 포스터 URL/경로 추출
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL/경로가 없습니다.")

    # 2) 포스터 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", BUS_ROAD_WIDTH))
    height = int(seedream_input.get("height", BUS_ROAD_HEIGHT))
    max_images = int(seedream_input.get("max_images", 1))
    aspect_ratio = seedream_input.get("aspect_ratio", "match_input_image")
    enhance_prompt = bool(seedream_input.get("enhance_prompt", True))
    sequential_image_generation = seedream_input.get(
        "sequential_image_generation", "disabled"
    )

    replicate_input = {
        "size": size,
        "width": width,
        "height": height,
        "prompt": prompt,
        "max_images": max_images,
        "image_input": [image_file],  # Replicate에는 실제 파일 객체로 전달
        "aspect_ratio": aspect_ratio,
        "enhance_prompt": enhance_prompt,
        "sequential_image_generation": sequential_image_generation,
    }

    model_name = os.getenv("BUS_ROAD_MODEL", "bytedance/seedream-4")

    # Seedream / Replicate 일시 오류(PA 등)에 대비한 재시도 로직
    output = None
    last_err: Exception | None = None

    for attempt in range(3):  # 최대 3번까지 시도
        try:
            output = replicate.run(model_name, input=replicate_input)
            break  # 성공하면 루프 탈출
        except ModelError as e:
            msg = str(e)
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            raise RuntimeError(
                f"Seedream model error during bus road banner generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during bus road banner generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during bus road banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_bus_road_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix=prefix
    )

    # Seedream 생성 결과 + seedream_input에 담아둔 메타데이터까지 같이 반환
    return {
        "size": size,
        "width": width,
        "height": height,
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        # 원본 축제 정보
        "festival_count": str(seedream_input.get("festival_count", "")),
        "festival_name_ko_pure": str(seedream_input.get("festival_name_ko_pure", "")),
        "festival_name_en": str(seedream_input.get("festival_name_en", "")),
        "festival_period_ko": str(seedream_input.get("festival_period_ko", "")),
        "festival_location_ko": str(seedream_input.get("festival_location_ko", "")),
    }


# -------------------------------------------------------------
# 6) editor 저장용 헬퍼 (run_id 기준)
# -------------------------------------------------------------
def run_bus_road_to_editor(
    run_id: int,
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    입력:
        run_id
        poster_image_url
        festival_name_ko   (예: "제7회 담양산타축제" 또는 "담양산타축제")
        festival_period_ko
        festival_location_ko

    동작:
      1) write_bus_road(...) 로 Seedream 입력용 seedream_input 생성
      2) create_bus_road(..., save_dir=before_image_dir) 로
         실제 버스 차도용 광고 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/bus_road.png 로 저장한다.
      3) 타입, 한글 축제명(회차 분리), 영어 축제명, 배너 크기만을 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/bus_road.json 에 저장한다.

    반환(예시):
      {
        "type": "bus_road",
        "pro_name": "버스 차도용",
        "festival_name_ko": "담양산타축제",
        "festival_count": "제7회",
        "festival_name_en": "damyang santa festival",
        "festival_period_ko": "2025.12.24 ~ 12.25",
        "festival_location_ko": "담양군 메타랜드 일원",
        "width": 3788,
        "height": 1024
      }
    """

    # 1) Seedream 입력 생성 (이 시점에서 회차/축제명 분리가 이루어짐)
    seedream_input = write_bus_road(
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # 2) editor 디렉터리 준비  ✅ app/data/editor/<run_id>/...
    editor_root = DATA_ROOT / "editor" / str(run_id)
    before_data_dir = editor_root / "before_data"
    before_image_dir = editor_root / "before_image"
    before_data_dir.mkdir(parents=True, exist_ok=True)
    before_image_dir.mkdir(parents=True, exist_ok=True)

    # 3) 실제 이미지 생성 (저장 위치를 before_image_dir 로 직접 지정)
    create_result = create_bus_road(
        seedream_input,
        save_dir=before_image_dir,
        prefix="bus_road_",
    )

    # 4) 최종 결과 JSON (API/백엔드에서 사용할 최소 정보 형태)
    result: Dict[str, Any] = {
        "type": BUS_ROAD_TYPE,
        "pro_name": BUS_ROAD_PRO_NAME,
        "festival_name_ko": create_result["festival_name_ko_pure"],
        "festival_count": create_result["festival_count"],
        "festival_name_en": create_result["festival_name_en"],
        "festival_period_ko": create_result["festival_period_ko"],
        "festival_location_ko": create_result["festival_location_ko"],
        "width": int(create_result.get("width", BUS_ROAD_WIDTH)),
        "height": int(create_result.get("height", BUS_ROAD_HEIGHT)),
    }

    # 5) before_data 밑에 JSON 저장 (파일명 고정)
    json_path = before_data_dir / "bus_road.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# -------------------------------------------------------------
# 7) CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    CLI 실행용 진입점.

    ✅ 콘솔에서:
        python app/service/bus/make_bus_road.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 버스 차도용 가로 광고 이미지 생성 (Seedream)
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 9  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    # 로컬 포스터 파일 경로 (예: PROJECT_ROOT/app/data/banner/...)
    # 축제명에 회차를 같이 넣어도 되고, 안 넣어도 됨
    # 예: "제7회 담양산타축제" 또는 "담양산타축제"
    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\goheung.png"
    festival_name_ko = "제 15회 고흥 우주항공 축제"
    festival_period_ko = "2025.05.03 ~ 2025.05.06"
    festival_location_ko = "고흥군 봉래면 나로우주센터 일원"

    # 2) 필수값 체크
    missing = []
    if not poster_image_url:
        missing.append("poster_image_url")
    if not festival_name_ko:
        missing.append("festival_name_ko")
    if not festival_period_ko:
        missing.append("festival_period_ko")
    if not festival_location_ko:
        missing.append("festival_location_ko")

    if missing:
        print("⚠️ main() 안에 아래 값들을 채워주세요:")
        for k in missing:
            print("  -", k)
        return

    # 3) 실제 실행
    result = run_bus_road_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "bus_road.json"
    image_path = editor_root / "before_image" / "bus_road.png"

    print("✅ bus road banner 생성 + editor 저장 완료")
    print("  type                 :", result.get("type"))
    print("  pro_name             :", result.get("pro_name"))
    print("  festival_count       :", result.get("festival_count"))
    print("  festival_name_ko     :", result.get("festival_name_ko"))
    print("  festival_name_en     :", result.get("festival_name_en"))
    print("  festival_period_ko   :", result.get("festival_period_ko"))
    print("  festival_location_ko :", result.get("festival_location_ko"))
    print("  width x height       :", result.get("width"), "x", result.get("height"))
    print("  json_path            :", json_path)
    print("  image_path           :", image_path)


if __name__ == "__main__":
    main()
