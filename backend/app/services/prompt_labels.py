from __future__ import annotations


LOCALIZATION_LEVEL_LABELS = {"none": "Không localize", "light": "Nhẹ", "medium": "Trung bình", "heavy": "Mạnh"}
ADAPTATION_MODE_LABELS = {"faithful": "Giữ sát bản gốc", "localized": "Bản địa hóa", "inspired": "Lấy cảm hứng"}
NARRATOR_PERSONA_LABELS = {
    "neutral_narrator": "Người kể trung lập",
    "funny_friend": "Người bạn hài hước",
    "drama_storyteller": "Người kể chuyện drama",
    "movie_reviewer": "Reviewer phim",
    "news_anchor": "Biên tập viên tin tức",
    "expert_analyst": "Chuyên gia phân tích",
    "detective": "Thám tử",
    "teacher": "Giáo viên",
    "podcast_host": "Host podcast",
    "tech_reviewer": "Reviewer công nghệ",
    "investor": "Nhà đầu tư",
}


def bool_label(value: bool) -> str:
    return "Có" if value else "Không"
