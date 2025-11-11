# app/service/banner/make_banner_from_prompt/banner_builder.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Optional, Literal, Any, Dict, List, Tuple, Union
from pathlib import Path
import os, io, time, base64

import requests

# Replicate 불러오기 (토큰 없으면 에러)
try:
    import replicate
except Exception as e:
    raise SystemExit("[에러] 'replicate' 모듈이 없습니다.  `pip install replicate`") from e

# ------------------ 환경 ------------------
DEFAULT_MODEL = "bytedance/dreamina-3.1"
MIN_WH = 512
MAX_WH = 3024

def _env_model() -> str:
    m = os.getenv("REPLICATE_MODEL", "").strip().strip('"').strip("'")
    return m or DEFAULT_MODEL

def _require_token():
    tok = os.getenv("REPLICATE_API_TOKEN")
    if not tok:
        raise RuntimeError("REPLICATE_API_TOKEN이 설정되지 않았습니다 (.env 또는 환경변수).")
    os.environ["REPLICATE_API_TOKEN"] = tok

def _default_save_dir() -> Path:
    # ENV 오버라이드 가능
    return Path(os.getenv("BANNER_SAVE_DIR", "C:/final_project/ACC/assets/banners"))

def _clamp(v: int) -> int:
    return max(MIN_WH, min(MAX_WH, int(v)))

def _infer_ext_from_bytes(buf: bytes) -> str:
    if buf.startswith(b"\xff\xd8"):  # JPEG
        return ".jpg"
    if buf.startswith(b"\x89PNG"):   # PNG
        return ".png"
    return ".jpg"

def _nowtag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")

def _ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

# ------------------ Replicate 출력 정규화 ------------------
def _to_url_or_bytes(item: Any) -> Tuple[Optional[str], Optional[bytes]]:
    """
    Replicate.run() 결과 항목을 URL 또는 bytes로 통일.
    반환: (url, bytes)
    """
    # 1) bytes류
    if isinstance(item, (bytes, bytearray)):
        return (None, bytes(item))

    # 2) file-like (read 메서드)
    if hasattr(item, "read") and callable(getattr(item, "read")):
        try:
            data = item.read()
            if isinstance(data, str):
                s = data.strip()
                if s.startswith("data:image/"):
                    try:
                        header, b64 = s.split(",", 1)
                        return (None, base64.b64decode(b64))
                    except Exception:
                        return (None, s.encode("utf-8", "ignore"))
                return (None, data.encode("utf-8", "ignore"))
            return (None, data)
        except Exception:
            pass

    # 3) dict에 url/bytes 들어있는 케이스
    if isinstance(item, dict):
        u = item.get("url") or item.get("image") or item.get("href")
        if isinstance(u, str) and u.startswith("http"):
            return (u, None)
        b = item.get("bytes") or item.get("data")
        if isinstance(b, (bytes, bytearray)):
            return (None, bytes(b))
        if isinstance(b, str) and b.startswith("data:image/"):
            try:
                _, b64 = b.split(",", 1)
                return (None, base64.b64decode(b64))
            except Exception:
                return (None, b.encode("utf-8", "ignore"))

    # 4) str
    if isinstance(item, str):
        s = item.strip()
        if s.startswith("http://") or s.startswith("https://"):
            return (s, None)
        if s.startswith("data:image/"):
            try:
                _, b64 = s.split(",", 1)
                return (None, base64.b64decode(b64))
            except Exception:
                return (None, s.encode("utf-8", "ignore"))
        if s.startswith("b'") or s.startswith('b"'):
            try:
                import ast
                buf = ast.literal_eval(s)
                if isinstance(buf, (bytes, bytearray)):
                    return (None, bytes(buf))
            except Exception:
                pass
        return (None, None)

    # 5) 기타 타입
    try:
        s = str(item)
        if s.startswith("http://") or s.startswith("https://"):
            return (s, None)
    except Exception:
        pass
    return (None, None)

def _save_url(u: str, out_dir: Path, prefix: str, idx: int) -> Tuple[Path, str]:
    r = requests.get(u, timeout=120)
    r.raise_for_status()
    ext = ".jpg"
    ct = r.headers.get("Content-Type", "").lower()
    if "png" in ct: ext = ".png"
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

# ------------------ 공개 함수 ------------------
def generate_banner_images_from_prompt(
    job: Dict[str, Any],
    *,
    orientation: Literal["horizontal", "vertical"] = "horizontal",
    width: Optional[int] = None,
    height: Optional[int] = None,
    aspect_ratio: str = "custom",
    resolution: str = "2K",
    use_pre_llm: bool = True,
    seed: Optional[int] = None,
    save_dir: Optional[Path] = None,
    filename_prefix: Optional[str] = None,
    return_type: Literal["dict", "list", "string"] = "dict",
) -> Union[dict, list, str]:
    """
    - job(dict): prompt, (prompt_ko/ko_baseline는 그대로 통과)
    - orientation에 맞춰 width/height 기본값 자동 적용
      horizontal: 3024x544, vertical: 1008x3024
    - Replicate 호출 결과(URL/bytes)를 로컬에 저장하고 경로/파일명 반환

    반환 형식:
      return_type == "dict": {
         ok, orientation, model, inputs, images(원시출력 URL들 또는 Fallback 로컬경로),
         file_path(str), file_name(str), job_used
      }
      "list": [file_path1, file_path2, ...]
      "string": "file_path1"
    """
    if not isinstance(job, dict) or not isinstance(job.get("prompt"), str):
        raise ValueError("job['prompt']가 문자열로 필요합니다.")

    # 기본 해상도 (orientation 기반 자동)
    if width is None or height is None:
        if orientation == "vertical":
            width = width or 1008
            height = height or 3024
        else:
            width = width or 3024
            height = height or 544

    w, h = _clamp(width), _clamp(height)

    # 입력 구성 (top-level 인자를 우선 적용, job 값은 보조)
    inputs = {
        "prompt": job["prompt"],
        "aspect_ratio": job.get("aspect_ratio", aspect_ratio),
        "width": w,
        "height": h,
        "resolution": resolution,
        "use_pre_llm": bool(use_pre_llm if use_pre_llm is not None else job.get("use_pre_llm", True)),
    }
    if seed is not None:
        inputs["seed"] = int(seed)

    # 실행
    _require_token()
    model = _env_model()
    raw_out = replicate.run(model, input=inputs)

    # 출력 정규화
    if raw_out is None:
        raise RuntimeError("Replicate 응답이 비어 있습니다.")
    if not isinstance(raw_out, (list, tuple)):
        raw_out = [raw_out]

    # 저장
    out_dir = save_dir or _default_save_dir()
    _ensure_dir(out_dir)
    prefix = (filename_prefix or "banner").strip() or "banner"

    saved_paths: List[Path] = []
    saved_names: List[str] = []
    url_list: List[str] = []   # 원시 URL(있는 경우만)

    for idx, item in enumerate(raw_out, 1):
        url, buf = _to_url_or_bytes(item)
        if url:
            p, name = _save_url(url, out_dir, prefix, idx)
            url_list.append(url)
        elif buf:
            p, name = _save_bytes(buf, out_dir, prefix, idx)
        else:
            # 알 수 없는 항목은 스킵
            continue
        saved_paths.append(p)
        saved_names.append(name)

    if not saved_paths:
        raise RuntimeError("이미지를 저장하지 못했습니다(출력 파싱 실패).")

    # ✅ Fallback: 원격 URL이 하나도 없으면 images에 로컬 경로를 넣어준다
    if not url_list:
        url_list = [p.as_posix() for p in saved_paths]

    # 반환 정리
    first_path = saved_paths[0].as_posix()
    first_name = saved_names[0]

    if return_type == "list":
        return [p.as_posix() for p in saved_paths]
    if return_type == "string":
        return first_path

    return {
        "ok": True,
        "orientation": orientation,
        "model": model,
        "inputs": inputs,
        "images": url_list,           # 원시 URL들(없으면 로컬 경로 Fallback)
        "file_path": first_path,      # DB 저장용 단일 문자열
        "file_name": first_name,      # DB 저장용 파일명
        "job_used": job,              # 생성에 사용된 job 그대로
    }
