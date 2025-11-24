import os
import openai
import replicate
import requests
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 1. 🌐 한글 -> 영어 번역
def translate_to_english(text):
    print(f"  [image_generator] 프롬프트 번역 중...")
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Translate to high-quality English prompt for Image Generator. Add 'text-free', 'illustration style'."},
                {"role": "user", "content": text}
            ]
        )
        return response.choices[0].message.content
    except:
        return text 

# 2. 🎨 Flux 이미지 생성
def generate_image_replicate(prompt, width, height, output_path):
    print(f"  [image_generator] Replicate(Flux) 생성 요청 ({width}x{height})...")
    try:
        # 비율 계산
        aspect_ratio = "9:16"
        if width == height: aspect_ratio = "1:1"
        elif width > height: aspect_ratio = "16:9"
        elif abs(width/height - 0.75) < 0.1: aspect_ratio = "3:4"

        output = replicate.run(
            "black-forest-labs/flux-schnell",
            input={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio, 
                "go_fast": True,
                "num_outputs": 1
            }
        )
        if output:
            image_url = str(output[0]) if isinstance(output, list) else str(output)
            img_data = requests.get(image_url).content
            with open(output_path, 'wb') as f:
                f.write(img_data)
            return {"status": "success", "file_path": output_path}

        return {"error": "No output from Replicate"}
    except Exception as e:
        print(f"    ❌ 오류: {e}")
        return {"error": str(e)}