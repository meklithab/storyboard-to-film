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


def _file_digest(path: Path) -> str:
    """Hash a reference image so a refreshed sheet invalidates keyframe caches."""
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    """Load chosen references, or auto-select the first generated variant.

    ``chosen.json`` remains the human approval gate. If it is absent but a
    reference sheet already exists, using ``<char>_v1.jpg`` lets a clean clone
    run ``make film`` end to end; writing chosen.json overrides that default.
    """
    if not CHOSEN_PATH.exists():
        auto_paths: dict[str, Path] = {}
        for char in storyboard["characters"]:
            candidates = sorted(REFERENCE_DIR.glob(f"{char['id']}_v*.jpg"))
            if not candidates:
                return None
            auto_paths[char["id"]] = candidates[0]
        print(
            "Note: outputs/reference/chosen.json not found; auto-selected "
            + json.dumps({k: v.name for k, v in auto_paths.items()})
            + ". Write chosen.json to override."
        )
        return auto_paths
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


def _step1_references(
    storyboard: dict,
    creds: tuple[str, str] | None,
    force: bool = False,
) -> dict[str, Path] | None:
    """Generate 4 reference variants per character, then verify chosen.json.

    With ``force=True`` the approved variants are regenerated from the current
    prompts; use ``make refresh_reference`` when the character design changes.
    """
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)

    # A human-approved sheet is final: never overwrite it during a normal film
    # run. An explicit refresh is the only way to replace approved images.
    if CHOSEN_PATH.exists() and not force:
        print("Using approved references from chosen.json; skipping reference generation.")
        return _load_chosen(storyboard)
    if force and CHOSEN_PATH.exists():
        print("Refreshing approved references from the current storyboard prompts.")

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

            if force or not is_cached("reference", item_id, payload, out_path):
                if not account_id:
                    account_id = get_env("CLOUDFLARE_ACCOUNT_ID")
                    api_token = get_env("CLOUDFLARE_API_TOKEN")
                _generate_image(account_id, api_token, prompt, seed, 512, 512, out_path, "reference")
                save_cache("reference", item_id, payload)
                print(f"{item_id}: {'refreshed' if force else 'generated'} -> {out_path.name}")

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
    """Generate a vertical and a true widescreen keyframe per shot."""
    KEYFRAMES_DIR.mkdir(parents=True, exist_ok=True)
    style_block = storyboard["style_block"]
    char_map = {c["id"]: c for c in storyboard["characters"]}
    shots = storyboard["shots"]
    horizontal_suffix = storyboard.get("format", {}).get(
        "horizontal_prompt_suffix",
        "Wide 16:9 landscape composition of the same scene, full action visible across the frame",
    )

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
        context = f"Story context: {shot['reason']}. Shot size: {shot['shot_size']}."
        base_prompt = f"{style_block}. {context} {char_descs}. {shot['image_prompt']}."
        ref_files = [chosen_paths[cid] for cid in shot["characters"] if cid in chosen_paths]
        ref_hashes = [_file_digest(p) for p in ref_files]

        specs = (
            (sid, f"{base_prompt} {NO_TEXT_SUFFIX}", 576, 1024, "keyframes"),
            (
                f"{sid}_wide",
                f"{base_prompt} {horizontal_suffix}. {NO_TEXT_SUFFIX}",
                1024,
                576,
                "keyframes_wide",
            ),
        )

        for item_id, prompt, width, height, stage in specs:
            out_path = KEYFRAMES_DIR / f"{item_id}.jpg"
            payload = {
                "shot_id": sid,
                "prompt": prompt,
                "seed": seed,
                "model": IMAGE_MODEL,
                "refs": [p.name for p in ref_files],
                "ref_hashes": ref_hashes,
                "width": width,
                "height": height,
            }

            if not is_cached(stage, item_id, payload, out_path):
                if not account_id:
                    account_id = get_env("CLOUDFLARE_ACCOUNT_ID")
                    api_token = get_env("CLOUDFLARE_API_TOKEN")
                _generate_image(
                    account_id,
                    api_token,
                    prompt,
                    seed,
                    width,
                    height,
                    out_path,
                    stage,
                    ref_images=ref_files,
                )
                save_cache(stage, item_id, payload)
                print(f"{item_id}: generated -> {out_path.name} ({width}x{height})")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate character references and shot keyframes.")
    parser.add_argument("--shot", help="Regenerate only this shot id (e.g. shot_03)")
    parser.add_argument(
        "--refresh-reference",
        action="store_true",
        help="Regenerate approved character sheets from the current prompts",
    )
    args = parser.parse_args()

    load_env()
    storyboard = load_storyboard()

    if args.refresh_reference:
        chosen_paths = _step1_references(storyboard, None, force=True)
    else:
        chosen_paths = _load_chosen(storyboard) if args.shot else None
        if chosen_paths is None:
            chosen_paths = _step1_references(storyboard, None)
    if chosen_paths is None:
        return 2

    return _step2_keyframes(storyboard, chosen_paths, only_shot=args.shot)


if __name__ == "__main__":
    sys.exit(main())
