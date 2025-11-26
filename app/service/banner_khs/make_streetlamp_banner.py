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
    name_text = _norm(name_text)
    period_text = _norm(period_text)
    location_text = _norm(location_text)

    prompt = (
        f"Tall 1:3 vertical illustration of {base_scene_en}, "
        "using the attached poster image only as reference for bright colors, lighting and atmosphere "
        f"but creating a completely new scene with {details_phrase_en}. "
        "Design this image as a clean standalone 1:3 vertical festival banner artwork, "
        "not shown hanging on any streetlamp, pole, wire, wall, or building, and with no surrounding street or environment. "
        "Leave small safe margins at the very top and bottom so that no important text is cut off when the banner is printed or trimmed. "

        # 👉 텍스트 위치/간격: 상단 중앙 + 서로 가깝게
        "Place exactly three horizontal lines of text in the upper central area of the banner, "
        "all perfectly center-aligned just above the vertical middle of the canvas, not near the very top edge. "
        "Keep these three lines visually close to one another as a single compact text block, "
        "with only small and even vertical gaps between the top, middle, and bottom lines, "
        "so that the period, title, and location feel tightly grouped as one unit. "

        f"On the middle line, write \"{name_text}\" in extremely large, ultra-bold sans-serif letters, "
        "the largest text in the entire image and clearly readable from a very long distance. "
        "Make this title block so large that it visually dominates the compact text group, "
        "and it must never look like a small caption or subtitle. "
        f"On the top line, above the title, write \"{period_text}\" in smaller bold sans-serif letters, "
        "but still keep these letters big, bright, and clearly readable from far away, not tiny caption text. "
        f"On the bottom line, below the title, write \"{location_text}\" in a size slightly smaller than the top line, "
        "but still as bold headline text, never thin or subtle. "

        "All three lines must be drawn in the foremost visual layer, clearly on top of every background element, "
        "character, object, and effect in the scene, and nothing may overlap, cover, or cut through any part of the letters. "
        "Draw exactly these three lines of text once each. Do not draw any second copy, shadow copy, reflection, "
        "mirrored copy, outline-only copy, blurred copy, or partial copy of any of this text anywhere else in the image, "
        "including on the ground, sky, buildings, decorations, or interface elements. "
        "Do not add any other text at all: no extra words, labels, dates, numbers, logos, watermarks, or UI elements "
        "beyond these three lines. "
        "Do not place the text on any separate banner, signboard, panel, box, frame, ribbon, or physical board; "
        "draw only clean floating letters directly over the background. "
        "The quotation marks in this prompt are for instruction only; do not draw quotation marks in the final image."
    )

    # f"{base_scene_en}의 높이 1:3 세로 삽화,"
    # "첨부된 포스터 이미지를 밝은 색상, 조명 및 분위기에만 참고할 수 있습니다."
    # f"하지만 {details_phrase_en}으로 완전히 새로운 장면을 만들고 있습니다."
    # "이 이미지를 깨끗한 독립형 1:3 수직 축제 배너 아트워크로 디자인하세요,"
    # 가로등, 기둥, 철조망, 벽, 건물에 걸려 있는 것이 표시되지 않으며, 주변 도로나 환경이 없습니다
    # 배너가 인쇄되거나 다듬어질 때 중요한 텍스트가 잘리지 않도록 상단과 하단에 작은 안전 여백을 남겨두세요

    # # 👉 텍스트 위치/간격: 상단 중앙 + 서로 가깝게
    # 배너의 상단 중앙 영역에 정확히 세 줄의 가로줄 텍스트를 배치합니다
    # "모든 것이 캔버스의 수직 중앙 바로 위, 맨 위 가장자리 근처가 아닌 완벽하게 중앙에 정렬되어 있습니다."
    # "이 세 줄을 하나의 컴팩트한 텍스트 블록으로 시각적으로 서로 가깝게 유지하세요,"
    # "위, 중간, 아래쪽 선 사이에 작고 고른 수직 간격만 있습니다,"
    # "기간, 제목, 위치가 하나의 단위로 긴밀하게 묶여 있는 느낌을 줍니다."

    # f"가운데 줄에 \\"{name_text}\"를 매우 크고 굵은 산세리프 문자로 씁니다,"
    # "전체 이미지에서 가장 큰 텍스트이며 매우 먼 거리에서도 명확하게 읽을 수 있습니다."
    # "이 제목 블록을 시각적으로 컴팩트 텍스트 그룹을 지배할 정도로 크게 만드세요,"
    # "그리고 그것은 절대 작은 자막이나 자막처럼 보여서는 안 됩니다."
    # f"제목 위 상단 줄에 작은 굵은 산세리프 문자로 \\"{period_text}\\"라고 적습니다,"
    # "하지만 여전히 이 글자들은 작은 캡션 텍스트가 아닌 멀리서도 크고 밝고 선명하게 읽을 수 있도록 유지하세요."
    # f"아래쪽 줄에는 제목 아래에 위쪽 줄보다 약간 작은 크기로 \\"{location_text}\\"라고 적습니다."
    # "하지만 여전히 대담한 헤드라인 텍스트로, 결코 얇거나 미묘하지 않습니다."

    # "세 줄 모두 모든 배경 요소 위에 명확하게 가장 앞쪽 시각적 층에 그려야 합니다,"
    # "장면에서 등장인물, 객체, 효과는 글자의 어떤 부분도 겹치거나 덮거나 자를 수 없습니다."
    # "이 세 줄의 텍스트를 각각 한 번씩 정확하게 그리세요. 두 번째 복사본, 그림자 복사본, 반사를 그리지 마세요,"
    # "이미지의 다른 부분에 있는 이 텍스트의 mirrored 사본, 개요 전용 사본, 흐릿한 사본 또는 부분 사본"
    # 지상, 하늘, 건물, 장식 또는 인터페이스 요소를 포함하여
    # "다른 텍스트는 전혀 추가하지 마세요: 단어, 라벨, 날짜, 숫자, 로고, 워터마크 또는 UI 요소는 추가하지 마세요."
    # "이 세 줄을 beyond."
    # "텍스트를 별도의 배너, 간판, 패널, 상자, 프레임, 리본 또는 물리적 보드에 배치하지 마십시오;"
    # 배경 바로 위에 깨끗한 떠다니는 글자만 그립니다
    # "이 프롬프트의 따옴표는 지시용이므로 최종 이미지에 따옴표를 그리지 마세요."

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
    run_id = 9  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    # 로컬 포스터 파일 경로 (PROJECT_ROOT/app/data/banner/...)
    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\goheung.png"
    festival_name_ko = "제 15회 고흥 우주항공 축제"
    festival_period_ko = "2025.05.03 ~ 2025.05.06"
    festival_location_ko = "고흥군 봉래면 나로우주센터 일원"

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
