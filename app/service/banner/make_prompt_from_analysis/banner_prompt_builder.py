# -*- coding: utf-8 -*-
"""
banner_prompt_builder.py

- FestivalService.analyze(...) 결과 payload(dict) → Dreamina 3.1 배너 프롬프트 JSON(dict)
- 파일 I/O, 콘솔 입력, main() 없음
- 하드코딩 금지: 입력에 없는 정보 임의 생성 금지, strict=True 시 부족하면 예외
- LLM 키 없으면 한국어 번역은 "" 처리
- orientation 기본값:
    * horizontal -> 3024×544
    * vertical   -> 1008×3024
"""

from __future__ import annotations
import os, re, json, hashlib
from typing import Optional, Dict, Any, List, Literal

# -------------------- 동적 기본값 --------------------
_DEFAULT_SIZE: dict[Literal["horizontal","vertical"], tuple[int,int]] = {
    "horizontal": (3024, 544),
    "vertical":   (1008, 3024),
}
DEFAULT_AR  = "custom"
DEFAULT_RES = "2K"

# (업데이트) 중복 억제 지시를 보다 강하게, 원문 의도 유지
PHRASE = (
    "Render EXACTLY {N} LINES of typography as ONE SINGLE GROUP. "
    "Print each quoted phrase ONCE ONLY. Do not add duplicates, variations, "
    "mirrored or background text, captions, signage, subtitles, or any other words or numbers. "
    "The phrases are provided inside double quotes (quotes are for parsing only; do not draw the quote marks)"
)

# -------------------- env / llm --------------------
def _ensure_env() -> None:
    try:
        from dotenv import load_dotenv, find_dotenv
        env = find_dotenv(usecwd=True)
        if env: load_dotenv(env, override=False)
    except Exception:
        pass

def _have_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))

def _chat(system: str, user: str, *, model: Optional[str], temperature: float = 0.2) -> str:
    mdl = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
        rsp = OpenAI().chat.completions.create(
            model=mdl, temperature=temperature,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}]
        )
        return (rsp.choices[0].message.content or "").strip()
    except Exception:
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            rsp = openai.ChatCompletion.create(
                model=mdl, temperature=temperature,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}]
            )
            return (rsp.choices[0].message["content"] or "").strip()
        except Exception:
            return ""

# -------------------- 텍스트 유틸 --------------------
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -")

def _sanitize_ascii_for_quoted_line(s: str) -> str:
    if not s: return ""
    s = (s.replace("–","-").replace("—","-").replace("~","-").replace("·"," "))
    s = re.sub(r'[<>\[\]\(\)\{\}",.\\/|:;*!?@#$%^&_=+`]', " ", s)
    out = []
    for ch in s:
        out.append(ch if ch in _ALLOWED else " ")
    return re.sub(r"\s+", " ", "".join(out)).strip()

def _normalize_prompt(text: str) -> str:
    t = (text or "").strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            obj = json.loads(t)
            if isinstance(obj, dict) and isinstance(obj.get("prompt"), str):
                t = obj["prompt"]
        except Exception:
            pass
    return " ".join(t.split())

# (추가) 따옴표 라인 중복 제거용 노멀라이저/디듀프
def _norm_for_dedupe(s: str) -> str:
    s = (s or "").lower().strip().strip('"')
    s = s.replace("–","-").replace("—","-").replace("~","-")
    s = re.sub(r"\s+", "", s)           # 공백 제거
    s = re.sub(r"[^a-z0-9\-]", "", s)   # 영문/숫자/하이픈만
    return s

def _dedupe_quoted(lines: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for ln in lines:
        key = _norm_for_dedupe(ln)
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(ln)  # 최초 1회만 보존
    return out

# -------------------- helper --------------------
def _resolve_size(
    width: Optional[int], height: Optional[int],
    orientation: Literal["horizontal","vertical"]
) -> tuple[int,int]:
    if orientation not in _DEFAULT_SIZE:
        raise ValueError("orientation must be 'horizontal' or 'vertical'")
    defsize = _DEFAULT_SIZE[orientation]
    W = int(width) if isinstance(width, int) and width > 0 else defsize[0]
    H = int(height) if isinstance(height, int) and height > 0 else defsize[1]
    if W <= 0 or H <= 0:
        raise ValueError("width/height must be positive integers.")
    return (W, H)

# -------------------- 필드 추출 --------------------
def _fields_from_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    fest = (payload or {}).get("festival", {}) or {}
    p_name = (payload or {}).get("p_name") or ""
    title_raw = fest.get("title") or p_name or ""
    date_raw  = fest.get("date") or fest.get("datetime") or ""
    loc_raw   = fest.get("location") or ""

    date_tmp = str(date_raw)
    date_tmp = date_tmp.replace("~","-").replace("–","-").replace("—","-").replace("/", "-")
    date_tmp = re.sub(r"[^\dA-Za-z\-\s\.]", " ", date_tmp)
    date_tmp = re.sub(r"\s+", " ", date_tmp).strip()

    return {
        "title_en":      _sanitize_ascii_for_quoted_line(title_raw),
        "date_range_en": _sanitize_ascii_for_quoted_line(date_tmp),
        "location_en":   _sanitize_ascii_for_quoted_line(loc_raw),
    }

def _llm_extract_fields_en(payload: Dict[str, Any], *, use_pre_llm: bool, llm_model: Optional[str]) -> Dict[str, str]:
    _ensure_env()
    if not (use_pre_llm and _have_key()):
        return _fields_from_payload(payload)

    system_msg = (
        "From the provided JSON, RETURN a minimal JSON with keys: title_en, date_range_en, location_en. "
        "ASCII only; use single '-' for ranges; do not invent values."
    )
    txt = _chat(system_msg, json.dumps(payload, ensure_ascii=False), model=llm_model, temperature=0.1)
    if not txt:
        return _fields_from_payload(payload)

    try:
        if not txt.strip().startswith("{"):
            m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
            if m: txt = m.group(0)
        data = json.loads(txt)
        out = {
            "title_en":      _sanitize_ascii_for_quoted_line(data.get("title_en","")),
            "date_range_en": _sanitize_ascii_for_quoted_line(data.get("date_range_en","")),
            "location_en":   _sanitize_ascii_for_quoted_line(data.get("location_en","")),
        }
        if not (out["title_en"] or out["date_range_en"] or out["location_en"]):
            return _fields_from_payload(payload)
        return out
    except Exception:
        return _fields_from_payload(payload)

# -------------------- 본문(3문장) --------------------
def _compose_body_en(
    payload: Dict[str, Any],
    title_en_hint: str,
    *,
    use_pre_llm: bool,
    llm_model: Optional[str],
    strict: bool
) -> str:
    _ensure_env()

    if use_pre_llm and _have_key():
        if strict and not title_en_hint:
            raise ValueError("Title missing for body composition (strict mode).")
        system_msg = (
            "Write EXACTLY THREE compact ENGLISH sentences for a LONG HORIZONTAL FESTIVAL BANNER BACKGROUND. "
            "Sentence 1 MUST begin with: 'Ultra-wide print banner for the {TITLE}, set against a ...' "
            "Sentence 2 MUST begin with: 'Emphasize ...' "
            "Sentence 3 MUST begin with: 'Incorporate ...' "
            "ASCII only. Do not invent facts; derive from the payload semantics."
        )
        payload2 = {"payload": payload, "title_en_hint": title_en_hint}
        raw = _chat(system_msg, json.dumps(payload2, ensure_ascii=False), model=llm_model, temperature=0.2)
        text = _normalize_prompt(raw).replace("{TITLE}", title_en_hint)
        text = "".join(ch if ord(ch) < 128 else " " for ch in text)
        text = re.sub(r"\s+", " ", text).strip()
        if strict and not text:
            raise ValueError("LLM body composition failed (strict mode).")
        return text

    # LLM 미사용: 입력 토큰만 사용
    fest = (payload or {}).get("festival", {}) or {}
    theme = " ".join([str(fest.get("theme") or ""), str(fest.get("summary") or "")])
    vk: List[str] = fest.get("visual_keywords") or []

    def _tok(s: str) -> List[str]:
        return re.findall(r"[A-Za-z]+", _sanitize_ascii_for_quoted_line(s))

    if strict and not title_en_hint:
        raise ValueError("Title missing for body composition (strict mode).")

    tokens: List[str] = []
    for x in vk:
        tokens += _tok(str(x))
    tokens += _tok(theme)
    tokens = [t.lower() for t in tokens if t]
    uniq: List[str] = []
    for t in tokens:
        if t not in uniq:
            uniq.append(t)

    if strict and not uniq:
        raise ValueError("Insufficient descriptive tokens in payload to compose body (strict mode).")

    scene     = ", ".join(uniq[:3]) if uniq else ""
    emphasize = ", ".join(uniq[3:6]) if len(uniq) > 3 else ""
    include   = ", ".join(uniq[6:9]) if len(uniq) > 6 else ""

    parts = []
    parts.append(f"Ultra-wide print banner for the {title_en_hint}, set against a {scene}.")
    if emphasize: parts.append(f"Emphasize {emphasize}.")
    if include:   parts.append(f"Incorporate {include}.")
    text = _normalize_prompt(" ".join(parts))
    if strict and not text:
        raise ValueError("Body composition produced empty text (strict mode).")
    return text

# -------------------- 한글 번역 --------------------
def _translate_en_to_ko(prompt_en: str, *, use_pre_llm: bool, llm_model: Optional[str]) -> str:
    _ensure_env()
    if not (use_pre_llm and _have_key()):
        return ""
    sysmsg = (
        "Translate the following English prompt for an image-generation model into natural Korean for user display. "
        "Preserve structure and content exactly; output only the translation."
    )
    return _chat(sysmsg, prompt_en, model=llm_model, temperature=0.0) or ""

# -------------------- Public API --------------------
def generate_banner_prompt_from_analysis(
    analysis: Dict[str, Any],
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    orientation: Literal["horizontal","vertical"] = "horizontal",
    aspect_ratio: str = DEFAULT_AR,
    resolution: str = DEFAULT_RES,
    use_pre_llm: bool = True,
    seed: Optional[int] = None,
    llm_model: Optional[str] = None,
    strict: bool = True
) -> Dict[str, Any]:
    """
    분석 payload(dict) → Dreamina 3.1 배너 프롬프트 JSON(dict)
    - width/height 미지정 시 orientation에 맞는 기본값 자동 적용
    - strict=True: 필요한 따옴표 라인/본문 토큰 부족 시 예외
    """
    # 0) 해상도 결정
    W, H = _resolve_size(width, height, orientation)

    # 1) 따옴표 라인
    fields = _llm_extract_fields_en(analysis, use_pre_llm=use_pre_llm, llm_model=llm_model)
    quoted: List[str] = []
    if fields.get("title_en"):      quoted.append(f"\"{fields['title_en']}\"")
    if fields.get("date_range_en"): quoted.append(f"\"{fields['date_range_en']}\"")
    if fields.get("location_en"):   quoted.append(f"\"{fields['location_en']}\"")

    # (업데이트) 같은 내용이 여러 번 들어온 경우 1회만 보존
    quoted = _dedupe_quoted(quoted)

    if strict and not quoted:
        raise ValueError("Required quoted lines missing (title/date/location).")

    # 2) 본문
    title_hint = fields.get("title_en", "")
    body_en = _compose_body_en(
        analysis, title_hint, use_pre_llm=use_pre_llm, llm_model=llm_model, strict=strict
    )

    # 3) tail (업데이트: 정확히 N줄, 중복 금지, 배경/사물 글씨 금지 명시)
    N = len(quoted)
    tail = (
        " " + PHRASE.format(N=N) + ": " + ", ".join(quoted) +
        ". No extra text anywhere, no repetitions or duplicate titles, "
        "no watermarks or logos, no borders or frames."
    )
    prompt_en = _normalize_prompt(body_en + " " + tail)

    # 4) ko
    prompt_ko_auto = _translate_en_to_ko(prompt_en, use_pre_llm=use_pre_llm, llm_model=llm_model)

    # 5) hash
    prompt_en_sha256 = hashlib.sha256(prompt_en.encode("utf-8")).hexdigest()

    # 6) 결과
    out: Dict[str, Any] = {
        "width": W,
        "height": H,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "use_pre_llm": use_pre_llm,
        "prompt_original": prompt_en,
        "prompt": prompt_en,
        "prompt_en_sha256": prompt_en_sha256,
        "prompt_ko_original": prompt_ko_auto,
        "prompt_ko": prompt_ko_auto,
        "prompt_ko_baseline": prompt_ko_auto,
    }
    if seed is not None:
        out["seed"] = int(seed)
    return out
