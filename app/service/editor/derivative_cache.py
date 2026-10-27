"""
프로젝트별 파생물 기록: "어떤 유형을 어떤 베이스 이미지로 만들었는지".

파생 만들기를 다시 할 때 같은 베이스로 이미 만든 유형은 다시 생성하지 않고 재사용한다 (외부 API 비용 절감).
베이스(포스터/마스코트)를 바꾸면 다시 만든다.

  - 현수막·광고 계열(POHS): 빌드 실행 폴더(editor/{run}/before_image, before_data)에 결과가 생긴다.
    → 이전 실행 폴더의 두 파일을 새 실행 폴더로 복사한다.
  - 그 밖(로고·표지판·굿즈·카드뉴스 등): 프로젝트별 고정 경로에 저장되고 결과 dict 를 돌려준다.
    → 기록해 둔 결과 dict 를 그대로 쓴다 (파일이 남아 있을 때만).

기록 파일: {EDITOR_ROOT_DIR}/projects/{pNo}.json
"""
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Optional

from app.core.config import EDITOR_ROOT_DIR

_lock = threading.Lock()


def _manifest_path(p_no: int) -> Path:
    return Path(EDITOR_ROOT_DIR) / "projects" / f"{p_no}.json"


def _load(p_no: int) -> dict:
    p = _manifest_path(p_no)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _base_key(url: Optional[str]) -> str:
    # 같은 파일을 절대 경로/웹 경로로 다르게 넘겨도 같은 베이스로 본다
    u = (url or "").replace("\\", "/")
    return u.split("/data/promotion/", 1)[-1] if "/data/promotion/" in u else u


def _local_file(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    p = Path(path.replace("\\", "/"))
    if p.is_absolute() and p.exists():
        return p
    rel = str(p).split("/public/", 1)[-1].lstrip("/")
    cand = Path(os.getenv("FRONT_PROJECT_ROOT") or "") / "public" / rel
    return cand if cand.exists() else None


def find(p_no: int, t: str, base_url: Optional[str]) -> Optional[dict]:
    """같은 베이스로 만든 기록이 있고 결과 파일이 남아 있으면 그 기록을 돌려준다."""
    with _lock:
        entry = _load(p_no).get(t)
    if not entry or entry.get("base") != _base_key(base_url):
        return None
    if "run_id" in entry:
        run_dir = Path(EDITOR_ROOT_DIR) / str(entry["run_id"])
        if not (run_dir / "before_image" / f"{t}.png").exists():
            return None
    elif not _local_file((entry.get("result") or {}).get("db_file_path")):
        return None
    return entry


def reuse_pohs(entry: dict, t: str, run_id: int) -> None:
    """이전 실행 폴더의 현수막·광고 결과를 새 실행 폴더로 복사한다."""
    src = Path(EDITOR_ROOT_DIR) / str(entry["run_id"])
    dst = Path(EDITOR_ROOT_DIR) / str(run_id)
    for sub, ext in (("before_image", "png"), ("before_data", "json")):
        s = src / sub / f"{t}.{ext}"
        if s.exists():
            (dst / sub).mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / sub / s.name)


def save(p_no: int, t: str, base_url: Optional[str], *, run_id: Optional[int] = None,
         result: Optional[dict] = None) -> None:
    with _lock:
        data = _load(p_no)
        entry = {"base": _base_key(base_url)}
        if run_id is not None:
            entry["run_id"] = run_id
        if result is not None:
            entry["result"] = result
        data[t] = entry
        path = _manifest_path(p_no)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_entries(p_no: int) -> dict:
    """이 프로젝트에서 이미 만든 파생물: {유형: 만든 베이스(…/data/promotion/ 이후 경로)}. 결과 파일이 남은 것만."""
    with _lock:
        data = _load(p_no)
    out = {}
    for t, entry in data.items():
        base = entry.get("base") or ""
        # 저장된 base 는 이미 정규화된 키이므로 같은 형태로 넘겨 확인한다
        if find(p_no, t, "/data/promotion/" + base) is not None:
            out[t] = base
    return out
