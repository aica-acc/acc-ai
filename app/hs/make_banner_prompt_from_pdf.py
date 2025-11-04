# -*- coding: utf-8 -*-
"""
콘솔 입력 -> pdf_tools.analyze_pdf() -> 현수막(5.55:1) 배경 프롬프트 JSON 생성
'현재 파일과 같은 폴더의 pdf_tools.py'만 강제로 로드합니다 (이름 충돌/경로 꼬임 방지).
"""

import os, sys, re, json
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
    return s[:80] if s else "banner_prompt"

def _to_keyword_list(raw: str):
    parts = [p.strip() for p in re.split(r"[,\n]+", raw) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in raw.split() if p.strip()]
    return parts

def build_banner_prompt(festival_name: str, intent: str, keywords, analysis: dict):
    def g(k, d=""):
        v = analysis.get(k)
        return v if v else d

    mood      = g("mood", "축제, 따뜻함, 가족 친화적")
    palette   = g("colorPalette", "레드·그린·골드 + 화이트 대비")
    imagery   = g("imagery", "따뜻한 겨울 야경, 라이트 트레일, 산타/눈/별 중 1~2개 선택")
    typography= g("typography", "가독성 높은 산세리프")
    hl        = analysis.get("highlights", [])
    hl_str    = ", ".join(hl) if isinstance(hl, list) else (hl or "아이 친화 요소, 포토존")

    banner_prompt = f"""[UNIVERSAL BANNER BACKGROUND PROMPT / 현수막 배경 전용]

Goal / 목적:
- 5.55:1 가로 현수막 '배경' 이미지를 생성합니다. (텍스트 금지)
- 상하 8%, 좌우 5% 안전 여백. 중앙 또는 좌측 60% 영역에 타이틀용 빈 공간 확보.
- 브랜드 일관성: 팔레트 {palette} | 분위기 {mood} | 서체 감성 {typography}
- 피해야 할 것: 과도한 디테일, 저해상도 아이콘, 워터마크, 테두리 잘림, 텍스트 렌더링.

Festival / 축제명: {festival_name}
Intent / 기획의도: {intent}
Keywords / 키워드: {", ".join(keywords)}
Aspect Ratio / 비율: 5.55:1 (예: 5550×1000 또는 5000×900)

Visual Guide / 시각 가이드:
- 주요 요소: {hl_str}
- 이미지 톤: {imagery}
- 컬러 팔레트: {palette}
- 안전 여백: 상하 8%, 좌우 5%

Output / 출력:
- 5.55:1 비율의 고해상도 '배경' 이미지 1장 (텍스트 없음).
"""
    text_layout_plan = {
        "title":     analysis.get("title") or festival_name,
        "subtitle":  intent,
        "datetime":  analysis.get("date", ""),
        "location":  analysis.get("location", ""),
        "meta":      " | ".join(analysis.get("highlights", [])) if isinstance(analysis.get("highlights"), list) else "",
        "language":  "Korean",
    }
    return banner_prompt, text_layout_plan

# ------------- 메인 -------------
def main():
    print("=== 현수막 프롬포트 JSON 생성기 ===")
    pdf_path = input("1) 기획서 파일 경로 (.pdf / .docx / .hwp): ").strip().strip('"')
    if not pdf_path:
        print("[중단] 파일 경로가 비어 있습니다."); return
    festival = input("2) 축제명: ").strip()
    intent   = input("3) 기획의도: ").strip()
    kw_raw   = input("4) 키워드(쉼표로 구분): ").strip()
    keywords = _to_keyword_list(kw_raw)

    print("\n[1/2] 기획서 분석 중 ...")
    analysis = pdf_tools.analyze_pdf(pdf_path)
    if isinstance(analysis, dict) and analysis.get("error"):
        print(f"[실패] 분석 오류: {analysis['error']}"); return

    print("[2/2] 현수막 프롬포트 구성 ...")
    prompt, text_plan = build_banner_prompt(festival, intent, keywords, analysis)

    out_path = OUT_DIR / f"{_safe_filename(festival)}_banner_analysis_and_prompt.json"
    payload = {
        "input": {"pdf_path": pdf_path, "festival_name": festival, "intent": intent, "keywords": keywords},
        "analysis": analysis,
        "banner": {"ratio": "5.55:1", "prompt": prompt, "text_layout_plan": text_plan},
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[완료] JSON 저장: {out_path}\n")

if __name__ == "__main__":
    main()
