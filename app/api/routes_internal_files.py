"""
백엔드 전용 내부 파일 API (트러블슈팅 #21).

AI 가 PROMOTION_DIR 아래에 만든 포스터·마스코트 결과를 백엔드가 공유 볼륨 경로로 직접 읽던 것을
HTTP 로 바꾼다. 백엔드는 이 API 로 목록을 보고, 받아 가고, 다 옮기면 지운다.

AI 컨테이너는 포트를 열지 않고, nginx·백엔드도 /internal 을 중계하지 않으므로 브라우저에서는 닿지 않는다.
"""
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.batch import _BATCH
from app.core.config import PROMOTION_DIR

router = APIRouter(prefix="/internal/promotion", tags=["Internal Files"])

_KIND = re.compile(r"^[a-z_]+$")
_NAME = re.compile(r"^[\w.\-]+$")


def _dir(kind: str, batch: Optional[str] = None) -> Path:
    if not _KIND.match(kind):
        raise HTTPException(status_code=400, detail="invalid kind")
    if batch is None:
        return PROMOTION_DIR / kind
    if not _BATCH.match(batch):
        raise HTTPException(status_code=400, detail="invalid batch")
    return PROMOTION_DIR / kind / batch


def _file(kind: str, name: str, batch: Optional[str] = None) -> Path:
    if not _NAME.match(name) or name.startswith("."):
        raise HTTPException(status_code=400, detail="invalid name")
    d = _dir(kind, batch).resolve()
    path = (d / name).resolve()
    if path.parent != d:
        raise HTTPException(status_code=400, detail="invalid name")
    return path


@router.get("/{kind}")
def list_files(kind: str, prefix: str = "", ext: str = ".png", batch: Optional[str] = None):
    """파일명 순 목록. batch 를 주면 그 요청 폴더({kind}/{batch}/)만 본다 (#31)"""
    d = _dir(kind, batch)
    if not d.is_dir():
        return {"files": []}
    names = sorted(p.name for p in d.iterdir() if p.is_file() and p.name.startswith(prefix) and p.name.endswith(ext))
    return {"files": names}


def _send(path: Path):
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path)


def _delete(path: Path):
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    path.unlink()
    # 다 옮긴 요청 폴더({kind}/{batch}/)는 비면 지운다
    if path.parent != PROMOTION_DIR.resolve() and path.parent.parent != PROMOTION_DIR.resolve() and not any(path.parent.iterdir()):
        path.parent.rmdir()
    return {"deleted": path.name}


@router.get("/{kind}/{name}")
def get_file(kind: str, name: str):
    return _send(_file(kind, name))


@router.get("/{kind}/{batch}/{name}")
def get_batch_file(kind: str, batch: str, name: str):
    return _send(_file(kind, name, batch))


@router.delete("/{kind}/{name}")
def delete_file(kind: str, name: str):
    return _delete(_file(kind, name))


@router.delete("/{kind}/{batch}/{name}")
def delete_batch_file(kind: str, batch: str, name: str):
    return _delete(_file(kind, name, batch))
