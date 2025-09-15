from models import User
from flask_sqlalchemy import SQLAlchemy

# 초기화
db = SQLAlchemy()

# 로그인, 사용자 정보 조회
def get_user_by_username(username):
    return User.query.filter_by(username=username).first()

#중복체크
def username_exists(username):
    return User.query.filter_by(username=username).first() is not None

def email_exists(email):
    return User.query.filter_by(email=email).first() is not None

def user_exists(username=None, email=None):
    query = User.query
    if username:
        query = query.filter_by(username=username)
    if email:
        query = query.filter_by(email=email)
    return query.first() is not None

def create_user(username, email, password):
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    return new_user
