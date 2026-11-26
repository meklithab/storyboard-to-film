# Design: audience, intent and tests

## Brief (written before generation)

- **Audience:** my family and friends, watching on their phones (vertical first).
- **Where:** shared in a family chat and on social feeds; sound on, subtitles visible.
- **Intent:** they should laugh at the everyday mishaps, recognise their own
  grandmother in a proverb for every situation, and end warm about the family
  sitting together over coffee.
- **Logline:** whatever goes wrong, my grandmother has a proverb ready, and in
  the end the whole family sits together over her coffee.
- **Intentional constraint:** one recurring character (grandmother), one visual
  style block, warm hand-painted cartoon look, 10 shots at about 8 s each.

## Why this storyboard changed

The first storyboard followed a coffee bean through picking, roasting and
grinding ("The Little Bean"). The creator replaced it with a proverb-led story
about a grandmother. That change moved the film from a narrated object joke to
a recognisable family voice: every shot now has two beats — a situation the
grandchild describes, then grandmother's proverb answering it. The pipeline was
changed with it: `voices`, per-shot `proverb`, 20 narration calls/20 subtitles,
and the narrator→proverb gap in the shared timeline.

## Shot reasons

Every shot carries a `reason` field in `storyboard.json`; the contract is
summarised here so the intent is visible without the JSON:

| Shot | Why it exists |
|---|---|
| 01 | Introduce grandmother and the running joke; seedling impatience → "slowly, slowly". |
| 02 | A rained-off picnic turns useful; "everything happens for the best". |
| 03 | Gold tested by fire; hardship reveals strength. |
| 04 | A long walk; "whoever keeps going, arrives". |
| 05 | Patient practice; "patience is bitter, its fruit is sweet". |
| 06 | Falling off a bicycle and getting back up; the proverb in action. |
| 07 | Temptation to gossip; "silence is golden". |
| 08 | Sharing a small meal; "one who shares never lacks". |
| 09 | Coffee ceremony begins; the warm centre of the film. |
| 10 | Everyone together; "when spiderwebs unite, they can tie up a lion". |

## User tests

Two tests are required by the brief. They are **planned, not yet recorded** in
this repository; this section will be filled with actual quotes and the
resulting storyboard changes after each session. Nothing below is presented as
feedback that was received.

1. **Radio cut (cheap prototype).** Show `outputs/final/radio_cut.mp4` (black
   screen, both voices) to at least three people from the audience. Ask what
   they understood, which proverb landed, and where they lost interest. Record
   the exact comments here and change `storyboard.json` before generating
   keyframes.
2. **Near-final cut.** Show both aspect ratios with music, subtitles and end
   card to three (ideally different) people from the audience. Ask whether the
   grandmother looks consistent, whether the proverbs feel earned, and whether
   the ending lands. Record comments and the exact storyboard fields changed.

## What the design changed so far

- Replaced the single narrator voice with two defined voices so grandmother
  "speaks" her own proverbs instead of being described.
- Added a 0.35 s pause between the setup and the proverb so the joke has time
  to breathe; both subtitles and the audio mix use the same timing.
- Kept the final gathering and the unity proverb as the payoff, matching the
  stated intent (warmth, not just comedy).
