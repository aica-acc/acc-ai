import openai
import os
import json
from dotenv import load_dotenv

load_dotenv()

def generate_report_text(report_type: str, metadata: dict) -> str:
    print(f"📝 [Report Service] 콘텐츠 생성 시작 - Type: {report_type}")

    # 1. 기본 프롬프트: JSON 포맷 강제
    system_prompt = """
    당신은 30년 경력의 베테랑 홍보 담당관이자 편집장입니다.
    주어진 정보를 바탕으로 요청된 형식의 홍보 콘텐츠를 작성해야 합니다.
    반드시 **JSON 포맷**으로만 응답하세요. Markdown이나 기타 텍스트를 포함하지 마십시오.
    """

    info_text = f"""
    [축제 정보]
    - 행사명: {metadata.get('title', '제목 미정')}
    - 기간: {metadata.get('date', '일정 미정')}
    - 장소: {metadata.get('location', '장소 미정')}
    - 주최/주관: {metadata.get('host', '주최 미정')}
    - 주요 프로그램: {metadata.get('programs', '프로그램 미정')}
    - 기획 의도: {metadata.get('concept', '')}
    - 문의: {metadata.get('contact', '문화관광과')}
    """

    user_prompt = ""

    # 2. 타입별 프롬프트 (프론트엔드 MOCK_DATA 구조와 100% 일치시킴)
    if report_type == "press":
        user_prompt = f"""
        {info_text}
        
        위 정보를 바탕으로 [기사 형식의 보도자료]를 작성해 주세요.
        
        [필수 JSON 구조]
        {{
            "title": "기사 제목 (강렬하고 매력적으로)",
            "subtitle": "부제 (핵심 요약)",
            "summary": ["핵심 요약 1 (이모지 포함)", "핵심 요약 2", "핵심 요약 3"],
            "mainImage": {{
                "caption": "메인 이미지 캡션 (현장감 있게 묘사)"
            }},
            "body": "본문 상단 (HTML 태그 <p> 사용, 2~3문단, 굵은 글씨는 <strong> 사용)",
            "highlight": "중간 강조 문구 (슬로건이나 핵심 메시지 1문장)",
            "body2": "본문 하단 (HTML 태그 <p> 사용, 기대효과 및 마무리)",
            "info": {{
                "name": "{metadata.get('title')}",
                "date": "{metadata.get('date')}",
                "location": "{metadata.get('location')}",
                "program": "주요 프로그램 나열",
                "contact": "{metadata.get('contact')}"
            }},
            "sidebar": {{
                "posters": [
                    {{ "title": "2025 공식 포스터" }},
                    {{ "title": "주요 프로그램 안내" }}
                ],
                "links": [
                    {{ "text": "홈페이지 바로가기" }},
                    {{ "text": "사전 예약 하기" }}
                ]
            }}
        }}
        """

    elif report_type == "notice":
        user_prompt = f"""
        {info_text}
        
        위 정보를 바탕으로 지자체 [공식 공고문]을 작성해 주세요.
        
        [필수 JSON 구조]
        {{
            "title": "공고 제목 (예: 제1회 OO축제 개최 안내)",
            "meta": {{
                "no": "거제시 공고 제2025-0000호",
                "date": "2025.05.XX",
                "dept": "문화관광과"
            }},
            "body": "공고문 본문 (HTML <p>, <br> 태그 사용. 격식 있는 어조. 행사 개요 포함)",
            "attachments": [
                {{ "name": "축제_참가신청서.hwp" }},
                {{ "name": "행사_배치도.pdf" }}
            ]
        }}
        """

    elif report_type == "sns":
        user_prompt = f"""
        {info_text}
        
        위 정보를 바탕으로 [SNS 홍보글]을 작성해 주세요.
        
        [필수 JSON 구조]
        {{
            "instagram": [
                {{
                    "id": 1,
                    "caption": "인스타용 감성 제목/카피",
                    "description": "본문 내용 (이모지 많이)",
                    "location": "{metadata.get('location')}",
                    "date": "{metadata.get('date')}",
                    "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4"]
                }},
                {{
                    "id": 2,
                    "caption": "두 번째 피드용 카피 (다른 컨셉)",
                    "description": "본문 내용",
                    "location": "{metadata.get('location')}",
                    "date": "{metadata.get('date')}",
                    "hashtags": ["#태그5", "#태그6"]
                }}
            ],
            "x": [
                {{
                    "id": 1,
                    "text": "트위터용 짧은 홍보글과 굿즈 소개(키링, 이모티콘등)",
                    "author": "@official_account"
                }}
            ],
            "facebook": [
                {{
                    "id": 1,
                    "title": "페이스북용 정보성 제목",
                    "content": "상세하고 친절한 축제 안내글. 특히 현장에 예쁜 굿즈(키링, 이모티콘, 인형 등)가 준비되어 있다는 점을 강조해서 작성.",
                    "link": "https://festival.geoje.go.kr"
                }}
            ]
        }}
        """

    elif report_type == "package":
        # 자바에서 보낸 실제 경로 받기 (없으면 기본값)
        real_poster_path = metadata.get('poster_image', 'poster_main.jpg')
        
        user_prompt = f"""
        {info_text}
        
        홍보 패키지(ZIP)에 들어갈 파일 목록을 생성해 주세요.
        
        [필수 JSON 구조]
        {{
            "files": [
                {{ "name": "보도자료.pdf", "desc": "언론 배포용 보도자료", "icon": "📄" }},
                {{ "name": "{real_poster_path}", "desc": "메인 포스터 고화질 원본", "icon": "🖼️" }}, 
                {{ "name": "program_list.xlsx", "desc": "세부 일정표", "icon": "📅" }}
            ],
            "preview": [
                {{ "title": "보도자료.pdf", "desc": "축제 개요 및 상세 소개 포함" }},
                {{ "title": "{real_poster_path}", "desc": "시각적 아이덴티티를 담은 포스터" }}
            ]
        }}
        """

    # 3. OpenAI 호출
    try:
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"} # JSON 강제
        )
        return response.choices[0].message.content

    except Exception as e:
        print(f"❌ [Report Service] 오류: {e}")
        # 에러 발생 시에도 프론트가 죽지 않게 최소한의 JSON 반환
        error_json = {
            "title": "생성 오류",
            "body": f"<p>죄송합니다. 글을 작성하는 중에 문제가 발생했습니다. ({str(e)})</p>",
            "summary": [],
            "info": {},
            "sidebar": {"posters": [], "links": []}
        }
        return json.dumps(error_json, ensure_ascii=False)