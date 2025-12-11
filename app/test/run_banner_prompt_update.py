# -*- coding: utf-8 -*-
"""
app/test/run_banner_prompt_update.py
- Facade: service_banner_prompt_update.banner_prompt_update_if_ko_changed 를 케이스별로 검증
- .env의 OPENAI_API_KEY 사용(실패 시 reason 코드로 확인 가능)
- 입력 job/출력 전체 JSON을 보기 좋게 프린트
"""

from __future__ import annotations
import os, sys, json
from typing import Dict, Any

# 프로젝트 루트에서 실행한다고 가정 (루트에 app/ 폴더가 보여야 함)
ROOT = os.path.abspath(".")
if os.path.isdir(os.path.join(ROOT, "app")) and ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# .env 로드(없어도 통과)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

PHRASE = "Place the following text exactly, each on its own line, inside double quotes"

from app.service.banner.banner_prompt_update.service_banner_prompt_update import (
    banner_prompt_update_if_ko_changed
)

def show_case(title: str, job: Dict[str, Any], rolling_baseline: bool = True):
    print("\n" + "="*88)
    print(f"[CASE] {title}  |  rolling={rolling_baseline}  |  OPENAI={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT-SET'}")
    print("- INPUT job:")
    print(json.dumps(job, ensure_ascii=False, indent=2))

    res = banner_prompt_update_if_ko_changed(job, rolling_baseline=rolling_baseline)
    print("- OUTPUT:")
    print(json.dumps(res, ensure_ascii=False, indent=2))

    # 핵심 확인 포인트
    print(f"[RESULT] ok={res.get('ok')}  changed={res.get('changed')}  reason={res.get('reason')}")
    if res.get("changed"):
        new_en = res["job"]["prompt"]
        print("[RESULT] updated EN prompt (head 200 chars):")
        print(new_en[:200] + ("..." if len(new_en) > 200 else ""))

def main():
    # 1) 변경 + 따옴표 3줄 완비 → 새 영문 본문 + 새 영문 tail 기대
    old_en = (
        "Ultra-wide print banner for OLD. Emphasize OLD. Incorporate OLD. "
        f"{PHRASE} (quotes are for parsing only; do not draw the quote marks in the image): "
        "\"Old Title\", \"Dec 1-2 2025\", \"Oldtown\". "
        "No extra text, no watermarks or logos, no borders or frames."
    )
    job_changed_quotes = {
        "prompt": old_en,
        "prompt_ko": "울트라 와이드 배너 본문(수정본). \"제7회 담양산타축제\" \"2025-12-03~12-04\" \"담양\"",
        "prompt_ko_baseline": "직전 확정본 KO와는 다름"
    }
    show_case("Changed + Quotes Complete", job_changed_quotes, rolling_baseline=True)

    # 2) 변경 + 따옴표 불완비 → 새 영문 본문 + 기존 tail 재사용 기대
    job_changed_no_quotes = {
        "prompt": old_en,
        "prompt_ko": "울트라 와이드 배너 본문(수정본, 따옴표 불완비 테스트)",
        "prompt_ko_baseline": "직전 확정본 KO와는 다름"
    }
    show_case("Changed + Quotes Incomplete", job_changed_no_quotes, rolling_baseline=False)

    # 3) 변경 없음 → no-change
    job_no_change = {
        "prompt": "EN stays same",
        "prompt_ko": "한글 동일   \n   문장   ",  # 공백만 다르게
        "prompt_ko_baseline": "한글 동일 문장"
    }
    show_case("No Change (KO == baseline)", job_no_change, rolling_baseline=True)

    # 4) 키 누락 → missing-key
    job_missing_key = {
        # "prompt": "...",  # 의도적으로 누락
        "prompt_ko": "무언가 수정본",
        "prompt_ko_baseline": "무언가 기준선"
    }
    show_case("Missing Key (error)", job_missing_key, rolling_baseline=True)

if __name__ == "__main__":
    main()
