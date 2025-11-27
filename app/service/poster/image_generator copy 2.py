import os
import openai
import requests
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 1. 🌐 [핵심] 글로벌 버전(영어 전용) 프롬프트 변환
def translate_to_english(raw_prompt, title_k, date_k, location_k):
    """
    한글 정보를 받아 '외국인 관광객용 글로벌 포스터' 컨셉의 
    강력한 영어 프롬프트로 재설계합니다. (한글 생성 원천 봉쇄)
    """
    print(f"  [image_generator] 글로벌 포스터(English Only) 프롬프트 최적화 중...")
    
    # GPT-4에게 내릴 지령: "한국적인 느낌은 살리되, 글자는 100% 영어로 해라"
    system_instruction = """
    You are an expert DALL-E 3 Prompt Engineer.
    Your goal is to create a prompt for an **"International Festival Poster"** targeting global tourists.

    [CRITICAL MISSION]
    The AI (DALL-E) tends to accidentally generate Korean text (Hangul) because the topic is Korean.
    You MUST write a prompt that **FORBIDS Korean text** and forces **English Typography**.

    [YOUR TASK]
    1. **TRANSLATE:** Convert Title, Date, Location into natural English.
       - Ex: "거제 몽돌" -> "GEOJE MONGDOL"
    
    2. **SCENE DESCRIPTION:** - Describe the festival visuals (fireworks, beach, etc.).
       - **IMPORTANT:** Add "International style", "Global tourist poster" to the description.

    3. **TYPOGRAPHY INSTRUCTIONS:**
       - Explicitly state: "The text must be written in **ENGLISH ONLY**."
       - "Render the title '[ENGLISH TITLE]' in the center."
       - "Render the date '[ENGLISH DATE]' at the bottom."
    
    4. **NEGATIVE PROMPT (Safety Lock):**
       - End the prompt with: **"DO NOT USE KOREAN CHARACTERS. NO HANGUL. ENGLISH TEXT ONLY."**
    """

    user_content = f"""
    [Original Concept]: {raw_prompt}
    [Title]: {title_k}
    [Date]: {date_k}
    [Location]: {location_k}
    """

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
            ]
        )
        final_english_prompt = response.choices[0].message.content
        print(f"    👉 최종 영어 프롬프트: {final_english_prompt[:100]}...")
        return final_english_prompt

    except Exception as e:
        print(f"    ⚠️ 번역/최적화 실패 (기본값 사용): {e}")
        return f"International Festival Poster. Title: '{title_k}' (English Only). Date: '{date_k}'. Style: {raw_prompt}. NO KOREAN TEXT."

# 2. 🎨 OpenAI DALL-E 3 이미지 생성
def generate_image_dalle3(prompt, width, height, output_path):
    print(f"  [DALL-E 3] 생성 요청...")
    
    # 세로형 포스터 규격 강제
    dalle_size = "1024x1792"
    
    try:
        client = openai.OpenAI()
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=dalle_size,
            quality="hd", # HD 화질
            n=1,
        )

        image_url = response.data[0].url
        print(f"    - 이미지 URL 확보 완료")

        img_data = requests.get(image_url).content
        with open(output_path, 'wb') as f:
            f.write(img_data)
            
        return {"status": "success", "file_path": output_path}

    except Exception as e:
        print(f"    ❌ DALL-E 3 생성 오류: {e}")
        return {"error": str(e)}