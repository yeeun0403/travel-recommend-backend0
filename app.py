from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
# os: 운영체제 기능 사용 모듈

app = Flask(__name__)
CORS(app) # 프론트에서 접근 가능하게 허용

# CSV 파일 읽어오기
place_df = pd.read_csv("강원도_관광지_20_예시.csv")


# 서버 링크 검색 시 나오는 문장
@app.route('/')
def home():
    return '서버 잘 작동 중입니다.'

@app.route('/recommend', methods=['POST'])
def recommend():
    data = request.get_json()
    tags = data.get("tags", [])

    # 선택된 태그가 없을 시 출력
    if not tags:
        return jsonify({"result": [], "message": "태그를 선택해주세요."})

    #추천 결과를 담을 리스트
    results = []

    
    for _, row in place_df.iterrows():
        row_tags = []
        for col in ['tags', 'season', 'nature', 'vibe', 'target']:
            if pd.notna(row[col]):
                # 쉼표+띄어쓰기로 구분해서 리스트로 만들기
                row_tags.extend([t.strip() for t in row[col].split(",")])

        # 중복 제거
        row_tags = list(set(row_tags))

        # 사용자가 선택한 태그 중 하나라도 포함되어 있으면 추천
        if any(tag in row_tags for tag in tags):
            results.append({
                "name": row["name"],
                "city": row["city"],
                "description": row["description"],
                "tags": row_tags
            })

    if results:
        return jsonify({"result": results, "message": "추천 성공"})
    else:
        return jsonify({"result": [], "message": "추천 결과 없음"})


if __name__ == "__main__":
    # 환경변수 설정
    port = int(os.environ.get("PORT", 5000))
    # 모든 IP주소에서 접근 가능
    app.run(debug=False, host="0.0.0.0", port=port)
