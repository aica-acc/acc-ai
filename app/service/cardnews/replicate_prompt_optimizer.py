from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import json


def optimize_for_replicate(visual_prompt: str) -> dict:
    """
    visual_prompt(배경 전용 프롬프트)를 기반으로
    Replicate(Stable Diffusion, SDXL, Flux 계열)에 최적화된
    prompt / negative_prompt / width / height를 생성
    """
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    template = ChatPromptTemplate.from_template(
        """
너는 Replicate(Stable Diffusion, SDXL, Flux) 최적화 전문가이다.

입력된 visual_prompt는
"텍스트가 전혀 없는 카드뉴스 배경 이미지"를 의도한다.

[목표]
- visual_prompt의 내용을 보존하되,
  Replicate용 prompt/negative_prompt 형태로 정리한다.
- 모든 텍스트/글자/타이포그래피/숫자/로고는 절대 생성하지 않도록 막는다.

[반드시 prompt에 포함]
- "festival card-news background"
- "no text, no letters, no typography, no logo, no watermark"
- top area for title, mid visual focus, bottom or mid-lower block for schedule-like table area
- 4k, sharp detail, clean layout, modern design

[반드시 negative_prompt에 포함]
- "text, letters, typography, Korean characters, English text"
- "numbers, date, time, watermark, logo, caption, ui, interface"
- "blurry, low quality, noisy, distorted"

[출력 형식(JSON ONLY)]
{{
  "prompt": "<Replicate에서 사용할 최종 positive prompt>",
  "negative_prompt": "<Replicate에서 사용할 최종 negative prompt>",
  "width": 1080,
  "height": 1350
}}

[입력 visual_prompt]
{visual_prompt}
"""
    )

    msgs = template.format_messages(visual_prompt=visual_prompt)
    result = llm.invoke(msgs)

    try:
        return json.loads(result.content)
    except Exception:
        return {
            "prompt": f"{visual_prompt}, festival card-news background, no text, no letters, no typography, no logo, no watermark, 4k, sharp detail",
            "negative_prompt": (
                "text, letters, typography, Korean characters, English text, "
                "numbers, date, time, watermark, logo, caption, ui, interface, "
                "blurry, low quality, noisy, distorted"
            ),
            "width": 1080,
            "height": 1350,
        }
