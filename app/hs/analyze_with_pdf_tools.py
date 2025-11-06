# -*- coding: utf-8 -*-
"""
콘솔 입력 -> pdf_tools.analyze_pdf() -> out/<slug>_analysis.json
추가: trend_tools.generate_trend() -> out/<slug>_trend_analysis.json

'현재 파일과 같은 폴더의 pdf_tools.py'와 'trend_tools.py'만 강제로 로드합니다.
"""

import sys, re, json
from pathlib import Path
import importlib.util as ilu

# ---------------- 경로/출력 ----------------
SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ------------- pdf_tools 강제 로드 -------------
PDF_TOOLS_PATH = SCRIPT_DIR / "pdf_tools.py"
if not PDF_TOOLS_PATH.exists():
    print(f"[에러] {PDF_TOOLS_PATH} 파일이 없습니다.")
    sys.exit(1)

spec = ilu.spec_from_file_location("pdf_tools_local", str(PDF_TOOLS_PATH))
pdf_tools = ilu.module_from_spec(spec)
try:
    spec.loader.exec_module(pdf_tools)  # <-- 무조건 이 파일을 로드
    print(f"[info] using pdf_tools: {PDF_TOOLS_PATH}")
except Exception as e:
    print(f"[에러] pdf_tools 로드 실패: {e}")
    sys.exit(1)

# ------------- trend_tools 강제 로드 (신규) -------------
TREND_TOOLS_PATH = SCRIPT_DIR / "trend_tools.py"
if not TREND_TOOLS_PATH.exists():
    print(f"[경고] {TREND_TOOLS_PATH} 파일이 없어 트렌드 분석을 건너뜁니다.")
    trend_tools = None
else:
    spec2 = ilu.spec_from_file_location("trend_tools_local", str(TREND_TOOLS_PATH))
    trend_tools = ilu.module_from_spec(spec2)
    try:
        spec2.loader.exec_module(trend_tools)  # <-- 현재 폴더의 trend_tools만 로드
        print(f"[info] using trend_tools: {TREND_TOOLS_PATH}")
    except Exception as e:
        print(f"[경고] trend_tools 로드 실패: {e}")
        trend_tools = None

# ------------- 유틸 -------------
def _safe_filename(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "analysis"

def _to_keyword_list(raw: str):
    parts = [p.strip() for p in re.split(r"[,\n]+", raw) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in raw.split() if p.strip()]
    return parts

# ------------- 메인 -------------
def main():
    print("=== 분석 JSON 생성기 (프롬프트 제외) ===")
    pdf_path = input("1) 기획서 파일 경로 (.pdf / .docx / .hwp): ").strip().strip('"')
    if not pdf_path:
        print("[중단] 파일 경로가 비어 있습니다."); return
    festival = input("2) 축제명: ").strip()
    intent   = input("3) 기획의도: ").strip()
    kw_raw   = input("4) 키워드(쉼표로 구분): ").strip()
    keywords = _to_keyword_list(kw_raw)

    print("\n[1/2] 기획서 분석 중 ...")
    try:
        analysis = pdf_tools.analyze_pdf(pdf_path)
    except TypeError:
        analysis = pdf_tools.analyze_pdf(pdf_path)
    except Exception as e:
        print(f"[실패] analyze_pdf 실행 오류: {e}")
        return

    if isinstance(analysis, dict) and analysis.get("error"):
        print(f"[실패] 분석 오류: {analysis['error']}")
        return

    slug = _safe_filename(festival)
    analysis_payload = {
        "input": {
            "pdf_path": pdf_path,
            "festival_name": festival,
            "intent": intent,
            "keywords": keywords
        },
        "analysis": analysis
    }

    # 1) 원래 동작: out/<slug>_analysis.json 저장
    analysis_out = OUT_DIR / f"{slug}_analysis.json"
    with open(analysis_out, "w", encoding="utf-8") as f:
        json.dump(analysis_payload, f, ensure_ascii=False, indent=2)
    print(f"[완료] 분석 JSON 저장: {analysis_out}")

    # 2) 추가: trend_tools가 있으면 트렌드 분석도 생성/저장
    print("[2/2] 트렌드 분석 생성 ...")
    trend_out = OUT_DIR / f"{slug}_trend_analysis.json"
    if trend_tools is None:
        # 모듈이 없으면 에러 JSON이라도 생성(파일 존재 기대 충족)
        with open(trend_out, "w", encoding="utf-8") as f:
            json.dump({"error": "trend_tools.py가 없어 트렌드 분석을 건너뜀"}, f, ensure_ascii=False, indent=2)
        print(f"[경고] trend_tools.py 미존재. 대체 JSON 저장: {trend_out}")
        return

    try:
        trend_obj = trend_tools.generate_trend(festival, intent, keywords, analysis_payload)
    except Exception as e:
        trend_obj = {"error": f"generate_trend 실행 실패: {e}"}

    with open(trend_out, "w", encoding="utf-8") as f:
        json.dump(trend_obj, f, ensure_ascii=False, indent=2)

    if "error" in trend_obj:
        print(f"[경고] 트렌드 분석 실패: {trend_obj['error']}")
    else:
        print(f"[완료] 트렌드 JSON 저장: {trend_out}")

if __name__ == "__main__":
    main()
