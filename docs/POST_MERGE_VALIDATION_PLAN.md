# Post-Merge Validation Plan — Voice Duration Fix

> **Purpose:** Manual pre-release validation of the voice-duration-fix render pipeline.  
> **Executor:** Human with backend + ffmpeg/ffprobe available.  
> **Blocking:** Release must be blocked if either Scenario A or Scenario B fails.

---

## 1. Backend Startup

```powershell
# Kill stale processes + clean pycache
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path "E:\AUTO_REVIEW\backend" -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# Start uvicorn hidden
Start-Process -WindowStyle Hidden -FilePath "E:\AUTO_REVIEW\.venv312\Scripts\python.exe" `
  -ArgumentList "-m uvicorn app.main:app --port 8007 --host 127.0.0.1" `
  -WorkingDirectory "E:\AUTO_REVIEW\backend"
Start-Sleep -Seconds 6

# Verify
if (-not (Get-NetTCPConnection -LocalPort 8007 -ErrorAction SilentlyContinue)) { throw "Port 8007 not listening" }
Invoke-RestMethod -Uri "http://127.0.0.1:8007/docs" -Method Get -ErrorAction Stop
Write-Host "Backend ready on port 8007"
```

### Verification

```powershell
python -c "import json, urllib.request; req=urllib.request.Request('http://127.0.0.1:8007/openapi.json'); spec=json.loads(urllib.request.urlopen(req).read()); print(f'{len(spec[\"paths\"])} routes')"
```

Expected: `45 routes`

---

## 2. Test Video Sources

Create two short synthetic video files for controlled testing.

### Source A — 10 second segment (used for `footage_extend`)

```powershell
# 10 seconds, 1920×1080, 30fps, colour bars + silence
& "ffmpeg" -y -f lavfi -i "color=c=blue:s=1920x1080:d=10:r=30" `
  -f lavfi -i "anullsrc=r=44100:cl=mono" `
  -c:v libx264 -preset ultrafast -crf 28 `
  -c:a aac -shortest `
  "E:\AUTO_REVIEW\tests\assets\source_10s.mp4"
```

### Source B — 4 second segment (used for `freeze_frame`)

```powershell
& "ffmpeg" -y -f lavfi -i "color=c=red:s=1920x1080:d=4:r=30" `
  -f lavfi -i "anullsrc=r=44100:cl=mono" `
  -c:v libx264 -preset ultrafast -crf 28 `
  -c:a aac -shortest `
  "E:\AUTO_REVIEW\tests\assets\source_4s.mp4"
```

Expected files:

```text
E:\AUTO_REVIEW\tests\assets\source_10s.mp4  (10.0s duration)
E:\AUTO_REVIEW\tests\assets\source_4s.mp4   (4.0s duration)
```

Verify with:

```powershell
& "ffprobe" -v error -select_streams v:0 -show_entries format=duration `
  -of csv=p=0 "E:\AUTO_REVIEW\tests\assets\source_10s.mp4"
& "ffprobe" -v error -select_streams v:0 -show_entries format=duration `
  -of csv=p=0 "E:\AUTO_REVIEW\tests\assets\source_4s.mp4"
```

---

## 3. Scenario A — `footage_extend`

**Goal:** Voice duration (120 chars TTS ≈ 6–7s) > scene duration (5s), but source has remaining footage.  
System should extend `source_end` instead of trimming voice.

### 3.1 Render Request (PowerShell)

```powershell
$body = @{
    local_video_path = "E:\AUTO_REVIEW\tests\assets\source_10s.mp4"
    burn_subtitle = $true
    gemini_json = @{
        metadata = @{
            video_title = "FootageExtend Test"
            rewrite_style = "Viral"
            target_audience = "Đại chúng"
            tone = "Năng lượng cao"
            target_duration = "1-3 phút"
        }
        sources = @(@{
            source_id = "source_a"
            local_video_path = "E:\AUTO_REVIEW\tests\assets\source_10s.mp4"
        })
        rewrite_script = @{
            full_text = "Đây là một câu nói rất dài để kiểm tra chức năng kéo dài video khi giọng nói vượt quá độ dài của cảnh quay gốc."
        }
        srt = @(@{
            index = 1
            start = "00:00:00,000"
            end = "00:00:05,000"
            text = "Đây là một câu nói rất dài để kiểm tra chức năng kéo dài video khi giọng nói vượt quá độ dài của cảnh quay gốc."
        })
        video_segments = @(@{
            segment_id = 1
            order = 1
            source_id = "source_a"
            source_start = "00:00:00.000"
            source_end = "00:00:05.000"
            subtitle_start = 1
            subtitle_end = 1
            scene_description = "Test footage extend"
            importance_score = 95
        })
    }
    render_options = @{
        tts_mode = "voiceover"
        tts_engine = "vieneu_turbo"
        # tts_language removed (dead code — vendor auto-detects)
        tts_persona = "neutral"
        tts_voice_region = "auto"
        tts_voice_gender = "female"
        tts_fit_policy = "hybrid"
        tts_max_speed = 1.5
        vertical_mode = "none"
        render_quality = "fast"
        subtitle_mode = "burn"
        subtitle_style = "default"
        artifact_retention = "keep_all"
    }
} | ConvertTo-Json -Depth 10

# Send render request
$response = Invoke-RestMethod -Uri "http://127.0.0.1:8007/api/render" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$response | ConvertTo-Json -Depth 10
```

### 3.2 Expected Output

Render response includes:

```json
{
    "message": "...",
    "final_video_path": "...output.mp4",
    "final_subtitle_path": "...subtitle.srt",
    "render_plan_path": "...render_plan.json",
    "voiceover_path": "...voiceover.wav",
    "output_duration_seconds": "..."
}
```

### 3.3 Verify

```powershell
# Paths from response
$outputDir = [System.IO.Path]::GetDirectoryName($response.final_video_path)
```

#### 3.3.1 `render_plan.json`

```powershell
$plan = Get-Content "$outputDir\*_render_plan.json" -Raw | ConvertFrom-Json
$plan.segment_plan[0] | Format-List
```

Expected:

```text
decision             : footage_extend
original_scene_duration : 5.0
final_scene_duration    : ≈ voice_natural_duration
natural_voice_duration  : ≈ TTS actual (6–7s)
extend_seconds       : final_scene_duration - original_scene_duration
speed_factor         : 1.0
freeze_duration      : null
warning              : ""
```

#### 3.3.2 Voiceover duration

```powershell
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "$outputDir\*_voiceover.wav"
```

Expected: `≈ 6–7s` (natural TTS, no trimming)

```powershell
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "$outputDir\*_output.mp4"
```

Assert: `video_duration >= voiceover_duration`

#### 3.3.3 Video `source_end` extended

```powershell
$plan = Get-Content "$outputDir\*_render_plan.json" -Raw | ConvertFrom-Json
$plan.video_segments[0].source_end
```

Expected: `"00:00:06.xxx"` (or higher), not `"00:00:05.000"`

#### 3.3.4 Subtitle reaches voice end

```powershell
Get-Content "$($response.final_subtitle_path)" -Encoding UTF8
```

Expected: last SRT cue end ≈ voiceover duration, not trimmed to 5s.

---

## 4. Scenario B — `freeze_frame`

**Goal:** Voice duration (120 chars TTS ≈ 6–7s) > scene duration (4s), and **no remaining footage** (source_end == source duration).  
System should add freeze frame without changing `source_end`.

### 4.1 Render Request (PowerShell)

```powershell
$body = @{
    local_video_path = "E:\AUTO_REVIEW\tests\assets\source_4s.mp4"
    burn_subtitle = $true
    gemini_json = @{
        metadata = @{
            video_title = "FreezeFrame Test"
            rewrite_style = "Viral"
            target_audience = "Đại chúng"
            tone = "Năng lượng cao"
            target_duration = "1-3 phút"
        }
        sources = @(@{
            source_id = "source_b"
            local_video_path = "E:\AUTO_REVIEW\tests\assets\source_4s.mp4"
        })
        rewrite_script = @{
            full_text = "Đây là một câu nói rất dài để kiểm tra chức năng đóng băng khung hình khi giọng nói vượt quá độ dài của cảnh quay nhưng không còn cảnh quay để kéo dài nữa."
        }
        srt = @(@{
            index = 1
            start = "00:00:00,000"
            end = "00:00:04,000"
            text = "Đây là một câu nói rất dài để kiểm tra chức năng đóng băng khung hình khi giọng nói vượt quá độ dài của cảnh quay nhưng không còn cảnh quay để kéo dài nữa."
        })
        video_segments = @(@{
            segment_id = 1
            order = 1
            source_id = "source_b"
            source_start = "00:00:00.000"
            source_end = "00:00:04.000"
            subtitle_start = 1
            subtitle_end = 1
            scene_description = "Test freeze frame"
            importance_score = 95
        })
    }
    render_options = @{
        tts_mode = "voiceover"
        tts_engine = "vieneu_turbo"
        # tts_language removed (dead code — vendor auto-detects)
        tts_persona = "neutral"
        tts_voice_region = "auto"
        tts_voice_gender = "female"
        tts_fit_policy = "hybrid"
        tts_max_speed = 1.5
        vertical_mode = "none"
        render_quality = "fast"
        subtitle_mode = "burn"
        subtitle_style = "default"
        artifact_retention = "keep_all"
    }
} | ConvertTo-Json -Depth 10

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8007/api/render" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body

$response | ConvertTo-Json -Depth 10
```

### 4.2 Verify

```powershell
$outputDir = [System.IO.Path]::GetDirectoryName($response.final_video_path)
```

#### 4.2.1 `render_plan.json`

```powershell
$plan = Get-Content "$outputDir\*_render_plan.json" -Raw | ConvertFrom-Json
$plan.segment_plan[0] | Format-List
```

Expected:

```text
decision             : freeze_frame
original_scene_duration : 4.0
final_scene_duration    : ≈ voice_natural_duration (6–7s)
natural_voice_duration  : ≈ TTS actual
extend_seconds       : final - original (2–3s)
speed_factor         : 1.0
freeze_duration      : ≈ extend_seconds
warning              : ""
```

#### 4.2.2 `source_end` unchanged (CRITICAL — no double-extension)

```powershell
$plan.video_segments[0].source_end
```

Expected: `"00:00:04.000"` — must NOT be extended.

#### 4.2.3 `freeze_frame_duration` set

```powershell
$plan.video_segments[0].freeze_frame_duration
```

Expected: `≈ 2–3` (not null)

#### 4.2.4 Video duration == original + freeze

```powershell
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "$outputDir\*_output.mp4"
```

Expected: `≈ 4.0 + freeze_duration` (e.g., 6.5s)  
Assert NOT equal to `4.0 + extend_seconds + extend_seconds` (no double-extension).

#### 4.2.5 Voiceover duration

```powershell
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "$outputDir\*_voiceover.wav"
```

Assert: `voiceover_duration ≥ video_duration - 0.15`  
Assert: `voiceover_duration ≥ final_scene_duration - 0.15`

#### 4.2.6 Subtitle reaches voice end

```powershell
Get-Content "$($response.final_subtitle_path)" -Encoding UTF8
```

Expected: last SRT cue end ≈ voiceover duration, not trimmed to 4s.

---

## 5. Expected Files

After each render, these files exist in `output_dir`:

| File | Description |
|------|-------------|
| `*_output.mp4` | Final rendered video |
| `*_voiceover.wav` | Full TTS voiceover (untrimmed) |
| `*_render_plan.json` | Full render plan + diagnostics |
| `*_subtitle.srt` | Output subtitle file |
| `*_tts_plan.json` | TTS segment plan (if generated) |

---

## 6. ffprobe Commands

```powershell
# Video duration
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "path\to\output.mp4"

# Audio duration
& "ffprobe" -v error -show_entries format=duration -of csv=p=0 "path\to\voiceover.wav"

# Video codec + resolution + fps
& "ffprobe" -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of json "path\to\output.mp4"

# Check voice is not silence (RMS audio level)
& "ffprobe" -v error -f lavfi -i "amovie=path\to\voiceover.wav,astats=metadata=1:reset=1" -show_entries frame=pkt_duration -of csv=p=0 2>$null | Measure-Object | Select-Object Count
```

---

## 7. Pass / Fail Checklist

### Scenario A — footage_extend

| # | Assertion | Pass | Fail |
|---|-----------|------|------|
| A1 | `segment_plan[0].decision == "footage_extend"` | ☐ | ☐ |
| A2 | `segment_plan[0].speed_factor == 1.0` | ☐ | ☐ |
| A3 | `source_end > original_source_end` (extended) | ☐ | ☐ |
| A4 | `voiceover_duration ≥ original_scene_duration - 0.1` | ☐ | ☐ |
| A5 | `video_duration ≥ voiceover_duration - 0.1` | ☐ | ☐ |
| A6 | `segment_plan[0].freeze_duration` is null | ☐ | ☐ |
| A7 | Last SRT cue end ≥ voiceover_duration - 0.1 | ☐ | ☐ |
| A8 | No warning about voice trimming in logs | ☐ | ☐ |

### Scenario B — freeze_frame

| # | Assertion | Pass | Fail |
|---|-----------|------|------|
| B1 | `segment_plan[0].decision == "freeze_frame"` | ☐ | ☐ |
| B2 | `segment_plan[0].speed_factor == 1.0` | ☐ | ☐ |
| B3 | `source_end == original_source_end` (NOT extended) | ☐ | ☐ |
| B4 | `freeze_frame_duration` is set and ≈ `extend_seconds` | ☐ | ☐ |
| B5 | `video_duration ≈ original_scene_duration + freeze_duration` | ☐ | ☐ |
| B6 | `video_duration != original_scene_duration + freeze_duration * 2` (no double-extend) | ☐ | ☐ |
| B7 | `voiceover_duration ≥ video_duration - 0.15` | ☐ | ☐ |
| B8 | Last SRT cue end ≥ voiceover_duration - 0.1 | ☐ | ☐ |
| B9 | No warning about voice trimming in logs | ☐ | ☐ |

### Overall

| # | Check | Pass | Fail |
|---|-------|------|------|
| O1 | Full test suite: `283 passed` | ☐ | ☐ |
| O2 | Backend route count: `45 routes` | ☐ | ☐ |
| O3 | No Python traceback in console logs | ☐ | ☐ |

---

## 8. Results Submission

After completing validation, paste the following into the release PR or ticket:

```text
## Pre-Release Validation Results

### Execution
- Date: _______________
- Executor: _______________
- Backend commit: _______________

### Scenario A — footage_extend
- [ ] All A1–A8 pass
- Artifacts: E:\AUTO_REVIEW\validation\scenario_a\

### Scenario B — freeze_frame
- [ ] All B1–B9 pass
- Artifacts: E:\AUTO_REVIEW\validation\scenario_b\

### Overall
- [ ] O1 (283 tests): _______
- [ ] O2 (45 routes): _______
- [ ] O3 (no traceback): _______

### Verdict
- [ ] RELEASE BLOCKED — one or more assertions failed (attach logs)
- [ ] RELEASE APPROVED — all assertions pass
```

### Store artifacts

```powershell
# Create validation output directory
New-Item -ItemType Directory -Path "E:\AUTO_REVIEW\validation\scenario_a" -Force
New-Item -ItemType Directory -Path "E:\AUTO_REVIEW\validation\scenario_b" -Force

# After each scenario, copy artifacts
Copy-Item "$outputDir\*_output.mp4" "E:\AUTO_REVIEW\validation\scenario_a\output.mp4"
Copy-Item "$outputDir\*_voiceover.wav" "E:\AUTO_REVIEW\validation\scenario_a\voiceover.wav"
Copy-Item "$outputDir\*_render_plan.json" "E:\AUTO_REVIEW\validation\scenario_a\render_plan.json"
Copy-Item "$outputDir\*_subtitle.srt" "E:\AUTO_REVIEW\validation\scenario_a\subtitle.srt"
```

### Blocking criteria

Release is **blocked** if:

- Any A-row or B-row assertion fails, **OR**
- Full test suite does not report `283 passed`, **OR**
- Backend reports fewer than `45 routes`, **OR**
- An unhandled exception / traceback appears in uvicorn stderr
