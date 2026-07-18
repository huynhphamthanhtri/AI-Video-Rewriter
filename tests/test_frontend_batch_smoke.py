from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_auto_pipeline_routes_single_and_multi_paths():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "if (urls.length > 1)" in app
    assert "startBatchAutoPipeline" in app
    assert "startAutoPipeline" in app
    assert app.index("if (urls.length > 1)") < app.index("startAutoPipeline({ form_data: formPayload")


def test_frontend_api_uses_expected_batch_endpoints():
    api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "export async function startAutoPipeline" in api
    assert "${API_BASE}/gemini/auto-submit" in api
    assert "export async function startBatchAutoPipeline" in api
    assert "${API_BASE}/gemini/batch-auto-submit" in api
    assert "${API_BASE}/gemini/batch/${batchId}" in api
    assert "${API_BASE}/gemini/batch/${batchId}/cancel" in api


def test_frontend_batch_panel_and_cancel_are_wired():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    component = (ROOT / "frontend" / "src" / "components" / "BatchPipelineProgress.tsx").read_text(encoding="utf-8")

    assert "<BatchPipelineProgress progress={batchProgress} onCancel={handleCancelBatchPipeline}" in app
    assert "cancelBatch(batchId)" in app
    assert "Hủy batch" in component


def test_frontend_analysis_mode_selector_is_removed():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    types = (ROOT / "frontend" / "src" / "types.ts").read_text(encoding="utf-8")

    assert "GeminiAnalysisMode" not in types
    assert "geminiAnalysisMode" not in app
    assert "Chế độ Gemini" not in app
    assert "gemini_analysis_mode" not in app


def test_frontend_target_languages_are_limited_to_tts_supported_languages():
    options = (ROOT / "frontend" / "src" / "constants" / "options.ts").read_text(encoding="utf-8")

    for language in ["Tiếng Việt", "English", "German", "Japanese", "Spanish", "Korean"]:
        assert language in options
    for language in ["Chinese", "French", "Portuguese", "Hindi", "Thai", "Indonesian"]:
        assert language not in options


def test_frontend_language_change_syncs_tts_voice():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "languageVoiceDefaults" in app
    assert "syncVoiceForLanguage" in app
    assert "updateTargetLanguage(e.target.value)" in app
