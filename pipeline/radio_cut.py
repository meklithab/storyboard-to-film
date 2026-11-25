"""Assemble narration audio clips in order over a black screen into radio_cut.mp4."""

from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT_DIR, load_storyboard

NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
MUSIC_PATH = ROOT_DIR / "outputs" / "music" / "temp.wav"
OUTPUT_PATH = ROOT_DIR / "outputs" / "final" / "radio_cut.mp4"
PAUSE_SECONDS = 0.5


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg not found on PATH.", file=sys.stderr)
        return 1

    storyboard = load_storyboard()
    shots = storyboard["shots"]
    audio_files = [NARRATION_DIR / f"{shot['id']}.wav" for shot in shots]

    missing = [str(p) for p in audio_files if not p.exists()]
    if missing:
        print("Missing narration files (run pipeline/narration.py first):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    fmt = storyboard.get("format", {})
    vertical = fmt.get("vertical", {})
    width = vertical.get("width", 720)
    height = vertical.get("height", 1280)
    fps = fmt.get("fps", 24)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}"]
    for path in audio_files:
        cmd.extend(["-i", str(path)])

    has_music = MUSIC_PATH.exists()
    if has_music:
        cmd.extend(["-stream_loop", "-1", "-i", str(MUSIC_PATH)])

    # Normalize sample rate/channels and pad short pauses between shots
    filters = []
    concat_labels = []
    n = len(audio_files)
    for i in range(n):
        in_idx = i + 1
        label = f"a{i}"
        pad = f",apad=pad_dur={PAUSE_SECONDS}" if i < n - 1 else ""
        filters.append(f"[{in_idx}:a]aresample=44100,aformat=channel_layouts=stereo{pad}[{label}]")
        concat_labels.append(f"[{label}]")

    filters.append(f"{''.join(concat_labels)}concat=n={n}:v=0:a=1[narr]")

    if has_music:
        music_idx = n + 1
        filters.append(
            f"[{music_idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.15[mus];"
            "[narr][mus]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_map = "[aout]"
    else:
        audio_map = "[narr]"

    cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", "0:v",
        "-map", audio_map,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(OUTPUT_PATH),
    ])

    subprocess.run(cmd, check=True)
    print(f"Exported {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
