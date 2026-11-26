"""Assemble both spoken lines of every shot over a black screen into a radio cut.

This is the cheap, pre-picture prototype: narrator line, pause, grandmother
proverb, then a short tail before the next shot.
"""

from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT_DIR, ffmpeg_bin, load_storyboard, narration_clips, narration_pads

NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
MUSIC_PATH = ROOT_DIR / "outputs" / "music" / "temp.wav"
OUTPUT_PATH = ROOT_DIR / "outputs" / "final" / "radio_cut.mp4"


def main() -> int:
    try:
        ffmpeg = ffmpeg_bin()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    storyboard = load_storyboard()
    shots = storyboard["shots"]

    clips: list[tuple[Path, float]] = []
    for shot in shots:
        lines = narration_clips(storyboard, shot)
        for (_role, _line, filename), pad in zip(lines, narration_pads(lines)):
            clips.append((NARRATION_DIR / filename, pad))

    missing = [str(p) for p, _ in clips if not p.exists()]
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

    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={fps}",
    ]
    for path, _pad in clips:
        cmd.extend(["-i", str(path)])

    has_music = MUSIC_PATH.exists()
    if has_music:
        cmd.extend(["-stream_loop", "-1", "-i", str(MUSIC_PATH)])

    filters = []
    labels = []
    for idx, (_path, pad) in enumerate(clips):
        label = f"a{idx}"
        filters.append(
            f"[{idx + 1}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"apad=pad_dur={pad:.3f}[{label}]"
        )
        labels.append(f"[{label}]")

    filters.append(f"{''.join(labels)}concat=n={len(clips)}:v=0:a=1[narr]")

    if has_music:
        music_idx = len(clips) + 1
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
    print(f"Exported {OUTPUT_PATH} ({len(clips)} spoken lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
