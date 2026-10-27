import uuid
import os
from pathlib import Path
from app.database.session import SessionLocal
from app.models.project import (
    Project,
    Video,
    TranscriptSegment,
    TranslationSegment,
    GeneratedAudio,
    ProjectStatus,
)
from tests.test_adaptive_speech_speed import make_sine_wav, make_test_mp4

def seed():
    db = SessionLocal()
    try:
        # 1. Project with Review Required
        p1_id = "demo-adaptive-review-required"
        existing1 = db.query(Project).filter(Project.id == p1_id).first()
        if existing1:
            db.delete(existing1)
            db.commit()

        video_dir1 = Path("/app/data/uploads") / p1_id
        audio_dir1 = Path("/app/data/projects") / p1_id / "audio"
        video_dir1.mkdir(parents=True, exist_ok=True)
        audio_dir1.mkdir(parents=True, exist_ok=True)

        vid_path1 = video_dir1 / "original_video.mp4"
        make_test_mp4(vid_path1, duration=70.0)

        p1 = Project(
            id=p1_id,
            title="Discipline Your Mind (Adaptive Speed v2.2 - Review Required)",
            original_video_path=str(vid_path1),
            original_language="en",
            target_language="km",
            translation_provider="nllb",
            translation_style="natural",
            tts_provider="edge",
            tts_voice="km-KH-PisethNeural",
            pipeline_version="v2.2",
            status=ProjectStatus.VOICE_GENERATED,
        )
        db.add(p1)

        v1 = Video(
            id=str(uuid.uuid4()),
            project_id=p1_id,
            filename="original_video.mp4",
            file_path=str(vid_path1),
            file_size_bytes=vid_path1.stat().st_size,
            duration_seconds=70.0,
            width=640,
            height=360,
            
        )
        db.add(v1)

        # Segments 1-3: Natural fitting
        # Segments 4-8: The screenshot scenario
        data1 = [
            (1, 1.0, 4.0, 3.0, 2.5, "Welcome to the mind training session.", "សូមស្វាគមន៍មកកាន់វគ្គបណ្តុះបណ្តាលចិត្ត។"),
            (2, 4.5, 7.5, 3.0, 2.8, "Today we will explore key habits.", "ថ្ងៃនេះយើងនឹងស្វែងយល់អំពីទម្លាប់សំខាន់ៗ។"),
            (3, 8.0, 11.5, 3.5, 3.2, "Discipline begins with conscious awareness.", "វិន័យចាប់ផ្តើមពីការដឹងខ្លួនដោយយកចិត្តទុកដាក់។"),
            # Consecutive segments from user screenshot
            (4, 12.0, 20.20, 8.20, 10.58, "Train your mind before life forces you to learn lessons the hard way.", "បង្វឹកចិត្តរបស់អ្នកមុនពេលជីវិតបង្ខំអ្នកឱ្យរៀនមេរៀនដោយការលំបាក។"),
            (5, 20.55, 28.89, 8.34, 10.75, "Every single day presents an opportunity to master thoughts and impulses.", "រាល់ថ្ងៃតែងតែផ្តល់ឱកាសដើម្បីគ្រប់គ្រងគំនិត និងអារម្មណ៍រំជើបរំជួល។"),
            (6, 29.24, 36.88, 7.64, 10.75, "When resistance appears in your path, push forward with relentless focus.", "នៅពេលឧបសគ្គលេចឡើងក្នុងដំណើររបស់អ្នក ចូររុញទៅមុខដោយការយកចិត្តទុកដាក់ខ្ពស់។"),
            (7, 37.23, 46.25, 9.02, 11.88, "True personal strength comes from steady daily repetition and continuous mental fortitude.", "កម្លាំងផ្ទាល់ខ្លួនពិតប្រាកដកើតចេញពីការអនុវត្តប្រចាំថ្ងៃជាប់លាប់ និងភាពរឹងមាំផ្លូវចិត្តជាបន្តបន្ទាប់។"),
            (8, 46.60, 52.36, 5.76, 8.04, "Commit to your purpose right now and never turn backward.", "ប្តេជ្ញាចិត្តចំពោះគោលបំណងរបស់អ្នកឥឡូវនេះ ហើយកុំងាកក្រោយឡើយ។"),
        ]

        for s_order, start_t, end_t, slot_dur, speech_dur, en_txt, km_txt in data1:
            t_id = f"t1_{s_order}"
            tr_id = f"tr1_{s_order}"
            r_id = f"r1_{s_order}"

            t_seg = TranscriptSegment(
                id=t_id,
                project_id=p1_id,
                segment_order=s_order,
                start_time=start_t,
                end_time=end_t,
                text=en_txt,
            )
            db.add(t_seg)

            tr_seg = TranslationSegment(
                id=tr_id,
                project_id=p1_id,
                transcript_segment_id=t_id,
                segment_order=s_order,
                khmer_text=km_txt,
            )
            db.add(tr_seg)

            wav_file = audio_dir1 / f"seg_{s_order}.wav"
            make_sine_wav(wav_file, duration=speech_dur)

            rec = GeneratedAudio(
                id=r_id,
                project_id=p1_id,
                translation_segment_id=tr_id,
                audio_path=str(wav_file),
                duration_seconds=speech_dur,
            )
            db.add(rec)

        db.commit()
        print(f"Created demo project with review required: {p1_id}")

        # 2. Project with Khmer Dubbing Ready (Zero Conflicts)
        p2_id = "demo-adaptive-ready"
        existing2 = db.query(Project).filter(Project.id == p2_id).first()
        if existing2:
            db.delete(existing2)
            db.commit()

        video_dir2 = Path("/app/data/uploads") / p2_id
        audio_dir2 = Path("/app/data/projects") / p2_id / "audio"
        video_dir2.mkdir(parents=True, exist_ok=True)
        audio_dir2.mkdir(parents=True, exist_ok=True)

        vid_path2 = video_dir2 / "original_video.mp4"
        make_test_mp4(vid_path2, duration=45.0)

        p2 = Project(
            id=p2_id,
            title="Rubik's Cube Speedcubing (Adaptive Speed v2.2 - Fully Ready)",
            original_video_path=str(vid_path2),
            original_language="en",
            target_language="km",
            translation_provider="nllb",
            translation_style="natural",
            tts_provider="edge",
            tts_voice="km-KH-PisethNeural",
            pipeline_version="v2.2",
            status=ProjectStatus.VOICE_GENERATED,
        )
        db.add(p2)

        v2 = Video(
            id=str(uuid.uuid4()),
            project_id=p2_id,
            filename="original_video.mp4",
            file_path=str(vid_path2),
            file_size_bytes=vid_path2.stat().st_size,
            duration_seconds=45.0,
            width=640,
            height=360,
            
        )
        db.add(v2)

        data2 = [
            (1, 1.0, 5.0, 4.0, 3.8, "Welcome to the CFOP Rubik's cube tutorial.", "សូមស្វាគមន៍មកកាន់ការបង្រៀនគូប CFOP។"),
            (2, 5.5, 10.0, 4.5, 4.9, "First, solve the white cross on bottom efficiently.", "ដំបូង ចូរដោះស្រាយសញ្ញាបូកពណ៌សនៅបាតក្រោមឱ្យមានប្រសិទ្ធភាព។"),
            (3, 10.5, 17.0, 6.5, 7.2, "Next, pair corners and edges into the first two layers.", "បន្ទាប់មក ផ្គូផ្គងជ្រុង និងគែមទៅក្នុងស្រទាប់ទាំងពីរដំបូង។"),
            (4, 17.5, 23.0, 5.5, 5.8, "Orient all top layer pieces using OLL algorithms.", "តម្រង់ទិសបំណែកស្រទាប់ខាងលើទាំងអស់ដោយប្រើក្បួន OLL។"),
            (5, 23.5, 30.0, 6.5, 6.9, "Finally, permute the last layer into solved positions.", "ចុងក្រោយ ចូរប្តូរទីតាំងស្រទាប់ចុងក្រោយឱ្យបានត្រឹមត្រូវ។"),
        ]

        for s_order, start_t, end_t, slot_dur, speech_dur, en_txt, km_txt in data2:
            t_id = f"t2_{s_order}"
            tr_id = f"tr2_{s_order}"
            r_id = f"r2_{s_order}"

            t_seg = TranscriptSegment(
                id=t_id,
                project_id=p2_id,
                segment_order=s_order,
                start_time=start_t,
                end_time=end_t,
                text=en_txt,
            )
            db.add(t_seg)

            tr_seg = TranslationSegment(
                id=tr_id,
                project_id=p2_id,
                transcript_segment_id=t_id,
                segment_order=s_order,
                khmer_text=km_txt,
            )
            db.add(tr_seg)

            wav_file = audio_dir2 / f"seg_{s_order}.wav"
            make_sine_wav(wav_file, duration=speech_dur)

            rec = GeneratedAudio(
                id=r_id,
                project_id=p2_id,
                translation_segment_id=tr_id,
                audio_path=str(wav_file),
                duration_seconds=speech_dur,
            )
            db.add(rec)

        db.commit()
        print(f"Created demo project with fully ready status: {p2_id}")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
