# -*- coding: utf-8 -*-
# app/service/banner/make_banner_from_prompt/banner_builder.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple, Union, Literal
from pathlib import Path
import os, time, base64, re

import requests

try:
    import replicate
except Exception as e:
    raise SystemExit("[에러] 'replicate' 모듈이 없습니다.  `pip install replicate`") from e

DEFAULT_MODEL = "bytedance/dreamina-3.1"
MIN_WH = 512
MAX_WH = 3024  # Dreamina 보수 범위

def _env_model() -> str:
    m = os.getenv("REPLICATE_MODEL", "").strip().strip('"').strip("'")
    return m or DEFAULT_MODEL

def _require_token():
    tok = os.getenv("REPLICATE_API_TOKEN")
    if not tok:
        raise RuntimeError("REPLICATE_API_TOKEN이 설정되지 않았습니다 (.env 또는 환경변수).")
    os.environ["REPLICATE_API_TOKEN"] = tok

def _default_save_dir() -> Path:
    return Path(os.getenv("BANNER_SAVE_DIR", "C:/final_project/ACC/assets/banners"))

def _clamp(v: int) -> int:
    return max(MIN_WH, min(MAX_WH, int(v)))

def _infer_ext_from_bytes(buf: bytes) -> str:
    if buf.startswith(b"\xff\xd8"): return ".jpg"
    if buf.startswith(b"\x89PNG"):  return ".png"
    return ".jpg"

def _nowtag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def _ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def _safe_prefix(prefix: Optional[str]) -> str:
    if not prefix: return "banner"
    base = re.sub(r"[^\w\s\uAC00-\uD7A3-]", "", prefix).strip()
    base = re.sub(r"\s+", "_", base)
    return base[:50] if base else "banner"

def _norm_job(job: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(job, dict):
        raise TypeError("job must be dict")
    if "prompt" not in job or not isinstance(job["prompt"], str) or not job["prompt"].strip():
        raise ValueError("job['prompt']가 문자열로 필요합니다.")
    j = dict(job)
    j.setdefault("aspect_ratio", "custom")
    j.setdefault("resolution", "2K")
    j.setdefault("use_pre_llm", True)
    j["width"]  = _clamp(int(j.get("width", 3024)))
    j["height"] = _clamp(int(j.get("height", 544)))
    return j

def _build_inputs(job: Dict[str, Any]) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {
        "prompt": job["prompt"],
        "aspect_ratio": job.get("aspect_ratio", "custom"),
        "width": int(job["width"]),
        "height": int(job["height"]),
        "resolution": job.get("resolution", "2K"),
        "use_pre_llm": bool(job.get("use_pre_llm", True)),
    }
    seed = job.get("seed", None)
    if seed is not None:
        inputs["seed"] = int(seed)
    return inputs

def _to_url_or_bytes(item: Any) -> Tuple[Optional[str], Optional[bytes]]:
    # bytes류
    if isinstance(item, (bytes, bytearray)): return (None, bytes(item))
    # dict에서 url/bytes 추출
    if isinstance(item, dict):
        u = item.get("url") or item.get("image") or item.get("href")
        if isinstance(u, str) and u.startswith(("http://", "https://")): return (u, None)
        b = item.get("bytes") or item.get("data")
        if isinstance(b, (bytes, bytearray)): return (None, bytes(b))
        if isinstance(b, str) and b.startswith("data:image/"):
            try:
                _, b64 = b.split(",", 1)
                return (None, base64.b64decode(b64))
            except Exception:
                return (None, b.encode("utf-8", "ignore"))
    # str → URL/data-url/bytes-repr
    if isinstance(item, str):
        s = item.strip()
        if s.startswith(("http://", "https://")): return (s, None)
        if s.startswith("data:image/"):
            try:
                _, b64 = s.split(",", 1)
                return (None, base64.b64decode(b64))
            except Exception:
                return (None, s.encode("utf-8", "ignore"))
        if s.startswith("b'") or s.startswith('b"'):
            import ast
            try:
                buf = ast.literal_eval(s)
                if isinstance(buf, (bytes, bytearray)): return (None, bytes(buf))
            except Exception:
                pass
        return (None, None)
    # 기타 타입 → 문자열 캐스팅 후 URL인지 확인
    try:
        s = str(item)
        if s.startswith(("http://", "https://")): return (s, None)
    except Exception:
        pass
    return (None, None)

def _save_url(u: str, out_dir: Path, prefix: str, idx: int) -> Tuple[Path, str]:
    r = requests.get(u, timeout=180)
    r.raise_for_status()
    ext = ".png" if "png" in r.headers.get("Content-Type", "").lower() else ".jpg"
    fname = f"{prefix}_{_nowtag()}_{idx}{ext}"
    path = out_dir / fname
    path.write_bytes(r.content)
    return path, fname

def _save_bytes(buf: bytes, out_dir: Path, prefix: str, idx: int) -> Tuple[Path, str]:
    ext = _infer_ext_from_bytes(buf)
    fname = f"{prefix}_{_nowtag()}_{idx}{ext}"
    path = out_dir / fname
    path.write_bytes(buf)
    return path, fname

def generate_banner_images_from_prompt(
    job: Dict[str, Any],
    *,
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    save_dir: Optional[Path] = None,
    filename_prefix: Optional[str] = None,
    return_type: Literal["dict", "list", "string"] = "dict",
) -> Union[dict, list, str]:
    """
    Replicate(Dreamina) 호출 → 로컬 저장 → 결과 반환
    - images: 원격 URL 목록(없으면 로컬 경로 Fallback)
    - file_path: 첫 저장 파일 경로(문자열)
    - file_name: 첫 저장 파일명(문자열)
    """
    _require_token()
    model = _env_model()

    job_used = _norm_job(job)
    inputs = _build_inputs(job_used)

    out_dir = save_dir or _default_save_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = _safe_prefix(filename_prefix or "banner")

    raw_out = replicate.run(model, input=inputs)
    if raw_out is None:
        raise RuntimeError("Replicate 응답이 비어 있습니다.")
    if not isinstance(raw_out, (list, tuple)):
        raw_out = [raw_out]

    saved_paths: List[Path] = []
    saved_names: List[str] = []
    url_list: List[str] = []

    for idx, item in enumerate(raw_out, 1):
        url, buf = _to_url_or_bytes(item)
        if url:
            p, name = _save_url(url, out_dir, prefix, idx)
            url_list.append(url)
        elif buf:
            p, name = _save_bytes(buf, out_dir, prefix, idx)
        else:
            continue
        saved_paths.append(p)
        saved_names.append(name)

    if not saved_paths:
        # 저장 실패 시 최소한의 메타만 반환
        if return_type == "list": return []
        if return_type == "string": return ""
        return {
            "ok": True,
            "orientation": orientation,
            "model": model,
            "inputs": inputs,
            "images": url_list,
            "file_path": "",
            "file_name": "",
            "job_used": job_used,
        }

    # images가 비면 로컬 경로로 Fallback
    if not url_list:
        url_list = [p.as_posix() for p in saved_paths]

    first = saved_paths[0]
    first_path = first.as_posix()
    first_name = first.name

    if return_type == "list":
        return [p.as_posix() for p in saved_paths]
    if return_type == "string":
        return first_path

    return {
        "ok": True,
        "orientation": orientation,
        "model": model,
        "inputs": inputs,
        "images": url_list,
        "file_path": first_path,
        "file_name": first_name,
        "job_used": job_used,
    }
