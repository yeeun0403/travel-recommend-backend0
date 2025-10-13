import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '3Ud9hD29Xd2eB3nF03qYn76V'

    # MongoDB 연결 정보
    # MongoDB에 설정해둔 사용자 계정 정보
    # 'mongodb://mongoDB서버주소:기본포트/사용할데이터베이스명' -> 필요
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/mydatabase') # 임시값
