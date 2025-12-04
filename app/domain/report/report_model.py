from pydantic import BaseModel
from typing import Dict, Any

class ReportRequest(BaseModel):
    """
    보도자료 생성 요청 데이터 모델
    """
    report_type: str        # press, notice, sns, kit
    metadata: Dict[str, Any] # Java에서 넘겨준 축제 정보 (title, date, location 등)