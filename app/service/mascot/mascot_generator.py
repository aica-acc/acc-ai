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
        You are a world-class Character Designer. Design 4 distinct Mascot Character concepts for a festival.

        [CRITICAL RULES]
        1. **Mascot Aesthetics:** The image MUST visually function as a **festival mascot character**. 
           - **Focus on the character design.** Cute, friendly, or symbolic characters suitable for a festival.
           - **Do NOT describe a complex background.** Keep the background simple or transparent-friendly.
        2. **English Only:** `visual_prompt` MUST be in English.
        3. **No Text:** Do NOT include text in the visual prompt unless it's part of the character's clothing or accessories (and keep it minimal).
        
        [JSON FORMAT]
        {{
            "master_prompt": {{
                "prompt_options": [
                    {{
                        "style_name": "Concept Name (e.g., Cute Animal, Robot, Traditional)",
                        "text_content": {{ "title": "", "date_location": "" }}, 
                        "visual_prompt": "A cute mascot character for... (English description)" 
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
