# app/service/video/video_gen.py
"""
홍보 영상(포스터·마스코트·기타) 생성 공용 모듈.

예전에는 make_*_video.py 마다 Veo(veo-3.1-generate-preview) 호출 코드가 복사되어 있었는데
그 모델이 종료되어(404) 여기로 모으고 공급자를 고를 수 있게 했다.

  VIDEO_PROVIDER=seedance (기본) : Replicate bytedance/seedance-1-pro-fast (REPLICATE_API_TOKEN)
  VIDEO_PROVIDER=omni            : Gemini gemini-omni-1.1-flash, Interactions REST API (GEMINI_API_KEY, 유료 등급 필요)

호출부가 기대하는 동작은 Veo 때와 같다.
  - generate_image_to_video / generate_text_to_video → (GeneratedVideo, 저장 경로)
  - extend_video → 앞 영상 + 이어진 구간이 합쳐진 "전체" 영상 (호출부는 이 결과를 본편으로 쓴다)
  - 실패하면 (None, None)
"""

import base64
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import httpx
import replicate
import requests
from dotenv import load_dotenv
from PIL import Image, ImageFilter

load_dotenv()

VIDEO_PROVIDER = os.getenv("VIDEO_PROVIDER", "seedance").strip().lower()
SEEDANCE_MODEL = os.getenv("SEEDANCE_VIDEO_MODEL", "bytedance/seedance-1-pro-fast")
OMNI_MODEL = os.getenv("OMNI_VIDEO_MODEL", "gemini-omni-1.1-flash")
OMNI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# Veo 결과와 같은 가로 16:9, 첫 구간 8초
ASPECT_RATIO = "16:9"
FIRST_SEGMENT_S = 8
RESOLUTION = os.getenv("VIDEO_RESOLUTION", "720p")

DOWNLOAD_DIR = Path("generated_videos")


@dataclass
class GeneratedVideo:
    path: Path
    interaction_id: Optional[str] = None  # omni 이어 만들기용


def _out_path(name: str) -> Path:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    return DOWNLOAD_DIR / name


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _fit_16_9(image_path: str) -> Path:
    """이미지를 16:9 캔버스 가운데에 두고 남는 곳은 같은 이미지를 흐리게 깔아 채운다 (Seedance 는 입력 이미지 비율을 따른다)"""
    im = Image.open(image_path).convert("RGB")
    W, H = 1280, 720
    bg = im.resize((W, H)).filter(ImageFilter.GaussianBlur(40))
    fg = im.copy()
    fg.thumbnail((W, H), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    out = Path(tempfile.mkstemp(suffix=".png")[1])
    bg.save(out)
    return out


def _last_frame(video: Path) -> Path:
    out = Path(tempfile.mkstemp(suffix=".png")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-sseof", "-0.1", "-i", str(video), "-frames:v", "1", "-update", "1", str(out)],
        capture_output=True, check=True,
    )
    return out


def _concat(first: Path, second: Path, out: Path) -> Path:
    """두 구간을 다시 인코딩해 이어 붙인다 (해상도·코덱이 달라도 되게)"""
    w, h = 1280, 720
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(first), "-i", str(second),
         "-filter_complex", f"[0:v]{vf}[a];[1:v]{vf}[b];[a][b]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)],
        capture_output=True, check=True,
    )
    return out


# --------------------------------------------------
# Seedance (Replicate)
# --------------------------------------------------
def _seedance(prompt: str, image_path: Optional[Path], duration_s: int, out: Path) -> Path:
    params = {
        "prompt": prompt,
        "duration": max(2, min(12, int(duration_s))),
        "resolution": RESOLUTION,
        "aspect_ratio": ASPECT_RATIO,
        "fps": 24,
    }
    # replicate.run 은 한 요청으로 결과를 기다리다 읽기 시간 초과가 나서, 예측을 만들고 상태를 주기적으로 확인한다
    last_error = None
    for attempt in range(2):
        try:
            if image_path:
                with open(image_path, "rb") as f:
                    pred = replicate.predictions.create(model=SEEDANCE_MODEL, input={**params, "image": f})
            else:
                pred = replicate.predictions.create(model=SEEDANCE_MODEL, input=params)
            started = time.time()
            while pred.status not in ("succeeded", "failed", "canceled"):
                if time.time() - started > 900:
                    pred.cancel()
                    raise TimeoutError("Seedance 생성이 15분 안에 끝나지 않았습니다.")
                time.sleep(5)
                pred.reload()
            if pred.status != "succeeded":
                raise RuntimeError(f"Seedance {pred.status}: {pred.error}")
            output = pred.output
            break
        except Exception as e:
            last_error = e
            print(f"⚠️ Seedance 시도 {attempt + 1} 실패: {e}")
    else:
        raise last_error
    url = str(output[0]) if isinstance(output, list) else str(output)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


# --------------------------------------------------
# Gemini Omni (Interactions REST, SDK 1.52 에는 interactions 가 없어 직접 호출)
# --------------------------------------------------
def _omni(input_value, out: Path, previous_id: Optional[str] = None) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 가 없습니다.")
    body = {
        "model": OMNI_MODEL,
        "input": input_value,
        "response_format": {"type": "video", "aspect_ratio": ASPECT_RATIO, "resolution": RESOLUTION},
    }
    if previous_id:
        body["previous_interaction_id"] = previous_id
    r = httpx.post(OMNI_URL, headers={"x-goog-api-key": key}, json=body, timeout=900)
    if r.status_code != 200:
        raise RuntimeError(f"Omni {r.status_code}: {r.text[:300]}")
    j = r.json()
    # REST 응답은 steps[].content[] 안에 type=video 항목으로 base64 가 온다
    for step in j.get("steps", []):
        for c in step.get("content") or []:
            if c.get("type") == "video" and c.get("data"):
                out.write_bytes(base64.b64decode(c["data"]))
                return j["id"]
    raise RuntimeError(f"Omni 응답에 영상이 없습니다 (status={j.get('status')})")


def _image_part(image_path: str) -> dict:
    mime = "image/png" if Path(image_path).suffix.lower() == ".png" else "image/jpeg"
    data = base64.b64encode(Path(image_path).read_bytes()).decode()
    return {"type": "image", "data": data, "mime_type": mime}


# --------------------------------------------------
# 호출부에서 쓰는 함수 (예전 Veo 헬퍼와 같은 이름·반환값)
# --------------------------------------------------
def generate_image_to_video(
    prompt: str,
    start_image_path: str,
    end_image_path: str = None,
    download_name: str = "image_to_video.mp4",
) -> Tuple[Optional[GeneratedVideo], Optional[Path]]:
    """이미지 → 영상 (첫 구간). end_image_path 는 Veo 때 인터페이스 호환용이며 쓰지 않는다"""
    print(f"\n--- 이미지→영상 [{VIDEO_PROVIDER}] (프롬프트: {prompt[:60]}...) ---")
    out = _out_path(download_name)
    try:
        if VIDEO_PROVIDER == "omni":
            iid = _omni([_image_part(start_image_path), {"type": "text", "text": prompt}], out)
            video = GeneratedVideo(out, iid)
        else:
            fitted = _fit_16_9(start_image_path)
            try:
                _seedance(prompt, fitted, FIRST_SEGMENT_S, out)
            finally:
                fitted.unlink(missing_ok=True)
            video = GeneratedVideo(out)
        print(f"⬇️ 영상 저장: {out.resolve()} ({_duration(out):.1f}s)")
        return video, out
    except Exception as e:
        print(f"❌ 이미지→영상 실패: {e}")
        return None, None


def generate_text_to_video(
    prompt: str,
    end_image_path: str = None,
    download_name: str = "text_to_video.mp4",
) -> Tuple[Optional[GeneratedVideo], Optional[Path]]:
    """텍스트 → 영상 (첫 구간)"""
    print(f"\n--- 텍스트→영상 [{VIDEO_PROVIDER}] (프롬프트: {prompt[:60]}...) ---")
    out = _out_path(download_name)
    try:
        if VIDEO_PROVIDER == "omni":
            video = GeneratedVideo(out, _omni(prompt, out))
        else:
            _seedance(prompt, None, FIRST_SEGMENT_S, out)
            video = GeneratedVideo(out)
        print(f"⬇️ 영상 저장: {out.resolve()} ({_duration(out):.1f}s)")
        return video, out
    except Exception as e:
        print(f"❌ 텍스트→영상 실패: {e}")
        return None, None


def extend_video(
    existing_video: Optional[GeneratedVideo],
    extension_prompt: str,
    duration_s: int = 7,
    download_name: str = "extended_video.mp4",
) -> Tuple[Optional[GeneratedVideo], Optional[Path]]:
    """앞 영상에 이어지는 구간을 만들어 붙인 전체 영상을 돌려준다"""
    if not existing_video:
        print("❌ 이어 만들 앞 영상이 없습니다.")
        return None, None
    print(f"\n--- 영상 이어 만들기 [{VIDEO_PROVIDER}] {duration_s}s (프롬프트: {extension_prompt[:60]}...) ---")
    out = _out_path(download_name)
    segment = _out_path(f"seg_{download_name}")
    try:
        first_len = _duration(existing_video.path)
        if VIDEO_PROVIDER == "omni" and existing_video.interaction_id:
            iid = _omni(extension_prompt, segment, previous_id=existing_video.interaction_id)
            # 문서에 결과가 전체인지 이어진 부분만인지 적혀 있지 않아 길이로 판단한다
            if _duration(segment) > first_len + 1:
                segment.replace(out)
                return GeneratedVideo(out, iid), out
        else:
            iid = None
            frame = _last_frame(existing_video.path)
            try:
                _seedance(extension_prompt, frame, duration_s, segment)
            finally:
                frame.unlink(missing_ok=True)
        _concat(existing_video.path, segment, out)
        segment.unlink(missing_ok=True)
        print(f"⬇️ 이어 붙인 영상 저장: {out.resolve()} ({_duration(out):.1f}s)")
        return GeneratedVideo(out, iid), out
    except Exception as e:
        print(f"❌ 영상 이어 만들기 실패: {e}")
        return None, None
