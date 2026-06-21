# UX-3A P1 Fix — SubtitleGallery Race Condition

## Verdict: P1 CONFIRMED FIXED

## Files Changed

| File | Change |
|---|---|
| `frontend/src/api.ts` | Added `signal?: AbortSignal` param to `fetchSubtitleStylePreviews`, passed into `fetch()` options |
| `frontend/src/components/SubtitleGallery.tsx` | Removed `useCallback`; added `abortRef` + `requestIdRef`; moved API call inside `useEffect` with request ID guard, `AbortError` silent catch, and full effect cleanup |

## What Was Fixed

**Before:** `SubtitleGallery` used a `useCallback`-wrapped `callApi` fired via debounced `useEffect`. No `AbortController`, no sequence guard. Rapid sample text input could produce stale in-flight responses overwriting fresh data.

**After:** Follows the exact pattern from `PromptPreviewCard.tsx:16-69`:

1. `useEffect` body creates a per-effect `AbortController` and increments `requestIdRef`
2. Previous in-flight request is aborted before each new one (`abortRef.current.abort()`)
3. `setData`, `setError`, `setLoading` are guarded by `requestIdRef.current === requestId`
4. `AbortError` (from `DOMException`) is caught silently — no error state set
5. Cleanup clears timeout **and** aborts the controller on effect teardown/unmount
6. Effect dependencies are individual `renderOptions.subtitle_*` fields + `sampleText`

## Validation

| Check | Result |
|---|---|
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | 414.96 KB JS, 0 errors |
| `python -m pytest tests/ -q` | 184 passed |

## Remaining Open Items from Audit (non-blocking)

| Severity | Issue | File:Line |
|---|---|---|
| P3 | `loading && !data` hides spinner during re-fetch | `SubtitleGallery.tsx:75` |
| P3 | Error message is generic, no retry button | `SubtitleGallery.tsx:76` |
| P4 | `as React.CSSProperties` (3×) for vendor-prefixed props | `SubtitlePreviewCard.tsx:23,28,33` |
| P4 | No `overflow:hidden` on text container | `SubtitlePreviewCard.tsx:40-46` |
| P5 | `text_align: string` could be narrowed to union | `types.ts:336` |
