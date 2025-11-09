# -*- coding: utf-8 -*-
"""
mascot_make_mascot_from_prompt.py

역할:
- mascot_config.json(프롬프트/하이퍼파라미터)을 읽어
- Replicate 모델 nandycc/sdxl-mascot-avatars:f0f8a1578f4e57da2090b1846a3c026bd75d38abd969e1d4788b07f203966294
  를 호출해 마스코트 이미지를 생성하고, 로컬 out/ 폴더에 저장합니다.

실행:
    python mascot_make_mascot_from_prompt.py
    # 1) config 경로 입력
    # 2) 출력 폴더(기본: 같은 상위의 out)
    # 3) 파일명 프리픽스

필요:
    pip install replicate requests python-dotenv
    환경변수(또는 .env): REPLICATE_API_TOKEN
"""

import os
import io
import re
import sys
import json
import time
from pathlib import Path
from typing import Iterable, Any

# -------- dotenv로 토큰 로드(선택) --------
try:
    from dotenv import load_dotenv, find_dotenv
except Exception:
    load_dotenv = None
    find_dotenv = None

def _load_env():
    if load_dotenv and find_dotenv:
        env = find_dotenv(usecwd=True)
        if env:
            load_dotenv(env, override=False)
        else:
            local = Path(__file__).resolve().parent / ".env"
            if local.exists():
                load_dotenv(local, override=False)

# -------- 외부 라이브러리 --------
try:
    import replicate
except Exception:
    print("❌ replicate 패키지가 필요합니다.  pip install replicate  후 다시 실행하세요.")
    sys.exit(1)

try:
    import requests
except Exception:
    print("❌ requests 패키지가 필요합니다.  pip install requests  후 다시 실행하세요.")
    sys.exit(1)

# -------- 모델/허용 키 --------
MODEL_ID = "nandycc/sdxl-mascot-avatars:f0f8a1578f4e57da2090b1846a3c026bd75d38abd969e1d4788b07f203966294"

ALLOWED_KEYS = {
    # Replicate 입력 스키마에서 일반적으로 쓰이는 키만 전달
    "prompt", "negative_prompt",
    "image", "mask",
    "width", "height",
    "num_outputs",
    "scheduler",
    "num_inference_steps",
    "guidance_scale",
    "prompt_strength",
    "seed",
    "refine",
    "high_noise_frac",
    "refine_steps",
    "apply_watermark",
    "lora_scale",
    "replicate_weights",
    "disable_safety_checker",
}

# -------- 입출력 도움 함수 --------
def ask_path(msg: str) -> Path:
    while True:
        raw = input(msg).strip().strip('"')
        p = Path(raw)
        if p.exists() and p.is_file():
            return p
        print("[안내] 경로가 올바르지 않습니다. 다시 입력하세요.")

def ask_dir(msg: str, default_dir: Path) -> Path:
    print(f"{msg} (엔터시 {default_dir}): ", end="")
    raw = input().strip().strip('"')
    d = Path(raw) if raw else default_dir
    d.mkdir(parents=True, exist_ok=True)
    return d

def ask_prefix(msg: str, default_prefix: str) -> str:
    print(f"{msg} (엔터시 {default_prefix}): ", end="")
    raw = input().strip()
    return raw if raw else default_prefix

def safe_filename(name: str) -> str:
    s = re.sub(r"[^\w\s\uAC00-\uD7A3-]", "", (name or ""), flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "mascot"

def infer_ext_from_url(url: str) -> str:
    url = url.split("?")[0]
    m = re.search(r"\.(png|jpg|jpeg|webp|bmp|gif)$", url, re.IGNORECASE)
    return "." + m.group(1).lower() if m else ".png"

def resolve_default_out_dir(cfg_path: Path) -> Path:
    """
    cfg_path 상위 경로들 중 'out'이 있으면 그대로 사용, 없으면 부모/out 생성.
    (out/out 중첩 방지)
    """
    parent = cfg_path.parent
    for p in [parent] + list(parent.parents):
        if p.name.lower() == "out":
            return p
    return parent / "out"

# -------- 모델 입력 가공 --------
def _coerce_types(d: dict) -> dict:
    out = dict(d)
    # 정수
    for k in ("width", "height", "num_outputs", "num_inference_steps", "seed", "refine_steps"):
        if k in out and isinstance(out[k], str) and out[k].strip().isdigit():
            out[k] = int(out[k].strip())
    # 실수
    for k in ("guidance_scale", "prompt_strength", "high_noise_frac", "lora_scale"):
        if k in out and isinstance(out[k], str):
            try:
                out[k] = float(out[k].strip())
            except:
                pass
    # 불리언
    for k in ("apply_watermark", "disable_safety_checker"):
        if k in out and isinstance(out[k], str):
            out[k] = out[k].strip().lower() in ("1","true","t","y","yes","on","참","예","네")
    return out

def build_input_from_config(config: dict) -> dict:
    raw = {k: config[k] for k in config.keys() if k in ALLOWED_KEYS}
    return _coerce_types(raw)

# -------- 다운로드 --------
def download_file(url: str, out_path: Path) -> Path:
    r = requests.get(url, stream=True, timeout=90)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return out_path

# -------- FileOutput/여러 포맷 저장 --------
def _is_iterable_but_not_str(x: Any) -> bool:
    if isinstance(x, (str, bytes, bytearray)):
        return False
    try:
        iter(x)
        return True
    except TypeError:
        return False

def save_output_items(output: Any, out_dir: Path, prefix: str) -> list[Path]:
    """
    Replicate 출력 여러 형태를 전부 저장 시도:
    - FileOutput 객체: read()로 bytes 저장, url 속성에서 확장자 추론
    - URL 문자열: 다운로드
    - dict에 url: 다운로드
    - bytes/bytearray: 그대로 저장
    - iterable: 각 item 재귀 처리
    - 그 외: _raw.txt로 덤프
    """
    saved: list[Path] = []
    ts = time.strftime("%Y%m%d_%H%M%S")

    def guess_ext_from_item(item):
        url = getattr(item, "url", None)
        if isinstance(url, str):
            return infer_ext_from_url(url)
        return ".png"

    def handle_item(item, idx: int):
        # 1) FileOutput 유사 객체 (read 메서드 존재)
        if hasattr(item, "read") and callable(getattr(item, "read")):
            try:
                data = item.read()  # bytes
                ext = guess_ext_from_item(item)
                out_path = out_dir / f"{prefix}_{ts}_{idx:02d}{ext}"
                with open(out_path, "wb") as f:
                    f.write(data)
                saved.append(out_path)
                return
            except Exception as e:
                # 실패 시 문자열로라도 떨굼
                dump_path = out_dir / f"{prefix}_{ts}_{idx:02d}_error.txt"
                dump_path.write_text(f"FileOutput read error: {e}\n{repr(item)}", encoding="utf-8")
                saved.append(dump_path)
                return

        # 2) URL 문자열
        if isinstance(item, str) and item.startswith(("http://", "https://")):
            ext = infer_ext_from_url(item)
            out_path = out_dir / f"{prefix}_{ts}_{idx:02d}{ext}"
            download_file(item, out_path)
            saved.append(out_path)
            return

        # 3) dict에 url
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            url = item["url"]
            ext = infer_ext_from_url(url)
            out_path = out_dir / f"{prefix}_{ts}_{idx:02d}{ext}"
            download_file(url, out_path)
            saved.append(out_path)
            return

        # 4) bytes
        if isinstance(item, (bytes, bytearray)):
            out_path = out_dir / f"{prefix}_{ts}_{idx:02d}.png"
            with open(out_path, "wb") as f:
                f.write(item)
            saved.append(out_path)
            return

        # 5) iterable이면 내부 원소들 처리
        if _is_iterable_but_not_str(item):
            try:
                j = 0
                for j, sub in enumerate(item, start=1):
                    handle_item(sub, idx*100 + j)  # 서브 인덱스
                if j == 0:
                    # 비어있는 iterable
                    dump_path = out_dir / f"{prefix}_{ts}_{idx:02d}_empty.txt"
                    dump_path.write_text("Empty iterable output", encoding="utf-8")
                    saved.append(dump_path)
                return
            except Exception as e:
                dump_path = out_dir / f"{prefix}_{ts}_{idx:02d}_iter_error.txt"
                dump_path.write_text(f"Iterable parse error: {e}\n{repr(item)}", encoding="utf-8")
                saved.append(dump_path)
                return

        # 6) 그 외: 문자열 덤프
        dump_path = out_dir / f"{prefix}_{ts}_{idx:02d}_raw.txt"
        try:
            dump_path.write_text(str(item), encoding="utf-8")
        except Exception:
            dump_path.write_bytes(repr(item).encode("utf-8", errors="ignore"))
        saved.append(dump_path)

    # output이 리스트/이터러블/단일 모두 대응
    if _is_iterable_but_not_str(output):
        for i, item in enumerate(output, start=1):
            handle_item(item, i)
    else:
        handle_item(output, 1)

    return saved

# -------- 메인 --------
def main():
    print("=== Mascot Image Generator (from mascot_config.json via Replicate) ===")

    # 1) config 경로
    cfg_path = ask_path("1) mascot_config.json 경로: ")

    # 2) 출력 폴더/프리픽스 (out/out 중첩 방지)
    default_out_dir = resolve_default_out_dir(cfg_path)
    out_dir = ask_dir("2) 출력 폴더", default_out_dir)
    default_prefix = safe_filename(cfg_path.stem.replace("_mascot_config", "")) or "mascot"
    prefix = ask_prefix("3) 파일명 프리픽스", default_prefix)

    # 3) 토큰
    _load_env()
    token = os.getenv("REPLICATE_API_TOKEN")
    if not token:
        print("❌ REPLICATE_API_TOKEN 이 없습니다. .env 또는 환경변수로 설정하세요.")
        return

    # 4) config 로드
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ 설정 JSON 로드 실패: {e}")
        return

    model_input = build_input_from_config(config)
    if not model_input.get("prompt"):
        print("❌ 설정 JSON에 'prompt'가 없습니다.")
        return

    # 5) 호출
    try:
        client = replicate.Client(api_token=token)
        print("⏳ Replicate 호출 중...")
        output = client.run(MODEL_ID, input=model_input)
    except Exception as e:
        print(f"❌ Replicate 실행 실패: {e}")
        return

    # 6) 저장
    try:
        saved = save_output_items(output, out_dir, prefix)
    except Exception as e:
        print(f"❌ 저장 중 오류: {e}")
        return

    # 7) 결과
    if saved:
        print("\n✅ 생성/저장 완료:")
        for p in saved:
            print(" -", p.resolve())
    else:
        print("⚠️ 저장된 파일이 없습니다.")

if __name__ == "__main__":
    main()