# -*- coding: utf-8 -*-
"""
vertical_1008_3024_make_prompt_from_analysis.py
- 세로형 1008×3024 기본 / aspect_ratio='custom'
- 배너에는 '값 3줄만' 렌더(영문/라틴 문자만, 라벨/세미콜론/따옴표/여타 문자 금지)
"""

import os, json, re
from pathlib import Path

DEFAULT_WIDTH  = 1008
DEFAULT_HEIGHT = 3024
DEFAULT_AR     = "custom"
DEFAULT_RES    = "2K"
DEFAULT_USE_LLM= True  # 기본 true

try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

def _load_env():
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env: load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists(): load_dotenv(local, override=False)

def _require_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if key: return key
    _load_env(); key = os.getenv("OPENAI_API_KEY")
    if key: return key
    raise RuntimeError("OPENAI_API_KEY가 없습니다(.env).")

def ask_path(msg: str) -> Path:
    while True:
        raw = input(msg).strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file(): return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def ask_int(msg: str, default_val: int) -> int:
    while True:
        raw = input(f"{msg} (기본 {default_val}): ").strip()
        if not raw: return default_val
        try:
            v = int(raw); assert v > 0
            return v
        except: print("[안내] 양의 정수를 입력하세요.")

def ask_str(msg: str, default_val: str) -> str:
    raw = input(f"{msg} (기본 {default_val}): ").strip()
    return raw if raw else default_val

def ask_bool(msg: str, default_val: bool) -> bool:
    raw = input(f"{msg} (기본 {'true' if default_val else 'false'}): ").strip().lower()
    if not raw: return default_val
    return raw in ("1","true","t","y","yes")

def ask_optional_int(msg: str):
    raw = input(f"{msg} (엔터시 미설정): ").strip()
    if not raw: return None
    try: return int(raw)
    except: print("[안내] 정수가 아니어서 seed는 설정하지 않습니다."); return None

def safe_filename(name: str) -> str:
    s = re.sub(r"[^\w\s\uAC00-\uD7A3-]", "", (name or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "dreamina_prompt"

def normalize_prompt(text: str) -> str:
    t = (text or "").strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
                t = obj["prompt"]
        except: pass
    return " ".join(t.split())

def llm_compose_prompt(analysis: dict) -> str:
    _require_openai_key()
    system_msg = (
        "You are a senior banner art director.\n"
        "Write ONE concise English prompt for bytedance/dreamina-3.1 to generate a TALL VERTICAL FESTIVAL BANNER BACKGROUND.\n"
        "Rules:\n"
        "- Use only the JSON the user provides; infer season/theme/visuals from it.\n"
        "- Background only; kid-safe; NO people. Bold sans-serif; high contrast; clean composition; clear area near TOP for headline.\n"
        "- Translate Korean title/date/location into English and provide the VALUES for clarity as:\n"
        "  Values — TITLE=<title>, DATE=<date>, LOCATION=<location>.\n"
        "- IMPORTANT: On the banner, render ONLY the three VALUES in English (Latin letters only). "
        "No labels, punctuation, quotes, symbols, extra words, numbers, logos, or any other text. "
        "Absolutely no Chinese/Korean/Japanese characters.\n"
        "- Use 4–8 vivid visual descriptors from the JSON; keep the whole prompt succinct (<=300 chars ideally).\n"
        "- Single line; do NOT mention size/aspect ratio."
    )
    model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model_name, temperature=0.2,
            messages=[{"role":"system","content":system_msg},
                      {"role":"user","content":json.dumps(analysis, ensure_ascii=False)}],
        )
        text = resp.choices[0].message.content.strip()
    except Exception:
        import openai
        openai.api_key = os.getenv("OPENAI_API_KEY")
        resp = openai.ChatCompletion.create(
            model=model_name, temperature=0.2,
            messages=[{"role":"system","content":system_msg},
                      {"role":"user","content":json.dumps(analysis, ensure_ascii=False)}],
        )
        text = resp.choices[0].message["content"].strip()
    return normalize_prompt(text)

def main():
    print("=== Dreamina 3.1 프롬프트 생성기 (analysis.json -> prompt JSON, 1008x3024 기본) ===")
    analysis_path = ask_path("1) analysis.json 경로: ")
    width  = ask_int("2) width", DEFAULT_WIDTH)
    height = ask_int("3) height", DEFAULT_HEIGHT)
    aspect_ratio = ask_str("4) aspect_ratio", DEFAULT_AR)
    resolution   = ask_str("5) resolution", DEFAULT_RES)
    use_pre_llm  = ask_bool("6) use_pre_llm(true/false)", DEFAULT_USE_LLM)
    seed         = ask_optional_int("7) seed 정수")

    try:
        root = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[에러] JSON 로드 실패: {e}"); return
    analysis = root.get("analysis") or {}

    try:
        prompt = llm_compose_prompt(analysis)
    except Exception as e:
        print(f"[실패] LLM 프롬프트 생성 오류: {e}"); return

    title = (analysis.get("title") or "banner").strip()
    out_default = Path("out") / f"{safe_filename(title)}_vert_1008x3024_dreamina_prompt.json"
    print(f"8) 출력 경로 (엔터시 {out_default}): ", end="")
    raw_out = input().strip().strip('"')
    out_path = Path(raw_out) if raw_out else out_default
    out_path.parent.mkdir(parents=True, exist_ok=True)

    obj = {
        "width": width, "height": height, "prompt": prompt,
        "aspect_ratio": aspect_ratio, "resolution": resolution, "use_pre_llm": use_pre_llm
    }
    if seed is not None: obj["seed"] = seed

    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[완료] Dreamina 프롬프트 JSON 저장:", out_path)
    print(json.dumps(obj, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
