from scripts.live_batch_e2e import run_batch


def test_live_batch_e2e_requires_done_items_and_quality(monkeypatch, tmp_path):
    videos = []
    for index in range(2):
        path = tmp_path / f"video_{index}.mp4"
        path.write_bytes(b"video")
        videos.append(path)
    responses = iter([
        {"batch_id": "batch-1"},
        {
            "batch_id": "batch-1",
            "status": "done",
            "items": [
                {"index": index, "source_url": f"https://example.test/{index}", "status": "done", "result": {"final_video_path": str(videos[index])}}
                for index in range(2)
            ],
        },
    ])
    monkeypatch.setattr("scripts.live_batch_e2e._request_json", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("scripts.live_batch_e2e.inspect_video", lambda *args, **kwargs: {"passed": True})
    report = run_batch(
        "http://127.0.0.1:8007",
        [{"media_url": "https://example.test/0"}, {"media_url": "https://example.test/1"}],
        30,
    )
    assert report["passed"] is True
    assert [item["status"] for item in report["items"]] == ["done", "done"]
