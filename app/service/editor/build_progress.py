"""
에디터 빌드(파생물 생성) 진행 상황.

/editor/build 는 한 요청 안에서 유형별 파생물을 차례로 만든다(수 분).
그동안 백엔드가 GET /editor/build/progress/{pNo} 로 진행 상황을 조회해 화면에 진행률을 보여 준다.
서버 메모리에만 두며(재시작하면 사라짐), 프로젝트(pNo)마다 마지막 빌드 하나만 기억한다.
"""
import threading
import time
from typing import Dict, List, Optional

TYPE_LABELS = {
    "road_banner": "도로용 현수막", "bus_shelter": "버스정류장 광고", "subway_light": "지하철 조명광고",
    "bus_road": "버스 도로 광고", "streetlamp_banner": "가로등 현수막", "subway_inner": "지하철 내부 광고",
    "logo_illustration": "로고 일러스트", "logo_typography": "로고 타이포그래피",
    "sign_parking": "주차 표지판", "sign_welcome": "입구 표지판", "sign_toilet": "화장실 표지판",
    "goods_sticker": "스티커", "goods_key_ring": "키링", "goods_emoticon": "이모티콘",
    "poster_cardnews": "안내 카드뉴스", "leaflet": "리플렛",
    "poster_video": "포스터 홍보영상", "mascot_video": "마스코트 홍보영상", "etc_video": "축제 홍보영상",
}

_lock = threading.Lock()
_progress: Dict[int, dict] = {}


def _now() -> float:
    return round(time.time(), 1)


def start(p_no: int, types: List[str]) -> None:
    with _lock:
        _progress[p_no] = {
            "status": "running",
            "phase": "파생물 생성",
            "startedAt": _now(),
            "finishedAt": None,
            "error": None,
            "items": [
                {"type": t, "label": TYPE_LABELS.get(t, t), "status": "pending",
                 "reused": False, "startedAt": None, "finishedAt": None}
                for t in types
            ],
        }


def _item(p_no: int, t: str) -> Optional[dict]:
    for it in _progress.get(p_no, {}).get("items", []):
        if it["type"] == t:
            return it
    return None


def item_start(p_no: int, t: str) -> None:
    with _lock:
        it = _item(p_no, t)
        if it:
            it.update(status="running", startedAt=_now())


def item_done(p_no: int, t: str, reused: bool = False) -> None:
    with _lock:
        it = _item(p_no, t)
        if it:
            it.update(status="done", reused=reused, finishedAt=_now())
            if it["startedAt"] is None:
                it["startedAt"] = it["finishedAt"]


def item_failed(p_no: int, t: str, error: str) -> None:
    with _lock:
        it = _item(p_no, t)
        if it:
            it.update(status="failed", finishedAt=_now(), error=error[:300])


def phase(p_no: int, label: str) -> None:
    with _lock:
        if p_no in _progress:
            _progress[p_no]["phase"] = label


def finish(p_no: int, ok: bool, error: Optional[str] = None) -> None:
    with _lock:
        if p_no in _progress:
            _progress[p_no].update(
                status="done" if ok else "failed",
                phase="완료" if ok else "실패",
                finishedAt=_now(),
                error=(error or "")[:500] or None,
            )


def get(p_no: int) -> Optional[dict]:
    with _lock:
        p = _progress.get(p_no)
        if not p:
            return None
        items = [dict(it) for it in p["items"]]
        done = sum(1 for it in items if it["status"] == "done")
        # 새로 만든 항목의 평균 소요 시간 (재사용 항목은 제외)
        made = [it["finishedAt"] - it["startedAt"] for it in items
                if it["status"] == "done" and not it["reused"] and it["startedAt"]]
        return {**p, "items": items, "total": len(items), "done": done,
                "avgItemSeconds": round(sum(made) / len(made), 1) if made else None,
                "now": _now()}
