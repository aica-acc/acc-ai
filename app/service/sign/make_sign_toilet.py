# -*- coding: utf-8 -*-
"""
app/service/sign/make_sign_toilet.py

축제 화장실 안내 표지용(정사각형 2048x2048) Seedream 모듈.

역할
- 참고용 마스코트 이미지(URL 또는 로컬 파일 경로)와 축제 정보(한글)를 입력받아서
  1) OpenAI LLM으로 축제명/기간/장소를 영어로 번역하고
  2) 마스코트 이미지를 시각적으로 분석해서 축제 테마/무드 정보를 영어로 만든 뒤
  3) 축제명/테마를 이용해 정사각형 화장실 안내 표지 프롬프트를 조립한다. (write_sign_toilet)
  4) 해당 JSON을 받아 Replicate(Seedream)를 호출해 실제 이미지를 한 번 생성하고 저장한다. (create_sign_toilet)
  5) run_sign_toilet_to_editor(...) 로 p_no 기준
     FRONT_PROJECT_ROOT/public/data/promotion 경로에
     생성 이미지를 저장하고, DB 저장용 메타 정보를 반환한다.
  6) python make_sign_toilet.py 로 단독 실행할 수 있다.

DB 저장용 리턴 예시:

{
  "db_file_type": "sign_toilet",
  "type": "image",
  "db_file_path": "C:\\final_project\\ACC\\acc-front\\public\\data\\promotion\\M000001\\P000001\\sign\\sign_toilet.png",
  "type_ko": "화장실 표지판"
}

전제 환경변수
- OPENAI_API_KEY             : OpenAI API 키 (banner_khs.make_road_banner 내부에서 사용)
- BANNER_LLM_MODEL           : (선택) 배너/버스/표지판용 LLM, 기본값 "gpt-4o-mini"
- SIGN_TOILET_MODEL          : (선택) 기본값 "bytedance/seedream-4"
- SIGN_TOILET_SAVE_DIR       : (선택) create_sign_toilet 단독 사용 시 저장 경로
- ACC_MEMBER_NO              : (선택) 프로모션 파일 경로용 회원번호, 기본값 "M000001"
- FRONT_PROJECT_ROOT         : (선택) acc-front 또는 acc-frontend 루트 경로
                               예) C:\\final_project\\ACC\\acc-front
"""

from __future__ import annotations

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

# 화장실 안내 표지 고정 스펙 (정사각형 2048 x 2048)
SIGN_TOILET_TYPE = "sign_toilet"
SIGN_TOILET_PRO_NAME = "화장실 표지판"
SIGN_TOILET_WIDTH = 2048
SIGN_TOILET_HEIGHT = 2048

env_path = PROJECT_ROOT / ".env"
load_dotenv(env_path)

# ✅ FRONT_PROJECT_ROOT 환경변수 기반 프론트 루트 경로 계산
_front_env = os.getenv("FRONT_PROJECT_ROOT")
if _front_env:
    _front_path = Path(_front_env)
    if not _front_path.is_absolute():
        _front_path = PROJECT_ROOT / _front_path
    FRONT_PROJECT_ROOT = _front_path
else:
    # 환경변수 없으면 기존 acc-front 위치로 백업
    FRONT_PROJECT_ROOT = PROJECT_ROOT.parent / "acc-front"

# app 패키지 import를 위해 루트를 sys.path에 추가
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# -------------------------------------------------------------
# 콘솔 진행 상황 로그 유틸
# -------------------------------------------------------------
def _log_progress(message: str) -> None:
    """
    화장실 안내 표지 생성용 진행 로그를 콘솔에 출력한다.
    """
    print(f"[sign_toilet] {message}", flush=True)


# -------------------------------------------------------------
# 기존 road_banner 유틸 재사용
# -------------------------------------------------------------
from app.service.banner_khs.make_road_banner import (  # type: ignore
    _translate_festival_ko_to_en,
    _build_scene_phrase_from_poster,
    _save_image_from_file_output,
    _download_image_bytes,
)


# -------------------------------------------------------------
# 1) 한글 축제명에서 회차/축제명 분리 (필요시)
# -------------------------------------------------------------
def _split_festival_count_and_name(full_name_ko: str) -> Tuple[str, str]:
    """
    입력: "제7회 담양산타축제", "제 7회 담양산타축제", "담양산타축제" 등

    반환:
      (festival_count, festival_name_ko)
    """
    text = str(full_name_ko or "").strip()
    if not text:
        return "제 1회", ""

    m = re.match(r"^\s*(제\s*\d+\s*회)\s*(.*)$", text)
    if not m:
        return "제 1회", text

    raw_count = m.group(1)
    rest_name = m.group(2)

    normalized_count = re.sub(r"\s+", "", raw_count)

    name_ko = rest_name.strip() if rest_name.strip() else text
    return normalized_count, name_ko


# -------------------------------------------------------------
# 2) 문자열 정규화 유틸
# -------------------------------------------------------------
def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


# -------------------------------------------------------------
# 3) 화장실 안내 표지 프롬프트 조립 (정사각형)
# -------------------------------------------------------------
def _build_sign_toilet_prompt_en(
    festival_name_en: str,
    base_scene_en: str,
    details_phrase_en: str,
) -> str:
    """
    화장실 안내 표지 프롬프트 (간결 버전)
    - TOILET, 50m, 위쪽 화살표, 마스코트
    """

    # 분위기 텍스트는 현재 직접 사용하지 않지만, LLM 입력 정규화용으로만 정리
    _ = _norm(festival_name_en)
    _ = _norm(base_scene_en)
    _ = _norm(details_phrase_en)

    prompt = (
        "Square flat graphic of a toilet direction sign on a light background. "
        "Ignore all text, letters, and numbers in the attached image and use only its colours and visual style. "
        "At the top, draw one large solid arrow pointing straight up. "
        "In the middle, write the word \"TOILET\" in very large bold capital letters, perfectly centered. "
        "Below it, write \"50m\" in smaller bold text, also centered. "
        "Place the mascot clearly below or to the side of the text so it does not touch or overlap "
        "the letters or the arrow. "
        "Do not add any other text or numbers."
    )

    return prompt.strip()


# -------------------------------------------------------------
# 4) write_sign_toilet: Seedream 입력 JSON 생성
# -------------------------------------------------------------
def write_sign_toilet(
    mascot_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    정사각형 화장실 안내 표지(2048x2048)용 Seedream 입력 JSON을 생성한다.

    - festival_name_ko: "제15회 고흥 우주항공 축제" 또는 "고흥 우주항공 축제" 등
      → 내부에서 회차/축제명을 분리해 영어 축제명 번역에 사용한다.
      (실제 이미지 안 텍스트에는 축제명은 사용하지 않는다.)
    """

    _log_progress("1) 화장실 표지판 Seedream 입력 생성 시작...")
    _log_progress(f"   - 원본 한글 축제명: {festival_name_ko}")
    _log_progress(f"   - 기간(ko): {festival_period_ko}")
    _log_progress(f"   - 장소(ko): {festival_location_ko}")
    _log_progress(f"   - 마스코트 이미지: {mascot_image_url}")

    # 1) 회차 / 축제명 분리 (회차는 번역 품질 향상을 위한 용도로만 사용)
    festival_count, pure_name_ko = _split_festival_count_and_name(festival_name_ko)
    _log_progress(f"   - 회차 추출: {festival_count}")
    _log_progress(f"   - 회차 제거 후 한글 축제명: {pure_name_ko}")

    # 2) 한글 축제 정보 → 영어 번역 (테마/씬 묘사용)
    _log_progress("2) 한글 축제 정보를 영어로 번역 중...")
    # 1) 회차 / 축제명 분리 (회차는 번역 품질 향상을 위한 용도로만 사용)
    _, pure_name_ko = _split_festival_count_and_name(festival_name_ko)

    # 2) 한글 축제 정보 → 영어 번역 (테마/씬 묘사용)
    translated = _translate_festival_ko_to_en(
        festival_name_ko=pure_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    name_en = translated["name_en"]
    period_en = translated["period_en"]
    location_en = translated["location_en"]
    _log_progress(
        f"   - 번역 결과: name_en='{name_en}', period_en='{period_en}', location_en='{location_en}'"
    )

    # 3) 마스코트(참고 이미지) 분석 → 축제 씬/무드 묘사 얻기
    _log_progress("3) 마스코트 이미지 기반 축제 씬/무드 분석 중...")

    # 3) 마스코트(참고 이미지) 분석 → 축제 씬/무드 묘사 얻기
    scene_info = _build_scene_phrase_from_poster(
        poster_image_url=mascot_image_url,
        festival_name_en=name_en,
        festival_period_en=period_en,
        festival_location_en=location_en,
    )
    base_scene_en = scene_info["base_scene_en"]
    details_phrase_en = scene_info["details_phrase_en"]
    _log_progress(f"   - base_scene_en: '{base_scene_en[:60]}...'")
    _log_progress(f"   - details_phrase_en: '{details_phrase_en[:60]}...'")

    # 4) 최종 프롬프트 조립
    _log_progress("4) 화장실 안내 표지용 프롬프트 조립 중...")
    prompt = _build_sign_toilet_prompt_en(
        festival_name_en=name_en,
        base_scene_en=base_scene_en,
        details_phrase_en=details_phrase_en,
    )
    _log_progress("   - 프롬프트 조립 완료.")

    # 4) 최종 프롬프트 조립
    prompt = _build_sign_toilet_prompt_en(
        festival_name_en=name_en,
        base_scene_en=scene_info["base_scene_en"],
        details_phrase_en=scene_info["details_phrase_en"],
    )

    # 5) Seedream / Replicate 입력 JSON 구성
    seedream_input: Dict[str, Any] = {
        "size": "custom",
        "width": SIGN_TOILET_WIDTH,
        "height": SIGN_TOILET_HEIGHT,
        "prompt": prompt,
        "max_images": 1,
        "aspect_ratio": "1:1",  # 정사각형 비율
        "enhance_prompt": True,
        "sequential_image_generation": "disabled",
        "image_input": [
            {
                "type": "image_url",
                "url": mascot_image_url,
            }
        ],
        # 원본 축제 정보 (메타용)
        "festival_name_ko": festival_name_ko,
        "festival_name_en": name_en,
        "festival_period_ko": festival_period_ko,
        "festival_location_ko": festival_location_ko,
    }

    _log_progress("✔ Seedream 입력 JSON 생성 완료.")
    return seedream_input


# -------------------------------------------------------------
# 5) 화장실 표지 저장 디렉터리 결정
# -------------------------------------------------------------
def _get_sign_toilet_save_dir() -> Path:
    """
    SIGN_TOILET_SAVE_DIR 환경변수가 있으면:
      - 절대경로면 그대로 사용
      - 상대경로면 PROJECT_ROOT 기준으로 사용
    없으면:
      - PROJECT_ROOT/app/data/sign_toilet 사용
    """
    env_dir = os.getenv("SIGN_TOILET_SAVE_DIR")
    if env_dir:
        p = Path(env_dir)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p
    return DATA_ROOT / "sign_toilet"


# -------------------------------------------------------------
# 6) create_sign_toilet: Seedream JSON → Replicate 호출 → 이미지 저장
#     (한 번만 생성, LLM 체크 없음)
# -------------------------------------------------------------
def create_sign_toilet(
    seedream_input: Dict[str, Any],
    save_dir: Path | None = None,
    prefix: str = "sign_toilet_",
) -> Dict[str, Any]:
    """
    write_sign_toilet(...) 에서 만든 Seedream 입력 JSON을 그대로 받아
    1) image_input 의 URL/경로를 이용해 이미지를 다운로드하고,
    2) Replicate(bytedance/seedream-4 또는 SIGN_TOILET_MODEL)에
       prompt + image_input과 함께 전달해 실제 정사각형 화장실 안내 표지 이미지를 한 번 생성하고,
    3) 생성된 이미지를 로컬에 저장한다.

    - LLM 비전 검사는 수행하지 않는다.
    - 최종 저장 파일명은 sign_toilet.png 하나만 사용하려고 시도한다.
    """

    _log_progress("6) Seedream 모델 호출 및 화장실 표지판 이미지 생성 단계 진입...")

    # 1) 참고 이미지 URL/경로 추출
    image_input = seedream_input.get("image_input") or []
    if not (isinstance(image_input, list) and image_input):
        raise ValueError("seedream_input.image_input 에 참조 이미지 정보가 없습니다.")

    image_url = image_input[0].get("url")
    if not image_url:
        raise ValueError("image_input[0].url 이 비어 있습니다.")

    _log_progress(f"   - 참고 이미지 로딩 중: {image_url}")

    # 2) 참고 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(image_url)
    image_file = BytesIO(img_bytes)
    _log_progress("   - 참고 이미지 로딩 완료.")
    # 2) 참고 이미지 로딩 (URL + 로컬 파일 모두 지원)
    img_bytes = _download_image_bytes(image_url)
    image_file = BytesIO(img_bytes)

    # 3) Replicate에 넘길 공통 input 구성
    prompt = seedream_input.get("prompt", "")
    size = seedream_input.get("size", "custom")
    width = int(seedream_input.get("width", SIGN_TOILET_WIDTH))
    height = int(seedream_input.get("height", SIGN_TOILET_HEIGHT))

    # 최종 생성 이미지는 항상 1장만 요청
    max_images = 1
    aspect_ratio = seedream_input.get("aspect_ratio", "1:1")
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
        "image_input": [image_file],
        "aspect_ratio": aspect_ratio,
        "enhance_prompt": enhance_prompt,
        "sequential_image_generation": sequential_image_generation,
    }

    model_name = os.getenv("SIGN_TOILET_MODEL", "bytedance/seedream-4")
    _log_progress(
        f"   - Seedream 입력 설정: model='{model_name}', size={width}x{height}, max_images={max_images}"
    )

    output = None
    last_err: Exception | None = None

    # 모델 호출은 최대 3번까지 재시도 (네트워크/모델 에러 대비)
    for attempt in range(3):
        try:
            _log_progress(f"   - Seedream 호출 시도 {attempt + 1}/3 ...")
            output = replicate.run(model_name, input=replicate_input)
            _log_progress("   - Seedream 호출 성공, 결과 수신 완료.")
            break
        except ModelError as e:
            msg = str(e)
            _log_progress(f"   - Seedream ModelError 발생: {msg}")
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                _log_progress("   - 일시적인 오류로 판단, 1초 후 재시도...")
            output = replicate.run(model_name, input=replicate_input)
            break
        except ModelError as e:
            msg = str(e)
            if "Prediction interrupted" in msg or "code: PA" in msg:
                last_err = e
                time.sleep(1.0)
                continue
            raise RuntimeError(
                f"Seedream model error during sign toilet generation: {e}"
            )
        except Exception as e:
            _log_progress(f"   - Seedream 호출 중 예기치 못한 오류: {e}")
            raise RuntimeError(
                f"Unexpected error during sign toilet generation: {e}"
            )

    if output is None:
        _log_progress("   - 3회 시도 후에도 Seedream 호출 실패.")
        raise RuntimeError(
            f"Seedream model error during sign toilet generation after retries: {last_err}."
        )

    if not (isinstance(output, (list, tuple)) and output):
        raise RuntimeError(f"Unexpected output from model {model_name}: {output!r}")

    file_output = output[0]

    # 저장 위치 결정
    if save_dir is not None:
        save_base = Path(save_dir)
    else:
        save_base = _get_sign_toilet_save_dir()
    save_base.mkdir(parents=True, exist_ok=True)

    _log_progress(f"7) 생성 이미지 저장 디렉터리 준비 완료: {save_base}")

    # 유틸로 한 번 저장
    tmp_image_path, tmp_image_filename = _save_image_from_file_output(
        file_output, save_base, prefix=prefix
    )
    tmp_path = Path(tmp_image_path)

    # 최종 파일명은 가능한 한 sign_toilet.png 로 통일
    final_filename = "sign_toilet.png"
    final_path = save_base / final_filename

    # 이미 유틸이 sign_toilet.png 라는 이름으로 저장했다면 그대로 사용
    if tmp_path.name != final_filename:
        # 다른 이름으로 저장된 경우에만 rename
        if final_path.exists():
            final_path.unlink()
        tmp_path.replace(final_path)
    else:
        # 같은 이름이면 그대로 final_path 로 취급
        final_path = tmp_path

    _log_progress(f"✔ 화장실 표지판 이미지 저장 완료: {final_path}")

    return {
        "size": size,
        "width": width,
        "height": height,
        "image_path": str(final_path),
        "image_filename": final_filename,
        "prompt": prompt,
        "festival_name_ko": str(seedream_input.get("festival_name_ko", "")),
        "festival_name_en": str(seedream_input.get("festival_name_en", "")),
        "festival_period_ko": str(seedream_input.get("festival_period_ko", "")),
        "festival_location_ko": str(
            seedream_input.get("festival_location_ko", "")
        ),
    }


# -------------------------------------------------------------
# 7) editor → DB 경로용 헬퍼 (p_no 사용)
# -------------------------------------------------------------
def run_sign_toilet_to_editor(
    p_no: int,
    mascot_image_url: str,
    festival_name_ko: str,
    festival_period_ko: str,
    festival_location_ko: str,
) -> Dict[str, Any]:
    """
    입력:
        p_no (int)
        mascot_image_url
        festival_name_ko
        festival_period_ko
        festival_location_ko

    동작:
      1) write_sign_toilet(...) 로 Seedream 입력용 seedream_input 생성
      2) create_sign_toilet(..., save_dir=표지판 저장 디렉터리) 로
         실제 화장실 안내 표지 이미지를 생성하고,
         FRONT_PROJECT_ROOT/public/data/promotion/<member_no>/<p_no>/sign 아래에 저장한다.
      3) DB 저장용 메타 정보 딕셔너리를 반환한다.

    반환:
      {
        "db_file_type": "sign_toilet",
        "type": "image",
        "db_file_path": "<FRONT_PROJECT_ROOT>\\public\\data\\promotion\\M000001\\{p_no}\\sign\\sign_toilet.png",
        "type_ko": "화장실 표지판"
      }
    """

    _log_progress("==============================================")
    _log_progress("▶ 화장실 표지판 생성(run_sign_toilet_to_editor) 시작")
    _log_progress(f"   - p_no={p_no}")
    _log_progress(f"   - mascot_image_url={mascot_image_url}")
    _log_progress(f"   - festival_name_ko={festival_name_ko}")
    _log_progress(f"   - festival_period_ko={festival_period_ko}")
    _log_progress(f"   - festival_location_ko={festival_location_ko}")

    # 1) 프롬프트 생성
    _log_progress("▶ 1단계: Seedream 입력 JSON 생성 시작")
    # 1) 프롬프트 생성
    seedream_input = write_sign_toilet(
        mascot_image_url=mascot_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )
    _log_progress("▶ 1단계 완료: Seedream 입력 JSON 생성")

    # 2) 저장 디렉터리: FRONT_PROJECT_ROOT/public/data/promotion/<member_no>/<p_no>/sign
    _log_progress("▶ 2단계: 저장 디렉터리 생성/확인 중...")

    # 2) 저장 디렉터리: FRONT_PROJECT_ROOT/public/data/promotion/<member_no>/<p_no>/sign
    member_no = os.getenv("ACC_MEMBER_NO", "M000001")
    sign_dir = (
        FRONT_PROJECT_ROOT
        / "public"
        / "data"
        / "promotion"
        / member_no
        / str(p_no)
        / "sign"
    )
    sign_dir.mkdir(parents=True, exist_ok=True)
    _log_progress(f"   - 저장 디렉터리: {sign_dir}")

    # 3) 이미지 생성
    _log_progress(
        "▶ 3단계: Seedream 모델 호출 및 화장실 표지판 이미지 생성 시작 (시간이 조금 걸릴 수 있습니다)..."
    )

    # 3) 이미지 생성
    create_result = create_sign_toilet(
        seedream_input,
        save_dir=sign_dir,
        prefix="sign_toilet_",
    )
    _log_progress("▶ 3단계 완료: 이미지 생성 및 저장 완료.")

    db_file_path = str(create_result["image_path"])
    _log_progress(f"▶ 4단계: 최종 DB 저장 경로 확정 → {db_file_path}")

    db_file_path = str(create_result["image_path"])

    result: Dict[str, Any] = {
        "db_file_type": SIGN_TOILET_TYPE,  # "sign_toilet"
        "type": "image",
        "db_file_path": db_file_path,
        "type_ko": SIGN_TOILET_PRO_NAME,  # "화장실 표지판"
    }

    _log_progress("✔ 화장실 표지판 생성 완료. DB 메타 정보 리턴.")
    _log_progress("==============================================")

    return result


# -------------------------------------------------------------
# 8) CLI 실행용 main
# -------------------------------------------------------------
def main() -> None:
    """
    python app/service/sign/make_sign_toilet.py
    """

    # 1) 여기 값만 네가 원하는 걸로 수정해서 쓰면 됨
    p_no = 11

    mascot_image_url = r"C:\final_project\ACC\acc-ai\app\data\mascot\kimcheon.png"
    festival_name_ko = "2025 김천김밥축제"
    festival_period_ko = "2024.10.25 ~ 2024.10.26"
    festival_location_ko = "김천시 직지문화공원 및 사명대사공원 일원"

    # 2) 필수값 체크
    missing = []
    if not p_no:
        missing.append("p_no")
    if not mascot_image_url:
        missing.append("mascot_image_url")
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

    # 3) 실제 실행 (Dict 리턴)
    result = run_sign_toilet_to_editor(
        p_no=p_no,
        mascot_image_url=mascot_image_url,
        festival_name_ko=festival_name_ko,
        festival_period_ko=festival_period_ko,
        festival_location_ko=festival_location_ko,
    )

    # stdout으로는 값 4개만 딱 찍어주기 (다른 모듈들과 동일 포맷)
    db_file_type = result.get("db_file_type", "")
    type = result.get("type", "")
    db_file_path = result.get("db_file_path", "")
    type_ko = result.get("type_ko", "")

    print(db_file_type)
    print(type)
    print(db_file_path)
    print(type_ko)


if __name__ == "__main__":
    main()
