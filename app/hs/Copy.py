# -*- coding: utf-8 -*-
"""
horizontal_3024_544_make_prompt_from_analysis.py

[요약]
- analysis.json을 읽어 Dreamina 3.1용 '영문' 프롬프트 JSON을 생성
- 기본: 3024×544, aspect_ratio='custom'
- 본문: 목적/장면/미학지시(2~4 문장, 간결)
- 끝부분: 따옴표 3줄(존재 항목만, 순서 고정): "TITLE", "DATE", "LOCATION"
  * TITLE/LOCATION: 영어 번역(LLM), 따옴표 내부는 ASCII 영문/숫자/공백/하이픈만 허용
  * DATE: 입력의 압축 표기를 '영문 범위'로 정규화(LLM) → 예) December 24-25 2025
  * 따옴표는 인식용이며, 이미지에 따옴표를 그리지 말 것을 명시
  * 대괄호/각종 괄호/한글/기호는 따옴표 내부에서 제거(문자 집합 정화)
- 하드코딩 문구 주입 없음(값이 없으면 해당 라인 생략)
"""

import os, json, re
from pathlib import Path

# ------------------------- 기본값 -------------------------
DEFAULT_WIDTH  = 3024
DEFAULT_HEIGHT = 544
DEFAULT_AR     = "custom"
DEFAULT_RES    = "2K"
DEFAULT_USE_LLM= True  # 기존 동작 유지

try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

# ------------------------- 환경/유틸 -------------------------
def _load_env():
    """ .env 로드 """
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env:
            load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists():
                load_dotenv(local, override=False)

def _require_openai_key() -> str:
    """ OPENAI_API_KEY 확인 """
    key = os.getenv("OPENAI_API_KEY")
    if key: return key
    _load_env()
    key = os.getenv("OPENAI_API_KEY")
    if key: return key
    raise RuntimeError("OPENAI_API_KEY is missing in environment (.env).")

def ask_path(msg: str) -> Path:
    """ 파일 경로 입력 루프 """
    while True:
        raw = input(msg).strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file(): return p
        print("[Info] Invalid path. Please try again.")

def ask_int(msg: str, default_val: int) -> int:
    """ 양의 정수 입력(엔터시 기본값) """
    while True:
        raw = input(f"{msg} (default {default_val}): ").strip()
        if not raw: return default_val
        try:
            v = int(raw); assert v > 0
            return v
        except:
            print("[Info] Enter a positive integer.")

def ask_str(msg: str, default_val: str) -> str:
    """ 문자열 입력(엔터시 기본값) """
    raw = input(f"{msg} (default {default_val}): ").strip()
    return raw if raw else default_val

def ask_bool(msg: str, default_val: bool) -> bool:
    """ 불리언 입력(엔터시 기본값) """
    raw = input(f"{msg} (default {'true' if default_val else 'false'}): ").strip().lower()
    if not raw: return default_val
    return raw in ("1","true","t","y","yes")

def ask_optional_int(msg: str):
    """ 정수 또는 미설정 """
    raw = input(f"{msg} (press Enter to skip): ").strip()
    if not raw: return None
    try: return int(raw)
    except:
        print("[Info] Not an integer; seed will not be set.")
        return None

def safe_filename(name: str) -> str:
    """ 파일명 안전화 """
    s = re.sub(r"[^\w\s-]", "", (name or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "dreamina_prompt"

def normalize_prompt(text: str) -> str:
    """ LLM 응답에서 불필요 개행/여백 제거 및 {"prompt":"..."} 언랩 """
    t = (text or "").strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
                t = obj["prompt"]
        except:
            pass
    return " ".join(t.split())

# ------------------------- 따옴표 라인 정화 -------------------------
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -")

def _to_ascii_hyphens(s: str) -> str:
    """ 다양한 대시/틸드 → ASCII 하이픈으로 정규화 """
    return s.replace("–", "-").replace("—", "-").replace("~", "-").replace("·", " ")

def _sanitize_quoted_line_ascii_en(s: str) -> str:
    """
    따옴표 안에 들어갈 한 줄을 정화:
    - ASCII 영문/숫자/공백/하이픈('-')만 허용
    - 각종 괄호/따옴표/꺾쇠/쉼표/마침표 제거
    - 다중 공백 정리
    """
    if not s: return ""
    s = _to_ascii_hyphens(s)
    # 불필요한 기호 제거
    s = re.sub(r'[<>\[\]\(\)\{\}",.\\/|:;*!?@#$%^&_=+`]', " ", s)
    # 허용 문자만 남김
    out = []
    for ch in s:
        out.append(ch if ch in _ALLOWED else " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()

# ------------------------- OpenAI 호출 유틸 -------------------------
def _openai_chat(model: str, temperature: float, system: str, user: str) -> str:
    """ OpenAI SDK v1 우선, 실패 시 v0 호환 """
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model, temperature=temperature,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        import openai
        openai.api_key = os.getenv("OPENAI_API_KEY")
        resp = openai.ChatCompletion.create(
            model=model, temperature=temperature,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}],
        )
        return resp.choices[0].message["content"].strip()

# ------------------------- LLM: 본문(설명) -------------------------
def _llm_body_description(analysis: dict) -> str:
    """
    - Dreamina 가이드 기반 2~4문장 설명만 생성 (따옴표/값 삽입 금지)
    - 영어만 출력
    """
    _require_openai_key()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    system_msg = (
        "Write 2-4 compact ENGLISH sentences for a LONG HORIZONTAL FESTIVAL BANNER BACKGROUND. "
        "Use ONLY the provided JSON. State purpose/type (ultra-wide print banner), "
        "scene/environment, and concise aesthetic directives (layout/typography/color/lighting/composition). "
        "Mention a clear headline area if implied. Do NOT include any quoted text or field values."
    )
    return normalize_prompt(_openai_chat(model, 0.2, system_msg, json.dumps(analysis, ensure_ascii=False)))

# ------------------------- LLM: 필드 추출/번역(영어) -------------------------
def _llm_extract_fields_en(analysis: dict) -> dict:
    """
    - TITLE/LOCATION: 자연스러운 영어
    - DATE: '언제부터–언제까지' 영어 범위(연/월 생략 시 시작값 승계, 하이픈 '-')
    - 출력: {"title_en":"...", "date_range_en":"...", "location_en":"..."}
    - 따옴표/괄호/특수문자 없이 ASCII 영문/숫자/공백/하이픈만 사용
    """
    _require_openai_key()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    system_msg = (
        "Extract ENGLISH fields for a festival banner from the given JSON and RETURN JSON only with keys: "
        "title_en, date_range_en, location_en. Rules: "
        "• title_en: natural English festival title (ASCII letters/numbers/spaces/hyphen only). "
        "• date_range_en: normalize compact forms (e.g., '2025.12.24 - 12.25', '2025.12.24 ~25') into an English range like 'December 24-25 2025'. "
        "  Inherit missing year/month from the start; use ASCII hyphen '-' as the range separator; avoid commas and abbreviations. "
        "• location_en: concise English place name (ASCII letters/numbers/spaces/hyphen only). "
        "• Do NOT include quotes, brackets, parentheses, or any non-ASCII characters. Use empty string if unknown."
    )
    txt = _openai_chat(model, 0.1, system_msg, json.dumps(analysis, ensure_ascii=False))
    try:
        # 모델이 JSON이 아닌 텍스트로 답하면, 중괄호 블록만 추출 시도
        if not txt.strip().startswith("{"):
            m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
            if m: txt = m.group(0)
        data = json.loads(txt)
    except Exception as e:
        raise RuntimeError(f"LLM field extraction failed to return valid JSON: {e}")
    # 최종 ASCII 정화
    title = _sanitize_quoted_line_ascii_en(data.get("title_en",""))
    date  = _sanitize_quoted_line_ascii_en(data.get("date_range_en",""))
    loc   = _sanitize_quoted_line_ascii_en(data.get("location_en",""))
    return {"title_en": title, "date_range_en": date, "location_en": loc}

# ------------------------- 프롬프트 작성(핵심) -------------------------
def llm_compose_prompt(analysis: dict) -> str:
    """
    - 본문(2~4문장)은 영어 설명만
    - 따옴표 라인은 우리가 조립: "TITLE", "DATE", "LOCATION" (존재하는 값만)
    - 따옴표는 인식용, 이미지엔 따옴표 그리지 말 것
    """
    body = _llm_body_description(analysis)
    fields = _llm_extract_fields_en(analysis)

    quoted_lines = []
    if fields.get("title_en"):
        quoted_lines.append(f"\"{fields['title_en']}\"")
    if fields.get("date_range_en"):
        quoted_lines.append(f"\"{fields['date_range_en']}\"")
    if fields.get("location_en"):
        quoted_lines.append(f"\"{fields['location_en']}\"")

    if not quoted_lines:
        raise RuntimeError("No valid quoted lines (title/date/location). Check the input JSON content.")

    quoted_clause = ", ".join(quoted_lines)

    tail = (
        " Place the following text exactly, each on its own line, inside double quotes "
        "(quotes are for parsing only; do not draw the quote marks in the image): "
        f"{quoted_clause}. No extra text, no watermarks or logos, no borders or frames."
    )

    return normalize_prompt(body + tail)

# ------------------------- 메인(입력 흐름 동일) -------------------------
def main():
    print("=== Dreamina 3.1 Prompt Builder (analysis.json -> prompt JSON, default 3024x544) ===")
    analysis_path = ask_path("1) Path to analysis.json: ")
    width  = ask_int("2) width", DEFAULT_WIDTH)
    height = ask_int("3) height", DEFAULT_HEIGHT)
    aspect_ratio = ask_str("4) aspect_ratio", DEFAULT_AR)
    resolution   = ask_str("5) resolution", DEFAULT_RES)
    use_pre_llm  = ask_bool("6) use_pre_llm(true/false)", DEFAULT_USE_LLM)
    seed         = ask_optional_int("7) seed (integer)")

    # 입력 JSON 로드
    try:
        root = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Error] Failed to load JSON: {e}"); return
    analysis = root.get("analysis") or {}

    # 프롬프트 생성
    try:
        prompt = llm_compose_prompt(analysis)
    except Exception as e:
        print(f"[Failed] LLM prompt generation error: {e}"); return

    # 출력 경로 및 저장
    title = (analysis.get("title") or "banner").strip()
    out_default = Path("out") / f"{safe_filename(title)}_horiz_3024x544_dreamina_prompt.json"
    print(f"8) Output path (press Enter for {out_default}): ", end="")
    raw_out = input().strip().strip('"')
    out_path = Path(raw_out) if raw_out else out_default
    out_path.parent.mkdir(parents=True, exist_ok=True)

    obj = {
        "width": width,
        "height": height,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "use_pre_llm": use_pre_llm
    }
    if seed is not None:
        obj["seed"] = seed

    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[Done] Dreamina prompt JSON saved:", out_path)
    print(json.dumps(obj, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
