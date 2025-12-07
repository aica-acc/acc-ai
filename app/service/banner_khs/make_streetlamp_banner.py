# -*- coding: utf-8 -*-
"""
app/service/banner_khs/make_streetlamp_banner.py

가로등(1:3) 세로 현수막용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 한글 자리수에 맞춘 플레이스홀더 텍스트(라틴 알파벳 시퀀스)를 사용해서
     1:3 세로 가로등 현수막 프롬프트를 조립한다. (write_streetlamp_banner)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_streetlamp_banner)
  5) run_streetlamp_banner_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  6) python make_streetlamp_banner.py 로 단독 실행할 수 있다.

전제 환경변수
- OPENAI_API_KEY               : OpenAI API 키
- BANNER_LLM_MODEL             : (선택) 기본값 "gpt-4o-mini"
- STREETLAMP_BANNER_MODEL      : (선택) 기본값 "bytedance/seedream-4"
- STREETLAMP_BANNER_SAVE_DIR   : (선택, 직접 create_streetlamp_banner 를 쓸 때용)
    * 절대경로면 그대로 사용
    * 상대경로면 acc-ai 프로젝트 루트 기준
    * 미설정 시 PROJECT_ROOT/app/data/streetlamp_banner 사용
"""

from __future__ import annotations

import json
import os
import sys
import time
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

# 배너 고정 스펙
BANNER_TYPE = "streetlamp_banner"
BANNER_PRO_NAME = "가로등 현수막"
BANNER_WIDTH = 1024
BANNER_HEIGHT = 3072

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


# -------------------------------------------------------------
# 1) 영어 씬 묘사 + 플레이스홀더 텍스트 → 세로 가로등 현수막 프롬프트
# -------------------------------------------------------------
def _build_streetlamp_banner_prompt_en(
    name_text: str,
    period_text: str,
    location_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)
    # 텍스트는 전혀 쓰지 않을 거라 실제 프롬프트에서는 사용하지 않음
    _ = (_norm(name_text), _norm(period_text), _norm(location_text))

    prompt = (
        # 기본 장면 설명 (포스터/배너라는 말은 아예 안 씀)
        f"Tall 1:3 vertical illustration showing {base_scene_en}, "
        "in a warm, colorful, storybook style, as if it were a frame from an animated film. "
        "Use the attached image only as very loose inspiration for overall color palette and lighting, "
        f"but create a completely new composition with {details_phrase_en}. "

        # 1) 순수 이미지 자체만, 어떤 ‘디자인’ 구조도 아닌 자연스러운 씬
        "This must look like a natural scene illustration, not like a designed poster, flyer, or banner. "
        "Do not create large empty rectangles or panels that look like they are reserved for titles or captions. "
        "Fill the whole canvas edge-to-edge with characters, props, scenery, and background details. "

        # 2) 참고 이미지의 텍스트/로고/타이틀 블록은 완전히 무시
        "Completely ignore and discard all text, numbers, logos, and title areas in the attached image. "
        "Do not copy, trace, or mimic any blocks of solid color where the original poster had writing. "
        "Where there used to be writing, instead paint puppets, people, decorations, lights, or background scenery. "

        # 3) 최종 결과에는 어떤 글자/숫자/로고도 절대 금지
        "ABSOLUTELY NO TEXT in the final image: no words, no letters, no numbers, no symbols, no logos, "
        "no banners with writing, and no signboards. "
        "This includes Korean characters, English letters, and any glyphs that could be read as writing. "
        "Every shape in the image must clearly read as illustration, not typography. "

        # 4) 네거티브 키워드(모델이 볼 수 있게 문장 형태로 추가)
        "Avoid: text, title, typography, labels, captions, dates, numbers, logos, signboards, subtitles, "
        "watermarks, UI, poster layout."
    )

    return prompt.strip()




# -------------------------------------------------------------
# 2) write_streetlamp_banner: Seedream 입력 JSON 생성 (+ 플레이스홀더 포함)
# -------------------------------------------------------------
def write_streetlamp_banner(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    가로등(1:3, 1024x3072) 세로 현수막용 Seedream 입력 JSON을 생성한다.
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
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        "festival_period_placeholder": _build_placeholder_from_hangul(
            festival_period_ko, "C"
        ),
        "festival_location_placeholder": _build_placeholder_from_hangul(
            festival_location_ko, "B"
        ),
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

    # 4) 최종 프롬프트 조립 (세로용)
    prompt = _build_streetlamp_banner_prompt_en(
        name_text=placeholders["festival_name_placeholder"],
        period_text=placeholders["festival_period_placeholder"] or period_en,
        location_text=placeholders["festival_location_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": BANNER_WIDTH,
        "height": BANNER_HEIGHT,
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

    seedream_input.update(placeholders)
    return seedream_input


# -------------------------------------------------------------
# 3) streetlamp 저장 디렉터리 결정 (직접 create_streetlamp_banner 쓸 때용)
# -------------------------------------------------------------
def _get_streetlamp_banner_save_dir() -> Path:
    """
    STREETLAMP_BANNER_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/streetlamp_banner 사용

    run_streetlamp_banner_to_editor(...) 에서는 이 경로를 사용하지 않고,
    곧바로 editor/<run_id>/before_image 에 저장한다.
    """
    env_dir = os.getenv("STREETLAMP_BANNER_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "streetlamp_banner"


# -------------------------------------------------------------
# 4) create_streetlamp_banner: Seedream JSON → Replicate 호출 → 이미지 저장
#     + 플레이스홀더까지 같이 반환
# -------------------------------------------------------------
def create_streetlamp_banner(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
) -> Dict[str, Any]:
    """
    write_streetlamp_banner(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4)에 prompt + image_input과 함께 전달해
       실제 1:3 세로 가로등 현수막 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.

    save_dir 가 주어지면 해당 디렉터리에 바로 저장하고,
    None 이면 STREETLAMP_BANNER_SAVE_DIR / streetlamp_banner 기본 경로를 사용한다.
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
        raise ValueError("seedream_input.image_input 에 참조 포스터 이미지 URL/경로가 없습니다.")

    # 2) 포스터 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(poster_url)
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", BANNER_WIDTH))
    height = int(seedream_input.get("height", BANNER_HEIGHT))
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

    model_name = os.getenv("STREETLAMP_BANNER_MODEL", "bytedance/seedream-4")

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
                f"Seedream model error during streetlamp banner generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during streetlamp banner generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during streetlamp banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_streetlamp_banner_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix="streetlamp_banner_"
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
def run_streetlamp_banner_to_editor(
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
      1) write_streetlamp_banner(...) 로 Seedream 입력용 seedream_input 생성
      2) create_streetlamp_banner(..., save_dir=before_image_dir) 로
         실제 세로 가로등 배너 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/streetlamp_banner.png 로 저장한다.
      3) 배너 타입, 한글 축제 정보, 배너 크기만을 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/streetlamp_banner.json 에 저장한다.

    반환:
      {
        "type": "streetlamp_banner",
        "pro_name": "가로등 현수막",
        "festival_name_ko": ...,
        "festival_period_ko": ...,
        "festival_location_ko": ...,
        "width": 1024,
        "height": 3072
      }
    """

    # 1) Seedream 입력 생성
    seedream_input = write_streetlamp_banner(
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

    # 3) 실제 배너 이미지 생성 (바로 before_image 에 저장)
    create_result = create_streetlamp_banner(
        seedream_input,
        save_dir=before_image_dir,
    )

    # 4) 최종 결과 JSON (API/백엔드에서 사용할 최소 정보 형태)
    result: Dict[str, Any] = {
        "type": BANNER_TYPE,
        "pro_name": BANNER_PRO_NAME,
        "festival_name_ko": festival_name_ko,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
        "width": int(create_result.get("width", BANNER_WIDTH)),
        "height": int(create_result.get("height", BANNER_HEIGHT)),
    }

    # 5) before_data 밑에 JSON 저장 (파일명 고정)
    json_path = before_data_dir / "streetlamp_banner.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


# -------------------------------------------------------------
# 6) CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    CLI 실행용 진입점.

    ✅ 콘솔에서:
        python make_streetlamp_banner.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 세로 가로등 배너 Seedream 입력 생성
    - Seedream 호출로 실제 이미지 생성
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 10  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    # 로컬 포스터 파일 경로 (PROJECT_ROOT/app/data/banner/...)
    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\arco.png"
    festival_name_ko = "예술 인형 축제"
    festival_period_ko = "2025.11.04 ~ 2025.11.09"
    festival_location_ko = "아르코꿈밭극장, 텃밭스튜디오"

    # 2) 혹시라도 비어 있으면 바로 알려주기
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
    result = run_streetlamp_banner_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "streetlamp_banner.json"
    image_path = editor_root / "before_image" / "streetlamp_banner.png"

    print("✅ streetlamp banner 생성 + editor 저장 완료")
    print("  run_id            :", run_id)
    print("  type              :", result.get("type"))
    print("  pro_name          :", result.get("pro_name"))
    print("  festival_name_ko  :", result.get("festival_name_ko"))
    print("  festival_period_ko:", result.get("festival_period_ko"))
    print("  festival_location_ko:", result.get("festival_location_ko"))
    print("  width x height    :", result.get("width"), "x", result.get("height"))
    print("  json_path         :", json_path)
    print("  image_path        :", image_path)


if __name__ == "__main__":
    main()
