# -*- coding: utf-8 -*-
"""
test_banner_prompt_full_io.py

목적
- 입력(payload)과 출력(result)을 "전부" 콘솔에 출력 (truncate 없음)
- .env를 로드하여 OPENAI_API_KEY/LLM_MODEL 반영
- out/test_prompts/ 에 입력/출력 JSON 저장(옵션)
- schema="basic" 으로 네가 지정한 출력 스키마만 반환/검증

실행(루트에서):
  python .\test\test_banner_prompt_full_io.py
또는
  python -m test.test_banner_prompt_full_io
"""

import os, sys, json, traceback
from pathlib import Path

# ========= 설정 =========
SAVE_TO_FILE = True   # 콘솔 출력 + 파일 저장
OUT_DIR = Path("out") / "test_prompts"

# --- 루트 자동 탐색 후 sys.path 추가 (파일 경로 실행 지원) ---
def _ensure_project_root_on_sys_path():
    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        if (parent / "app").is_dir():
            sys.path.insert(0, str(parent))
            return str(parent)
    raise SystemExit("❌ 프로젝트 루트를 찾지 못했습니다. 'app' 폴더 경로를 확인하세요.")

ROOT = _ensure_project_root_on_sys_path()

# ✅ .env 로드 (.env는 프로젝트 루트에 있어야 함)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(ROOT) / ".env", override=False)
except Exception:
    # python-dotenv 미설치시에도 테스트는 동작(단, 키는 미반영)
    pass

from app.service.banner.make_prompt_from_analysis import (
    make_horizontal_banner_prompt_service,
    make_vertical_banner_prompt_service,
    make_banner_prompt_service,
)

# 네가 요구한 출력 스키마 키 집합
EXPECTED_KEYS = {
    "width","height","aspect_ratio","resolution","use_pre_llm",
    "prompt_original","prompt","prompt_ko_original","prompt_ko","prompt_ko_baseline",
}

def build_payload_ascii_ok() -> dict:
    """FestivalService.analyze(...) 반환 스키마와 호환되는 샘플 입력"""
    return {
        "p_name": "제7회 담양산타축제",
        "user_theme": "어린아이들의 행복",
        "keywords": ["행복", "미래", "꿈"],
        "festival": {
            "title": "The 7th Damyang Santa Festival",   # ASCII title
            "date": "2025.12.20 ~ 2025.12.21",           # 숫자/기호 ASCII
            "location": "Damyang Meta Land Area",        # ASCII location
            "theme": "Family-centered winter festival",
            "summary": "Night lights, photo zones, participatory parade",
            "visual_keywords": ["Santa", "snow", "warm red green palette", "winter night lights", "photo zone"],
        },
        "analysis": {
            "similarity": 0.86,
            "decision": "accept",
            "original_theme": "어린이 중심 체험형 겨울축제",
            "corrected_theme": "어린아이들의 행복을 강조한 가족 참여형 겨울축제",
        },
    }

def dump_json(title: str, obj: dict, path: Path | None = None):
    """truncate 없이 전체 JSON을 콘솔에 출력하고(필요시) 파일로 저장"""
    print(f"\n===== {title} =====")
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    print(txt)  # ✅ 전체 출력
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(txt, encoding="utf-8")
        print(f"[saved] {path.resolve()}")

def assert_basic_schema(d: dict):
    keys = set(d.keys())
    assert keys == EXPECTED_KEYS, f"반환 키 불일치: {keys} != {EXPECTED_KEYS}"

def case_horizontal(payload: dict):
    name = "horizontal_basic"
    dump_json("INPUT (analyze payload)", payload, OUT_DIR / f"{name}_input.json" if SAVE_TO_FILE else None)
    out = make_horizontal_banner_prompt_service(
        payload,
        use_pre_llm=True,   # 키 있으면 번역/본문 LLM 사용, 없으면 폴백
        strict=True,
        schema="basic",     # ⬅️ 네가 지정한 스키마로 축소
    )
    assert_basic_schema(out)
    dump_json("OUTPUT (result obj)", out, OUT_DIR / f"{name}_output.json" if SAVE_TO_FILE else None)

def case_vertical(payload: dict):
    name = "vertical_basic"
    dump_json("INPUT (analyze payload)", payload, OUT_DIR / f"{name}_input.json" if SAVE_TO_FILE else None)
    out = make_vertical_banner_prompt_service(
        payload,
        use_pre_llm=True,
        strict=True,
        schema="basic",
    )
    assert_basic_schema(out)
    dump_json("OUTPUT (result obj)", out, OUT_DIR / f"{name}_output.json" if SAVE_TO_FILE else None)

def case_custom(payload: dict):
    name = "custom_basic_4096x736_seed123"
    dump_json("INPUT (analyze payload)", payload, OUT_DIR / f"{name}_input.json" if SAVE_TO_FILE else None)
    out = make_banner_prompt_service(
        payload,
        orientation="horizontal",
        width=4096, height=736,
        use_pre_llm=True,
        seed=123,     # basic 스키마에는 seed를 포함하지 않음
        strict=True,
        schema="basic",
    )
    assert_basic_schema(out)
    dump_json("OUTPUT (result obj)", out, OUT_DIR / f"{name}_output.json" if SAVE_TO_FILE else None)

def main():
    print(f"[i] project root: {ROOT}")
    print(f"[i] OPENAI_API_KEY set? {'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")
    payload = build_payload_ascii_ok()

    for fn in (case_horizontal, case_vertical, case_custom):
        try:
            fn(payload)
        except Exception as e:
            print("[ERROR]", fn.__name__, "-", type(e).__name__, str(e))
            traceback.print_exc()
            raise

    print("\n✅ All full-IO cases completed.")

if __name__ == "__main__":
    main()
