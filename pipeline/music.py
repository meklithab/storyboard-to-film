"""Prepare the score contract from storyboard.json and provide a fallback score.

ACE-Step candidates are still generated in ``notebooks/acestep_music.ipynb``.
When no chosen candidate is available, this stage synthesises a short,
deterministic, originally-generated instrumental from the storyboard's own
music block using only the Python standard library. It is a quiet plucked
krar-like texture with a low drone, tagged in ``runs.jsonl`` as
``procedural-krar-fallback`` so it is never confused with an ACE-Step output.
"""

import array
import json
import math
from pathlib import Path
import random
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import ROOT_DIR, is_cached, load_storyboard, log_run, save_cache

MUSIC_DIR = ROOT_DIR / "outputs" / "music"
CUES_PATH = MUSIC_DIR / "cues.json"
CHOSEN_PATH = MUSIC_DIR / "chosen.wav"
SAMPLE_RATE = 44100
PENTATONIC_HZ = (196.0, 220.0, 246.94, 293.66, 329.63, 392.0, 440.0, 493.88)  # G major pentatonic


def _cue_density(cues: list[dict], t: float) -> float:
    """Note density follows the storyboard's cue notes."""
    for cue in cues:
        if float(cue["start"]) <= t < float(cue["end"]):
            note = cue["note"].lower()
            if "playful" in note:
                return 0.55
            if "warm" in note or "resolv" in note:
                return 0.70
            return 0.45
    return 0.45


def _write_fallback_score(music: dict, out_path: Path) -> None:
    """Write a deterministic, low-volume instrumental WAV from the music block."""
    duration = float(music["duration_seconds"])
    bpm = float(music.get("bpm", 90)) or 90.0
    seed = int(music.get("seed", 42))
    cues = [
        {"start": float(c["start"]), "end": float(c["end"]), "note": c["note"]}
        for c in music.get("cues", [])
    ]
    rng = random.Random(seed)
    total = int(duration * SAMPLE_RATE)
    samples = array.array("h", [0]) * total
    beat = 60.0 / bpm

    # A very quiet low drone keeps the bed continuous under narration.
    for i in range(total):
        t = i / SAMPLE_RATE
        samples[i] = int(0.018 * 32767 * math.sin(2 * math.pi * 98.0 * t))

    # Plucked notes on a pentatonic scale, one idea every half beat.
    step = beat / 2.0
    t = 0.0
    while t < duration - 0.2:
        if rng.random() < _cue_density(cues, t):
            freq = rng.choice(PENTATONIC_HZ)
            note_len = min(0.75, max(0.25, beat * rng.uniform(0.7, 1.4)))
            amp = 0.10 * rng.uniform(0.7, 1.0)
            start = int(t * SAMPLE_RATE)
            length = int(note_len * SAMPLE_RATE)
            attack = max(1, int(0.02 * SAMPLE_RATE))
            for j in range(length):
                pos = start + j
                if pos >= total:
                    break
                env = min(1.0, j / attack) * math.exp(-3.5 * j / length)
                phase = 2 * math.pi * freq * j / SAMPLE_RATE
                tone = math.sin(phase) + 0.25 * math.sin(2 * phase)
                samples[pos] = max(
                    -32768, min(32767, samples[pos] + int(amp * 32767 * env * tone))
                )
        t += step

    peak = max(1, max(abs(v) for v in samples))
    scale = 0.30 * 32767 / peak
    if scale < 1.0:
        for i in range(total):
            samples[i] = int(samples[i] * scale)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.tobytes())


def main() -> int:
    storyboard = load_storyboard()
    music = storyboard["music"]
    duration = float(music["duration_seconds"])
    cues = [
        {"start": float(c["start"]), "end": float(c["end"]), "note": c["note"]}
        for c in music.get("cues", [])
    ]

    invalid = [c for c in cues if c["start"] < 0 or c["end"] <= c["start"] or c["end"] > duration]
    if invalid:
        print("Invalid music cues (outside 0..duration or reversed):", file=sys.stderr)
        for cue in invalid:
            print(f"  {cue}", file=sys.stderr)
        return 1

    payload = {
        "caption": music["caption"],
        "instrumental": bool(music["instrumental"]),
        "bpm": music["bpm"],
        "key": music["key"],
        "duration_seconds": duration,
        "seed": music["seed"],
        "cues": cues,
    }
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    if not is_cached("music", "cues", payload, CUES_PATH):
        CUES_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        save_cache("music", "cues", payload)
        print(f"Wrote {len(cues)} music cues to {CUES_PATH}")

    if CHOSEN_PATH.exists() and CHOSEN_PATH.stat().st_size > 0:
        print(f"Score ready: {CHOSEN_PATH}")
        return 0

    score_payload = dict(payload, generator="procedural-krar-fallback-v1")
    if not is_cached("music", "score", score_payload, CHOSEN_PATH):
        t0 = time.perf_counter()
        _write_fallback_score(music, CHOSEN_PATH)
        log_run(
            "music",
            "procedural-krar-fallback",
            score_payload,
            seed=int(music.get("seed", 42)),
            latency_seconds=time.perf_counter() - t0,
            success=True,
        )
        save_cache("music", "score", score_payload)
        print(
            f"Generated fallback score -> {CHOSEN_PATH.name} "
            f"({duration:.0f}s, seed {music.get('seed', 42)}, no GPU needed)"
        )
    else:
        print(f"Score cached: {CHOSEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
