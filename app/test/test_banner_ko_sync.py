# -*- coding: utf-8 -*-
"""
test_banner_ko_sync.py

목적
- KO 프롬프트가 수정되었을 때만 EN 프롬프트를 자동 갱신한 뒤 Dreamina 생성
- 생성물 경로(artifact_paths)까지 확인

실행
> python app/test/test_banner_ko_sync.py
"""

import os, sys, json
from pathlib import Path

# ---------------- sys.path 루트 주입 ----------------
HERE = Path(__file__).resolve()
for p in [HERE.parent] + list(HERE.parents):
    if (p / "app").is_dir():
        sys.path.insert(0, str(p))
        PROJECT_ROOT = p
        break
else:
    print("[ERROR] 프로젝트 루트를 찾지 못했습니다."); sys.exit(1)

# ---------------- .env 로드 ----------------
try:
    from dotenv import load_dotenv, find_dotenv
    env = find_dotenv(usecwd=True)
    if env: load_dotenv(env, override=False)
    else:
        local_env = PROJECT_ROOT / ".env"
        if local_env.exists(): load_dotenv(local_env, override=False)
except Exception:
    pass
if not os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_API_TOKEN"):
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_TOKEN")

print(f"[i] project root: {PROJECT_ROOT}")
print(f"[i] OPENAI_API_KEY set? {'YES' if os.getenv('OPENAI_API_KEY') else 'NO'}")
print(f"[i] REPLICATE_API_TOKEN set? {'YES' if os.getenv('REPLICATE_API_TOKEN') else 'NO'}\n")

# ---------------- 모듈 임포트 ----------------
from app.service.banner.make_prompt_from_analysis import make_banner_prompt_service
from app.service.banner.make_banner_from_prompt import make_banner_from_prompt_service

def dump(title, obj):
    print(title)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print()

# 샘플 분석 payload
analysis_payload = {
    "p_name": "제7회 담양산타축제",
    "user_theme": "어린아이들의 행복",
    "keywords": ["행복", "미래", "꿈"],
    "festival": {
        "title": "제7회 담양 산타 축제",
        "date": "2025.12.20 ~ 2025.12.21",
        "location": "담양 메타랜드 일원",
        "theme": "가족 참여형 겨울축제",
        "summary": "야간 조명, 포토존, 퍼레이드",
        "visual_keywords": ["산타", "눈", "레드 그린 팔레트", "겨울 야간 조명", "포토존"]
    },
    "analysis": {
        "similarity": 0.86,
        "decision": "accept",
        "original_theme": "어린이 중심 체험형 겨울축제",
        "corrected_theme": "어린아이들의 행복을 강조한 가족 참여형 겨울축제"
    }
}

def to_job(prompt_obj: dict) -> dict:
    return {
        "prompt":         prompt_obj["prompt"],            # EN
        "prompt_ko":      prompt_obj.get("prompt_ko", ""), # KO (수정 가능)
        "prompt_ko_baseline": prompt_obj.get("prompt_ko_baseline", ""),  # KO 기준선
        "width":          prompt_obj["width"],
        "height":         prompt_obj["height"],
        "aspect_ratio":   prompt_obj["aspect_ratio"],
        "resolution":     prompt_obj["resolution"],
        "use_pre_llm":    prompt_obj["use_pre_llm"],
        # "seed":         prompt_obj.get("seed"),
    }

def run_case(orientation: str, modify_ko: bool, prefix: str):
    print(f"===== CASE: orientation={orientation}, modify_ko={modify_ko} =====")
    # 1) 프롬프트 빌드(basic 스키마)
    prompt_obj = make_banner_prompt_service(
        analysis_payload=analysis_payload,
        orientation=orientation,
        schema="basic",
        use_pre_llm=True,
        strict=True,
    )
    dump("PROMPT OBJ:", {k: prompt_obj[k] for k in ["width","height","aspect_ratio","resolution","use_pre_llm"]})
    print("[EN prompt head]:", prompt_obj["prompt"][:140], "...\n")
    print("[KO prompt head]:", (prompt_obj.get("prompt_ko") or "")[:140], "...\n")

    # 2) job 매핑
    job = to_job(prompt_obj)

    # 3) KO 프롬프트 수정(옵션) → EN 자동 동기화 기대
    if modify_ko and job["prompt_ko"]:
        job["prompt_ko"] = job["prompt_ko"].replace("따뜻한 빨강과 초록", "따뜻한 골드와 화이트") \
                                           .replace("포토존", "체험형 라이트 가든")
        print("[INFO] KO prompt modified.\n")

    # 4) 배너 생성 (ko_sync=True, artifact_paths 포함 dict 반환)
    out_dir = PROJECT_ROOT / "out" / "test_banners_ko_sync"
    result = make_banner_from_prompt_service(
        job,
        orientation=orientation,
        ko_sync=True,                  # ✅ KO→EN 동기화 on
        return_type="dict",
        save_dir=str(out_dir),
        filename_prefix=prefix,
        strict=True,
    )

    # 5) 결과 확인
    dump("IMAGE RESULT (meta):", {
        "orientation": result["orientation"],
        "model": result["model"],
        "artifact_paths": result.get("artifact_paths", []),
    })
    print("[EN prompt head USED]:", result["job_used"]["prompt"][:140], "...\n")
    print("IMAGES(URLs):", result.get("images"))
    print("ARTIFACT PATHS:", result.get("artifact_paths"))
    print()

def main():
    run_case("horizontal", modify_ko=False, prefix="ko_sync_h_nochange")
    run_case("horizontal", modify_ko=True,  prefix="ko_sync_h_changed")
    # 필요 시 세로도:
    # run_case("vertical",   modify_ko=True,  prefix="ko_sync_v_changed")
    print("✅ KO-sync tests completed.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n[ERROR]", type(e).__name__, ":", e)
        if "REPLICATE_API_TOKEN" in str(e):
            print("  - .env에 REPLICATE_API_TOKEN이 설정되어 있는지 확인하세요.")
        if "job['prompt']" in str(e):
            print("  - job['prompt']가 비어있지 않은지 확인하세요.")
