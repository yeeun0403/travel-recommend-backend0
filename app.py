from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config

# 회원가입, 로그인 관련
import datetime
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity

# DB 관련
from extensions import mongo
from user_utils import username_exists, email_exists, create_user, get_user_by_username, check_user_password

# 모델 관련 라이브러리
import joblib, os

# MongoDB _id 검색 위해 문자열을 ObjectId로 변환(변환 실패시 에러 반환)
from bson.objectid import ObjectId


# 앱초기화
app = Flask(__name__)
CORS(app) # 프론트에서 접근 가능하게 허용(모든 도메인 허용 - 개발용)
app.config.from_object(Config)

mongo.init_app(app) 
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

    user_id = create_user(username, email, password)
    return jsonify({'message': '사용자가 성공적으로 생성되었습니다.', 'user_id': user_id}), 201


# 로그인
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': '아이디와 비밀번호를 입력해주세요.'}), 400

    user = get_user_by_username(username)
    
    if not user or not check_user_password(user, password):
        return jsonify({'error': '아이디 또는 비밀번호 오류'}), 401

    # JWT 발급
    access_token = create_access_token(identity=str(user['_id']))
    return jsonify({'access_token': access_token}), 200


# 마이페이지(로그인된 사용자만 접근 가능)
@app.route('/mypage', methods=['GET'])
@jwt_required()
def mypage():
    try:
        current_user_id = ObjectId(get_jwt_identity())
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    user = mongo.db.users.find_one({"_id": current_user_id})
    
    if not user:
        return jsonify({"error": "사용자를 찾을 수 없습니다."}), 404

    return jsonify({
        "id": str(user['_id']),
        "username": user['username'],
        "email": user['email'],
        "message": f"{user['username']}님의 마이페이지입니다!"
    })



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
    # DB 연결 상태도 체크
    try:
        mongo.db.command("ping")
        db_status = True
    except:
        db_status = False
        
    return jsonify({
        "status": "ok",
        "models_loaded": all([vectorizer, season_model, nature_model, vibe_model, target_model]),
        "db_connected": db_status
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

    # ObjectId로 변환(변환 실패시 에러 반환)
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 user_id"}), 400

    # 같은 user가 같은 여행지에 준 별점이 있는지 확인
    existing_rating = mongo.db.ratings.find_one({"user_id": user_oid, "travel_id": travel_id})

    # 별점이 있을 시 기존 별점 업데이트
    if existing_rating:
        mongo.db.ratings.update_one(
            {"_id": existing_rating["_id"]},
            {"$set": {"score": score, "updated_at": datetime.datetime.utcnow()}}
        )
    else:
         mongo.db.ratings.insert_one({
            "user_id": user_oid,
            "travel_id": travel_id,
            "score": score,
            "created_at": datetime.datetime.utcnow()
        })
    
    return jsonify({"message": "Rating submitted successfully"})

# 별점 피드백 추가 시
# @app.route('/rating/feedback', methods=['POST'])

if __name__ == "__main__":
    # 환경변수 설정
    port = int(os.environ.get("PORT", 5000))
    # 모든 IP주소에서 접근 가능
    app.run(debug=False, host="0.0.0.0", port=port)
