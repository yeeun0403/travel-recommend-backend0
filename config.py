import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '3Ud9hD29Xd2eB3nF03qYn76V'

    # MySQL 연결 정보
    # MySQL에 설정해둔 사용자 계정 정보
    SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://유저명:비번@localhost:3306/데이터베이스 이름'

    SQLALCHEMY_TRACK_MODIFICATIONS = False
