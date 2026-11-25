"""Shared helpers for loading config, logging model calls, retrying, and caching."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, TypeVar
import wave

try:
    from dotenv import load_dotenv
except ImportError:  # Fallback if python-dotenv is not installed yet
    load_dotenv = None

ROOT_DIR = Path(__file__).resolve().parent.parent
STORYBOARD_PATH = ROOT_DIR / "storyboard.json"
SCHEMA_PATH = ROOT_DIR / "schema" / "storyboard.schema.json"
RUNS_PATH = ROOT_DIR / "runs.jsonl"
CACHE_DIR = ROOT_DIR / "outputs" / "cache"

T = TypeVar("T")


def load_env(env_path: Path | None = None) -> None:
    """Load environment variables from .env without printing or overriding existing vars."""
    path = env_path or (ROOT_DIR / ".env")
    if not path.exists():
        return
    if load_dotenv is not None:
        load_dotenv(dotenv_path=path, override=False)
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable: {name} (add it to .env)")
    return value


def load_storyboard(path: Path = STORYBOARD_PATH) -> dict[str, Any]:
    """Read and parse storyboard.json."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def log_run(
    stage: str,
    model: str,
    parameters: dict[str, Any],
    seed: int | None = None,
    latency_seconds: float = 0.0,
    estimated_cost: float = 0.0,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Append one model-call record as a JSON line to runs.jsonl."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "model": model,
        "parameters": parameters,
        "seed": seed,
        "latency_seconds": round(latency_seconds, 3),
        "estimated_cost": round(estimated_cost, 6),
        "success": success,
        "error": error,
    }
    with RUNS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def retry_call(
    fn: Callable[[], T],
    retries: int = 3,
    delays: tuple[float, ...] = (1.0, 2.0, 4.0),
) -> T:
    """Call fn(); on failure retry up to `retries` times with increasing waits."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception:
            if attempt >= retries:
                raise
            wait = delays[min(attempt, len(delays) - 1)]
            time.sleep(wait)
    raise RuntimeError("Unreachable")


def compute_hash(payload: Any) -> str:
    """Compute a deterministic SHA-256 hex digest for JSON-serializable inputs."""
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cache_file(stage: str, item_id: str) -> Path:
    return CACHE_DIR / f"{stage}_{item_id}.sha256"


def is_cached(stage: str, item_id: str, payload: Any, output_path: Path) -> bool:
    """Return True and print 'skipped (cached)' if input hash matches and output exists."""
    cfile = _cache_file(stage, item_id)
    if not cfile.exists() or not output_path.exists() or output_path.stat().st_size == 0:
        return False
    expected = compute_hash(payload)
    if cfile.read_text(encoding="utf-8").strip() == expected:
        print(f"{item_id}: skipped (cached)")
        return True
    return False


def save_cache(stage: str, item_id: str, payload: Any) -> None:
    """Persist the input hash for a completed stage item."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_file(stage, item_id).write_text(compute_hash(payload), encoding="utf-8")


def save_audio_wav(output_path: Path, audio_bytes: bytes, mime_type: str = "") -> None:
    """Save Gemini TTS audio bytes as a valid WAV file (handles raw PCM or WAV)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if audio_bytes[:4] == b"RIFF" or "wav" in mime_type.lower():
        output_path.write_bytes(audio_bytes)
        return

    # Gemini TTS commonly returns raw 16-bit mono PCM (e.g. audio/L16;rate=24000)
    sample_rate = 24000
    for part in mime_type.split(";"):
        part = part.strip().lower()
        if part.startswith("rate="):
            try:
                sample_rate = int(part.split("=", 1)[1])
            except ValueError:
                pass

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_bytes)


def _test_cache() -> None:
    """Verify cache skips unchanged inputs and re-runs when inputs change."""
    import tempfile

    stage = "_selftest"
    item_id = "shot_test"
    calls = 0

    def produce(out_file: Path, data: dict[str, Any]) -> None:
        nonlocal calls
        if is_cached(stage, item_id, data, out_file):
            return
        calls += 1
        out_file.write_text("audio", encoding="utf-8")
        save_cache(stage, item_id, data)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "shot_test.wav"
            inputs = {"text": "hello", "style": "warm"}

            produce(out, inputs)
            assert calls == 1, f"Expected 1 call, got {calls}"

            # Unchanged inputs: should skip and print "skipped (cached)"
            produce(out, inputs)
            assert calls == 1, f"Expected cache hit (1 call), got {calls}"

            # Changed inputs: should run again
            produce(out, {"text": "changed", "style": "warm"})
            assert calls == 2, f"Expected re-run (2 calls), got {calls}"

        print("Cache test passed.")
    finally:
        cfile = _cache_file(stage, item_id)
        if cfile.exists():
            cfile.unlink()


if __name__ == "__main__":
    _test_cache()
