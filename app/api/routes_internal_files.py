"""
백엔드 전용 내부 파일 API (트러블슈팅 #21).

AI 가 PROMOTION_DIR 아래에 만든 포스터·마스코트 결과를 백엔드가 공유 볼륨 경로로 직접 읽던 것을
HTTP 로 바꾼다. 백엔드는 이 API 로 목록을 보고, 받아 가고, 다 옮기면 지운다.

AI 컨테이너는 포트를 열지 않고, nginx·백엔드도 /internal 을 중계하지 않으므로 브라우저에서는 닿지 않는다.
"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import PROMOTION_DIR

router = APIRouter(prefix="/internal/promotion", tags=["Internal Files"])

_KIND = re.compile(r"^[a-z_]+$")
_NAME = re.compile(r"^[\w.\-]+$")


def _dir(kind: str) -> Path:
    if not _KIND.match(kind):
        raise HTTPException(status_code=400, detail="invalid kind")
    return PROMOTION_DIR / kind


def _file(kind: str, name: str) -> Path:
    if not _NAME.match(name) or name.startswith("."):
        raise HTTPException(status_code=400, detail="invalid name")
    path = (_dir(kind) / name).resolve()
    if path.parent != (PROMOTION_DIR / kind).resolve():
        raise HTTPException(status_code=400, detail="invalid name")
    return path


@router.get("/{kind}")
def list_files(kind: str, prefix: str = "", ext: str = ".png"):
    """파일명 순으로 정렬한 목록 ({type}_{시각}_{순번}.png 라서 프롬프트 순서와 짝이 맞는다)"""
    d = _dir(kind)
    if not d.is_dir():
        return {"files": []}
    names = sorted(p.name for p in d.iterdir() if p.is_file() and p.name.startswith(prefix) and p.name.endswith(ext))
    return {"files": names}


@router.get("/{kind}/{name}")
def get_file(kind: str, name: str):
    path = _file(kind, name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path)


@router.delete("/{kind}/{name}")
def delete_file(kind: str, name: str):
    path = _file(kind, name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    path.unlink()
    return {"deleted": name}
