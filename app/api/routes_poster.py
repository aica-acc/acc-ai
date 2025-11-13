import os
import json
import tempfile
from fastapi import APIRouter, Form, File, UploadFile, HTTPException

# ⭐️ v31: Pydantic 모델 import
from app.domain.poster import poster_model as models

# ----------------------------------------------------
# 1. '엔진' 파일들을 import (v29/v30.1)
# ----------------------------------------------------
try:
    from app.tools import pdf_tools           # (v17: 문서 분석)
    from app.service.poster import poster_generator    # (v30.1: '그림같은' 스타일 가이드 제안)
    from app.service.poster import trend_analyzer      # (CSV 내부 DB)
    from app.service.poster import image_generator     # (v29: '텍스트 없는' 배경 생성)
    from app.service.poster import trend_search        # (v17: 외부 트렌드)
except ImportError as e:
    print(f"🚨 [router.py] 치명적 오류: 모듈 import 실패! {e}")
    exit()

# ----------------------------------------------------
# 2. FastAPI 라우터 생성
# ----------------------------------------------------
router = APIRouter(prefix="/poster", tags=["Poster Generation (v29/v30.1)"])
SCRIPT_DIR = os.path.dirname(__file__)

# ----------------------------------------------------
# [API 1] ⭐️ 1단계 UI: "분석" 버튼용 (v17 - FastAPI)
# ----------------------------------------------------
@router.post("/analyze")
async def handle_analysis_request(
    theme: str = Form(...),
    keywords: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...)
):
    print("\n--- [FastAPI 서버] /analyze (1단계 분석 v17) 요청 수신 ---")
    
    # 30년 경력자로서, '임시 파일'은 'with' 구문으로 안전하게 처리합니다.
    try:
        _, file_extension = os.path.splitext(file.filename)
        # 'poster_service' 폴더 내에 임시 파일 생성
        temp_file_path = os.path.join(SCRIPT_DIR, f"temp_uploaded_file{file_extension}")

        with open(temp_file_path, "wb") as temp_file:
            temp_file.write(await file.read())
        
        user_keywords_list = [k.strip() for k in keywords.split(',')]
        
        final_response_to_frontend = {}

        # (v17 로직 100% 동일)
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
            theme, pdf_data, poster_trend_data,   
            google_trend_data, naver_datalab_data, naver_search_data    
        )
        final_response_to_frontend["strategy_report"] = report_3_json
        if "error" in report_3_json:
            raise Exception(f"전략 보고서 생성 실패: {report_3_json['error']}")
        
        print("--- ✅ [FastAPI 서버] 1단계 '분석' (v17 리팩토링) 완료 ---")
        final_response_to_frontend["status"] = "success"
        
        return final_response_to_frontend

    except Exception as e:
        print(f"🚨 [FastAPI 서버] /analyze 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path) # 임시 파일 삭제

# ----------------------------------------------------
# [API 2] ⭐️ 2단계 UI: "AI 프롬프트 생성" 버튼용 (v30.1)
# ----------------------------------------------------
@router.post("/generate-prompt")
async def handle_prompt_generation(body: models.GeneratePromptRequest):
    print("\n--- [FastAPI 서버] /generate-prompt (2단계 v30.1) 요청 수신 ---")
    
    try:
        print("    [1/1] AI 프롬프트 시안 (v30.1 - '포스터 디자인' 강제) 생성 시작...")
        
        prompt_options_data = poster_generator.create_master_prompt(
            body.theme, 
            body.analysis_summary,
            body.poster_trend_report,
            body.strategy_report,
            body.selected_formats
        )
        if "error" in prompt_options_data:
            raise Exception(f"마스터 프롬프트 생성 실패: {prompt_options_data['error']}")
        
        print("--- ✅ [FastAPI 서버] 2단계 '프롬프트 생성' 완료 ---")
        return {"status": "success", "prompt_options_data": prompt_options_data}

    except Exception as e:
        print(f"🚨 [FastAPI 서버] /generate-prompt 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------
# [API 3] ⭐️ 3단계 UI: "홍보물 생성" 버튼용 (v29 - 하이브리드)
# ----------------------------------------------------
@router.post("/create-image")
async def handle_image_creation(body: models.CreateImageRequest):
    """
    [v29 - 하이브리드] 
    1. '텍스트 없는' 배경 생성 (Dreamina)
    2. '정확한 한글' 추출 (Python)
    3. '스타일 가이드' + '배경 URL' + '한글 JSON' 3종 세트를 반환
    """
    print("\n--- [FastAPI 서버] /create-image (3단계 최종 생성 v29 - 하이브리드) 요청 수신 ---")
    
    try:
        # ⭐️ v31: Pydantic 모델(body)에서 v29 데이터를 바로 추출
        selected_prompt_data = body.selected_prompt
        analysis_summary = body.analysis_summary
        
        background_prompt = selected_prompt_data.visual_prompt_for_background
        style_guide = selected_prompt_data.suggested_text_style
        width = selected_prompt_data.width
        height = selected_prompt_data.height

        # --- 1. (AI) '텍스트 없는' 배경 생성 ---
        print(f"    [1/3] 'image_generator' (v29 - {width}x{height} 배경) 엔진 호출 시작...")
        
        # ⭐️ 'poster_service' 폴더 내에 이미지 저장
        output_filename = f"background_final_{width}x{height}.png"
        output_filepath = os.path.join(SCRIPT_DIR, output_filename)
        
        bg_result = image_generator.create_background_image_v29(
            background_prompt,
            width,
            height,
            output_filepath # ⭐️ v31: 전체 경로 전달
        )
        if "error" in bg_result:
            raise Exception(bg_result['error'])
        
        # ⭐️ v31: FastAPI는 Request 객체에서 host를 가져와야 함 (main.py에서 마운트한 경로)
        image_url = f"/images/{output_filename}" # ⭐️ main.py의 /images 경로와 일치
        print(f"    [1/3] '배경' 생성 완료: {image_url}")

        # --- 2. (Python) '정확한 한글' 추출 ---
        print(f"    [2/3] 1단계 'analysis_summary'에서 '정확한 한글' 추출 중...")
        text_data = {
            "title": analysis_summary.get("title", "제목 없음"),
            "date": analysis_summary.get("date", "날짜 정보 없음"),
            "location": analysis_summary.get("location", "장소 정보 없음"),
            "programs": (analysis_summary.get("programs", [])[:2])
        }
        print(f"    [2/3] '한글' 추출 완료.")
        
        # --- 3. (React) '3종 세트' 반환 ---
        print("--- ✅ [FastAPI 서버] 3단계 '하이브리드 데이터' 생성 완료 ---")
        
        return {
            "status": "success",
            "image_url": image_url,       # 1. '텍스트 없는' 배경
            "text_data": text_data,       # 2. '정확한 한글'
            "style_guide": style_guide    # 3. 'AI 스타일 가이드'
        }

    except Exception as e:
        print(f"🚨 [FastAPI 서버] /create-image 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))