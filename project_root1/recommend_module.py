import os
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer


class TravelRecommender:
    def __init__(self, base_dir: str = None):
        import torch

        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.BASE_DIR = base_dir
        self.DATA_PATH = os.path.join(
            self.BASE_DIR, "project_root", "data", "processed", "gangwon_places_100_processed.csv"
        )

        # 1 CSV 로드
        self.df = pd.read_csv(self.DATA_PATH, encoding="utf-8")

        # 2 문자열 형태의 리스트 컬럼 처리
        for col in ["nature_list", "vibe_list", "target_list"]:
            if col in self.df.columns and self.df[col].dtype == object:
                self.df[col] = self.df[col].apply(self._safe_eval_list)

        # 3 SBERT 모델 로드
        model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        self.embedding_generator = SentenceTransformer(model_name)

        # 4 여행지 설명 임베딩 미리 계산
        print("⚙️ 임베딩 생성 중... (처음 실행 시 약간 시간 걸릴 수 있음)")
        self.place_embeddings = self.embedding_generator.encode(
            self.df["short_description"].fillna(""), show_progress_bar=True
        )

        self.place_names = self.df["name"].tolist()
        print(f"✅ 임베딩 완료 — 총 {len(self.place_embeddings)}개 장소 준비됨")

    # 문자열을 안전하게 리스트로 변환
    def _safe_eval_list(self, x):
        import ast
        if isinstance(x, str):
            try:
                return ast.literal_eval(x)
            except:
                return [x]
        elif isinstance(x, list):
            return x
        return []

    # 사용자 입력 파싱
    def parse_user_input(self, user_input: Dict) -> Dict:
        parsed = {"season": None, "nature": [], "vibe": [], "target": []}

        # 자유 문장 입력
        if "free_text" in user_input:
            text = user_input["free_text"].lower()
            # (태그 자동추출 기능은 단순화)
        else:
            if "season" in user_input:
                parsed["season"] = user_input["season"]
            for category in ["nature", "vibe", "target"]:
                if category in user_input:
                    value = user_input[category]
                    parsed[category] = value if isinstance(value, list) else [value]

        return parsed

    # 하이브리드 점수 계산
    def calculate_hybrid_score(
        self, user_input: Dict, similarity_weight: float = 0.6, tag_weight: float = 0.4
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        parsed_input = self.parse_user_input(user_input)

        # 입력 문장 생성
        if "free_text" in user_input:
            query_text = user_input["free_text"]
        else:
            query_parts = []
            if parsed_input["season"]:
                query_parts.append(f"{parsed_input['season']}에")
            if parsed_input["target"]:
                query_parts.append(f"{', '.join(parsed_input['target'])}와")
            if parsed_input["nature"]:
                query_parts.append(f"{', '.join(parsed_input['nature'])}에서")
            if parsed_input["vibe"]:
                query_parts.append(f"{', '.join(parsed_input['vibe'])} 여행")
            query_text = " ".join(query_parts)

        # 쿼리 임베딩 계산
        query_embedding = self.embedding_generator.encode([query_text])
        similarity_scores = cosine_similarity(query_embedding, self.place_embeddings)[0]

        # 태그 점수 계산
        tag_scores = np.zeros(len(self.df))
        for idx, row in self.df.iterrows():
            score, total_weight = 0, 0
            if parsed_input["season"] and row["season"] == parsed_input["season"]:
                score += 0.3
            total_weight += 0.3
            if parsed_input["nature"]:
                n_match = len(set(parsed_input["nature"]) & set(row["nature_list"]))
                if n_match > 0:
                    score += 0.25 * (n_match / len(parsed_input["nature"]))
            total_weight += 0.25
            if parsed_input["vibe"]:
                v_match = len(set(parsed_input["vibe"]) & set(row["vibe_list"]))
                if v_match > 0:
                    score += 0.25 * (v_match / len(parsed_input["vibe"]))
            total_weight += 0.25
            if parsed_input["target"]:
                t_match = len(set(parsed_input["target"]) & set(row["target_list"]))
                if t_match > 0:
                    score += 0.2 * (t_match / len(parsed_input["target"]))
            total_weight += 0.2
            tag_scores[idx] = score / total_weight if total_weight > 0 else 0

        hybrid_scores = (similarity_weight * similarity_scores) + (tag_weight * tag_scores)
        return hybrid_scores, similarity_scores, tag_scores

    # 메인 추천 함수
    def recommend_places(self, user_input: Dict, top_k: int = 10) -> Dict:
        hybrid_scores, similarity_scores, tag_scores = self.calculate_hybrid_score(user_input)
        top_indices = np.argsort(hybrid_scores)[::-1][:top_k]

        recommendations = []
        for idx in top_indices:
            place_info = {
                "name": self.df.iloc[idx]["name"],
                "description": self.df.iloc[idx].get("short_description"),
                "season": self.df.iloc[idx].get("season"),
                "nature": self.df.iloc[idx].get("nature_list"),
                "vibe": self.df.iloc[idx].get("vibe_list"),
                "target": self.df.iloc[idx].get("target_list"),
                "hybrid_score": float(hybrid_scores[idx]),
                "similarity_score": float(similarity_scores[idx]),
                "tag_score": float(tag_scores[idx]),
            }
            recommendations.append(place_info)

        parsed_input = self.parse_user_input(user_input)
        return {
            "user_input": user_input,
            "parsed_input": parsed_input,
            "recommendations": recommendations,
            "total_places": len(self.df),
        }
