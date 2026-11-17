# Per-segment voice selection — implementation and verification

Completed 31 October 2026 (Asia/Phnom_Penh). Scope: existing project dubbing units, existing voices, default inheritance, individual/bulk overrides, safe regeneration and export. No new provider/model, dependency installation, Phase 14 work, database reset or commit.

## 1. Files and functions changed

| File | Relevant changes |
|---|---|
| [project models](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/models/project.py) | Optional voice identity, source assignment provenance, selection revision and generation error on TranslationSegment; accepted voice revision on GeneratedAudio. |
| [migration b2c3d4e5f607](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/alembic/versions/b2c3d4e5f607_add_segment_voice_overrides.py) | Additive upgrade from existing head; old rows inherit defaults, old audio retains null revision. |
| [project schemas](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/schemas/project.py) | SegmentVoiceUpdate/BulkSegmentVoiceUpdate; selected/effective voice, revision and error response fields. |
| [selection service](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/services/tts/selection.py) | effective_voice, voice_catalog, validate_voice, source_keys, preserve_partition, voice_aware_groups, set_unit_voice, audio_matches_selection. |
| [project endpoints](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/api/endpoints/projects.py) | Individual/bulk save and Khmer catalog; inherited-only project default invalidation; effective voice response metadata; regeneration/error/freshness handling; split/merge/resegmentation safeguards. |
| [TTS worker](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/workers/tts.py) | Per-unit provider resolution and validation, conditional revision/text publication, immutable accepted recordings, targeted resume and persistent errors. |
| [translation worker](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/workers/translation.py) | Source-based override propagation and voice-aware grouping; avoid attaching saved assignments by ordinal. Preserve unmatched manually edited Khmer as outdated rather than deleting it during cleanup. |
| [transcription worker](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/workers/transcription.py) | Check that saved assignment provenance survives before replacing the transcript. |
| [grouper](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/services/dubbing/grouper.py) | Separate synthesis units at differing saved voice boundaries; carry the override on group definitions. |
| [dubbing pipeline](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/app/services/dubbing/pipeline.py) | Check audio selection freshness before export and verify selection/text/audio snapshots after rendering before marking export current. |
| [VoiceTab](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/frontend/src/components/studio/VoiceTab.tsx) | Per-unit selectors, checkboxes, bulk apply/reset, availability, selected/recorded distinction, saving/error status and targeted Generate/Regenerate. Removed hardcoded fallback voice list from this component. |
| [ProjectWorkspace](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/frontend/src/pages/ProjectWorkspace.tsx) | Fetch project Khmer catalog, save overrides and refresh affected audio/readiness, refresh errors after regeneration, show failed default saves. |
| [frontend types](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/frontend/src/types/index.ts), [API client](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/frontend/src/services/api.ts) | Add voice selection contracts, catalog and bulk API calls. |
| [new regression tests](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/tests/test_segment_voice_selection.py) | 22 collected cases, including parameterized cases, covering the new behavior and races. |
| [retry tests](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/tests/test_tts_retry_integrity.py), [custom voice tests](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/tests/test_voxcpm_integration.py) | Authorized fixture for post-generation consent check; immutable accepted-path assertion; explicitly online mocked worker for mocked custom synthesis tests. |
| [acceptance script](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/scripts/accept_mixed_segment_voices.py), [export audit](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/backend/scripts/audit_selected_video_export.py) | Isolated real-video prepare/generate/verify workflow; allow the existing full-stream/per-unit audit to inspect the mixed-voice acceptance project. |

The working tree already contained substantial earlier repairs. Those pre-existing edits were preserved; this report lists the additional feature work rather than claiming ownership of the entire diff.

## 2. Database changes

Migration head: `b2c3d4e5f607`, applied successfully through Docker Alembic.

Added to `translation_segments`:

- `voice_override_provider`: nullable provider identity.
- `voice_override_id`: nullable registered voice/profile identity; custom choices use profile UUIDs.
- `voice_source_keys`: nullable JSON of stable source-word occurrence IDs, with member segment IDs for older unaligned data.
- `voice_revision`: non-null integer, default/server default 0; incremented on selection changes, including reset and inherited default changes.
- `tts_error`: nullable last generation failure.

Added to `generated_audios`: nullable `voice_revision`, identifying the accepted selection revision.

No project, transcript, translation, audio, profile or consent row was removed by this migration. No existing project was assigned an override. Existing recordings with null revision remain supported under the unchanged inherited-selection policy; changing selection invalidates them and requires regeneration.

## 3. API changes

| Method / endpoint | Behavior |
|---|---|
| `GET /api/projects/{project_id}/segment-voices` | Dynamic Khmer-compatible registry voices and profile IDs, including disabled entries explaining offline/inactive/missing-consent status. |
| `PATCH /api/projects/{project_id}/translations/{segment_id}/voice` | Save one override, or reset with both fields null. Returns enriched translation/unit. |
| `PATCH /api/projects/{project_id}/translations/voices` | Atomic bulk update for `segment_ids`, `provider`, `voice`; validates every unit belongs to the project before writing. |
| Existing `PATCH /api/projects/{project_id}/voice` | Retained project default; invalidates inherited units while preserving explicit overrides. |
| Existing TTS/regenerate/readiness/export endpoints | Resolve each unit separately, expose voice metadata/revision/error, reject stale recordings and prevent older in-flight generation from becoming current. |

Individual example:

```json
{"provider":"edge","voice":"km-KH-SreymomNeural"}
```

Bulk reset example:

```json
{"segment_ids":["unit-id-1","unit-id-2"],"provider":null,"voice":null}
```

English-only voices, unknown provider/profile IDs, incomplete provider/voice pairs, offline custom voices and missing/revoked consent are rejected. No silent substitute voice is selected. New custom assignments require registered IDs, not display names. Legacy named/prefixed custom project defaults can resolve to their registered profile identity without rewriting the project.

Voice changes are allowed during TTS with revision protection. They return 409 during active export/transcription/translation so source/voice changes do not race those operations. Generation rechecks authorization before accepting custom speech. Standard-voice validation does not probe an unrelated offline custom worker.

## 4. Frontend improvements and browser verification

The existing Voice tab retains project default cards and adds a selector to every Khmer dubbing unit before audio exists. Rows show Khmer text, selected/effective voice, availability, generated-recording voice, current/outdated state, generation error and audio preview. Selectors use the dynamic Khmer registry; English-only options are excluded.

Checkboxes support applying a voice to selected units and resetting selected overrides to inheritance. Selection saves automatically; failures remain visible. The unit's Generate button works before project-wide synthesis. Regenerate uses the existing targeted path.

Actual browser checks on the isolated acceptance project:

- Saved a different voice for unit #52 while its audio had not yet been generated and the batch was processing earlier units.
- Reset that unit to project inheritance, then used bulk selection to restore the planned saved Sreymom override for units #50/#52.
- Refreshed the page and confirmed the saved selection persisted.
- Reset generated unit #1 to inheritance; its selected label became Piseth while its old recorded label remained Sreymom and only its audio became outdated.
- Used the row's Regenerate control; it then displayed recorded Piseth/current audio.
- Switched Translation → Voice and confirmed the saved assignments remained.
- Reopened the project in a fresh browser tab; unit #1 inherited Piseth and unit #2 retained Sreymom, both with matching current recordings.
- Verified Tasok was visible but disabled with “Voice worker offline.” Missing/revoked consent behavior was tested with disposable backend fixtures, without changing the user's consent record.

Evidence:

![Inherited Piseth and overridden Sreymom with matching current recordings](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/docs/verification/segment-voices-browser.jpg)

[Selected/recorded mismatch before targeted regeneration](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/docs/verification/segment-voice-outdated-browser.jpg).

## 5. Supported voice list

| Voice observed | Provider | Current status |
|---|---|---|
| Microsoft Piseth | Existing Edge Khmer voice | Used for 26 full-video units. |
| Microsoft Sreymom | Existing Edge Khmer voice | Used for 26 full-video units. |
| Tasok | Registered VoxCPM2 profile UUID | Authorized profile preserved; worker offline, disabled; real synthesis not tested. |

Other registered Khmer-compatible profiles automatically appear through the existing registry/profile data. English Aria/Guy remain available in their existing English toolkit contexts but are excluded from Khmer unit selection. Google gTTS remains compatibility-only and was not restored as a selectable voice.

## 6. Default-voice behavior

Null override means the unit inherits the project's provider/voice. New projects still default to Piseth. Choosing an explicit override freezes that unit's voice independently of future project default changes. Resetting both override fields to null returns it to inheritance.

A default change increments selection revisions and invalidates only inherited units' recordings. Explicit overrides, Khmer wording and source timestamps are preserved.

## 7. Override persistence and source mapping

Assignments live on the translation/dubbing unit and include stable source identities. They are not attached solely to the displayed segment number.

Split children can retain the saved assignment through word occurrence identities; older member-ID assignments are expanded to cover both manual split children. Regrouping preserves separate synthesis units where neighboring assignments differ. A manual merge or resegmentation which would combine conflicting assignments returns an explicit conflict, requiring the user to align/reset those assignments first.

If a new transcription cannot be matched reliably to saved source identities, the operation refuses to guess; reset the affected overrides before replacing it. Retained manually edited Khmer is not deleted as incidental cleanup. These protections may require explicit source/translation review after substantial repartitioning.

## 8. Freshness and concurrency

Each generation captures the saved effective provider/profile ID, Khmer text and voice revision. The selected provider is resolved afresh for every unit; it is not carried over from the previous unit.

Raw candidate masters and metadata remain preserved. Accepted recordings use unique immutable paths. Publication performs a conditional database write against the captured revision/text and requires the source translation to remain current. A voice change away and back still increments revision, so an earlier take cannot slip through by matching the final display name. A failed or stale take cannot overwrite the previous accepted file.

The generated row stores actual provider/voice and accepted revision. Freshness checks use those fields as well as the existing outdated flags. Export validates selection freshness at entry and checks its snapshot again after slow rendering before marking its output current.

Tests use separate SQLite sessions to change override/default/text during provider execution, including away-and-back selection. They verify previous accepted bytes/pointers remain unchanged and obsolete generation is refused. Export has a separate mutation-during-render regression. These are deterministic contract tests; the browser's live batch selection check is additional UI evidence.

## 9. Mixed-voice timing verification

The timing engine and speed cap were retained. New accepted paths invalidate affected render-cache identities naturally; unchanged units keep their accepted files and reusable variants. The optimizer and mixer measure the newly selected voice's actual audio.

Final full-video measurements:

| Check | Result |
|---|---|
| Dubbing units | 52: 26 Piseth, 26 Sreymom |
| Units fitting at natural speed | 41 |
| Selectively accelerated units | 11 |
| Maximum applied speed | 1.25× |
| Unresolved physical timing conflicts | 0 |
| Unintended overlaps | 0 |
| Alignment-review units | 2; warnings retained |
| Largest original-start deviation | 0.888073 seconds |
| Processed technical inspections | 52 plausibly complete; 0 invalid/review-required |
| Minimum unit-to-export waveform correlation | 0.9998853 |
| Complete timeline-to-export correlation | 0.9999821 |

The two alignment warnings distinguish local original-slot alignment from physically fitting the full soundtrack. They have not been hidden. Signal checks establish transport/preservation of generated recordings, not word-for-word Khmer accuracy, pronunciation or human speaker identity.

## 10. Full real-video export

Discovered a valid current upload rather than relying on an old deleted repair project:

`When_Everyone_Says_Your_Dream_is_Impossible_-_Remember_the_Bamboo_Tree.mp4`

- Source duration: **193.793741 seconds**.
- Source SHA-256: `2bfba49a5d7aa920056577c7ede19d6c11e104502cf101aede02df299595fc19`.
- Isolated project: **`0dbe625f-6a12-4da8-8971-7ad153e8a4f4`**, `[Mixed voice acceptance] Bamboo Tree`.
- Copied the original video/audio, transcript and existing saved Khmer verbatim into the isolated project. Did not retranslate or alter the source project's wording/timestamps.
- Generated real Edge speech for all 52 units using saved mixed assignments, measured every recording and verified request/provider identity metadata.
- Exercised targeted regeneration in the script, then again through the browser. **All other 51 recordings retained identical paths and content hashes.**
- Final MP4: H.264/AAC, **193.790 seconds**, **38,168,017 bytes**. The approximately 3.7ms container-duration difference is not a missing utterance: full decoding and every scheduled piece were checked.
- Both output streams decoded fully with error checking. Compressed video-stream hash equals the source stream hash. All 52 processed utterances correlate with their scheduled exported soundtrack ranges.
- Source project snapshot, source video hash and source generated audio hashes were verified unchanged.

[Final mixed-voice MP4](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/0dbe625f-6a12-4da8-8971-7ad153e8a4f4/output/dubbed_khmer.mp4)

[Acceptance manifest](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/0dbe625f-6a12-4da8-8971-7ad153e8a4f4/mixed_voice_acceptance.json), [full export and per-unit audit](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/0dbe625f-6a12-4da8-8971-7ad153e8a4f4/output/full_export_audit.json), [pre-generation selections](/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/0dbe625f-6a12-4da8-8971-7ad153e8a4f4/mixed_voice_preparation.json).

## 11. Backend verification

Final actual Docker suite: **421 passed, 1 skipped**, 2 existing deprecation warnings. Log: `/tmp/segment-voice-complete-final-suite.log`.

Tests ran in a one-off Docker backend container with isolated `/app/data`, an isolated database and `HF_HUB_OFFLINE=1`; user projects/consent/reference media were not test fixtures. The optional real custom-generation test was skipped because the isolated test storage does not contain the user's authorized voice. Mocked custom tests explicitly declare mock availability and are not presented as real synthesis.

New coverage includes inheritance, override/provider resolution, persistence, atomic bulk updates, incompatible/offline/unauthorized selection rejection, targeted default/override invalidation, separate-session generation races, regeneration/resume, source-word mapping across repartitioning, split propagation, conflicting merge rejection, mixed-duration real FFmpeg scheduling, legacy audio/custom defaults, export freshness and a voice change during export rendering.

The backend was restarted after confirming zero active project jobs so the running application loads the final source. Alembic migration and live API/browser checks confirm the feature is available in Docker.

## 12. Frontend verification

- Docker TypeScript check: **passed**, `/tmp/segment-voice-complete-typecheck.log`.
- Docker production build: **passed**, `/tmp/segment-voice-complete-build.log`.
- Existing bundle-size advisory remains; no new dependency was added.
- Live browser workflow checks described in section 4 passed. No automated frontend test framework was added.
- `git diff --check` passed at verification. No commit was created.

## 13. Limitations and preserved data

- Tasok's real custom synthesis was **not tested** because its worker was offline. No worker/model installation or consent modification was performed. It becomes selectable when the existing authorized profile and worker are available; otherwise the UI/API reject generation explicitly.
- No human listening was performed. Voice identity is verified from selected/requested/returned registered identity metadata, not claimed as a perceptual identity assessment. Technical completeness checks do not prove that the model pronounced every approved Khmer word.
- A source change that cannot preserve assignment identity, or a proposed merge with differing assignments, requires explicit voice reset/alignment and translation review. The implementation intentionally avoids transferring assignments by ordinal guesswork.
- Existing legacy pipeline branches remain supported. Old recordings without selection revision use the compatibility policy until selection changes; new recordings carry revisions.
- Original user projects, uploaded videos, saved Khmer, voice profile and consent were preserved. The new acceptance project and evidence remain available for review. No new voice provider/model, unrelated audit repair or Phase 14 work was introduced.
