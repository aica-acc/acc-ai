# app.py (v29: '하이브리드 편집기' 아키텍처)

import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask import send_from_directory

# ----------------------------------------------------
# 1. '엔진' 파일들을 import (⭐️ v17/v29 호환)
# ----------------------------------------------------
try:
    import pdf_tools           # (v17: 문서 분석)
    import poster_generator    # (v29: 스타일 가이드 제안)
    import trend_analyzer      # (CSV 내부 DB)
    import image_generator     # (v29: 텍스트 없는 배경 생성)
    import trend_search        # (v17: 외부 트렌드)
except ImportError as e:
    print(f"🚨 [app.py] 치명적 오류: 모듈 import 실패! {e}")
    exit()

# ----------------------------------------------------
# 2. Flask 앱 생성 및 CORS 설정
# ----------------------------------------------------
app = Flask(__name__)
# ( ... CORS 설정 동일 ... )
CORS(app, resources={
    r"/analyze": {"origins": ["http://localhost:3000", "http://localhost:5173", "http://localhost:5175"]},
    r"/generate-prompt": {"origins": ["http://localhost:3000", "http://localhost:5173", "http://localhost:5175"]},
    r"/create-image": {"origins": ["http://localhost:3000", "http://localhost:5173", "http://localhost:5175"]},
    r"/images/*": {"origins": ["http://localhost:3000", "http://localhost:5173", "http://localhost:5175"]} 
}) 

# ----------------------------------------------------
# [API 1] ⭐️ 1단계 UI: "분석" 버튼용 (v17 - 변경 없음)
# ----------------------------------------------------
@app.route("/analyze", methods=["POST"])
def handle_analysis_request():
    print("\n--- [Flask 서버] /analyze (1단계 분석 v17) 요청 수신 ---")
    # ( ... v17 코드와 100% 동일 ... )
    temp_file_path = None 
    try:
        user_theme = request.form.get('theme')
        user_keywords_str = request.form.get('keywords')
        user_title = request.form.get('title')
        file = request.files.get('file')
        if not all([user_theme, user_keywords_str, user_title, file]):
            return jsonify({"status": "error", "message": "필수 입력값이 누락되었습니다."}), 400
        original_filename = file.filename
        _, file_extension = os.path.splitext(original_filename)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        temp_file_path = os.path.join(script_dir, f"temp_uploaded_file{file_extension}")
        file.save(temp_file_path)
        user_keywords_list = [k.strip() for k in user_keywords_str.split(',')]
        final_response_to_frontend = {}
        pdf_data = pdf_tools.analyze_pdf(temp_file_path)
        final_response_to_frontend["analysis_summary"] = pdf_data
        if "error" in pdf_data:
            raise Exception(f"PDF 분석 실패: {pdf_data['error']}")
        keywords_from_pdf = pdf_data.get("visualKeywords", [])
        base_keywords = list(dict.fromkeys(user_keywords_list + keywords_from_pdf))
        expanded_keywords = pdf_tools.expand_keywords_with_ai(base_keywords)
        final_response_to_frontend["expanded_keywords"] = expanded_keywords
        poster_trend_data = trend_analyzer.get_poster_trends(expanded_keywords) 
        final_response_to_frontend["poster_trend_report"] = poster_trend_data
        main_keyword = user_keywords_list[0] if user_keywords_list else keywords_from_pdf[0] if keywords_from_pdf else "축제"
        google_trend_data = trend_search.get_google_trends(base_keywords)
        final_response_to_frontend["google_trend_summary"] = google_trend_data
        naver_datalab_data = trend_search.get_naver_datalab_trend(main_keyword)
        final_response_to_frontend["naver_datalab_data"] = naver_datalab_data
        strategy_query = f"{main_keyword} 홍보 방법"
        naver_search_data = trend_search.get_naver_search_content(strategy_query)
        final_response_to_frontend["naver_search_data"] = naver_search_data
        report_3_json = poster_generator.create_strategy_report(
            user_theme, pdf_data, poster_trend_data,   
            google_trend_data, naver_datalab_data, naver_search_data    
        )
        final_response_to_frontend["strategy_report"] = report_3_json
        if "error" in report_3_json:
            raise Exception(f"전략 보고서 생성 실패: {report_3_json['error']}")
        print("--- ✅ [Flask 서버] 1단계 '분석' (v17 리팩토링) 완료 ---")
        final_response_to_frontend["status"] = "success"
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return jsonify(final_response_to_frontend)
    except Exception as e:
        print(f"🚨 [Flask 서버] /analyze 오류: {e}")
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------------------------------------------
# [API 2] ⭐️ 2단계 UI: "AI 프롬프트 생성" 버튼용 (v29)
# ----------------------------------------------------
@app.route("/generate-prompt", methods=["POST"])
def handle_prompt_generation():
    print("\n--- [Flask 서버] /generate-prompt (2단계 v29) 요청 수신 ---")
    
    try:
        data = request.json
        user_theme = data.get('theme')
        analysis_summary = data.get('analysis_summary')
        poster_trend_report = data.get('poster_trend_report')
        strategy_report = data.get('strategy_report') 

        if not all([user_theme, analysis_summary, poster_trend_report, strategy_report]):
             return jsonify({"status": "error", "message": "1단계 분석 데이터(summary, trend_report, strategy_report)가 누락되었습니다."}), 400

        print("    [1/1] AI 프롬프트 시안 (v29 - 스타일 가이드) 생성 시작...")
        
        prompt_options_data = poster_generator.create_master_prompt(
            user_theme, 
            analysis_summary,
            poster_trend_report,
            strategy_report
        )
        if "error" in prompt_options_data:
            raise Exception(f"마스터 프롬프트 생성 실패: {prompt_options_data['error']}")
        
        print("--- ✅ [Flask 서버] 2단계 '프롬프트 생성' 완료 ---")
        return jsonify({"status": "success", "prompt_options_data": prompt_options_data})

    except Exception as e:
        print(f"🚨 [Flask 서버] /generate-prompt 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------------------------------------------
# [API 3] ⭐️ 3단계 UI: "홍보물 생성" 버튼용 (⭐️ v29 - 하이브리드 ⭐️)
# ----------------------------------------------------
@app.route("/create-image", methods=["POST"])
def handle_image_creation():
    """
    [v29 - 하이브리드] 
    1. '텍스트 없는' 배경 생성 (Dreamina)
    2. '정확한 한글' 추출 (Python)
    3. '스타일 가이드' + '배경 URL' + '한글 JSON' 3종 세트를 React로 반환
    """
    print("\n--- [Flask 서버] /create-image (3단계 최종 생성 v29 - 하이브리드) 요청 수신 ---")
    
    try:
        data = request.json
        
        # ⭐️ [v29] Front-end는 1단계 요약본과 2단계 시안을 모두 전달
        selected_prompt_data = data.get('selected_prompt') 
        analysis_summary = data.get('analysis_summary') # ⭐️ (텍스트 추출용)

        if not selected_prompt_data or not analysis_summary:
             return jsonify({"status": "error", "message": "필수 데이터(selected_prompt, analysis_summary)가 누락되었습니다."}), 400
        
        # ⭐️ [v29] 2단계 시안에서 4가지 핵심 정보를 추출
        background_prompt = selected_prompt_data.get('visual_prompt_for_background')
        style_guide = selected_prompt_data.get('suggested_text_style')
        width = selected_prompt_data.get('width')
        height = selected_prompt_data.get('height')

        if not all([background_prompt, style_guide, width, height]):
             return jsonify({"status": "error", "message": "시안 객체에 v29 필수 정보(프롬프트, 가이드, 규격)가 없습니다."}), 400

        # --- 1. (AI) '텍스트 없는' 배경 생성 ---
        print(f"    [1/3] 'image_generator' (v29 - {width}x{height} 배경) 엔진 호출 시작...")
        output_filename = f"background_final_{width}x{height}.png"
        
        bg_result = image_generator.create_background_image_v29(
            background_prompt,
            width,
            height,
            output_filename
        )
        if "error" in bg_result:
            raise Exception(bg_result['error'])
        
        image_url = f"http://{request.host.split(':')[0]}:5000/images/{output_filename}"
        print(f"    [1/3] '배경' 생성 완료: {image_url}")

        # --- 2. (Python) '정확한 한글' 추출 ---
        print(f"    [2/3] 1단계 'analysis_summary'에서 '정확한 한글' 추출 중...")
        text_data = {
            "title": analysis_summary.get("title", "제목 없음"),
            "date": analysis_summary.get("date", "날짜 정보 없음"),
            "location": analysis_summary.get("location", "장소 정보 없음"),
            "programs": (analysis_summary.get("programs", [])[:2]) # (예: 핵심 프로그램 2개)
        }
        print(f"    [2/3] '한글' 추출 완료.")
        
        # --- 3. (React) '3종 세트' 반환 ---
        print("--- ✅ [Flask 서버] 3단계 '하이브리드 데이터' 생성 완료 ---")
        
        return jsonify({
            "status": "success",
            "image_url": image_url,       # 1. '텍스트 없는' 배경
            "text_data": text_data,       # 2. '정확한 한글'
            "style_guide": style_guide    # 3. 'AI 스타일 가이드'
        })

    except Exception as e:
        print(f"🚨 [Flask 서버] /create-image 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ----------------------------------------------------
# [API 4] 이미지 파일 접근용 URL
# ----------------------------------------------------
@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(os.path.dirname(__file__), filename)

# ----------------------------------------------------
# 5. 서버 실행 
# ----------------------------------------------------
if __name__ == "__main__":
    print("--- 🚀 FestGen AI (v30.1 - '하이브리드 편집기' / Reloader OFF) 백엔드 서버를 [ http://127.0.0.1:5000 ] 에서 시작합니다 ---")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False) # ⭐️ 이 부분이 중요합니다.