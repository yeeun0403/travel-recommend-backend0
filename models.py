from werkzeug.security import generate_password_hash, check_password_hash

# 비번 설정, 체크 해시화 함수(보안)
    
    def set_password(self, password):
        return generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(hashed, password)
