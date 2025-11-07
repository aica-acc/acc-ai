import replicate
import requests

# ------------------------------
# 1️⃣ JSON 데이터
# ------------------------------
selected_prompt = {
    "master_prompt_for_replicate": "A playful cartoon style poster for '제7회 담양산타축제', depicting children and families in Santa hats, engaging in fun Christmas activities",
    "style_name": "가족 친화 애니메이션 스타일",
    "text_content": {
        "date_location": "2025.12.24. - 12.25. 메타랜드 일원",
        "title": "제7회 담양산타축제"
    },
    "visual_prompt": "Cartoon style with vibrant and playful depiction of children and families wearing Santa hats, engaging in various fun Christmas activities"
}

# ------------------------------
# 2️⃣ 프롬프트 자동 생성
# ------------------------------
prompt_text = (
    f"{selected_prompt['master_prompt_for_replicate']} | "
    f"{selected_prompt['visual_prompt']} | "
    f"Vertical poster, title '{selected_prompt['text_content']['title']}' at the top, "
    f"date/location '{selected_prompt['text_content']['date_location']}' at the bottom, "
    "festive, colorful, high resolution, detailed"
)

# ------------------------------
# 3️⃣ Replicate 모델 실행
# ------------------------------
output_url = replicate.run(
    "ideogram-ai/ideogram-v3-turbo",
    input={
        "prompt": prompt_text,
        "aspect_ratio": "2:3"  # 세로 포스터
    }
)

print("Generated image URL:", output_url)

# ------------------------------
# 4️⃣ 이미지 다운로드
# ------------------------------
img_data = requests.get(output_url).content
file_name = "damyang_santa_vertical_with_text.png"

with open(file_name, "wb") as f:
    f.write(img_data)

print(f"Saved as {file_name}")
