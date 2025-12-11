import os
import json
import tempfile
from fastapi import APIRouter, Form, File, UploadFile, HTTPException

# ⭐️ v31: Pydantic 모델 import
from app.domain.poster import poster_model as models

# ----------------------------------------------------
# 1. '엔진' 파일들을 import (v29/v30.1)
# ----------------------------------------------------
# ----------------------------------------------------
# 1. 기획서(PDF) 분석 모듈 불러오기 (v17)
# ----------------------------------------------------
try:
    from app.tools.proposal import pdf_tools
except ImportError as e:
    print(f"❌ [router/analyze] pdf_tools import 실패: {e}")
    raise e

# ----------------------------------------------------
# 2. 라우터 설정
# ----------------------------------------------------
router = APIRouter(
    prefix="/analyze",
    tags=["Proposal Analysis"]
)

SCRIPT_DIR = os.path.dirname(__file__)


# ----------------------------------------------------
# [API] 기획서 분석 전용 엔드포인트 (v31)
# ----------------------------------------------------
@router.post("/proposal")
async def analyze_proposal(
    title: str = Form(...),     # DB 저장용이므로 입력은 받지만 응답에는 포함 X
    theme: str = Form(...),
    keywords: str = Form(...),
    file: UploadFile = File(...)
):
    print("\n--- [FastAPI] ▶ /analyze/proposal 요청 수신 ---")

    # 1) 업로드 파일 검증
    if file.content_type not in ["application/pdf"]:
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

    # 2) 임시 파일 경로 생성
    _, ext = os.path.splitext(file.filename)
    temp_filename = f"temp_proposal{ext}"
    temp_path = os.path.join(SCRIPT_DIR, temp_filename)

    try:
        # 3) PDF 파일을 서버에 임시 저장
        with open(temp_path, "wb") as f:
            f.write(await file.read())

        print(f"📄 임시 파일 저장 완료 → {temp_path}")

        # 4) PDF 분석 수행
        pdf_data = pdf_tools.analyze_pdf(temp_path)
        if "error" in pdf_data:
            raise Exception(pdf_data["error"])

        print("📊 PDF 분석 완료")

        # ----------------------------------------------------
        # RESPONSE (최소 구조)
        # ----------------------------------------------------
        return {
            "status": "success",
            "analysis": pdf_data  # 프론트는 이 분석 데이터만 사용
        }

    except Exception as e:
        print(f"❌ 분석 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 5) 임시 파일 삭제
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"🧹 임시 파일 삭제 완료: {temp_path}")
        except Exception as cleanup_error:
            print(f"⚠ 임시 파일 삭제 실패: {cleanup_error}")
