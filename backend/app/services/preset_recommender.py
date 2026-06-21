from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

RECOMMENDATION_TIMEOUT = 5.0


@dataclass
class PresetRule:
    preset_name: str
    keywords: set[str]
    phrases: list[str] = field(default_factory=list)
    description: str = ""


PRESET_RULES: list[PresetRule] = [
    PresetRule(
        preset_name="Review Công Nghệ",
        keywords={"review", "unboxing", "technology", "cong-nghe", "smartphone", "laptop", "gadget", "tech", "danh-gia", "app", "software", "hardware", "digital", "device"},
        description="Technology reviews and unboxings",
    ),
    PresetRule(
        preset_name="TikTok Viral 60s",
        keywords={"viral", "trend", "shorts", "tiktok", "reels", "xu-huong", "meme", "challenge", "trending"},
        description="Short-form viral content",
    ),
    PresetRule(
        preset_name="YouTube Shorts Review",
        keywords={"shorts", "review", "quick", "short", "fast", "nhanh", "review-nhanh", "ngan", "summary", "sport", "highlight", "football", "bong-da", "nba", "soccer", "match", "tournament", "game", "athlete", "championship", "olympic", "the-thao"},
        phrases=["short review", "nhanh review", "review nhanh"],
        description="Short-form reviews and sports highlights",
    ),
    PresetRule(
        preset_name="Podcast Tóm Tắt",
        keywords={"podcast", "interview", "phong-van", "talk", "discussion", "conversation", "episode", "host"},
        description="Podcast summaries and interviews",
    ),
    PresetRule(
        preset_name="Documentary Mini",
        keywords={"documentary", "tai-lieu", "phong-su", "explore", "history", "lich-su", "kham-pha", "mini-doc"},
        description="Short documentaries",
    ),
    PresetRule(
        preset_name="Tin Tức Nhanh",
        keywords={"news", "breaking", "tin-tuc", "thoi-su", "current", "update", "report", "ban-tin", "headline"},
        description="Quick news updates",
    ),
    PresetRule(
        preset_name="Drama Kể Chuyện",
        keywords={"drama", "story", "cau-chuyen", "ke-chuyen", "tale", "plot", "twist", "tinh-tiet", "emotional", "cam-xuc"},
        description="Story-driven dramatic content",
    ),
    PresetRule(
        preset_name="Phân Tích Chuyên Gia",
        keywords={"analysis", "phan-tich", "expert", "chuyen-gia", "deep-dive", "insight", "chuyen-sau", "professional"},
        description="Expert analysis and deep dives",
    ),
    PresetRule(
        preset_name="Content Giáo Dục",
        keywords={"education", "hoc", "giao-duc", "course", "lesson", "kien-thuc", "tutorial", "how-to", "guide", "huong-dan", "learn", "study", "science"},
        description="Educational content",
    ),
    PresetRule(
        preset_name="Nhà Đầu Tư",
        keywords={"finance", "invest", "stock", "dau-tu", "chung-khoan", "bitcoin", "crypto", "market", "trading", "economic", "kinh-te", "tai-chinh"},
        description="Financial and investment analysis",
    ),
    PresetRule(
        preset_name="Marketing Case Study",
        keywords={"marketing", "business", "brand", "startup", "case-study", "kinh-doanh", "doanh-nghiep", "campaign", "strategy"},
        description="Marketing case studies and business analysis",
    ),
    PresetRule(
        preset_name="Reaction Hài Hước",
        keywords={"funny", "comedy", "hai-huoc", "mem", "meme", "humor", "joke", "troll", "hai", "laugh", "comic", "reaction"},
        description="Humorous reactions and comedy",
    ),
    PresetRule(
        preset_name="Tranh Luận/Góc Nhìn Trái Chiều",
        keywords={"debate", "argument", "phan-bien", "tranh-luan", "opinion", "opposing", "goc-nhin", "quan-diem", "controversy", "tranh-cai"},
        description="Debates and opposing viewpoints",
    ),
    PresetRule(
        preset_name="US COPS Documentary",
        keywords={"bodycam", "police", "cops", "crime", "true-crime", "hinh-su", "canh-sat", "arrest", "case-file", "toi-pham", "investigation", "dieu-tra", "court", "justice"},
        description="Police and true crime documentary content",
    ),

]


class TitleNormalizer:
    @staticmethod
    def strip_diacritics(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text)
        stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return unicodedata.normalize("NFC", stripped)

    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower().strip()
        text = TitleNormalizer.strip_diacritics(text)
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return [t for t in text.split() if 2 <= len(t) <= 20]


class PresetRecommender:
    def __init__(self):
        pass

    def _extract_title_from_url(self, url: str) -> str | None:
        """Use yt-dlp to extract title (flat, no download)."""
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "skip_download": True,
                "timeout": RECOMMENDATION_TIMEOUT,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("title")
        except Exception as e:
            logger.warning("yt-dlp title extraction failed for %s: %s", url, e)
            return None

    def recommend(self, video_title: str | None = None, youtube_url: str | None = None, max_results: int = 5) -> dict:
        # Step 1: Resolve title
        title = None
        title_source = "none"

        if video_title and video_title.strip():
            title = video_title.strip()
            title_source = "provided"
        elif youtube_url and youtube_url.strip():
            title = self._extract_title_from_url(youtube_url.strip())
            if title:
                title_source = "extracted"

        if not title:
            return {"title": None, "title_source": title_source, "recommendations": []}

        # Step 2: Normalize and tokenize
        normalized = TitleNormalizer.normalize(title)
        tokens = TitleNormalizer.tokenize(normalized)

        # Step 3: Score each preset rule
        scored: list[dict] = []
        for rule in PRESET_RULES:
            matched_keywords: set[str] = set()

            # Check single keywords
            for kw in rule.keywords:
                kw_normalized = TitleNormalizer.normalize(kw)
                kw_tokens = TitleNormalizer.tokenize(kw_normalized)
                if any(t in tokens for t in kw_tokens):
                    matched_keywords.add(kw)

            # Check phrases
            phrase_matches = 0
            for phrase in rule.phrases:
                phrase_normalized = TitleNormalizer.normalize(phrase)
                if phrase_normalized in normalized:
                    phrase_matches += 1

            if not matched_keywords and phrase_matches == 0:
                continue

            # Confidence computation
            keyword_count = len(matched_keywords)
            keyword_score = min(keyword_count * 0.15, 0.6)
            phrase_score = min(phrase_matches * 0.25, 0.5)

            # Exact preset name bonus
            preset_normalized = TitleNormalizer.normalize(rule.preset_name)
            exact_bonus = 0.30 if preset_normalized in normalized else 0.0

            confidence = min(keyword_score + phrase_score + exact_bonus, 1.0)
            confidence = round(confidence, 2)

            if confidence < 0.15:
                continue

            scored.append({
                "preset_name": rule.preset_name,
                "confidence": confidence,
                "confidence_label": self._confidence_label(confidence),
                "matched_keywords": sorted(matched_keywords),
            })

        # Step 4: Sort by confidence DESC
        scored.sort(key=lambda r: r["confidence"], reverse=True)

        return {
            "title": title,
            "title_source": title_source,
            "recommendations": scored[:max_results],
        }

    @staticmethod
    def _confidence_label(confidence: float) -> str:
        if confidence >= 0.70:
            return "strong"
        elif confidence >= 0.40:
            return "medium"
        elif confidence >= 0.15:
            return "weak"
        return "none"
