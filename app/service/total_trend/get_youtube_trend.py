# %%
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import datetime
load_dotenv()
import os


# %%
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# %%
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_SERVICE_VERSION = 'v3'
youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_SERVICE_VERSION, developerKey = YOUTUBE_API_KEY)

# %%

# 설정
TARGET_COUNT = 30


# 🔹 숏폼: 크리스마스 기준 2개월 전 ~ 크리스마스
#   나중에는 이 부분을 DB에서 가져온 축제 시작일로 바꾸면 됨

now = datetime.datetime.now(timezone.utc)

# Long (1개월)
long_start_dt = now - timedelta(days=30)
long_end_dt = now

LONG_PUBLISHED_AFTER = long_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
LONG_PUBLISHED_BEFORE = long_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# Short (2개월)
short_start_dt = now - timedelta(days=60)
short_end_dt = now

SHORT_PUBLISHED_AFTER = short_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
SHORT_PUBLISHED_BEFORE = short_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../data"))

os.makedirs(DATA_DIR, exist_ok=True)

LONG_OUTPUT_PATH = os.path.join(DATA_DIR, "youtube_long_result.txt")
SHORT_OUTPUT_PATH = os.path.join(DATA_DIR, "youtube_short_result.txt")


# %%
import datetime
import os

TARGET_COUNT = 30


def has_hangul(s: str) -> bool:
    return any('가' <= ch <= '힣' for ch in (s or ""))


def fetch_and_print_non_shorts(youtube, keyword):
    results = []

    def search_by_duration(dur):
        return youtube.search().list(
            q=keyword,
            part="snippet",
            type="video",
            order="relevance",
            regionCode="KR",
            relevanceLanguage="ko",
            publishedAfter=LONG_PUBLISHED_AFTER,
            publishedBefore=LONG_PUBLISHED_BEFORE,
            videoDuration=dur,  # medium: 4~20분, long: 20분~
            maxResults=50
        ).execute().get("items", [])

    # 1) medium + long 영상 합치기
    items = search_by_duration("medium") + search_by_duration("long")

    # 2) 한국어 채널만 남기기
    items = [it for it in items if has_hangul(it["snippet"]["channelTitle"])]

    # 3) 비디오 ID 중복 제거
    seen_ids, video_ids = set(), []
    for it in items:
        vid = it["id"]["videoId"]
        if vid not in seen_ids:
            seen_ids.add(vid)
            video_ids.append(vid)

    if not video_ids:
        print("롱폼: 조건에 맞는 영상이 없습니다.")
        return []

    # 4) 상세 정보 조회
    videos = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids[:50])
    ).execute().get("items", [])

    # 5) 조회수 기준 정렬 + 채널 중복 제거
    videos_norm = []
    for v in videos:
        stats = v.get("statistics", {})
        views = int(stats.get("viewCount", 0))
        videos_norm.append({
            "id": v["id"],
            "title": v["snippet"]["title"],
            "channel_id": v["snippet"]["channelId"],
            "channel_title": v["snippet"]["channelTitle"],
            "description": v["snippet"].get("description", "").strip(),
            "views": views
        })

    videos_norm.sort(key=lambda x: x["views"], reverse=True)

    seen_channels = set()
    selected = []
    for v in videos_norm:
        if v["channel_id"] in seen_channels:
            continue
        seen_channels.add(v["channel_id"])
        selected.append(v)
        if len(selected) >= TARGET_COUNT:
            break

    # 6) 출력 만들기
    for v in selected:
        url = f"https://www.youtube.com/watch?v={v['id']}"
        desc = v["description"].replace("\n", " ").strip()  # 한 줄로 정리

        record = (
            f"URL: {url}\n"
            f"제목: {v['title']}\n"
            f"채널: {v['channel_title']}\n"
            f"조회수: {v['views']}\n"
            f"설명: {desc or '없음'}\n"
        )
        results.append(record)

    return results


def save_to_long_file(texts, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(texts))





# %%

# 설정
TARGET_COUNT = 30

def has_hangul(s: str) -> bool:
    return any('가' <= ch <= '힣' for ch in (s or ""))


def fetch_and_print_shorts(youtube, keyword):
    results = []

    # 🔹 쇼츠(4분 미만) 검색 — 축제 시작일 기준 2개월 윈도우
    search = youtube.search().list(
        q=keyword,
        part="snippet",
        type="video",
        order="viewCount",
        regionCode="KR",
        relevanceLanguage="ko",
        publishedAfter=SHORT_PUBLISHED_AFTER,   # ← 네가 이미 선언해둔 날짜
        publishedBefore=SHORT_PUBLISHED_BEFORE, # ← 네가 이미 선언해둔 날짜
        videoDuration="short",
        maxResults=50
    ).execute()

    items = search.get("items", [])

    # 🔹 한국어 채널만 필터링
    items = [it for it in items if has_hangul(it["snippet"]["channelTitle"])]

    # video ID 수집
    video_ids = [it["id"]["videoId"] for it in items]
    if not video_ids:
        print("숏폼: 조건에 맞는 영상이 없습니다.")
        return []

    # 🔹 상세 정보 조회
    videos = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids[:50])
    ).execute().get("items", [])

    # 🔹 조회수 정렬 + 채널당 한 개만 선택
    videos_norm = []
    for v in videos:
        stats = v.get("statistics", {})
        views = int(stats.get("viewCount", 0))

        videos_norm.append({
            "id": v["id"],
            "title": v["snippet"]["title"],
            "channel_id": v["snippet"]["channelId"],
            "channel_title": v["snippet"]["channelTitle"],
            "description": v["snippet"].get("description", "").strip(),
            "views": views
        })

    videos_norm.sort(key=lambda x: x["views"], reverse=True)

    # 채널 중복 제거
    seen_channels = set()
    selected = []

    for v in videos_norm:
        if v["channel_id"] in seen_channels:
            continue
        seen_channels.add(v["channel_id"])
        selected.append(v)
        if len(selected) >= TARGET_COUNT:
            break

    # 🔹 결과 레코드 구성 (설명 기반)
    for v in selected:
        url = f"https://www.youtube.com/watch?v={v['id']}"
        desc = v["description"].replace("\n", " ").strip()

        record = (
            f"URL: {url}\n"
            f"제목: {v['title']}\n"
            f"채널: {v['channel_title']}\n"
            f"조회수: {v['views']}\n"
            f"설명: {desc or '없음'}\n"
        )

        results.append(record)

    return results


def save_to_short_file(texts, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(texts))



def run_youtube_search(keyword: str):
    """유튜브 검색 실행 → long/short 파일 생성"""

    # 1) 숏폼
    short_texts = fetch_and_print_shorts(youtube, keyword)
    save_to_short_file(short_texts, SHORT_OUTPUT_PATH)

    # 2) 롱폼
    long_texts = fetch_and_print_non_shorts(youtube, keyword)
    save_to_long_file(long_texts, LONG_OUTPUT_PATH)

    print("📌 YouTube 검색 완료 (파일 저장 완료)")