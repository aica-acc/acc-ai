# -*- coding: utf-8 -*-
# app/service/banner/banner_prompt_update/service_banner_prompt_update.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, List
import os, re

# ───────── OpenAI (필수) ─────────
# 하드코딩/규칙기반 치환 금지: LLM 없으면 에러 처리
try:
    from openai import OpenAI  # openai>=1.x
except Exception as e:
    OpenAI = None

HANGUL_RE = re.compile(r'[\uAC00-\uD7A3]')
Q_ALL_RE = re.compile(r'"([^"]+)"')

def _need_openai() -> OpenAI:
    if OpenAI is None:
        raise RuntimeError("OPENAI 라이브러리가 없습니다. `pip install openai` 후 재시도하세요.")
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN")
    if not key:
        raise RuntimeError("OPENAI_API_KEY(또는 OPENAI_API_TOKEN)이 필요합니다. 하드코딩 없이 KO→EN 동기화를 수행하려면 LLM 키가 필수입니다.")
    return OpenAI(api_key=key)

def _extract_three_lines_from_ko(ko: str) -> Optional[Tuple[str, str, str]]:
    """KO 문자열에서 따옴표로 감싼 마지막 3개 항목(title/date/location)을 뽑는다."""
    if not isinstance(ko, str):
        return None
    items = Q_ALL_RE.findall(ko)
    if len(items) < 3:
        return None
    return tuple(items[-3:])  # (title, date, location)

def _remove_hangul(s: str) -> str:
    return HANGUL_RE.sub("", s or "").strip()

def _chat(client: OpenAI, prompt: str) -> str:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    rsp = client.chat.completions.create(
        model=model,
        messages=[{"role":"user","content": prompt}],
        temperature=0.2,
    )
    out = (rsp.choices[0].message.content or "").strip()
    return out

def _translate_triple_with_llm(client: OpenAI, tko: str, dko: str, lko: str) -> Tuple[str, str, str]:
    # 세 줄 각각 독립 번역(출력에 따옴표 금지)
    def t(line: str) -> str:
        txt = _chat(client, f'Translate to concise natural English. Do not add quotes. Keep numerals/ISO date if present. Text:\n{line}')
        return _remove_hangul(txt.strip().strip('"'))
    return t(tko), t(dko), t(lko)

def _compose_body_from_ko_with_llm(client: OpenAI, ko_block: str, title_en: str) -> str:
    prompt = (
        "Write a clean, production-ready English prompt (2–3 sentences) for generating a wide print banner image. "
        "Strictly avoid any Korean characters. Reflect the season/time/motifs/palette implied by the Korean text. "
        f"Use this exact English festival title in the body if needed: {title_en}. "
        "Do NOT include any quoted constraints or metadata—only the descriptive body."
        "\n\nKorean text:\n" + ko_block
    )
    body = _chat(client, prompt)
    return _remove_hangul(body)

def ensure_prompt_synced_before_generation(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    KO 변경 감지 → LLM으로 EN 본문/3줄을 재구성 → EN 프롬프트 완전 교체.
    - 하드코딩/치환 사전 사용 금지.
    - OPENAI 키 없으면 오류 발생(임의값 주입 금지).
    """
    if not isinstance(job, dict):
        raise TypeError("job must be dict")

    j = dict(job)
    ko = str(j.get("prompt_ko", "") or "")
    ko_base = str(j.get("prompt_ko_baseline", "") or "")
    prev_en = str(j.get("prompt", "") or j.get("prompt_original", "") or "")

    # 변경 없음 → 그대로 통과
    if not ko.strip() or ko.strip() == ko_base.strip():
        return j

    # KO에서 따옴표 3줄 추출 (없으면 변경 베이스만 갱신하고 pass)
    triple = _extract_three_lines_from_ko(ko)
    if not triple:
        j["prompt_ko_baseline"] = ko
        return j

    title_ko, date_ko, loc_ko = triple

    # LLM 필수
    client = _need_openai()

    # 1) 3줄 번역
    title_en, date_en, loc_en = _translate_triple_with_llm(client, title_ko, date_ko, loc_ko)

    # 2) KO 전체 의미를 반영해 EN 설명 본문 생성
    body_en = _compose_body_from_ko_with_llm(client, ko, title_en)
    if not body_en:
        raise RuntimeError("LLM이 본문 생성을 반환하지 않았습니다. 입력 KO를 확인하세요.")

    # 3) 영문 최종 프롬프트 구성 (한글 금지)
    #    - 본문
    #    - 고정 제약 블록(따옴표 3줄) ← 이 부분은 포맷만 고정 (콘텐츠는 LLM 결과 사용)
    constraint = (
        'Place the following text exactly, each on its own line, inside double quotes '
        '(quotes are for parsing only; do not draw the quote marks in the image): '
        f"\"{title_en}\", \"{date_en}\", \"{loc_en}\". "
        "No extra text, no watermarks or logos, no borders or frames."
    )
    en_full = f"{body_en.strip()} {constraint}"

    # 4) 한글 완전 제거 보증
    en_full = _remove_hangul(en_full)

    # 5) 필드 갱신
    if "prompt_original" not in j:
        j["prompt_original"] = prev_en
    j["prompt"] = en_full
    if "prompt_ko_original" not in j:
        j["prompt_ko_original"] = ko_base or ko
    j["prompt_ko_baseline"] = ko

    return j
