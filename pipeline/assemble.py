"""Assemble shots, narration, intro, music, subtitles, end card, and two true-format finals."""

import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CACHE_DIR,
    ROOT_DIR,
    ffmpeg_bin,
    intro_seconds,
    is_cached,
    load_storyboard,
    narration_clips,
    narration_pads,
    save_cache,
)

SHOTS_DIR = ROOT_DIR / "outputs" / "shots"
NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
DURATIONS_PATH = NARRATION_DIR / "durations.json"
SUBTITLES_PATH = ROOT_DIR / "outputs" / "subtitles" / "subtitles.srt"
MUSIC_PATH = ROOT_DIR / "outputs" / "music" / "chosen.wav"
FINAL_DIR = ROOT_DIR / "outputs" / "final"


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_ffmpeg(step_name: str, cmd: list[str]) -> None:
    print(f"[{step_name}] {shlex.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT_DIR, check=True)


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def find_font() -> str:
    """Return a real TTF path for drawtext; ffmpeg cannot render text without one."""
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    for font in candidates:
        if font.is_file():
            # Filtergraph escaping: wrap the value in quotes and escape the drive colon.
            return "'" + font.as_posix().replace(":", "\\:") + "'"
    raise RuntimeError("No TrueType font found for text cards (tried arial.ttf / DejaVuSans.ttf).")


def _intro_filter(font: str, title: str, description: str, vertical: bool) -> str:
    """Draw a wrapped title card; drawtext itself does not wrap long lines."""
    title_size = 42 if vertical else 54
    desc_size = 24 if vertical else 30
    # Keep the whole sentence; a 720 px card needs three short lines, while a
    # 1280 px card fits two. Never drop the tail with a hard [:2] slice.
    lines = textwrap.wrap(description, width=34 if vertical else 52) or [description]

    parts = [
        f"drawtext=fontfile={font}:text='{_escape_drawtext(title)}':"
        f"fontcolor=white:fontsize={title_size}:x=(w-text_w)/2:y=h/2-72"
    ]
    base_offset = 10 if vertical else 30
    for idx, line in enumerate(lines[:3]):
        y_offset = base_offset + idx * (desc_size + 12)
        parts.append(
            f"drawtext=fontfile={font}:text='{_escape_drawtext(line)}':"
            f"fontcolor=0xF2D8B5:fontsize={desc_size}:"
            f"x=(w-text_w)/2:y=h/2+{y_offset}"
        )
    return ",".join(parts)


def _build_intro(
    ffmpeg: str,
    intro: dict,
    font: str,
    w: int,
    h: int,
    fps: int,
    vertical: bool,
    out_path: Path,
) -> None:
    duration = float(intro["duration_seconds"])
    vf = _intro_filter(
        font,
        str(intro["title"]),
        str(intro["description"]),
        vertical,
    )
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=0x2A1810:s={w}x{h}:r={fps}:d={duration}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration}",
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run_ffmpeg("step_b_intro_card", cmd)


def _build_format(
    ffmpeg: str,
    storyboard: dict,
    shots: list[dict],
    narr_clips: list[Path],
    narr_pads: list[float],
    durations: dict,
    has_music: bool,
    fmt_name: str,
    suffix: str,
    w: int,
    h: int,
    fps: int,
    font: str,
    out_path: Path,
) -> int:
    shot_clips = [SHOTS_DIR / f"{s['id']}{suffix}.mp4" for s in shots]
    missing = [str(p) for p in shot_clips if not p.exists()]
    if missing:
        print(f"Missing {fmt_name} shot clips (run pipeline/shots.py first):", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    intro = storyboard["intro"]
    end_card = storyboard["end_card"]
    n = len(shots)

    cache_payload = {
        "assembler_version": 2,
        "format": fmt_name,
        "clips": [_file_digest(p) for p in shot_clips],
        "narration": [_file_digest(p) for p in narr_clips],
        "narration_pads": narr_pads,
        "durations": durations,
        "subtitles": _file_digest(SUBTITLES_PATH),
        "music": _file_digest(MUSIC_PATH) if has_music else None,
        "intro": intro,
        "end_card": end_card,
        "width": w,
        "height": h,
        "fps": fps,
    }
    if is_cached("assemble", fmt_name, cache_payload, out_path):
        return 0

    body_av = CACHE_DIR / f"assemble_{fmt_name}_body.mp4"
    intro_av = CACHE_DIR / f"assemble_{fmt_name}_intro.mp4"
    with_intro_av = CACHE_DIR / f"assemble_{fmt_name}_with_intro.mp4"
    music_av = CACHE_DIR / f"assemble_{fmt_name}_music.mp4"
    subbed_av = CACHE_DIR / f"assemble_{fmt_name}_subbed.mp4"
    with_end_av = CACHE_DIR / f"assemble_{fmt_name}_with_end.mp4"

    # a: Join this format's clips and place both spoken lines at each shot's start.
    cmd_join = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    for p in shot_clips:
        cmd_join.extend(["-i", str(p)])
    for p in narr_clips:
        cmd_join.extend(["-i", str(p)])

    v_in = "".join(f"[{i}:v]" for i in range(n))
    a_filters = []
    a_labels = []
    for i, pad in enumerate(narr_pads):
        a_filters.append(
            f"[{n + i}:a]aresample=44100,aformat=channel_layouts=stereo,apad=pad_dur={pad:.3f}[a{i}]"
        )
        a_labels.append(f"[a{i}]")
    fc_join = (
        f"{v_in}concat=n={n}:v=1:a=0[vout];"
        + ";".join(a_filters)
        + f";{''.join(a_labels)}concat=n={len(narr_clips)}:v=0:a=1[aout]"
    )
    cmd_join.extend([
        "-filter_complex", fc_join,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(body_av),
    ])
    _run_ffmpeg(f"{fmt_name}_step_a_join_clips_and_narration", cmd_join)

    # b: Build the story intro in the same format, then prepend it to the body.
    _build_intro(ffmpeg, intro, font, w, h, fps, fmt_name == "vertical", intro_av)
    fc_pre = (
        "[0:v]setsar=1[iv];[1:v]setsar=1[bv];"
        "[0:a]asetpts=PTS-STARTPTS[ia];[1:a]asetpts=PTS-STARTPTS[ba];"
        "[iv][ia][bv][ba]concat=n=2:v=1:a=1[vout][aout]"
    )
    cmd_pre = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(intro_av),
        "-i", str(body_av),
        "-filter_complex", fc_pre,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(with_intro_av),
    ]
    _run_ffmpeg(f"{fmt_name}_step_c_prepend_intro", cmd_pre)

    # d: Mix optional music with sidechain compression under narration.
    current_av = with_intro_av
    if has_music:
        fc_music = (
            "[0:a]asplit=2[narr][narr_sc];"
            "[1:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.4[mus];"
            "[mus][narr_sc]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked];"
            "[narr][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        cmd_music = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(with_intro_av),
            "-stream_loop", "-1", "-i", str(MUSIC_PATH),
            "-filter_complex", fc_music,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(music_av),
        ]
        _run_ffmpeg(f"{fmt_name}_step_d_music_sidechain", cmd_music)
        current_av = music_av
    else:
        print(f"Warning: {MUSIC_PATH} not found; continuing without music.")

    # e: Burn English subtitles. The SRT already includes the intro offset.
    sub_rel = SUBTITLES_PATH.relative_to(ROOT_DIR).as_posix()
    if fmt_name == "vertical":
        sub_style = (
            "Alignment=2,MarginV=220,MarginL=50,MarginR=50,"
            "FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1"
        )
    else:
        sub_style = (
            "Alignment=2,MarginV=60,MarginL=80,MarginR=80,"
            "FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1"
        )
    cmd_sub = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(current_av),
        "-vf", f"subtitles='{sub_rel}':force_style='{sub_style}'",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "copy",
        str(subbed_av),
    ]
    _run_ffmpeg(f"{fmt_name}_step_e_burn_subtitles", cmd_sub)

    # f: Append the AI-disclosure end card in this format's true dimensions.
    end_text = _escape_drawtext(str(end_card["text"]))
    end_dur = float(end_card["duration_seconds"])
    end_size = 42 if fmt_name == "vertical" else 52
    fc_end = (
        f"[0:v]setsar=1[v0];"
        f"[1:v]drawtext=fontfile={font}:text='{end_text}':fontcolor=white:fontsize={end_size}:"
        "x=(w-text_w)/2:y=(h-text_h)/2,setsar=1[endv];"
        "[v0][0:a][endv][2:a]concat=n=2:v=1:a=1[vout][aout]"
    )
    cmd_end = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(subbed_av),
        "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={end_dur}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={end_dur}",
        "-filter_complex", fc_end,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(with_end_av),
    ]
    _run_ffmpeg(f"{fmt_name}_step_f_end_card", cmd_end)

    # g: Normalize loudness and write the final file.
    cmd_final = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(with_end_av),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(f"{fmt_name}_step_g_export", cmd_final)

    save_cache("assemble", fmt_name, cache_payload)
    print(f"Exported {out_path}")
    return 0


def main() -> int:
    try:
        ffmpeg = ffmpeg_bin()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    try:
        font = find_font()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    storyboard = load_storyboard()
    shots = storyboard["shots"]
    if not DURATIONS_PATH.exists():
        print(f"Missing {DURATIONS_PATH}", file=sys.stderr)
        return 1
    if not SUBTITLES_PATH.exists():
        print(f"Missing {SUBTITLES_PATH}", file=sys.stderr)
        return 1
    if "intro" not in storyboard:
        print("Missing intro block in storyboard.json", file=sys.stderr)
        return 1

    durations = json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))

    # Two audio clips per shot: narrator first, then the grandmother's proverb.
    narr_clips: list[Path] = []
    narr_pads: list[float] = []
    for shot in shots:
        lines = narration_clips(storyboard, shot)
        for (_role, _line, filename), pad in zip(lines, narration_pads(lines)):
            narr_clips.append(NARRATION_DIR / filename)
            narr_pads.append(pad)

    missing_narration = [str(p) for p in narr_clips if not p.exists()]
    if missing_narration:
        print("Missing narration inputs for assembly:", file=sys.stderr)
        for m in missing_narration:
            print(f"  - {m}", file=sys.stderr)
        return 1

    fmt = storyboard.get("format", {})
    v_dim = fmt.get("vertical", {})
    h_dim = fmt.get("horizontal", {})
    vw, vh = int(v_dim.get("width", 720)), int(v_dim.get("height", 1280))
    hw, hh = int(h_dim.get("width", 1280)), int(h_dim.get("height", 720))
    fps = int(fmt.get("fps", 24))
    has_music = MUSIC_PATH.exists()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    configs = (
        ("vertical", "", vw, vh, FINAL_DIR / "film_vertical.mp4"),
        ("horizontal", "_wide", hw, hh, FINAL_DIR / "film_horizontal.mp4"),
    )
    for fmt_name, suffix, w, h, out_path in configs:
        rc = _build_format(
            ffmpeg, storyboard, shots, narr_clips, narr_pads, durations, has_music,
            fmt_name, suffix, w, h, fps, font, out_path,
        )
        if rc:
            return rc

    print(f"Exported both finals ({intro_seconds(storyboard):.1f}s intro included)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
