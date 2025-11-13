import asyncio
from app.tools.cardnews.festival_loader import load_festivals, filter_festivals_by_region
from app.service.cardnews.cardnews_score_service import score_cardnews_image
from app.tools.cardnews.image_loader import download_cardnews_images
from pathlib import Path
import json

async def process_cardnews_batch(csv_path: str, region: str, limit_festivals: int, limit_images: int):
    """🎯 축제별 카드뉴스 이미지 일괄 수집 및 점수화"""
    festivals = load_festivals(csv_path)
    target_list = filter_festivals_by_region(festivals, region, limit_festivals)

    all_results = []
    for f in target_list:
        name = f["festival_name"]
        year = f.get("year", 2025)

        print(f"📦 {region} - {name} ({year}) 수집 중...")

        # 이미지 다운로드 (썸네일 기반)
        records = await download_cardnews_images(
            category="전체",
            query=f"{name} 카드뉴스 site:instagram.com",
            festival_name=name,
            region=region,
            year=year,
            limit_images=limit_images
        )

        # 점수 부여
        scored_records = []
        for rec in records:
            try:
                score = score_cardnews_image(rec["thumbnail_path"])
                scored_records.append({
                    **rec,
                    "score": score.dict()
                })
            except Exception as e:
                scored_records.append({
                    **rec,
                    "error": str(e)
                })

        all_results.append({
            "festival": name,
            "region": region,
            "year": year,
            "results": scored_records
        })

        # 💾 중간 저장 (FastAPI 서버가 죽더라도 복구 가능)
        tmp_path = Path("tmp_results") / f"{region}_{year}_{name}.json"
        tmp_path.parent.mkdir(exist_ok=True)
        tmp_path.write_text(json.dumps(scored_records, ensure_ascii=False, indent=2))

        print(f"✅ {name} 완료 (이미지 {len(records)}개, 점수화 완료)")

    return all_results
