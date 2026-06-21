# UX-1.5 Performance — Prompt Preview Latency

**Date:** 2026-06-08  
**Endpoint:** `POST /api/prompt/preview`  
**Iterations per size:** 10

| Size | Min (ms) | Avg (ms) | Max (ms) | p50 (ms) |
|------|----------|----------|----------|----------|
| small | 1.26 | 14.14 | 82.48 | 1.75 |
| medium | 1.59 | 7.88 | 25.12 | 2.22 |
| large | 1.34 | 6.18 | 25.18 | 2.08 |

## Conclusion

**Average latency 9.40ms ≤ 100ms.**  
No caching strategy needed at this time.
