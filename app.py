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
CORS(app) # 프론트에서 접근 가능하게 허용(모든 도메인 허용 - 개발용)
app.config.from_object(Config)

#초기화
db.init_app(app) 
jwt = JWTManager(app)

# 회원가입
@app.route('/signup', methods=['POST'])
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
@app.route('/login', methods=['POST'])
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


# 모델 관련 라이브러리
import joblib
import os


# 학습된 모델 불러오기
vectorizer = joblib.load("models/tfidf_vectorizer.pkl")
season_model = joblib.load("models/season_model.pkl")
nature_model = joblib.load("models/nature_model.pkl")
vibe_model = joblib.load("models/vibe_model.pkl")
target_model = joblib.load("models/target_model.pkl")


# 서버 링크 검색 시 나오는 문장
@app.route('/')
def home():
    return '서버 잘 작동 중입니다.'

BASE = os.path.dirname(__file__) # app.py의 절대 경로 기준으로 디렉토리 반환
def model_path(name): 
    return os.path.join(BASE, "models", name)

try:
    # 학습된 모델 불러오기
    vectorizer = joblib.load("models/tfidf_vectorizer.pkl")
    season_model = joblib.load("models/season_model.pkl")
    nature_model = joblib.load("models/nature_model.pkl")
    vibe_model = joblib.load("models/vibe_model.pkl")
    target_model = joblib.load("models/target_model.pkl")


except Exception as e:
    print("모델 로드 실패:", e)
    # raise를 하면 모델 로드 실패 시 앱 중단, raise X 시 서버 계속 동작

@app.route('/recommend', methods=['POST'])
def recommend():
    if not vectorizer or not season_model:
        return jsonify({"error": "모델이 로드되지 않아 추천을 제공할 수 없음"}), 500
    
    data = request.get_json(silent=True)
    if not data or 'description' not in data:
        return jsonify({"error":"description 필드가 필요함"}), 400
    
    user_input = data['description', '']
    
    try:
        X = vectorizer.transform([user_input])
        season = season_model.predict(X)[0]
        nature = nature_model.predict(X)[0]
        vibe = vibe_model.predict(X)[0]
        target = target_model.predict(X)[0]
        
        return jsonify({
            "season": season,
            "nature": nature,
            "vibe": vibe,
            "target": target
        })
    except Exception as e:
        return jsonify({"error": "예측 실패", "detail": str(e)}), 500


# 서버가 작동중인 지 확인하기 위함
@app.route('/health', methods=['GET'])
def health():
    # 모델이 정상적으로 로드됐는지도 상태에 포함
    return jsonify({
        "status": "ok",
        "models_loaded": all([vectorizer, season_model, nature_model, vibe_model, target_model])
    })

# 별점 등록 및 업데이트
@app.route('/rating', methods=['POST'])
def submit_rating():
    data = request.json
    user_id = data.get('user_id')
    travel_id = data.get('travel_id') # 별점 남긴 여행지id
    score = data.get('score')

    # 필수 데이터 없을 시 오류처리
    if not all([user_id, travel_id, score]):
        return jsonify({"error": "Missing data"}), 400

    # 같은 user가 같은 여행지에 준 별점이 있는지 확인
    rating = Rating.query.filter_by(user_id=user_id, travel_id=travel_id).first()

    # 별점이 있을 시 기존 별점 업데이트
    if rating:
        rating.score = score
    else:
        rating = Rating(user_id=user_id, travel_id=travel_id, score=score)
        db.session.add(rating)
    db.session.commit() # DB에 반영
    
    return jsonify({"message": "Rating submitted successfully"})

# 별점 피드백 추가 시
# @app.route('/rating/feedback', methods=['POST'])

if __name__ == "__main__":
    # 환경변수 설정
    port = int(os.environ.get("PORT", 5000))
    # 모든 IP주소에서 접근 가능
    app.run(debug=False, host="0.0.0.0", port=port)
