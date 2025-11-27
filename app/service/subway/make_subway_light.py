# -*- coding: utf-8 -*-
"""
app/service/subway/make_subway_light.py

지하철 조명광고(1500x1620) 세로 포스터용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) 축제명을 이용해 지하철 조명광고 프롬프트를 조립한다. (write_subway_light)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_subway_light)
  5) run_subway_light_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  6) python make_subway_light.py 로 단독 실행할 수 있다.

결과 JSON 형태 (editor용 최소 정보):

{
  "type": "subway_light",
  "pro_name": "지하철 조명광고",
  "festival_name_ko": "제7회 담양산타축제",
  "width": 1500,
  "height": 1620
}

전제 환경변수
- OPENAI_API_KEY             : OpenAI API 키
- BANNER_LLM_MODEL           : (선택) 배너/버스용 LLM, 기본값 "gpt-4o-mini"
- SUBWAY_LIGHT_MODEL         : (선택) 기본값 "bytedance/seedream-4"
- SUBWAY_LIGHT_SAVE_DIR      : (선택) 직접 create_subway_light 를 쓸 때 저장 경로
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
# 프로젝트 루트 및 .env 로딩 + sys.path 설정
# -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = PROJECT_ROOT / "app" / "data"

# 지하철 조명광고 고정 스펙
SUBWAY_LIGHT_TYPE = "subway_light"
SUBWAY_LIGHT_PRO_NAME = "지하철 조명광고"
SUBWAY_LIGHT_WIDTH_PX = 1500
SUBWAY_LIGHT_HEIGHT_PX = 1620

# .env 로딩
env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# -------------------------------------------------------------
# road_banner 모듈의 공용 유틸 재사용
# -------------------------------------------------------------
from app.service.banner_khs.make_road_banner import (  # type: ignore
    get_openai_client,
    _build_placeholder_from_hangul,
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _extract_poster_url_from_input,
    _save_image_from_file_output,
    _download_image_bytes,
)

# -------------------------------------------------------------
# 1) 지하철 조명광고 프롬프트 조립 (중앙 일러스트 + 중앙 정렬 제목)
# -------------------------------------------------------------
def _build_subway_light_prompt_en(
    title_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    지하철 조명광고용 Seedream 영어 프롬프트.

    - 실제 역/프레임/액자를 그리는 것이 아니라
      'LED 느낌의 한 장짜리 포스터 일러스트'만 생성하게 만든다.
    - 핵심 일러스트와 축제명이 모두 중앙 정렬.
    """

    def _n(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _n(base_scene_en)
    details_phrase_en = _n(details_phrase_en)
    title_text = _n(title_text)

    prompt = (
        # 전체 장면: **절대 지하철 역/프레임 언급 금지**
        f"Square-ish festival poster illustration themed around {base_scene_en}, "
        "using the attached poster image only as reference for overall color palette, lighting, and mood, "
        "but creating a completely new composition as a clean printable artwork. "
        "Fill the ENTIRE canvas edge to edge with the illustration, with NO outer borders and NO white margins. "
        "Do NOT draw any subway station, wall, tiles, ceiling, floor, people, or surrounding environment. "
        "Do NOT draw any metal frame, bezel, glass, panel structure, screws, or physical light-box enclosure. "
        "Just produce a single flat digital poster image. "

        # 중앙 일러스트 + LED 느낌
        "Use a dark, rich background with a subtle vignette, and create a soft inner glow so that the center area "
        "looks like it is gently illuminated from behind, similar to an LED-backlit poster. "
        f"In the central area, place the PRIMARY FESTIVAL ILLUSTRATION inspired by {details_phrase_en}, "
        "such as rockets, mascots, symbolic objects, or thematic scenery. "
        "This illustration should be vertically centered and feel like the main attraction. "

        # 텍스트 배치: 중앙 정렬
        "Place the festival title as a single main line of text, perfectly centered horizontally, "
        "and positioned at the visual center of the canvas or only a little above or below the center. "
        f"Write \"{title_text}\" in extremely large, bold, clean sans-serif letters, "
        "with a subtle glowing outline or halo so it looks like luminous LED text. "

        # 텍스트 규칙
        "The title text must be the only text in the image. "
        "Do NOT add any other text, numbers, dates, labels, logos, watermarks, or UI elements. "
        "Draw the quoted string exactly once. "
        "Do not create shadow copies, reflections, outlines without fill, duplicated faint versions, or any repeated text. "
        "No text may appear at the edges or corners; only this one centered line. "

        # 배너/박스 금지
        "Do not place the text inside any box, banner, signboard, ribbon, frame, or physical container; "
        "render only clean glowing letters directly over the illuminated background. "

        "Do not draw quotation marks."
    )

    return prompt.strip()



# -------------------------------------------------------------
# 2) write_subway_light: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_subway_light(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    지하철 조명광고(1500x1620)용 Seedream 입력 JSON을 생성한다.
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

    # 2) 자리수 맞춘 플레이스홀더 (축제명)
    placeholders: Dict[str, str] = {
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        # 원문 백업
        "festival_base_name_ko_placeholder": str(festival_name_ko or ""),
        "festival_base_period_ko_placeholder": str(festival_period_ko or ""),
        "festival_base_location_ko_placeholder": str(festival_location_ko or ""),
    }

    # 3) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 4) 최종 프롬프트 조립
    prompt = _build_subway_light_prompt_en(
        title_text=placeholders["festival_name_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": SUBWAY_LIGHT_WIDTH_PX,
        "height": SUBWAY_LIGHT_HEIGHT_PX,
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
        "festival_name_ko": festival_name_ko,
    }

    seedream_input.update(placeholders)
    return seedream_input


# -------------------------------------------------------------
# 3) 지하철 조명광고 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_subway_light_save_dir() -> Path:
    """
    SUBWAY_LIGHT_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/subway_light 사용
    """
    env_dir = os.getenv("SUBWAY_LIGHT_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "subway_light"


# -------------------------------------------------------------
# 4) create_subway_light: Seedream JSON → Replicate 호출 → 이미지 저장
# -------------------------------------------------------------
def create_subway_light(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "subway_light_",
) -> Dict[str, Any]:
    """
    write_subway_light(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4 또는 SUBWAY_LIGHT_MODEL)에
       prompt + image_input과 함께 전달해
       실제 1500x1620 지하철 조명광고용 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.
    """

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
    width = int(seedream_input.get("width", SUBWAY_LIGHT_WIDTH_PX))
    height = int(seedream_input.get("height", SUBWAY_LIGHT_HEIGHT_PX))
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

    model_name = os.getenv("SUBWAY_LIGHT_MODEL", "bytedance/seedream-4")

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
                f"Seedream model error during subway light poster generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during subway light poster generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during subway light poster generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_subway_light_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    image_path, image_filename = _save_image_from_file_output(
        file_output, save_base, prefix=prefix
    )

    return {
        "size": size,
        "width": width,
        "height": height,
        "image_path": image_path,
        "image_filename": image_filename,
        "prompt": prompt,
        "festival_name_ko": str(seedream_input.get("festival_name_ko", "")),
    }


# -------------------------------------------------------------
# 5) editor 저장용 헬퍼 (run_id 기준)
# -------------------------------------------------------------
def run_subway_light_to_editor(
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
      1) write_subway_light(...) 로 Seedream 입력용 seedream_input 생성
      2) create_subway_light(..., save_dir=before_image_dir) 로
         실제 지하철 조명광고 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/subway_light.png 로 저장한다.
      3) 타입, 한글 축제명, 픽셀 단위 가로/세로를 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/subway_light.json 에 저장한다.

    반환(예시):
      {
        "type": "subway_light",
        "pro_name": "지하철 조명광고",
        "festival_name_ko": "제7회 담양산타축제",
        "width": 1500,
        "height": 1620
      }
    """

    # 1) Seedream 입력 생성
    seedream_input = write_subway_light(
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
    create_result = create_subway_light(
        seedream_input,
        save_dir=before_image_dir,
        prefix="subway_light_",
    )

    # 4) 최종 결과 JSON (API/백엔드에서 사용할 최소 정보 형태)
    result: Dict[str, Any] = {
        "type": SUBWAY_LIGHT_TYPE,
        "pro_name": SUBWAY_LIGHT_PRO_NAME,
        "festival_name_ko": create_result["festival_name_ko"],
        "width": SUBWAY_LIGHT_WIDTH_PX,
        "height": SUBWAY_LIGHT_HEIGHT_PX,
    }

    # 5) before_data 밑에 JSON 저장 (파일명 고정)
    json_path = before_data_dir / "subway_light.json"
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
        python app/service/subway/make_subway_light.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 지하철 조명광고 이미지 생성 (Seedream)
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 9  # 에디터 실행 번호 (폴더 이름에도 사용됨)

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
    result = run_subway_light_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "subway_light.json"
    image_path = editor_root / "before_image" / "subway_light.png"

    print("✅ subway light poster 생성 + editor 저장 완료")
    print("  type             :", result.get("type"))
    print("  pro_name         :", result.get("pro_name"))
    print("  festival_name_ko :", result.get("festival_name_ko"))
    print("  width x height   :", result.get("width"), "x", result.get("height"))
    print("  json_path        :", json_path)
    print("  image_path       :", image_path)


if __name__ == "__main__":
    main()
