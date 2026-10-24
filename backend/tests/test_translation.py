import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.project import (
    Project,
    TranscriptSegment,
    TranslationSegment,
    ProcessingJob,
    ProjectStatus,
    JobStatus,
)
from app.services.translation.nllb import (
    NLLBTranslationProvider,
    normalize_language_code,
    get_current_process_ram_mb,
)
from app.workers.translation import process_translation




def test_language_normalization():
    assert normalize_language_code("en") == "eng_Latn"
    assert normalize_language_code("km") == "khm_Khmr"
    assert normalize_language_code("eng_Latn") == "eng_Latn"
    assert normalize_language_code("khm_Khmr") == "khm_Khmr"
    assert normalize_language_code("fra_Latn") == "fra_Latn"


def test_translation_empty_texts():
    provider = NLLBTranslationProvider()
    assert provider.translate([]) == []
    assert provider.translate(["", "  "]) == ["", ""]


def test_translation_provider_mocked():
    provider = NLLBTranslationProvider()
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()

    mock_tokenizer.convert_tokens_to_ids.return_value = 256092
    mock_tokenizer.batch_decode.return_value = ["សួស្តីពិភពលោក"]

    with patch.object(provider, "get_model_and_tokenizer", return_value=(mock_model, mock_tokenizer)):
        results = provider.translate(["Hello world"])
        assert len(results) == 1
        assert results[0] == "សួស្តីពិភពលោក"


def test_translation_api_nonexistent_project(client: TestClient):
    response = client.post("/api/projects/non-existent-id/translate")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_translation_api_missing_transcripts(client: TestClient, db_session: Session):
    project = Project(
        title="No Transcript Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.UPLOADED,
    )
    db_session.add(project)
    db_session.commit()

    response = client.post(f"/api/projects/{project.id}/translate")
    assert response.status_code == 400
    assert "No transcript segments found" in response.json()["detail"]


def test_concurrent_translation_conflict(client: TestClient, db_session: Session):
    project = Project(
        title="Concurrent Translation Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.TRANSCRIBED,
    )
    db_session.add(project)
    db_session.commit()

    t_seg = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=2.0,
        text="Testing concurrency",
    )
    db_session.add(t_seg)

    running_job = ProcessingJob(
        project_id=project.id,
        job_type="translate",
        status=JobStatus.RUNNING,
        progress_percentage=45,
    )
    db_session.add(running_job)
    db_session.commit()

    response = client.post(f"/api/projects/{project.id}/translate")
    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"].lower()


def test_translation_workflow_and_crud(client: TestClient, db_session: Session):
    # 1. Setup project with transcript segments
    project = Project(
        title="Translation E2E Project",
        original_language="en",
        target_language="km",
        status=ProjectStatus.TRANSCRIBED,
    )
    db_session.add(project)
    db_session.commit()

    seg1 = TranscriptSegment(
        project_id=project.id,
        segment_order=1,
        start_time=0.0,
        end_time=3.5,
        text="Hello world and welcome to our demo.",
    )
    seg2 = TranscriptSegment(
        project_id=project.id,
        segment_order=2,
        start_time=3.5,
        end_time=7.0,
        text="Artificial intelligence makes dubbing easy.",
    )
    db_session.add_all([seg1, seg2])
    db_session.commit()

    # 2. Trigger translation job
    job = ProcessingJob(
        project_id=project.id,
        job_type="translate",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db_session.add(job)
    db_session.commit()

    mock_translations = [
        "សួស្តីពិភពលោក និងសូមស្វាគមន៍មកកាន់ការបង្ហាញរបស់យើង។",
        "បញ្ញាសិប្បនិម្មិតធ្វើឱ្យការបញ្ចូលសំឡេងមានភាពងាយស្រួល។",
    ]

    with patch("app.workers.translation.NLLBTranslationProvider") as mock_provider_cls:
        mock_instance = MagicMock()
        mock_instance.translate.return_value = mock_translations
        mock_provider_cls.return_value = mock_instance

        process_translation(project.id, job.id, db=db_session)

    # 3. Verify project and job status
    db_session.refresh(project)
    db_session.refresh(job)
    assert job.status == JobStatus.COMPLETED
    assert job.progress_percentage == 100
    assert project.status == ProjectStatus.TRANSLATED

    # 4. Fetch translations via API
    res = client.get(f"/api/projects/{project.id}/translations")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == project.id
    assert len(data["segments"]) == 2

    trans1 = data["segments"][0]
    trans2 = data["segments"][1]

    assert trans1["segment_order"] == 1
    assert trans1["khmer_text"] == mock_translations[0]
    assert trans1["english_text"] == "Hello world and welcome to our demo."
    assert trans1["start_time"] == 0.0
    assert trans1["end_time"] == 3.5
    assert trans1["is_manually_edited"] is False
    assert trans1["is_outdated"] is False

    assert trans2["segment_order"] == 2
    assert trans2["khmer_text"] == mock_translations[1]

    # 5. Manually edit segment 1
    custom_khmer = "ជំរាបសួរអ្នកទាំងអស់គ្នា!"
    patch_res = client.patch(
        f"/api/projects/{project.id}/translations/{trans1['id']}",
        json={"khmer_text": custom_khmer},
    )
    assert patch_res.status_code == 200
    patched_data = patch_res.json()
    assert patched_data["khmer_text"] == custom_khmer
    assert patched_data["is_manually_edited"] is True
    assert patched_data["is_outdated"] is False

    # 6. Re-run translation worker: manually edited segment MUST be preserved
    job2 = ProcessingJob(
        project_id=project.id,
        job_type="translate",
        status=JobStatus.PENDING,
        progress_percentage=0,
    )
    db_session.add(job2)
    db_session.commit()

    with patch("app.workers.translation.NLLBTranslationProvider") as mock_provider_cls:
        mock_instance = MagicMock()
        # Only segment 2 should be sent to the provider because segment 1 is manually edited!
        mock_instance.translate.return_value = ["ការបញ្ចូលសំឡេងថ្មី"]
        mock_provider_cls.return_value = mock_instance

        process_translation(project.id, job2.id, db=db_session)

        # Ensure provider was called only with segment 2 text
        assert mock_instance.translate.call_count == 1
        call_texts = mock_instance.translate.call_args[1]["texts"]
        assert len(call_texts) == 1
        assert call_texts[0] == seg2.text

    # Verify segment 1 still has the user's manual edit
    db_trans1 = db_session.query(TranslationSegment).filter(TranslationSegment.id == trans1["id"]).first()
    assert db_trans1.khmer_text == custom_khmer
    assert db_trans1.is_manually_edited is True

    # 7. Modify English transcript segment 1: corresponding translation must be marked as outdated
    transcript_patch_res = client.patch(
        f"/api/projects/{project.id}/transcript/{seg1.id}",
        json={"text": "Hello world and welcome to our brand new demo."},
    )
    assert transcript_patch_res.status_code == 200

    db_session.refresh(db_trans1)
    assert db_trans1.is_outdated is True
    # Still manually edited until retranslated
    assert db_trans1.is_manually_edited is True

    # 8. Single segment retranslation
    with patch("app.api.endpoints.projects.NLLBTranslationProvider") as mock_api_provider_cls:
        mock_api_instance = MagicMock()
        mock_api_instance.translate.return_value = ["សួស្តីពិភពលោក និងសូមស្វាគមន៍មកកាន់ការបង្ហាញថ្មីរបស់យើង។"]
        mock_api_provider_cls.return_value = mock_api_instance

        retrans_res = client.post(f"/api/projects/{project.id}/translations/{trans1['id']}/retranslate")
        assert retrans_res.status_code == 200
        retrans_data = retrans_res.json()
        assert retrans_data["khmer_text"] == "សួស្តីពិភពលោក និងសូមស្វាគមន៍មកកាន់ការបង្ហាញថ្មីរបស់យើង។"
        assert retrans_data["is_manually_edited"] is False
        assert retrans_data["is_outdated"] is False
