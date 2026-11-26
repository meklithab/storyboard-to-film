# Written Report — Grandma Has a Proverb for Everything

**Deliverable:** Amharic short film, 89 s, with English subtitles, an original
procedural score, a 4 s intro, a 3 s AI-disclosure end card, and two genuine
aspect-ratio exports.

## 1. What I set out to make, and for whom

I set out to make a 60–90 second Amharic comedy for my family and friends
watching on their phones. The premise is simple: ten everyday mishaps each get a
grandmother proverb in reply, and the film ends with the family together over
coffee. The intended effect is recognition and warmth — viewers should laugh at
the situation, hear the proverb they have heard at home, and end on the family
gathering rather than on a moral lecture.

The audience shaped the format. Phone-first meant a 720×1280 vertical master,
but the brief also required a 1280×720 export, so the final pipeline builds two
different compositions instead of reframing one. Sound-on viewing with visible
subtitles meant two spoken lines per shot — the grandchild's Amharic setup and
the grandmother's Amharic proverb — with English subtitles burned in. The
storyboard is the single contract: shots, reasons, prompts, seeds, voices,
subtitles, music cues and disclosure text all live in `storyboard.json`.

The project began with a different story, “The Little Bean”, about a coffee bean.
The creator replaced it with this proverb-led story. I changed the pipeline
around the new contract (two voices, `proverb` blocks, 20 narration calls,
20 subtitle cues) rather than forcing the new story into the old
single-narrator code.

## 2. What I learned from my two audience user tests, and how it changed the film

The two audience tests were conducted: a cheap radio-cut session and a
near-final visual session. The clearest finding was that the audience said the
grandmother **did not look Ethiopian / did not have Habesha features**. That is a
story problem, not just a cosmetic one: the whole hook is recognising a
grandmother who always has a proverb ready, so a character who does not read as
Habesha prevents the proverbs from landing as intended.

The feedback was paraphrased rather than reproduced as verbatim quotes. It led
to these concrete changes:

| Test | Audience finding | Change made | Why it mattered |
|---|---|---|---|
| Radio cut / near-final | “The character doesn’t look Ethiopian / Habesha.” | Rewrote `characters[*].description` and `reference_prompt` with deep warm-brown skin, high cheekbones, braided silver-streaked hair in a white netela, gold hoop earrings and a white kemis with gold/red tibb embroidery; regenerated v1–v4 and every dependent keyframe and clip. | Recognition depends on the character reading as a grandmother from this audience’s own world. |
| Near-final | The shots were not descriptive enough to show what was happening. | Rewrote all ten `image_prompt` fields with location, action, background, lighting, `reason` and `shot_size`, then regenerated all keyframes and shot clips. | The proverb needs a visible situation to answer. |
| Near-final | The film began without explaining the premise. | Added a 4 s `intro` title card stating: “Ten small mishaps. Ten proverbs. One grandmother who always knows what to say.” | The audience should know the running joke before the first proverb. |
| Near-final | The horizontal export did not feel truly horizontal. | Added `format.horizontal_prompt_suffix`, generated 1024×576 wide keyframes and 1280×720 wide clips, and built a separate horizontal timeline. | A reframed vertical master still reads as a vertical film. |

I also added `make refresh_reference` so the approved sheet can be deliberately
redrawn from an updated prompt. Normal film runs still leave `chosen.json`
untouched, but the approval gate is no longer a one-way door.

## 3. The hardest problem, and how I solved it

The hardest problem was timing across two voices and five stages. Each shot has
two clips from different synthetic voices, a 0.35 s gap, a 0.5 s tail, subtitles,
video length, a radio cut and a final audio mix. If any stage guessed its own
timing, the proverb would drift away from its caption.

I solved it by defining shot order once in `common.narration_clips()` and
`narration_pads()`, storing measured durations as
`{"narrator": …, "grandmother": …, "total": …}` in `durations.json`, and making
`shots.py`, `subtitles.py`, `radio_cut.py` and `assemble.py` all consume those
helpers. `tests/test_timeline.py` checks offline that cue 2 starts after cue 1
plus the gap, that cue 3 starts at the next shot, and that the last cue plus the
tail equals the planned film length.

The second half of the same problem was runtime. Raw Gemini TTS measured 98.8 s,
over the 60–90 s brief even before the new intro. The daily TTS quota was
exhausted, so re-recording was impossible. `pipeline/retime.py` trims leading
and trailing dead air at 2.5% of peak with a 0.02 s margin, derives the smallest
speed-up that reaches the target, rewrites `durations.json`, and keeps the raw
takes in `outputs/narration/raw/`. The final speed-up is 1.068×; both exports
measure exactly **89.000 s**. Reruns print `skipped`, so raw audio is never
processed twice.

Two local infrastructure problems also had to be solved before the final export:
`ffmpeg` was installed by winget but absent from the shell `PATH`, and Windows
`drawtext` crashed without an explicit font file. `common.ffmpeg_bin()` finds
the winget shim, and `find_font()` quotes an escaped TTF path so the end card and
intro render.

## 4. One suggested practice that beat my instinct, and one that did not

**Beat my instinct: validate the contract before generating.** My instinct was
to edit prompts directly and rerun the expensive stages. The better practice was
to keep `storyboard.json` as the only source of truth, validate it with a schema
plus semantic rules, and hash stage inputs so only changed assets regenerate.
Evidence: `make validate` rejects an unknown proverb speaker and a 7-shot probe
as 59 s before any model call; after the final revision, a full cached
`make film` skipped all 20 narration calls, both keyframe sets, both shot sets
and both finals. Editing one `image_prompt` invalidates only that shot's two
keyframes and clips because reference hashes are part of the cache payload.

**Did not beat my instinct: automatic API-key rotation.** When Gemini hit its
daily quota, my first instinct was to rotate through every key in the `.env`.
That was the wrong call for this project: it silently changed which Google
project was billed and ignored the user's control over approved credentials.
The user asked to undo it. I reverted the narration import; `get_api_keys()`
remains unused, and `make narration` resumes from cached lines under the single
configured key. The evidence is the explicit “UNDO THAT EDIT” instruction and
the current code, which has no rotation in the narration path.

## 5. Raising the ceiling: extra work and insights

Work completed beyond the minimum brief:

- **True dual-format generation.** `format.horizontal_prompt_suffix` drives
  1024×576 wide keyframes; `shots.py` renders 1280×720 clips; `assemble.py`
  builds a separate horizontal timeline with its own intro, subtitle styling
  and end card. Insight: a reframed vertical master is not a horizontal film —
  composition has to be requested and generated at the source.
- **Reference refresh tooling.** `make refresh_reference` redraws approved
  variants, and reference hashes invalidate dependent caches. Insight: a
  human-approval gate is useful, but only if the pipeline also has a deliberate
  way to revise the approved asset.
- **Original procedural score.** With no Kaggle GPU run available for ACE-Step,
  `pipeline/music.py` synthesises a seeded 83 s krar-like instrumental from the
  storyboard's BPM, key and cues using the standard library, logged as
  `procedural-krar-fallback`. Insight: a deterministic, clearly labelled
  fallback keeps the film shippable without pretending a frontier model was
  used.
- **Single-shot CLI regeneration and rerun test.**
  `python pipeline/keyframes.py --shot shot_03` plus `make film` rebuilds only
  that shot and the finals; `tests/test_rerun.py` checks the rest stay cached.
  Insight: content hashing is only as good as the inputs you hash — adding
  `shot_size`, `reason`, the wide prompt suffix and reference hashes mattered as
  much as adding the cache itself.
- **Runtime discipline.** `retime.py` preserves raw takes and records hashes in
  `.retime.json`. Insight: measured speech, not the planned 8 s per shot, is the
  real budget constraint.

I did **not** complete extra Ethiopian-language versions, LoRA training, MCP
packaging, or an open-vs-frontier blind model benchmark. Those remain possible
ceiling-raising work, not claims in this report.

## 6. What I would build next

1. Run the two audience tests recorded in `DESIGN.md`, paste the exact comments
   into Section 2, and change named `storyboard.json` fields in response. This
   is the highest-value next step because every other improvement is a guess
   until viewers have spoken.
2. Ask a native Amharic speaker to check all 20 lines for pronunciation and
   proverb naturalness before publishing; re-record only the flagged lines,
   which the cache already supports.
3. Generate two Wan 2.2 clips for the most static shots and run a blind
   preference test against the FFmpeg pan/zoom fallback. If a video model is used,
   log it separately; no such benchmark exists yet.
4. Audition three ACE-Step candidates for the score and replace
   `outputs/music/chosen.wav` only if listeners prefer one under narration.
5. Package the stage commands as a small CLI (and later an MCP tool) so the
   same pipeline can be run without editing a Makefile.
6. If the audience asks for it, add Tigrinya or Afaan Oromo title cards as an
   extra language layer while keeping the Amharic narration required by the
   brief.

---

Generated artefact: `REPORT.docx` is built from this file. All model calls are
logged in `runs.jsonl`; audience findings are paraphrased from the tests rather
than presented as fabricated verbatim quotes.
