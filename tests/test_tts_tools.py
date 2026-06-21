from app.services.tts_tools import TtsVoiceoverService, normalize_text_for_vietnamese_tts


class TestNormalizeText:
    def test_west_numbers_to_viet(self):
        result = normalize_text_for_vietnamese_tts("1,234.56 dollars")
        assert "1.234,56" in result or "1.234" in result

    def test_dollar_sign(self):
        result = normalize_text_for_vietnamese_tts("It costs $80")
        assert "đô la" in result

    def test_km_conversion(self):
        result = normalize_text_for_vietnamese_tts("He ran 5km")
        assert "ki-lô-mét" in result

    def test_percent(self):
        result = normalize_text_for_vietnamese_tts("Over 90% success")
        assert "phần trăm" in result

    def test_ceo(self):
        result = normalize_text_for_vietnamese_tts("The CEO spoke")
        assert "si-ai-âu" in result.lower()

    def test_ok(self):
        result = normalize_text_for_vietnamese_tts("It is OK")
        assert "âu-kây" in result.lower()

    def test_usa(self):
        result = normalize_text_for_vietnamese_tts("From USA")
        assert "u ét a" in result.lower()

    def test_normal_text_unchanged(self):
        text = "Xin chào, đây là văn bản tiếng Việt bình thường"
        assert normalize_text_for_vietnamese_tts(text) == text


class TestSplitLongCue:
    def test_short_text_no_split(self):
        service = TtsVoiceoverService()
        text = "Hello world"
        parts = service._split_long_cue(text, max_chars=200)
        assert parts == [text]

    def test_long_text_split_by_sentence(self):
        service = TtsVoiceoverService()
        text = "First sentence. Second sentence. Third sentence."
        parts = service._split_long_cue(text, max_chars=20)
        assert len(parts) >= 2
