# Grandma Has a Proverb for Everything — AI short-film pipeline

A 60–90 second Amharic short with English subtitles, made from one contract
file, `storyboard.json`. Ten shots follow a grandchild through everyday
mishaps; each time, grandmother has a proverb ready, and the film ends with the
family together over coffee.

The old "Little Bean" storyboard has been replaced. This repository now makes
**"Grandma Has a Proverb for Everything"**; every stage reads the new
storyboard, including its two voices and its per-shot `proverb` blocks.

## What the pipeline does

| Stage | Command | Output |
|---|---|---|
| Validate | `make validate` | Schema + semantic checks (voices, proverb speakers, 8–12 shots, 60–90 s plan) |
| Narration | `make narration` | Two Amharic WAVs per shot (`<id>_narrator.wav`, `<id>_grandmother.wav`), `durations.json`, `voices_used.json` |
| Retime | `make retime` | Trims TTS dead air and applies a small speed-up so the film lands at ~89 s including the 4 s intro; raw takes kept in `outputs/narration/raw/` |
| Keyframes | `make keyframes` | Four reference variants per character, then a 9:16 and a **true 16:9** keyframe per shot via Cloudflare FLUX.2 |
| Refresh reference | `make refresh_reference` | Regenerates the approved character sheets from the current prompts when the character design changes |
| Shots | `make shots` | Vertical and horizontal per-shot MP4s (Wan 2.2 clip if present, otherwise FFmpeg slow pan/zoom) |
| Music | `make music` | Music cue sheet from `storyboard.json`; checks for `outputs/music/chosen.wav` |
| Subtitles | `make subtitles` | 20 English SRT cues, shifted by the intro and timed from measured narration including the narrator→proverb gap |
| Assemble | `make assemble` | Intro card, ducking, burned-in subtitles, end card, −14 LUFS master, two independent true-format MP4s |
| Radio cut | `make radio_cut` | Black screen with both voices in order; the cheap story prototype |

`storyboard.json` is the only place prompts, seeds, shots, narration, proverbs,
voices and music cues are written. `schema/storyboard.schema.json` is checked
before every run. Every model call appends one line to `runs.jsonl` with model,
parameters, seed, latency and cost.

## Install

1. Install **Python 3**, **FFmpeg** and **Make**. FFmpeg is found on `PATH` or at
   its usual winget/scoop install location automatically.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   # macOS/Linux:        source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Environment variables

Copy `.env.example` to `.env` and fill in your keys (never commit `.env`):

- `GEMINI_API_KEY` — Google Gemini API key, used for text smoke test and both TTS voices.
- `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` — Cloudflare Workers AI, used for reference sheets and keyframes.

## Run

```bash
make film
```

That runs `validate → narration → retime → keyframes → shots → music → subtitles → assemble`.

- `outputs/reference/chosen.json` currently approves `grandmother_v1.jpg`,
  regenerated from the Habesha-specific character prompt. When it exists, normal
  reference generation is skipped so the chosen image is never overwritten. To
  redraw the approved sheets after a prompt change, run `make refresh_reference`.
  To approve a different sheet, edit that file (e.g.
  `{"grandmother": "grandmother_v3.jpg"}`) and rerun; only affected keyframes
  change.
- No ACE-Step GPU is required: `make music` writes a deterministic 83 s
  procedural krar-like score to `outputs/music/chosen.wav` when no candidate is
  present, and logs it as `procedural-krar-fallback` in `runs.jsonl`. To use a
  generated ACE-Step track instead, run `notebooks/acestep_music.ipynb`, copy a
  candidate over `chosen.wav`, and rerun `make music`.
- Optional: generate Wan 2.2 clips in `notebooks/wan_shots.ipynb`. A
  `<shot_id>_wan.mp4` automatically overrides the FFmpeg pan/zoom fallback.

The film opens with a 4-second title card ("Ten small mishaps. Ten proverbs.
One grandmother who always knows what to say."), then runs the ten shots and a
3-second "Made with AI" end card. It is written to
`outputs/final/film_vertical.mp4` (720×1280) and
`outputs/final/film_horizontal.mp4` (1280×720). The horizontal file is **not** a
letterboxed vertical video: it is assembled from separately generated 16:9
keyframes, clips, intro and end card. The storyboard plans 87 s with the intro;
measured TTS came out longer, so `make retime` removes dead air and applies a
small speed-up. Both exports are **89.0 s**, inside the 60–90 s requirement.
Override the target with `TARGET_FILM_SECONDS` if you want a different pace.

## Regenerating one shot

```bash
python pipeline/keyframes.py --shot shot_03   # regenerates both 9:16 and 16:9 keyframes
make film
```

The cache hashes each stage's inputs, so only `shot_03` is regenerated; the
other nine shots and all 20 narration calls are skipped. `tests/test_rerun.py`
checks exactly that, and `tests/test_timeline.py` checks the dual-voice timing
offline without keys or FFmpeg:

```bash
make test
python tests/test_rerun.py   # full pipeline + one-shot regeneration
```

## Cost and licences

See `COSTS.md` for measured latency/GPU minutes and list-price equivalents,
and `ETHICS.md` for voice/licence/labelling notes. Both voices are **synthetic
Gemini TTS voices**; no real person's voice or likeness is reproduced.
