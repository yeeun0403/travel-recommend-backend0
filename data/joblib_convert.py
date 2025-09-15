import os
import joblib
from flask import Flask, request, jsonify

app = Flask(__name__)

# 모델 불러오기
model_dir = 'C:/flask_project/models'
season_model = joblib.load(os.path.join(model_dir, 'season_model.pkl'))
nature_model = joblib.load(os.path.join(model_dir, 'nature_model.pkl'))
vibe_model = joblib.load(os.path.join(model_dir, 'vibe_model.pkl'))
target_model = joblib.load(os.path.join(model_dir, 'target_model.pkl'))
vectorizer = joblib.load(os.path.join(model_dir, 'tfidf_vectorizer.pkl'))
