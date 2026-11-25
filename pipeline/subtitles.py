"""Build an English SRT subtitle file timed by real narration lengths."""

import json
from pathlib import Path
import sys
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT_DIR, is_cached, load_storyboard, save_cache

DURATIONS_PATH = ROOT_DIR / "outputs" / "narration" / "durations.json"
SUBTITLES_PATH = ROOT_DIR / "outputs" / "subtitles" / "subtitles.srt"
SHOT_PAD_SECONDS = 0.5


def _format_srt_time(seconds: float) -> str:
    ms_total = max(0, round(seconds * 1000))
    hours, rem = divmod(ms_total, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def wrap_subtitle(text: str, max_chars: int = 40) -> str:
    """Wrap subtitle into at most 2 balanced lines near max_chars per line."""
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean

    wrapped = textwrap.wrap(clean, width=max_chars)
    if len(wrapped) <= 2:
        return "\n".join(wrapped)

    # Split at the word boundary closest to the midpoint so it fits in 2 lines
    mid = len(clean) // 2
    best_split = None
    best_dist = len(clean)
    for idx, ch in enumerate(clean):
        if ch == " " and abs(idx - mid) < best_dist:
            best_dist = abs(idx - mid)
            best_split = idx
    if best_split is None:
        return clean
    return f"{clean[:best_split]}\n{clean[best_split + 1:]}"


def main() -> int:
    if not DURATIONS_PATH.exists():
        print(f"Missing {DURATIONS_PATH} (run pipeline/narration.py first).", file=sys.stderr)
        return 1

    durations = json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))
    storyboard = load_storyboard()

    entries = []
    for shot in storyboard["shots"]:
        sid = shot["id"]
        if sid not in durations:
            print(f"Error: '{sid}' missing from {DURATIONS_PATH}", file=sys.stderr)
            return 1
        entries.append((sid, float(durations[sid]), shot["narration"]["english_subtitle"]))

    if is_cached("subtitles", "all", entries, SUBTITLES_PATH):
        return 0

    lines = []
    cursor = 0.0
    for idx, (_, dur, text) in enumerate(entries, start=1):
        start_ts = _format_srt_time(cursor)
        end_ts = _format_srt_time(cursor + dur)
        lines.append(f"{idx}\n{start_ts} --> {end_ts}\n{wrap_subtitle(text)}\n")
        cursor += dur + SHOT_PAD_SECONDS

    SUBTITLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBTITLES_PATH.write_text("\n".join(lines), encoding="utf-8")
    save_cache("subtitles", "all", entries)
    print(f"Wrote {len(entries)} subtitles to {SUBTITLES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
