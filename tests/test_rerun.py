"""Test that editing one shot's image_prompt regenerates only that shot and final assembly."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
STORYBOARD_PATH = ROOT_DIR / "storyboard.json"
KEYFRAMES_DIR = ROOT_DIR / "outputs" / "keyframes"
SHOTS_DIR = ROOT_DIR / "outputs" / "shots"
FINAL_DIR = ROOT_DIR / "outputs" / "final"
STAGES = ("validate", "narration", "keyframes", "shots", "subtitles", "assemble")


def _run_film() -> str:
    """Run `make film` (or stage scripts directly if `make` is unavailable)."""
    if shutil.which("make"):
        res = subprocess.run(
            ["make", "film", f"PYTHON={sys.executable}"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"`make film` failed:\n{res.stdout}\n{res.stderr}")
        return res.stdout

    outputs = []
    for stage in STAGES:
        res = subprocess.run(
            [sys.executable, f"pipeline/{stage}.py"],
            cwd=ROOT_DIR,
            text=True,
            capture_output=True,
        )
        outputs.append(res.stdout)
        if res.returncode != 0:
            raise RuntimeError(f"pipeline/{stage}.py failed:\n{res.stdout}\n{res.stderr}")
    return "\n".join(outputs)


def _snapshot_mtimes(shot_ids: list[str]) -> dict[str, int]:
    files = {f"keyframe:{sid}": KEYFRAMES_DIR / f"{sid}.jpg" for sid in shot_ids}
    files.update({f"shot:{sid}": SHOTS_DIR / f"{sid}.mp4" for sid in shot_ids})
    files["final:vertical"] = FINAL_DIR / "film_vertical.mp4"
    files["final:horizontal"] = FINAL_DIR / "film_horizontal.mp4"
    return {k: (p.stat().st_mtime_ns if p.exists() else 0) for k, p in files.items()}


def main() -> int:
    original_text = STORYBOARD_PATH.read_text(encoding="utf-8")
    storyboard = json.loads(original_text)
    shot_ids = [s["id"] for s in storyboard["shots"]]
    target_id = shot_ids[0]

    try:
        print("1) Running initial `make film`...")
        _run_film()
        before = _snapshot_mtimes(shot_ids)

        time.sleep(0.05)
        storyboard["shots"][0]["image_prompt"] += ", warm morning mist"
        STORYBOARD_PATH.write_text(
            json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(f"2) Modified image_prompt of {target_id}; re-running `make film`...")
        _run_film()
        after = _snapshot_mtimes(shot_ids)

        print("\nRerun summary:")
        regenerated_shots = []
        skipped_shots = []
        for sid in shot_ids:
            kf_changed = after[f"keyframe:{sid}"] != before[f"keyframe:{sid}"]
            sh_changed = after[f"shot:{sid}"] != before[f"shot:{sid}"]
            if kf_changed or sh_changed:
                regenerated_shots.append(sid)
                print(f"  {sid}: REGENERATED (keyframe={kf_changed}, shot={sh_changed})")
            else:
                skipped_shots.append(sid)
                print(f"  {sid}: skipped (cached)")

        final_changed = (
            after["final:vertical"] != before["final:vertical"]
            and after["final:horizontal"] != before["final:horizontal"]
        )
        print(f"  final assembly: {'REGENERATED' if final_changed else 'SKIPPED'}")

        assert regenerated_shots == [target_id], f"Expected only [{target_id}], got {regenerated_shots}"
        assert len(skipped_shots) == len(shot_ids) - 1
        assert final_changed, "Expected final assembly to regenerate"
        print("\nRerun test passed.")
        return 0
    finally:
        STORYBOARD_PATH.write_text(original_text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
