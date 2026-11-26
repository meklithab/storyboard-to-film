# Architecture

`storyboard.json` is the single contract between stages. Every script in
`pipeline/` reads it (plus earlier stage outputs in `outputs/`) and writes only
to `outputs/` and `runs.jsonl`. A stage can be run alone, so changing one shot
does not force a full regeneration.

## Stages

| Stage | Script | Reads | Writes |
|---|---|---|---|
| Validate | `pipeline/validate.py` | `storyboard.json`, `schema/storyboard.schema.json` | Nothing; exits `1` on schema errors, bad voice/proverb references, duplicate shot IDs, shot count outside 8–12, or planned runtime outside 60–90 s |
| Smoke test | `pipeline/smoketest.py` | `.env`, storyboard | `outputs/cache/smoketest_*.wav/.jpg`, `runs.jsonl` |
| Narration | `pipeline/narration.py` | `storyboard.json` (`voices`, both spoken lines), `.env` | `outputs/narration/<id>_narrator.wav`, `<id>_<speaker>.wav`, `durations.json`, `voices_used.json`, `runs.jsonl` |
| Retime | `pipeline/retime.py` | all 20 narration WAVs, `durations.json` | trims silence, speeds up to `TARGET_FILM_SECONDS` (default 86 s), rewrites `durations.json`, keeps originals in `outputs/narration/raw/` |
| Radio cut | `pipeline/radio_cut.py` | storyboard + both WAVs per shot, optional `outputs/music/temp.wav` | `outputs/final/radio_cut.mp4` |
| Keyframes | `pipeline/keyframes.py` | storyboard (`characters`, `style_block`, `image_prompt`), `.env`, `outputs/reference/chosen.json` | `outputs/reference/<char>_v1..4.jpg`, `outputs/keyframes/<id>.jpg`, `runs.jsonl` |
| Shots | `pipeline/shots.py` | storyboard (`duration_seconds`, `motion_prompt`), `durations.json`, keyframe or `<id>_wan.mp4` | `outputs/shots/<id>.mp4` |
| Music | `pipeline/music.py` | storyboard `music` block | `outputs/music/cues.json`; writes a deterministic procedural `chosen.wav` if no ACE-Step candidate was chosen; logs the fallback in `runs.jsonl` |
| Subtitles | `pipeline/subtitles.py` | storyboard (both `english_subtitle`s), `durations.json` | `outputs/subtitles/subtitles.srt` (20 cues) |
| Assemble | `pipeline/assemble.py` | all above | `outputs/final/film_vertical.mp4`, `film_horizontal.mp4` |

`notebooks/acestep_music.ipynb` and `notebooks/wan_shots.ipynb` both read
`storyboard.json` directly, so changing the storyboard changes their prompts,
duration and seeds without editing notebook code.

## The dual-voice timeline

`common.narration_clips()` is the single definition of shot order: narrator
line, then the line whose `speaker` is named in `proverb`. `narration_pads()`
adds a 0.35 s gap between them and a 0.5 s tail after the proverb. The result
is stored per shot in `durations.json`:

```json
{
  "shot_01": {"narrator": 4.12, "grandmother": 2.98, "total": 7.95}
}
```

`shots.py` makes each video clip exactly `total` seconds long; `subtitles.py`
starts the proverb caption after the narrator caption plus the gap;
`radio_cut.py` and `assemble.py` concat the same two WAVs with the same pads.
All four stages therefore stay in sync when a line is re-recorded.

## Caching, retries and failure handling

- **Caching:** each stage hashes its inputs with SHA-256 into
  `outputs/cache/<stage>_<id>.sha256`. A matching hash plus a non-empty output
  prints `skipped (cached)`. Editing one `image_prompt` invalidates only that
  keyframe and its shot; editing one narration line invalidates only that one
  TTS call.
- **Retries and logging:** `retry_call()` retries model calls with backoff;
  `log_run()` appends every attempt (success or failure) to `runs.jsonl`.
- **Voice fallback:** a configured Gemini voice that is rejected is retried
  once, then tried against `Kore`, `Puck` and `Sulafat`. The voice actually
  used is recorded in `outputs/narration/voices_used.json`.
- **Reference approval:** `outputs/reference/chosen.json` is the human gate.
  If absent, keyframes auto-select `<char>_v1.jpg` so a clean clone still runs
  `make film` end to end.
- **Runtime budget:** the raw Gemini TTS lines measured 98.8 s with the end
  card, over the 60–90 s limit. `retime.py` trims leading/trailing silence
  (2.5% of peak) and derives the smallest speed-up needed to reach the target,
  then stores the result and hashes in `.retime.json` so reruns are no-ops and
  raw takes are never processed twice. Both finals measured 86.0 s.
- **FFmpeg discovery:** `common.ffmpeg_bin()` checks `PATH`, then winget/scoop
  and common install folders, so `make film` works in a fresh shell.
- **Moving-shot fallback:** if a Wan 2.2 clip exists it is used; otherwise
  `shots.py` animates the keyframe with FFmpeg `zoompan`. Explicit camera words
  in `motion_prompt` (`pushes in`, `pulls back`, `pan left/right`) choose the
  motion; otherwise the stage cycles gently through four motions.
- **Music fallback:** `music.py` writes a seeded, originally-generated
  instrumental to `outputs/music/chosen.wav` when no ACE-Step candidate was
  chosen. Assembly therefore always has a ducked score; the fallback is tagged
  `procedural-krar-fallback` in `runs.jsonl` and is never claimed to be an
  ACE-Step output.
- **Limits:** three model attempts per shot before a fallback (TTS uses
  configured voice + fallbacks; images use `retry_call`), so a quota or a bad
  model never stalls the whole edit.

## Secrets

Keys (`GEMINI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`) live
only in `.env`, which is ignored by Git. `common.load_env()` loads them without
printing or logging their values.
