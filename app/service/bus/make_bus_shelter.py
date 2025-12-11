# -*- coding: utf-8 -*-
"""
app/service/bus/make_bus_shelter.py

버스 쉘터(1024x1906) 세로 광고판용 Seedream 입력/프롬프트 생성 + 생성 이미지 저장 + editor 저장 모듈.

역할
- 참고용 포스터 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 포스터 이미지를 시각적으로 분석해서 "축제 씬 묘사"를 영어로 만든 뒤
  3) LLM으로 한국어 서브 타이틀(festival_subtitle_ko)을 생성한다.
  4) 축제명/서브타이틀을 이용해 버스 쉘터 세로 광고 프롬프트를 조립한다. (write_bus_shelter)
  5) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 생성하고 저장한다. (create_bus_shelter)
  6) run_bus_shelter_to_editor(...) 로 run_id 기준 editor 폴더에 JSON/이미지 사본을 저장한다.
  7) python make_bus_shelter.py 로 단독 실행할 수 있다.

결과 JSON 형태 (editor용 최소 정보):

{
  "type": "bus_shelter",
  "pro_name": "버스 쉘터",
  "festival_name_ko": "담양산타축제",
  "festival_subtitle_ko": "한 20자 이상으로\\n줄개행 하나 있게",
  "width": 1024,
  "height": 1906
}

※ festival_subtitle_ko 는 축제명/기간/장소를 참고해 LLM이 만든 한국어 카피이며,
   두 줄의 문장으로, 문자열 안에는 정확히 한 번의 줄바꿈 문자('\\n')가 포함된다.

전제 환경변수
- OPENAI_API_KEY             : OpenAI API 키
- BANNER_LLM_MODEL           : (선택) 배너/버스용 LLM, 기본값 "gpt-4o-mini"
- BUS_SHELTER_MODEL          : (선택) 기본값 "bytedance/seedream-4"
- BUS_SHELTER_SAVE_DIR       : (선택) 직접 create_bus_shelter 를 쓸 때 저장 경로
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

# 버스 쉘터 고정 스펙
BUS_SHELTER_TYPE = "bus_shelter"
BUS_SHELTER_PRO_NAME = "버스 쉘터"
BUS_SHELTER_WIDTH = 1024
BUS_SHELTER_HEIGHT = 1906

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
# 1) 한국어 서브 타이틀 생성 (festival_subtitle_ko)
# -------------------------------------------------------------
def _build_bus_shelter_subtitle_ko(
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> str:
    """
    축제명/기간/장소를 기반으로 버스 쉘터 광고용 한국어 서브 타이틀 문구를 생성한다.

    요구 조건(의도):
    - 한국어 문장 2줄
    - 문자열 안에 정확히 한 번의 줄바꿈 문자('\\n') 포함
    - 전체 글자 수는 대략 20자 이상 (엄격 검증은 하지 않음)
    - 이모지, 해시태그, 따옴표, 과도한 특수문자 사용 금지
    - 축제 성격/분위기를 설명하는 짧은 홍보 카피

    LLM 호출이 실패하면 빈 문자열("")을 반환한다.
    """

    client = get_openai_client()
    model_name = os.getenv("BANNER_LLM_MODEL", "gpt-4o-mini")

    system_msg = (
        "너는 한국 축제 포스터와 옥외 광고를 위한 카피라이터다. "
        "입력으로 주어지는 축제명, 기간, 장소 정보를 참고해서 "
        "관람객에게 매력적으로 들리는 짧은 한국어 홍보 문구를 만든다. "
        "결과는 두 줄의 문장으로, 문자열 안에 줄바꿈 문자('\\n')가 정확히 한 번만 들어가도록 구성해라. "
        "각 줄은 자연스러운 문장이어야 하며, 이모지, 해시태그, 따옴표, 특수문자는 사용하지 마라."
    )

    user_payload = {
        "festival_name_ko": festival_name_ko or "",
        "festival_period_ko": festival_period_ko or "",
        "festival_location_ko": festival_location_ko or "",
    }

    try:
        resp = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_msg},
                {
                    "role": "user",
                    "content": (
                        "다음 축제 정보를 참고해서 버스 쉘터 광고에 들어갈 한국어 서브 타이틀을 만들어줘.\n"
                        "- 형식: 두 줄짜리 한국어 문장, 문자열 안에는 줄바꿈 문자('\\n')가 정확히 한 번 포함되어야 한다.\n"
                        "- 길이: 전체 글자 수는 대략 20자 이상이 되도록.\n"
                        "- 말투: 명료하고 긍정적인 홍보 카피.\n"
                        "- 따옴표(\"\',「」 등), 이모지, 해시태그, 특수문자는 사용하지 마.\n\n"
                        'JSON 객체 하나만 반환해. 키는 "festival_subtitle_ko" 하나만 사용해.\n\n'
                        + json.dumps(user_payload, ensure_ascii=False)
                    ),
                },
            ],
            temperature=0.8,
        )

        data = json.loads(resp.choices[0].message.content or "{}")
        subtitle = str(data.get("festival_subtitle_ko", "")).strip()
    except Exception as e:
        print(f"[make_bus_shelter._build_bus_shelter_subtitle_ko] failed: {e}")
        return ""

    # 줄바꿈/공백 정리
    subtitle = subtitle.replace("\r", "")
    # 첫 줄바꿈만 유지
    if "\n" in subtitle:
        first, rest = subtitle.split("\n", 1)
        subtitle = first.strip() + "\n" + rest.strip()
    else:
        # 줄바꿈이 없다면 가운데 근처에서 인위적으로 하나 넣어 준다.
        text = subtitle.strip()
        if not text:
            return ""
        mid = len(text) // 2
        split_idx = mid
        # 공백 기준으로 나누면 더 자연스럽게 보일 수 있음
        for offset in range(len(text)):
            i1 = mid - offset
            i2 = mid + offset
            if i1 >= 0 and text[i1] == " ":
                split_idx = i1
                break
            if i2 < len(text) and text[i2] == " ":
                split_idx = i2
                break
        left = text[:split_idx].strip()
        right = text[split_idx:].strip()
        subtitle = left + "\n" + right

        subtitle = subtitle.strip("\n")

    return subtitle


# -------------------------------------------------------------
# 2) 버스 쉘터 프롬프트 조립 (세로 포스터 + 제목/서브타이틀)
# -------------------------------------------------------------
def _build_bus_shelter_prompt_en(
    subtitle_text: str,
    festival_name_text: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    버스쉘터(세로 포스터)용 Seedream 영어 프롬프트 생성 (텍스트 제거 + 순수 포스터 이미지 버전).

    규칙:
    1) 첨부 이미지의 글자/로고/숫자는 전혀 참고하지 않는다.
    2) 중앙에 메인 일러스트가 크게 배치된다.
    3) 최종 결과물에는 텍스트가 절대 들어가지 않는다.
    4) 주변 환경 없이 '순수 광고 이미지'만 생성한다. (목업 X)
    """

    def _norm(s: str) -> str:
        return " ".join(str(s or "").split())

    base_scene_en = _norm(base_scene_en)
    details_phrase_en = _norm(details_phrase_en)
    # subtitle_text, festival_name_text 는 분위기/컨셉 참고용 인자일 뿐,
    # 실제 프롬프트에서는 텍스트를 그리도록 사용하지 않는다.

    prompt = (
        # 4) 순수 포스터 이미지 자체만 (짧은 버전)
        "Create only the pure festival poster illustration as a flat image. "
        "Do not generate any surrounding environment or mockup such as walls, bus shelters, billboards, streets, or frames. "
        "The illustration itself must fill the entire canvas. "

        # 1) 첨부 이미지의 글자는 무시, 색감/무드만 참고
        f"The visual theme is based on {base_scene_en}. "
        "Use the attached poster image only as a loose reference for overall color palette, atmosphere, and lighting. "
        "Completely ignore and do not copy any text, logos, numbers, or typography from the attached image. "

        # 2) 중앙 메인 일러스트
        "Around the center of the canvas, place one large main illustration: "
        f"iconic visual elements inspired by {details_phrase_en}, such as mascots, symbolic objects, or key festival scenery. "
        "This main illustration should be the clear focal point with a balanced composition and comfortable breathing space. "

        # 캔버스 끝까지 꽉 채우기 (프레임/여백 금지)
        "The background and illustration must extend fully to every edge of the canvas with no white borders, "
        "no margins, no paper edges, and no frames. "

        # 3) 텍스트 절대 금지
        "Absolutely no text: do not draw any letters, words, numbers, logos, UI icons, or symbols that look like writing "
        "in any language. If an object would normally have writing on it, keep that area blank or fill it with simple shapes instead."
    )

    return prompt.strip()




# -------------------------------------------------------------
# 3) write_bus_shelter: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_bus_shelter(
    poster_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    버스 쉘터(1024x1906) 세로 광고판용 Seedream 입력 JSON을 생성한다.
    """

    # 1) 한국어 서브타이틀 생성
    festival_subtitle_ko = _build_bus_shelter_subtitle_ko(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # 2) 한글 축제 정보 → 영어 번역 (씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]

    # 3) 자리수 맞춘 플레이스홀더 (제목/서브타이틀)
    placeholders: Dict[str, str] = {
        "festival_name_placeholder": _build_placeholder_from_hangul(
            festival_name_ko, "A"
        ),
        "festival_subtitle_placeholder": _build_placeholder_from_hangul(
            festival_subtitle_ko, "B"
        ),
        # 원문 백업
        "festival_base_name_ko_placeholder": str(festival_name_ko or ""),
        "festival_base_subtitle_ko_placeholder": str(festival_subtitle_ko or ""),
    }

    # 4) 포스터 이미지 분석 → 씬 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=poster_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )

    # 5) 최종 프롬프트 조립
    prompt = _build_bus_shelter_prompt_en(
        subtitle_text=placeholders["festival_subtitle_placeholder"],
        festival_name_text=placeholders["festival_name_placeholder"],
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 6) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": BUS_SHELTER_WIDTH,
        "height": BUS_SHELTER_HEIGHT,
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
        "festival_subtitle_ko": festival_subtitle_ko,
    }

    seedream_input.update(placeholders)
    return seedream_input


# -------------------------------------------------------------
# 4) 버스 쉘터 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_bus_shelter_save_dir() -> Path:
    """
    BUS_SHELTER_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/bus_shelter 사용
    """
    env_dir = os.getenv("BUS_SHELTER_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "bus_shelter"


# -------------------------------------------------------------
# 5) create_bus_shelter: Seedream JSON → Replicate 호출 → 이미지 저장
# -------------------------------------------------------------
def create_bus_shelter(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "bus_shelter_",
) -> Dict[str, Any]:
    """
    write_bus_shelter(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 에서 포스터 URL/경로를 추출하고,
    2) 그 이미지를 다운로드(또는 로컬 파일 읽기)해 파일 객체로 만든 뒤,
    3) Replicate(bytedance/seedream-4 또는 BUS_SHELTER_MODEL)에
       prompt + image_input과 함께 전달해
       실제 1024x1906 버스 쉘터용 광고 이미지를 생성하고,
    4) 생성된 이미지를 로컬에 저장한다.

    save_dir 가 주어지면 해당 디렉터리에 바로 저장하고,
    None 이면 BUS_SHELTER_SAVE_DIR / app/data/bus_shelter 기본 경로를 사용한다.
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
    width = int(seedream_input.get("width", BUS_SHELTER_WIDTH))
    height = int(seedream_input.get("height", BUS_SHELTER_HEIGHT))
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

    model_name = os.getenv("BUS_SHELTER_MODEL", "bytedance/seedream-4")

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
                f"Seedream model error during bus shelter banner generation: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Unexpected error during bus shelter banner generation: {e}"
            )

    if output is None:
        raise RuntimeError(
            f"Seedream model error during bus shelter banner generation after retries: {last_err}"
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_bus_shelter_save_dir()
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
        "festival_subtitle_ko": str(seedream_input.get("festival_subtitle_ko", "")),
    }


# -------------------------------------------------------------
# 6) editor 저장용 헬퍼 (run_id 기준)
# -------------------------------------------------------------
def run_bus_shelter_to_editor(
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
      1) write_bus_shelter(...) 로 Seedream 입력용 seedream_input 생성
      2) create_bus_shelter(..., save_dir=before_image_dir) 로
         실제 버스 쉘터용 광고 이미지를 생성하고,
         app/data/editor/<run_id>/before_image/bus_shelter.png 로 저장한다.
      3) 타입, 한글 축제명, LLM이 생성한 한국어 서브타이틀, 배너 크기만을 포함한
         최소 결과 JSON을 구성하여
         app/data/editor/<run_id>/before_data/bus_shelter.json 에 저장한다.

    반환(예시):
      {
        "type": "bus_shelter",
        "pro_name": "버스 쉘터",
        "festival_name_ko": "담양산타축제",
        "festival_subtitle_ko": "한 20자 이상으로\\n줄개행 하나 있게",
        "width": 1024,
        "height": 1906
      }
    """

    # 1) Seedream 입력 생성
    seedream_input = write_bus_shelter(
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
    create_result = create_bus_shelter(
        seedream_input,
        save_dir=before_image_dir,
        prefix="bus_shelter_",
    )

    # 4) 최종 결과 JSON (API/백엔드에서 사용할 최소 정보 형태)
    result: Dict[str, Any] = {
        "type": BUS_SHELTER_TYPE,
        "pro_name": BUS_SHELTER_PRO_NAME,
        "festival_name_ko": create_result["festival_name_ko"],
        "festival_subtitle_ko": create_result["festival_subtitle_ko"],
        "width": int(create_result.get("width", BUS_SHELTER_WIDTH)),
        "height": int(create_result.get("height", BUS_SHELTER_HEIGHT)),
    }

    # 5) before_data 밑에 JSON 저장 (파일명 고정)
    json_path = before_data_dir / "bus_shelter.json"
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
        python app/service/bus/make_bus_shelter.py

    를 실행하면, 아래에 적어둔 입력값으로
    - 버스 쉘터 세로 광고 이미지 생성 (Seedream)
    - app/data/editor/<run_id>/before_data, before_image 저장
    까지 한 번에 수행한다.
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    run_id = 10  # 에디터 실행 번호 (폴더 이름에도 사용됨)

    poster_image_url = r"C:\final_project\ACC\acc-ai\app\data\banner\arco.png"
    festival_name_ko = "예술 인형 축제"
    festival_period_ko = "2025.11.04 ~ 2025.11.09"
    festival_location_ko = "아르코꿈밭극장, 텃밭스튜디오"

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
    result = run_bus_shelter_to_editor(
        run_id=run_id,
        poster_image_url=poster_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    editor_root = DATA_ROOT / "editor" / str(run_id)
    json_path = editor_root / "before_data" / "bus_shelter.json"
    image_path = editor_root / "before_image" / "bus_shelter.png"

    print("✅ bus shelter banner 생성 + editor 저장 완료")
    print("  type                 :", result.get("type"))
    print("  pro_name             :", result.get("pro_name"))
    print("  festival_name_ko     :", result.get("festival_name_ko"))
    print("  festival_subtitle_ko :", result.get("festival_subtitle_ko"))
    print("  width x height       :", result.get("width"), "x", result.get("height"))
    print("  json_path            :", json_path)
    print("  image_path           :", image_path)


if __name__ == "__main__":
    main()
