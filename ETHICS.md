# Ethics, consent, licences and labelling

## Consent record

| Person / likeness | Status |
|---|---|
| Grandmother character | Fictional hand-painted cartoon built from a character sheet. No real person's face is uploaded, cloned or reproduced. |
| Narrator and grandmother voices | Synthetic Gemini TTS prebuilt voices (`Puck`/`Sulafat`, with fallbacks). No voice cloning and no imitation of a real person's voice. |
| Family members shown in the final wide shot | Generic silhouettes, no identifiable real people. |

No consent form is required for the current film because no real person's
likeness or voice is used. If a relative's real face or voice is added later,
record their informed, signed consent here **before** generating that material,
including the exact words they agreed to.

## Labelling

- The film ends with a 3-second visible card reading **"Made with AI"**, from
  `storyboard.json` (`end_card.text`).
- On YouTube/TikTok/Meta, switch the platform's AI-generated-content label on.
- Keep provider watermarks and provenance (SynthID, C2PA) intact when exporting
  and re-uploading; do not crop or strip them.
- The public post should say plainly that the film was generated with a
  multi-model code pipeline.

## Model and output licences

| Tool | Licence / terms relevant here |
|---|---|
| Gemini text + `gemini-3.8-flash-tts` | Google Gemini API terms, free tier; synthetic voices, no third-party voice cloning. |
| FLUX.2 klein 4B via Cloudflare Workers AI | Apache 2.0 weights; Cloudflare service terms for calls. |
| Wan 2.2 TI2V-5B | Apache 2.0. |
| ACE-Step 1.5 | MIT; outputs may be used commercially; trained on licensed, royalty-free and synthetic data. |
| FFmpeg | LGPL/GPL depending on build; used locally for deterministic assembly. |
| Storyboard, prompts and code | Authored in this repository; no living artist is named in style prompts (the style block describes qualities only). |

## Private data

The story contains no addresses, phone numbers or private family records. The
prompts describe generic Ethiopian highland settings and proverbs already
publicly told in the family. Avoid sending identifying documents or private
details to free hosted endpoints, which may use inputs for training.
