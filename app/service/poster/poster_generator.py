import json
import openai
import os
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[poster_generator] OPENAI_API_KEY를 찾을 수 없습니다.")
else:
    openai.api_key = OPENAI_API_KEY

def create_strategy_report(user_theme, pdf_data_dict, poster_trend_data, google_trend_data, naver_datalab_data, naver_search_data):
    try:
        return {
            "strategy_text": "AI 전략 보고서...",
            "proposed_content": {"title": pdf_data_dict.get('title', '')}
        }
    except:
        return {}

# 2단계: 마스터 프롬프트 생성 (포스터 느낌 극대화)
def create_master_prompt(user_theme, analysis_summary, poster_trend_report, strategy_report):
    print(f"  [poster_generator] AI 프롬프트 기획 시작 (Commercial Art Focus)...")
    
    try:
        analysis_str = json.dumps(analysis_summary, ensure_ascii=False)

        system_prompt = f"""
        You are a world-class Art Director. Design 4 distinct Festival Poster concepts.

        [CRITICAL RULES]
        1. **Poster Aesthetics:** The image MUST visually function as a **promotional festival poster**. 
           - **Do NOT describe a generic background.** Describe a **finished, highly composed promotional artwork.**
           - **Typography Balance:** Korean text should be prominent but NOT overpowering (15-25% of total composition)
           - The poster should look like professional festival/event promotional material you'd see in a gallery or subway station
        2. **English Only:** `visual_prompt` MUST be in English.
        3. **Include Korean Text Only:** The final visual prompt must contain instructions for Korean Title, Date, and Location to be rendered in the image. Korean typography should be the centerpiece of the design with artistic, creative placement and 3D effects. NO ENGLISH TEXT allowed.
        [JSON FORMAT]
        {{
            "master_prompt": {{
                "prompt_options": [
                    {{
                        "style_name": "Concept Name",
                        "text_content": {{ ... }},
                        "visual_prompt": "A professional promotional poster for... (English description with typography)" 
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
        Design EXACTLY 4 diverse poster concepts with the following artistic styles:

        1. 3D Artistic Architecture & Objects (3D 아트적 건축물/오브젝트)
        - Imaginative 3D structures or symbolic festival objects with creative architecture
        - Artistic rendering (NOT photorealistic - more stylized and creative)
        - Vibrant colors, playful compositions with artistic exaggeration
        - Festival theme integrated into the 3D structure design

        2. Geometric Technical Infographic (기하학적 테크니컬 디자인)
        - Clean geometric shapes, technical diagrams, and infographic elements
        - Modern, sophisticated layout with precise lines and circles
        - Space/science aesthetic with a contemporary feel
        - Typography integrated into the geometric design

        3. Modern Art Gallery Exhibition (모던 아트 갤러리 전시회)
        - High-end museum exhibition poster style
        - Clean, sophisticated composition with a focus on "Art as Hero"
        - Generous negative space (white or solid color) for a premium feel
        - Typography: Elegant, minimal, and professional (often sans-serif)
        - Layout: Asymmetric text placement (e.g., small text at bottom corners) to let the artwork breathe
        - Vibe: Cultural, expensive, sophisticated, "Picture-like"

        4. Cinematic Sci-Fi & Tech Art (시네마틱 SF & 테크 아트)
        - Grand scale composition with dark backgrounds and glowing elements
        - High-tech aesthetic: blueprints, neon lines, geometric wireframes (like the rocket reference)
        - Dramatic lighting and cinematic perspective (looking up at a massive structure)
        - Typography: Integrated into the tech lines or bold cinematic title
        - Vibe: "Blockbuster movie poster", "Futuristic", "Grand", "Cool"

        CRITICAL REQUIREMENTS FOR ALL 4 CONCEPTS:
        - **Typography Size:** MUST NOT exceed 25% of the total poster area. (Keep it elegant)
        - **LAYOUT DIVERSITY:** DO NOT default to centered text for all posters.
        - **Style 3 (Gallery):** Use asymmetric, minimal text placement.
        - **Style 4 (Sci-Fi):** Use bold, cinematic text placement.
        - ARTISTIC and ILLUSTRATIVE styles ONLY (avoid photorealistic approaches)
        - Korean text ONLY (NO English text whatsoever)
        - Creative, artistic Korean lettering integrated naturally
        - Premium festival poster design with artistic merit
        
        Focus on ARTISTIC ILLUSTRATION rather than photography or realism.

        """
        
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo", 
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        
        return json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"    ❌ 프롬프트 생성 오류: {e}")
        return {"error": str(e)}