"""
지금 처리 중인 요청의 회원 폴더 (data/promotion/{회원}/{프로젝트}/...).

예전에는 생성기마다 os.getenv("ACC_MEMBER_NO", "M000001") 이나 고정값 "M000001" 을 써서,
모든 회원의 파생물이 M000001 폴더에 저장되었다 (주소에 엉뚱한 회원번호가 보이고, 프로젝트 삭제 때 지워지지 않음).
빌드 요청이 받은 베이스 경로에서 회원 폴더를 읽어 이 요청 동안만 쓴다 (contextvars: 동시에 도는 빌드끼리 섞이지 않음).
"""
import os
import re
from contextvars import ContextVar

_member: ContextVar[str | None] = ContextVar("acc_member_no", default=None)

_FROM_PATH = re.compile(r"/data/promotion/([A-Za-z0-9_-]+)/")


def member_no() -> str:
    return _member.get() or os.getenv("ACC_MEMBER_NO", "M000001")


def use_member_from_path(*paths) -> None:
    """베이스 이미지 경로들 중 처음 찾은 회원 폴더를 이 요청의 회원으로 쓴다"""
    for p in paths:
        m = _FROM_PATH.search(str(p or "").replace("\\", "/"))
        if m:
            _member.set(m.group(1))
            return
