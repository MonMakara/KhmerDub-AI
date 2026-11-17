import pytest
import io
import json
from fastapi.testclient import TestClient
from app.models.project import Project, ProjectStatus, TranscriptSegment, TranslationSegment


def test_transcript_import_and_export(client: TestClient):
    # 1. Create a fresh project
    create_res = client.post("/api/projects", json={"title": "Transcript Import Export Test"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Test export before any transcript exists -> 400
    export_empty = client.get(f"/api/projects/{project_id}/transcript/export?format=srt")
    assert export_empty.status_code == 400

    # 3. Import transcript via raw SRT text
    raw_srt = (
        "1\n"
        "00:00:01,000 --> 00:00:04,500\n"
        "Welcome to our video presentation.\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:09,200\n"
        "Today we explore automatic Khmer dubbing with AI.\n"
    )

    import_res = client.post(
        f"/api/projects/{project_id}/transcript/import",
        data={"raw_content": raw_srt},
    )
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["segment_count"] == 2
    assert import_data["status"] == ProjectStatus.TRANSCRIBED.value

    # Verify segments in GET endpoint
    trans_res = client.get(f"/api/projects/{project_id}/transcript")
    assert trans_res.status_code == 200
    segs = trans_res.json()["segments"]
    assert len(segs) == 2
    assert segs[0]["text"] == "Welcome to our video presentation."
    assert segs[0]["start_time"] == 1.0
    assert segs[0]["end_time"] == 4.5
    assert segs[1]["text"] == "Today we explore automatic Khmer dubbing with AI."

    # 4. Export transcript in various formats
    # SRT
    res_srt = client.get(f"/api/projects/{project_id}/transcript/export?format=srt")
    assert res_srt.status_code == 200
    assert "text/plain" in res_srt.headers["Content-Type"]
    assert "00:00:01,000 --> 00:00:04,500" in res_srt.text
    assert "Welcome to our video presentation." in res_srt.text

    # VTT
    res_vtt = client.get(f"/api/projects/{project_id}/transcript/export?format=vtt")
    assert res_vtt.status_code == 200
    assert "text/vtt" in res_vtt.headers["Content-Type"]
    assert "WEBVTT" in res_vtt.text
    assert "00:00:01.000 --> 00:00:04.500" in res_vtt.text

    # TXT
    res_txt = client.get(f"/api/projects/{project_id}/transcript/export?format=txt")
    assert res_txt.status_code == 200
    assert "Welcome to our video presentation." in res_txt.text
    assert "Today we explore automatic Khmer dubbing with AI." in res_txt.text

    # JSON
    res_json = client.get(f"/api/projects/{project_id}/transcript/export?format=json")
    assert res_json.status_code == 200
    json_data = res_json.json()
    assert len(json_data) == 2
    assert json_data[0]["text"] == "Welcome to our video presentation."

    # 5. Import transcript via file upload
    new_vtt = (
        "WEBVTT\n\n"
        "1\n"
        "00:00:02.000 --> 00:00:06.000\n"
        "Updated transcript cue via file upload.\n"
    )
    file_bytes = io.BytesIO(new_vtt.encode("utf-8"))
    upload_res = client.post(
        f"/api/projects/{project_id}/transcript/import",
        files={"file": ("subtitles.vtt", file_bytes, "text/vtt")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["segment_count"] == 1

    trans_res2 = client.get(f"/api/projects/{project_id}/transcript")
    segs2 = trans_res2.json()["segments"]
    assert len(segs2) == 1
    assert segs2[0]["text"] == "Updated transcript cue via file upload."
    assert segs2[0]["start_time"] == 2.0


def test_translation_import_and_export(client: TestClient):
    # 1. Create a fresh project
    create_res = client.post("/api/projects", json={"title": "Translation Import Export Test"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 2. Setup transcript segments first
    raw_transcript = (
        "1\n"
        "00:00:01,000 --> 00:00:04,000\n"
        "Artificial intelligence is transforming content creation.\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "This tool supports natural voice dubbing.\n"
    )
    t_res = client.post(
        f"/api/projects/{project_id}/transcript/import",
        data={"raw_content": raw_transcript},
    )
    assert t_res.status_code == 200

    # 3. Export translation before any exists -> 400
    export_empty = client.get(f"/api/projects/{project_id}/translation/export?format=srt")
    assert export_empty.status_code == 400

    # 4. Import Khmer translation via raw SRT text (bilingual or Khmer)
    raw_km_srt = (
        "1\n"
        "00:00:01,000 --> 00:00:04,000\n"
        "Artificial intelligence is transforming content creation.\n"
        "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។\n\n"
        "2\n"
        "00:00:05,000 --> 00:00:08,000\n"
        "This tool supports natural voice dubbing.\n"
        "ឧបករណ៍នេះគាំទ្រការបញ្ចូលសំឡេងបែបធម្មជាតិ។\n"
    )
    import_res = client.post(
        f"/api/projects/{project_id}/translation/import",
        data={"raw_content": raw_km_srt},
    )
    assert import_res.status_code == 200
    import_data = import_res.json()
    assert import_data["segment_count"] == 2
    assert import_data["status"] == ProjectStatus.TRANSLATED.value

    # Check translations in GET endpoint
    trans_res = client.get(f"/api/projects/{project_id}/translations")
    assert trans_res.status_code == 200
    segs = trans_res.json()["segments"]
    assert len(segs) == 2
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។" in segs[0]["khmer_text"]
    assert segs[0]["is_manually_edited"] is True
    assert "ឧបករណ៍នេះគាំទ្រការបញ្ចូលសំឡេងបែបធម្មជាតិ។" in segs[1]["khmer_text"]

    # 5. Export translation:
    # Khmer SRT
    res_km_srt = client.get(f"/api/projects/{project_id}/translation/export?format=srt")
    assert res_km_srt.status_code == 200
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។" in res_km_srt.text

    # Bilingual SRT (contains English on top, Khmer on bottom)
    res_bilingual = client.get(f"/api/projects/{project_id}/translation/export?format=bilingual")
    assert res_bilingual.status_code == 200
    assert "Artificial intelligence is transforming content creation." in res_bilingual.text
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។" in res_bilingual.text

    # WebVTT
    res_km_vtt = client.get(f"/api/projects/{project_id}/translation/export?format=vtt")
    assert res_km_vtt.status_code == 200
    assert "WEBVTT" in res_km_vtt.text
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។" in res_km_vtt.text

    # TXT
    res_km_txt = client.get(f"/api/projects/{project_id}/translation/export?format=txt")
    assert res_km_txt.status_code == 200
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា។" in res_km_txt.text

    # JSON
    res_km_json = client.get(f"/api/projects/{project_id}/translation/export?format=json")
    assert res_km_json.status_code == 200
    json_data = res_km_json.json()
    assert len(json_data) == 2
    assert "បញ្ញាសិប្បនិម្មិតកំពុងផ្លាស់ប្តូរការបង្កើតមាតិកា" in json_data[0]["khmer_text"]

    # 6. Import translation via file upload
    file_srt = (
        "1\n"
        "00:00:01,000 --> 00:00:04,000\n"
        "ការបកប្រែថ្មីតាមរយៈការបង្ហោះឯកសារ\n"
    )
    km_bytes = io.BytesIO(file_srt.encode("utf-8"))
    upload_res = client.post(
        f"/api/projects/{project_id}/translation/import",
        files={"file": ("translation.srt", km_bytes, "text/plain")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["segment_count"] >= 1

    trans_check = client.get(f"/api/projects/{project_id}/translations")
    assert trans_check.status_code == 200
    assert "ការបកប្រែថ្មីតាមរយៈការបង្ហោះឯកសារ" in trans_check.json()["segments"][0]["khmer_text"]


def test_import_translation_without_prior_transcript(client: TestClient):
    # Test importing subtitle file into project that doesn't have transcripts yet
    # It should automatically create both transcript & translation cues
    create_res = client.post("/api/projects", json={"title": "Direct Translation Import"})
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    raw_srt = (
        "1\n"
        "00:00:00,500 --> 00:00:03,500\n"
        "ជំរាបសួរអ្នកទាំងអស់គ្នា\n"
    )
    import_res = client.post(
        f"/api/projects/{project_id}/translation/import",
        data={"raw_content": raw_srt},
    )
    assert import_res.status_code == 200
    assert import_res.json()["segment_count"] == 1
    assert import_res.json()["status"] == ProjectStatus.TRANSLATED.value

    # Check both transcripts and translations were created
    t_res = client.get(f"/api/projects/{project_id}/transcript")
    assert t_res.status_code == 200
    assert len(t_res.json()["segments"]) == 1

    tr_res = client.get(f"/api/projects/{project_id}/translations")
    assert tr_res.status_code == 200
    assert len(tr_res.json()["segments"]) == 1
    assert tr_res.json()["segments"][0]["khmer_text"] == "ជំរាបសួរអ្នកទាំងអស់គ្នា"


def test_v2_3_import_coalesces_62_transcript_cues_into_dubbing_units(client: TestClient):
    """Verify that importing 62 separate cue translations into a v2.3 project
    coalesces them into cohesive dubbing units without 1-to-1 fragmentation,
    preventing 60 false timing conflicts on dubbing export.
    """
    create_res = client.post("/api/projects", json={
        "title": "V2.3 Coalescing Test",
        "pipeline_version": "v2.3",
    })
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    # 1. Simulate 62 short transcript cues (1.6s speech, 0.4s pause between cues)
    def format_srt_time(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    srt_cues = []
    for i in range(1, 63):
        st = (i - 1) * 2.0
        et = st + 1.6
        st_str = format_srt_time(st)
        et_str = format_srt_time(et)
        srt_cues.append(f"{i}\n{st_str} --> {et_str}\nEnglish transcript clause #{i}.")

    t_res = client.post(
        f"/api/projects/{project_id}/transcript/import",
        data={"raw_content": "\n\n".join(srt_cues)},
    )
    assert t_res.status_code == 200
    assert t_res.json()["segment_count"] == 62

    # 2. Test export mode=dubbing_units vs mode=cues
    exp_cues = client.get(f"/api/projects/{project_id}/transcript/export?format=json&mode=cues")
    assert exp_cues.status_code == 200
    assert len(exp_cues.json()) == 62

    exp_units = client.get(f"/api/projects/{project_id}/transcript/export?format=json&mode=dubbing_units")
    assert exp_units.status_code == 200
    dub_units = exp_units.json()
    # Should coalesce adjacent short cues into ~21 dubbing units
    assert len(dub_units) == 21
    assert "duration_seconds" in dub_units[0]
    assert dub_units[0]["duration_seconds"] > 3.0  # Much wider window for Khmer speech

    # 3. Simulate user translating all 62 cues with an external AI and importing them
    km_cues = []
    for i in range(1, 63):
        st = (i - 1) * 2.0
        et = st + 1.6
        st_str = format_srt_time(st)
        et_str = format_srt_time(et)
        km_cues.append(f"{i}\n{st_str} --> {et_str}\nឃ្លាភាសាខ្មែរលេខ {i}។")

    import_km = client.post(
        f"/api/projects/{project_id}/translation/import",
        data={"raw_content": "\n\n".join(km_cues), "auto_fit": "true"},
    )
    assert import_km.status_code == 200
    # Crucial assertion: returns the number of dubbing units (21), NOT 62 fragmented units!
    assert import_km.json()["segment_count"] == 21

    # Check translations endpoint
    tr_res = client.get(f"/api/projects/{project_id}/translations")
    assert tr_res.status_code == 200
    segs = tr_res.json()["segments"]
    assert len(segs) == 21

    # Check first unit contains combined text of clauses 1, 2, 3
    first_seg = segs[0]
    assert "ឃ្លាភាសាខ្មែរលេខ 1" in first_seg["khmer_text"]
    assert "ឃ្លាភាសាខ្មែរលេខ 2" in first_seg["khmer_text"]
    assert "ឃ្លាភាសាខ្មែរលេខ 3" in first_seg["khmer_text"]
    assert first_seg["start_time"] == 0.0
    assert first_seg["end_time"] > 5.0
    assert first_seg["is_manually_edited"] is False  # Because auto_fit was set to true

    # Check that transcript segments have dubbing_unit_id linked
    t_check = client.get(f"/api/projects/{project_id}/transcript")
    assert t_check.status_code == 200
    t_items = t_check.json()["segments"]
    assert len(t_items) == 62
    assert t_items[0]["dubbing_unit_id"] == first_seg["id"]
    assert t_items[1]["dubbing_unit_id"] == first_seg["id"]
    assert t_items[2]["dubbing_unit_id"] == first_seg["id"]


def test_imported_grouped_translation_avoids_review_conflicts(client: TestClient, db_session):
    """Verify that coalescing imported translations eliminates false review conflicts
    because speech audio is placed into wide, cohesive dubbing unit windows.
    """
    from app.services.dubbing.timing_optimizer import TimingOptimizerService
    from app.models.project import GeneratedAudio, Video

    create_res = client.post("/api/projects", json={
        "title": "Timing Conflict Resolution Test",
        "pipeline_version": "v2.3",
    })
    assert create_res.status_code == 201
    project_id = create_res.json()["id"]

    def format_srt_time(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    # 1. Add 6 transcript cues (2 dubbing units of 3 cues each)
    srt_cues = []
    for i in range(1, 7):
        st = (i - 1) * 2.0
        et = st + 1.6
        srt_cues.append(f"{i}\n{format_srt_time(st)} --> {format_srt_time(et)}\nSentence {i}.")

    client.post(
        f"/api/projects/{project_id}/transcript/import",
        data={"raw_content": "\n\n".join(srt_cues)},
    )

    # 2. Import 6 translated cues
    km_cues = []
    for i in range(1, 7):
        st = (i - 1) * 2.0
        et = st + 1.6
        km_cues.append(f"{i}\n{format_srt_time(st)} --> {format_srt_time(et)}\nឃ្លាខ្មែរ {i}។")

    client.post(
        f"/api/projects/{project_id}/translation/import",
        data={"raw_content": "\n\n".join(km_cues), "auto_fit": "true"},
    )

    # 3. Simulate video duration and audio generation for the 2 coalesced units
    trans_segs = db_session.query(TranslationSegment).filter_by(project_id=project_id).order_by(TranslationSegment.segment_order.asc()).all()
    assert len(trans_segs) == 2

    vid = Video(project_id=project_id, filename="video.mp4", file_path="/fake/video.mp4", file_size_bytes=1024, duration_seconds=15.0)
    db_session.add(vid)

    for seg in trans_segs:
        # Each unit has a slot duration of 5.6s (e.g. 0 to 5.6s, 6.0 to 11.6s).
        # Normal Khmer speech takes ~4.0s (which fits comfortably without overflowing).
        audio = GeneratedAudio(
            project_id=project_id,
            translation_segment_id=seg.id,
            audio_path=f"/fake/path/{seg.id}.wav",
            duration_seconds=4.0,
            provider="edge",
            voice="km-KH-PisethNeural",
        )
        db_session.add(audio)
    db_session.commit()

    # 4. Run TimingOptimizer
    optimizer = TimingOptimizerService(max_tempo=1.25)
    opt_result = optimizer.optimize_project(project_id, db_session)

    assert opt_result.total_segments == 2
    assert opt_result.unresolved_conflicts == 0
    assert opt_result.fitted_naturally == 2


