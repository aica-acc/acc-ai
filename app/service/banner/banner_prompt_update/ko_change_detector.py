# 한글 프롬프트가 베이스라인 대비 바뀌었는지 “판단만” 담당

# app/service/banner/banner_prompt_update/ko_change_detector.py
# -*- coding: utf-8 -*-
"""
ko_change_detector.py
- 역할: "한글 프롬프트가 바뀌었는가?"만 판단하는 최소 모듈
- 책임:
  * 공백/개행/유니코드 스페이스 등 '의미 없는 차이'는 무시하고 비교
  * 순수함수(입력 -> 출력)만 제공 → 단위테스트 용이
- 비고:
  * 파일/터미널 I/O 없음
  * 예외를 던지지 않고, 소비 측(퍼사드)에서 키 누락 등을 먼저 검증한다고 가정
"""

from __future__ import annotations
import re

# 공백 정규표현식 (UNICODE 플래그 사용: 한글·전각 스페이스 등 포함)
_WS = re.compile(r"\s+", re.UNICODE)

def _collapse(s: str) -> str:
    """
    문자열의 '모양만 다른 공백 차이'를 제거하기 위한 유틸.
    - 모든 연속 공백을 1칸으로 축소
    - 앞뒤 공백 제거
    """
    return _WS.sub(" ", (s or "").strip())

def is_ko_banner_prompt_modified(current_ko: str, baseline_ko: str) -> bool:
    """
    한글 프롬프트가 변경되었는지 판단.

    Parameters
    ----------
    current_ko : str
        현재(사용자 편집) 한글 프롬프트
    baseline_ko : str
        직전 기준선(확정분) 한글 프롬프트

    Returns
    -------
    bool
        정규화(collapse) 후 '내용상' 차이가 있으면 True, 아니면 False
    """
    return _collapse(current_ko) != _collapse(baseline_ko)