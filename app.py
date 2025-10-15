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

# 여행지 추천 시스템 TravelRecommender 클래스  파일 읽어오기
from project_root.recommend_module import TravelRecommender


# 앱초기화
app = Flask(__name__)
CORS(app) # 프론트에서 접근 가능하게 허용(모든 도메인 허용 - 개발용)
app.config.from_object(Config)


# DB 연동 환경변수
if "MONGO_URI" in os.environ:
    app.config["MONGO_URI"] = os.environ["MONGO_URI"]

# DB 환경변수 버그확인 코드
print("DEBUG env MONGO_URI =", os.environ.get("MONGO_URI"))
print("DEBUG conf MONGO_URI =", app.config.get("MONGO_URI"))


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


# ---------------------------------
# 여행지 추천 코드


# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # app.py 경로
recommender = TravelRecommender(base_dir=BASE_DIR)

    

@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "입력 데이터가 없습니다."}), 400

        # 추천 실행 (상위 3개 결과 반환)
        result = recommender.recommend_places(data, top_k=3)

        return jsonify({
            "parsed_input": result.get("parsed_input"),
            "recommendations": result.get("recommendations", [])[:3],
            "total_places": result.get("total_places")
        })
    
    except Exception as e:
        print("추천 오류:", e)
        return jsonify({"error": "추천 실패", "detail": str(e)}), 500
    



# 서버가 작동중인 지 확인하기 위함
@app.route('/health', methods=['GET'])
def health():
    # 모델이 정상적으로 로드됐는지도 상태에 포함
    # DB 연결 상태도 체크

    db_ok = False # 기본
    db_error = None # 기본
    
    try:
        mongo.cx.admin.command("ping")
        db_ok = True
    except:
        db_error = str(e) # 에러메시지 저
        
    # 모델 연결 체크
    places_loaded = len(recommender.df) if getattr(recommender, "df", None) is not None else 0
    embedding_ready = hasattr(recommender, "place_embeddings")

    # 전체 연결상태 판단
    overall_ok = db_ok and places_loaded > 0 and embedding_ready # 전부 연결됐을 때
    status_code = 200 if overall_ok else 503  # 전부 연결 -> 200, 하나라도 연결 안됨 -> 503

    return jsonify({
        "status": "ok" if overall_ok else "degraded",
        "db_connected": db_ok,
        "db_error": db_error if not db_ok else None,
        "places_loaded": places_loaded,
        "embedding_ready": embedding_ready
    }), status_code



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


# ------------------------------
# 서버 링크 검색 시 나오는 문장
@app.route('/')
def home():
    return '서버 잘 작동 중입니다.'


if __name__ == "__main__":
    # 환경변수 설정
    port = int(os.environ.get("PORT", 5000))
    # 모든 IP주소에서 접근 가능
    app.run(debug=False, host="0.0.0.0", port=port)
