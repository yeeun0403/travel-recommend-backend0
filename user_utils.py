from extensions import mongo
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import datetime


# 사용자 조회/중복 체크

def get_user_by_username(username):
    return mongo.db.users.find_one({"username": username})

def username_exists(username):
    return mongo.db.users.find_one({"username": username}) is not None

def email_exists(email):
    return mongo.db.users.find_one({"email": username}) is not None


# 사용자 생성

def create_user(username, email, password, name):
    hashed_pw = generate_password_hash(password)
    user = {
        "username": username,
        "email": email,
        "password": hashed_pw,
        "name" : name
    }
    result = mongo.db.users.insert_one(user)
    return str(result.inserted_id)


# 비밀번호 체크

def check_user_password(user, password):
    return check_password_hash(user['password'], password)


# travel_id
