"""Generate character reference sheets (Step 1) and shot keyframes (Step 2) via Cloudflare FLUX.2."""

import argparse
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    ROOT_DIR,
    get_env,
    is_cached,
    load_env,
    load_storyboard,
    log_run,
    retry_call,
    save_cache,
)

# Best free-tier Cloudflare FLUX model supporting seed, width, height, and input_image_0..3
IMAGE_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
REFERENCE_DIR = ROOT_DIR / "outputs" / "reference"
KEYFRAMES_DIR = ROOT_DIR / "outputs" / "keyframes"
CHOSEN_PATH = REFERENCE_DIR / "chosen.json"
NO_TEXT_SUFFIX = "no text, no words, no letters, no captions, no watermarks"


def _generate_image(
    account_id: str,
    api_token: str,
    prompt: str,
    seed: int,
    width: int,
    height: int,
    out_path: Path,
    stage: str,
    ref_images: list[Path] | None = None,
) -> None:
    """Call Cloudflare Workers AI FLUX.2 via multipart/form-data with retries and logging."""
    import requests

    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{IMAGE_MODEL}"
    params = {"width": width, "height": height, "refs": len(ref_images or [])}

    def _call() -> None:
        t0 = time.perf_counter()
        opened_files = []
        try:
            files: list[tuple[str, tuple]] = [
                ("prompt", (None, prompt)),
                ("seed", (None, str(seed))),
                ("width", (None, str(width))),
                ("height", (None, str(height))),
            ]
            for idx, ref_path in enumerate((ref_images or [])[:4]):
                fh = ref_path.open("rb")
                opened_files.append(fh)
                mime = "image/png" if ref_path.suffix.lower() == ".png" else "image/jpeg"
                files.append((f"input_image_{idx}", (ref_path.name, fh, mime)))

            resp = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_token}"},
                files=files,
                timeout=120,
            )
            if not resp.ok:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

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
            log_run(
                stage,
                IMAGE_MODEL,
                params,
                seed=seed,
                latency_seconds=time.perf_counter() - t0,
                success=True,
            )
        except Exception as exc:
            log_run(
                stage,
                IMAGE_MODEL,
                params,
                seed=seed,
                latency_seconds=time.perf_counter() - t0,
                success=False,
                error=str(exc),
            )
            raise
        finally:
            for fh in opened_files:
                fh.close()

    retry_call(_call)


def _load_chosen(storyboard: dict) -> dict[str, Path] | None:
    """Load and verify outputs/reference/chosen.json if present."""
    if not CHOSEN_PATH.exists():
        return None
    chosen_raw = json.loads(CHOSEN_PATH.read_text(encoding="utf-8"))
    chosen_paths: dict[str, Path] = {}
    for char in storyboard["characters"]:
        cid = char["id"]
        entry = chosen_raw.get(cid, "")
        if not entry:
            print(f"Error: '{cid}' missing in {CHOSEN_PATH}", file=sys.stderr)
            return None
        p = Path(entry)
        if not p.is_absolute():
            p = REFERENCE_DIR / p.name if not (ROOT_DIR / p).exists() else (ROOT_DIR / p)
        if not p.exists():
            print(f"Error: chosen reference image not found for '{cid}': {p}", file=sys.stderr)
            return None
        chosen_paths[cid] = p
    return chosen_paths


def _step1_references(storyboard: dict, creds: tuple[str, str] | None) -> dict[str, Path] | None:
    """Generate 4 reference variants per character, then verify chosen.json."""
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    style_block = storyboard["style_block"]
    account_id, api_token = creds or ("", "")

    for char in storyboard["characters"]:
        cid = char["id"]
        base_seed = int(char["seed"])
        prompt = f"{style_block}. {char['reference_prompt']}. {NO_TEXT_SUFFIX}"

        for variant in range(4):
            seed = base_seed + variant
            item_id = f"{cid}_v{variant + 1}"
            out_path = REFERENCE_DIR / f"{item_id}.jpg"
            payload = {"char_id": cid, "prompt": prompt, "seed": seed, "model": IMAGE_MODEL}

            if not is_cached("reference", item_id, payload, out_path):
                if not account_id:
                    account_id = get_env("CLOUDFLARE_ACCOUNT_ID")
                    api_token = get_env("CLOUDFLARE_API_TOKEN")
                _generate_image(account_id, api_token, prompt, seed, 512, 512, out_path, "reference")
                save_cache("reference", item_id, payload)
                print(f"{item_id}: generated -> {out_path.name}")

    chosen_paths = _load_chosen(storyboard)
    if chosen_paths is None and not CHOSEN_PATH.exists():
        example = {c["id"]: f"{c['id']}_v1.jpg" for c in storyboard["characters"]}
        print("\nStep 1 complete. Inspect images in outputs/reference/ and write outputs/reference/chosen.json:")
        print(json.dumps(example, indent=2))
    return chosen_paths


def _step2_keyframes(
    storyboard: dict,
    chosen_paths: dict[str, Path],
    only_shot: str | None = None,
) -> int:
    """Generate keyframe per shot (or one shot with --shot)."""
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    style_block = storyboard["style_block"]
    char_map = {c["id"]: c for c in storyboard["characters"]}
    shots = storyboard["shots"]

    if only_shot:
        shots = [s for s in shots if s["id"] == only_shot]
        if not shots:
            print(f"Error: shot '{only_shot}' not found in storyboard.json", file=sys.stderr)
            return 1

    account_id = ""
    api_token = ""

    for shot in shots:
        sid = shot["id"]
        seed = int(shot["seed"])
        char_descs = ". ".join(char_map[cid]["description"] for cid in shot["characters"])
        prompt = f"{style_block}. {char_descs}. {shot['image_prompt']}. {NO_TEXT_SUFFIX}"
        ref_files = [chosen_paths[cid] for cid in shot["characters"] if cid in chosen_paths]
        out_path = KEYFRAMES_DIR / f"{sid}.jpg"

        payload = {
            "shot_id": sid,
            "prompt": prompt,
            "seed": seed,
            "model": IMAGE_MODEL,
            "refs": [p.name for p in ref_files],
        }

        if not is_cached("keyframes", sid, payload, out_path):
            if not account_id:
                account_id = get_env("CLOUDFLARE_ACCOUNT_ID")
                api_token = get_env("CLOUDFLARE_API_TOKEN")
            _generate_image(
                account_id,
                api_token,
                prompt,
                seed,
                576,
                1024,
                out_path,
                "keyframes",
                ref_images=ref_files,
            )
            save_cache("keyframes", sid, payload)
            print(f"{sid}: generated -> {out_path.name}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate character references and shot keyframes.")
    parser.add_argument("--shot", help="Regenerate only this shot id (e.g. shot_03)")
    args = parser.parse_args()

    load_env()
    storyboard = load_storyboard()

    chosen_paths = _load_chosen(storyboard) if args.shot else None
    if chosen_paths is None:
        chosen_paths = _step1_references(storyboard, None)
    if chosen_paths is None:
        return 2

    return _step2_keyframes(storyboard, chosen_paths, only_shot=args.shot)


if __name__ == "__main__":
    sys.exit(main())
