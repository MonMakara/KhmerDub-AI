# Shared speech timing repair — 2026-10-31

This change applies to future projects through the ordinary speech-generation workflow;
it is not a database patch for the screenshot's project.

## Cause and implementation

Translation previously treated all time until the next cue as available speech time,
including pauses, and its batch-error fallback lost the timing budget. The TTS optimizer
only reported remaining shortages; it did not attempt a measured translation retry.
Warnings also included delay inherited from earlier speech, even when a sentence itself fit.

- `services/translation/timing.py` reserves 130 ms for pause/safety and limits translation's
  borrowing of long gaps to 350 ms. Both grouped and ordinary translation workers use it.
- OpenAI-compatible translation keeps each duration budget when falling back from batch
  JSON to individual requests.
- `services/dubbing/duration_repair.py` measures actual selected-voice pace and requests one
  concise, meaning-preserving candidate for each genuine local shortage. It uses the
  project's configured translation provider. It skips manually edited/outdated text and
  naturally fitting units delayed by earlier speech. No regex shortening is used by this retry.
- Candidate guards check numeric values, Latin identifiers and presence of negation.
  These are conservative checks, not semantic-equivalence verification.
- The existing TTS generator synthesizes the candidate with the same selected voice and
  normal speech-completeness inspection. Up to two immutable seeded attempts are allowed.
  Acceptance requires measured duration within the local window times 1.15; the existing
  scheduler retains its hard 1.25x cap. No clipping, forced truncation or higher speed cap.
- Candidate text and audio publish atomically under the existing text/voice revision checks.
  A manual edit during generation blocks replacement. Failed/overlong candidates preserve
  the current translation/audio; raw masters and prior text remain in generation manifests.
  Accepted translation explanations identify automatic timing rephrasing and request review.
- Batch TTS, individual regeneration, and the existing auto-fit action invoke shared repair.
  The worker's final scheduler still reports any genuine remaining conflicts.
- Voice UI offers **Fit Speech Timing** for current-but-conflicting speech and explains
  automatic timing checks. Inherited delay is labelled separately. Translation/audio/status
  refresh together when a speech job finishes.

## Real cloned-voice verification

Existing authorized Tasok worker was online on CUDA. No worker installation, voice profile,
consent record or reference recording was changed. The project's existing custom translator
and clone were used on separate copies of source units 67–69.

Isolated project: `ec7b1981-5f3d-4b06-840c-c88468e2be68`.
This fixture contains three audio/timing units, not a complete-video export.

| Original unit | Before raw speech | After raw speech | Final schedule |
|---|---:|---:|---|
| 67 | 3.24 s | 3.24 s, unchanged text/audio | Natural, no overflow |
| 68 | 5.47 s | 3.38 s | Natural, no overflow |
| 69 | 6.12 s | 3.72 s | Natural, no overflow |

Both requested candidate replacements passed measurement and publication. The shared
scheduler classified all three final units as natural at 1.0x. Original project translations
and source recording SHA256s were checked unchanged. Machine-aided meaning preservation
and acoustic plausibility are not a substitute for human listening/semantic review.

Reproduction: `python -m scripts.accept_future_timing` inside the existing backend Docker
container creates a separate acceptance project. It does not repair the source project in place.
Raw before/after evidence is in `future-project-timing-evidence/acceptance.json`.

## Limits

This reduces avoidable future overflows; it cannot guarantee every translation fits.
Manually approved translations stay unchanged. NLLB does not provide meaning-aware revision,
so its originals remain intact and unresolved timing stays visible. Provider outages,
unsafe candidates, failed synthesis and true content-density shortages also stay flagged.
Automatic retries add provider calls and synthesis time for affected segments.

No human listening or complete-video export was performed for this change. Browser
verification encountered an unavailable in-app browser connection; frontend compilation
was verified separately. The original project was not batch-regenerated or modified.

Tests cover pause budgets, protected tokens, atomic acceptance/rejection, selected voice,
manual edits before/during inference, unsupported rewriting, and automatic batch invocation.
Final isolated Docker backend suite: **452 passed, 1 skipped**, two deprecation warnings,
62.94 seconds. Final Docker frontend TypeScript/Vite build passed; existing bundle-size
advisory remains. Test and build logs are stored in `future-project-timing-evidence/`.
