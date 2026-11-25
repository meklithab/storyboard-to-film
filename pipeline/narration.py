"""Generate per-shot Amharic narration audio using Gemini TTS and record durations."""

import json
from pathlib import Path
import sys
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ROOT_DIR,
    get_env,
    is_cached,
    load_env,
    load_storyboard,
    log_run,
    retry_call,
    save_audio_wav,
    save_cache,
)

TTS_MODEL = "gemini-3.8-flash-tts"
VOICE_NAME = "Kore"
NARRATION_DIR = ROOT_DIR / "outputs" / "narration"
DURATIONS_PATH = NARRATION_DIR / "durations.json"


def _synthesize_shot(client, shot: dict, out_path) -> None:
    """Call Gemini TTS for one shot with retries and run logging."""
    from google.genai import types

    shot_id = shot["id"]
    seed = shot.get("seed")
    narration = shot["narration"]
    text = narration["text"]
    style = narration["style"]
    prompt = f"Speak in this style ({style}):\n{text}"
    params = {"shot_id": shot_id, "voice_name": VOICE_NAME, "style": style}

    def _call() -> None:
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=TTS_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                        )
                    ),
                ),
            )
            for cand in resp.candidates or []:
                for part in cand.content.parts or []:
                    if part.inline_data and part.inline_data.data:
                        save_audio_wav(out_path, part.inline_data.data, part.inline_data.mime_type or "")
                        log_run(
                            "narration",
                            TTS_MODEL,
                            params,
                            seed=seed,
                            latency_seconds=time.perf_counter() - t0,
                            success=True,
                        )
                        return
            raise RuntimeError(f"No audio returned for {shot_id}")
        except Exception as exc:
            log_run(
                "narration",
                TTS_MODEL,
                params,
                seed=seed,
                latency_seconds=time.perf_counter() - t0,
                success=False,
                error=str(exc),
            )
            raise

    retry_call(_call)


def _measure_wav_seconds(wav_path) -> float:
    """Return real WAV audio duration in seconds."""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return round(frames / float(rate), 3)


def main() -> int:
    load_env()
    storyboard = load_storyboard()
    NARRATION_DIR.mkdir(parents=True, exist_ok=True)

    client = None
    durations: dict[str, float] = {}

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        narration = shot["narration"]
        out_path = NARRATION_DIR / f"{shot_id}.wav"
        cache_payload = {
            "shot_id": shot_id,
            "text": narration["text"],
            "style": narration["style"],
            "model": TTS_MODEL,
            "voice": VOICE_NAME,
        }

        if not is_cached("narration", shot_id, cache_payload, out_path):
            if client is None:
                from google import genai

                client = genai.Client(
                    api_key=get_env("GEMINI_API_KEY"),
                    http_options={"api_version": "v1beta"},
                )
            _synthesize_shot(client, shot, out_path)
            save_cache("narration", shot_id, cache_payload)
            print(f"{shot_id}: generated -> {out_path.name}")

        durations[shot_id] = _measure_wav_seconds(out_path)

    DURATIONS_PATH.write_text(json.dumps(durations, indent=2), encoding="utf-8")
    print(f"Wrote {len(durations)} durations to {DURATIONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
