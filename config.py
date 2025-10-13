import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '3Ud9hD29Xd2eB3nF03qYn76V'

    # MongoDB 연결 정보
    # MongoDB에 설정해둔 사용자 계정 정보
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongoDB 서버주소:기본포트/사용할 데이터베이스 명'
