# Architecture

`storyboard.json` is the single contract between stages. Every script lives in `pipeline/`, reads `storyboard.json` (plus earlier stage files in `outputs/`), and writes only to `outputs/` and `runs.jsonl`.

## Stages

| Stage | Script | Reads | Writes |
|---|---|---|---|
| Validate | `pipeline/validate.py` | `storyboard.json`, `schema/storyboard.schema.json` | Nothing (exits `1` on errors: schema, 8–12 shots, duplicate shot IDs, unknown character IDs) |
| Smoke test | `pipeline/smoketest.py` | `.env` | `outputs/cache/smoketest_tts.wav`, `outputs/cache/smoketest_image.jpg`, `runs.jsonl` |
| Narration | `pipeline/narration.py` | `storyboard.json`, `.env` | `outputs/narration/<shot_id>.wav`, `outputs/narration/durations.json`, `runs.jsonl` |
| Radio cut | `pipeline/radio_cut.py` | `storyboard.json`, `outputs/narration/*.wav`, optional `outputs/music/temp.wav` | `outputs/final/radio_cut.mp4` |
| Keyframes | `pipeline/keyframes.py` | `storyboard.json`, `.env`, `outputs/reference/chosen.json` | Step 1: `outputs/reference/<char>_v1..4.jpg`; Step 2: `outputs/keyframes/<shot_id>.jpg`, `runs.jsonl` |
| Shots | `pipeline/shots.py` | `storyboard.json`, `outputs/narration/durations.json`, `<shot>_wan.mp4` or keyframe | `outputs/shots/<shot_id>.mp4` |
| Subtitles | `pipeline/subtitles.py` | `storyboard.json`, `outputs/narration/durations.json` | `outputs/subtitles/subtitles.srt` |
| Assemble | `pipeline/assemble.py` | `storyboard.json`, `outputs/shots/*.mp4`, `outputs/narration/*.wav`, `durations.json`, `subtitles.srt`, optional `outputs/music/chosen.wav` | `outputs/final/film_vertical.mp4` (`720x1280`), `outputs/final/film_horizontal.mp4` (`1280x720`) |

*(Note: `pipeline/music.py` is currently an empty stub; music candidates are generated in `notebooks/acestep_music.ipynb`.)*

## Caching, Retries, and Fallback

- **Caching (`pipeline/common.py`):** Each stage hashes its item inputs with SHA-256 into `outputs/cache/<stage>_<id>.sha256`. If the hash matches and the output file exists and is non-empty, work is skipped and `skipped (cached)` is printed.
- **Retries & Logging (`pipeline/common.py`):** `retry_call` retries failed model API calls 3 times with `1s`, `2s`, `4s` waits. `log_run` appends every call attempt as one JSON line to `runs.jsonl`.
- **Zoom Fallback (`pipeline/shots.py`):** If `outputs/shots/<shot_id>_wan.mp4` (from Kaggle `notebooks/wan_shots.ipynb`) exists, it is trimmed/scaled to 24 fps; otherwise `shots.py` animates the keyframe with FFmpeg `zoompan`, alternating `zoom_in`, `zoom_out`, `pan_left`, and `pan_right` for `durations[id] + 0.5` seconds.
- **Optional Music Ducking (`pipeline/assemble.py`):** If `outputs/music/chosen.wav` exists, it is ducked under narration with FFmpeg `sidechaincompress` (`threshold=0.02`, `ratio=6`, `attack=300` ms, `release=1500` ms). If missing, `assemble.py` prints a warning and exports without music.

## Secrets

API keys (`GEMINI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`) are stored only in `.env`, which is listed in `.gitignore`. `common.load_env()` loads `.env` into process environment variables and never prints or logs key values.
