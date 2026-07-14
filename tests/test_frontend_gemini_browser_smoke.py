from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_open_gemini_browser_api_throws_on_failure():
    api = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "export async function openGeminiBrowser" in api
    assert "body: JSON.stringify({ user_data_dir: userDataDir ?? null })" in api
    assert "if (!res.ok) throw new Error(await parseError(res, 'Không thể mở trình duyệt Gemini.'))" in api


def test_open_gemini_browser_ui_shows_error_toast_on_api_failure():
    app = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "const res = await openGeminiBrowser()" in app
    assert "toast.success(res.message)" in app
    assert "toast.error(e instanceof Error ? e.message : 'Không mở được trình duyệt')" in app
