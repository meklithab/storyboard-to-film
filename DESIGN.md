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

The **audience tests** then raised four presentation issues: the grandmother
did not look Ethiopian / Habesha, the images were too vague to show what was
happening, the film began without context, and the horizontal export was a
reframed vertical video. The contract was revised again: the character
reference now names highland features and clothing, every shot prompt includes
setting, action, background and light, a 4 s intro states the premise before the
first line, and the pipeline makes a genuine 16:9 cut from its own wide
keyframes. These changes came directly from the audience findings recorded
below.

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

Both tests required by the brief were conducted: the radio-cut session and the
near-final visual session. The findings below are paraphrases of what the
audience said; they are not invented verbatim quotes.

| Test | Audience finding | Field or file changed |
|---|---|---|
| Radio cut / near-final | The grandmother did not look Ethiopian / Habesha. | `characters[*].description`, `characters[*].reference_prompt`, all reference sheets and keyframes |
| Near-final | The shots were not descriptive enough. | All `shots[*].image_prompt` fields, plus `reason` and `shot_size` added to the generation prompt |
| Near-final | There was no setup before the first line. | New `intro` block in `storyboard.json`; new intro card in `pipeline/assemble.py` |
| Near-final | The horizontal version was not really horizontal. | New `format.horizontal_prompt_suffix`, wide keyframes/clips and an independent horizontal assembly path |

The most important change was the character rewrite. Because the audience did
not read the character as Ethiopian, the premise — recognising your own
grandmother in a proverb — could not work. The reference prompt was rebuilt with
deep warm-brown skin, high cheekbones, braided silver-streaked hair in a white
netela, gold hoop earrings and a white kemis with gold/red tibb embroidery, then
`make refresh_reference` regenerated the approved sheets and all dependent
shots.

## What the design changed so far

- Replaced the single narrator voice with two defined voices so grandmother
  "speaks" her own proverbs instead of being described.
- Added a 0.35 s pause between the setup and the proverb so the joke has time
  to breathe; both subtitles and the audio mix use the same timing.
- Kept the final gathering and the unity proverb as the payoff, matching the
  stated intent (warmth, not just comedy).
- Added a 4 s intro card so the premise is clear before the first proverb.
- Redrew the approved grandmother reference with explicit Habesha features and
  rebuilt all shots from it, instead of treating the first approved sheet as
  permanent.
- Replaced the blurred-letterbox horizontal export with an independently
  generated 16:9 composition.
