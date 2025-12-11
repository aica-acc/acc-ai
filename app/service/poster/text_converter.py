# app/service/poster/text_converter.py

def korean_to_english(text_data):
    """
    DB에서 가져온 한글 분석 결과(JSON)를 영어로 변환
    text_data 예시:
    {
        "title": "홍보물 제목",
        "date": "2025-12-01",
        "location": "서울",
        "host": "주최 기관",
        "organizer": "주관 기관",
        ...
    }
    """
    translation_map = {
        "홍보물 제목 예시": "Poster Title Example",
        "서울": "Seoul",
        "주최 기관": "Hosting Organization",
        "주관 기관": "Organizing Institution",
        # 필요시 추가 매핑
    }
    eng_data = {k: translation_map.get(v, v) for k, v in text_data.items()}
    return eng_data
