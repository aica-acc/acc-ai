# -*- coding: utf-8 -*-
"""
trend_tools.py
- pdf_tools.analyze_pdf 결과(analysis_payload)와 사용자 입력(축제명/의도/키워드)을 받아
  정성적 현수막 트렌드 분석을 LLM으로 생성해 dict(JSON)으로 반환.
- 결과 JSON에 'paste_md' (붙여넣기용 마크다운) 포함. 없으면 내부 fallback로 생성.
- 모델: gpt-4o-mini (환경변수로 변경 가능)
.env:
  OPENAI_API_KEY=sk-...
  (옵션) OPENAI_TREND_MODEL=gpt-4o-mini
"""

import os, json, re
from datetime import datetime

# .env 로드(있으면)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# OpenAI SDK (>=1.x)
import openai
client = openai.OpenAI()

OPENAI_TREND_MODEL = os.getenv("OPENAI_TREND_MODEL", "gpt-4o-mini")


def _json_guard(text: str) -> dict:
    """모델이 JSON만 내도록 요청하지만, 혹시 앞뒤 문장이 섞이면 중괄호 블록만 파싱."""
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("LLM 응답에서 JSON을 찾을 수 없습니다.")
        return json.loads(m.group(0))


def _mk_messages(festival: str, intent: str, keywords: list, analysis_payload: dict):
    # analysis가 길 수 있어 앞부분만 사용
    analysis_excerpt = json.dumps(analysis_payload, ensure_ascii=False)[:6000]

    system = (
        "You are a senior OOH/banner art director. "
        "Produce qualitative trend analysis of banners/posters for festivals, "
        "focusing on how similar events express visuals, copy patterns, color directions, "
        "layout habits, and pitfalls. Do NOT include step-by-step reasoning. "
        "Return ONLY a single JSON object that matches the schema. No prose outside JSON."
    )

    # 🟡 여기서 'paste_md'를 명시적으로 요구한다
    user = f"""
[Task]
Given the festival info and analysis excerpt, infer thematic clusters (season, audience, vibe),
summarize how comparable festivals typically express their banners, and produce A/B/C application options.
Avoid numeric specs (px, mm, ppi). Focus on qualitative patterns in natural Korean.

[Festival]
- name: {festival}
- intent: {intent}
- keywords: {', '.join(keywords)}

[Analysis_excerpt JSON]
{analysis_excerpt}

[Output JSON schema]
{{
  "schema_version": "1.0",
  "festival": {{"name": "...", "intent": "...", "keywords": ["..."]}},
  "theme_clusters": ["..."],
  "reference_patterns": [
    {{
      "cluster": "…",
      "how_others_do": {{
         "visual_motifs": ["…","…"],
         "copy_patterns":  ["…","…"],
         "color_directions":["…","…"],
         "layout_habits":  ["…","…"],
         "pitfalls":       ["…","…"]
      }},
      "notable_examples_text": ["문구형 예: ‘…’", "패턴 예: ‘…’"]
    }}
  ],
  "recommendations": {{
     "A": {{"one_liner":"…","visual":"…","notes":["…","…"]}},
     "B": {{"one_liner":"…","visual":"…","notes":["…","…"]}},
     "C": {{"one_liner":"…","visual":"…","notes":["…","…"]}}
  }},
  "do_not": ["문구 나열", "폰트 과다", "명도 대비 약함"],
  "trend_summary": "한 단락 요약",
  "paste_md": "## 현수막 트렌드 분석\\n최근 현수막 홍보물의 주요 트렌드를 분석한 결과: ...\\n- ...\\n- ...\\n\\n**권장 방향**: 유사 테마에서 ... 경향이 뚜렷하므로, 본 축제는 ...안을 권장합니다.",
  "generated_at": "ISO-8601 string"
}}

[Constraints]
- Tailor clusters and narrative to the input (여름/벚꽃/물놀이/야간/로컬 요소 등).
- Output ONE JSON only, no other text.
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


# ---------- Fallback: paste_md 자동 생성기 ----------
def _choose_reco_key(intent: str, keywords: list) -> str:
    text = (intent + " " + " ".join(keywords)).lower()
    # 간단한 휴리스틱: 가족/아이 → A, 야간/빛 → B, 로컬/지역/도시명 → C
    if any(k in text for k in ["아이", "어린", "가족", "kids", "family"]):
        return "A"
    if any(k in text for k in ["빛", "야간", "라이트", "night", "illumi"]):
        return "B"
    if any(k in text for k in ["로컬", "지역", "담양", "제주", "부산", "강릉"]):
        return "C"
    return "A"

def _render_paste_md(obj: dict) -> str:
    f = obj.get("festival", {})
    name = f.get("name", "-")
    intent = f.get("intent", "-")
    keywords = ", ".join(f.get("keywords", [])) or "-"

    # 집계
    vis, copies, colors, layouts, pitfalls = [], [], [], [], []
    for r in obj.get("reference_patterns", []):
        h = r.get("how_others_do", {})
        vis += h.get("visual_motifs", []) or []
        copies += h.get("copy_patterns", []) or []
        colors += h.get("color_directions", []) or []
        layouts += h.get("layout_habits", []) or []
        pitfalls += h.get("pitfalls", []) or []

    # 중복 제거, 앞쪽 3~4개만
    def uniq_take(seq, n): 
        out, seen = [], set()
        for x in seq:
            if x in seen: 
                continue
            seen.add(x); out.append(x)
            if len(out) >= n: 
                break
        return out

    vis = uniq_take(vis, 4)
    copies = uniq_take(copies, 3)
    colors = uniq_take(colors, 3)
    layouts = uniq_take(layouts, 3)
    pitfalls = uniq_take(pitfalls, 3)

    # 추천안 선택
    recs = obj.get("recommendations", {}) or {}
    pick = _choose_reco_key(intent, f.get("keywords", []))
    picked = recs.get(pick) or next(iter(recs.values()), {})

    # 본문 생성
    lines = []
    lines.append("## 현수막 트렌드 분석")
    lines.append("최근 현수막 홍보물의 주요 트렌드를 분석한 결과:\n")
    if copies:
        lines.append(f"- **카피 경향**: {', '.join(copies)}")
    if vis:
        lines.append(f"- **시각 모티프**: {', '.join(vis)}")
    if colors:
        lines.append(f"- **색 경향**: {', '.join(colors)}")
    if layouts:
        lines.append(f"- **레이아웃 습관**: {', '.join(layouts)}")
    if pitfalls:
        lines.append(f"- **지양 요소**: {', '.join(pitfalls)}")

    lines.append("\n**추천 방향(우리 축제)**")
    if picked:
        one = picked.get("one_liner", "")
        visual = picked.get("visual", "")
        notes = ", ".join(picked.get("notes", []) or [])
        lines.append(f"- 제안안: **{pick}안 — {one}**")
        if visual:
            lines.append(f"- 비주얼: {visual}")
        if notes:
            lines.append(f"- 포인트: {notes}")
    else:
        lines.append("- 제안안: 입력된 추천안이 없습니다.")

    # 문장형 결론
    theme = " · ".join(obj.get("theme_clusters", []) or [])
    lines.append(
        f"\n> 유사 테마({theme})의 현수막에서는 위와 같은 경향이 뚜렷했습니다. "
        f"**'{name}'**의 기획의도({intent})와 키워드({keywords})를 고려할 때, "
        f"상기 제안안을 우선 적용하는 구성이 적합합니다."
    )
    return "\n".join(lines).strip()


def generate_trend(festival: str, intent: str, keywords: list, analysis_payload: dict) -> dict:
    """
    반환: LLM이 생성한 트렌드 분석 dict (실패 시 {'error': '...'} 형식)
          + obj['paste_md'] 보장(미제공 시 fallback 렌더링)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY가 설정되어 있지 않습니다(.env)."}

    try:
        resp = client.chat.completions.create(
            model=OPENAI_TREND_MODEL,
            messages=_mk_messages(festival, intent, keywords, analysis_payload),
            temperature=0.4,
            top_p=0.9,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        obj = _json_guard(content)

        # 필수 메타 보정
        obj.setdefault("schema_version", "1.0")
        obj.setdefault("festival", {"name": festival, "intent": intent, "keywords": keywords})
        obj.setdefault("generated_at", datetime.now().astimezone().isoformat())

        # 붙여넣기용 md가 없으면 생성
        if not obj.get("paste_md"):
            obj["paste_md"] = _render_paste_md(obj)
        return obj

    except Exception as e:
        return {"error": f"트렌드 분석 생성 실패: {e}"}
