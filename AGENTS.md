# AGENTS.md — Auto Review Project

## Role Constraints

- **RC branch: feature freeze.** No new features, no architecture refactors, no schema changes, no non-defect code cleanup.
- Fix only bugs that block validation completely.
- Do NOT introduce UI fields, change schemas, or add new dependencies.

## Standard Commands

### Run uvicorn (không block bash tool)
Dùng `-WindowStyle Hidden` để chạy nền, **không dùng** `-NoNewWindow` vì output log vô hạn sẽ block bash tool đến timeout:

```powershell
# Kill processes cũ trên port
Get-NetTCPConnection -LocalPort 8007 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  Stop-Process -Force -ErrorAction SilentlyContinue

# Kill ALL Python processes nếu port vẫn bận (stale .pyc issue)
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Clean pycache
Get-ChildItem -Path "E:\AUTO_REVIEW\backend" -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force

# Start uvicorn hidden
Start-Process -WindowStyle Hidden -FilePath "E:\AUTO_REVIEW\.venv312\Scripts\python.exe" `
  -ArgumentList "-m uvicorn app.main:app --port 8007 --host 127.0.0.1" `
  -WorkingDirectory "E:\AUTO_REVIEW\backend"
Start-Sleep -Seconds 6

# Verify port listen
if (-not (Get-NetTCPConnection -LocalPort 8007 -ErrorAction SilentlyContinue)) {
  throw "uvicorn chua listen port 8007"
}

# Verify API
Invoke-RestMethod -Uri "http://127.0.0.1:8007/docs" -Method Get -ErrorAction Stop
```

### Run tests
```powershell
python -m pytest tests/ -q
```

### Build frontend
```powershell
Set-Location "E:\AUTO_REVIEW\frontend"; npm run build
```
Không cần copy dist — backend serve trực tiếp từ `frontend/dist/`.

### Package Windows installer
```powershell
# Stage package (skip tests + frontend if already validated)
.\packaging\package_windows.ps1 -SkipTests -SkipFrontendBuild -Version "1.0.0-rc1"

# Compile Inno Setup installer
ISCC.exe "E:\AUTO_REVIEW\packaging\inno\MrTris_AUTO.iss"
```

### Verify all API routes registered
```powershell
# Start backend, then:
python -c "import json, urllib.request; req=urllib.request.Request('http://127.0.0.1:8007/openapi.json'); spec=json.loads(urllib.request.urlopen(req).read()); print(f'{len(spec[\"paths\"])} routes')"
```

## API Route Prefix Constraint

Router được mount ở `/api` trong `main.py`:
```python
app.include_router(router, prefix="/api")
```

Route decorators trong `routes.py` **không được thêm `/api`** vào path, vì sẽ tạo double prefix `/api/api/...` khiến route không register.

**Đúng:** `@router.post("/prompt/recommend")`
**Sai:** `@router.post("/api/prompt/recommend")`

## Versioning

Single source of truth: **`backend/app/core/versions.py`**

```python
CURRENT_PRESET_SCHEMA_VERSION: int = 1
CURRENT_PROMPT_TEMPLATE_VERSION: int = 1
CURRENT_JSON_OUTPUT_SCHEMA_VERSION: int = 1
```

## Privacy Constraints (Prompt Telemetry)

- **Không lưu `prompt_text`** vào database.
- Telemetry chỉ lưu `prompt_chars` (số ký tự) + `prompt_hash` (SHA-256 hex digest).
- `_sanitize_form_data()` strip các field nhạy cảm: `youtube_url`, `youtube_urls`, `ytdlp_cookies_file`.
- Telemetry failure không break prompt generation (best-effort, catch exception, log warning).

## Files & Paths

### Backend core
- `backend/app/main.py` — FastAPI app factory
- `backend/app/api/routes.py` — All API routes
- `backend/app/core/config.py` — Settings
- `backend/app/core/database.py` — SQLAlchemy engine + migrations
- `backend/app/core/versions.py` — Version constants
- `backend/app/schemas/` — Pydantic models (prompt, render, preset)
- `backend/app/models/` — SQLAlchemy ORM models (preset, prompt_run)
- `backend/app/services/` — Business logic services

### Frontend
- `frontend/src/App.tsx` — Main app component
- `frontend/src/api.ts` — API client functions
- `frontend/src/types.ts` — TypeScript type definitions
- `frontend/src/components/` — UI components
- `frontend/dist/` — Built static files (served by backend)

### Packaging
- `packaging/package_windows.ps1` — Windows packaging script
- `packaging/inno/MrTris_AUTO.iss` — Inno Setup installer script
- `packaging/launcher/mrtris_auto_launcher.py` — App launcher (port fallback 8000-8004, DB init, browser auto-open)

## Xử lý lỗi 422 "Field required" từ backend
1. Clean .pyc cache
2. Kill ALL Python processes + restart uvicorn
3. Kiểm tra schema trực tiếp bằng Python
4. Gọi API test

## Troubleshooting: Missing route (404/405 on known endpoints)

Nếu một API route (ví dụ `/api/subtitle/preview-style`) không hoạt động dù code đã định nghĩa:

1. Kill ALL Python processes:
   ```powershell
   Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
   ```
2. Xoá toàn bộ `__pycache__`:
   ```powershell
   Get-ChildItem -Path "E:\AUTO_REVIEW\backend" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
   ```
3. Restart uvicorn + verify route count:
   ```powershell
   # Start backend
   Start-Process -WindowStyle Hidden -FilePath "python.exe" `
     -ArgumentList "-m uvicorn app.main:app --port 8007 --host 127.0.0.1" `
     -WorkingDirectory "E:\AUTO_REVIEW\backend"
   Start-Sleep -Seconds 6

   # Verify route count (expect 45)
   python -c "import json, urllib.request; req=urllib.request.Request('http://127.0.0.1:8007/openapi.json'); spec=json.loads(urllib.request.urlopen(req).read()); print(f'{len(spec[\"paths\"])} routes')"
   ```
4. Nếu route count thấp hơn mong đợi, kiểm tra logs ở `backend/logs/error.log`.

Nguyên nhân thường gặp: Python load bytecode `.pyc` cũ, khiến module không import được các route mới.

## Kiểm tra schema đã load đúng chưa
```powershell
python.exe -c "
import sys; sys.path.insert(0, 'E:\\AUTO_REVIEW\\backend')
from app.schemas.render import BlurRegion, BlurKeyframe
r = BlurRegion(start=0, end=10, keyframes=[BlurKeyframe(time=0, x=0.1, y=0.1, width=0.3, height=0.3, strength=15)], interpolate=False)
print('Fields:', list(r.model_dump().keys()))
"
```
Kết quả mong đợi: `['start', 'end', 'keyframes', 'interpolate']`

## RC-1 Known Warnings
1. `PresetRecommendationCard` có prop `videoTitle` chưa được wire trong `App.tsx` — component fallback sang `youtubeUrl` OK.
2. `README_USER.txt` trong staged package có thể còn version `beta` nếu staging không rebuild với version mới.

## Release / Updater Skill

For publishing new updater releases, follow `docs/RELEASE_SKILL.md`.

Do not update `manifest.json` before the matching release zip is uploaded and SHA256 verified.
