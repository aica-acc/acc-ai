# -*- coding: utf-8 -*-
"""
app/service/subway_platform/make_screendoor_a_type_wall.py

지하철 스크린도어 A형 벽체(21:17) 외부 광고용 Seedream 입력/프롬프트 생성
+ 생성 이미지 저장 + 폰트/색상 추천 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 한글 자리수에 맞춘 플레이스홀더 텍스트(라틴 알파벳 시퀀스)를 사용해서
     21:17 비율 스크린도어 A형 벽체 프롬프트를 조립한다. (write_screendoor_a_type_wall)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_screendoor_a_type_wall)
  5) 완성된 배너 이미지를 기반으로 폰트/색상 추천을 수행한다.
  6) run_screendoor_a_type_wall_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  7) python make_screendoor_a_type_wall.py 로 단독 실행할 수 있다.

전제 환경변수
- OPENAI_API_KEY                           : OpenAI API 키
- BANNER_LLM_MODEL                         : (선택) 기본값 "gpt-4o-mini"
- SUBWAY_SCREENDOOR_A_TYPE_WALL_MODEL      : (선택) 기본값 "bytedance/seedream-4"
- SUBWAY_SCREENDOOR_A_TYPE_WALL_SAVE_DIR   : (선택, create_* 단독 사용 시)
    * 절대경로면 그대로 사용
    * 상대경로면 acc-ai 프로젝트 루트 기준
    * 미설정 시 PROJECT_ROOT/app/data/subway_screendoor_a_type_wall 사용

CLI 실행:
    python make_screendoor_a_type_wall.py
"""

from __future__ import annotations

import os
import sys
import time
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import replicate
from dotenv import load_dotenv
from replicate.exceptions import ModelError

# -------------------------------------------------------------
# 프로젝트 루트 및 DATA_ROOT, .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

# .env 로딩 (예: C:\final_project\ACC\acc-ai\.env)
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

# 폰트/색상 추천 모듈 (지하철/버스 공용으로 사용 가능)
from app.service.font_color.bus_font_color_recommend import (  # type: ignore
    recommend_fonts_and_colors_for_bus,
)


# -------------------------------------------------------------
# 1) 영어 씬 묘사 + 플레이스홀더 텍스트 → 스크린도어 A형 벽체 프롬프트
# -------------------------------------------------------------
def _build_screendoor_a_type_wall_prompt_en(
    name_text: str,
    period_text: str,
    location_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    21:17 비율 지하철 스크린도어 A형 벽체용 영어 프롬프트 생성.
    실제 역사/열차/스크린도어 구조물은 그리지 않고, 광고 이미지 자체만 생성하도록 설계.
    """

    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)
    name_text = _norm(name_text)
    period_text = _norm(period_text)
    location_text = _norm(location_text)

    prompt = (
        f"Wide rectangular festival illustration of {base_scene_en}, "
        "designed as a 21:17 aspect ratio wall-type screen door advertisement in a subway platform, "
        "but do not draw any actual train, subway car, platform, station architecture, physical screen doors, "
        "frames, clamps, or mounting structures. "
        "Treat this as a standalone poster-like artwork only. "
        "Fill the entire canvas edge to edge with the scene, "
        "with no black bars, frames, borders, or letterbox areas at the top or bottom. "
        "Use the attached poster image only as reference for bright colors, lighting and atmosphere, "
        f"but create a completely new scene with {details_phrase_en}. "

        "Place three lines of text near the visual center of the advertisement, all perfectly center-aligned. "
        f"On the middle line, write \"{name_text}\" in extremely large, ultra-bold sans-serif letters, "
        "the largest text in the entire image and clearly readable from a very long distance. "
        f"On the top line, directly above the title, write \"{period_text}\" in smaller bold sans-serif letters, "
        "but still clearly readable from far away. "
        f"On the bottom line, directly below the title, write \"{location_text}\" in a size slightly smaller than the top line. "

        "All three lines must be drawn in the foremost visual layer, clearly on top of every background element, "
        "character, object, and effect in the scene, and nothing may overlap, cover, or cut through any part of the letters. "
        "Draw exactly these three lines of text once each. Do not draw any second copy, shadow copy, reflection, "
        "mirrored copy, outline-only copy, blurred copy, or partial copy of any of this text anywhere else in the image, "
        "including on the ground, sky, water, buildings, decorations, or interface elements. "
        "Do not add any other text at all: no extra words, labels, dates, numbers, logos, watermarks, UI elements, "
        "or any small text in the corners, such as aspect ratio labels or the words 'Subway', 'ScreenDoor', or model names. "
        "Do not place the text on any banner, signboard, panel, box, frame, ribbon, or physical board; "
        "draw only clean floating letters directly over the background. "
        "The quotation marks in this prompt are for instruction only; do not draw quotation marks in the final image."
    )

    return prompt.strip()


# -------------------------------------------------------------
# 2) write_screendoor_a_type_wall: Seedream 입력 JSON 생성 (+ 플레이스홀더 포함)
# -------------------------------------------------------------
def write_screendoor_a_type_wall(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    지하철 스크린도어 A형 벽체(21:17, 2100x1700) Seedream 입력 JSON을 생성한다.

    입력:
        poster_image_url    : 참고용 포스터 이미지 URL 또는 로컬 파일 경로
        festival_name_ko    : 축제명 (한글)
        festival_period_ko  : 축제 기간 (한글 또는 숫자/영문)
        festival_location_ko: 축제 장소 (한글 또는 영문)
    """

    # 1) 한글 축제 정보 → 영어 번역 (씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 2) 자리수 맞춘 플레이스홀더 + 원본 한글 텍스트 보존
    placeholders: Dict[str, str] = {
        # 축제명: A부터 시작하는 시퀀스
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        # 축제기간: 숫자/기호는 그대로, 한글만 C부터 시작하는 시퀀스
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        # 축제장소: B부터 시작하는 시퀀스
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "B"
        ),
        # 원본 한글 텍스트도 그대로 같이 넣어줌 (폰트/색상 추천 등에서 활용 가능)
        "festival_base_name_placeholder": str(festival_name_ko or ""),
        "festival_base_period_placeholder": str(festival_period_ko or ""),
        "festival_base_location_placeholder": str(festival_location_ko or ""),
    }

    # 3) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립 (21:17 스크린도어 A형 벽체)
    prompt = _build_screendoor_a_type_wall_prompt_en(
        name_text=placeholders["festival_name_placeholder"],
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    #   - 21:17 비율: width=2100, height=1700
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": 2100,
        "height": 1700,
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
    }

    # 플레이스홀더 + 원본 한글도 같이 포함
    seedream_input.update(placeholders)

    return seedream_input


# -------------------------------------------------------------
# 3) 스크린도어 A형 벽체 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_screendoor_a_type_wall_save_dir() -> Path:
    """
    SUBWAY_SCREENDOOR_A_TYPE_WALL_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/subway_screendoor_a_type_wall 사용

    run_screendoor_a_type_wall_to_editor(...) 에서는 이 경로 대신
    editor/<run_id>/before_image 를 save_dir 로 직접 넘긴다.
    """
    env_dir = os.getenv("SUBWAY_SCREENDOOR_A_TYPE_WALL_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "subway_screendoor_a_type_wall"


# -------------------------------------------------------------
# 4) create_screendoor_a_type_wall: Seedream JSON → Replicate 호출 → 이미지 저장
#     + 플레이스홀더까지 같이 반환
# -------------------------------------------------------------
def create_screendoor_a_type_wall(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    write_screendoor_a_type_wall(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4)에 prompt + image_input과 함께 전달해
       실제 21:17 비율 스크린도어 A형 벽체 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.

    save_dir 가 주어지면 해당 디렉터리에 바로 저장하고,
    None 이면 SUBWAY_SCREENDOOR_A_TYPE_WALL_SAVE_DIR /
    subway_screendoor_a_type_wall 기본 경로를 사용한다.
    """

    # 입력 JSON에서 플레이스홀더 + 원본 한글 그대로 꺼냄
    festival_name_placeholder = str(seedream_input.get("festival_name_placeholder", ""))
    festival_period_placeholder = str(
        seedream_input.get("festival_period_placeholder", "")
    )
    festival_location_placeholder = str(
        seedream_input.get("festival_location_placeholder", "")
    )

    festival_base_name_placeholder = str(
        seedream_input.get("festival_base_name_placeholder", "")
    )
    festival_base_period_placeholder = str(
        seedream_input.get("festival_base_period_placeholder", "")
    )
    festival_base_location_placeholder = str(
        seedream_input.get("festival_base_location_placeholder", "")
    )

    # 1) 포스터 URL/경로 추출
    poster_url = _extract_poster_url_from_input(seedream_input)
    if not poster_url:
        raise ValueError(
            "seedream_input.image_input 에 참조 포스터 이미지 URL/경로가 없습니다."
        )

    # 2) 포스터 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", 2100))
    height = int(seedream_input.get("height", 1700))
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

    model_name = os.getenv(
        "SUBWAY_SCREENDOOR_A_TYPE_WALL_MODEL",
        "bytedance/seedream-4",
    )

    # Seedream / Replicate 일시 오류(PA 등)에 대비한 재시도 로직
    output = None
    last_err: Exception | None = None

    for attempt in range(3):  # 최대 3번까지 시도
        try:
            output = replicate.run(model_name, input=replicate_input)
            break  # 성공하면 루프 탈출
        except ModelError as e:
            msg = str(e)
            # Prediction interrupted; please retry (code: PA) 같은 일시 오류만 재시도
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            # 그 외 ModelError는 그대로 넘김
            raise RuntimeError(
                f"Seedream model error during screendoor_a_type_wall generation: {e}"
            )
        except Exception as e:
            # 네트워크 등 다른 예외는 바로 실패
            raise RuntimeError(
                f"Unexpected error during screendoor_a_type_wall generation: {e}"
            )

    # 3번 모두 실패한 경우
    if output is None:
        raise RuntimeError(
            f"Seedream model error during screendoor_a_type_wall generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_screendoor_a_type_wall_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix="screendoor_a_type_wall_"
    )

    # 플레이스홀더 + 원본 한글까지 같이 반환 + size/width/height 포함
    return {
        "size": size,
        "width": width,
        "height": height,
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "festival_name_placeholder": festival_name_placeholder,
        "festival_period_placeholder": festival_period_placeholder,
        "festival_location_placeholder": festival_location_placeholder,
        "festival_base_name_placeholder": festival_base_name_placeholder,
        "festival_base_period_placeholder": festival_base_period_placeholder,
        "festival_base_location_placeholder": festival_base_location_placeholder,
    }


# -------------------------------------------------------------
# 5) editor 저장용 헬퍼 (run_id 기준)
# -------------------------------------------------------------
def run_screendoor_a_type_wall_to_editor(
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
        festival_name_ko
        festival_period_ko
        festival_location_ko

    동작:
      1) write_screendoor_a_type_wall(...) 로 seedream_input 생성
      2) editor/<run_id>/before_data, before_image 디렉터리 생성
      3) create_screendoor_a_type_wall(..., save_dir=before_image_dir) 로
         실제 이미지를 생성하고, 곧바로
         app/data/editor/<run_id>/before_image 에 저장
      4) recommend_fonts_and_colors_for_bus(...) 로 폰트/색상 추천
      5) 결과 JSON 을 app/data/editor/<run_id>/before_data 아래에 저장

    반환:
        editor에 저장된 경로까지 포함한 결과 dict
    """

    # 1) Seedream 입력 생성
    seedream_input = write_screendoor_a_type_wall(
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

    # 3) 실제 이미지 생성 (바로 before_image 에 저장)
    create_result = create_screendoor_a_type_wall(
        seedream_input,
        save_dir=before_image_dir,
    )

    # 4) 폰트/색상 추천
    font_color_result = recommend_fonts_and_colors_for_bus(
        bus_type="subway_screendoor_a_type_wall",  # 타입 식별용
        image_path=create_result["image_path"],
        festival_name_placeholder=create_result["festival_name_placeholder"],
        festival_period_placeholder=create_result["festival_period_placeholder"],
        festival_location_placeholder=create_result["festival_location_placeholder"],
        festival_base_name_placeholder=create_result[
            "festival_base_name_placeholder"
        ],
        festival_base_period_placeholder=create_result[
            "festival_base_period_placeholder"
        ],
        festival_base_location_placeholder=create_result[
            "festival_base_location_placeholder"
        ],
    )

    original_image_path = create_result.get("image_path") or ""

    # 5) 결과 dict 구성
    result: Dict[str, Any] = {
        "run_id": int(run_id),
        "status": "success",
        "type": "screendoor_a_type_wall",
        "poster_image_url": poster_image_url,
        "festival_name_ko": festival_name_ko,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
        **create_result,
        **font_color_result,
        "generated_image_path": original_image_path,
    }

    if original_image_path:
        result["image_path"] = original_image_path
        result["editor_image_path"] = original_image_path
    else:
        result["status"] = "warning"
        result["image_copy_error"] = "generated image path is empty"

    # 6) before_data 밑에 JSON 저장
    image_filename = result.get("image_filename") or ""
    if image_filename:
        stem = Path(image_filename).stem
        json_name = f"{stem}.json"
    else:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        json_name = f"screendoor_a_type_wall_{ts}.json"

    json_path = before_data_dir / json_name
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    result["editor_json_path"] = str(json_path.resolve())

    return result


# -------------------------------------------------------------
# 6) 프로젝트 루트 헬퍼 (필요하면 사용)
# -------------------------------------------------------------
def _get_project_root() -> Path:
    """
    acc-ai 루트 디렉터리를 반환한다.
    """
    return PROJECT_ROOT


# -------------------------------------------------------------
# 7) CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    CLI 실행용 진입점.

    ✅ 콘솔에서:
        python make_screendoor_a_type_wall.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 스크린도어 A형 벽체 Seedream 입력 생성
    - Seedream 호출로 실제 이미지 생성
    - 폰트/색상 추천
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 4  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    # 예시 포스터 파일 경로 (원하는 걸로 교체해서 사용)
    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\busan.png"
    festival_name_ko = "제12회 해운대 빛축제"
    festival_period_ko = "2025.11.29 ~ 2026.01.18"
    festival_location_ko = "해운대해수욕장 구남로 일원"

    # 2) 혹시라도 비어 있으면 바로 알려주기
    missing: list[str] = []
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
    result = run_screendoor_a_type_wall_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    print("✅ screendoor_a_type_wall 생성 + 폰트/색상 추천 + editor 저장 완료")
    print("  run_id            :", result.get("run_id"))
    print("  type              :", result.get("type"))
    print("  editor_json_path  :", result.get("editor_json_path"))
    print(
        "  editor_image_path :",
        result.get("editor_image_path", result.get("image_path")),
    )
    print("  generated_image_path :", result.get("generated_image_path"))
    print("  font_name         :", result.get("festival_font_name_placeholder"))
    print("  font_period       :", result.get("festival_font_period_placeholder"))
    print("  font_location     :", result.get("festival_font_location_placeholder"))
    print("  color_name        :", result.get("festival_color_name_placeholder"))
    print("  color_period      :", result.get("festival_color_period_placeholder"))
    print("  color_location    :", result.get("festival_color_location_placeholder"))


if __name__ == "__main__":
    main()
