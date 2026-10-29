"""
백엔드와 주고받는 생성물 파일 (트러블슈팅 #33).

예전에는 백엔드와 AI 가 같은 폴더(FRONT_PROJECT_ROOT/public)를 마운트하고 파일 경로를 주고받았다.
그러면 두 서버를 다른 PC 로 나눌 수 없다. FILES_MODE 로 고른다.

  FILES_MODE=shared (기본) : 지금처럼 같은 폴더. fetch·publish 는 아무것도 하지 않는다
  FILES_MODE=http          : AI 는 자기 폴더를 쓰고, 입력은 백엔드에서 받아 오고(fetch) 결과는 올려 보낸다(publish).
                             BACKEND_INTERNAL_URL, INTERNAL_TOKEN 필요 (백엔드 /internal/files)

경로는 DB 에 저장하는 웹 경로 형식(data/promotion/{회원}/{프로젝트}/...)으로 주고받는다.
"""
import os
from pathlib import Path
from typing import Optional

import requests

FILES_MODE = os.getenv("FILES_MODE", "shared").strip().lower()
BACKEND_INTERNAL_URL = os.getenv("BACKEND_INTERNAL_URL", "http://backend:8081").rstrip("/")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")
_MARK = "data/promotion/"


def public_root() -> Path:
    return Path(os.getenv("FRONT_PROJECT_ROOT") or "") / "public"


def rel_of(path_or_url: Optional[str]) -> Optional[str]:
    """…/data/promotion/… 형태면 data/promotion/ 부터의 상대 경로, 아니면 None"""
    if not path_or_url:
        return None
    s = str(path_or_url).replace("\\", "/")
    i = s.find(_MARK)
    return s[i:] if i >= 0 else None


def _headers():
    return {"X-Internal-Token": INTERNAL_TOKEN}


def fetch(path_or_url: Optional[str]) -> Optional[str]:
    """
    입력 파일을 이 서버의 로컬 경로로. http 모드에서 로컬에 없으면 백엔드에서 받아 둔다.
    data/promotion 경로가 아니거나(외부 URL, AI 자체 파일) shared 모드면 그대로 돌려준다.
    """
    rel = rel_of(path_or_url)
    if FILES_MODE != "http" or rel is None or str(path_or_url).startswith(("http://", "https://")):
        return path_or_url
    local = public_root() / rel
    if not local.exists():
        res = requests.get(f"{BACKEND_INTERNAL_URL}/internal/files", params={"path": rel}, headers=_headers(), timeout=60)
        res.raise_for_status()
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(res.content)
        print(f"[shared_files] 백엔드에서 받음: {rel}")
    return str(local)


def publish(path: Optional[str]) -> None:
    """만든 결과(data/promotion/…)를 백엔드에 올린다. shared 모드면 이미 같은 폴더라 하지 않는다"""
    rel = rel_of(path)
    if FILES_MODE != "http" or rel is None:
        return
    local = public_root() / rel
    with open(local, "rb") as f:
        res = requests.put(f"{BACKEND_INTERNAL_URL}/internal/files", params={"path": rel}, headers=_headers(),
                           data=f, timeout=300)
    res.raise_for_status()
    print(f"[shared_files] 백엔드로 보냄: {rel}")
