import io
import os
import requests
import replicate
from dotenv import load_dotenv
from replicate.helpers import FileOutput
from PIL import Image
import cairosvg

load_dotenv()

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    raise Exception("❌ REPLICATE_API_TOKEN is not set in .env")

# 전역 클라이언트
client = replicate.Client(api_token=REPLICATE_API_TOKEN)

# ------------------------------------------------------------
# 마스코트 모델 (2026-10 교체, 트러블슈팅 #28)
#   flux     : flux-dev($0.025)            → flux-2-pro($0.015/MP)
#   ideogram : ideogram-v2a-turbo($0.025)  → ideogram-v3-turbo($0.03)
#   imagen   : stable-diffusion-3.5-medium($0.035) → imagen-4-fast($0.02)
#   recraft  : recraft-v3-svg($0.08)       → recraft-v4($0.04, 래스터)
# 모델 id 는 환경변수로 바꿀 수 있다. 입력 형식이 다른 모델로 바꾸면 payload 도 같이 고친다.
# ------------------------------------------------------------
FLUX_MODEL = os.getenv("MASCOT_FLUX_MODEL", "black-forest-labs/flux-2-pro")
IDEOGRAM_MODEL = os.getenv("MASCOT_IDEOGRAM_MODEL", "ideogram-ai/ideogram-v3-turbo")
IMAGEN_MODEL = os.getenv("MASCOT_IMAGEN_MODEL", "google/imagen-4-fast")
RECRAFT_MODEL = os.getenv("MASCOT_RECRAFT_MODEL", "recraft-ai/recraft-v4")


def _extract_image_url(output):
    """
    Replicate run() 결과에서 첫 번째 이미지 URL을 뽑는다.
    - list[str] / list[FileOutput] / list[dict] / str / dict 형태를 모두 허용.
    """
    if isinstance(output, list):
        if not output:
            return None
        first = output[0]
    else:
        first = output

    # FileOutput
    if isinstance(first, FileOutput):
        v = first.url
        if callable(v):
            return v()
        return v

    # dict 또는 유사 객체
    if isinstance(first, dict):
        if "url" in first:
            return first["url"]
        if "image" in first and isinstance(first["image"], dict):
            return first["image"].get("url")

    # 그냥 문자열
    if isinstance(first, str):
        return first

    return None


def _save_as_png(url: str, output_path: str):
    """
    받은 이미지를 실제 PNG 로 저장한다.
    예전에는 webp·svg 를 그대로 .png 이름으로 저장해 에디터·브라우저에서 형식이 어긋났다 (#22 와 같은 문제).
    """
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.content
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    head = data[:512].lstrip().lower()
    if head.startswith(b"<?xml") or head.startswith(b"<svg"):
        cairosvg.svg2png(bytestring=data, write_to=output_path)
        return

    Image.open(io.BytesIO(data)).save(output_path, format="PNG")


def _run(tag: str, model: str, payload: dict, output_path: str):
    print("==============================")
    print(f"=== [{tag}] 모델 호출 시작: {model} ===")
    print("==============================")
    print(f"[{tag} PAYLOAD]", payload)

    try:
        raw = client.run(model, input=payload)
        print(f"[{tag} RAW OUTPUT]", raw)
    except Exception as e:
        msg = f"{tag}_CALL_ERROR: {e}"
        print(f"[{tag} ERROR]", msg)
        return {"status": "error", "error": msg}

    url = _extract_image_url(raw)
    if not url:
        msg = f"{tag}_NO_IMAGE_URL"
        print(f"[{tag} ERROR]", msg)
        return {"status": "error", "error": msg}

    try:
        _save_as_png(url, output_path)
    except Exception as e:
        msg = f"{tag}_DOWNLOAD_ERROR: {e}"
        print(f"[{tag} ERROR]", msg)
        return {"status": "error", "error": msg}

    return {
        "status": "success",
        "image_url": url,          # Replicate 원본 URL (디버깅용)
        "file_path": output_path,  # 실제 저장 경로 (mascot_xxx.png)
        "file_name": os.path.basename(output_path),
    }


def run_flux(prompt: str, output_path: str):
    return _run("FLUX", FLUX_MODEL, {
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "resolution": "1 MP",
        "output_format": "png",
        # 평범한 마스코트를 NSFW 로 오탐해 거부하던 문제(#17) 완화. 범위 1(엄격)~5
        "safety_tolerance": 5,
    }, output_path)


def run_ideogram(prompt: str, output_path: str):
    return _run("IDEOGRAM", IDEOGRAM_MODEL, {
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "magic_prompt_option": "Auto",
    }, output_path)


def run_imagen(prompt: str, output_path: str):
    return _run("IMAGEN", IMAGEN_MODEL, {
        "prompt": prompt,
        "aspect_ratio": "1:1",
        "output_format": "png",
    }, output_path)


def run_recraft(prompt: str, output_path: str):
    # recraft-v4-svg 로 바꿔도 동작한다 (SVG 는 PNG 로 변환해 저장)
    return _run("RECRAFT", RECRAFT_MODEL, {
        "prompt": prompt,
        "size": "1024x1024",
    }, output_path)
