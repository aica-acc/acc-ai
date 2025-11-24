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
        3. **Include Text:** The final visual prompt must contain instructions for the English Title and Date to be rendered in the image.
        
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
        Design 4 diverse poster concepts.
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