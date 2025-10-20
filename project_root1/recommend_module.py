import os
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class GangwonPlaceRecommender:
    def __init__(self, config_path=None):
        self.df = None
        self.place_embeddings = None
        self.embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

    # 사용자 입력 파싱 (description + tags 모두 대응)
    def _parse_user_input(self, user_input: Dict) -> Dict:
        parsed = {
            "description": None,
            "tags": []
        }

        if "description" in user_input:
            parsed["description"] = user_input["description"]

        if "tags" in user_input and isinstance(user_input["tags"], list):
            parsed["tags"] = user_input["tags"]

        return parsed

    # SBERT 유사도 점수
    def _calculate_similarity_scores(self, query_text: str) -> np.ndarray:
        if not query_text:
            return np.zeros(len(self.df))

        query_embedding = self.embedding_model.encode([query_text])
        similarity_scores = cosine_similarity(query_embedding, self.place_embeddings)[0]
        return similarity_scores

    # 태그 기반 점수
    def _calculate_tag_scores(self, tags: List[str]) -> np.ndarray:
        tag_scores = np.zeros(len(self.df))
        tag_set = set(tags)

        for idx, row in self.df.iterrows():
            row_tags = set(row.get("tag_list", []))
            if len(tag_set) > 0:
                match = len(tag_set & row_tags)
                tag_scores[idx] = match / len(tag_set)

        return tag_scores

    # 추천 실행
    def recommend_places(self, user_input: Dict, top_k: int = 3) -> Dict:
        parsed = self._parse_user_input(user_input)

        description = parsed.get("description")
        tags = parsed.get("tags", [])

        # similarity
        similarity_scores = self._calculate_similarity_scores(description)

        # tag score
        tag_scores = self._calculate_tag_scores(tags)

        # hybrid (A 전략: 0.6 / 0.4)
        hybrid_scores = (0.6 * similarity_scores) + (0.4 * tag_scores)

        # top_k index
        top_indices = np.argsort(hybrid_scores)[::-1][:top_k]

        recommendations = []
        for idx in top_indices:
            row = self.df.iloc[idx]
            recommendations.append({
                "travel_id": int(row["travel_id"]),
                "hybrid_score": float(hybrid_scores[idx]),
                "similarity_score": float(similarity_scores[idx]),
                "tag_score": float(tag_scores[idx])
            })

        return {
            "parsed_input": parsed,
            "recommendations": recommendations,
            "total_places": len(self.df)
        }
