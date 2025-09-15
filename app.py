from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
from config import Config

# 회원가입, 로그인 관련
from werkzeug.security import generate_password_hash, check_password_hash
import jwt, datetime
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

# DB 관련
from extensions import db
from user_utils import get_user_by_username, username_exists, email_exists, user_exists, create_user


app = Flask(__name__)
CORS(app) # 프론트에서 접근 가능하게 허용
app.config.from_object(Config)

#초기화
db.init_app(app) 
jwt = JWTManager(app)

# 회원가입
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({'error': '모든 값을 입력해주세요.'}), 400
    
    if username_exists(username):
        return jsonify({'error': '이미 존재하는 아이디입니다.'}), 409

    if email_exists(email):
        return jsonify({'error': '이미 존재하는 이메일입니다.'}), 409

    new_user = create_user(username, email, password)
    return jsonify({'message': '사용자가 성공적으로 생성되었습니다.',
                    'user_id': new_user.id}), 201
    

# 로그인
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    user = get_user_by_username(username)
    
    if not user or not user.check_password(password):
        return jsonify({'error': '아이디 또는 비밀번호 오류'}), 401

    if user and user.check_password(password):
        access_token = create_access_token(identity=username)
        return jsonify({'access_token': access_token}), 200


# 마이페이지(로그인된 사용자만 접근 가능)
@app.route('/mypage', methods=['GET'])
@jwt_required()
def mypage():
    current_user = get_jwt_identity()
    return jsonify({'message': f'{current_user}님의 마이페이지입니다!'})



# 여행지 추천 출력
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
