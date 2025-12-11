from fastapi import APIRouter, HTTPException
from app.domain.report.report_model import ReportRequest
from app.service.report.report_generator import generate_report_text

router = APIRouter(prefix="/report", tags=["Report Generation"])

# 1. 📰 기사형 보도자료 생성
@router.post("/article")
async def generate_article(request: ReportRequest):
    try:
        print("🚀 [AI] 기사(Article) 생성 요청 수신")
        # 로직에서는 'press' 타입을 사용하여 생성
        content = generate_report_text("press", request.metadata)
        return {"status": "success", "type": "article", "content": content}
    except Exception as e:
        print(f"❌ [AI] 기사 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 2. 📢 공식 공고문 생성
@router.post("/notice")
async def generate_notice(request: ReportRequest):
    try:
        print("🚀 [AI] 공고문(Notice) 생성 요청 수신")
        content = generate_report_text("notice", request.metadata)
        return {"status": "success", "type": "notice", "content": content}
    except Exception as e:
        print(f"❌ [AI] 공고문 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 3. 📱 SNS 홍보글 생성
@router.post("/sns")
async def generate_sns(request: ReportRequest):
    try:
        print("🚀 [AI] SNS 홍보글 생성 요청 수신")
        content = generate_report_text("sns", request.metadata)
        return {"status": "success", "type": "sns", "content": content}
    except Exception as e:
        print(f"❌ [AI] SNS 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 4. 📦 미디어 키트(패키지) 생성
@router.post("/package")
async def generate_package(request: ReportRequest):
    try:
        print("🚀 [AI] 패키지(Package) 생성 요청 수신")
        # 로직에서는 'package' (또는 kit) 타입을 사용
        content = generate_report_text("package", request.metadata)
        return {"status": "success", "type": "package", "content": content}
    except Exception as e:
        print(f"❌ [AI] 패키지 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))