# DB 정의
# db.Model -> SQLAlchemy 베이스 모델 클래스

class User(db.Model):
    __tablename__ = ‘users' # users란 이름의 DB테이블 필요

    # DB에 전달해야하는 테이블 구조(컬럼명, 자료형, 제약 조건)
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 중복불가, 빈값 허용 X
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # 비번 설정, 체크 해시화 함수(보안)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # 비밀번호 제외하고 JSON 응답 전송
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email
        }
