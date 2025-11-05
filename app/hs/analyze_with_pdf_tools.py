# -*- coding: utf-8 -*-
"""
콘솔 입력 -> pdf_tools.analyze_pdf() -> 분석 JSON 생성
'현재 파일과 같은 폴더의 pdf_tools.py'만 강제로 로드합니다 (이름 충돌/경로 꼬임 방지).
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

    print("\n[1/1] 기획서 분석 중 ...")
    try:
        analysis = pdf_tools.analyze_pdf(pdf_path)
    except TypeError:
        # 혹시 시그니처가 다르면 pdf_path만 넣어 호출
        analysis = pdf_tools.analyze_pdf(pdf_path)
    except Exception as e:
        print(f"[실패] analyze_pdf 실행 오류: {e}")
        return

    if isinstance(analysis, dict) and analysis.get("error"):
        print(f"[실패] 분석 오류: {analysis['error']}")
        return

    out_path = OUT_DIR / f"{_safe_filename(festival)}_analysis.json"
    payload = {
        "input": {
            "pdf_path": pdf_path,
            "festival_name": festival,
            "intent": intent,
            "keywords": keywords
        },
        "analysis": analysis
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] 분석 JSON 저장: {out_path}\n")

if __name__ == "__main__":
    main()
