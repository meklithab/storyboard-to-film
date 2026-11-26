
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "pipeline"))

from common import (  # noqa: E402
    NARRATION_GAP_SECONDS,
    SHOT_PAD_SECONDS,
    load_storyboard,
    narration_clips,
    narration_pads,
    shot_total_seconds,
)
from shots import _motion_for_shot  # noqa: E402
from subtitles import _build_entries  # noqa: E402


def main() -> int:
    storyboard = load_storyboard()
    durations: dict[str, dict] = {}
    for shot in storyboard["shots"]:
        clips = narration_clips(storyboard, shot)
        assert len(clips) == 2, shot["id"]
        entry = {role: 3.0 for role, _line, _filename in clips}
        entry["total"] = round(
            sum(entry.values())
            + NARRATION_GAP_SECONDS * (len(clips) - 1)
            + SHOT_PAD_SECONDS,
            3,
        )
        durations[shot["id"]] = entry
        assert narration_pads(clips) == [NARRATION_GAP_SECONDS, SHOT_PAD_SECONDS]

    entries = _build_entries(storyboard, durations)
    assert len(entries) == 2 * len(storyboard["shots"])
    assert entries[0]["start"] == 0.0
    assert abs(entries[0]["end"] - 3.0) < 1e-6
    assert abs(entries[1]["start"] - (3.0 + NARRATION_GAP_SECONDS)) < 1e-6
    assert abs(entries[2]["start"] - shot_total_seconds(durations, storyboard["shots"][0]["id"])) < 1e-6

    film_length = sum(e["total"] for e in durations.values()) + float(
        storyboard["end_card"]["duration_seconds"]
    )
    assert abs((entries[-1]["end"] + SHOT_PAD_SECONDS + 3.0) - film_length) < 1e-6

    assert _motion_for_shot({"motion_prompt": "Camera pushes in slowly, leaves sway"}, 0) == "zoom_in"
    assert _motion_for_shot({"motion_prompt": "Camera pulls back slowly"}, 0) == "zoom_out"
    assert _motion_for_shot({"motion_prompt": "Camera holds still"}, 0) in ("zoom_in", "zoom_out", "pan_left", "pan_right")

    print(f"Timeline test passed: {len(entries)} subtitle cues, {film_length:.1f}s film")
    return 0


if __name__ == "__main__":
    sys.exit(main())
