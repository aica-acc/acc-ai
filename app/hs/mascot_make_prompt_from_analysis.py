# -*- coding: utf-8 -*-
"""
mascot_make_prompt_from_analysis.py

- analysis.json만 보고 '마스코트 이미지 생성 모델'용 설정 JSON 생성
- 출력 스키마 예시:
  {
    "width": 1024,
    "height": 1024,
    "prompt": "...",
    "refine": "no_refiner",
    "scheduler": "K_EULER",
    "lora_scale": 0.6,
    "num_outputs": 1,
    "guidance_scale": 7.5,
    "apply_watermark": true,
    "high_noise_frac": 0.8,
    "negative_prompt": "...",
    "prompt_strength": 0.8,
    "num_inference_steps": 26
  }

실행 흐름:
  1) python mascot_make_prompt_from_analysis.py
  2) 콘솔에 analysis.json 경로 입력
  3) (선택) 기본값 유지 또는 하이퍼파라미터 조정
  4) 같은 폴더에 <입력파일명>_mascot_config.json 저장 + stdout 출력

주의:
 - 프롬프트 내용은 '입력 JSON의 값'만 사용해 구성(계절/행사타입 등 키워드 하드코딩 분기 없음).
 - LLM 사용 시에도 입력 JSON 외 정보 금지.
"""

import os
import json
import re
from pathlib import Path

# -----------------------------
# 기본 하이퍼파라미터 (엔터 시 유지)
# -----------------------------
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_REFINE = "no_refiner"
DEFAULT_SCHEDULER = "K_EULER"
DEFAULT_LORA_SCALE = 0.6
DEFAULT_NUM_OUTPUTS = 1
DEFAULT_GUIDANCE_SCALE = 7.5
DEFAULT_APPLY_WATERMARK = True
DEFAULT_HIGH_NOISE_FRAC = 0.8
DEFAULT_PROMPT_STRENGTH = 0.8
DEFAULT_NUM_INFERENCE_STEPS = 26
DEFAULT_USE_LLM = True  # 배너 예제와 동일하게 기본 True

# -----------------------------
# (선택) dotenv로 OPENAI_API_KEY 읽기
# -----------------------------
try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

def _load_env():
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env:
            load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists():
                load_dotenv(local, override=False)

def _get_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    _load_env()
    return os.getenv("OPENAI_API_KEY", "")

# -----------------------------
# 입력 헬퍼
# -----------------------------
def ask_path(msg: str) -> Path:
    while True:
        raw = input(msg).strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file():
            return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def ask_int(msg: str, default_val: int) -> int:
    raw = input(f"{msg} (기본 {default_val}): ").strip()
    if not raw:
        return default_val
    try:
        v = int(raw)
        assert v > 0
        return v
    except:
        print("[안내] 양의 정수를 입력하세요. 기본값을 사용합니다.")
        return default_val

def ask_float(msg: str, default_val: float) -> float:
    raw = input(f"{msg} (기본 {default_val}): ").strip()
    if not raw:
        return default_val
    try:
        return float(raw)
    except:
        print("[안내] 숫자를 입력하세요. 기본값을 사용합니다.")
        return default_val

def ask_bool(msg: str, default_val: bool) -> bool:
    raw = input(f"{msg} (기본 {'true' if default_val else 'false'}): ").strip().lower()
    if not raw:
        return default_val
    return raw in ("1", "true", "t", "y", "yes", "ㅇ", "예", "네")

def ask_str(msg: str, default_val: str) -> str:
    raw = input(f"{msg} (기본 {default_val}): ").strip()
    return raw if raw else default_val

def ask_optional_int(msg: str):
    raw = input(f"{msg} (엔터시 미설정): ").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except:
        print("[안내] 정수가 아니어서 설정하지 않습니다.")
        return None

# -----------------------------
# 유틸
# -----------------------------
def safe_get(dct, path, default=None):
    cur = dct
    for p in path.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def join_list(items):
    return ", ".join([str(x) for x in items if x])

def safe_filename(name: str) -> str:
    s = re.sub(r"[^\w\s\uAC00-\uD7A3-]", "", (name or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "mascot_config"

def normalize_one_line(text: str) -> str:
    return " ".join((text or "").split())

# -----------------------------
# 프롬프트 생성 (LLM 보조 / 규칙 기반)
# -----------------------------
def deterministic_compose_prompt(analysis: dict) -> str:
    """
    입력 JSON의 값만으로 구성하는 규칙 기반 프롬프트.
    - 계절/행사타입 등 하드코딩 키워드 분기 없음
    - 축제명/의도/키워드/비주얼키워드/요약/대상/장소/프로그램/이벤트를 서술형 힌트로만 연결
    - 마스코트 일반 규칙(전신, 정면, 심플 배경 등)은 '일반 디자인 가이드'로만 표기 (특정 작가/브랜드 금지)
    """
    title   = safe_get(analysis, "title") or safe_get(analysis, "festival_name") or ""
    date    = safe_get(analysis, "date") or ""
    loc     = safe_get(analysis, "location") or ""
    intent  = safe_get(analysis, "intent") or ""
    summary = safe_get(analysis, "summary") or ""
    audience= safe_get(analysis, "targetAudience") or ""
    kws_in  = safe_get(analysis, "keywords", []) or []           # 일부 분석 JSON엔 여기 없을 수 있음
    kws_in2 = safe_get(analysis, "visualKeywords", []) or []
    programs= safe_get(analysis, "programs", []) or []
    events  = safe_get(analysis, "events", []) or []

    # 입력 JSON의 원문 값을 최대한 보존하여, 묘사 힌트로만 사용
    descriptors = []
    if summary: descriptors.append(summary)
    if kws_in: descriptors.append("keywords: " + join_list(kws_in))
    if kws_in2: descriptors.append("visual: " + join_list(kws_in2))
    if programs: descriptors.append("programs: " + join_list(programs))
    if events: descriptors.append("events: " + join_list(events))
    if audience: descriptors.append("audience: " + audience)
    if date: descriptors.append("date: " + date)
    if loc: descriptors.append("location: " + loc)

    core_rules = (
        "Kid-safe festival mascot character; full body; front-facing; rounded, readable silhouette; "
        "clean neutral background; high quality; sticker/merch-ready; no text; no logos; no watermark; "
        "no branded characters; avoid copyrights."
    )

    header = f"For the festival: {title}. Concept inspired by intent: {intent}." if (title or intent) else ""
    desc = " ".join(descriptors) if descriptors else ""
    style = "Style: clean vector-plus-soft-shading, minimal seams, even lighting, simple color harmony."

    return normalize_one_line(" ".join([core_rules, header, desc, style]).strip())

def llm_compose_prompt(analysis: dict) -> str:
    """
    LLM이 입력 JSON만으로 한 줄 프롬프트를 요약 생성.
    - 특정 아티스트/브랜드/IP 사용 금지
    - 결과가 비어있거나 예외가 나면 deterministic_compose_prompt로 폴백
    """
    try:
        key = _get_openai_key()
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")

        system_msg = (
            "You are a senior character designer for festival mascots.\n"
            "Write ONE concise English prompt for a generic diffusion model to generate a kid-safe festival MASCOT image.\n"
            "STRICT RULES:\n"
            "- Use ONLY the JSON provided by the user. Do NOT add facts from elsewhere.\n"
            "- No people; it's a mascot character. Full body, front-facing, clean neutral background.\n"
            "- Avoid any artist/brand/IP names. No copyrighted characters. No text/logos/watermarks.\n"
            "- Use the festival title/intent/keywords/visualKeywords/summary/programs/events/audience/date/location ONLY as descriptive hints.\n"
            "- Keep it a SINGLE sentence (<= 300 chars ideally)."
        )
        model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model=model_name, temperature=0.2,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": json.dumps(analysis, ensure_ascii=False)}
                ],
            )
            text = resp.choices[0].message.content.strip()
        except Exception:
            import openai
            openai.api_key = key
            resp = openai.ChatCompletion.create(
                model=model_name, temperature=0.2,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": json.dumps(analysis, ensure_ascii=False)}
                ],
            )
            text = resp.choices[0].message["content"].strip()

        text = normalize_one_line(text)
        # 혹시 {"prompt":"..."} 형태면 언랩
        if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
                    text = normalize_one_line(obj["prompt"])
            except:
                pass
        if not text:
            raise RuntimeError("Empty prompt from LLM")
        return text

    except Exception:
        # 키 없음/오류 시 규칙 기반으로 폴백
        return deterministic_compose_prompt(analysis)

# -----------------------------
# 메인
# -----------------------------
def main():
    print("=== Mascot Config Generator (analysis.json -> mascot_config.json) ===")
    in_path = ask_path("1) analysis.json 경로: ")

    # 하이퍼파라미터(배너 예제처럼 기본값 제시 — 엔터로 그대로 사용)
    width  = ask_int("2) width", DEFAULT_WIDTH)
    height = ask_int("3) height", DEFAULT_HEIGHT)
    refine = ask_str("4) refine", DEFAULT_REFINE)
    scheduler = ask_str("5) scheduler", DEFAULT_SCHEDULER)
    lora_scale = ask_float("6) lora_scale", DEFAULT_LORA_SCALE)
    num_outputs = ask_int("7) num_outputs", DEFAULT_NUM_OUTPUTS)
    guidance_scale = ask_float("8) guidance_scale", DEFAULT_GUIDANCE_SCALE)
    apply_watermark = ask_bool("9) apply_watermark (true/false)", DEFAULT_APPLY_WATERMARK)
    high_noise_frac = ask_float("10) high_noise_frac", DEFAULT_HIGH_NOISE_FRAC)
    prompt_strength = ask_float("11) prompt_strength", DEFAULT_PROMPT_STRENGTH)
    num_inference_steps = ask_int("12) num_inference_steps", DEFAULT_NUM_INFERENCE_STEPS)
    use_pre_llm = ask_bool("13) use_pre_llm (true/false)", DEFAULT_USE_LLM)
    seed = ask_optional_int("14) (선택) seed 정수")

    # JSON 로드
    try:
        root = json.loads(in_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[에러] JSON 로드 실패: {e}")
        return

    # 'analysis' 블록 우선, 없으면 루트 전체에서 사용 가능한 키만 활용
    analysis = root.get("analysis") or root

    # 프롬프트 생성
    prompt = llm_compose_prompt(analysis) if use_pre_llm else deterministic_compose_prompt(analysis)

    # 네거티브 프롬프트 (일반 품질/안전 가이드, 특정 축제명/테마 하드코딩 없음)
    negative_prompt = ", ".join([
        "text", "logo", "watermark", "signature", "low quality", "lowres", "blurry",
        "gore", "nsfw", "extra limbs", "disfigured", "cropped", "busy background",
        "noisy", "bad proportions", "branded character", "copyrighted character"
    ])

    # 출력 경로
    default_out = in_path.with_name(in_path.stem + "_mascot_config.json")
    print(f"15) 출력 경로 (엔터시 {default_out}): ", end="")
    out_raw = input().strip().strip('"')
    out_path = Path(out_raw) if out_raw else default_out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 결과 구성
    obj = {
        "width": width,
        "height": height,
        "prompt": prompt,
        "refine": refine,
        "scheduler": scheduler,
        "lora_scale": lora_scale,
        "num_outputs": num_outputs,
        "guidance_scale": guidance_scale,
        "apply_watermark": bool(apply_watermark),
        "high_noise_frac": high_noise_frac,
        "negative_prompt": negative_prompt,
        "prompt_strength": prompt_strength,
        "num_inference_steps": num_inference_steps
    }
    if seed is not None:
        obj["seed"] = seed

    # 저장 + 출력
    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[완료] Mascot 설정 JSON 저장:", out_path)
    print(json.dumps(obj, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
