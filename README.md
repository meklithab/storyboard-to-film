# The Little Bean — Short Film Pipeline

Turns `storyboard.json` into narrated vertical (`720x1280`) and horizontal (`1280x720`) MP4 films.

## Install

1. Install **Python 3**, **FFmpeg** (on `PATH`), and **Make**.
2. Create a virtual environment and install Python dependencies:
   ```bash
   python -m venv .venv
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   # macOS/Linux:        source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Environment Variables

Copy `.env.example` to `.env` and fill in your keys (never commit `.env`):

- `GEMINI_API_KEY` — Google Gemini API key (used by `smoketest.py` and `narration.py`).
- `CLOUDFLARE_ACCOUNT_ID` — Cloudflare account ID (used by `smoketest.py` and `keyframes.py`).
- `CLOUDFLARE_API_TOKEN` — Cloudflare Workers AI API token (used by `smoketest.py` and `keyframes.py`).

## Run

Run the full pipeline with one command:

```bash
make film
```

This runs `validate`, `narration`, `keyframes`, `shots`, `subtitles`, and `assemble` in order.

- On the first run, `keyframes` stops after generating 4 character reference images per character in `outputs/reference/` (exit code `2`). Pick your preferred file for each character, write `outputs/reference/chosen.json` (for example `{"bean": "bean_v1.jpg", "grandmother": "grandmother_v1.jpg"}`), and run `make film` again.
- Optional: place `outputs/shots/shot_XX_wan.mp4` clips (from `notebooks/wan_shots.ipynb`) or `outputs/music/chosen.wav` (from `notebooks/acestep_music.ipynb`) before running `make film`.

Outputs are written to `outputs/final/film_vertical.mp4` and `outputs/final/film_horizontal.mp4`. Individual stages can also be run alone (`make validate`, `make narration`, `make keyframes`, `make shots`, `make subtitles`, `make assemble`, `make smoketest`, `make radio_cut`).
