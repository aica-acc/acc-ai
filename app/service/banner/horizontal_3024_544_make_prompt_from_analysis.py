# -*- coding: utf-8 -*-
"""
horizontal_3024_544_make_prompt_from_analysis.py

- analysis.json → Dreamina 3.1용 프롬프트 JSON 생성
- 기본 입력 흐름/질문 유지
- 출력 JSON에 다음 필드 포함:
  * prompt                : 영문 원본
  * prompt_ko_auto        : 자동 생성된 한글 원본(기준선)
  * prompt_ko             : 사용자 편집용(초기에는 prompt_ko_auto와 동일)
  * prompt_en_sha256      : 영문 prompt 해시 (기준 검증용)
- 하드코딩 금지: OPENAI_API_KEY 없으면 prompt_ko_*는 ""로 저장
"""

import os, json, re, hashlib
from pathlib import Path

DEFAULT_WIDTH  = 3024
DEFAULT_HEIGHT = 544
DEFAULT_AR     = "custom"
DEFAULT_RES    = "2K"
DEFAULT_USE_LLM= True

PHRASE = "Place the following text exactly, each on its own line, inside double quotes"

# ---------- I/O ----------
def ask_path(msg: str) -> Path:
    while True:
        raw = input(f"{msg}: ").strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file(): return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def ask_int(msg: str, default_val: int) -> int:
    while True:
        raw = input(f"{msg} (default {default_val}): ").strip()
        if not raw: return default_val
        try:
            v = int(raw); assert v>0
            return v
        except: print("[안내] 양의 정수를 입력하세요.")

def ask_str(msg: str, default_val: str) -> str:
    raw = input(f"{msg} (default {default_val}): ").strip()
    return raw if raw else default_val

def ask_bool(msg: str, default_val: bool) -> bool:
    raw = input(f"{msg} (default {'true' if default_val else 'false'}): ").strip().lower()
    if not raw: return default_val
    return raw in ("1","true","t","y","yes")

def ask_optional_int(msg: str):
    raw = input(f"{msg} (press Enter to skip): ").strip()
    if not raw: return None
    try: return int(raw)
    except: print("[안내] 정수가 아닙니다. seed 미사용."); return None

def safe_filename(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", (name or ""), flags=re.UNICODE).strip()
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

# ---------- OpenAI ----------
def _ensure_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        env = find_dotenv(usecwd=True)
        if env: load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists(): load_dotenv(local, override=False)
    except Exception: pass

def _have_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))

def _chat(system: str, user: str, model: str = None, temperature: float = 0.2) -> str:
    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
        rsp = OpenAI().chat.completions.create(
            model=model, temperature=temperature,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}]
        )
        return (rsp.choices[0].message.content or "").strip()
    except Exception:
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            rsp = openai.ChatCompletion.create(
                model=model, temperature=temperature,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}]
            )
            return (rsp.choices[0].message["content"] or "").strip()
        except Exception:
            return ""

# ---------- LLM 보조 ----------
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -")
def _to_ascii_hyphens(s: str) -> str:
    return (s or "").replace("–","-").replace("—","-").replace("~","-").replace("·"," ")

def _sanitize_quoted_line_ascii_en(s: str) -> str:
    if not s: return ""
    s = _to_ascii_hyphens(s)
    s = re.sub(r'[<>\[\]\(\)\{\}",.\\/|:;*!?@#$%^&_=+`]', " ", s)
    out = []
    for ch in s:
        out.append(ch if ch in _ALLOWED else " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()

def _llm_extract_fields_en(analysis: dict) -> dict:
    _ensure_env()
    if not _have_key():
        # 하드코딩 금지: 임의 생성 불가 → 빈값
        return {"title_en":"","date_range_en":"","location_en":""}
    system_msg = (
        "From the provided JSON, RETURN a minimal JSON with keys: title_en, date_range_en, location_en. "
        "ASCII only; use single '-' for ranges; do not invent values."
    )
    txt = _chat(system_msg, json.dumps(analysis, ensure_ascii=False), temperature=0.1)
    try:
        if not txt.strip().startswith("{"):
            m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
            if m: txt = m.group(0)
        data = json.loads(txt)
    except Exception as e:
        raise RuntimeError(f"Field extraction JSON error: {e}")
    return {
        "title_en":       _sanitize_quoted_line_ascii_en(data.get("title_en","")),
        "date_range_en":  _sanitize_quoted_line_ascii_en(data.get("date_range_en","")),
        "location_en":    _sanitize_quoted_line_ascii_en(data.get("location_en","")),
    }

def _llm_body_description(analysis: dict, title_en_hint: str) -> str:
    _ensure_env()
    if not _have_key():
        raise RuntimeError("OPENAI_API_KEY missing; cannot compose body.")
    system_msg = (
        "Write EXACTLY THREE compact ENGLISH sentences for a LONG HORIZONTAL FESTIVAL BANNER BACKGROUND. "
        "Sentence 1 MUST begin with: 'Ultra-wide print banner for the {TITLE}, set against a ...' "
        "Sentence 2 MUST begin with: 'Emphasize ...' "
        "Sentence 3 MUST begin with: 'Incorporate ...' "
        "ASCII only."
    )
    payload = {"analysis": analysis, "title_en_hint": title_en_hint or "the festival"}
    raw = _chat(system_msg, json.dumps(payload, ensure_ascii=False), temperature=0.2)
    text = normalize_prompt(raw)
    # title 강제 치환
    text = text.replace("{TITLE}", (title_en_hint or "the festival"))
    def _force_title_ascii(body: str, title_en: str) -> str:
        patts = [
            r'^(Ultra\-wide print banner for the\s*)([^,]+)(,)(.*)$',
            r'^(Ultra\-wide print banner for\s*)([^,]+)(,)(.*)$',
        ]
        for prx in patts:
            m = re.match(prx, body)
            if m: return m.group(1) + (title_en or "the festival") + m.group(3) + m.group(4)
        return body
    text = _force_title_ascii(text, title_en_hint or "the festival")
    text = "".join(ch if ord(ch) < 128 else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()

def compose_prompt_en(analysis: dict) -> str:
    fields = _llm_extract_fields_en(analysis)
    title_en = fields.get("title_en") or "the festival"
    body = _llm_body_description(analysis, title_en)

    quoted = []
    if fields.get("title_en"):      quoted.append(f"\"{fields['title_en']}\"")
    if fields.get("date_range_en"): quoted.append(f"\"{fields['date_range_en']}\"")
    if fields.get("location_en"):   quoted.append(f"\"{fields['location_en']}\"")
    if not quoted:
        raise RuntimeError("No valid quoted lines; title/date/location missing.")

    tail = (
        " Place the following text exactly, each on its own line, inside double quotes "
        "(quotes are for parsing only; do not draw the quote marks in the image): "
        + ", ".join(quoted)
        + ". No extra text, no watermarks or logos, no borders or frames."
    )
    return normalize_prompt(body + " " + tail)

def translate_prompt_to_ko(prompt_en: str) -> str:
    _ensure_env()
    if not _have_key(): return ""
    sysmsg = ("Translate the following English prompt for an image-generation model into natural Korean for user display. "
              "Preserve structure and content exactly; output only the translation.")
    return _chat(sysmsg, prompt_en, temperature=0.0) or ""

# ---------- main ----------
def main():
    print("=== Dreamina Prompt Builder (3024x544) ===")
    analysis_path = ask_path("1) Path to analysis.json")
    width  = ask_int("2) width", DEFAULT_WIDTH)
    height = ask_int("3) height", DEFAULT_HEIGHT)
    aspect_ratio = ask_str("4) aspect_ratio", DEFAULT_AR)
    resolution   = ask_str("5) resolution", DEFAULT_RES)
    use_pre_llm  = ask_bool("6) use_pre_llm(true/false)", DEFAULT_USE_LLM)
    seed         = ask_optional_int("7) seed (integer)")

    try:
        root = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Error] JSON load failed: {e}"); return
    analysis = root.get("analysis") or {}

    try:
        prompt_en = compose_prompt_en(analysis)
    except Exception as e:
        print(f"[Failed] prompt compose error: {e}"); return

    # 한글 번역(기준선)
    prompt_ko_auto = translate_prompt_to_ko(prompt_en)  # 키 없으면 ""

    title = (analysis.get("title") or "banner").strip()
    out_path = Path("out") / f"{safe_filename(title)}_horiz_3024x544_dreamina_prompt.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ... prompt_en, prompt_ko_auto(=최초 한글)까지 만들었다고 가정
    obj = {
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "use_pre_llm": use_pre_llm,
        "prompt_original": prompt_en,           # 최초 영문 원형
        "prompt": prompt_en,                    # 현재 사용 영문
        "prompt_ko_original": prompt_ko_auto,   # 최초 한글 원형
        "prompt_ko": prompt_ko_auto,            # 사용자 편집용
        "prompt_ko_baseline": prompt_ko_auto    # 🔁 롤링 비교 기준선(초기값은 원형과 동일)
    }
    if seed is not None:
        obj["seed"] = seed


    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[Done]", out_path.resolve())

if __name__ == "__main__":
    main()
