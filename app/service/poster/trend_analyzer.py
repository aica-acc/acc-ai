import pandas as pd
import json
import warnings
import os

CSV_PATH = "poster_scores_korean_progress.csv" # 1. CSV DB 경로
# ( 참고: 이 CSV 파일은 app.py가 있는 'src' 폴더가 아니라,
#  'uv_festival' 최상위 폴더에 있어야 한다.
#  만약 'src' 폴더 안에 있다면 CSV_PATH = "poster_scores_korean_progress.csv"로 수정)
CSV_FULL_PATH = os.path.join(os.path.dirname(__file__), CSV_PATH)

warnings.filterwarnings("ignore", 'This pattern is interpreted as a regular expression')

def get_poster_trends(keywords_list):
    """
    CSV 데이터베이스를 읽어,
    주어진 '키워드 리스트'와 '연관된' 포스터 트렌드를 '요약'해서 반환합니다.
    """
    print(f"  [trend_analyzer] 1. '{CSV_FULL_PATH}' DB 로드 중...")
    
    try:
        if not os.path.exists(CSV_FULL_PATH):
            print(f" CSV 파일 없음: '{CSV_FULL_PATH}' 파일을 찾을 수 없습니다.")
            return {"status": "error", "message": f"'{CSV_PATH}' 파일을 찾을 수 없습니다."}
            
        try:
            df = pd.read_csv(CSV_FULL_PATH)
        except UnicodeDecodeError:
            df = pd.read_csv(CSV_FULL_PATH, encoding='euc-kr')
        
        # (AI 평가 설명이 들어있는 4개의 설명 열)
        description_cols = ['Aesthetic_Description', 'Thematic_Description', 'Readability_Description', 'Creativity_Description']
        required_cols = ['Aesthetic', 'Thematic', 'Readability', 'Creativity', 'IMAGE_PATH'] + description_cols

        if not all(col in df.columns for col in required_cols):
            missing_cols = [col for col in required_cols if col not in df.columns]
            return {"status": "error", "message": f"CSV 필수 열 누락: {missing_cols}"}

        # (검색용 텍스트 열 생성)
        df['Combined_Search_Text'] = df[description_cols].fillna('').agg(' '.join, axis=1)

        print(f"  [trend_analyzer] 2. 키워드로 필터링 시작: {keywords_list}")
        
        filtered_dfs = [] 
        for keyword in keywords_list:
            if not keyword or not keyword.strip(): continue
            mask = df['Combined_Search_Text'].str.contains(keyword, case=False, na=False)
            filtered_dfs.append(df[mask])
            
        if not filtered_dfs:
            return {"status": "no_match", "message": "연관된 포스터 트렌드를 찾지 못했습니다."}
            
        final_filtered_df = pd.concat(filtered_dfs).drop_duplicates()
        
        if final_filtered_df.empty:
             return {"status": "no_match", "message": "연관된 포스터 트렌드를 찾지 못했습니다."}
        
        print(f"  [trend_analyzer] 3. '연관 포스터 {len(final_filtered_df)}개' 요약 중...")

        # (트렌드 보고서 생성)
        avg_scores = {
            "average_aesthetic": round(final_filtered_df['Aesthetic'].mean(), 1),
            "average_thematic": round(final_filtered_df['Thematic'].mean(), 1),
            "average_readability": round(final_filtered_df['Readability'].mean(), 1),
            "average_creativity": round(final_filtered_df['Creativity'].mean(), 1)
        }
        
        top_creativity_poster = final_filtered_df.nlargest(1, 'Creativity')
        top_creativity_desc = top_creativity_poster['Creativity_Description'].values[0]
        top_creativity_example_file = top_creativity_poster['IMAGE_PATH'].values[0] 

        top_readability_poster = final_filtered_df.nlargest(1, 'Readability')
        top_readability_desc = top_readability_poster['Readability_Description'].values[0]
        top_readability_example_file = top_readability_poster['IMAGE_PATH'].values[0]

        report = {
            "status": "success",
            "matched_poster_count": len(final_filtered_df),
            "related_keywords_used": keywords_list,
            "average_scores_of_matches": avg_scores,
            "top_creativity_example": {
                "file_name": top_creativity_example_file,
                "description": top_creativity_desc
            },
            "top_readability_example": {
                "file_name": top_readability_example_file,
                "description": top_readability_desc
            }
        }
        return report
        
    except Exception as e:
        print(f"  [trend_analyzer] 분석 중 심각한 오류 발생: {e}")
        return {"status": "error", "message": str(e)}