"""Trim dead air from the narration and gently tighten it into the 60-90 s budget.

No API calls and no GPU. The Gemini TTS clips contain 0.1-0.9 s of silence at
each end; removing that dead air plus a small speed-up (default target ~86 s)
keeps the dual-voice timeline inside the assignment's runtime. Raw TTS output
is preserved in ``outputs/narration/raw/`` so processing is never applied twice.
"""

import array
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    NARRATION_GAP_SECONDS,
    ROOT_DIR,
    SHOT_PAD_SECONDS,
    load_storyboard,
    narration_clips,
)

NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
RAW_DIR = NARRATION_DIR / "raw"
DURATIONS_PATH = NARRATION_DIR / "durations.json"
MARKER_PATH = NARRATION_DIR / ".retime.json"
TARGET_FILM_SECONDS = float(os.environ.get("TARGET_FILM_SECONDS", "86"))
MAX_SPEED = 1.15
SILENCE_RATIO = 0.025  # 2.5% of each clip's peak
EDGE_MARGIN_SECONDS = 0.02


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _read_wav(path: Path) -> tuple[array.array, int, int, int]:
    """Return (interleaved samples, channels, sample width, frame rate)."""
    import wave

    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise RuntimeError(f"{path.name}: expected 16-bit PCM, got {width * 8}-bit")
    samples = array.array("h")
    samples.frombytes(frames)
    return samples, channels, width, rate


def _write_wav(path: Path, samples: array.array, channels: int, width: int, rate: int) -> None:
    import wave

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


def _deinterleave(samples: array.array, channels: int) -> list[array.array]:
    if channels == 1:
        return [samples]
    out = [array.array("h") for _ in range(channels)]
    out[0].extend(samples[0::channels])
    out[1].extend(samples[1::channels])
    for ch in range(2, channels):
        out[ch].extend(samples[ch::channels])
    return out


def _interleave(channels: list[array.array]) -> array.array:
    if len(channels) == 1:
        return channels[0]
    count = min(len(c) for c in channels)
    out = array.array("h", [0]) * (count * len(channels))
    for i in range(count):
        for ch, data in enumerate(channels):
            out[i * len(channels) + ch] = data[i]
    return out


def _trim(channels: list[array.array], rate: int) -> list[array.array]:
    """Remove leading/trailing silence shared by all channels."""
    peak = max((abs(v) for c in channels for v in c), default=0) or 1
    threshold = peak * SILENCE_RATIO
    first = 0
    for i, _ in enumerate(channels[0]):
        if any(abs(c[i]) > threshold for c in channels):
            first = i
            break
    last = len(channels[0]) - 1
    for i in range(len(channels[0]) - 1, -1, -1):
        if any(abs(c[i]) > threshold for c in channels):
            last = i
            break
    margin = int(EDGE_MARGIN_SECONDS * rate)
    start = max(0, first - margin)
    end = min(len(channels[0]), last + margin + 1)
    return [c[start:end] for c in channels]


def _speed_up(channel: array.array, speed: float) -> array.array:
    """Linear-interpolation resample; speed > 1 shortens without changing format."""
    if abs(speed - 1.0) < 1e-6 or len(channel) < 2:
        return channel
    length = len(channel)
    out_len = max(1, int(length / speed))
    out = array.array("h", [0]) * out_len
    for j in range(out_len):
        pos = j * speed
        i = int(pos)
        frac = pos - i
        if i + 1 < length:
            value = channel[i] * (1.0 - frac) + channel[i + 1] * frac
        else:
            value = channel[i] if i < length else channel[-1]
        out[j] = int(max(-32768, min(32767, value)))
    return out


def _retime_bytes(path: Path, speed: float) -> tuple[bytes, float]:
    samples, channels, width, rate = _read_wav(path)
    trimmed = _trim(_deinterleave(samples, channels), rate)
    parts = [_speed_up(channel, speed) for channel in trimmed]
    result = _interleave(parts)
    seconds = round(len(parts[0]) / float(rate), 3)
    return _build_wav_bytes(result, channels, width, rate), seconds


def _build_wav_bytes(samples: array.array, channels: int, width: int, rate: int) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def _load_marker() -> dict:
    if not MARKER_PATH.exists():
        return {}
    try:
        return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def main() -> int:
    storyboard = load_storyboard()
    clips = [
        (role, filename)
        for shot in storyboard["shots"]
        for role, _line, filename in narration_clips(storyboard, shot)
    ]
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    marker = _load_marker()
    old_hashes = marker.get("retimed_hashes", {})
    sources: dict[str, Path] = {}
    for _role, filename in clips:
        current = NARRATION_DIR / filename
        raw = RAW_DIR / filename
        if not current.exists():
            print(f"Missing narration clip: {current}", file=sys.stderr)
            return 1
        # A changed current file means narration.py wrote a fresh TTS take.
        if not raw.exists() or _digest_file(current) != old_hashes.get(filename):
            shutil.copyfile(current, raw)
        sources[filename] = raw

    # First pass with speed 1 just to measure trimmed speech and derive the
    # smallest speed-up that reaches the target film length.
    trimmed_seconds = 0.0
    for filename, raw in sources.items():
        trimmed_seconds += _retime_bytes(raw, 1.0)[1]

    pads_total = NARRATION_GAP_SECONDS * len(storyboard["shots"]) + SHOT_PAD_SECONDS * len(storyboard["shots"])
    end_card = float(storyboard["end_card"]["duration_seconds"])
    available = TARGET_FILM_SECONDS - pads_total - end_card
    if available <= 0:
        print("TARGET_FILM_SECONDS is too small for the pads and end card.", file=sys.stderr)
        return 1
    speed = min(MAX_SPEED, max(1.0, trimmed_seconds / available))
    film_seconds = trimmed_seconds / speed + pads_total + end_card

    payloads: dict[str, bytes] = {}
    lengths: dict[str, float] = {}
    for filename, raw in sources.items():
        data, seconds = _retime_bytes(raw, speed)
        payloads[filename] = data
        lengths[filename] = seconds

    new_hashes = {fn: _digest_bytes(data) for fn, data in payloads.items()}
    unchanged = (
        marker.get("speed") == round(speed, 4)
        and all(_digest_file(NARRATION_DIR / fn) == h for fn, h in new_hashes.items())
    )
    if unchanged:
        print(f"retime: skipped (already trimmed, speed {speed:.3f}x, ~{film_seconds:.1f}s film)")
        durations = marker.get("durations", {})
        if durations and DURATIONS_PATH.exists():
            DURATIONS_PATH.write_text(
                json.dumps(durations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        return 0

    durations: dict[str, dict] = {}
    for shot in storyboard["shots"]:
        entry: dict[str, float] = {}
        for role, filename in ((r, f) for r, f in clips if f.startswith(shot["id"] + "_")):
            entry[role] = lengths[filename]
            (NARRATION_DIR / filename).write_bytes(payloads[filename])
        entry["total"] = round(
            sum(entry.values())
            + NARRATION_GAP_SECONDS * (len(entry) - 1)
            + SHOT_PAD_SECONDS,
            3,
        )
        durations[shot["id"]] = entry

    DURATIONS_PATH.write_text(
        json.dumps(durations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    MARKER_PATH.write_text(
        json.dumps(
            {
                "speed": round(speed, 4),
                "target_film_seconds": TARGET_FILM_SECONDS,
                "retimed_hashes": new_hashes,
                "durations": durations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"retime: trimmed dead air and tightened {len(clips)} clips by {speed:.3f}x "
        f"-> ~{film_seconds:.1f}s film (raw TTS kept in outputs/narration/raw/)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
