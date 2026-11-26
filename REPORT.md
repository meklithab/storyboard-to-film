# Report — Grandma Has a Proverb for Everything

*Draft reflecting the current repository. Items still pending are marked as such.*

## What I set out to make, and for whom

A 60–90 second Amharic short for my family and friends watching on their
phones. Ten everyday mishaps each get a grandmother proverb in reply; the film
ends with the family together over coffee. The intended feeling is amusement
followed by warmth and recognition, not a lecture about proverbs. The
storyboard is the contract: shots, reasons, prompts, seeds, both spoken lines,
English subtitles, voices and music cues all live in `storyboard.json`.

The first storyboard followed a coffee bean ("The Little Bean"). It was
replaced with this proverb-led story, and the pipeline was changed around the
new contract rather than forcing the new story into the old single-narrator
code.

## What I learned from the audience

Not yet measured. `DESIGN.md` records the two required tests (radio cut and
near-final cut), the questions to ask, and explicitly marks the results as
pending. I have not written invented feedback. The storyboard change from a
bean to a speaking grandmother came from the creator, before either test.

## Hardest problem and how I solved it

One shot now contains two timed spoken lines from two voices, and five stages
need to agree on that timing. The fix was to define the shot's spoken order in
one place, `common.narration_clips()` + `narration_pads()`, and store measured
durations as `{"narrator": …, "grandmother": …, "total": …}`. `shots.py`,
`subtitles.py`, `radio_cut.py` and `assemble.py` all consume the same helper and
the same 0.35 s / 0.5 s gaps. `tests/test_timeline.py` checks offline that cue 2
starts after cue 1 plus the gap and that cue 3 starts at the next shot.

The second hard problem was that real Amharic speech ran far longer than the
8 s plan: the first complete assembly was 98.8 s, over the brief. With the TTS
daily quota exhausted, re-recording was not an option, so `pipeline/retime.py`
removes dead air at the ends of each clip and derives the smallest speed-up
that reaches an 86 s target, keeping the raw takes for comparison. Every stage
then re-reads the rewritten `durations.json`, so subtitles, video clips and the
audio mix stay aligned. Both exports measure exactly 86.0 s.

## A suggested practice that helped

The single JSON contract plus a validation step before generation. When the
storyboard changed, a schema update and one semantic check (proverb speaker
must be a defined voice and character) caught inconsistent data before any
paid or GPU-backed call. A deliberate bad speaker produced two clear errors in
`validate.py`, and a 7-shot probe was rejected as 59 s.

## A suggested practice that did not help as first written

The reference-approval gate stopped `make film` after reference generation and
awaited a hand-written `chosen.json`. That breaks the "clone → one command →
film" requirement. I kept `chosen.json` as the human override but added an
auto-selection fallback to `<char>_v1.jpg`, with the choice printed, so a clean
clone proceeds end to end.

## Curiosity beyond the floor

- A CLI-style regeneration path: `python pipeline/keyframes.py --shot shot_03`
  plus `make film`; `tests/test_rerun.py` checks that only that shot and the
  finals change, and that all 20 narration calls stay cached.
- Music is now a real validated stage (`pipeline/music.py`) rather than an
  empty stub, with cues read from the storyboard.
- Motion is derived from each shot's `motion_prompt` instead of a blind cycle.

## What I would build next

Run the radio-cut and near-final tests with three family members each and let
their comments change specific fields in `storyboard.json`; generate and audition
three ACE-Step candidates; generate Wan 2.2 clips for the two most static shots
and compare them blind against the FFmpeg fallback; then check Amharic
pronunciation of every proverb with a native speaker before publishing.
