# -*- coding: utf-8 -*-
"""
banner_prompt_updater.py (refactor: 작은 함수로 분해)
- 'KO 프롬프트가 변경된 상황'에서 호출되어 EN 프롬프트를 갱신하고(성공 시),
  정책에 따라 baseline(prompt_ko_baseline)을 최신 KO로 굴려서 갱신.

핵심 분해:
  A) build_en_prompt_from_ko()   ← KO → EN(본문 3문장) + tail(따옴표 3줄 완비 시)
  B) update_ko_baseline()        ← 롤링 정책에 따라 baseline 갱신
  C) apply_banner_prompt_update()← 오케스트레이션(짧음)

I/O 금지: 파일/터미널 입출력 없음. 예외는 삼키고 'reason' 코드로만 보고.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import os, re, json

# --------------------------------------------------------------------
# EN 프롬프트에서 따옴표 블록(3줄)을 안내하는 '고정 사양' 문구
PHRASE = "Place the following text exactly, each on its own line, inside double quotes"
# --------------------------------------------------------------------

# =========================
# 공통 유틸 (짧고 단순)
# =========================

_WS = re.compile(r"\s+")

def _collapse(s: str) -> str:
    """연속 공백을 1칸으로 줄이고 앞뒤 공백 제거."""
    return _WS.sub(" ", (s or "").strip())

def _split_ko_body(text: str) -> str:
    """처음 큰따옴표 이전까지를 본문으로 간주하여 KO 본문 추출."""
    qpos = (text or "").find('"')
    return text[:qpos].strip() if qpos != -1 else (text or "").strip()

def _extract_ko_quote_items(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """KO 텍스트에서 "..."로 감싼 항목들 중 마지막 3개(title/date/location) 추출."""
    items = re.findall(r'"([^"]+)"', text or "", flags=re.DOTALL)
    if len(items) >= 3:
        return items[-3], items[-2], items[-1]
    return None, None, None

def _extract_existing_en_tail(fallback_en: str) -> str:
    """기존 EN 프롬프트에서 PHRASE 이하 tail만 추출(없으면 빈 문자열)."""
    idx = (fallback_en or "").lower().find(PHRASE.lower())
    return fallback_en[idx:].strip() if (idx is not None and idx >= 0) else ""

def _make_en_tail_from_items(title_en: str, date_en: str, location_en: str) -> str:
    """EN 따옴표 3줄 tail 템플릿(사양 고정). 주의: 축제 고유 텍스트 하드코딩 금지."""
    return (
        'Place the following text exactly, each on its own line, inside double quotes '
        '(quotes are for parsing only; do not draw the quote marks in the image): '
        f'"{title_en}", "{date_en}", "{location_en}". '
        'No extra text, no watermarks or logos, no borders or frames.'
    )

# =========================
# 얇은 LLM 어댑터
# =========================

class _OpenAILLM:
    """
    외부 LLM 호출 캡슐화(새 SDK 우선 → 구 SDK 폴백).
    - available(): OPENAI_API_KEY 존재 여부
    - body_ko_to_en(): KO 본문 → EN 3문장(문장 시작 고정)
    - items_ko_to_en(): KO 따옴표 3줄 → EN (엄격 JSON 파싱)
    """

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

    # ---- 상태 ----
    def available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    # ---- 내부 채팅 호출 ----
    def _chat(self, system: str, user: str, temperature: float = 0.0) -> str:
        try:
            from openai import OpenAI  # 새 SDK
            rsp = OpenAI().chat.completions.create(
                model=self.model, temperature=temperature,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}]
            )
            return (rsp.choices[0].message.content or "").strip()
        except Exception:
            try:
                import openai  # 구 SDK
                openai.api_key = os.getenv("OPENAI_API_KEY")
                rsp = openai.ChatCompletion.create(
                    model=self.model, temperature=temperature,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}]
                )
                return (rsp.choices[0].message["content"] or "").strip()
            except Exception:
                return ""

    # ---- KO → EN: 본문 3문장 ----
    def body_ko_to_en(self, ko_body: str) -> str:
        """
        EN 본문 3문장 규칙 강제:
          1) Ultra-wide print banner for ...
          2) Emphasize ...
          3) Incorporate ...
        (ASCII only, 정보 추가/삭제 금지)
        """
        sysmsg = (
            "Translate the Korean banner description (body only) into English, "
            "USING EXACTLY THREE SENTENCES with these starts: "
            "Sentence 1 starts with 'Ultra-wide print banner for'. "
            "Sentence 2 starts with 'Emphasize'. "
            "Sentence 3 starts with 'Incorporate'. "
            "Use ASCII only; professional and concise; do not add or remove information."
        )
        en = self._chat(sysmsg, ko_body, temperature=0.0)
        en = "".join(ch if ord(ch) < 128 else " " for ch in (en or ""))
        return _collapse(en)

    # ---- KO → EN: 따옴표 3줄(JSON) ----
    def items_ko_to_en(self, title_ko: str, date_ko: str, location_ko: str) -> Tuple[str, str, str]:
        """
        {"title_en":"...","date_en":"...","location_en":"..."} 만 허용.
        실패 시 ("","","") 반환하여 상위에서 '기존 tail 재사용'으로 분기.
        """
        sysmsg = (
            "Translate the given Korean festival title, date range, and location into concise English. "
            "Return strict JSON with ASCII-only values and a single ASCII hyphen '-' for ranges: "
            '{"title_en":"...", "date_en":"...", "location_en":"..."} '
            "No other keys."
        )
        payload = json.dumps(
            {"title_ko": title_ko or "", "date_ko": date_ko or "", "location_ko": location_ko or ""},
            ensure_ascii=False
        )
        txt = self._chat(sysmsg, payload, temperature=0.0)
        m = re.search(r"\{.*\}", txt or "", flags=re.DOTALL)
        if not m:
            return "", "", ""
        try:
            data = json.loads(m.group(0))
            return (_collapse(data.get("title_en", "")),
                    _collapse(data.get("date_en", "")),
                    _collapse(data.get("location_en", "")))
        except Exception:
            return "", "", ""

# =========================
# A) KO → EN 재구성 (짧은 조립)
# =========================

def build_en_prompt_from_ko(prompt_ko: str, fallback_en: str, *, llm: _OpenAILLM) -> str:
    """
    KO 프롬프트를 기반으로 EN 배너 프롬프트를 '재구성'한다.
    1) KO 본문 → EN 3문장 변환 (실패 시 fallback_en 반환)
    2) KO의 따옴표 3줄이 완비되면 EN으로 번역하여 새 tail 구성
       - 불완비면 기존 EN tail을 재사용
    """
    # 1) KO 본문 → EN 3문장
    body_ko = _split_ko_body(prompt_ko)
    body_en = llm.body_ko_to_en(body_ko) if body_ko else ""
    if not body_en:
        return fallback_en  # 본문 변환 실패: 안전하게 기존 EN 그대로 유지

    # 2) 따옴표 3줄 → EN tail (완비 시)
    tko, dko, lko = _extract_ko_quote_items(prompt_ko)
    if all([tko, dko, lko]):
        ten, den, len_ = llm.items_ko_to_en(tko, dko, lko)
        if ten and den and len_:
            tail_en = _make_en_tail_from_items(ten, den, len_)
            return _collapse(f"{body_en} {tail_en}")

    # 3) 불완비 → 기존 tail 재사용
    old_tail = _extract_existing_en_tail(fallback_en)
    return _collapse(f"{body_en} {old_tail}") if old_tail else body_en

# =========================
# B) 베이스라인 갱신 (단일 책임)
# =========================

def update_ko_baseline(job: Dict[str, Any], *, enable: bool) -> None:
    """롤링 정책이 켜져 있으면 baseline을 현재 KO로 치환."""
    if enable:
        job["prompt_ko_baseline"] = job["prompt_ko"]

# =========================
# C) 퍼사드가 부르는 오케스트레이션(짧음)
# =========================

def apply_banner_prompt_update(job: Dict[str, Any],
                               *,
                               rolling_baseline: bool = True,
                               llm: Optional[object] = None) -> Dict[str, Any]:
    """
    퍼사드에서 'KO 변경이 확정'된 상황에서 호출.
    - LLM 키 없음 → no-openai-key
    - 재구성 실패/동일 → rebuild-failed-or-same
    - 성공 → EN 교체 + (옵션) baseline 롤링
    """
    # 0) LLM 준비/가용성 확인
    llm = llm or _OpenAILLM()
    if not getattr(llm, "available", lambda: False)():
        return {"ok": True, "changed": False, "reason": "no-openai-key", "job": job}

    # 1) KO→EN 재구성 (A)
    new_en = build_en_prompt_from_ko(job["prompt_ko"], job["prompt"], llm=llm)
    if not new_en or _collapse(new_en) == _collapse(job["prompt"]):
        return {"ok": True, "changed": False, "reason": "rebuild-failed-or-same", "job": job}

    # 2) 반영 + baseline 롤링(B)
    job2 = dict(job)
    job2["prompt"] = new_en
    update_ko_baseline(job2, enable=rolling_baseline)

    return {"ok": True, "changed": True, "reason": "updated", "job": job2}
