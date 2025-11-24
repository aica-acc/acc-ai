import requests
from pathlib import Path
from io import BytesIO
from PIL import Image

def download_image_from_url(url: str, save_path: str) -> str:
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content)).convert("RGB")

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(save_path)

    return save_path
