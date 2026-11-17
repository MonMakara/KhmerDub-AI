# KhmerDub AI repair verification — 2026-10-31

Technical repair and full-video export completed. Human speech-quality approval remains outstanding.

## Source and isolation

- Selected source: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/uploads/aa4afefc-ae6d-434d-ab84-caeeea0b30c9/A_Wise_Man_Taught_a_Lost_Boy_About_Choosing_Himself.mp4`
- Size: 46,953,991 bytes; H.264 video and AAC audio. Audio language tag is undefined; full English narration was recognized by Faster-Whisper.
- Source container duration: 175.426757 seconds.
- Source SHA-256: `311dfe4aaca4fd10a8a661e78567dadffee1c339fb28bd4f1e88a6d998b17d7e`.
- Isolated final project: `368534c5-040d-4821-b50a-c408bf93a043`. The source path was discovered from disk and explicitly selected by the user.
- Fresh legacy-baseline project: `31149c6c-7dab-4285-b3b3-6d4c567697aa`.
- Existing user projects were not used as reusable acceptance records. Their data was left in place. Both fresh test projects and every pacing trial have been retained.
- Branch: `cleanup/codebase-organization`; extensive uncommitted changes existed before this repair. No commit, database reset, volume deletion, model deletion, or storage cleanup was performed.
- The existing host VoxCPM worker was started with explicit user authorization as an exception to Docker-only execution. Backend/frontend verification ran inside Docker. No new large recognition model was installed.

## Confirmed causes and corrections

| File / function | Reproduction and actual behavior | Correction |
|---|---|---|
| `backend/app/workers/tts.py::synthesize_segment_audio` | Retry reused the selected file path before comparing durations; a shorter or failed retry could overwrite bytes while metadata described the first take. Longer duration was treated as evidence of completeness. | Separate preserved candidates, bounded retries, technical inspection for VoxCPM, actual duration measurement, first acceptable take, atomic publication, preserved text/voice/revision evidence. |
| `backend/app/services/tts/voxcpm.py::synthesize` | Intermediate lossless WAV was discarded after MP3 encoding. | Preserve the WAV master next to each synthesis attempt. |
| `backend/app/services/voice/worker.py::_run_inference` and `voice/generation.py::validate_generation_length` | Installed VoxCPM2 yields the last bad case after its internal bounded retries, including a generation-limit result. Wrapper discarded feature metadata. | Reject detected absolute/bad-case generation limits in both normal and memory-retry inference paths. Passing this check does not prove every word was spoken. |
| `backend/app/services/dubbing/speech_guard.py::inspect_speech_audio` | Digital silence has RMS `-inf`, which the numeric regex did not recognize; decoder failure was ignored. | Recognize negative infinity, require measurable energy and successful complete decoding. |
| `backend/app/services/transcription/segmentation.py::segment_transcript` | Missing word alignment was replaced by estimated word times; zero-duration word objects were modified in place. | Preserve unaligned text and original boundaries, retain uncertain ASR word times, mark review/approximation explicitly, and preserve aligned runs in order. |
| `backend/app/services/dubbing/timing_optimizer.py::optimize_project/optimize_speech_tempo` and `auto_fit.py::auto_fit_project` | Automatic regex rewriting changed translations; acceleration overwrote files later treated as raw. | Preserve text and raw audio; use measured scheduling variants, with explicit remaining shortages. No automatic semantic deletion. |
| `backend/app/services/dubbing/scheduler.py::schedule_timeline/_measure_variant` | Scheduling used duration/speed predictions. Local-slot warnings ignored already allocated slack. Group refinement could accelerate naturally fitting takes. | Measure rendered variants from raw files, cache atomically, preserve natural takes at 1.00x, cap speed at 1.25x, account for real allocated space, and preserve local alignment warnings separately from hard group overflow. |
| `backend/app/services/video/ffmpeg.py::get_audio_duration` and `dubbing/synchronizer.py::generate_silence/synchronize` | Full-video waveform audit initially found poor per-unit alignment despite a valid whole-track decode. Duration measurement rounded to 0.01 s; silence had a 0.01 s minimum. | Use PCM frame counts, unrounded duration values, exact sample-count silence, sample-aligned start times, and the same rendered pieces for scheduler and mixer. Final per-unit correlation exceeds 0.999004. |
| `backend/app/services/dubbing/exporter.py::export` | `-t` could cut the soundtrack to the expected duration. | Remove duration cutoff; verify the full output. Oversized soundtracks fail verification rather than being cut. |
| `backend/app/workers/dubbing.py::process_dubbing`, pipeline and export endpoint | Running worker requested non-strict scheduling; translation freshness was not independently enforced in every export path. | Enforce strict hard schedule deadlines and reject stale translations/audio. |
| `backend/app/api/endpoints/projects.py::get_export_status` and frontend timeline/workspace/export views | Timeline displayed raw-duration/original-slot ratios as applied speeds and mapped grouped speech by transcript order. | Expose measured unit schedules; render grouped speech independently; display actual speed/placement, correct unit counts, and visible alignment warnings. |
| `backend/app/services/translation/prompts.py` | Short-style guidance emphasized core meaning without explicitly preserving every detail. | Explicitly preserve names, numbers, negations, conditions, instructions, details and order; budgets remain advisory. |

## Full-video workflow and evidence

The entire 175.426757-second original was extracted, freshly transcribed with word times, segmented, translated through the existing configured custom provider, and synthesized using the authorized Tasok profile. The raw transcript is retained in the isolated project. The 424 recognized word records match the segmented sequence exactly; none has an inverted or zero-duration interval in this run. Transcript segments remain separate from the 39 synthesis units.

Seven bounded same-text pacing trials were selected in the isolated test project; all original takes, rejected trials, exact text, selected voice and trial decisions remain preserved in `pacing_trials/trials.json`. Selection used the first technically acceptable candidate meeting scheduling criteria, rather than ranking takes by shortest duration. No wording was changed by the pacing trial.

All selected raw takes and all final processed variants passed technical speech inspection. Both complete MP4 streams decoded successfully. The exported compressed video stream hash equals the source video stream hash. Every one of the 39 exported utterance waveforms was checked against its scheduled rendered recording. Minimum per-unit correlation: 0.999003759; full soundtrack correlation: 0.999468772. These are audio-preservation measurements, not lexical or perceptual speech-quality scores.

## Before / after measurements

The before column uses the fresh full-video legacy run. Legacy optimization replaced audio and could rewrite text, so its reported natural/raw/speed values are not comparable with preserved-master values. No timing-conflict reduction is claimed: both completed runs reported zero blocking conflicts. The existing user project also reported zero at initial inspection (37 transcript/TTS units, 168.17 seconds stored audio).

| Metric | Before | After |
|---|---|---|
| Actual video filename | A_Wise_Man_Taught_a_Lost_Boy_About_Choosing_Himself.mp4 | A_Wise_Man_Taught_a_Lost_Boy_About_Choosing_Himself.mp4 |
| Source duration | 175.426757 s | 175.426757 s |
| Recognized English words | 424 | 424 |
| Transcript segments | 40 | 40 |
| Khmer TTS units | 39 | 39 |
| Raw TTS total duration | Not reliably comparable: legacy optimization overwrote generated audio | 178.110 s (measured unaccelerated files; MP3 framing included) |
| Natural-speed units | 28 reported after legacy mutation | 23 |
| Speed-adjusted units | 11 reported after legacy mutation | 16 |
| Suspected incomplete selected units | 0 technical flags; lexical status unverified | 0 |
| Blocking timing conflicts | 0 reported | 0 |
| Total unresolved physical overflow | 0 reported | 0.000 s |
| Maximum physical overflow | 0 reported | 0.000 s |
| Maximum applied speed | Not reliably recoverable from mutated legacy metadata | 1.25x |
| Mean absolute start deviation | Not recorded | 0.277125 s |
| Maximum absolute start deviation | Not recorded | 0.961882 s |
| Visible alignment-review units | Not separately exposed | 3 |
| Unintended scheduled overlaps | Not independently audited | 0 |
| Final MP4 duration | 175.43 s reported | 175.430000 s |
| Export status | Completed (legacy pipeline) | completed |
| Khmer exact word completeness | Human listening required | Human listening required |
| Naturalness | Human listening required | Human listening required |

## Alignment review retained

Original phrase slots are soft within bounded conversational groups. A complete non-overlapping measured group must meet its hard deadline. Source-relative displacement and local-window use remain visible warnings; they are not represented as a physically impossible soundtrack when the measured group fits.

| Unit | Scheduled start offset from source | Neighboring timeline use |
|---|---:|---:|
| 9 | -0.500000 s | 0.932 s |
| 10 | +0.962000 s | 0.000 s |
| 14 | -0.386000 s | 0.080 s |

These three units require visual/listening review, particularly the transition from units 9 to 10. Scene-boundary analysis was not performed, so scene correspondence is not certified.

## Output

- Full exported MP4: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/368534c5-040d-4821-b50a-c408bf93a043/output/dubbed_khmer.mp4`
- Raw transcript: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/368534c5-040d-4821-b50a-c408bf93a043/asr_raw.json`
- Acceptance measurements: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/368534c5-040d-4821-b50a-c408bf93a043/acceptance_report.json`
- Per-unit schedule, full stream probes, audio inspections and waveform audit: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/368534c5-040d-4821-b50a-c408bf93a043/output/full_export_audit.json`
- Pacing comparisons: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/368534c5-040d-4821-b50a-c408bf93a043/pacing_trials/trials.json`
- The final MP4 retains the full original video stream. Container duration: 175.430000 seconds. Original container duration: 175.426757 seconds.

## Verification

- Initial backend baseline: 374 passed, 1 skipped (VoxCPM worker was offline).
- Final Docker backend suite: 387 passed; 2 dependency deprecation warnings.
- Frontend TypeScript: passed inside Docker.
- Frontend production build: passed inside Docker; existing bundle-size advisory remains.
- Real FFmpeg tests cover exact waveform placement, fractional-duration gaps, immutable variants, cap/overflow enforcement, silence rejection, full export duration and refusal to truncate an oversized soundtrack.
- Backend source is bind-mounted and the service was restarted. Frontend uses the current bind-mounted source and passed a production build.
- Browser project loading, measured speeds, 39/39 speech units, zero blocking conflicts, three visible alignment warnings, and final export controls were checked. Final application-triggered export completed through the browser. The project displays Completed, 39/39 current speech units, 23 natural-speed units, 16 adjusted units, zero blocking conflicts and three retained alignment warnings. Its normal export job completed successfully.

## Limitations and human review

Exact English recognition and word boundaries were not verified by human listening. One recognized phrase around 54.9 seconds reads “said an old wise man”; it is retained as recognized, with wording review outstanding. No timestamps were invented to conceal this uncertainty.

No human Khmer listening was performed. Lexical completeness, pronunciation, semantic equivalence, repetitions, naturalness and voice similarity remain unverified. Technical checks detect known failures and preserve the selected recordings; they cannot certify that every intended word was spoken. The existing configured translation provider produced fresh translations in each isolated run, so before/after linguistic content is not a controlled identical-translation comparison.

The installed VoxCPM2 inference interface provides no native speaking-rate parameter. Pacing uses conservative measured pitch-preserving variants. Translation duration predictions retain the existing rough character-rate guidance; a newly calibrated voice-specific predictor was not introduced.

No unrelated phase or feature was started. The user must approve any commit. The working tree already contained many edits and untracked files; aggregate Git diff statistics include that pre-existing work and must not be attributed entirely to this repair.

## Git diff summary

The repair touches TTS retry/master handling, VoxCPM completion checks, speech inspection, segmentation uncertainty, translation guidance, measured scheduling/mixing, export safety, and the studio timeline/readiness display. Three new regression files cover retry integrity, measured waveform scheduling and generation caps; existing tests were updated to preserve uncertain ASR evidence and to distinguish soft phrase boundaries from hard schedule deadlines. Three new scripts retain full-video acceptance, bounded pacing-trial and per-unit export-audit evidence. Browser evidence is saved in `docs/verification/tts-repair-browser.jpg`.

No commit was created. Current tracked working-tree diff: 81 files changed, 1,762 insertions and 783 deletions. Those aggregate statistics include the extensive edits that existed before this repair; new untracked files are additional.
