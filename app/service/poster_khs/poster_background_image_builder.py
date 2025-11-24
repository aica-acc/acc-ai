# -*- coding: utf-8 -*-
# app/service/poster_khs/poster_background_image_builder.py
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Literal

import replicate
import requests
from replicate.helpers import FileOutput


def _get_replicate_model() -> str:
    """
    실제 사용할 이미지 모델 ID를 결정한다.

    - 환경변수 REPLICATE_MODEL 을 사용한다.
      (예: "bytedance/dreamina-3.1")
    - 값이 없으면 에러를 발생시켜서, 어떤 모델을 쓸지 반드시
      .env 에서 명시적으로 정하도록 강제한다.
    """
    model = os.getenv("REPLICATE_MODEL")
    if not model:
        raise RuntimeError(
            "REPLICATE_MODEL 환경변수가 설정되어 있지 않습니다. "
            "예: REPLICATE_MODEL=bytedance/dreamina-3.1"
        )
    return model


def _default_poster_save_dir() -> Path:
    """
    포스터 배경 이미지를 저장할 기본 경로.

    - POSTER_SAVE_DIR 환경변수가 있으면 우선 사용
    - 없으면 C:/final_project/ACC/assets/posters 로 저장
    """
    return Path(os.getenv("POSTER_SAVE_DIR", "C:/final_project/ACC/assets/posters"))


def build_poster_background_image_from_prompt(
    job: Dict[str, Any],
    *,
    save_dir: Optional[str | Path] = None,
    filename_prefix: Optional[str] = None,
    return_type: Literal["dict", "raw"] = "dict",
) -> Dict[str, Any] | bytes:
    """
    Replicate의 Dreamina 3.1 (또는 REPLICATE_MODEL 로 지정한 어떤 모델이든)을 호출해서
    '배경 전용' 이미지를 실제로 생성하고 디스크에 PNG로 저장한다.

    Parameters
    ----------
    job : dict
        Dreamina 입력 형식과 동일한 딕셔너리.
        예:
        {
          "width": 1536,
          "height": 2048,
          "prompt": "...",
          "resolution": "2K",
          "use_pre_llm": false,
          "aspect_ratio": "3:4",
          ...
        }

    save_dir : str | Path | None
        이미지 저장 폴더. None 이면 _default_poster_save_dir() 사용.
    filename_prefix : str | None
        파일명 접두사. None 이면 "poster_bg" 사용.
    return_type : "dict" | "raw"
        - "dict": 메타데이터 + 경로 정보를 담은 dict 반환
        - "raw" : 이미지 바이트(bytes)만 반환 (파일은 여전히 저장됨)

    Returns
    -------
    dict 또는 bytes
        return_type="dict" 인 경우:
        {
          "ok": True,
          "width": ...,
          "height": ...,
          "prompt": "...",
          "resolution": "...",
          "use_pre_llm": ...,
          "aspect_ratio": "...",
          "image_path": "C:/.../poster_bg_20251118_123045_xxxx.png",
          "image_filename": "poster_bg_20251118_123045_xxxx.png"
        }
    """
    if not isinstance(job, dict):
        raise TypeError("job 인자는 dict 형태여야 합니다.")

    width = int(job.get("width") or 1536)
    height = int(job.get("height") or 2048)
    prompt = str(job.get("prompt") or "").strip()
    resolution = job.get("resolution")
    use_pre_llm = job.get("use_pre_llm")
    aspect_ratio = job.get("aspect_ratio")

    if not prompt:
        raise ValueError("job['prompt'] 가 비어 있습니다. 프롬프트 문자열이 필요합니다.")

    model = _get_replicate_model()

    # --------------------------------------------------
    # 1) Replicate 실행 (Dreamina 3.1 등)
    #    - REPLICATE_API_TOKEN 은 환경변수에서 읽힌다.
    #    - job 전체를 input 으로 그대로 넘김.
    # --------------------------------------------------
    output = replicate.run(model, input=job)

    # --------------------------------------------------
    # 1-1) Replicate 출력 정규화
    #   - list[str | FileOutput] 이거나,
    #   - 단일 FileOutput, 혹은 str 일 수 있음
    # --------------------------------------------------
    if isinstance(output, list):
        if not output:
            raise RuntimeError("Replicate가 빈 리스트를 반환했습니다.")
        file_obj = output[0]
    else:
        file_obj = output

    # FileOutput 타입인 경우: .url 속성 사용
    if isinstance(file_obj, FileOutput):
        image_url = file_obj.url
    elif isinstance(file_obj, str):
        image_url = file_obj
    else:
        # 혹시 다른 타입이 올 경우: 문자열로 URL을 뽑을 수 있으면 사용
        try:
            image_url = str(file_obj)
        except Exception:
            raise RuntimeError(f"예상치 못한 Replicate 출력 형식: {type(file_obj)}")

    # --------------------------------------------------
    # 2) 이미지 다운로드
    # --------------------------------------------------
    resp = requests.get(image_url)
    resp.raise_for_status()
    img_bytes = resp.content

    # --------------------------------------------------
    # 3) 디스크에 PNG 저장
    # --------------------------------------------------
    base_dir = Path(save_dir) if save_dir is not None else _default_poster_save_dir()
    base_dir.mkdir(parents=True, exist_ok=True)

    prefix = filename_prefix or "poster_bg"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_filename = f"{prefix}_{ts}.png"
    image_path = base_dir / image_filename

    with open(image_path, "wb") as f:
        f.write(img_bytes)

    if return_type == "raw":
        return img_bytes

    return {
        "ok": True,
        "width": width,
        "height": height,
        "prompt": prompt,
        "resolution": resolution,
        "use_pre_llm": use_pre_llm,
        "aspect_ratio": aspect_ratio,
        "image_path": image_path.as_posix(),
        "image_filename": image_filename,
    }
