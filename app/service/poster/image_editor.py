# import os
# import json
# import requests
# import vertexai
# from vertexai.generative_models import GenerativeModel, Part, SafetySetting
# from vertexai.preview.vision_models import Image as VertexImage, ImageGenerationModel
# from google.oauth2 import service_account
# from PIL import Image, ImageDraw

# # --- [설정 영역] ---
# GOOGLE_PROJECT_ID = "네-구글-프로젝트-ID" # <--- ⚠️ 확인
# GOOGLE_KEY_PATH = r"C:\final_project\ACC\acc-ai\내_구글_키_파일.json" # <--- ⚠️ 확인
# LOCATION = "us-central1"
# CLIPDROP_API_KEY = "네-클립드롭-API-키" # <--- ⚠️ 확인

# # 인증 초기화
# try:
#     creds = service_account.Credentials.from_service_account_file(GOOGLE_KEY_PATH)
#     vertexai.init(project=GOOGLE_PROJECT_ID, location=LOCATION, credentials=creds)
#     print("[image_editor] ✅ Vertex AI 연결 성공")
# except Exception as e:
#     print(f"[image_editor] 🚨 인증 오류: {e}")

# # -------------------------------------------------------
# # 1. [스마트 분석] Gemini 1.5 Flash로 레이아웃 파악
# # -------------------------------------------------------
# def analyze_layout_with_gemini(image_path):
#     print(f"  🧠 [Gemini 1.5] 포스터 레이아웃(제목/날짜 위치) 분석 중...")
#     try:
#         model = GenerativeModel("gemini-1.5-flash-001")
        
#         with open(image_path, "rb") as f:
#             img_data = f.read()
        
#         image_part = Part.from_data(data=img_data, mime_type="image/png")
        
#         # 제미나이에게 좌표를 물어보는 프롬프트
#         prompt = """
#         Analyze this poster image.
#         I need the bounding box coordinates for:
#         1. The 'Main Title' text area (ymin, xmin, ymax, xmax).
#         2. The 'Date/Location' info text area (ymin, xmin, ymax, xmax).

#         Return ONLY a JSON object like this:
#         {
#             "title": [ymin, xmin, ymax, xmax],
#             "info": [ymin, xmin, ymax, xmax]
#         }
#         Do not ignore any text. If there are multiple lines, group them appropriately.
#         """
        
#         response = model.generate_content(
#             [image_part, prompt],
#             generation_config={"response_mime_type": "application/json"}
#         )
        
#         layout = json.loads(response.text)
#         print(f"    👉 분석 결과: {layout}")
#         return layout

#     except Exception as e:
#         print(f"    ⚠️ 레이아웃 분석 실패: {e}")
#         return None

# # -------------------------------------------------------
# # 2. [마스크 생성] 분석된 좌표대로 마스크 뚫기
# # -------------------------------------------------------
# def create_smart_mask(image_path, layout):
#     print("  ✂️ [Mask] 분석된 좌표로 마스크 생성 중...")
#     try:
#         orig_img = Image.open(image_path)
#         W, H = orig_img.size
#         mask_img = Image.new("RGB", (W, H), (0, 0, 0))
#         draw = ImageDraw.Draw(mask_img)

#         # 1. 제목 마스크 (흰색)
#         if layout and "title" in layout:
#             ymin, xmin, ymax, xmax = layout["title"]
#             # 좌표는 0~1000 단위로 올 수 있어서 정규화 필요할 수 있으나
#             # Gemini 1.5는 보통 0~1000 스케일 사용. 
#             # 하지만 여기서는 편의상 픽셀 좌표로 변환 로직이 필요할 수 있음.
#             # **중요:** Flash 모델이 0~1000 좌표계를 쓴다면 아래와 같이 변환:
            
#             # 좌표 범위 체크 (혹시 0~1 사이면 W, H 곱하기)
#             if ymin <= 1 and ymax <= 1:
#                 box = [xmin*W, ymin*H, xmax*W, ymax*H]
#             else:
#                 # 1000 단위라면
#                 box = [xmin/1000*W, ymin/1000*H, xmax/1000*W, ymax/1000*H]
            
#             draw.rectangle(box, fill=(255, 255, 255))

#         # 2. 정보 마스크 (흰색)
#         if layout and "info" in layout:
#             ymin, xmin, ymax, xmax = layout["info"]
#             if ymin <= 1 and ymax <= 1:
#                 box = [xmin*W, ymin*H, xmax*W, ymax*H]
#             else:
#                 box = [xmin/1000*W, ymin/1000*H, xmax/1000*W, ymax/1000*H]
            
#             draw.rectangle(box, fill=(255, 255, 255))
        
#         # 만약 분석 실패했으면 기본값
#         if not layout:
#             draw.rectangle([W*0.1, H*0.05, W*0.9, H*0.35], fill=(255, 255, 255)) # 상단
#             draw.rectangle([W*0.1, H*0.8, W*0.9, H*0.95], fill=(255, 255, 255)) # 하단

#         mask_path = image_path.replace(".png", "_smart_mask.png")
#         mask_img.save(mask_path)
#         return mask_path

#     except Exception as e:
#         print(f"    🚨 마스크 생성 실패: {e}")
#         return None

# # -------------------------------------------------------
# # 3. [청소] Clipdrop
# # -------------------------------------------------------
# def remove_text_with_clipdrop(image_path):
#     print("  🧹 [Clipdrop] 텍스트 제거 요청 중...")
#     url = "https://clipdrop-api.co/remove-text/v1"
#     if not CLIPDROP_API_KEY or "네-클립드롭" in CLIPDROP_API_KEY:
#         return image_path
#     try:
#         with open(image_path, "rb") as f:
#             files = {"image_file": (os.path.basename(image_path), f, "image/png")}
#             headers = {"x-api-key": CLIPDROP_API_KEY}
#             response = requests.post(url, files=files, headers=headers)
#         if response.ok:
#             clean_path = image_path.replace(".png", "_clean.png")
#             with open(clean_path, "wb") as f: f.write(response.content)
#             return clean_path
#         return image_path
#     except: return image_path

# # -------------------------------------------------------
# # 4. [메인 실행]
# # -------------------------------------------------------
# def edit_image_process(original_image_path, title, date, location):
#     print(f"\n🤖 [포스터 재디자인 시작] {original_image_path}")
    
#     # 1. Gemini로 레이아웃 분석 (원본 보면서)
#     layout = analyze_layout_with_gemini(original_image_path)
    
#     # 2. 분석된 위치로 마스크 생성
#     mask_path = create_smart_mask(original_image_path, layout)
    
#     # 3. 청소 (글자 지우기)
#     clean_path = remove_text_with_clipdrop(original_image_path)

#     # 4. AI 생성 (스타일 입히기)
#     print("  🎨 [Vertex AI] 텍스트 디자인 생성 중...")
#     try:
#         model = ImageGenerationModel.from_pretrained("imagegeneration@006")
#         base_img = VertexImage.load_from_file(clean_path)
#         mask_img = VertexImage.load_from_file(mask_path)

#         # ⭐️ 가장 강력한 프롬프트
#         prompt = f"""
#         Task: Render Text into the masked areas.
        
#         1. Upper Area (Title):
#            - Write: "{title}"
#            - Style: Large, Bold, 3D, Artistic Font.
#            - Color: Make it pop against the background.
           
#         2. Lower Area (Info):
#            - Write: "{date} {location}"
#            - Style: Clean, White, Sans-serif Font.
           
#         3. Background: Keep seamless.
#         """

#         generated_images = model.edit_image(
#             base_image=base_img,
#             mask=mask_img,
#             prompt=prompt,
#             guidance_scale=60,
#             number_of_images=1,
#             language="ko"
#         )

#         final_output_path = original_image_path.replace(".png", "_final_design.png")
#         if generated_images:
#             generated_images[0].save(final_output_path)
#             print(f"✨ [완료] 포스터 완성: {final_output_path}")
#             return final_output_path
#         return clean_path

#     except Exception as e:
#         print(f"🚨 Vertex AI 오류: {e}")
#         return clean_path