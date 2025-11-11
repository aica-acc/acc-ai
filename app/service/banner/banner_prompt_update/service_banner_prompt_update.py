# app/service/banner/service_banner_prompt_update.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Tuple, Dict, Any
from copy import deepcopy
import re

# "2025 12 20-2025 12 21" 같은 형태의 따옴표 포함 날짜 추출
DATE_RE = re.compile(r'"(\d{4}\s+\d{2}\s+\d{2}\s*-\s*\d{4}\s+\d{2}\s+\d{2})"')

def _extract_quoted_date(s: str | None) -> str | None:
    if not isinstance(s, str):
        return None
    m = DATE_RE.search(s)
    return m.group(1) if m else None

def ensure_prompt_synced_before_generation(job: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
    """
    - 한글 prompt 변경 여부를 확인하고, 변경되었으면 영어 prompt 일부(날짜 토큰)를 동기화
    - 반환: (synced_job, changed_bool, reason_str)
    """
    if not isinstance(job, dict):
        return {}, False, "invalid_job"

    j = deepcopy(job)
    ko = j.get("prompt_ko")
    ko_base = j.get("prompt_ko_baseline")

    # ko/baseline 없으면 동기화 스킵
    if not isinstance(ko, str) or not isinstance(ko_base, str):
        return j, False, "no_ko_baseline"

    # 변경 없음
    if ko == ko_base:
        return j, False, "no_diff"

    en = j.get("prompt")
    changed = False
    reasons = []

    # 1) 날짜 토큰 동기화: "YYYY MM DD-YYYY MM DD"
    new_date = _extract_quoted_date(ko)
    old_date = _extract_quoted_date(en)

    if isinstance(en, str) and new_date and old_date and new_date != old_date:
        # 첫 매치만 교체
        en_synced = DATE_RE.sub(f'"{new_date}"', en, count=1)
        j["prompt"] = en_synced
        changed = True
        reasons.append("date_changed")

    # (확장 포인트) 타이틀/장소 등도 숫자 기반이거나 영어로 확정된 값이면 여기서 규칙치환 가능

    # baseline 갱신
    j["prompt_ko_baseline"] = ko

    return j, changed, ",".join(reasons) if reasons else "ko_changed_but_no_en_patch"
