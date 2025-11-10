# 퍼사드 (백엔드에선 이걸 호출한다고함)
# -*- coding: utf-8 -*-
"""
service_banner_prompt_update.py (Facade)
- 백엔드(스프링)에서 이 파일의 퍼사드 함수 'banner_prompt_update_if_ko_changed'만 호출하면 됨.
- 역할: 입력 검증 → KO 변경감지 → 변경된 경우에만 업데이트 로직 위임 → 결과 그대로 반환
- I/O 없음(파일/터미널). dict in / dict out.

입력(인자):
  job: dict (필수 키 3개만 요구)
    - "prompt"             : str  # 현재 영어 프롬프트(이미지 생성에 실제로 사용됨)
    - "prompt_ko"          : str  # 사용자에게 보여주는/수정되는 한글 프롬프트
    - "prompt_ko_baseline" : str  # 직전 기준선(확정본) 한글 프롬프트
  rolling_baseline: bool = True
    - True이면, 업데이트 성공 시 baseline을 현재 KO로 '굴려서' 갱신
  llm: object = None
    - (선택) 외부에서 LLM 더블/모킹을 주입할 때 사용. None이면 내부 기본 어댑터 사용

출력(반환):
  {
    "ok": bool,
    "changed": bool,      # 영어 프롬프트가 실제로 바뀌었는지
    "reason": str,        # "missing-key:...", "no-change", "no-openai-key",
                          # "rebuild-failed-or-same", "updated"
    "job": dict           # 성공 시 'prompt' 교체, rolling_baseline=True면 'prompt_ko_baseline'도 교체
  }

주의:
- 여기서는 '입력 유효성/분기/위임'만 담당한다. 실제 갱신 로직은 banner_prompt_updater.py에 캡슐화.
"""

from __future__ import annotations
from typing import Dict, Any, Optional

# 변경 감지(완료된 모듈)
from .ko_change_detector import is_ko_banner_prompt_modified
# 변경 발생 시 갱신(LLM 호출 포함)
from .banner_prompt_updater import apply_banner_prompt_update


def banner_prompt_update_if_ko_changed(
    job: Dict[str, str],
    *,
    rolling_baseline: bool = True,
    llm: Optional[object] = None,
) -> Dict[str, Any]:
    """
    퍼사드(백엔드에서 호출). KO가 바뀌었을 때만 EN 프롬프트를 갱신한다.
    - 파일/터미널 I/O 없음
    - 예외를 던지지 않고 항상 dict로 결과를 반환(컨트롤러에서 그대로 JSON 응답 가능)
    """
    # 0) 필수 키 검증: 세 키 모두 '문자열'이어야 한다.
    required_keys = ("prompt", "prompt_ko", "prompt_ko_baseline")
    for k in required_keys:
        if not isinstance(job.get(k), str):
            # 어떤 키가 비어있거나 타입이 다르면 즉시 실패 사유를 반환
            return {"ok": False, "changed": False, "reason": f"missing-key:{k}", "job": job}

    # 1) KO 프롬프트 변경 여부 확인 (의미 없는 공백 차이는 무시)
    if not is_ko_banner_prompt_modified(job["prompt_ko"], job["prompt_ko_baseline"]):
        # 바뀐 게 없다면 아무것도 하지 않고 종료
        return {"ok": True, "changed": False, "reason": "no-change", "job": job}

    # 2) 변경됨 → 실제 갱신 로직으로 위임
    #    - 내부에서 OPENAI_API_KEY 여부를 확인하고,
    #      KO→EN 재구성 실패/동일 여부를 판단한 뒤 적절한 reason과 함께 반환한다.
    return apply_banner_prompt_update(
        job,
        rolling_baseline=rolling_baseline,
        llm=llm,
    )
