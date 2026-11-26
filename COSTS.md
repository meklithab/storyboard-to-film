# Costs and measurements

Free tier at the time of this build: Gemini text/TTS free tier, Cloudflare
Workers AI daily allowance, Wan 2.2 and ACE-Step 1.5 on borrowed Kaggle/Colab
GPUs, FFmpeg local. Free limits change often; treat the figures below as what
this repository actually observed, not as provider guarantees.

## Observed model calls (`runs.jsonl`)

Aggregated from all logged calls currently in the repository (some were made
while developing the earlier storyboard, but they use the same models):

| Stage / model | Calls | Total latency | Mean | Max |
|---|---:|---:|---:|---:|
| `reference` — `@cf/black-forest-labs/flux-2-klein-4b` | 8 | 76.8 s | 9.6 s | 13.2 s |
| `narration` — `gemini-3.8-flash-tts` | 17 | 40.0 s | 2.35 s | 5.37 s |
| `smoketest` — text / TTS / FLUX | 5 | 298.1 s | 59.6 s | 288.2 s |

The 288 s smoketest call was a slow/failed Cloudflare request; failed attempts
are retained with `success: false` rather than hidden. New calls from the
dual-voice film append to the same file with `role`, `voice_name`, seed and
latency in `parameters`.

Observed free-tier limit: `gemini-3.8-flash-tts` allows **3 requests/minute**
(`429 RESOURCE_EXHAUSTED`, `retryDelay` ≈ 42 s). The narration stage therefore
paces calls 21 s apart by default; 20 lines take roughly 7 minutes of waiting
plus synthesis time. Override with `GEMINI_TTS_MIN_INTERVAL_SECONDS` if your
quota differs, and rerun `make narration` after a stop — cached lines are kept.

## Planned per-stage cost for this film

| Stage | Unit | GPU minutes | List-price equivalent | Measured? |
|---|---|---:|---|---|
| Validate / music cues / subtitles | 1 run each | 0 | $0 (local code) | Yes: `make test` |
| Narration | 20 TTS calls (2 voices × 10 shots) | 0 hosted | Gemini TTS free tier; frontier TTS list price would be ~$0.015–0.06 per 1k chars | Yes: 20 cached WAVs, all calls logged in `runs.jsonl` |
| Keyframes | 4 reference sheets + 40 keyframes (20 vertical + 20 wide) | 0 hosted | Cloudflare free daily allowance; comparable hosted FLUX ≈ $0.002–0.01/image | Yes: refreshed reference and all keyframes regenerated after audience feedback |
| Moving shots | 10 × 8 s | 0 if fallback; Wan 2.2 TI2V-5B ≈ 4–10 GPU min per 5 s draft clip on T4 | Open weights; hosted 720p video ≈ $0.05–0.30/s | Not yet run |
| Music | Procedural fallback score, 83 s | 0 | $0 (stdlib synthesis); ACE-Step would be open weights (MIT), hosted ≈ $0.05–0.20/track | Yes: `chosen.wav` 83.0 s, 44.1 kHz, seed 42 |
| Assembly | 2 exports, 2 aspect ratios | 0 | $0 (FFmpeg) | Yes: both 89.0 s finals exported via `common.ffmpeg_bin()` |

List-price figures are indicative comparisons, not charges made by this
project. GPU minutes are the real constraint: draft at 480p, batch jobs and keep
only chosen candidates.

## Runtime budget

The storyboard now plans 10 × 8 s + 4 s intro + 3 s end card = **87 s**.
Measured TTS gave 98.8 s; `make retime` trims dead air and applies a 1.068x
speed-up so both exports are **89.0 s**, inside the 60–90 s requirement. The
character revision regenerated 4 reference sheets and 40 keyframes (20 vertical
+ 20 wide) through Cloudflare Workers AI; all calls are recorded in
`runs.jsonl`. FFmpeg encoding of the two finals and 20 shot clips is local and
free (~1–2 CPU minutes).
