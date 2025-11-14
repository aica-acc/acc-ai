# app/data/seed_festivals_with_banners.py
# -*- coding: utf-8 -*-
"""
실제로 존재하는 한국 축제들을
festivals_with_banners.json 파일에 저장하는 시드 스크립트.

⚠ 여기 들어가는 축제명은 전부 실존 축제여야 합니다.
   날짜 / 배너 이미지 경로 / 설명은 너가 필요에 따라 수정하면 됩니다.
"""

from __future__ import annotations

from pathlib import Path
import json

# 이 파일과 같은 폴더에 festivals_with_banners.json 생성
DATA_PATH = Path(__file__).with_name("festivals_with_banners.json")

FESTIVALS = [
    {
        "id": "damyang_santa_2024",
        "name_ko": "담양산타축제",
        "tags": ["겨울", "크리스마스", "산타", "가족", "야간", "눈"],
        "start_date": "2024-12-20",
        "end_date": "2025-01-05",
        "region": "전남 담양군",
        "banner_image_url": "/static/banners/damyang_santa_2024_main.jpg",
        "banner_image_description": "담양산타축제의 메인 현수막으로, 눈이 쌓인 거리와 크리스마스트리, 전구 장식이 이어져 있는 겨울 야간 풍경을 사용한 디자인입니다. 중앙에는 산타 모자를 쓴 아이들의 실루엣이 배치되어 가족 중심 겨울 축제의 분위기를 강조합니다."
    },
    {
        "id": "hwacheon_sancheoneo_2025",
        "name_ko": "화천산천어축제",
        "tags": ["겨울", "얼음낚시", "산천어", "체험", "가족"],
        "start_date": "2025-01-04",
        "end_date": "2025-01-26",
        "region": "강원 화천군",
        "banner_image_url": "/static/banners/hwacheon_sancheoneo_2025.jpg",
        "banner_image_description": "얼음 위에서 산천어 낚시를 즐기는 사람들의 모습을 담은 사진을 크게 사용한 현수막입니다. 차가운 파란색과 흰색 조합으로 겨울 축제의 시원한 분위기를 전달하며, 상단에는 축제명이 굵은 서체로 눈에 띄게 배치되어 있습니다."
    },
    {
        "id": "pyeongchang_trout_2025",
        "name_ko": "평창송어축제",
        "tags": ["겨울", "얼음낚시", "송어", "체험", "가족"],
        "start_date": "2025-01-01",
        "end_date": "2025-01-19",
        "region": "강원 평창군",
        "banner_image_url": "/static/banners/pyeongchang_trout_2025.jpg",
        "banner_image_description": "눈으로 덮인 강 위에 설치된 얼음낚시 터를 배경으로 한 배너입니다. 중앙에는 송어 일러스트와 함께 축제명이 배치되어 있고, 하단에는 날짜와 장소가 간결한 정보 박스로 정리되어 있습니다."
    },
    {
        "id": "taebaeksan_snow_2025",
        "name_ko": "태백산눈축제",
        "tags": ["겨울", "눈", "눈조각", "가족", "야간"],
        "start_date": "2025-01-10",
        "end_date": "2025-01-19",
        "region": "강원 태백시",
        "banner_image_url": "/static/banners/taebaeksan_snow_2025.jpg",
        "banner_image_description": "대형 눈조각 작품과 눈 덮인 태백산 풍경을 크게 배치한 눈축제 현수막입니다. 흰색과 진한 파란색의 대비로 시원한 인상을 주며, 상단에는 축제명이 세로형 또는 가로형으로 강하게 강조되어 있습니다."
    },
    {
        "id": "daegwallyeong_snowflower_2025",
        "name_ko": "대관령눈꽃축제",
        "tags": ["겨울", "눈", "눈꽃", "야간", "포토존"],
        "start_date": "2025-01-17",
        "end_date": "2025-01-26",
        "region": "강원 평창군",
        "banner_image_url": "/static/banners/daegwallyeong_snowflower_2025.jpg",
        "banner_image_description": "눈으로 덮인 숲길과 눈꽃 조형물을 야간 조명과 함께 담은 사진을 사용한 배너입니다. 따뜻한 조명 색과 짙은 남색 하늘이 대비를 이루며, 중앙에 축제명이 배치되어 겨울 야간 산책의 분위기를 강조합니다."
    },
    {
        "id": "boryeong_mud_2025",
        "name_ko": "보령머드축제",
        "tags": ["여름", "해변", "머드", "체험", "외국인", "음악"],
        "start_date": "2025-07-19",
        "end_date": "2025-07-28",
        "region": "충남 보령시",
        "banner_image_url": "/static/banners/boryeong_mud_2025.jpg",
        "banner_image_description": "머드 슬라이드와 해변에서 즐기는 참가자들의 모습을 담은 역동적인 사진을 사용한 여름 축제 배너입니다. 강렬한 파란색과 갈색 머드 색의 조합으로 시원함과 에너지를 동시에 전달합니다."
    },
    {
        "id": "jinju_lantern_2025",
        "name_ko": "진주남강유등축제",
        "tags": ["가을", "등불", "야간", "강변", "포토존"],
        "start_date": "2025-10-01",
        "end_date": "2025-10-13",
        "region": "경남 진주시",
        "banner_image_url": "/static/banners/jinju_lantern_2025.jpg",
        "banner_image_description": "남강 위를 떠다니는 다양한 유등을 담은 야간 사진을 크게 사용한 현수막입니다. 검푸른 강물 위에 떠 있는 등불의 노란빛이 돋보이며, 축제명은 상단 또는 중앙에 고딕 계열 서체로 배치되어 있습니다."
    },
    {
        "id": "busan_fireworks_2025",
        "name_ko": "부산불꽃축제",
        "tags": ["가을", "불꽃놀이", "야간", "해변", "야경"],
        "start_date": "2025-11-01",
        "end_date": "2025-11-01",
        "region": "부산광역시",
        "banner_image_url": "/static/banners/busan_fireworks_2025.jpg",
        "banner_image_description": "야간의 광안대교와 그 위로 터지는 불꽃을 한 화면에 담은 이미지를 사용한 배너입니다. 짙은 남색 하늘과 다채로운 불꽃 색상이 강한 대비를 이루며, 하단에는 축제명과 날짜가 간단한 정보 블록으로 정리되어 있습니다."
    }
]


def main() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(FESTIVALS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] festivals_with_banners.json 저장 완료: {DATA_PATH}")


if __name__ == "__main__":
    main()
