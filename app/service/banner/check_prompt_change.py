# -*- coding: utf-8 -*-
"""
check_prompt_change.py  — 롤링 기준선(prompt_ko_baseline) 사용

규칙
- prompt_ko != prompt_ko_baseline 이면 '수정됨' → prompt_ko로부터 영어 prompt 재조립 → 'prompt' 교체
  → 롤링 기준선이면 prompt_ko_baseline = prompt_ko 로 갱신
- 같으면 '수정 없음' → 파일 무변경
- prompt_original / prompt_ko_original 은 절대 수정하지 않음
- OPENAI_API_KEY 없으면 재조립 불가 → 무변경

실행
python check_prompt_change.py
  1) job JSON 경로
  2) 미리보기(dry-run) 여부
"""

import os, json, re, sys
from pathlib import Path
from typing import Tuple

PHRASE = "Place the following text exactly, each on its own line, inside double quotes"
_ALLOWED_ASCII = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -")

# ---------- I/O ----------
def ask_path(msg: str) -> Path:
    while True:
        raw = input(f"{msg}: ").strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file():
            return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def ask_bool(msg: str, default: bool) -> bool:
    dv = "Y/n" if default else "y/N"
    raw = input(f"{msg} ({dv}): ").strip().lower()
    if not raw: return default
    return raw in ("y","yes","1","true","t")

def info(s): print(s)
def err(s): print("[에러]", s); sys.exit(1)

# ---------- OpenAI ----------
def _ensure_env():
    try:
        from dotenv import load_dotenv, find_dotenv
        env = find_dotenv(usecwd=True)
        if env: load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists(): load_dotenv(local, override=False)
    except Exception:
        pass

def _have_key(): return bool(os.getenv("OPENAI_API_KEY"))

def _chat(system: str, user: str, model: str = None, temperature: float = 0.0) -> str:
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

# ---------- 텍스트 유틸 ----------
def _collapse(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _to_ascii_hyphens(s: str) -> str:
    return (s or "").replace("–","-").replace("—","-").replace("~","-").replace("·"," ")

def _sanitize_ascii_line(s: str) -> str:
    s = _to_ascii_hyphens(s)
    s = re.sub(r'[<>\[\]\(\)\{\}",.\\/|:;*!?@#$%^&_=+`]', " ", s)
    out = []
    for ch in s:
        if ch in _ALLOWED_ASCII: out.append(ch)
        elif ch.isspace(): out.append(" ")
    return _collapse("".join(out))

def _extract_last_three_quoted(text: str):
    items = re.findall(r'"([^"]+)"', text or "", flags=re.DOTALL)
    if len(items) >= 3:
        return items[-3], items[-2], items[-1]
    return None, None, None

def _extract_tail(prompt_en: str) -> str:
    idx = prompt_en.lower().find(PHRASE.lower())
    return prompt_en[idx:].strip() if idx >= 0 else ""

# ---------- 번역기 ----------
def _translate_ko_body_to_en(ko_body: str) -> str:
    _ensure_env()
    if not _have_key(): return ""
    sysmsg = (
        "Translate the Korean banner description (body only, without the quotes block) into English, "
        "USING EXACTLY THREE SENTENCES with these starts: "
        "Sentence 1 starts with 'Ultra-wide print banner for'. "
        "Sentence 2 starts with 'Emphasize'. "
        "Sentence 3 starts with 'Incorporate'. "
        "Use only ASCII characters; professional, compact tone; do not add or remove information."
    )
    en = _chat(sysmsg, ko_body, temperature=0.0)
    en = "".join(ch if ord(ch) < 128 else " " for ch in en)
    return _collapse(en)

def _translate_ko_items_to_en(title_ko: str, date_ko: str, location_ko: str):
    _ensure_env()
    if not _have_key(): return "", "", ""
    sysmsg = (
        "Translate the given Korean festival title, date range, and location into concise English. "
        "Return strict JSON with ASCII-only values and a single ASCII hyphen '-' for ranges: "
        '{"title_en":"...", "date_en":"...", "location_en":"..."} '
        "Do not include any other keys."
    )
    user = json.dumps({"title_ko": title_ko, "date_ko": date_ko, "location_ko": location_ko}, ensure_ascii=False)
    txt = _chat(sysmsg, user, temperature=0.0)
    m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
    if not m: return "", "", ""
    try:
        data = json.loads(m.group(0))
        t = _sanitize_ascii_line(data.get("title_en",""))
        d = _sanitize_ascii_line(data.get("date_en",""))
        l = _sanitize_ascii_line(data.get("location_en",""))
        return t, d, l
    except Exception:
        return "", "", ""

# ---------- 재조립 ----------
def _rebuild_prompt_from_ko(prompt_ko: str, fallback_prompt_en: str) -> str:
    tko, dko, lko = _extract_last_three_quoted(prompt_ko)
    # 따옴표 앞의 한글 본문
    qpos = prompt_ko.find('"')
    body_ko = prompt_ko[:qpos].strip() if qpos != -1 else prompt_ko.strip()

    # 본문 KO→EN (3문장)
    body_en = _translate_ko_body_to_en(body_ko) if body_ko else ""
    if not body_en:
        # 실패 시 기존 본문 유지
        tail = _extract_tail(fallback_prompt_en)
        return fallback_prompt_en if not tail else _collapse(fallback_prompt_en[:len(fallback_prompt_en)-len(tail)])

    # 항목 KO→EN
    ten = den = len_ = ""
    if tko or dko or lko:
        ten, den, len_ = _translate_ko_items_to_en(tko or "", dko or "", lko or "")
        ten  = _sanitize_ascii_line(ten)
        den  = _sanitize_ascii_line(den)
        len_ = _sanitize_ascii_line(len_)

    # 템플릿 조립
    if ten and den and len_:
        quoted = (
            'Place the following text exactly, each on its own line, inside double quotes '
            '(quotes are for parsing only; do not draw the quote marks in the image): '
            f'"{ten}", "{den}", "{len_}". '
            'No extra text, no watermarks or logos, no borders or frames.'
        )
        return _collapse(body_en) + " " + quoted
    else:
        # 항목이 불완전하면 기존 따옴표 블록 유지
        tail = _extract_tail(fallback_prompt_en)
        return _collapse(body_en + " " + tail) if tail else fallback_prompt_en

# ---------- 비대화형 API ----------
def process_job(job: dict, *, rolling_baseline: bool = True) -> Tuple[dict, bool, str]:
    """
    - prompt_ko != prompt_ko_baseline 이면 → prompt_ko 기반으로 영어 prompt 재조립
    - 성공 시 job['prompt'] 교체, rolling_baseline=True면 job['prompt_ko_baseline'] = job['prompt_ko']
    - 변경 없거나 실패/키부족/OPENAI 키 없음 → 그대로 반환
    반환: (job, changed_bool, reason_str)
    """
    for k in ("prompt", "prompt_ko", "prompt_ko_baseline"):
        if k not in job or not isinstance(job[k], str):
            return job, False, f"missing-key:{k}"

    prompt_en = job["prompt"]
    prompt_ko = job["prompt_ko"]
    base_ko   = job["prompt_ko_baseline"]

    if prompt_ko == base_ko:
        return job, False, "no-change"

    _ensure_env()
    if not _have_key():
        return job, False, "no-openai-key"

    new_prompt = _rebuild_prompt_from_ko(prompt_ko, prompt_en)
    if not new_prompt or _collapse(new_prompt) == _collapse(prompt_en):
        return job, False, "rebuild-failed-or-same"

    job["prompt"] = new_prompt
    if rolling_baseline:
        job["prompt_ko_baseline"] = job["prompt_ko"]
    return job, True, "updated"

# ---------- 대화형 실행 ----------
def main():
    print("=== check_prompt_change (rolling baseline: prompt_ko_baseline) ===")
    path = ask_path("1) job JSON 경로 입력")
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        err(f"JSON 로드 실패: {e}")

    dry = ask_bool("2) 미리보기(dry-run)로 실행할까요?", False)

    job2, changed, reason = process_job(job, rolling_baseline=True)

    if not changed:
        print(f"[결과] 변경 없음 ({reason})")
        return

    if dry:
        print("\n----- DRY RUN: 새 prompt 미리보기 -----\n")
        print(job2["prompt"])
        print("\n----- END PREVIEW -----\n")
        return

    try:
        path.write_text(json.dumps(job2, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 저장됨 → {path.resolve()}")
    except Exception as e:
        err(f"저장 실패: {e}")

if __name__ == "__main__":
    main()
