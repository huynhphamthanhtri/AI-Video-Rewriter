from scripts.video_quality_gate import parse_silences


def test_parse_silences_handles_internal_and_trailing_ranges():
    log = """
    [silencedetect] silence_start: 1.25
    [silencedetect] silence_end: 2.75 | silence_duration: 1.5
    [silencedetect] silence_start: 8.0
    """
    assert parse_silences(log, 10.0) == [
        {"start": 1.25, "end": 2.75, "duration": 1.5},
        {"start": 8.0, "end": 10.0, "duration": 2.0},
    ]


def test_parse_silences_recovers_missing_start_from_duration():
    log = "[silencedetect] silence_end: 5.0 | silence_duration: 1.25"
    assert parse_silences(log, 8.0) == [{"start": 3.75, "end": 5.0, "duration": 1.25}]
