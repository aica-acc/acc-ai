from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
import json

# LangGraph State
class MascotPromptState(TypedDict):
    context: str   # 입력값 합쳐서 만든 컨텍스트
    draft: str     # 브레인스토밍 단계 임시 메모
    output: str    # 최종 JSON 출력

# -------------------------------
# Node 1: 입력값 → 컨텍스트 병합
# -------------------------------
def node_merge_context(state: MascotPromptState, provided_context: str):
    state["context"] = provided_context
    return state

# -------------------------------
# Node 2: 스타일 초안 6~8개 생성
# -------------------------------
def node_brainstorm_styles(state: MascotPromptState, llm: ChatOpenAI):
    system_prompt = """
    You are a senior Korean festival mascot concept artist.
    Based on the given festival context, brainstorm 6~8 diverse mascot style ideas.

    For each idea briefly note:
    - Style name (creative English)
    - Character concept
    - Visual vibe (color tone, shape, emotion)
    """

    user_prompt = f"""
    [Festival Full Context]
    {state['context']}

    Brainstorm 6~8 mascot styles.
    """

    res = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ])

    state["draft"] = res.content
    return state

# -------------------------------
# Node 3: 4개 최종 JSON Prompt 생성
# -------------------------------
def node_create_final_prompts(state: MascotPromptState, llm_json: ChatOpenAI):
    system_prompt = """
    You are a top-tier Korean festival mascot designer.
    Use the festival context and your brainstorm memo to generate EXACTLY 4 mascot concepts.

    Each must follow:
    - 1 mascot only
    - full body, centered
    - pure white background
    - no layout, no poster text, no objects
    - friendly, soft Korean cute style

    JSON OUTPUT FORMAT:
    {
      "master_prompt": {
        "prompt_options": [
          {
            "style_name": "",
            "text_content": {"title": "", "date_location": ""},
            "visual_prompt": ""
          }
        ]
      },
      "status": "success"
    }
    """

    user_prompt = f"""
    [Festival Context]
    {state['context']}

    [Draft Styles]
    {state['draft']}

    Produce 4 final mascot prompts.
    Ensure "visual_prompt" ends with:
    "full body, centered, pure white background, no text, no logo, no objects, Korean cute style"
    """

    res = llm_json.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ])

    state["output"] = res.content
    return state

# ==========================================================
# 🔥 실행 함수 (외부에서 이 함수만 호출하면 됨)
# ==========================================================
def run_mascot_prompt_pipeline(provided_context: str):
    # LLMs
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.9)
    llm_json = ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=0.6,
        model_kwargs={"response_format": {"type": "json_object"}}
    )

    # LangGraph 구성
    workflow = StateGraph(MascotPromptState)

    workflow.add_node("merge", lambda s: node_merge_context(s, provided_context))
    workflow.add_node("draft", lambda s: node_brainstorm_styles(s, llm))
    workflow.add_node("final", lambda s: node_create_final_prompts(s, llm_json))

    workflow.set_entry_point("merge")
    workflow.add_edge("merge", "draft")
    workflow.add_edge("draft", "final")
    workflow.add_edge("final", END)

    app = workflow.compile()

    # 초기 상태
    initial_state: MascotPromptState = {
        "context": "",
        "draft": "",
        "output": ""
    }

    final_state = app.invoke(initial_state)
    return json.loads(final_state["output"])