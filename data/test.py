from flask import Flask, request, jsonify
import joblib

app = Flask(__name__)

# 모델 로딩
try:
    vectorizer = joblib.load('C:/flask_project/models/tfidf_vectorizer.pkl')
    season_model = joblib.load('C:/flask_project/models/season_model.pkl')
    nature_model = joblib.load('C:/flask_project/models/nature_model.pkl')
    vibe_model = joblib.load('C:/flask_project/models/vibe_model.pkl')
    target_model = joblib.load('C:/flask_project/models/target_model.pkl')

    mlb_season = joblib.load('C:/flask_project/models/season_encoder.pkl')
    mlb_nature = joblib.load('C:/flask_project/models/nature_encoder.pkl')
    mlb_vibe = joblib.load('C:/flask_project/models/vibe_encoder.pkl')
    mlb_target = joblib.load('C:/flask_project/models/target_encoder.pkl')
    print("✅ 모델 로딩 성공")
except Exception as e:
    print(f"❌ 모델 로딩 에러: {e}")


@app.route('/')
def home():
    return "flask operating"

@app.route('/predict', methods=['POST'])
def predict():
    try:
        data = request.get_json()
        print("받은 데이터: ", data)
        
        if not data or 'text' not in data:
            return jsonify({"error": "No 'text' field in JSON"}), 400

        input_text = data['text']

        # 벡터화
        X = vectorizer.transform([input_text])
        print("입력 텍스트: ", input_text)
        print("벡터화 완료")

        # 예측
        season_label_encoded = season_model.predict(X)[0]
        season = mlb_season.inverse_transform([season_label_encoded])[0]

        nature_label_encoded = nature_model.predict(X)[0]
        nature = mlb_nature.inverse_transform([nature_label_encoded])[0]

        vibe_label_encoded = vibe_model.predict(X)
        vibe = mlb_vibe.inverse_transform([vibe_label_encoded])[0]

        target_label_encoded = target_model.predict(X)
        target = mlb_target.inverse_transform([target_label_encoded])[0]
        print("예측 완료")

        return jsonify({
            'season': season,
            'nature': nature,
            'vibe': vibe,
            'target': target
        })

    except Exception as e:
        print(f"예측 중 오류 발생: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
