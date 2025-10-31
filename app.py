from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config
import pandas as pd
import numpy as np

# 회원가입, 로그인 관련
import datetime
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request

# DB 관련
from extensions import mongo
from user_utils import username_exists, email_exists, create_user, get_user_by_username, check_user_password

# 모델 관련 라이브러리
import joblib, os

# MongoDB _id 검색 위해 문자열을 ObjectId로 변환(변환 실패시 에러 반환)
from bson.objectid import ObjectId

# 여행지 추천 시스템 GangwonPlaceRecommender 클래스  파일 읽어오기
from project_root1.recommend_module import GangwonPlaceRecommender

# 지도URL
from urllib.parse import quote


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

# 전역 JSON 검사
@app.before_request
def enforce_json_for_api():
    # JSON 바디를 요구하는 엔드포인트만 제한
    json_required_paths = {"/signup", "/login", "/rating", "/recommend"}
    if request.path in json_required_paths and request.method == "POST":
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

# ===========================================================================================
# 기본 코드



# 회원가입
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username') # 사용자 로그인용 아이디
    email = data.get('email')
    password = data.get('password')
    name = data.get('name') # 사용자 이름

    if not username or not email or not password or not name:
        return jsonify({'error': '모든 값을 입력해주세요.'}), 400
    
    if username_exists(username):
        return jsonify({'error': '이미 존재하는 아이디입니다.'}), 409

    if email_exists(email):
        return jsonify({'error': '이미 존재하는 이메일입니다.'}), 409

    user_id = create_user(username, email, password, name)
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

    # ratings 호출
    cur = mongo.db.ratings.find({"user_id": current_user_id}).sort("updated_at", -1)
    rating_list = list(cur)

    # travel_id 목록 추출
    travel_ids = [r.get("travel_id") for r in rating_list if r.get("travel_id")]

    # 여행지 메타 조인 (추가된 필드 포함)
    travel_docs = list(mongo.db.travels.find(
        {"travel_id": {"$in": travel_ids}},
        {
            "_id": 0,
            "travel_id": 1,
            "name": 1,
            "image_urls": 1,
            "location": 1,
            "address": 1,                # optional
            "short_description": 1       # optional
        }
    ))
    tmap = {d["travel_id"]: d for d in travel_docs}

    ratings = []
    for r in rating_list:
        meta = tmap.get(r["travel_id"], {})
        loc = meta.get("location", {})

        # 썸네일(첫번째 이미지) 처리
        raw = meta.get("image_urls")
        if isinstance(raw, list) and raw:
            thumbnail = raw[0]
        elif isinstance(raw, str) and raw.strip():
            thumbnail = raw.split(",")[0].strip()
        else:
            thumbnail = None

        ratings.append({
            "id": str(r["_id"]),
            "user_id": str(r["user_id"]),
            "travel_id": r.get("travel_id"),
            "score": r.get("score"),
            "feedback_tags": r.get("feedback_tags", []),
            "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            "updated_at": r.get("updated_at").isoformat() if r.get("updated_at") else None,

            # 여행지 메타정보 추가
            "name": meta.get("name"),
            "image_urls": raw or [],        # 썸네일 포함
            "location": {
                "lat": loc.get("lat"),
                "lng": loc.get("lng")
            },

            # optional — 요청한 필드 (없어도 JSON에 표시됨)
            "address": meta.get("address"),                # optional
            "short_description": meta.get("short_description")  # optional
        })    


    return jsonify({
        "id": str(user['_id']),
        "username": user['username'],
        "email": user['email'],
        "message": f"{user['username']}님의 마이페이지입니다!",
        "ratings": ratings
    }), 200




# ==================================================================================
# 여행지 추천 코드



# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # app.py 경로
PROJECT_ROOT = os.path.join(BASE_DIR, "project_root1")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PROCESSED_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "gangwon_matching_results_sorted.csv")
EMBEDDING_NPY = os.path.join(PROJECT_ROOT, "place_embeddings_v2.npy")

# 초기
recommender = GangwonPlaceRecommender(config_path=CONFIG_PATH)

# 모델/ 데이터 로딩
try:
    recommender.df = pd.read_csv(PROCESSED_CSV).reset_index(drop=True)
    recommender.place_embeddings = np.load(EMBEDDING_NPY)
except Exception as e:
    print("[WARN] 추천기 초기 로딩 실패.", e)

try:
    print("[BOOT] df loaded rows:", len(recommender.df) if getattr(recommender, "df", None) is not None else 0)
    print("[BOOT] df has 'travel_id':", bool(getattr(recommender, "df", None) is not None and "travel_id" in list(recommender.df.columns)))
    if getattr(recommender, "place_embeddings", None) is not None:
        print("[BOOT] embeddings shape:", getattr(recommender.place_embeddings, "shape", None))
    else:
        print("[BOOT] embeddings NOT loaded")
except Exception as e:
    print("[BOOT] startup check failed:", e)


# 지도 URL 자동생성(클릭하면 카카오맵 오픈)
def build_map_url(name, lat, lng):
    enc_name = quote(name or "", safe="")
    return f"https://map.kakao.com/link/map/{enc_name},{lat},{lng}"



@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        body = request.get_json(silent=True) or {}

        # 1) 로그인 유저 확인
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

        # 2) 설문태그(DB)
        user_tags = []
        if user_id:
            try:
                doc = mongo.db.user_tags.find_one(
                    {"user_id": ObjectId(user_id)},
                    {"_id": 0, "tags": 1}
                )
                if doc and doc.get("tags"):
                    user_tags = doc["tags"]
            except Exception as e:
                print("[WARN] user_tags 議고쉶 �ㅽ뙣:", e)

        # 3) 입력 우선순위 결정
        data_for_model = {}
        mode = "fallback"

        # 우선순위 1: free_text가 있으면 그대로 사용
        if isinstance(body.get("free_text"), str) and body["free_text"].strip():
            data_for_model = {"free_text": body["free_text"].strip()}
            mode = "free_text"

        # 우선순위 2: 카테고리별로 구분된 태그가 있으면 그대로 전달
        elif any(body.get(k) for k in ['season', 'nature', 'vibe', 'target']):
            data_for_model = {
                k: body.get(k, [])
                for k in ['season', 'nature', 'vibe', 'target']
                if body.get(k)
            }
            mode = "categorized_tags"
            print(f"[INFO] Categorized tags received: {data_for_model}")

        # 우선순위 3: 단순 태그 리스트가 있으면 free_text로 변환
        elif isinstance(body.get("tags"), list) and body["tags"]:
            norm = [str(t).strip().lstrip("#").lower() for t in body["tags"] if str(t).strip()]
            # ✅ 수정: 태그를 free_text로 변환 (모델이 parse_free_text()로 자동 분류)
            data_for_model = {"free_text": " ".join(norm)}
            mode = "tags_as_text"
            print(f"[INFO] Converting tags to free_text: {data_for_model}")

        # 우선순위 4: DB에 저장된 설문 태그
        elif user_tags:
            # ✅ 수정: 설문 태그도 free_text로 변환
            data_for_model = {"free_text": " ".join(user_tags)}
            mode = "survey"
            print(f"[INFO] Using survey tags as free_text: {data_for_model}")

        # 아무 입력도 없으면 빈 딕셔너리
        else:
            data_for_model = {}
            mode = "fallback"

        # ✅ 디버깅 로그 추가
        print(f"[DEBUG] Mode: {mode}")
        print(f"[DEBUG] data_for_model: {data_for_model}")


        # 4) 추천 수행
        result = recommender.recommend_places(data_for_model, top_k=3)
        recs = result.get("recommendations", [])[:3]

        # 디버깅 로그
        print(f"[DEBUG] Number of recommendations: {len(recs)}")
        if recs:
            print(f"[DEBUG] First rec tag_score: {recs[0].get('tag_score')}")
        #상위 결과 비교(최대 10개)
        for idx, r in enumerate(recs[:10]):  # 상위 10개만
            print("[DEBUG TOP] travel_id:", r["travel_id"], "tag_score:", r["tag_score"])
            

        # 5) travel_id 議댁옱 �뺤씤
        recs = [r for r in recs if r.get("travel_id") is not None]
        if not recs:
            return jsonify({"error": "異붿쿇 寃곌낵�� �좏슚�� travel_id媛� �놁뒿�덈떎."}), 500

        print("[DEBUG] keys in first rec:", recs[0].keys() if recs else "NO RECS")

        # 6) 여행지 메타 조인
        travel_ids = [r["travel_id"] for r in recs]
        travel_docs = list(mongo.db.travels.find(
        {"travel_id": {"$in": travel_ids}},
        {"_id": 0, "travel_id": 1, "name": 1,"image_urls": 1, "location": 1, "latitude": 1, "longitude": 1}
            ))
        tmap = {d["travel_id"]: d for d in travel_docs}

        def build_map_url(name, lat, lng):
            from urllib.parse import quote
            enc = quote(name or "", safe="")
            return f"https://map.kakao.com/link/map/{enc},{lat},{lng}"

        # 7) 응답 R1 형태로 변환
        enriched = []
        for r in recs:
            meta = tmap.get(r["travel_id"])
            if not meta:
                continue
            
            loc = meta.get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")

            raw = meta.get("image_urls")

            # 1. 배열이면 그대로
            if isinstance(raw, list):
                image_urls = raw

            # 2. 문자열이면 콤마 기준으로 나눔
            elif isinstance(raw, str) and raw.strip():
                image_urls = [url.strip() for url in raw.split(",")]

            # 3. 단일 값 image_url만 있는 경우
            elif meta.get("image_url"):
                image_urls = [meta.get("image_url")]

            # 4. 아무것도 없을 때
            else:
                image_urls = []

            enriched.append({
                "travel_id": r["travel_id"],
                "name": meta.get("name"),
                "image_urls": image_urls,
                "location": {
                    "lat": lat,
                    "lng": lng
                },
                "map_url": build_map_url(meta.get("name"), lat, lng),
                "scores": {
                    "hybrid": r.get("hybrid_score"),
                    "similarity": r.get("similarity_score"),
                    "tag_match": r.get("tag_score")
                }
            })

        return jsonify({
            "status": "success",
            "mode": mode,
            "recommendations": enriched
        }), 200

    except Exception as e:
        print("異붿쿇 �ㅻ쪟:", e)
        return jsonify({"error": "異붿쿇 �ㅽ뙣", "detail": str(e)}), 500
    

# ==========================================================================
# 북마크, 별점, 태그 관련 코드



# 별점 등록 업데이트
@app.route('/rating', methods=['POST'])
@jwt_required()
def submit_rating():
    data = request.get_json() or {}

    # user_id는 더 이상 body에서 받지 않음
    try:
        user_id = get_jwt_identity()  # 로그인한 유저의 _id
        user_oid = ObjectId(user_id)
    except Exception:
        return jsonify({"error": "잘못된 사용자 인증 정보입니다."}), 400

    travel_id = data.get('travel_id')  # 별점 남긴 여행지id
    score = data.get('score')

    # 심화: 피드백 기능
    feedback_tags = data.get('feedback_tags', [])
    if not isinstance(feedback_tags, list):
        feedback_tags = [feedback_tags]

    # 필수 데이터 체크
    if not all([travel_id, score]):
        return jsonify({"error": "travel_id와 score는 필수입니다."}), 400

    # score 숫자/범위 체크
    try:
        score_f = float(score)
    except:
        return jsonify({"error": "별점은 숫자여야 합니다."}), 400

    if not (0.0 <= score_f <= 5.0):
        return jsonify({"error": "별점은 0~5 사이여야 합니다."}), 400

    # travel_id 정수 변환
    try:
        travel_id_int = int(travel_id)
    except:
        return jsonify({"error": "travel_id는 정수여야 합니다."}), 400

    now = datetime.datetime.utcnow()

    # 자동 북마크 처리
    bookmark = mongo.db.bookmarks.find_one({"user_id": user_oid, "travel_id": travel_id_int})
    if not bookmark:
        mongo.db.bookmarks.insert_one({
            "user_id": user_oid,
            "travel_id": travel_id_int,
            "tags": [],  # 초기 태그 없음
            "created_at": now
        })
        print(f"[DEBUG] 자동 북마크 생성됨 travel_id={travel_id_int}")

    # 기존 별점 업데이트 또는 생성
    result = mongo.db.ratings.update_one(
        {"user_id": user_oid, "travel_id": travel_id_int},
        {
            "$set": {
                "score": score_f,
                "feedback_tags": feedback_tags,
                "updated_at": now
            },
            "$setOnInsert": {"created_at": now}
        },
        upsert=True
    )

    # 응답 메시지
    if result.upserted_id:
        message = "별점이 새로 등록되었습니다."
        status = 201
    elif result.modified_count > 0:
        message = "별점이 수정되었습니다."
        status = 200
    else:
        message = "기존 별점과 동일하여 변경되지 않았습니다."
        status = 200

    return jsonify({"message": message}), status



# 마이페이지에서 태그 설문조사
@app.route('/mypage/tags', methods=['POST'])
@jwt_required()
def save_user_tags():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    body = request.get_json() or {}
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    # 정규화(공백/중복 제거, '#' 제거, 소문자)
    norm = []
    seen = set()
    for t in tags:
        s = str(t).strip().lstrip("#").lower()
        if s and s not in seen:
            seen.add(s)
            norm.append(s)

    mongo.db.user_tags.update_one(
        {"user_id": user_oid},
        {"$set": {"tags": norm, "updated_at": datetime.datetime.utcnow()}},
        upsert=True
    )
    return jsonify({"user_id": user_id, "tags": norm}), 200




# 마이페이지에서 설문한 태그 확인
@app.route('/mypage/tags', methods=['GET'])
@jwt_required()
def get_user_tags():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    doc = mongo.db.user_tags.find_one({"user_id": user_oid}, {"_id": 0, "tags": 1})
    return jsonify({"user_id": user_id, "tags": doc.get("tags", []) if doc else []}), 200




# 추천 받은 여행지 북마크할 때 호출
@app.route('/mypage/bookmarks/<int:travel_id>', methods=['POST'])
@jwt_required()
def toggle_bookmark(travel_id):
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    existing = mongo.db.bookmarks.find_one({"user_id": user_oid, "travel_id": travel_id})
    if existing:
        mongo.db.bookmarks.delete_one({"_id": existing["_id"]})
        return jsonify({"status": "unbookmarked", "travel_id": travel_id}), 200
    else:
        mongo.db.bookmarks.insert_one({
            "user_id": user_oid,
            "travel_id": travel_id,
            "tags": [],  # 초기엔 태그 없음
            "created_at": datetime.datetime.utcnow()
        })
        return jsonify({"status": "bookmarked", "travel_id": travel_id}), 200


# 북마크 한 여행지 목록 확
@app.route('/mypage/bookmarks', methods=['GET'])
@jwt_required()
def list_my_bookmarks():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    # bookmarks 조인: travels에서 메타 가져오기
    bs = list(mongo.db.bookmarks.find({"user_id": user_oid}))
    
    travel_ids = [b["travel_id"] for b in bs]
    
    travel_docs = list(mongo.db.travels.find(
        {"travel_id": {"$in": travel_ids}},
        {"_id": 0, "travel_id": 1, "name": 1,"image_urls":1, "location": 1}
    ))
    tmap = {d["travel_id"]: d for d in travel_docs}

    items = []
    for b in bs:
        meta = tmap.get(b["travel_id"], {})
        loc = meta.get("location", {})
        image_urls = meta.get("image_urls")
        if not image_urls and meta.get("image_urls"):
            urls = str(meta.get("image_urls")).split(",")
            image_urls = urls[0].strip() if urls else None
        items.append({
            "travel_id": b["travel_id"],
            "name": meta.get("name"),
            "image_urls": meta.get("image_urls"),
            "location": {
                "lat": loc.get("lat"),
                "lng": loc.get("lng")
            },
            "my_tags": b.get("tags", []),
            "bookmarked_at": b.get("created_at").isoformat() if b.get("created_at") else None
        })
        
    return jsonify({"bookmarks": items, "count": len(items)}), 200


# 북마크한 여행지에 사용자가 태그 추가
@app.route('/mypage/bookmarks/<int:travel_id>/tags', methods=['POST'])
@jwt_required()
def save_bookmark_tags(travel_id):
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "잘못된 사용자 ID"}), 400

    body = request.get_json() or {}
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    # 정규화
    norm, seen = [], set()
    for t in tags:
        s = str(t).strip().lstrip("#").lower()
        if s and s not in seen:
            seen.add(s)
            norm.append(s)

    # 내 북마크인지 확인
    bk = mongo.db.bookmarks.find_one({"user_id": user_oid, "travel_id": travel_id})
    if not bk:
        return jsonify({"error": "해당 여행지는 북마크되어 있지 않습니다."}), 404

    mongo.db.bookmarks.update_one(
        {"_id": bk["_id"]},
        {"$set": {"tags": norm}}
    )
    return jsonify({"travel_id": travel_id, "my_tags": norm}), 200


# ===================================================================================
# 확정 코드


# 서버가 작동중인 지 확인하기 위함
@app.route('/health', methods=['GET'])
def health():
    # 모델이 정상적으로 로드됐는지도 상태에 포함
    # DB 연결 상태도 체크

    db_ok = False # 湲곕낯
    db_error = None # 湲곕낯
    
    try:
        mongo.cx.admin.command("ping")
        db_ok = True
    except Exception as e:
        db_error = str(e) # 오류메시지 저장
        
    # 모델 연결 체크
    places_loaded = len(recommender.df) if getattr(recommender, "df", None) is not None else 0
    embedding_ready = hasattr(recommender, "place_embeddings")

    # 전체 연결상태 판단
    overall_ok = db_ok and places_loaded > 0 and embedding_ready # 전부 연결됐을 때
    status_code = 200 if overall_ok else 503  # 전부 연결 -> 200, 하나라도 연결 안 됨 -> 503

    return jsonify({
        "status": "ok" if overall_ok else "degraded",
        "db_connected": db_ok,
        "db_error": db_error if not db_ok else None,
        "places_loaded": places_loaded,
        "embedding_ready": embedding_ready
    }), status_code




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
