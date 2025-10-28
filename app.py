from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config
import pandas as pd
import numpy as np

# �뚯썝媛���, 濡쒓렇�� 愿���
import datetime
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request

# DB 愿���
from extensions import mongo
from user_utils import username_exists, email_exists, create_user, get_user_by_username, check_user_password

# 紐⑤뜽 愿��� �쇱씠釉뚮윭由�
import joblib, os

# MongoDB _id 寃��� �꾪빐 臾몄옄�댁쓣 ObjectId濡� 蹂���(蹂��� �ㅽ뙣�� �먮윭 諛섑솚)
from bson.objectid import ObjectId

# �ы뻾吏� 異붿쿇 �쒖뒪�� GangwonPlaceRecommender �대옒��  �뚯씪 �쎌뼱�ㅺ린
from project_root1.recommend_module import GangwonPlaceRecommender

# 吏��꼀RL
from urllib.parse import quote


# �깆큹湲고솕
app = Flask(__name__)
CORS(app) # �꾨줎�몄뿉�� �묎렐 媛��ν븯寃� �덉슜(紐⑤뱺 �꾨찓�� �덉슜 - 媛쒕컻��)
app.config.from_object(Config)


# DB �곕룞 �섍꼍蹂���
if "MONGO_URI" in os.environ:
    app.config["MONGO_URI"] = os.environ["MONGO_URI"]

# DB �섍꼍蹂��� 踰꾧렇�뺤씤 肄붾뱶
print("DEBUG env MONGO_URI =", os.environ.get("MONGO_URI"))
print("DEBUG conf MONGO_URI =", app.config.get("MONGO_URI"))


mongo.init_app(app) 
jwt = JWTManager(app)

# �꾩뿭 JSON 寃���
@app.before_request
def enforce_json_for_api():
    # JSON 諛붾뵒瑜� �붽뎄�섎뒗 �붾뱶�ъ씤�몃쭔 �쒗븳
    json_required_paths = {"/signup", "/login", "/rating", "/recommend"}
    if request.path in json_required_paths and request.method == "POST":
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415
    

# �뚯썝媛���
@app.route('/signup', methods=['POST'])
def signup():
    data = request.get_json()
    username = data.get('username') # �ъ슜�� 濡쒓렇�몄슜 �꾩씠��
    email = data.get('email')
    password = data.get('password')
    name = data.get('name') # �ъ슜�� �대쫫

    if not username or not email or not password or not name:
        return jsonify({'error': '紐⑤뱺 媛믪쓣 �낅젰�댁＜�몄슂.'}), 400
    
    if username_exists(username):
        return jsonify({'error': '�대� 議댁옱�섎뒗 �꾩씠�붿엯�덈떎.'}), 409

    if email_exists(email):
        return jsonify({'error': '�대� 議댁옱�섎뒗 �대찓�쇱엯�덈떎.'}), 409

    user_id = create_user(username, email, password, name)
    return jsonify({'message': '�ъ슜�먭� �깃났�곸쑝濡� �앹꽦�섏뿀�듬땲��.', 'user_id': user_id}), 201


# 濡쒓렇��
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': '�꾩씠�붿� 鍮꾨�踰덊샇瑜� �낅젰�댁＜�몄슂.'}), 400

    user = get_user_by_username(username)
    
    if not user or not check_user_password(user, password):
        return jsonify({'error': '�꾩씠�� �먮뒗 鍮꾨�踰덊샇 �ㅻ쪟'}), 401

    # JWT 諛쒓툒
    access_token = create_access_token(identity=str(user['_id']))
    return jsonify({'access_token': access_token}), 200


# 留덉씠�섏씠吏�(濡쒓렇�몃맂 �ъ슜�먮쭔 �묎렐 媛���)
@app.route('/mypage', methods=['GET'])
@jwt_required()
def mypage():
    try:
        current_user_id = ObjectId(get_jwt_identity())
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    user = mongo.db.users.find_one({"_id": current_user_id})
    
    if not user:
        return jsonify({"error": "�ъ슜�먮� 李얠쓣 �� �놁뒿�덈떎."}), 404

    cur = mongo.db.ratings.find({"user_id": current_user_id}).sort("updated_at", -1)
    ratings = []
    
    for r in cur:
        ratings.append({
            "_id": str(r["_id"]),
            "user_id": str(r["user_id"]),
            "travel_id": r.get("travel_id"),
            "score": r.get("score"),
            "feedback_tags": r.get("feedback_tags", []),
            "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            "updated_at": r.get("updated_at").isoformat() if r.get("updated_at") else None
        })



    return jsonify({
        "id": str(user['_id']),
        "username": user['username'],
        "email": user['email'],
        "message": f"{user['username']}�섏쓽 留덉씠�섏씠吏��낅땲��!",
        "ratings": ratings
    }), 200


# ============================================================================
# 誘쇱꽌�� �뚰듃 異붽��� 遺�遺�


# 留덉씠�섏씠吏��먯꽌 �쒓렇 �ㅻЦ議곗궗
@app.route('/mypage/tags', methods=['POST'])
@jwt_required()
def save_user_tags():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    body = request.get_json() or {}
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    # �뺢퇋��(怨듬갚/以묐났 �쒓굅, '#' �쒓굅, �뚮Ц��)
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


# 留덉씠�섏씠吏��먯꽌 �ㅻЦ�� �쒓렇 �뺤씤
@app.route('/mypage/tags', methods=['GET'])
@jwt_required()
def get_user_tags():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    doc = mongo.db.user_tags.find_one({"user_id": user_oid}, {"_id": 0, "tags": 1})
    return jsonify({"user_id": user_id, "tags": doc.get("tags", []) if doc else []}), 200


# 異붿쿇 諛쏆� �ы뻾吏� 遺곷쭏�ы븷 �� �몄텧
@app.route('/mypage/bookmarks/<int:travel_id>', methods=['POST'])
@jwt_required()
def toggle_bookmark(travel_id):
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    existing = mongo.db.bookmarks.find_one({"user_id": user_oid, "travel_id": travel_id})
    if existing:
        mongo.db.bookmarks.delete_one({"_id": existing["_id"]})
        return jsonify({"status": "unbookmarked", "travel_id": travel_id}), 200
    else:
        mongo.db.bookmarks.insert_one({
            "user_id": user_oid,
            "travel_id": travel_id,
            "tags": [],  # 珥덇린�� �쒓렇 �놁쓬
            "created_at": datetime.datetime.utcnow()
        })
        return jsonify({"status": "bookmarked", "travel_id": travel_id}), 201


# 遺곷쭏�� �� �ы뻾吏� 紐⑸줉 ��
@app.route('/mypage/bookmarks', methods=['GET'])
@jwt_required()
def list_my_bookmarks():
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    # bookmarks 議곗씤: travels�먯꽌 硫뷀� 媛��몄삤湲�
    bs = list(mongo.db.bookmarks.find({"user_id": user_oid}))
    
    travel_ids = [b["travel_id"] for b in bs]
    
    travel_docs = list(mongo.db.travels.find(
        {"travel_id": {"$in": travel_ids}},
        {"_id": 0, "travel_id": 1, "name": 1, "image_url": 1,"image_urls":1, "location": 1}
    ))
    tmap = {t["travel_id"]: t for t in travel_docs}

    items = []
    for b in bs:
        meta = tmap.get(b["travel_id"], {})
        loc = meta.get("location", {})
        image_url = meta.get("image_url")
        if not image_url and meta.get("image_urls"):
            urls = str(meta.get("image_urls")).split(",")
            image_url = urls[0].strip() if urls else None
        items.append({
            "travel_id": b["travel_id"],
            "name": meta.get("name"),
            "image_url": meta.get("image_url"),
            "location": {
                "lat": meta.get("lat"),
                "lng": meta.get("lng")
            },
            "my_tags": b.get("tags", []),
            "bookmarked_at": b.get("created_at").isoformat() if b.get("created_at") else None
        })
        
    return jsonify({"bookmarks": items, "count": len(items)}), 200


# 遺곷쭏�ы븳 �ы뻾吏��� �ъ슜�먭� �쒓렇 異붽�
@app.route('/mypage/bookmarks/<int:travel_id>/tags', methods=['POST'])
@jwt_required()
def save_bookmark_tags(travel_id):
    user_id = get_jwt_identity()
    try:
        user_oid = ObjectId(user_id)
    except:
        return jsonify({"error": "�섎せ�� �ъ슜�� ID"}), 400

    body = request.get_json() or {}
    tags = body.get("tags", [])
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    # �뺢퇋��
    norm, seen = [], set()
    for t in tags:
        s = str(t).strip().lstrip("#").lower()
        if s and s not in seen:
            seen.add(s)
            norm.append(s)

    # �� 遺곷쭏�ъ씤吏� �뺤씤
    bk = mongo.db.bookmarks.find_one({"user_id": user_oid, "travel_id": travel_id})
    if not bk:
        return jsonify({"error": "�대떦 �ы뻾吏��� 遺곷쭏�щ릺�� �덉� �딆뒿�덈떎."}), 404

    mongo.db.bookmarks.update_one(
        {"_id": bk["_id"]},
        {"$set": {"tags": norm}}
    )
    return jsonify({"travel_id": travel_id, "my_tags": norm}), 200




# ==================================================================================
# �ы뻾吏� 異붿쿇 肄붾뱶


# 寃쎈줈 �ㅼ젙
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # app.py 寃쎈줈
PROJECT_ROOT = os.path.join(BASE_DIR, "project_root1")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
PROCESSED_CSV = os.path.join(PROJECT_ROOT, "data", "processed", "gangwon_matching_results_sorted.csv")
EMBEDDING_NPY = os.path.join(PROJECT_ROOT, "place_embeddings_v2.npy")

# 珥덇린
recommender = GangwonPlaceRecommender(config_path=CONFIG_PATH)

# 紐⑤뜽/ �곗씠�� 濡쒕뵫
try:
    recommender.df = pd.read_csv(PROCESSED_CSV).reset_index(drop=True)
    recommender.place_embeddings = np.load(EMBEDDING_NPY)
except Exception as e:
    print("[WARN] 異붿쿇湲� 珥덇린 濡쒕뵫 �ㅽ뙣:", e)

try:
    print("[BOOT] df loaded rows:", len(recommender.df) if getattr(recommender, "df", None) is not None else 0)
    print("[BOOT] df has 'travel_id':", bool(getattr(recommender, "df", None) is not None and "travel_id" in list(recommender.df.columns)))
    if getattr(recommender, "place_embeddings", None) is not None:
        print("[BOOT] embeddings shape:", getattr(recommender.place_embeddings, "shape", None))
    else:
        print("[BOOT] embeddings NOT loaded")
except Exception as e:
    print("[BOOT] startup check failed:", e)


# 吏��� URL �먮룞�앹꽦(�대┃�섎㈃ 移댁뭅�ㅻ㏊ �ㅽ뵂)
def build_map_url(name, lat, lng):
    enc_name = quote(name or "", safe="")
    return f"https://map.kakao.com/link/map/{enc_name},{lat},{lng}"



@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        body = request.get_json(silent=True) or {}

        # 1) 濡쒓렇�� �좎� �뺤씤 (optional)
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
        except Exception:
            user_id = None

        # 2) �ㅻЦ �쒓렇(DB)
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

        # 3) �낅젰 �곗꽑�쒖쐞 寃곗젙 (A 諛⑹떇: �ㅻЦ�쒓렇 �곗꽑)
        # - free_text > tags > �ㅻЦ�쒓렇 > 紐낆떆�꾨뱶
        if isinstance(body.get("free_text"), str) and body["free_text"].strip():
            data_for_model = {"free_text": body["free_text"].strip()}
            mode = "free_text"

        elif isinstance(body.get("tags"), list) and body["tags"]:
            norm = [str(t).strip().lstrip("#").lower() for t in body["tags"] if str(t).strip()]
            data_for_model = {"tags": norm}
            mode = "tags"

        elif user_tags:
            data_for_model = {"tags": user_tags}
            mode = "survey"

        else:
            data_for_model = {}
            mode = "fallback"

        # 4) 異붿쿇 �섑뻾
        result = recommender.recommend_places(data_for_model, top_k=3)
        recs = result.get("recommendations", [])[:3]

        print("[DEBUG] recs raw:", recs)

        # 5) travel_id 議댁옱 �뺤씤
        recs = [r for r in recs if r.get("travel_id") is not None]
        if not recs:
            return jsonify({"error": "異붿쿇 寃곌낵�� �좏슚�� travel_id媛� �놁뒿�덈떎."}), 500

        print("[DEBUG] keys in first rec:", recs[0].keys() if recs else "NO RECS")

        # 6) �ы뻾吏� 硫뷀� 議곗씤
        travel_ids = [r["travel_id"] for r in recs]
        travel_docs = list(mongo.db.travels.find(
        {"travel_id": {"$in": travel_ids}},
        {"_id": 0, "travel_id": 1, "name": 1, "image_url": 1, "image_urls": 1, "location": 1}
            ))
        tmap = {d["travel_id"]: d for d in travel_docs}

        def build_map_url(name, lat, lng):
            from urllib.parse import quote
            enc = quote(name or "", safe="")
            return f"https://map.kakao.com/link/map/{enc},{lat},{lng}"

        # 7) �묐떟 R1 �뺥깭濡� 蹂���
        enriched = []
        for r in recs:
            meta = tmap.get(r["travel_id"])
            if not meta:
                continue
            
            loc = meta.get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")

            # �� image_url 泥섎━
            image_url = meta.get("image_url")
            if not image_url and meta.get("image_urls"):
                urls = str(meta.get("image_urls")).split(",")
                image_url = urls[0].strip() if urls else None

            enriched.append({
                "travel_id": r["travel_id"],
                "name": meta.get("name"),
                "image_url": meta.get("image_url"),  # �� DB 而щ읆紐� 諛섏쁺
                "location": {
                    "lat": lat,
                    "lng": lng
                },
                "map_url": build_map_url(meta.get("name"), loc.get("lat"), loc.get("lng")),
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
    


# �쒕쾭媛� �묐룞以묒씤 吏� �뺤씤�섍린 �꾪븿
@app.route('/health', methods=['GET'])
def health():
    # 紐⑤뜽�� �뺤긽�곸쑝濡� 濡쒕뱶�먮뒗吏��� �곹깭�� �ы븿
    # DB �곌껐 �곹깭�� 泥댄겕

    db_ok = False # 湲곕낯
    db_error = None # 湲곕낯
    
    try:
        mongo.cx.admin.command("ping")
        db_ok = True
    except Exception as e:
        db_error = str(e) # �먮윭硫붿떆吏� ��
        
    # 紐⑤뜽 �곌껐 泥댄겕
    places_loaded = len(recommender.df) if getattr(recommender, "df", None) is not None else 0
    embedding_ready = hasattr(recommender, "place_embeddings")

    # �꾩껜 �곌껐�곹깭 �먮떒
    overall_ok = db_ok and places_loaded > 0 and embedding_ready # �꾨� �곌껐�먯쓣 ��
    status_code = 200 if overall_ok else 503  # �꾨� �곌껐 -> 200, �섎굹�쇰룄 �곌껐 �덈맖 -> 503

    return jsonify({
        "status": "ok" if overall_ok else "degraded",
        "db_connected": db_ok,
        "db_error": db_error if not db_ok else None,
        "places_loaded": places_loaded,
        "embedding_ready": embedding_ready
    }), status_code


# 별점 등록 업데이트
@app.route('/rating', methods=['POST'])
@jwt_required()
def submit_rating():
    data = request.get_json() or {}

    # ✅ user_id는 더 이상 body에서 받지 않음
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

    # 기존 별점 업데이트 or 새로 추가
    print("===== RATING DEBUG =====")
    print("[DEBUG] user_id from JWT:", user_id, type(user_id))
    print("[DEBUG] user_oid:", user_oid)
    print("[DEBUG] travel_id_int:", travel_id_int, type(travel_id_int))

    before = mongo.db.ratings.find_one({"user_id": user_oid, "travel_id": travel_id_int})
    print("[DEBUG] 기존 rating 존재?:", before)

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

    print("[DEBUG] update result:", result.raw_result)
    after = mongo.db.ratings.find_one({"user_id": user_oid, "travel_id": travel_id_int})
    print("[DEBUG] 저장 결과:", after)
    print("===== END DEBUG =====")

    # 응답 메시지
    if result.upserted_id:
        message = "별점이 새로 등록되었습니다."
    elif result.modified_count > 0:
        message = "별점이 수정되었습니다."
    else:
        message = "기존 별점과 동일하여 변경되지 않았습니다."

    return jsonify({"message": message}), 201


# ------------------------------
# �쒕쾭 留곹겕 寃��� �� �섏삤�� 臾몄옣
@app.route('/')
def home():
    return '�쒕쾭 �� �묐룞 以묒엯�덈떎.'


if __name__ == "__main__":
    # �섍꼍蹂��� �ㅼ젙
    port = int(os.environ.get("PORT", 5000))
    # 紐⑤뱺 IP二쇱냼�먯꽌 �묎렐 媛���
    app.run(debug=False, host="0.0.0.0", port=port)
