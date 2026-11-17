# Short natural transcript segmentation — verification, 2026-10-31

The complete original Bamboo Tree video was transcribed and segmented in a separate project. The selected Sentence mode now produces 65 segments with all 441 recognized source-word occurrences retained. No TTS generation, speaking-speed adjustment or synchronization redesign was performed for this task.

## 1. Original video and protection

- Filename: `When_Everyone_Says_Your_Dream_is_Impossible_-_Remember_the_Bamboo_Tree.mp4`
- Absolute path: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/uploads/0018b756-0169-4883-9c7d-d154c338802b/When_Everyone_Says_Your_Dream_is_Impossible_-_Remember_the_Bamboo_Tree.mp4`
- Size: 37,298,800 bytes. Video H.264; audio AAC.
- Original video duration, measured with FFprobe: **193.793741 seconds**. Extracted 16 kHz PCM audio: 193.79375000 seconds (sample quantization).
- SHA-256 before and after: `2bfba49a5d7aa920056577c7ede19d6c11e104502cf101aede02df299595fc19`.
- The other current upload has the same filename, size and SHA-256. They are identical source content; no deleted project was used.
- Isolated acceptance project: `8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933`, titled `[Segmentation acceptance] Bamboo Tree`.
- Existing user projects, transcripts, Khmer translations, generated audio and Tasok voice data were not changed by the acceptance workflow. The new project points read-only to the original video and has its own extracted audio and transcript evidence.

## 2. Confirmed defects

1. Sentence mode defaulted to a 6.5-second limit, and long-phrase scoring could choose still later boundaries. The full-video baseline had seven Sentence segments longer than five seconds.
2. Dubbing mode merged short sentences across terminal punctuation. This removed genuine boundaries in short independent utterances.
3. Grammatical and expression protection used penalties that other scores could outweigh. There were no explicit number/unit or multi-token Rubik notation protections.
4. Completely unaligned text was divided proportionally into estimated sentence times, despite a lack of acoustic evidence. Manual splitting without word alignment did the same.
5. Source words had no persistent occurrence IDs. Counts/string comparisons alone could not demonstrate assignment integrity for repeated words.
6. Word times were rounded before persistence, and the frontend independently floored fractional milliseconds. Actual model values such as 123.439999… displayed as 02:03.439 rather than 02:03.440.
7. Applying a new partition retargeted existing translations by row order and deleted excess translation rows. This could pair approved Khmer with different English content.
8. Subtitle invalidation considered text hashes, which could miss a timing-only source change. Edited text could also be split using its old word alignment and silently restore the old recognized wording.

## 3. Algorithm before and after

Original mode keeps the recognizer's original segmentation and text. New provenance is additive; the raw mode remains 27 segments for this recording.

Sentence and Dubbing modes now prefer word-attested phrase boundaries near three seconds, with a one-second preferred minimum and five-second soft maximum. Both respect sentence punctuation and actual pauses. Dubbing uses a slightly shorter pause threshold. Hard exclusions protect incomplete grammatical endings, known multiword terminology, number/unit expressions and adjacent Rubik move tokens. A known expression may exceed a soft limit rather than being cut internally.

Short independent sentences remain separate. Pause splitting is rejected if it would orphan the short final word of the same clause. For example, the 0.3-second tail “nothing.” was retained with its clause, while the independent 0.7-second sentence “Then dream.” remains intact with its actual interval. No silence was added to reach a preferred length.

Unaligned legacy text keeps its complete recorded interval and is marked uncertain. No proportional sentence times are generated. Splitting without alignment, or splitting human-corrected text using mismatched old word alignment, returns a clear error requesting alignment review.

## 4. Word identity and timing

Source occurrence IDs are deterministic from source-audio identity, recognized position, text and original interval. Segmentation does not change them. New transcript row IDs are deterministic from ordered word identities and namespaced to each project. Reapplying unchanged boundaries retains segment IDs.

The API exposes source word IDs, source audio reference and actual duration. Existing `words_json` storage holds the additional word metadata; no schema reset or mandatory backfill of existing projects was needed. Legacy data remains readable.

The complete raw recognizer output is preserved. Segment start/end values inherit the first/last word interval without rounding or extension. Recognized word strings and punctuation are retained; whitespace is normalized when forming readable segment text.

After-run ID validation for all three modes found **441 assigned occurrences, zero unassigned occurrences, zero duplicate IDs, and unchanged order**. Word start order is chronological. There are no overlapping word intervals, overlapping transcript segments, or timestamps outside the original video in this test. The last recognized word ends at 193.360 seconds.

## 5. Complete-video before/after measurements

| Metric | Sentence before | Sentence after | Dubbing before | Dubbing after |
|---|---:|---:|---:|---:|
| Recognized words | 441 | 441 | 441 | 441 |
| Transcript segments | 56 | 65 | 51 | 70 |
| Average duration (s) | 2.839107 | 2.362923 | 3.171569 | 2.156714 |
| Minimum duration (s) | 0.700000 | 0.700000 | 1.180000 | 0.700000 |
| Maximum duration (s) | 5.920000 | 4.540000 | 5.420000 | 4.560000 |
| Segments over 5 seconds | 7 | 0 | 5 | 0 |
| Segments under 1 second | 1 | 1 | 0 | 1 |
| Overlapping transcript segments | 0 | 0 | 0 | 0 |
| Invalid word intervals | 0 | 0 | 0 | 0 |

Before/after recognized word sequences are identical. Stable word-ID assignment checks were unavailable in the old implementation; they are independently checked in the new implementation. These measurements demonstrate preservation and shorter natural boundaries, not correctness of every ASR word.

## 6. VAD and acoustic evidence

Faster-Whisper's installed cached `base` model processed the entire recording with word timestamps. The complete audio was also transcribed with VAD disabled. Both produced the same **441-word sequence**. No large recognition model was installed and no unverified decoding parameters were added.

A separate diagnostic using the installed speech detector with 200 ms minimum silence and zero speech padding found **87 speech regions**. No detected region was entirely without recognized word overlap. This is a region-coverage check: it cannot prove that every word inside a region was recognized or that quiet speech below the detector threshold was captured.

Beginning, middle and ending waveform panels overlay the actual audio energy and original word intervals. Per-word RMS measurements and all representative intervals are retained in the after-run JSON. This verifies timing inheritance and acoustic occupancy; exact word/phoneme boundaries and spoken content were not verified by human listening.

**11 low-confidence source words remain flagged and retained.** The uncertain IDs and probabilities remain in the raw and after-run evidence. In particular, the recognized wording near 157–161 seconds (“First, they make a strong…”) warrants listening review; no guessed correction was inserted.

## 7. Translation, TTS, subtitles and editing compatibility

- Transcript segments remain separate from synthesis units. The unchanged grouper mapped the 65 current transcript segments into **60 coherent TTS units**, with every transcript ID assigned once and no source-content omission or duplication.
- Existing approved Khmer is retained during user-requested resegmentation. Matching uses unchanged English source content and interval, rather than row number. Unmatched records keep their historical provenance and remain outdated for explicit review. Extra approved records are retained.
- Translation refuses to silently retarget outdated approved Khmer to a different new unit. No translations or audio were regenerated automatically.
- Cached subtitle cues are marked source-outdated when segmentation changes, including timing-only changes. The verified English SRT contains all 65 current cues using millisecond-rounded source boundaries.
- Editing marks old word alignment as uncertain and invalidates linked translations/audio. Unsafe splitting of changed text using old alignment is rejected.
- Regression tests cover export freshness guards and source mapping. Full-video TTS/export was deliberately not rerun: this task is transcription and segmentation only.

## 8. Running application verification

The backend was restarted while user processing was idle. Live API checks returned 65 Sentence segments, all 441 unique source word IDs, source audio references and exact stored durations. The running Dubbing preview returned 70 segments.

The browser loaded the complete source video and all 65 transcript rows. Actual media playback ranges began at **4.340, 95.900 and 188.820 seconds** after clicking the corresponding beginning/middle/ending transcript timestamps. The editor opened with the source text and saved unchanged text successfully; actual text changes and downstream invalidation are exercised by integration tests. The original user projects were not edited for these checks.

The frontend timestamp display now rounds correctly to the same millisecond convention used by subtitle export. Uncertain rows display an explicit “Alignment review” label.

## 9. Tests

- Docker backend suite: **399 passed, 1 skipped**, with two dependency deprecation warnings.
- Skipped test: optional VoxCPM custom-voice generation, because isolated test storage does not contain the user's authorized voice. The user's real clone was kept separate from test storage.
- New regression coverage includes exact repeated-word ID coverage, deterministic IDs, exact interval inheritance, long sentence splitting, short sentence preservation, orphan tails, final-word retention, Cube terminology/notation, number/unit protection, punctuation, silence gaps, subtitle timing, TTS mappings, approved translation preservation and unsafe edit/split prevention.
- Frontend TypeScript check: passed inside Docker.
- Frontend production build: passed inside Docker. Existing bundle-size advisory remains.
- The full backend suite used an isolated `/app/data` mount so test records and fixtures did not populate the live user database.

## 10. Files and functions changed

| File | Relevant functions / behavior |
|---|---|
| `backend/app/services/transcription/base.py` | WordTiming and TranscriptionSegment serialization; identify_source_words; project_segment_id |
| `backend/app/services/transcription/whisper.py` | transcribe: preserve model precision, confidence flags and source identity |
| `backend/app/services/transcription/segmentation.py` | segment_transcript, phrase splitting, hard boundary exclusions, validate_word_coverage, uncertain fallback, safe manual split/merge |
| `backend/app/workers/transcription.py` | Preserve occurrence coverage and persist stable project-scoped segment IDs |
| `backend/app/models/project.py` | Additive transcript provenance/duration properties |
| `backend/app/schemas/project.py` | Transcript response provenance fields |
| `backend/app/api/endpoints/projects.py` | Safe resegmentation mappings, stable row IDs, retained approved text, stale subtitle marking and edit uncertainty |
| `backend/app/workers/translation.py` | Block retargeting outdated approved Khmer by order |
| `backend/app/services/subtitles/service.py` | Respect explicit source-outdated flags even when text hashes match |
| `frontend/src/types/index.ts` | Optional transcript provenance metadata |
| `frontend/src/components/studio/TranscriptTab.tsx` | Millisecond rounding and alignment-review label |
| `backend/tests/test_short_natural_segmentation.py` | New segmentation and mapping regressions |
| Existing transcription/segmentation tests | Replace old expectations of fabricated times or merged independent sentences |
| `backend/scripts/verify_short_segmentation.py` | Fresh full-video baseline evidence |
| `backend/scripts/audit_short_segmentation.py` | Full-video after test, VAD comparison, subtitle and waveform evidence |

## 11. Evidence paths

- Baseline: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/segmentation_before.json`
- Final after-run report: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/segmentation_after_1793383444972010816.json`
- Raw transcription with IDs: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/asr_raw.json`
- English subtitles: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/verified_english.srt`
- Beginning/middle/end waveform evidence: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/original_waveform_boundaries.svg`
- Running API/browser measurements: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/data/projects/8e9f3b99-d78c-4f69-b1d9-bc9f16c3c933/running_app_verification.json`
- Browser screenshot: `/home/mark/Documents/MyDocuments/Projects/KhmerDub-AI/docs/verification/short-segmentation-browser.jpg`

## 12. Limitations

Human listening was not performed. ASR accuracy, missing/repeated/hallucinated source words, quiet speech below detector thresholds and exact acoustic word boundaries are not certified by these checks. All uncertain recognized words remain available for review. No forced-aligner or larger ASR model was installed.

Expression protection is deterministic and covers the known terminology and notation exercised by the tests. It is not an unrestricted linguistic parser for every possible technical expression or grammatical construction. Soft duration targets yield to protected expressions and genuine standalone short utterances.

## 13. Git diff and scope

The working tree already contained substantial uncommitted repairs and unrelated edits. The files above describe this task's scope; aggregate Git statistics include that pre-existing work. No commit was made. TTS speed controls and synchronization were not redesigned or changed by this task. No Phase 14 work was started.
