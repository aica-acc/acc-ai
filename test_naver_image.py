# test_naver_image.py
# -*- coding: utf-8 -*-

from app.service.banner.common.naver_image_search import search_naver_images


def main():
    # 1) 관련 테마 축제 현수막 느낌으로 테스트
    query_similar = "가족 야간 축제 현수막"
    print(f"[유사 테마 검색] query = {query_similar!r}")
    similar_results = search_naver_images(
        query_similar,
        display=20,      # 많이 가져와서
        sort="sim",      # 유사도 기준
        festival_only=True,  # 축제 느낌만 필터
    )
    print("  -> 결과 개수:", len(similar_results))
    for item in similar_results[:5]:
        print("   -", item["festival_name"], "=>", item["image_url"])

    print("\n" + "=" * 60 + "\n")

    # 2) 최근 축제 트렌드 느낌으로 테스트
    query_recent = "축제 현수막 배너 디자인"
    print(f"[최근 트렌드 검색] query = {query_recent!r}")
    recent_results = search_naver_images(
        query_recent,
        display=20,
        sort="date",         # 최신순
        festival_only=True,  # 축제 느낌만 필터
    )
    print("  -> 결과 개수:", len(recent_results))
    for item in recent_results[:5]:
        print("   -", item["festival_name"], "=>", item["image_url"])


if __name__ == "__main__":
    main()
