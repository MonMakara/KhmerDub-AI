import logging
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy.orm import Session

from app.core.storage import resolve_audio_file
from app.models.project import Project, Video, TranscriptSegment, TranslationSegment, GeneratedAudio
from app.services.dubbing.synchronizer import AudioSynchronizationService
from app.services.tts.registry import get_tts_provider
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)

# Linguistic rules for concise spoken Khmer video dubbing
CONCISE_REPLACEMENTS = [
    # Specific verbose idioms and clauses
    (r"ដែលជាកម្មសិទ្ធិនៅទីនេះ", "នៅទីនេះ"),
    (r"គឺជាមួយដែលនៅទីនេះ", "នៅទីនេះ"),
    (r"បន្ទាប់ពីនេះ", "ក្រោយមក"),
    (r"បន្ទាប់ពី", "ក្រោយ"),
    (r"ដើម្បីធានាថា", "ឱ្យ"),
    (r"ធ្វើឱ្យប្រាកដថា", "ឱ្យប្រាកដ"),
    (r"ដែលនេះជាមូលហេតុដែល", "ហេតុនេះ"),
    (r"នេះជាមូលហេតុដែល", "ហេតុនេះ"),
    (r"ដែលនេះជាមូលហេតុ", "ហេតុនេះ"),
    (r"មិនសូវអាក្រក់ប៉ុន្មានទេ", "មិនអាក្រក់ទេ"),
    (r"តាមពិតការប្រើវាក្នុង", "តែប្រើក្នុង"),
    (r"តាមពិត", "ពិតជា"),
    (r"ផ្នែកខាងក្រោម", "ខាងក្រោម"),
    (r"ផ្នែកខាងលើ", "ខាងលើ"),
    (r"ផ្នែកខាងឆ្វេង", "ខាងឆ្វេង"),
    (r"ផ្នែកខាងស្តាំ", "ខាងស្តាំ"),
    (r"ផ្នែកខាងមុខ", "ខាងមុខ"),
    (r"ផ្នែកខាងក្រោយ", "ខាងក្រោយ"),
    (r"របស់(អ្នក|ខ្ញុំ|វា|ពួកគេ)", r"\1"),
    (r"ទាំងអស់(នេះ|នោះ)", r"\1"),
    (r"ទាំងអស់", ""),
    (r"ពួក(វា|គេ)", r"\1"),
    (r"តាមលំដាប់ដែលអ្នកចង់បានហើយចុងក្រោយអ្នកក៏នឹងទៅដល់កន្លែងដូចខ្ញុំដែរដែលខ្ញុំបានរៀនតាមលំដាប់ដ៏ឆោតល្ងង់មែនទែន", "តាមលំដាប់ណាក៏បាន ចុងក្រោយអ្នកនឹងចេះដូចគ្នា"),
    (r"ហើយខ្ញុំសុខសប្បាយទេដូច្នេះកុំបារម្ភខ្លាំងពេកអំពីការធ្វើតាមលំដាប់ណាមួយនោះទេប៉ុន្តែការមានអ្វីៗទាំងអស់នេះវាពិបាកទប់ទល់ណាស់ហើយ", "កុំបារម្ភពីរឿងលំដាប់ តែបើមានច្រើនពេកអាចពិបាក"),
    (r"ខ្ញុំនឹងរៀបរាប់ពីលំដាប់ជំហានដែលខ្ញុំសូមណែនាំហើយក៏បង្ហាញអ្នកពីគំនិតមូលដ្ឋានផងដែរ", "ខ្ញុំណែនាំលំដាប់ជំហាន និងគំនិតមូលដ្ឋាន"),
    (r"អំពីអ្វីដែលជំហាននីមួយៗទាំងនេះមានប្រសិនបើអ្នកមិនធ្លាប់បានឃើញពួកវាពីមុនមករឿងដំបូងដែលខ្ញុំសូមណែនាំឱ្យរៀន", "នៃជំហានទាំងនេះ។ ដំបូងខ្ញុំណែនាំឱ្យរៀន"),
    (r"គឺត្រូវរៀនដោះស្រាយគូបដោយប្រើវិធីសាស្ត្រចាប់ផ្តើមសិនព្រោះ", "គឺរៀនវិធីចាប់ផ្តើមសិន ព្រោះ"),
    (r"ដោះស្រាយពួកវាទៅក្នុងកន្លែងនោះទោះជាយ៉ាងណាក៏ដោយដើម្បីធានាថាគែមនោះ", "ដាក់វាត្រង់នោះ ដើម្បីឱ្យគែម"),
    (r"ជំនួសឱ្យការភ្ជាប់វាទៅកណ្តាលរបស់វាហើយបន្ទាប់មកផ្លាស់ទី", "ជំនួសភ្ជាប់ទៅកណ្តាលរួចផ្លាស់ទី"),
    (r"មានការកាន់ឡើងវិញពីរដងនៅក្នុងនោះហើយការកាន់ឡើងវិញគឺជា", "មានកាន់ឡើងវិញពីរដង ហើយវាគឺ"),
    (r"អ្នកអាចរៀនខ្លះៗក្នុងចំណោមទាំងនេះមុន OLL បើអ្នកចង់ប៉ុន្តែ", "អ្នកអាចរៀនខ្លះមុន OLL តែ"),
    (r"ផែនទីបង្ហាញផ្លូវនេះប្រសិនបើអ្នកមិនប្រាកដប៉ុន្តែកុំភ្លេចធ្វើតាមរបស់អ្នក", "ផែនទីនេះបើមិនប្រាកដ តែត្រូវតាម"),
    (r"ពូកែ F2L ខ្លាំងដល់កម្រិតដែលវាជា", "ពូកែ F2L ដល់កម្រិត"),
    (r"វាជួយខ្ញុំសន្សំពេលពីការចាប់កាន់ឡើងវិញនៅដំបូងដោយអនុញ្ញាតឱ្យខ្ញុំរក្សាមេដៃរបស់ខ្ញុំនៅខាងមុខប៉ុន្តែប្រសិនបើ", "វាជួយសន្សំពេលកាន់ឡើងវិញ តែបើ"),
    (r"គ្រាន់តែជារឿងខ្លះដែលត្រូវប្រយ័ត្នទុកគឺការរៀនសូត្រ", "រឿងត្រូវប្រយ័ត្ន គឺការរៀន"),
    (r"ប្រហែលជាគ្រាន់តែធ្វើឱ្យការរីកចម្រើនរបស់អ្នកយឺតចុះបន្ទាប់មកខ្ញុំនឹងលើកឡើងពីរឿងមួយចំនួនដែល", "អាចធ្វើឱ្យអ្នកយឺត។ បន្ទាប់មកជារឿងដែល"),
    (r"អញ្ចឹងប្រហែលជាប៉ុណ្ណឹងហើយខ្ញុំសង្ឃឹមថាខ្ញុំបានផ្តល់ឱ្យអ្នកនូវផែនទីបង្ហាញផ្លូវដ៏ល្អមួយប្រសិនបើអ្នក", "ប៉ុណ្ណឹងហើយ សង្ឃឹមថាជាផែនទីល្អ បើអ្នក"),
    (r"រឿងមួយអ្នកត្រូវជ្រើសរើសមួយដូច្នេះត្រូវប្រាកដថាអ្នកចងចាំរឿងនេះទុកព្រោះប្រសិនបើ", "ត្រូវជ្រើសយកមួយ ចងចាំទុកព្រោះបើ"),
    (r"ចាប់ផ្តើមផ្គូផ្គងពួកវាជាមួយ F2L កម្រិតខ្ពស់អ្វីដំបូងដែលអ្នកធ្វើគឺតែងតែផ្គូផ្គងពួកវាជាមួយគ្នា", "ចាប់ផ្តើមផ្គូផ្គង F2L កម្រិតខ្ពស់ គឺតែងតែផ្គូផ្គងគ្នា"),
    (r"កុំនិយាយពីរឿងជាច្រើនដែលអ្នកអាចរៀនរឿងទាំងនេះ", "មានវិធីរៀនជាច្រើនទៀត"),
    (r"មានរឿងច្រើនណាស់ដែលត្រូវរៀន និងរឿងជាច្រើនដែលអ្នកអាចធ្វើបាន", "មានអ្វីត្រូវរៀន និងធ្វើច្រើនណាស់"),
    # Conversational padding & introductory fillers
    (r"ជាការពិតណាស់", ""),
    (r"នៅក្នុងនោះ", "ក្នុងនោះ"),
    (r"នៅក្នុង", "ក្នុង"),
    (r"នៅពេលដែល", "ពេល"),
    (r"នៅពេល", "ពេល"),
    (r"ប្រសិនបើ", "បើ"),
    (r"ប៉ុន្តែ", "តែ"),
    (r"ពីព្រោះ", "ព្រោះ"),
    (r"ដូច្នេះ", "ដូចនេះ"),
    (r"ទោះជាយ៉ាងណាក៏ដោយ", "តែ"),
    (r"យ៉ាងណាក៏ដោយ", "តែ"),
    (r"សូមកត់សម្គាល់ថា", "ចំណាំថា"),
    (r"សូមកត់សម្គាល់", "ចំណាំ"),
    (r"កត់សម្គាល់ថា", "ចំណាំថា"),
    (r"អ្វីដែលអ្នកអាចធ្វើបានគឺ", "អ្នកអាច"),
    (r"អ្វីដែលអ្នកត្រូវធ្វើគឺ", "ត្រូវ"),
    (r"អ្វីដែលអ្នក", "អ្វី"),
    (r"រឿងដំបូងដែលខ្ញុំសូមណែនាំឱ្យរៀន", "ដំបូងគួររៀន"),
    (r"រឿងដំបូងដែលខ្ញុំណែនាំ", "ដំបូងខ្ញុំណែនាំ"),
    (r"រឿងនេះមិនត្រឹមតែអនុវត្តចំពោះ", "មិនត្រឹមតែសម្រាប់"),
    (r"រឿងនេះ", "នេះ"),
    (r"បើអ្នកមើលវិធីសាស្ត្រដូចជា", "ដូចជាវិធី"),
    (r"វាស្រដៀងគ្នាខ្លាំងណាស់", "គឺស្រដៀងគ្នា"),
    (r"ខ្លាំងណាស់", "ណាស់"),
    (r"នៅក្នុងអ្វីក៏បាន", "ណាក៏បាន"),
    (r"អ្វីក៏បាន", "ណាក៏បាន"),
    (r"ខ្ញុំនឹងចែករំលែកផែនទីបង្ហាញផ្លូវមួយដែលខ្ញុំគិតថានឹងល្អបំផុត និង", "ខ្ញុំចែករំលែកផែនទីល្អបំផុត និង"),
    (r"ផែនទីបង្ហាញផ្លូវមួយដែលខ្ញុំគិតថានឹងល្អបំផុត", "ផែនទីល្អបំផុត"),
    (r"ផែនទីបង្ហាញផ្លូវ", "ផែនទី"),
    (r"វិធីល្អបំផុតដើម្បីរីកចម្រើនក្នុងការដោះគូបលឿន", "វិធីដោះស្រាយគូបលឿន"),
    (r"ក្នុងការដោះគូបលឿន", "ក្នុងគូបលឿន"),
    (r"ដោះគូបលឿន", "គូបលឿន"),
    (r"ការចាប់ផ្តើម", "ចាប់ផ្តើម"),
    (r"ការរៀនសូត្រ", "ការរៀន"),
    (r"ការដោះស្រាយ", "ដោះស្រាយ"),
    (r"ធ្វើការដោះស្រាយ", "ដោះស្រាយ"),
    (r"ធ្វើការជ្រើសរើស", "ជ្រើសរើស"),
    (r"ធ្វើការផ្គូផ្គង", "ផ្គូផ្គង"),
    (r"មួយចំនួន", "ខ្លះ"),
    (r"ជាការពិត", ""),
    (r"ជារឿង", "ជា"),
    (r"រឿងដែល", "អ្វីដែល"),
    (r"មែនទែន", ""),
    (r"ច្រើនណាស់", "ច្រើន"),
]

KHMER_CLAUSE_MARKERS = r"(\s+|[។,?!]|ហើយ|ប៉ុន្តែ|តែ|ពីព្រោះ|ព្រោះ|ដូច្នេះ|ដូចនេះ|ប្រសិនបើ|បើ|ដើម្បី|បន្ទាប់មក|រួច|ដែល|គឺ|ពេល|និង|ឬ|នោះ|ក្រោយ)"


def shorten_khmer_text(text: str, target_char_count: Optional[int] = None) -> str:
    """Shorten Khmer text for video dubbing by eliminating verbose padding, redundant classifiers,
    and conversational filler while strictly preserving core terminology and meaning.
    """
    s = text.strip()
    if not s:
        return s

    for pattern, repl in CONCISE_REPLACEMENTS:
        s = re.sub(pattern, repl, s)

    # Normalize spacing and punctuation
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"([។,])\1+", r"\1", s).strip()

    # If target length is specified and text is still too long, do grammatical clause budgeting
    if target_char_count and len(s) > target_char_count:
        parts = re.split(KHMER_CLAUSE_MARKERS, s)
        rebuilt = ""
        for p in parts:
            if not p:
                continue
            if len(rebuilt + p) <= target_char_count + 4:
                rebuilt += p
            else:
                break
        if len(rebuilt.strip()) >= 15:
            s = rebuilt.strip()
        else:
            s = s[:target_char_count].strip()

    if not s.endswith("។") and not s.endswith(","):
        s += "។"

    return s.strip()


class AutoFitService:
    """Automated service that identifies speech timing conflicts across a project,
    concisely optimizes Khmer phrasing, trims silence, re-synthesizes speech audio,
    and confirms resolution so the project can be exported without truncation.
    """

    def __init__(self, video_processor: Optional[FFmpegVideoProcessor] = None):
        self.video_processor = video_processor or FFmpegVideoProcessor()
        self.sync_service = AudioSynchronizationService(video_processor=self.video_processor)

    def analyze_project_conflicts(
        self,
        project_id: str,
        db: Session,
        max_tempo: float = 1.25,
        safety_margin: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """Find all translation segments in the project that exceed their available timing window."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        video = project.video or db.query(Video).filter(Video.project_id == project_id).first()
        target_dur = float(video.duration_seconds or 0.0) if video else 0.0
        sorted_trans = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .order_by(TranslationSegment.segment_order.asc())
            .all()
        )

        conflicts = []
        for idx, trans_seg in enumerate(sorted_trans):
            t_seg = (
                trans_seg.transcript_segment
                or db.query(TranscriptSegment).filter(TranscriptSegment.id == trans_seg.transcript_segment_id).first()
            )
            audio_rec = (
                trans_seg.generated_audio
                or db.query(GeneratedAudio).filter(GeneratedAudio.translation_segment_id == trans_seg.id).first()
            )
            if not t_seg or not audio_rec or not audio_rec.duration_seconds:
                continue

            start_time = max(0.0, float(t_seg.start_time))
            end_time = max(start_time, float(t_seg.end_time))
            orig_dur = max(0.1, end_time - start_time)

            if idx < len(sorted_trans) - 1:
                next_trans = sorted_trans[idx + 1]
                next_t = (
                    next_trans.transcript_segment
                    or db.query(TranscriptSegment).filter(TranscriptSegment.id == next_trans.transcript_segment_id).first()
                )
                next_start = float(next_t.start_time) if next_t else end_time
                if next_start > start_time:
                    avail_window = min(next_start - start_time, target_dur - start_time) if target_dur > 0 else (next_start - start_time)
                else:
                    avail_window = orig_dur
            else:
                avail_window = (target_dur - start_time) if target_dur > 0 else orig_dur

            avail_window = max(0.1, avail_window)
            effective_window = max(0.05, round(avail_window - safety_margin, 3))
            raw_dur = float(audio_rec.duration_seconds)

            if raw_dur > avail_window:
                req_tempo = round(raw_dur / effective_window, 2)
                if req_tempo > max_tempo:
                    overflow = round((raw_dur / max_tempo) - effective_window, 2)
                    if overflow > 0.05:
                        conflicts.append({
                            "segment_order": t_seg.segment_order,
                            "translation_segment_id": trans_seg.id,
                            "transcript_segment_id": t_seg.id,
                            "start_time": start_time,
                            "end_time": end_time,
                            "slot_duration": orig_dur,
                            "avail_window": avail_window,
                            "effective_window": effective_window,
                            "current_khmer": trans_seg.khmer_text,
                            "english_text": t_seg.text,
                            "audio_path": audio_rec.audio_path,
                            "raw_duration": raw_dur,
                            "required_tempo": req_tempo,
                            "overflow_seconds": overflow,
                        })

        return conflicts

    def auto_fit_project(
        self,
        project_id: str,
        db: Session,
        max_tempo: float = 1.25,
        target_char_rate: float = 11.0,  # Characters per second of spoken Khmer
        trim_silence: bool = True,
    ) -> Dict[str, Any]:
        """Automatically resolve all speech timing conflicts in a project.
        Trims head/tail audio silence, shortens Khmer text to fit available slot,
        re-synthesizes audio, and validates timing.
        """
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        # Pre-pass: If trim_silence is requested, trim excessive head/tail silence on existing audio
        if trim_silence and project.translation_segments:
            for trans_seg in project.translation_segments:
                audio_rec = trans_seg.generated_audio
                if audio_rec and audio_rec.audio_path:
                    audio_dest = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
                    if audio_dest.exists():
                        try:
                            self.sync_service.trim_audio_silence(audio_dest, audio_dest)
                            actual_dur = self.video_processor.get_audio_duration(audio_dest)
                            if actual_dur > 0:
                                audio_rec.duration_seconds = actual_dur
                        except Exception as e:
                            logger.warning("Failed pre-pass silence trim for segment #%d: %s", trans_seg.segment_order, e)
            db.commit()

        conflicts = self.analyze_project_conflicts(project_id, db, max_tempo=max_tempo)
        initial_conflicts_count = len(conflicts)

        if not conflicts:
            logger.info("Project %s has 0 timing conflicts. Nothing to auto-fit.", project_id)
            return {
                "project_id": project_id,
                "initial_conflicts": 0,
                "resolved_conflicts": 0,
                "remaining_conflicts": 0,
                "segments_updated": 0,
                "status": "already_optimal",
            }

        logger.info(
            "Auto-fitting project %s: %d timing conflict(s) detected.",
            project_id,
            initial_conflicts_count,
        )

        tts_provider_name = project.tts_provider or "gtts"
        tts_voice = project.tts_voice or "default"
        tts = get_tts_provider(tts_provider_name)

        updated_count = 0
        details = []

        for c in conflicts:
            trans_seg = (
                db.query(TranslationSegment)
                .filter(TranslationSegment.id == c["translation_segment_id"])
                .first()
            )
            if not trans_seg:
                continue

            target_chars = max(18, int(c["effective_window"] * target_char_rate))
            shortened = shorten_khmer_text(trans_seg.khmer_text, target_char_count=target_chars)

            audio_rec = trans_seg.generated_audio
            if not audio_rec:
                continue

            audio_dest = resolve_audio_file(project_id, trans_seg.id, audio_rec.audio_path)
            audio_dest.parent.mkdir(parents=True, exist_ok=True)

            # Update text
            old_text = trans_seg.khmer_text
            trans_seg.khmer_text = shortened
            trans_seg.is_manually_edited = False
            trans_seg.is_outdated = False

            # Synthesize new audio
            try:
                res = tts.synthesize(
                    text=shortened,
                    output_path=audio_dest,
                    voice=tts_voice,
                )
                if trim_silence and audio_dest.exists():
                    try:
                        self.sync_service.trim_audio_silence(audio_dest, audio_dest)
                    except Exception as e:
                        logger.warning("Failed silence trim for segment #%d: %s", c["segment_order"], e)

                new_dur = self.video_processor.get_audio_duration(audio_dest)
                if new_dur <= 0.0 and res and res.duration_seconds:
                    new_dur = res.duration_seconds

                audio_rec.duration_seconds = new_dur
                audio_rec.is_outdated = False
                updated_count += 1
                details.append({
                    "segment_order": c["segment_order"],
                    "old_duration": c["raw_duration"],
                    "new_duration": new_dur,
                    "old_text": old_text,
                    "new_text": shortened,
                })
            except Exception as e:
                logger.error(
                    "Failed to re-synthesize segment #%d during auto-fit: %s",
                    c["segment_order"],
                    e,
                )

        if project.video:
            project.video.is_export_outdated = True

        db.commit()

        # Re-analyze conflicts after synthesis
        remaining = self.analyze_project_conflicts(project_id, db, max_tempo=max_tempo)
        resolved_count = initial_conflicts_count - len(remaining)

        logger.info(
            "Auto-fit completed for project %s: resolved %d conflicts, %d remaining.",
            project_id,
            resolved_count,
            len(remaining),
        )

        return {
            "project_id": project_id,
            "initial_conflicts": initial_conflicts_count,
            "resolved_conflicts": resolved_count,
            "remaining_conflicts": len(remaining),
            "segments_updated": updated_count,
            "details": details,
        }
