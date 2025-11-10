# -*- coding: utf-8 -*-
"""
banner_builder.py (Require KO-sync)

역할
- job(dict) + 옵션 → Replicate Dreamina 3.1 호출
- 생성 직전, 한글 프롬프트 변경 감지 & EN 프롬프트 자동 동기화를 '필수'로 수행
  * 실패(업데이터 모듈 없음 / 필수 키 누락 / 동기화 실패) 시 예외 발생
- 파일 저장(save_dir 지정) 시, 생성물 경로(artifact_paths)까지 반환

반환 형태
- return_type="list"   → URL 리스트
- return_type="string" → URL 리스트를 '\n'로 join
- return_type="dict"   → 상세 메타(dict): inputs, images(URL), artifact_paths(파일경로) 포함
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Literal, List, Union
import os, re, time
from pathlib import Path

# --- 외부 의존성 ---
try:
    import replicate
except Exception as e:
    raise RuntimeError("[에러] 'replicate' 모듈이 없습니다.  `pip install replicate`") from e

# 로컬 저장(선택)용
try:
    import requests
except Exception:
    requests = None  # save_dir 안 쓰면 없어도 OK

# ✅ KO 변경감지 & EN 동기화 퍼사드(서비스)
#   표준 경로 우선 시도 → 대체 경로(유연성)
_updater = None
try:
    from app.service.banner.banner_prompt_update.service_banner_prompt_update import (
        banner_prompt_update_if_ko_changed as _updater
    )
except Exception:
    try:
        from app.service.banner.service_banner_prompt_update import (
            banner_prompt_update_if_ko_changed as _updater
        )
    except Exception:
        _updater = None  # 모듈 없으면 None → 필수 모드에서 예외 발생

# dotenv(.env) 로드 (선택)
try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

# ---------- 상수 ----------
DEFAULT_MODEL = "bytedance/dreamina-3.1"
DEFAULT_ASPECT = "custom"
DEFAULT_RESOLUTION = "2K"
DEFAULT_HORIZONTAL = (3024, 544)
DEFAULT_VERTICAL = (1008, 3024)
MIN_WH = 512
MAX_WH = 3024

__all__ = [
    "generate_banner_images_from_prompt",
]

# ---------- 내부 유틸 ----------
def _load_env_once() -> None:
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env:
            load_dotenv(env, override=False)
        else:
            here = Path(__file__).resolve().parent
            local = here / ".env"
            if local.exists():
                load_dotenv(local, override=False)

def _require_token() -> str:
    tok = os.getenv("REPLICATE_API_TOKEN")
    if tok:
        return tok
    _load_env_once()
    tok = os.getenv("REPLICATE_API_TOKEN")
    if not tok:
        raise RuntimeError("REPLICATE_API_TOKEN을 찾을 수 없습니다(.env).")
    return tok

def _model_slug() -> str:
    m = os.getenv("REPLICATE_MODEL")
    if not m:
        _load_env_once()
        m = os.getenv("REPLICATE_MODEL")
    return (m or DEFAULT_MODEL).strip().strip('"').strip("'")

def _clamp_dim(v: int) -> int:
    v = int(v)
    if v < MIN_WH: return MIN_WH
    if v > MAX_WH: return MAX_WH
    return v

def _effective_dims(
    orientation: Optional[Literal["horizontal", "vertical"]],
    width: Optional[int],
    height: Optional[int],
    job: Dict[str, Any],
) -> tuple[int, int, Literal["horizontal","vertical"]]:
    """
    최종 width/height/orientation 결정
    - width/height 인자로 직접 오면 그 값 우선
    - 없으면 job의 width/height
    - 그래도 없으면 orientation 기본 해상도(orientation None이면 horizontal 가정)
    """
    ort: Literal["horizontal","vertical"] = (orientation or "horizontal")
    w = width if width is not None else job.get("width")
    h = height if height is not None else job.get("height")
    if w is None or h is None:
        w, h = (DEFAULT_VERTICAL if ort == "vertical" else DEFAULT_HORIZONTAL)
    return _clamp_dim(w), _clamp_dim(h), ort

def _build_inputs(job: Dict[str, Any], w: int, h: int) -> Dict[str, Any]:
    """
    Dreamina 입력 페이로드 구성. job에 존재하면 가져오고, 없으면 기본값 적용.
    - prompt: 필수
    - aspect_ratio: 기본 'custom'
    - width/height: 필수(이미 결정됨)
    - resolution/seed/use_pre_llm: 선택
    """
    prompt = job.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("job['prompt']가 비어있습니다.")
    inputs: Dict[str, Any] = {
        "prompt": prompt,
        "aspect_ratio": job.get("aspect_ratio", DEFAULT_ASPECT),
        "width": w,
        "height": h,
    }
    inputs["resolution"] = job.get("resolution", DEFAULT_RESOLUTION)
    if "seed" in job:        inputs["seed"] = job["seed"]
    if "use_pre_llm" in job: inputs["use_pre_llm"] = job["use_pre_llm"]
    return inputs

def _run_replicate(model: str, inputs: Dict[str, Any]) -> List[str]:
    """
    Replicate 실행. 결과는 보통 이미지 URL 리스트.
    """
    os.environ["REPLICATE_API_TOKEN"] = _require_token()
    out = replicate.run(model, input=inputs)
    if isinstance(out, list):
        return out
    if isinstance(out, str):
        return [out]
    if isinstance(out, dict):
        for k in ("images", "output", "results"):
            if k in out and isinstance(out[k], list):
                return [str(x) for x in out[k]]
    return [str(out)]

# ---- 파일 저장(옵션) ----
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 -_.\uAC00-\uD7A3")
def _safe_name(s: str, default: str = "banner") -> str:
    s = (s or "").strip()
    if not s: return default
    s = re.sub(r"\s+", "_", s)
    return "".join(ch if ch in _ALLOWED else "_" for ch in s)[:80] or default

def _slug_from_prompt(prompt: str) -> str:
    m = re.search(r'TITLE\s*=\s*([^,;|\n]+)', prompt, flags=re.IGNORECASE)
    if not m:
        m = re.search(r'TITLE\s*:\s*(?:"([^"]+)"|([^;,\n]+))', prompt, flags=re.IGNORECASE)
    base = (m.group(1) or m.group(2)).strip() if m else "banner"
    return _safe_name(base)

def _download_and_save(urls: List[str], save_dir: Path, base_name: Optional[str] = None) -> List[str]:
    if requests is None:
        raise RuntimeError("'requests' 모듈이 없습니다.  `pip install requests`")
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = _safe_name(base_name or "banner")
    saved_paths: List[str] = []
    for i, url in enumerate(urls, 1):
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").lower()
        ext = ".jpg" if "jpeg" in content_type or "jpg" in content_type else ".png"
        out_path = save_dir / f"{base}_{ts}_{i}{ext}"
        out_path.write_bytes(r.content)
        saved_paths.append(str(out_path.resolve()))
    return saved_paths

# ---------- 공개 API ----------
def generate_banner_images_from_prompt(
    job: Dict[str, Any],
    *,
    orientation: Optional[Literal["horizontal", "vertical"]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    seed: Optional[int] = None,
    use_pre_llm: Optional[bool] = None,
    # ✅ 변경감지 & 동기화는 '필수'로 수행
    rolling_baseline: bool = True,
    return_type: Literal["dict", "list", "string"] = "list",
    strict: bool = True,
    model: Optional[str] = None,
    # 파일 저장 옵션
    save_dir: Optional[Union[str, Path]] = None,
    filename_prefix: Optional[str] = None,
) -> Union[List[str], Dict[str, Any], str]:
    """
    job(dict) → Dreamina 이미지 생성 (KO 변경감지 & EN 동기화 필수)

    요구 job 키(필수):
      - "prompt" (영문)
      - "prompt_ko" (현재 한글)
      - "prompt_ko_baseline" (기준선 한글)

    실패 시: 예외 발생
    """
    if not isinstance(job, dict):
        raise TypeError("job은 dict이어야 합니다.")

    # 0) 필수 키 검증 (필수 모드)
    required = ["prompt", "prompt_ko", "prompt_ko_baseline"]
    missing = [k for k in required if not isinstance(job.get(k), str) or not job.get(k, "").strip()]
    if missing:
        raise ValueError(f"KO-sync 필수 키 누락: {missing} (job에 prompt/prompt_ko/prompt_ko_baseline이 필요합니다.)")

    # 1) 너비/높이/방향 최종 결정
    w, h, ort = _effective_dims(orientation, width, height, job)

    # 2) job override
    job_eff = dict(job)
    job_eff["width"] = w
    job_eff["height"] = h
    if aspect_ratio is not None: job_eff["aspect_ratio"] = aspect_ratio
    if resolution is not None:   job_eff["resolution"]   = resolution
    if seed is not None:         job_eff["seed"]         = seed
    if use_pre_llm is not None:  job_eff["use_pre_llm"]  = use_pre_llm

    # 3) ✅ KO 변경 감지 & EN 동기화 (필수)
    if _updater is None:
        raise RuntimeError("KO-sync가 필수이지만, 업데이트 퍼사드 모듈을 찾을 수 없습니다.")
    try:
        upd = _updater(job_eff, rolling_baseline=rolling_baseline, llm=None)
    except Exception as e:
        raise RuntimeError(f"KO-sync 수행 실패: {type(e).__name__}: {e}") from e

    if not (isinstance(upd, dict) and upd.get("ok")):
        raise RuntimeError("KO-sync가 실패했습니다(업데이터 반환 ok=False).")
    job_eff = upd.get("job", job_eff) or job_eff

    # 4) 입력 페이로드 구성
    inputs = _build_inputs(job_eff, w, h)

    # 5) 모델
    model_slug = model or _model_slug()

    # 6) Replicate 호출
    urls = _run_replicate(model_slug, inputs)

    # 7) (옵션) 파일 저장 → 경로 반환
    artifact_paths: List[str] = []
    if save_dir:
        prefix = filename_prefix or _slug_from_prompt(job_eff.get("prompt", ""))
        artifact_paths = _download_and_save(urls, Path(save_dir), prefix)

    # 8) 반환
    if return_type == "list":
        return urls
    elif return_type == "string":
        return "\n".join(urls)
    else:
        return {
            "ok": True,
            "orientation": ort,
            "model": model_slug,
            "inputs": inputs,
            "images": urls,
            "artifact_paths": artifact_paths,  # 생성물 경로
            "job_used": job_eff,               # 동기화 반영 최종 스냅샷
        }
