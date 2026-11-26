"""Generate per-shot Amharic narration with the two voices defined in storyboard.json.

Every shot has two spoken lines: the grandchild narrator sets up the situation,
then ``proverb.speaker`` (grandmother) delivers the proverb. Each line is saved
as its own WAV so a re-take of one line only regenerates that call.

The Gemini free tier allows only 3 TTS requests per minute. This stage paces
calls, honours the `retryDelay` returned with 429s, and keeps already-cached
lines, so an interrupted run simply resumes from the next missing line.
"""

import json
import os
from pathlib import Path
import re
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    CACHE_DIR,
    DEFAULT_VOICE_FALLBACKS,
    NARRATION_GAP_SECONDS,
    ROOT_DIR,
    SHOT_PAD_SECONDS,
    get_env,
    is_cached,
    load_env,
    load_storyboard,
    log_run,
    narration_clips,
    save_audio_wav,
    save_cache,
)

TTS_MODEL = "gemini-3.8-flash-tts"
NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
DURATIONS_PATH = NARRATION_DIR / "durations.json"
VOICES_PATH = NARRATION_DIR / "voices_used.json"
RATE_STATE_PATH = CACHE_DIR / "tts_last_call.txt"
DEFAULT_MIN_INTERVAL_SECONDS = 21.0  # 3 requests/minute + 1 s margin
MAX_QUOTA_WAITS = 4


def _min_interval() -> float:
    try:
        return max(0.0, float(os.environ.get("GEMINI_TTS_MIN_INTERVAL_SECONDS", DEFAULT_MIN_INTERVAL_SECONDS)))
    except ValueError:
        return DEFAULT_MIN_INTERVAL_SECONDS


def _wait_for_slot() -> None:
    """Space TTS calls so the free-tier RPM quota is not exceeded."""
    interval = _min_interval()
    if interval <= 0:
        return
    last: float | None = None
    if RATE_STATE_PATH.exists():
        try:
            last = float(RATE_STATE_PATH.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            last = None
    if last is not None:
        wait = interval - (time.time() - last)
        if wait > 0.5:
            print(f"  rate limit: waiting {wait:.1f}s before the next TTS call")
            time.sleep(wait)
    RATE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RATE_STATE_PATH.write_text(str(time.time()), encoding="utf-8")


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "429" in text
        or "resource_exhausted" in text
        or "quota exceeded" in text
        or "free_tier_requests" in text
    )


def _retry_delay_seconds(exc: Exception) -> float:
    """Read the retryDelay Google includes in 429 error details."""
    text = str(exc)
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s", text)
    if not match:
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", text, re.IGNORECASE)
    return float(match.group(1)) if match else 25.0


def _voice_candidates(storyboard: dict, role: str) -> list[str]:
    """Configured voice first, then known-good fallbacks for this API."""
    configured = storyboard.get("voices", {}).get(role, {}).get("voice", "Kore")
    candidates = [configured]
    for voice in DEFAULT_VOICE_FALLBACKS:
        if voice not in candidates:
            candidates.append(voice)
    return candidates


def _synthesize(
    client,
    storyboard: dict,
    shot: dict,
    role: str,
    line: dict,
    out_path: Path,
) -> str:
    """Synthesize one spoken line; return the voice name that actually worked."""
    from google.genai import types

    text = line["text"]
    style = line["style"]
    language = storyboard.get("language", "am")
    prompt = f"Speak in {language} in this style ({style}):\n{text}"
    params = {
        "shot_id": shot["id"],
        "role": role,
        "style": style,
        "text": text,
        "language": language,
    }
    errors: list[str] = []
    candidates = _voice_candidates(storyboard, role)
    quota_waits = 0

    for voice_name in candidates:
        params["voice_name"] = voice_name
        attempts = 0

        while attempts < 6:
            attempts += 1
            _wait_for_slot()
            t0 = time.perf_counter()
            try:
                resp = client.models.generate_content(
                    model=TTS_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice_name
                                )
                            )
                        ),
                    ),
                )
                for cand in resp.candidates or []:
                    for part in cand.content.parts or []:
                        if part.inline_data and part.inline_data.data:
                            save_audio_wav(
                                out_path, part.inline_data.data, part.inline_data.mime_type or ""
                            )
                            log_run(
                                "narration",
                                TTS_MODEL,
                                params,
                                seed=shot.get("seed"),
                                latency_seconds=time.perf_counter() - t0,
                                success=True,
                            )
                            return voice_name
                raise RuntimeError(f"No audio returned for {shot['id']}/{role}")
            except Exception as exc:
                log_run(
                    "narration",
                    TTS_MODEL,
                    params,
                    seed=shot.get("seed"),
                    latency_seconds=time.perf_counter() - t0,
                    success=False,
                    error=str(exc),
                )

                if _is_quota_error(exc):
                    quota_waits += 1
                    if quota_waits > MAX_QUOTA_WAITS:
                        raise RuntimeError(
                            f"TTS quota exhausted at {shot['id']}/{role} after "
                            f"{quota_waits} rate-limit waits. Cached lines are safe; "
                            "just rerun `make narration` later."
                        ) from exc
                    delay = _retry_delay_seconds(exc) + 2.0
                    print(
                        f"  {shot['id']}/{role}: rate limited, waiting {delay:.0f}s "
                        f"(free tier allows {int(60 / _min_interval()) if _min_interval() else 3} calls/min)"
                    )
                    time.sleep(delay)
                    continue

                # A rejected voice name is retryable once with a short backoff;
                # then try the next configured fallback voice.
                if voice_name == candidates[0] and attempts < 3:
                    time.sleep(1.5)
                    continue
                errors.append(f"{voice_name}: {exc}")
                break

    raise RuntimeError(f"TTS failed for {shot['id']}/{role}: " + " | ".join(errors))


def _measure_wav_seconds(wav_path: Path) -> float:
    """Return real WAV audio duration in seconds."""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return round(frames / float(rate), 3)


def _load_voices_used() -> dict[str, str]:
    if not VOICES_PATH.exists():
        return {}
    try:
        return json.loads(VOICES_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def main() -> int:
    load_env()
    storyboard = load_storyboard()
    NARRATION_DIR.mkdir(parents=True, exist_ok=True)

    client = None
    durations: dict[str, dict] = {}
    voices_used = _load_voices_used()

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        entry: dict[str, float] = {}
        clips = narration_clips(storyboard, shot)

        for role, line, filename in clips:
            out_path = NARRATION_DIR / filename
            configured = storyboard.get("voices", {}).get(role, {}).get("voice", "Kore")
            cache_payload = {
                "shot_id": shot_id,
                "role": role,
                "text": line["text"],
                "style": line["style"],
                "language": storyboard.get("language", "am"),
                "model": TTS_MODEL,
                "voice": configured,
            }

            if is_cached("narration", f"{shot_id}_{role}", cache_payload, out_path):
                voices_used[f"{shot_id}:{role}"] = voices_used.get(
                    f"{shot_id}:{role}", configured
                )
            else:
                if client is None:
                    from google import genai

                    client = genai.Client(
                        api_key=get_env("GEMINI_API_KEY"),
                        http_options={"api_version": "v1beta"},
                    )
                used_voice = _synthesize(client, storyboard, shot, role, line, out_path)
                save_cache("narration", f"{shot_id}_{role}", cache_payload)
                voices_used[f"{shot_id}:{role}"] = used_voice
                print(f"{shot_id}/{role}: generated -> {out_path.name} ({used_voice})")

            entry[role] = _measure_wav_seconds(out_path)

        total = sum(entry.values()) + NARRATION_GAP_SECONDS * (len(entry) - 1) + SHOT_PAD_SECONDS
        entry["total"] = round(total, 3)
        durations[shot_id] = entry

    DURATIONS_PATH.write_text(
        json.dumps(durations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    VOICES_PATH.write_text(
        json.dumps(voices_used, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    film_seconds = sum(e["total"] for e in durations.values()) + float(
        storyboard["end_card"]["duration_seconds"]
    )
    print(
        f"Wrote {len(durations)} shot durations to {DURATIONS_PATH} "
        f"(estimated film: {film_seconds:.1f}s incl. end card)"
    )

    if not 60 <= film_seconds <= 90:
        print("Warning: estimated runtime is outside the 60-90 s target.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
