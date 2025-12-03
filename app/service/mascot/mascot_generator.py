import json
import openai
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[mascot_generator] OPENAI_API_KEY를 찾을 수 없습니다.")
else:
    openai.api_key = OPENAI_API_KEY

# 마스코트 프롬프트 생성
def create_mascot_prompt(user_theme, analysis_summary, poster_trend_report, strategy_report):
    print(f"  [mascot_generator] AI 마스코트 프롬프트 기획 시작...")
    
    try:
        analysis_str = json.dumps(analysis_summary, ensure_ascii=False)

        system_prompt = f"""
        You are a top-tier Character Designer specializing in **Korean-style festival mascots**.

        Your task:
        Generate 4 **unique mascot character concepts** where the *style itself is dynamically chosen by you*,
        as long as it matches Korean public taste.

        ====================================================================
        🎨 [STYLE GENERATION RULES — LLM decides the style]
        ====================================================================
        You MUST create the style_name yourself for each prompt.

        ✔ 스타일 특징 예시(이런 방향이면 OK):
        - 부드럽고 동글동글한 한국형 캐릭터 감성
        - Kakao Friends / Line Friends / BT21 계열의 귀엽고 단순한 형태
        - Soft 3D, Webtoon Flat, Warm Pastel, Clay Style 등은 사용 가능
        - 단, 스타일 이름은 무작위 + 창의적으로 만들 것
        예) “Warm Puffy 3D Mascot”, “Soft Bubble Toon”, “Creamy Sticker Style”, “Pastel Mini-Pet Style”

        ❌ 다음 금지:
        - Pixar/Disney 스타일
        - Marvel, DC, realistic western cartoon style
        - overly American cute style
        - realism, hyper-real textures
        - muscular body types

        ====================================================================
        🧸 [CHARACTER DESIGN RULES]
        ====================================================================
        1. Exactly **ONE mascot character** (no friends, no groups)
        2. **Full-body**, centered, simple pose
        3. **Facial emotion must be friendly, approachable**
        4. No props unless essential to the concept (max 1 small item allowed)
        5. Do NOT add poster layout, text, titles, or decorations

        ====================================================================
        🧼 [BACKGROUND]
        ====================================================================
        - MUST be pure white (#FFFFFF)
        - No gradients, shadows, objects, sparkles, lights, snow, or scenery

        ====================================================================
        🈲 [ABSOLUTE FORBIDDEN CONTENT]
        ====================================================================
        no poster, no typography, no title, no date, no icons, no tags, no stickers around
        no foreign objects, no Christmas elements unless explicitly required
        no scenery, no backgrounds, no additional characters
        no hands holding items unless conceptually necessary

        ====================================================================
        📝 [VISUAL PROMPT FORMAT]
        ====================================================================
        - English only
        - Describe:
            - Species / concept identity
            - Outfit related to the provided festival theme
            - Color palette
            - Facial expression
            - Pose
            - Unique Korean-style charm
        - At the END ALWAYS append:
        "full body, centered, pure white background, no text, no logo, no objects, Korean cute style"

        ====================================================================
        📦 [JSON OUTPUT FORMAT]
        ====================================================================
        {{
            "master_prompt": {{
                "prompt_options": [
                    {{
                        "style_name": "LLM generated style name",
                        "text_content": {{"title": "", "date_location": ""}},
                        "visual_prompt": "Detailed mascot-only prompt following ALL rules"
                    }}
                ]
            }},
            "status": "success"
        }}
        """
        
        user_prompt = f"""
        [Theme]: {user_theme}
        [Info]: {analysis_str}
        ---
        Design 4 diverse mascot concepts.
        """
        
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo", 
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"    ❌ 마스코트 프롬프트 생성 오류: {e}")
        return {"error": str(e)}

def build_mascot_image_prompt(base_prompt: str) -> str:
    prefix = (
        "High-quality Korean-style cute mascot character illustration, "
        "full body, centered, standing, pure white background, "
        "soft lighting, round shapes, warm and friendly expression, "
        "Kakao Friends / Line Friends inspired mood (but NOT copying), "
        "clean sticker-style rendering. "
    )
    
    negative = (
        "no poster, no flyer, no layout, no title, no text, no logo, "
        "no western cartoon style, no Pixar, no Disney, no Marvel, "
        "no Christmas elements, no presents, no decorations, "
        "no background objects, no scenery, no props, "
        "no additional characters, no crowd, no icons, no symbols."
    )
    
    return f"{prefix}{base_prompt}. {negative}"