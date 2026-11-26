"""Build English subtitles for both spoken lines in every shot.

Timings come from the measured narration durations, including the short pause
between the grandchild's line and the grandmother's proverb.
"""

import json
from pathlib import Path
import sys
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    NARRATION_GAP_SECONDS,
    ROOT_DIR,
    SHOT_PAD_SECONDS,
    is_cached,
    load_storyboard,
    narration_clips,
    save_cache,
)

DURATIONS_PATH = ROOT_DIR / "outputs" / "narration" / "durations.json"
SUBTITLES_PATH = ROOT_DIR / "outputs" / "subtitles" / "subtitles.srt"


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


def _build_entries(storyboard: dict, durations: dict) -> list[dict]:
    """One SRT entry per spoken line, in film time order."""
    entries: list[dict] = []
    cursor = 0.0
    for shot in storyboard["shots"]:
        sid = shot["id"]
        if sid not in durations:
            raise ValueError(f"'{sid}' missing from {DURATIONS_PATH}")
        measured = durations[sid]
        if not isinstance(measured, dict):
            measured = {narration_clips(storyboard, shot)[0][0]: float(measured)}
        clips = narration_clips(storyboard, shot)
        for idx, (role, line, _filename) in enumerate(clips):
            if role not in measured:
                raise ValueError(f"'{sid}/{role}' missing from {DURATIONS_PATH}")
            dur = float(measured[role])
            gap = NARRATION_GAP_SECONDS if idx < len(clips) - 1 else SHOT_PAD_SECONDS
            entries.append(
                {
                    "shot_id": sid,
                    "role": role,
                    "start": round(cursor, 3),
                    "end": round(cursor + dur, 3),
                    "text": line["english_subtitle"],
                }
            )
            cursor += dur + gap
    return entries


def main() -> int:
    if not DURATIONS_PATH.exists():
        print(f"Missing {DURATIONS_PATH} (run pipeline/narration.py first).", file=sys.stderr)
        return 1

    try:
        durations = json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))
        entries = _build_entries(load_storyboard(), durations)
    except (ValueError, KeyError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if is_cached("subtitles", "all", entries, SUBTITLES_PATH):
        return 0

    lines = []
    for idx, entry in enumerate(entries, start=1):
        lines.append(
            f"{idx}\n{_format_srt_time(entry['start'])} --> "
            f"{_format_srt_time(entry['end'])}\n{wrap_subtitle(entry['text'])}\n"
        )

    SUBTITLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUBTITLES_PATH.write_text("\n".join(lines), encoding="utf-8")
    save_cache("subtitles", "all", entries)
    print(
        f"Wrote {len(entries)} subtitles to {SUBTITLES_PATH} "
        f"({NARRATION_GAP_SECONDS}s narrator-to-proverb gap)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
