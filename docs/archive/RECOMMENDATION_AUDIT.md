# Recommendation Card — Wiring Audit

**Date:** 2026-06-08  
**Component:** `PresetRecommendationCard` (`frontend/src/components/PresetRecommendationCard.tsx`)  
**Consumer:** `App.tsx` (line 683)

---

## Props Interface

```typescript
{
  videoTitle?: string;     // Optional — currently unused
  youtubeUrl?: string;     // Optional — wired in App.tsx
  onApplyPreset: (presetName: string) => void;  // Wired
}
```

## Current Wiring in `App.tsx`

```tsx
<PresetRecommendationCard youtubeUrl={form.youtube_url} onApplyPreset={applyPreset} />
```

**Only `youtubeUrl` is passed.** `videoTitle` is **not passed**.

## Internal Behavior

Inside `PresetRecommendationCard`, the effect checks both props:

```typescript
const hasTitle = videoTitle?.trim();
const hasUrl = youtubeUrl?.trim();
if (!hasTitle && !hasUrl) { setData(null); return; }
```

Since `videoTitle` is always `undefined`, the card operates exclusively on `youtubeUrl`. This causes `fetchPresetRecommendations` to be called with `youtube_url` only.

The API endpoint `POST /api/prompt/recommend` handles this gracefully — it falls back to fetching the video title from YouTube's metadata using `youtube_url` when `video_title` is not provided.

## Impact

| Aspect | Status |
|---|---|
| Card renders correctly? | ✅ Yes (via `youtubeUrl` fallback) |
| `videoTitle` provides extra signal? | ✅ Would improve recommendation accuracy when available |
| Any crash or warning? | ❌ No — optional prop, component handles undefined |
| New state needed in `App.tsx`? | ✅ Would need a `videoTitle` state extracted from form |
| Scope boundary | 🚫 Out of scope for UX-1.5 |

## Recommendation

The `videoTitle` prop is **unwired but benign**. The card works correctly using only `youtubeUrl`. Wiring `videoTitle` would require either:

1. A new input field for manual title entry (new UI — out of scope), or
2. Extracting the title from the YouTube URL via a server call before showing the card (new API interaction — out of scope), or
3. Deriving it from `renderOptions.title_text` (only available in TitleTool, not in workflow tab — fragile).

**Decision:** No code changes. `videoTitle` prop remains available for future use. No TODO added since the prop is already marked optional and the fallback path is functional.

## Files Examined

| File | Lines |
|---|---|
| `frontend/src/components/PresetRecommendationCard.tsx` | 11–19 (props), 24–47 (effect) |
| `frontend/src/App.tsx` | 683 (usage site) |
| `frontend/src/api.ts` | 333–344 (`fetchPresetRecommendations`) |
| `backend/app/api/routes.py` | 764–770 (route handler) |
