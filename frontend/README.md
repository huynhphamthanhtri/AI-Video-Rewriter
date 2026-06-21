# AI Video Rewriter Frontend

Dashboard React + Vite + TypeScript cho hệ thống AI Video Rewriter & Video Rebuilder.

## Chạy dev

```bash
npm install
npm run dev
```

## Mock mode

Nếu backend chưa chạy, bật mock mode:

```bash
set VITE_USE_MOCK_API=true
npm run dev
```

Mock mode hỗ trợ preset mẫu, generate prompt mẫu, validate JSON mẫu và render job giả lập progress.

## Backend API

Frontend gọi backend tại `http://127.0.0.1:8000/api` và ưu tiên async render job:

- `POST /api/render-jobs`
- `GET /api/render-jobs/{job_id}`

Không dùng `/api/render` làm flow chính.

## Schema

Frontend dùng schema EDL chính thức: `metadata`, `rewrite_script`, `srt[]`, `video_segments[]`. Không dùng `clips[]` hoặc `timeline[]`.