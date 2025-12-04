import os
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from app.service.mascot.model_engines import (
    run_flux,
    run_pixart,
    run_sd3,
    run_recraft,
)

# ============================================
# 1. LangGraph State 정의
# ============================================

class MascotImageState(TypedDict, total=False):
    style_name: str
    base_prompt: str
    translated_prompt: str
    final_prompt: str
    model_name: str
    output_path: str
    width: int
    height: int
    status: str
    error: Optional[str]
    image_url: str
    file_path: str
    file_name: str


# ============================================
# 2. 번역 노드
# ============================================

def node_preprocess(state: MascotImageState, translator_llm: ChatOpenAI):
    print("[ImageGraph] ▷ node_preprocess 진입")
    print(f"[ImageGraph]   base_prompt 길이 = {len(state['base_prompt'])}")

    system_prompt = """
    You are a specialized translator for mascot image generation.
    Translate the given text into clean English.
    Do NOT add extra objects, background, layout, or scenery.
    """

    res = translator_llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state["base_prompt"]},
        ]
    )

    translated = res.content.strip()
    print(f"[ImageGraph]   translated_prompt 길이 = {len(translated)}")

    state["translated_prompt"] = translated
    return state


# ============================================
# 3. 스타일 → 모델 선택 (유사도 기반)
# ============================================

from sentence_transformers import SentenceTransformer, util

embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

MODEL_STYLE_REFERENCES = {
    "recraft": [
        "flat vector illustration",
        "minimal icon symbol",
        "simple geometric shapes",
        "outline svg style",
        "clean vector mascot",
    ],
    "pixart": [
        "text focused design",
        "typography based style",
        "lettering art",
        "headline graphic",
        "word art illustration",
    ],
    "sd3": [
        "anime fantasy magical character",
        "chibi cute mascot",
        "soft pastel children illustration",
        "dreamy fairy style",
    ],
    "flux": [
        "realistic mascot full body",
        "high quality shading",
        "studio lighting illustration",
        "clean modern mascot design",
    ],
}


def semantic_choose_model(style_sentence: str) -> str:
    print("[ModelSelector] ▷ semantic_choose_model 진입")
    print(f"[ModelSelector]   style_sentence = {style_sentence!r}")

    vec = embedding_model.encode(style_sentence, convert_to_tensor=True)

    best_model = None
    best_score = -1.0

    for model_name, examples in MODEL_STYLE_REFERENCES.items():
        ref_vec = embedding_model.encode(examples, convert_to_tensor=True)
        score = util.cos_sim(vec, ref_vec).max().item()
        print(f"[ModelSelector] {model_name} = {score:.4f}")

        if score > best_score:
            best_model = model_name
            best_score = score

    print(f"[ModelSelector] 최종 선택 모델 = {best_model}")
    return best_model or "flux"


def node_model_select(state: MascotImageState):
    print("[ImageGraph] ▷ node_model_select 진입")
    print(f"[ImageGraph]   style_name = {state['style_name']!r}")

    model = semantic_choose_model(state["style_name"])
    state["model_name"] = model

    print(f"[MascotImageGraph] 선택된 모델 = {model}")
    return state


# ============================================
# 4. 최종 프롬프트 구성
# ============================================

def node_build_final_prompt(state: MascotImageState):
    print("[ImageGraph] ▷ node_build_final_prompt 진입")

    base = state["translated_prompt"]

    prefix = (
        "High-quality cute mascot illustration, Korean-style, "
        "full body, centered, pure white background, "
        "soft lighting, round shapes, friendly expression. "
    )

    negative = (
        "no poster, no text, no logo, no layout, no background scenery, "
        "no additional characters, no objects, no icons."
    )

    final_prompt = f"{prefix}{base}. {negative}"
    state["final_prompt"] = final_prompt

    print("[ImageGraph]   final_prompt 미리보기:")
    print("-------------- PROMPT START --------------")
    print(final_prompt[:300])
    print("--------------- PROMPT END ---------------")

    return state


# ============================================
# 5. 모델별 이미지 생성 실행 + 디버그
# ============================================

def node_generate_image(state: MascotImageState):
    print("[ImageGraph] ▷ node_generate_image 진입")
    model = state["model_name"]
    prompt = state["final_prompt"]
    out_path = state["output_path"]

    print(f"[ImageGraph]   model = {model}")
    print(f"[ImageGraph]   output_path = {out_path}")

    if model == "flux":
        print("=== [FLUX] 모델 호출 ===")
        result = run_flux(prompt, out_path)
    elif model == "pixart":
        print("=== [PIXART] 모델 호출 ===")
        result = run_pixart(prompt, out_path)
    elif model == "sd3":
        print("=== [SD3] 모델 호출 ===")
        result = run_sd3(prompt, out_path)
    elif model == "recraft":
        print("=== [RECRAFT] 모델 호출 ===")
        result = run_recraft(prompt, out_path)
    else:
        state["status"] = "error"
        state["error"] = f"Unknown model: {model}"
        print(f"[ImageGraph] ❌ Unknown model: {model}")
        return state

    print(f"[ImageGraph]   model result raw = {result}")

    if result.get("status") != "success":
        state["status"] = "error"
        state["error"] = result.get("error", "unknown error from model_engines")
        print(f"[ImageGraph] ❌ 모델 실행 실패: {state['error']}")
        return state

    # 여기서 반드시 state에 값 세팅
    state["image_url"] = result.get("image_url")
    state["file_path"] = result.get("file_path") or out_path
    state["file_name"] = os.path.basename(state["file_path"])
    state["status"] = "success"

    print("[ImageGraph]   state.image_url  =", state["image_url"])
    print("[ImageGraph]   state.file_path  =", state["file_path"])
    print("[ImageGraph]   state.file_name  =", state["file_name"])

    return state


# ============================================
# 6. 최종 응답 JSON 구성 + 검증 로그
# ============================================

def node_save_and_return(state: MascotImageState):
    print("[ImageGraph] ▷ node_save_and_return 진입")
    print("[ImageGraph]   state.status =", state.get("status"))
    print("[ImageGraph]   state.image_url =", state.get("image_url"))
    print("[ImageGraph]   state.file_path =", state.get("file_path"))
    print("[ImageGraph]   state.file_name =", state.get("file_name"))

    if state.get("status") == "error":
        print("[ImageGraph]   에러 상태로 종료")
        return {
            "status": "error",
            "message": state.get("error"),
            "image_url": None,
            "file_name": None,
            "visual_prompt": state.get("final_prompt", ""),
        }

    filename = state.get("file_name") or os.path.basename(state["output_path"])
    url = f"/poster-images/mascot/{filename}"

    print("[ImageGraph]   최종 image_url =", url)

    return {
        "status": "success",
        "image_url": url,
        "file_name": filename,
        "visual_prompt": state["final_prompt"],
    }


# ============================================
# 7. 외부에서 호출하는 함수 (엔트리 포인트)
# ============================================

def run_mascot_image_pipeline(style_name: str, raw_prompt: str, output_path: str):
    print("===================================================")
    print("[run_mascot_image_pipeline] 호출")
    print(f"[run_mascot_image_pipeline] style_name  = {style_name}")
    print(f"[run_mascot_image_pipeline] output_path = {output_path}")
    print("===================================================")

    state: MascotImageState = {
        "style_name": style_name,
        "base_prompt": raw_prompt,
        "translated_prompt": "",
        "final_prompt": "",
        "model_name": "",
        "output_path": output_path,
        "width": 1024,
        "height": 1024,
        "status": "",
        "error": None,
    }

    translator_llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.3)

    graph = StateGraph(MascotImageState)

    graph.add_node("preprocess", lambda s: node_preprocess(s, translator_llm))
    graph.add_node("select_model", node_model_select)
    graph.add_node("build_prompt", node_build_final_prompt)
    graph.add_node("generate_image", node_generate_image)
    graph.add_node("final", node_save_and_return)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "select_model")
    graph.add_edge("select_model", "build_prompt")
    graph.add_edge("build_prompt", "generate_image")
    graph.add_edge("generate_image", "final")
    graph.add_edge("final", END)

    app = graph.compile()
    result = app.invoke(state)

    print("[run_mascot_image_pipeline] 최종 result =", result)
    return result
