"""Smoke test for Gemini text, Gemini TTS (Amharic), and Cloudflare Workers AI image."""

import base64
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import CACHE_DIR, get_env, load_env, log_run, retry_call, save_audio_wav

TEXT_MODEL = "gemini-3.8-flash"
TTS_MODEL = "gemini-3.8-flash-tts"
IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def test_gemini_text() -> str:
    """Call Gemini text generation once and log latency."""
    from google import genai

    api_key = get_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    prompt = "Reply with one short word: ready."
    params = {"prompt_length": len(prompt)}

    def _call() -> str:
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=TEXT_MODEL, contents=prompt)
            text = (resp.text or "").strip()
            if not text:
                raise RuntimeError("Empty text response from Gemini")
            log_run("smoketest", TEXT_MODEL, params, latency_seconds=time.perf_counter() - t0, success=True)
            return text
        except Exception as exc:
            log_run("smoketest", TEXT_MODEL, params, latency_seconds=time.perf_counter() - t0, success=False, error=str(exc))
            raise

    return retry_call(_call)


def test_gemini_tts() -> str:
    """Call Gemini TTS with one short Amharic sentence and save a WAV file."""
    from google import genai
    from google.genai import types

    api_key = get_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    sentence = "ሰላም፣ እኔ ትንሽ ቡና ነኝ።"
    voice_name = "Kore"
    params = {"voice_name": voice_name, "text_length": len(sentence)}
    out_path = CACHE_DIR / "smoketest_tts.wav"

    def _call() -> str:
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=TTS_MODEL,
                contents=f"Read warmly in Amharic: {sentence}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                        )
                    ),
                ),
            )
            for cand in resp.candidates or []:
                for part in cand.content.parts or []:
                    if part.inline_data and part.inline_data.data:
                        save_audio_wav(out_path, part.inline_data.data, part.inline_data.mime_type or "")
                        log_run("smoketest", TTS_MODEL, params, latency_seconds=time.perf_counter() - t0, success=True)
                        return str(out_path)
            raise RuntimeError("No audio data returned by Gemini TTS")
        except Exception as exc:
            log_run("smoketest", TTS_MODEL, params, latency_seconds=time.perf_counter() - t0, success=False, error=str(exc))
            raise

    return retry_call(_call)


def test_cloudflare_image() -> str:
    """Generate one small image via Cloudflare Workers AI Flux Schnell."""
    import requests

    account_id = get_env("CLOUDFLARE_ACCOUNT_ID")
    api_token = get_env("CLOUDFLARE_API_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{IMAGE_MODEL}"
    payload = {"prompt": "Small cute cartoon coffee bean on a plain warm background", "steps": 2}
    params = {"steps": payload["steps"], "prompt_length": len(payload["prompt"])}
    out_path = CACHE_DIR / "smoketest_image.jpg"

    def _call() -> str:
        t0 = time.perf_counter()
        try:
            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

            ctype = resp.headers.get("Content-Type", "")
            if ctype.startswith("image/"):
                img_bytes = resp.content
            else:
                body = resp.json()
                b64 = body.get("result", {}).get("image")
                if not b64:
                    raise RuntimeError(f"Unexpected Cloudflare response: {body}")
                img_bytes = base64.b64decode(b64)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(img_bytes)
            log_run("smoketest", IMAGE_MODEL, params, latency_seconds=time.perf_counter() - t0, success=True)
            return str(out_path)
        except Exception as exc:
            log_run("smoketest", IMAGE_MODEL, params, latency_seconds=time.perf_counter() - t0, success=False, error=str(exc))
            raise

    return retry_call(_call)


def main() -> int:
    load_env()
    checks = [
        ("gemini_text", test_gemini_text),
        ("gemini_tts", test_gemini_tts),
        ("cloudflare_image", test_cloudflare_image),
    ]
    failed = False
    for name, fn in checks:
        start = time.perf_counter()
        try:
            result = fn()
            elapsed = time.perf_counter() - start
            print(f"[PASS] {name} ({elapsed:.2f}s): {result}")
        except Exception as exc:
            elapsed = time.perf_counter() - start
            print(f"[FAIL] {name} ({elapsed:.2f}s): {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
