# check_imagen_models.py
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("API 키가 없습니다.")
    exit()

# v1beta를 명시하여 호환성 문제 방지
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version':'v1beta'})

print("--- 사용 가능한 이미지 생성 모델 목록 ---")
try:
    for m in client.models.list():
        name = m.name.split("/")[-1]
        # 'imagen'이 포함된 모델만 필터링
        if "imagen" in name:
            print(f"**확인된 Imagen 모델명:** {name}")
            print(f"  지원 기능: {m.supported_generation_methods}")
except Exception as e:
    print(f"목록 조회 실패 (인터넷 연결 확인 필요): {e}")