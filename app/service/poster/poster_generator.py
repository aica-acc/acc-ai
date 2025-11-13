# poster_generator.py (v30.1: '포스터 디자인' 강제 가드레일 + v29 '스타일 가이드')

import json
import openai
import os
from dotenv import load_dotenv

# --- OpenAI API 키 설정 (GPT-4 프롬프트 번역용) ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[poster_generator] OPENAI_API_KEY를 찾을 수 없습니다.")
else:
    openai.api_key = OPENAI_API_KEY

# 규격
FORMAT_MAP = {
    "9:16": {"width": 896, "height": 1536, "title": "모바일 (9:16) 시안"},
    "1:1": {"width": 1024, "height": 1024, "title": "인스타그램 (1:1) 시안"},
    "3:4": {"width": 864, "height": 1152, "title": "A3 (3:4) 시안"},
    "16:9": {"width": 1536, "height": 864, "title": "와이드 (16:9) 시안"}
}

# ----------------------------------------------------
# [엔진 기능 1] 1단계: '전략 보고서' 생성기 
# ----------------------------------------------------
def create_strategy_report(
    user_theme, 
    pdf_data_dict, 
    poster_trend_data, 
    google_trend_data,
    naver_datalab_data,
    naver_search_data
):
    """
    [v17] (기획서 + 내부DB + 네이버 API 2종 + 테마)를 '융합'하여
    'AI 전략 보고서'를 생성합니다.
    """
    print(f"  [poster_generator] AI 전략 보고서(보고서 3 - v17 융합) 생성 시작...")
    try:
        # ( ... v17 코드와 100% 동일 ... )
        pdf_json_string = json.dumps(pdf_data_dict, ensure_ascii=False, indent=2)
        internal_trend_string = json.dumps(poster_trend_data, ensure_ascii=False, indent=2)
        google_trend_string = json.dumps(google_trend_data, ensure_ascii=False, indent=2)
        naver_datalab_string = json.dumps(naver_datalab_data, ensure_ascii=False, indent=2)
        naver_search_string = json.dumps(naver_search_data, ensure_ascii=False, indent=2)
        system_prompt = """
        당신은 대한민국 최고의 축제 홍보 '아트 디렉터'이자 '트렌드 분석가'입니다.
        당신의 임무는 5가지의 분리된 정보를 '융합'하여, 전문가 수준의 '종합 전략 보고서'를 작성하는 것입니다.
        [당신이 가진 5가지 정보]
        1. [기획서 정보]: 클라이언트의 핵심 요구사항
        2. [내부 DB 분석]: 과거 포스터 데이터 (CSV 분석 결과)
        3. [실시간 트렌드 (Naver DataLab)]: '검색량 추이' (JSON).
        4. [실시간 트렌드 (Naver Search)]: '홍보 방법'에 대한 블로그/뉴스 검색 결과 ('요약글' 리스트).
        5. [실시간 트렌드 (Google)]: (참고용. 'error'가 있다면 무시)
        [보고서 작성 규칙 (매우 중요)]
        1. 'strategy_text'는 이 모든 정보를 융합한 '최종 분석 리포트'입니다.
        2. [Naver DataLab]의 'ratio' 값을 분석하여, "최근 검색량이 상승/하락 중"인지 반드시 언급하십시오.
        3. [Naver Search]의 'snippet'(요약글)을 분석하여, "화제가 되는 최신 홍보 전략"을 1~2개 찾아내어 언급하십시오.
        4. [내부 DB 분석]의 'top_creativity_example'(과거 스타일)과 2, 3번의 '실시간 트렌드'를 '비교 분석' 하십시오.
        5. 데이터를 나열하지 말고, '해석'하여 통찰력(Insight)을 담은 전략을 3~5문장으로 제안하십시오.
        [JSON 응답 형식]
        {
          "strategy_text": "(여기에 'Naver 검색량', 'Naver 홍보 방법', '내부 DB'를 모두 비교 분석한 상세한 전략 보고서 텍스트 작성...)",
          "proposed_content": { "title": "(선별된 축제 제목)", "subtitle": "(AI가 생성한 감성 부제)", "date_location": "(선별된 날짜 및 장소)", "programs_or_copy": "(스타일에 맞는 프로그램 리스트 또는 홍보 문구)", "sponsors": "(선별된 주최/주관)" }
        }
        """
        user_prompt = f"""
        [1. 사용자 핵심 테마]
        {user_theme}
        [2. 기획서 정보 (JSON)]
        {pdf_json_string}
        [3. 내부 DB 분석 (CSV 분석 결과)]
        {internal_trend_string}
        [4. 실시간 트렌드 (Naver DataLab - 검색량)]
        {naver_datalab_string}
        [5. 실시간 트렌드 (Naver Search - 관련 내용)]
        {naver_search_string}
        [6. 실시간 트렌드 (Google)]
        {google_trend_string}
        ---
        위 6가지 정보를 모두 '융합'하고 '비교 분석'하여, [JSON 응답 형식]에 맞는 '종합 전략 보고서'를 생성해 주십시오.
        """
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo", 
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            timeout=60.0
        )
        ai_generated_data = json.loads(response.choices[0].message.content)
        print("    - AI '종합 전략 보고서(v17)' 생성 완료.")
        visual_reference_path = "정보 없음"
        if poster_trend_data.get("status") == "success":
            visual_reference_path = poster_trend_data.get("top_creativity_example", {}).get("file_name", "정보 없음")
        ai_generated_data["visual_reference_path"] = visual_reference_path
        return ai_generated_data
    except Exception as e:
        print(f"    ❌ AI 전략 보고서(v17) 생성 중 오류 발생: {e}")
        return {"error": f"AI 전략 보고서(v17) 생성 오류: {e}"}

# ----------------------------------------------------
# [엔진 기능 2] 2단계: '프롬프트 시안' 생성기 (⭐️ v30.1: '포스터 디자인' 강제 ⭐️)
# ----------------------------------------------------
def create_master_prompt(
    user_theme, 
    analysis_summary,
    poster_trend_report,
    strategy_report,
    selected_formats
):
    """
    [1단계 분석 결과] + [선택된 규격]을 입력받아,
    '선택된 규격'의 개수만큼만 '동적'으로 프롬프트 시안을 생성합니다.
    """
    print(f"  [poster_generator] AI 프롬프트 시안 생성 시작...")
    
    try:
        # --- 1. AI(GPT-4)에게 1단계 분석 결과 전달 ---
        analysis_summary_string = json.dumps(analysis_summary, ensure_ascii=False, indent=2)
        poster_trend_string = json.dumps(poster_trend_report, ensure_ascii=False, indent=2)
        strategy_report_string = json.dumps(strategy_report, ensure_ascii=False, indent=2)

        # --- 2. 'selected_formats' 리스트로 'AI 시안 뼈대'를 동적 생성 ---
        prompt_skeletons = []
        for format_key in selected_formats:
            if format_key in FORMAT_MAP:
                format_data = FORMAT_MAP[format_key]
                prompt_skeletons.append({
                    "style_name": f"AI 제안: {format_data['title']}", # 예: "AI 제안: 모바일 (9:16) 시안"
                    "width": format_data["width"],
                    "height": format_data["height"],
                    "visual_prompt_for_background": "(AI가 이 값을 채울 것입니다)",
                    "suggested_text_style": "(AI가 이 값을 채울 것입니다)"
                })

        # 선택된 유효한 규격이 없으면 오류 반환
        if not prompt_skeletons:
            print("   ❌ 'poster_generator': 유효한 규격이 선택되지 않았습니다.")
            return {"error": "No valid formats selected or provided."}

        # 3. AI 지시문(Prompt)을 파트너님의 '그림같은 느낌' 요구사항에 맞게 
        # F-string을 사용하여 '동적'으로 AI 지시문을 만듭니다

        system_prompt = f"""
        당신은 30년 경력의 아트 디렉터입니다.

        [당신의 임무]
        [1단계 분석 자료] 3개를 입력받아, 요청된 {len(prompt_skeletons)}개의 규격별 시안을 제안해야 합니다.
        각 시안은 '텍스트 없는 배경'과 그 배경에 '매칭되는 텍스트 스타일' 2가지로 구성됩니다.

        [1단계 분석 자료]
        1. [기획서 요약]: 클라이언트의 핵심 요구사항 (타겟 고객, 비주얼 키워드 등)
        2. [내부 DB 분석]: 과거 포스터(CSV) 분석 결과
        3. [최종 융합 보고서]: '실시간 트렌드'와 '홍보 전략'이 포함된 AI의 최종 전략 제안

        [시안 생성 규칙 (매우 중요)]
        1. 모든 스타일 제안은 '사실적인 사진(photorealistic)' 스타일을 '절대' 제안해서는 안 됩니다.
        2. 모든 스타일 제안은 [1단계 분석 자료]를 기반으로, 'illustration', 'graphic design', 'digital art', 'typography', 'abstract', 'minimalist' 카테고리 중에서만 '창의적으로' 해석해야 합니다.
        3. 'visual_prompt_for_background':
           - 'bytedance/dreamina-3.1' 모델이 생성할 '텍스트가 없는(text-free)' 배경 프롬프트입니다.
           - '일러스트'나 '그래픽 디자인' 스타일로 영문으로 묘사되어야 합니다.
        4. 'suggested_text_style':
           - 3번 배경 프롬프트(일러스트/그래픽)와 '매칭'되는 '텍스트 스타일 가이드'입니다. (예: "우아하고 얇은 명조 폰트, 금색")

        [JSON 응답 형식 (⭐️ 요청된 {len(prompt_skeletons)}개 만큼만 생성)]
        {{
          "prompt_options": [
            // (AI가 이 뼈대를 기반으로 {len(prompt_skeletons)}개만큼 생성)
            {json.dumps(prompt_skeletons, indent=2, ensure_ascii=False)}
          ]
        }}
        """
        
        user_prompt = f"""
        [사용자 핵심 테마]
        {user_theme}
        [1. 기획서 요약 (JSON)]
        {analysis_summary_string}
        [2. 내부 DB 분석 (CSV 분석 결과)]
        {poster_trend_string}
        [3. 최종 융합 보고서 (AI 전략 제안)]
        {strategy_report_string}
        ---
        위 3가지 [1단계 분석 자료]를 '반드시' 읽고 '근거'하여, [JSON 응답 형식]에 맞는 '시안'을 생성해 주십시오.
        (⭐️ v31.1 규칙: 요청된 {len(prompt_skeletons)}개의 규격 {selected_formats}에 대해서만 생성해야 합니다.)
        (⭐️ v30.1 규칙: 모든 스타일은 '사진'이 아닌 '일러스트/그래픽 디자인' 중심이어야 합니다.)
        """
        
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4-turbo", 
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            timeout=60.0 
        )
        
        ai_generated_data = json.loads(response.choices[0].message.content)
        print(f"     - AI '{len(prompt_skeletons)}개 동적 규격 시안(v31.1)' 생성 완료.")
        
        return ai_generated_data

    except Exception as e:
        print(f"    ❌ AI 마스터 프롬프트(v30.1) 생성 중 오류 발생: {e}")
        return {"error": f"AI 마스터 프롬프트(v30.1) 생성 오류: {e}"}