"""Create per-shot animated clips from keyframes using slow pan/zoom in FFmpeg."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT_DIR, compute_hash, is_cached, load_storyboard, save_cache

KEYFRAMES_DIR = ROOT_DIR / "outputs" / "keyframes"
DURATIONS_PATH = ROOT_DIR / "outputs" / "narration" / "durations.json"
SHOTS_DIR = ROOT_DIR / "outputs" / "shots"
MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right")


def _file_digest(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_keyframe(shot_id: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = KEYFRAMES_DIR / f"{shot_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def _zoompan_filter(motion: str, total_frames: int, width: int, height: int, fps: int) -> str:
    """Build an upscale + centred zoompan filter for smooth 24 fps motion."""
    up_w, up_h = width * 3, height * 3
    pre = f"scale={up_w}:{up_h}:force_original_aspect_ratio=increase,crop={up_w}:{up_h}"
    n = max(1, total_frames)

    if motion == "zoom_in":
        z = f"min(1+0.12*on/{n},1.12)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "zoom_out":
        z = f"max(1.12-0.12*on/{n},1.0)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_left":
        z = "1.10"
        x = f"(iw-iw/zoom)*(0.65-0.30*on/{n})"
        y = "ih/2-(ih/zoom/2)"
    else:  # pan_right
        z = "1.10"
        x = f"(iw-iw/zoom)*(0.35+0.30*on/{n})"
        y = "ih/2-(ih/zoom/2)"

    return f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={width}x{height}:fps={fps},setsar=1"


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg not found on PATH.", file=sys.stderr)
        return 1

    if not DURATIONS_PATH.exists():
        print(f"Missing {DURATIONS_PATH} (run pipeline/narration.py first).", file=sys.stderr)
        return 1

    durations = json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))
    storyboard = load_storyboard()
    fmt = storyboard.get("format", {})
    vertical = fmt.get("vertical", {})
    width = int(vertical.get("width", 720))
    height = int(vertical.get("height", 1280))
    fps = int(fmt.get("fps", 24))

    SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    for idx, shot in enumerate(storyboard["shots"]):
        sid = shot["id"]
        if sid not in durations:
            print(f"Error: '{sid}' missing from {DURATIONS_PATH}", file=sys.stderr)
            return 1

        duration = round(float(durations[sid]) + 0.5, 3)
        total_frames = max(1, round(duration * fps))
        motion = MOTIONS[idx % len(MOTIONS)]
        out_path = SHOTS_DIR / f"{sid}.mp4"
        wan_path = SHOTS_DIR / f"{sid}_wan.mp4"

        if wan_path.exists():
            source_kind = "wan"
            source_path = wan_path
        else:
            source_kind = "keyframe"
            source_path = _find_keyframe(sid)
            if source_path is None:
                print(f"Missing keyframe for '{sid}' in {KEYFRAMES_DIR}", file=sys.stderr)
                return 1

        payload = {
            "shot_id": sid,
            "source_kind": source_kind,
            "source_hash": _file_digest(source_path),
            "duration": duration,
            "motion": motion,
            "width": width,
            "height": height,
            "fps": fps,
        }

        if is_cached("shots", sid, payload, out_path):
            continue

        if source_kind == "wan":
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps={fps},setsar=1"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", str(source_path),
                "-vf", vf,
                "-t", f"{duration:.3f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                str(out_path),
            ]
        else:
            vf = _zoompan_filter(motion, total_frames, width, height, fps)
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", str(source_path),
                "-vf", vf,
                "-t", f"{duration:.3f}",
                "-r", str(fps),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
                str(out_path),
            ]

        subprocess.run(cmd, check=True)
        save_cache("shots", sid, payload)
        print(f"{sid}: rendered ({source_kind}, {motion}, {duration:.2f}s) -> {out_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
