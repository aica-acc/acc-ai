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

        3. Retro Vintage Illustration (레트로 빈티지 일러스트)
        - Warm, nostalgic illustration style with vintage poster aesthetics
        - Hand-drawn feel with rich textures and classic compositions
        - Traditional color palettes (navy, cream, warm tones)
        - Storytelling elements with silhouettes or vintage scenes

        4. Abstract Flowing Art with Symbolic Elements (추상적 아트 + 상징 요소)
        - Bold organic shapes with flowing curves, waves, and abstract patterns
        - Festival's symbolic elements subtly integrated into the abstract composition
        - Examples: Santa hat silhouette in flowing ribbons, cherry blossom shapes in waves, musical notes in curves
        - Vibrant, energetic color combinations with smooth gradients
        - Balance between abstract art and recognizable festival symbols (70% abstract, 30% symbolic)
        - Typography flowing naturally with the abstract shapes

        CRITICAL REQUIREMENTS FOR ALL 4 CONCEPTS:
        - Typography should be 25-35% of the poster (NOT more than 40%)
        - ARTISTIC and ILLUSTRATIVE styles ONLY (avoid photorealistic approaches)
        - Korean text ONLY (NO English text whatsoever)
        - Creative, artistic Korean lettering integrated naturally
        - Premium festival poster design with artistic merit
        - Each concept must be visually distinct and radically different

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