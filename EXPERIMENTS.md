# Experiments: hypothesis → change → result

Entries marked **offline** were verified without API keys or FFmpeg; entries
marked **live** need a provider call and are recorded when that call is made.
Nothing here is a claimed model comparison that was not run.

1. **E01 — One voice cannot deliver a proverb conversation. (offline)**  
   *Hypothesis:* the new storyboard needs two distinct speakers per shot.  
   *Change:* added `voices` to the schema, `proverb` to every shot, and
   `common.narration_clips()`.  
   *Result:* `make validate` passes on the new storyboard; the offline timeline
   test builds exactly 20 spoken clips from 10 shots.

2. **E02 — A proverb must be spoken by a defined, visible character. (offline)**  
   *Hypothesis:* a typo in `proverb.speaker` would silently produce a missing
   WAV late in assembly.  
   *Change:* semantic validation checks the speaker is in `voices` and in
   `characters`.  
   *Result:* a probe with `"speaker": "stranger"` returned two explicit errors
   before any generation.

3. **E03 — The proverb needs a beat after the setup. (offline)**  
   *Hypothesis:* 0.35 s between narrator and grandmother reads as a pause, not
   a cut; 0.5 s tail keeps shots separate.  
   *Change:* `NARRATION_GAP_SECONDS` and `SHOT_PAD_SECONDS` in `common.py`, used
   by narration, subtitles, radio cut, shots and assembly.  
   *Result:* `tests/test_timeline.py` passes: cue 2 starts at 3.35 s when cue 1
   ends at 3.0 s, and cue 3 starts exactly at shot 1's `total`.

4. **E04 — Runtime must stay inside 60–90 s. (offline)**  
   *Hypothesis:* an 8 s × 10 plan plus a 3 s end card passes; dropping three
   shots should fail before generation.  
   *Change:* planned-runtime check in `validate.py`.  
   *Result:* new storyboard passes at 83.0 s; a 7-shot probe failed with
   "Planned runtime must be 60-90 seconds ... (found 59.0)".

5. **E05 — Camera words in `motion_prompt` should win over a fixed cycle. (offline)**  
   *Hypothesis:* explicit "pushes in" / "pulls back" directions are better than
   the old index-based motion cycle.  
   *Change:* `shots._motion_for_shot()` maps explicit words, else cycles; the
   prompt text is part of the cache key.  
   *Result:* timeline test maps push→`zoom_in`, pull→`zoom_out`, and keeps a
   gentle fallback for "holds still" shots.

6. **E06 — Music cues should be a checked artifact, not a comment. (offline)**  
   *Hypothesis:* out-of-range cue timecodes would be caught before assembly.  
   *Change:* new `pipeline/music.py` writes `outputs/music/cues.json` and
   rejects cues outside `0..duration_seconds`.  
   *Result:* `make music` wrote 3 cues (0–16, 16–56, 56–83) from the new
   storyboard and reported that no `chosen.wav` is ready yet.

7. **E07 — One-command run needs a reference fallback. (code review)**  
   *Hypothesis:* stopping after reference generation breaks "clone → one
   command → film".  
   *Change:* `keyframes._load_chosen()` auto-selects `<char>_v1.jpg` when
   `chosen.json` is absent, printing the choice; `chosen.json` still overrides.  
   *Result:* the stage now returns paths for the existing grandmother sheet,
   so keyframes can begin on the first run. Confirmed in the full live
   API + FFmpeg run: all keyframes, clips and both finals were produced.

8. **E08 — Editing an image prompt must not re-synthesise voices. (code)**  
   *Hypothesis:* dual-voice outputs made cache isolation easier to get wrong.  
   *Change:* narration cache keys are per `<shot>_<role>`, and
   `tests/test_rerun.py` snapshots all 20 WAVs.  
   *Result:* test now asserts zero narration re-takes after an image-prompt
   edit; confirmed in the full pipeline run: all 20 narration WAVs stayed cached.

9. **E09 — A rejected TTS voice should not waste the whole quota. (code)**  
   *Hypothesis:* `Puck`/`Sulafat` may not exist on every endpoint; three blind
   retries per bad voice would be wasteful.  
   *Change:* retry the configured voice once, then try `Kore`, `Puck`,
   `Sulafat` with fail-fast; log every attempt and record the used voice in
   `voices_used.json`.  
   *Result:* failure path is logged in `runs.jsonl`; live voice availability
   to be confirmed with `make narration`.

10. **E10 — Stale outputs from the replaced storyboard mislead inspection. (offline)**  
    *Hypothesis:* old bean narration WAVs, reference images and radio cut would
    look like outputs of the new film.  
    *Change:* removed those generated files; only grandmother references and
    the new music cue sheet remain.  
    *Result:* `git status` shows the deletions; the new stages only read
    `<id>_narrator.wav` / `<id>_<speaker>.wav`.

11. **E11 — A 503 on one text model should not fail the smoke test. (live)**  
    *Hypothesis:* the free text endpoint is occasionally overloaded; a second
    model should answer.  
    *Change:* `smoketest.py` tries `gemini-3.8-flash`, then Flash-Lite, then
    `gemini-2.5-flash`, logging every attempt.  
    *Result:* the observed failure was `503 UNAVAILABLE` after 99.62 s on the
    primary model; the new fallback chain is in place. TTS and Cloudflare both
    passed in the same run (11.78 s and 6.68 s).

12. **E12 — TTS failures were quota, not bad voice names. (live)**  
    *Hypothesis:* `Sulafat`, `Kore` and `Puck` all returned `429`, so trying
    three voices burned quota instead of fixing the problem.  
    *Change:* `narration.py` detects 429/`RESOURCE_EXHAUSTED`, reads the API's
    `retryDelay`, waits that long plus 2 s on the same voice, paces all calls
    21 s apart by default, and stops after four waits with a clear resume
    message.  
    *Result:* the first run completed 7 of 20 lines before hitting the 3/min
    limit; cached lines mean a later `make narration` continues at shot 04.

13. **E13 — A score is needed even without a GPU. (offline)**  
    *Hypothesis:* a deterministic, originally-generated instrumental from the
    storyboard's own caption/BPM/key/cues is better for the edit than silence.  
    *Change:* `pipeline/music.py` writes a seeded G-major pentatonic pluck bed
    to `outputs/music/chosen.wav` when no ACE-Step candidate exists, and logs
    it as `procedural-krar-fallback` with the music payload and seed.  
    *Result:* `make music` produced an 83.0 s, 44.1 kHz WAV (7,320,644 bytes)
    with seed 42, no GPU and no API call; assembly now always has a score.

14. **E14 — An approved reference sheet must not be overwritten. (offline)**  
    *Hypothesis:* regenerating references after `chosen.json` exists destroys
    the human-approved `grandmother_v1.jpg`.  
    *Change:* `keyframes._step1_references()` returns the chosen paths
    immediately when `chosen.json` exists.  
    *Result:* `_load_chosen()` resolves `{'grandmother': 'grandmother_v1.jpg'}`
    and no Cloudflare calls are made for references.

15. **E15 — Silence trimming plus a small speed-up fits the brief. (live)** 
    *Hypothesis:* the 20 Gemini clips carry 0.1–0.9 s of dead air each; removing
    it would bring the 98.8 s film under 90 s. 
    *Change:* `pipeline/retime.py` trims at 2.5% of peak with a 0.02 s margin,
    then derives the smallest speed-up needed to hit `TARGET_FILM_SECONDS`.
    Raw WAVs stay in `outputs/narration/raw/`. After the intro was added, the
    target became 89 s including intro and end card. 
    *Result:* the final revision uses a 1.068x deterministic resample and both
    exports measure exactly **89.0 s**. Rerunning prints `skipped (already
    trimmed)`, so nothing is processed twice.

16. **E16 — The end card needed a real font. (live)** 
    *Hypothesis:* the assembly crash (`0xC0000005`) at `drawtext` was a missing
    font, not a bad concat. 
    *Change:* `find_font()` selects an installed TTF and quotes the escaped
    Windows path; `shots.py`, `radio_cut.py` and `assemble.py` now use
    `common.ffmpeg_bin()` so winget installs work without a PATH edit. 
    *Result:* `make assemble` exported `film_vertical.mp4` (720×1280) and
    `film_horizontal.mp4` (1280×720), both 89.000 s after the intro revision.

17. **E17 — The grandmother needed explicitly Habesha features. (live)** 
    *Hypothesis:* generic "old grandmother" language produced a character the
    audience said did not look Ethiopian / Habesha. 
    *Change:* the character `description` and `reference_prompt` now specify
    deep warm-brown skin, high cheekbones, braided silver-streaked hair in a
    white netela, gold hoop earrings, and a white kemis with gold/red tibb
    embroidery. `make refresh_reference` redraws approved sheets; reference
    hashes were added to the keyframe cache. 
    *Result:* v1–v4 were regenerated, all 20 keyframes and both sets of shot
    clips were rebuilt from the new reference. No TTS calls were repeated.

18. **E18 — Descriptive prompts and an intro made the story readable. (live)** 
    *Hypothesis:* listing a subject in `image_prompt` was not enough to show
    what was happening, and starting on shot 01 gave the audience no setup. 
    *Change:* each prompt now includes `reason`, `shot_size`, location, action,
    background and lighting; a 4 s `intro` block renders a title plus "Ten small
    mishaps. Ten proverbs. One grandmother who always knows what to say." 
    *Result:* the first subtitle cue moved to 00:00:04, the intro is present in
    both finals, and `make test` still passes with the intro-aware timeline.

19. **E19 — The horizontal export had to be shot wide, not reframed. (live)** 
    *Hypothesis:* a blurred 16:9 background around the vertical master would
    always look like a vertical film. 
    *Change:* `format.horizontal_prompt_suffix` drives 1024×576 keyframes;
    `shots.py` renders 1280×720 wide clips, and `assemble.py` builds an
    independent horizontal timeline, intro, subtitles and end card. 
    *Result:* ffprobe reports `film_horizontal.mp4` at 1280×720 and
    `film_vertical.mp4` at 720×1280, both 89.000 s.

## Still to run (live)

- Three ACE-Step candidates for the 83 s score, chosen by ear under narration
  (notebook exports seeds to `runs.jsonl`).
- Wan 2.2 image-to-video versus FFmpeg pan/zoom for two representative shots,
  comparing latency and a blind preference between five viewers.
- Native-speaker check of Amharic TTS pronunciation of each proverb.
