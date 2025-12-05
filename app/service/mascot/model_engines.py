import os
import requests
import replicate
from dotenv import load_dotenv
from replicate.helpers import FileOutput
import cairosvg

load_dotenv()

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if not REPLICATE_API_TOKEN:
    raise Exception("❌ REPLICATE_API_TOKEN is not set in .env")

# 전역 클라이언트
client = replicate.Client(api_token=REPLICATE_API_TOKEN)

# ------------------------------------------------------------
# 공통: 출력에서 URL 뽑는 로직만 최소한으로 재사용
# (payload / 호출 / 성공 여부 판단은 모델별로 따로 처리)
# ------------------------------------------------------------

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

def _download_image(url: str, output_path: str):
    resp = requests.get(url)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

# ============================================================
# 1) FLUX (black-forest-labs/flux-dev)
#    - 네가 준 input schema 기준으로 필드 구성
# ============================================================
FLUX_MODEL = "black-forest-labs/flux-dev"

def run_flux(prompt: str, output_path: str):
    print("==============================")
    print("=== [FLUX] 모델 호출 시작 ===")
    print("==============================")

    payload = {
        "prompt": prompt,
        "go_fast": True,
        "guidance": 3.5,
        "megapixels": "1",
        "num_outputs": 1,
        "aspect_ratio": "1:1",
        "output_format": "webp",
        "output_quality": 80,
        "prompt_strength": 0.8,
        "num_inference_steps": 28,
        # None 들어가는 필드는 아예 안 보냄
    }

    print("[FLUX PAYLOAD]", payload)

    try:
        raw = client.run(FLUX_MODEL, input=payload)
        print("[FLUX RAW OUTPUT]", raw)
    except Exception as e:
        msg = f"FLUX_CALL_ERROR: {e}"
        print("[FLUX ERROR]", msg)
        return {"status": "error", "error": msg}

    url = _extract_image_url(raw)
    if not url:
        msg = "FLUX_NO_IMAGE_URL"
        print("[FLUX ERROR]", msg)
        return {"status": "error", "error": msg}

    try:
        _download_image(url, output_path)
    except Exception as e:
        msg = f"FLUX_DOWNLOAD_ERROR: {e}"
        print("[FLUX ERROR]", msg)
        return {"status": "error", "error": msg}

    file_name = os.path.basename(output_path)

    return {
        "status": "success",
        "image_url": url,         # Replicate 원본 URL (디버깅용)
        "file_path": output_path, # 실제 저장 경로 (네가 정한 mascot_xxx.png)
        "file_name": file_name,
    }

# ============================================================
# 2) Ideogram v2a Turbo (ideogram-ai/ideogram-v2a-turbo)
#    - 네가 준 input schema 기준
# ============================================================
IDEOGRAM_MODEL = "ideogram-ai/ideogram-v2a-turbo"

def run_pixart(prompt: str, output_path: str):
    print("==============================")
    print("=== [PIXART] 모델 호출 시작 ===")
    print("==============================")

    payload = {
        "prompt": prompt,
        "resolution": "None",       # 그대로 사용 (aspect_ratio가 우선)
        "style_type": "None",       # 필요 시 "Design" / "Anime" 등으로 바꿔도 됨
        "aspect_ratio": "1:1",
        "magic_prompt_option": "Auto",
    }

    print("[PIXART PAYLOAD]", payload)

    try:
        raw = client.run(IDEOGRAM_MODEL, input=payload)
        print("[PIXART RAW OUTPUT]", raw)
    except Exception as e:
        msg = f"PIXART_CALL_ERROR: {e}"
        print("[PIXART ERROR]", msg)
        return {"status": "error", "error": msg}

    url = _extract_image_url(raw)
    if not url:
        msg = "PIXART_NO_IMAGE_URL"
        print("[PIXART ERROR]", msg)
        return {"status": "error", "error": msg}

    try:
        _download_image(url, output_path)
    except Exception as e:
        msg = f"PIXART_DOWNLOAD_ERROR: {e}"
        print("[PIXART ERROR]", msg)
        return {"status": "error", "error": msg}

    file_name = os.path.basename(output_path)

    return {
        "status": "success",
        "image_url": url,
        "file_path": output_path,
        "file_name": file_name,
    }

# ============================================================
# 3) Stable Diffusion 3.5 Medium
#    (stability-ai/stable-diffusion-3.5-medium)
#    - schema 기준으로 None 값은 아예 안 보냄
# ============================================================
SD3_MODEL = "stability-ai/stable-diffusion-3.5-medium"

def run_sd3(prompt: str, output_path: str):
    print("==============================")
    print("=== [SD3] 모델 호출 시작 ===")
    print("==============================")

    payload = {
        "prompt": prompt,
        "cfg": 5,
        "aspect_ratio": "1:1",
        "output_format": "webp",
        "prompt_strength": 0.85,
        # seed / image / negative_prompt 는 안 보냄 (None 넣지 말기)
    }

    print("[SD3 PAYLOAD]", payload)

    try:
        raw = client.run(SD3_MODEL, input=payload)
        print("[SD3 RAW OUTPUT]", raw)
    except Exception as e:
        msg = f"SD3_CALL_ERROR: {e}"
        print("[SD3 ERROR]", msg)
        return {"status": "error", "error": msg}

    url = _extract_image_url(raw)
    if not url:
        msg = "SD3_NO_IMAGE_URL"
        print("[SD3 ERROR]", msg)
        return {"status": "error", "error": msg}

    # 여기서부터는 "성공"으로 보고 그냥 다운로드
    try:
        _download_image(url, output_path)
    except Exception as e:
        msg = f"SD3_DOWNLOAD_ERROR: {e}"
        print("[SD3 ERROR]", msg)
        return {"status": "error", "error": msg}

    file_name = os.path.basename(output_path)

    return {
        "status": "success",
        "image_url": url,
        "file_path": output_path,
        "file_name": file_name,
    }

# ============================================================
# 4) Recraft v3 SVG (recraft-ai/recraft-v3-svg)
# ============================================================
RECRAFT_MODEL = "recraft-ai/recraft-v3-svg"

def run_recraft(prompt: str, output_path: str):
    print("==============================")
    print("=== [RECRAFT] 모델 호출 시작 ===")
    print("==============================")

    payload = {
        "prompt": prompt,
        "size": "1024x1024",
        "style": "any",
        "aspect_ratio": "Not set",
    }

    print("[RECRAFT PAYLOAD]", payload)

    try:
        raw = client.run(RECRAFT_MODEL, input=payload)
        print("[RECRAFT RAW OUTPUT]", raw)
    except Exception as e:
        msg = f"RECRAFT_CALL_ERROR: {e}"
        print("[RECRAFT ERROR]", msg)
        return {"status": "error", "error": msg}

    url = _extract_image_url(raw)
    if not url:
        msg = "RECRAFT_NO_IMAGE_URL"
        print("[RECRAFT ERROR]", msg)
        return {"status": "error", "error": msg}

    # ============================
    # 🔥 SVG인 경우 PNG로 변환
    # ============================
    try:
        print("[RECRAFT] SVG 변환 처리 시작")
        svg_bytes = requests.get(url).content
        
        # output_path는 PNG 확장자로 저장됨
        cairosvg.svg2png(bytestring=svg_bytes, write_to=output_path)
        print("[RECRAFT] SVG → PNG 변환 완료:", output_path)

    except Exception as e:
        msg = f"RECRAFT_SVG_CONVERT_ERROR: {e}"
        print("[RECRAFT ERROR]", msg)
        return {"status": "error", "error": msg}

    file_name = os.path.basename(output_path)

    return {
        "status": "success",
        "image_url": url,         # SVG 원본 URL (디버깅용)
        "file_path": output_path, # 변환된 PNG 경로
        "file_name": file_name,
    }
