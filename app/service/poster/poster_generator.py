import json
import openai
import os
from dotenv import load_dotenv
from app.core.config import OPENAI_TEXT_MODEL

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[poster_generator] OPENAI_API_KEY를 찾을 수 없습니다.")
else:
    openai.api_key = OPENAI_API_KEY

def create_strategy_report(user_theme, pdf_data_dict, poster_trend_data, google_trend_data, naver_datalab_data, naver_search_data):
    """
    (기존 유지) 전략 리포트 생성 함수
    """
    try:
        return {
            "strategy_text": "AI 전략 보고서...",
            "proposed_content": {"title": pdf_data_dict.get('title', '')}
        }
    except:
        return {}

# 2단계: 마스터 프롬프트 생성 (High-End 2D Poster Style)
def create_master_prompt(user_theme, analysis_summary, poster_trend_report, strategy_report):
    print(f"  [poster_generator] AI 프롬프트 기획 시작 (High-End Poster Style)...")
    
    try:
        analysis_str = json.dumps(analysis_summary, ensure_ascii=False)

        # [System Prompt] 3D 제거 + 고퀄리티 2D 포스터 스타일 정의
        system_prompt = f"""
        You are a world-class Art Director creating a **High-End Festival Poster**.
        Your goal is to generate 4 distinct, **commercially viable** poster concepts.

        [🚫 CRITICAL NEGATIVE CONSTRAINTS]
        - **NO 3D RENDER STYLES:** Do NOT use "3D render", "CGI", "plastic", "clay", "toy-like".
        - **NO AMATEUR ART:** Avoid "sketch", "doodle", "low quality", "blurry", "distorted".
        - **TEXT SIZE:** The title must be readable, but **keep other text SMALL and ELEGANT**. Do NOT cover the entire image with giant text.

        [✨ DESIGN QUALITY RULES]
        1. **Professional Finish:** The image must look like a printed poster (CMYK texture, matte finish).
        2. **Composition:** Use "Rule of Thirds" or "Central Symmetrical" layouts. Leave **Negative Space** for text.
        3. **Lighting:** Use "Cinematic Lighting", "Volumetric Fog", or "Soft Studio Lighting" to add depth without making it 3D.

        [🎨 4 MANDATORY STYLE CONCEPTS]
        Create prompts for these 4 specific styles (replace '3D' with 'Flat/Illustrative'):

        1. **"Modern Vector Illustration"**
           - Style: Clean lines, flat colors, geometric shapes, minimalist.
           - Ref: "Swiss Design", "Bauhaus", "Vector Art".
           - Vibe: Trendy, Hip, Young.

        2. **"Cinematic Photography"** (If theme allows) OR **"Watercolor Painting"**
           - Style (Photo): High-resolution, dramatic depth of field, golden hour.
           - Style (Paint): Soft watercolor textures, dreamy, artistic, "Studio Ghibli" vibes.
           - Vibe: Emotional, Grand, Atmospheric.

        3. **"Retro/Vintage Print"**
           - Style: Halftone patterns, paper texture, washed-out colors, 70s/80s typography.
           - Ref: "Risograph", "Screen Print".
           - Vibe: Nostalgic, Warm, Classic.

        4. **"Neon/Cyberpunk (2D)"** OR **"Korean Traditional Ink (Sumukhwa)"**
           - Style (Neon): Glowing lines on dark background (2D anime style), vibrant.
           - Style (Ink): Brush strokes, black and white with red accents, elegant empty space.
           - Vibe: Night festival, energetic OR Traditional, calm.

        [OUTPUT FORMAT - JSON ONLY]
        {{
            "master_prompt": {{
                "prompt_options": [
                    {{
                        "style_name": "Modern Vector",
                        "visual_prompt": "Detailed prompt describing the visual..."
                    }},
                    ... (Total 4 items)
                ]
            }}
        }}
        """
        
        # ✅ [User Prompt] 데이터 전달 및 심플한 실행 명령
        user_prompt = f"""
        [Theme]: {user_theme}
        [Info]: {analysis_str}
        ---
        Based on the [CRITICAL NEGATIVE CONSTRAINTS] and [4 MANDATORY STYLE CONCEPTS] defined above,
        generate 4 high-quality poster prompts.
        """
        
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=OPENAI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"    ❌ 프롬프트 생성 오류: {e}")
        return {"error": str(e)}