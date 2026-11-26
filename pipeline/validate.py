"""Validate storyboard.json against schema/storyboard.schema.json and semantic rules."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from jsonschema import Draft7Validator
except ImportError as exc:
    print(f"Missing dependency: {exc}. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

from common import SCHEMA_PATH, STORYBOARD_PATH, load_storyboard


def validate_storyboard(storyboard_path=STORYBOARD_PATH, schema_path=SCHEMA_PATH) -> list[str]:
    """Return a list of validation error messages (empty if valid)."""
    errors: list[str] = []

    try:
        storyboard = load_storyboard(storyboard_path)
    except Exception as exc:
        return [f"Failed to load {storyboard_path}: {exc}"]

    try:
        with schema_path.open("r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as exc:
        return [f"Failed to load {schema_path}: {exc}"]

    validator = Draft7Validator(schema)
    for err in sorted(validator.iter_errors(storyboard), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in err.path) or "<root>"
        errors.append(f"Schema error at {location}: {err.message}")

    # Semantic checks: 8-12 shots, unique shot IDs, valid character IDs
    shots = storyboard.get("shots", [])
    if isinstance(shots, list):
        if not (8 <= len(shots) <= 12):
            errors.append(f"Shot count must be between 8 and 12 (found {len(shots)}).")

        seen_ids: set[str] = set()
        for idx, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            sid = shot.get("id")
            if isinstance(sid, str):
                if sid in seen_ids:
                    errors.append(f"Duplicate shot id: '{sid}' at shots[{idx}].")
                seen_ids.add(sid)

        characters = storyboard.get("characters", [])
        valid_chars = {
            c.get("id") for c in characters if isinstance(c, dict) and isinstance(c.get("id"), str)
        }
        voices = storyboard.get("voices", {})
        valid_voices = set(voices) if isinstance(voices, dict) else set()
        for voice_role, voice_cfg in voices.items() if isinstance(voices, dict) else []:
            if isinstance(voice_cfg, dict) and not voice_cfg.get("voice"):
                errors.append(f"Voice '{voice_role}' has no TTS voice name.")

        for shot in shots:
            if not isinstance(shot, dict):
                continue
            sid = shot.get("id", "<unknown>")
            for cid in shot.get("characters", []):
                if cid not in valid_chars:
                    errors.append(
                        f"Shot '{sid}' references unknown character id '{cid}'."
                    )
            proverb = shot.get("proverb")
            if isinstance(proverb, dict):
                speaker = proverb.get("speaker")
                if speaker not in valid_voices:
                    errors.append(
                        f"Shot '{sid}' proverb speaker '{speaker}' is not defined in voices."
                    )
                if speaker not in valid_chars:
                    errors.append(
                        f"Shot '{sid}' proverb speaker '{speaker}' is not a storyboard character."
                    )

        try:
            planned = sum(float(s["duration_seconds"]) for s in shots if isinstance(s, dict))
            planned += float(storyboard["end_card"]["duration_seconds"])
            if not 60 <= planned <= 90:
                errors.append(
                    f"Planned runtime must be 60-90 seconds including the end card (found {planned:.1f})."
                )
        except (KeyError, TypeError, ValueError):
            # Schema validation already reports malformed duration fields.
            pass

    return errors


def main() -> int:
    errors = validate_storyboard()
    if errors:
        print("Storyboard validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    sb = load_storyboard()
    print(f"Storyboard valid: '{sb['title']}' ({len(sb['shots'])} shots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
