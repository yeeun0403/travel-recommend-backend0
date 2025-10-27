import os
import pandas as pd
import numpy as np
import yaml
from typing import Dict, List, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class GangwonPlaceRecommender:
    def __init__(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # 외부(app.py)에서 셋업됨
        self.df: pd.DataFrame = None
        self.place_embeddings: np.ndarray = None

        # SBERT (쿼리 임베딩용)
        model_name = self.config.get("model", {}).get(
            "sbert_model", "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
        )
        self.embedder = SentenceTransformer(model_name)

        # 가중치
        rec_conf = self.config.get("recommendation", {})
        self.sim_w = float(rec_conf.get("similarity_weight", 0.6))
        self.tag_w = float(rec_conf.get("tag_weight", 0.4))

        # 간단 태그 매핑(키워드 → 카테고리)
        self.tag_mapping = {
            "nature": ["산", "바다", "호수", "계곡", "자연", "도시"],
            "vibe": ["감성", "활력", "휴식", "산책", "모험", "힐링", "사진명소", "액티비티", "조용한"],
            "target": ["연인", "가족", "친구", "혼자"]
        }

    # ---------- 입력 파싱/정규화 ----------
    def _normalize_tags(self, items: List[str]) -> List[str]:
        out, seen = [], set()
        for x in (items or []):
            s = str(x).strip().lstrip("#").lower()
            if not s:
                continue
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def _to_cased_tags(self, items: List[str]) -> List[str]:
        """모델 내부는 소문자로 처리, DF의 리스트 항목도 소문자로 맞춘 상태라는 가정 권장."""
        return self._normalize_tags(items)

    def parse_user_input(self, user_input: Dict) -> Dict:
        """
        지원 입력:
        - {"free_text": "..."}  → 자유문장
        - {"tags": [...] }      → 범용 해시태그(자연/분위기/대상에 동일반영)
        - {"season": "...", "nature":[...], "vibe":[...], "target":[...]} → 명시
        """
        if not user_input:
            return {"free_text": None, "season": None, "nature": [], "vibe": [], "target": []}

        # free_text 최우선
        if isinstance(user_input.get("free_text"), str) and user_input["free_text"].strip():
            return {
                "free_text": user_input["free_text"].strip(),
                "season": None,
                "nature": [],
                "vibe": [],
                "target": []
            }

        # generic tags → nature/vibe/target 모두에 반영
        if isinstance(user_input.get("tags"), list) and user_input["tags"]:
            norm = self._to_cased_tags(user_input["tags"])
            return {"free_text": None, "season": None, "nature": norm, "vibe": norm, "target": norm}

        # 명시적 필드
        season = user_input.get("season")
        nature = self._to_cased_tags(user_input.get("nature", []))
        vibe = self._to_cased_tags(user_input.get("vibe", []))
        target = self._to_cased_tags(user_input.get("target", []))
        return {"free_text": None, "season": season, "nature": nature, "vibe": vibe, "target": target}

    # ---------- 점수 계산 ----------
    def _calc_similarity(self, query_text: str) -> np.ndarray:
        """SBERT 768D 코사인 유사도 (쿼리 1 x 768 vs 코퍼스 N x 768)"""
        if self.place_embeddings is None or self.df is None or len(self.df) == 0:
            raise RuntimeError("Recommender is not initialized with df/embeddings.")

        qv = self.embedder.encode([query_text], convert_to_numpy=True)  # (1,768)
        sim = cosine_similarity(qv, self.place_embeddings)[0]           # (N,)
        return sim

    def _calc_tag_score_row(self, parsed: Dict, row) -> float:
        """
        간단 가중치 방식:
        - season match: +0.3
        - nature Jaccard: *0.25
        - vibe   Jaccard: *0.25
        - target overlap ratio: *0.2
        DF의 nature_list / vibe_list / target_list 는 소문자 리스트라고 가정 권장.
        """
        score = 0.0

        # season
        if parsed.get("season") and isinstance(row.get("season"), str):
            # season은 문자열 비교(데이터에 '봄','여름' 같은 값이 있다고 가정)
            if str(row["season"]).strip() == parsed["season"]:
                score += 0.3

        # list helper (소문자 기준 매칭)
        def to_set(x):
            if isinstance(x, list):
                return set([str(i).strip().lower() for i in x if str(i).strip()])
            return set()

        # nature
        if parsed["nature"]:
            u = set(parsed["nature"])
            p = to_set(row.get("nature_list"))
            if u and p:
                inter = len(u & p)
                union = len(u | p) or 1
                jacc = inter / union
                score += 0.25 * jacc

        # vibe
        if parsed["vibe"]:
            u = set(parsed["vibe"])
            p = to_set(row.get("vibe_list"))
            if u and p:
                inter = len(u & p)
                union = len(u | p) or 1
                jacc = inter / union
                score += 0.25 * jacc

        # target
        if parsed["target"]:
            u = set(parsed["target"])
            p = to_set(row.get("target_list"))
            if u and p:
                inter = len(u & p)
                score += 0.2 * (inter / max(len(u), 1))

        return score

    def _calc_hybrid(self, parsed: Dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        # similarity
        if parsed["free_text"]:
            query_text = parsed["free_text"]
        else:
            # 태그 기반일 때 쿼리 문장 생성 (간단 조합)
            parts = []
            if parsed.get("season"):
                parts.append(parsed["season"])
            for k in ("target", "nature", "vibe"):
                if parsed[k]:
                    parts.append(", ".join(parsed[k]))
            query_text = " ".join(parts) if parts else "여행지 추천"

        sim = self._calc_similarity(query_text)

        # tag scores (0~1로 정규화)
        tag_scores = np.zeros(len(self.df), dtype=float)
        for i, (_, row) in enumerate(self.df.iterrows()):
            tag_scores[i] = self._calc_tag_score_row(parsed, row)
        if tag_scores.max() > 0:
            tag_scores = tag_scores / tag_scores.max()

        hybrid = self.sim_w * sim + self.tag_w * tag_scores
        return hybrid, sim, tag_scores

    # ---------- 최종 추천 ----------
    def recommend_places(self, user_input: Dict, top_k: int = 3) -> Dict:
        parsed = self.parse_user_input(user_input)
        hybrid, sim, tag = self._calc_hybrid(parsed)

        idxs = np.argsort(hybrid)[::-1][:top_k]
        recs = []
        for i in idxs:
            row = self.df.iloc[i]
            # travel_id 꼭 포함!
            recs.append({
                "travel_id": int(row["travel_id"]),
                "name": row.get("name"),
                "season": row.get("season"),
                "nature": row.get("nature_list", []),
                "vibe": row.get("vibe_list", []),
                "target": row.get("target_list", []),
                "description": row.get("short_description"),
                "hybrid_score": float(hybrid[i]),
                "similarity_score": float(sim[i]),
                "tag_score": float(tag[i]),
            })

        return {
            "parsed_input": parsed,
            "recommendations": recs,
            "total_places": len(self.df),
        }
