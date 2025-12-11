import time
import random
import pandas as pd
from typing import List, Dict, Any
from datetime import date, timedelta
from pytrends.request import TrendReq
from dotenv import load_dotenv

load_dotenv()

# ---------------------------
# Pytrends 초기화
# ---------------------------
_PT = TrendReq(
    hl="ko-KR",
    tz=540,
    retries=3,
    backoff_factor=0.1,
)

# ============================================================
#  Google Trends - 오늘 기준 정확한 1년 범위
# ============================================================
def get_google_trends_1year(
    keyword: str,
    festival_title: str,
    festival_start_date: str
) -> List[Dict[str, Any]]:

    # ✔ 오늘 기준 1년 계산
    today = date.today()
    one_year_ago = today - timedelta(days=365)

    # Google Trends 날짜 형식: "YYYY-MM-DD YYYY-MM-DD"
    timeframe = f"{one_year_ago.strftime('%Y-%m-%d')} {today.strftime('%Y-%m-%d')}"

    try:
        # 페이로드 생성 (메인 키워드만)
        _PT.build_payload(
            kw_list=[keyword],
            timeframe=timeframe,
            geo="KR"
        )

        # 데이터 요청
        iot = None
        for i in range(4):
            try:
                iot = _PT.interest_over_time()
                break
            except Exception as e:
                if "429" in str(e):
                    time.sleep((2 ** i) + random.uniform(0, 0.5))
                    continue
                print("❗ Google Trends 오류:", e)
                return []

        if iot is None or iot.empty:
            return []

        # isPartial 제거
        iot = iot.drop(
            columns=[c for c in iot.columns if "ispartial" in str(c).lower()],
            errors="ignore"
        )

        # 메인 키워드 기준 데이터 추출
        series = iot.iloc[:, 0]

        # period/ratio 변환
        graph_data = []
        for idx, value in series.items():
            graph_data.append({
                "period": idx.strftime("%Y-%m-%d"),
                "ratio": int(value) if pd.notnull(value) else 0
            })

        return graph_data

    except Exception as e:
        print("❗ Google Trends 전체 오류:", e)
        return []


