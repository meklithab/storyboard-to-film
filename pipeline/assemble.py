"""Assemble shots, narration, optional ducked music, subtitles, end card, and loudness-normalized finals."""

import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import CACHE_DIR, ROOT_DIR, is_cached, load_storyboard, save_cache

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


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("Error: ffmpeg not found on PATH.", file=sys.stderr)
        return 1

    storyboard = load_storyboard()
    shots = storyboard["shots"]
    if not DURATIONS_PATH.exists():
        print(f"Missing {DURATIONS_PATH}", file=sys.stderr)
        return 1
    if not SUBTITLES_PATH.exists():
        print(f"Missing {SUBTITLES_PATH}", file=sys.stderr)
        return 1

    durations = json.loads(DURATIONS_PATH.read_text(encoding="utf-8"))
    shot_clips = [SHOTS_DIR / f"{s['id']}.mp4" for s in shots]
    narr_clips = [NARRATION_DIR / f"{s['id']}.wav" for s in shots]

    missing = [str(p) for p in shot_clips + narr_clips if not p.exists()]
    if missing:
        print("Missing inputs for assembly:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    fmt = storyboard.get("format", {})
    v_dim = fmt.get("vertical", {})
    h_dim = fmt.get("horizontal", {})
    vw, vh = int(v_dim.get("width", 720)), int(v_dim.get("height", 1280))
    hw, hh = int(h_dim.get("width", 1280)), int(h_dim.get("height", 720))
    fps = int(fmt.get("fps", 24))

    end_card = storyboard["end_card"]
    end_text = str(end_card["text"])
    end_dur = float(end_card["duration_seconds"])
    has_music = MUSIC_PATH.exists()

    out_vertical = FINAL_DIR / "film_vertical.mp4"
    out_horizontal = FINAL_DIR / "film_horizontal.mp4"

    cache_payload = {
        "clips": [_file_digest(p) for p in shot_clips],
        "narration": [_file_digest(p) for p in narr_clips],
        "subtitles": _file_digest(SUBTITLES_PATH),
        "music": _file_digest(MUSIC_PATH) if has_music else None,
        "end_card": end_card,
        "format": fmt,
    }
    if is_cached("assemble", "vertical", cache_payload, out_vertical) and out_horizontal.exists():
        print("assemble: skipped (cached)")
        return 0

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    body_av = CACHE_DIR / "assemble_body.mp4"
    music_av = CACHE_DIR / "assemble_music.mp4"
    subbed_av = CACHE_DIR / "assemble_subbed.mp4"
    with_end_av = CACHE_DIR / "assemble_endcard.mp4"

    # a & b: Join clips in order and align each narration line to the start of its shot
    n = len(shots)
    cmd_join = ["ffmpeg", "-y"]
    for p in shot_clips:
        cmd_join.extend(["-i", str(p)])
    for p in narr_clips:
        cmd_join.extend(["-i", str(p)])

    v_in = "".join(f"[{i}:v]" for i in range(n))
    a_filters = []
    a_labels = []
    for i, shot in enumerate(shots):
        shot_len = float(durations[shot["id"]]) + 0.5
        a_filters.append(
            f"[{n + i}:a]aresample=44100,aformat=channel_layouts=stereo,apad=whole_dur={shot_len:.3f}[a{i}]"
        )
        a_labels.append(f"[a{i}]")
    fc_join = f"{v_in}concat=n={n}:v=1:a=0[vout];" + ";".join(a_filters) + f";{''.join(a_labels)}concat=n={n}:v=0:a=1[aout]"
    cmd_join.extend([
        "-filter_complex", fc_join,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(body_av),
    ])
    _run_ffmpeg("step_ab_join_clips_and_narration", cmd_join)

    # c: Mix optional music with sidechain compression under narration
    current_av = body_av
    if has_music:
        fc_music = (
            "[0:a]asplit=2[narr][narr_sc];"
            "[1:a]aresample=44100,aformat=channel_layouts=stereo,volume=0.4[mus];"
            "[mus][narr_sc]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked];"
            "[narr][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        cmd_music = [
            "ffmpeg", "-y",
            "-i", str(body_av),
            "-stream_loop", "-1", "-i", str(MUSIC_PATH),
            "-filter_complex", fc_music,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            str(music_av),
        ]
        _run_ffmpeg("step_c_music_sidechain", cmd_music)
        current_av = music_av
    else:
        print("Warning: outputs/music/chosen.wav not found; continuing without music.")

    # d: Burn in English subtitles inside vertical safe area
    sub_rel = SUBTITLES_PATH.relative_to(ROOT_DIR).as_posix()
    sub_style = (
        "Alignment=2,MarginV=220,MarginL=50,MarginR=50,"
        "FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=1"
    )
    cmd_sub = [
        "ffmpeg", "-y",
        "-i", str(current_av),
        "-vf", f"subtitles='{sub_rel}':force_style='{sub_style}'",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "copy",
        str(subbed_av),
    ]
    _run_ffmpeg("step_d_burn_subtitles", cmd_sub)

    # e: Append 3-second end card with storyboard text
    escaped_text = _escape_drawtext(end_text)
    fc_end = (
        f"[0:v]setsar=1[v0];"
        f"[1:v]drawtext=text='{escaped_text}':fontcolor=white:fontsize=42:"
        "x=(w-text_w)/2:y=(h-text_h)/2,setsar=1[endv];"
        "[v0][0:a][endv][2:a]concat=n=2:v=1:a=1[vout][aout]"
    )
    cmd_end = [
        "ffmpeg", "-y",
        "-i", str(subbed_av),
        "-f", "lavfi", "-i", f"color=c=black:s={vw}x{vh}:r={fps}:d={end_dur}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={end_dur}",
        "-filter_complex", fc_end,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        str(with_end_av),
    ]
    _run_ffmpeg("step_e_end_card", cmd_end)

    # f & g: Normalize loudness (-14 LUFS, TP -1 dB) and export vertical + horizontal finals
    cmd_vert = [
        "ffmpeg", "-y",
        "-i", str(with_end_av),
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_vertical),
    ]
    _run_ffmpeg("step_fg_export_vertical", cmd_vert)

    fc_horiz = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={hw}:{hh}:force_original_aspect_ratio=increase,crop={hw}:{hh},"
        "boxblur=20:5,eq=brightness=-0.25[bg_blur];"
        f"[fg]scale=-2:{hh}[fg_s];"
        "[bg_blur][fg_s]overlay=(W-w)/2:(H-h)/2[vout]"
    )
    cmd_horiz = [
        "ffmpeg", "-y",
        "-i", str(out_vertical),
        "-filter_complex", fc_horiz,
        "-map", "[vout]", "-map", "0:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-movflags", "+faststart",
        str(out_horizontal),
    ]
    _run_ffmpeg("step_g_export_horizontal", cmd_horiz)

    save_cache("assemble", "vertical", cache_payload)
    print(f"Exported {out_vertical} and {out_horizontal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
