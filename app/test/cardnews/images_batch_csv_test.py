import asyncio
import json
import random
from pathlib import Path
from datetime import datetime

from app.tools.cardnews.festival_loader import load_festivals
from app.tools.cardnews.image_loader import download_cardnews_images
from app.service.cardnews.cardnews_score_service import hybrid_cardnews_score

def resolve_paths():
    """
    📁 현재 파일 위치 기준으로 ACC/data 경로 계산
    __file__ = ACC/acc_ai/app/test/cardnews/test_cardnews_batch.py

    parents[0] = cardnews
    parents[1] = test
    parents[2] = app
    parents[3] = acc_ai
    parents[4] = ACC   ✅ 여기 기준으로 data 폴더 사용
    """
    here = Path(__file__).resolve()
    acc_root = here.parents[4]          # .../final_project/ACC
    data_root = acc_root / "data"       # .../final_project/ACC/data

    csv_path = data_root / "festivals_2025.csv"
    results_dir = data_root / "cardnews_results"

    return csv_path, results_dir, data_root


async def run_batch_test():
    """
    🎯 테스트용 카드뉴스 배치 실행
    - CSV에서 축제 리스트 로드
    - 무작위(Random)로 N개의 축제를 선택
    - 각 축제에 대해 [부스소개, 지도, 축제개요, 행사일정] 카테고리별로
      인스타 카드뉴스 썸네일 수집 + 점수화
    - 최종 결과를 JSON 파일로 저장
    """

    csv_path, results_dir, data_root = resolve_paths()

    # 0️⃣ CSV 존재 여부 확인
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

    print(f"📄 CSV 경로: {csv_path}")
    print(f"📁 데이터 루트: {data_root}")

    # 1️⃣ 입력값 받기 (테스트니까 단순하게)
    num_festivals = int(input("📦 몇 개의 축제를 랜덤으로 조회할까요?: ").strip())
    limit_images = int(input("🖼️ 축제별 최대 몇 장의 이미지를 가져올까요?: ").strip())

    # 2️⃣ CSV → 축제 리스트 로드
    festivals = load_festivals(str(csv_path))
    if not festivals:
        print("⚠ CSV에서 축제 데이터를 찾지 못했습니다.")
        return

    # 3️⃣ 랜덤으로 축제 N개 선택
    if num_festivals > len(festivals):
        print(f"요청한 개수({num_festivals})가 축제 수({len(festivals)})보다 많아 전체 축제 사용합니다.")
        num_festivals = len(festivals)

    target_list = random.sample(festivals, num_festivals)

    print(f"\n[INFO] 총 {len(festivals)}개 중에서 {num_festivals}개 축제를 랜덤 선택했습니다.\n")

    # 4️⃣ 카테고리 정의 (데이터/폴더 구조와 맞춤)
    categories = ["부스소개", "지도", "축제개요", "행사일정"]

    # 필요하다면 여기서 data/{카테고리명} 폴더를 미리 만들어둘 수도 있음
    for cat in categories:
        cat_dir = data_root / cat
        cat_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    # 5️⃣ 축제별 수집 + 점수화
    for f in target_list:
        name = f.get("festival_name")
        region = f.get("region", "")
        year = f.get("year", 2025)

        print(f"📡 [축제] {region} - {name} ({year}) 처리 시작...")

        festival_result = {
            "festival_name": name,
            "region": region,
            "year": year,
            "categories": []
        }

        for cat in categories:
            print(f"   🔎 카테고리 [{cat}] 수집 중...")

            query = f"{name} 카드뉴스 {cat} site:instagram.com"

            # 5-1. 인스타 카드뉴스 썸네일 수집
            records = await download_cardnews_images(
                category=cat,
                query=query,
                festival_name=name,
                region=region,
                year=year,
                limit_images=limit_images,
            )

            scored_items = []
            for rec in records:
                try:
                    # 5-2. 점수화 (자동 배치 모드 → text_prompt=None)
                    score = hybrid_cardnews_score(
                        image_path=rec["file_path"],
                        text_prompt=None,  # 기획의도 없이 트렌드 참조용 수집
                    )
                    scored_items.append({
                        **rec,
                        "score": score.model_dump(mode="json"),
                    })
                except Exception as e:
                    scored_items.append({
                        **rec,
                        "error": str(e),
                    })

            festival_result["categories"].append({
                "category": cat,
                "images": scored_items,
            })

            print(f"   ✅ [{cat}] 완료 (이미지 {len(records)}개)")

        all_results.append(festival_result)
        print(f"✅ [축제 완료] {name}\n")

    # 6️⃣ 최종 JSON 저장 (→ Spring Boot에서 읽어서 DB에 넣을 대상)
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"cardnews_batch_random_{ts}.json"

    out_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("📁 최종 결과 JSON 저장 완료")
    print(f"➡ 경로: {out_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(run_batch_test())
