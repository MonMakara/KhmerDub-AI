"""Isolated toolkit acceptance copies; never modifies project source media."""
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from app.core.storage import get_toolkit_task_dir
from app.database.session import SessionLocal
from app.models.toolkit import ToolkitTask
from app.services.audio_cleaning import process_cleaning
from app.services.video.cleaning import AudioCleaningProcessor
from scripts.evaluate_audio_cleaning import ROOT


def main():
    fixture = json.loads((ROOT / "fixture.json").read_text())
    original = Path(fixture["video_source"])
    processor = AudioCleaningProcessor()
    results = []
    for mode in ("noise", "music"):
        task_id = str(uuid.uuid4())
        folder = get_toolkit_task_dir(task_id) / "input"
        folder.mkdir(parents=True)
        source = folder / "source.mp4"
        shutil.copyfile(original, source)
        with SessionLocal() as db:
            db.add(ToolkitTask(id=task_id, tool_type="audio_cleaning", source_type="upload",
                source_filename=f"Acceptance {mode} — {original.name}", source_file_path=str(source),
                source_media_metadata=json.dumps({"mode":mode,"strength":"balanced"}),
                target_format="wav", status="pending"))
            db.commit()
        print("START", mode, task_id, flush=True)
        process_cleaning(task_id)
        with SessionLocal() as db:
            task = db.get(ToolkitTask, task_id)
            assert task.status == "completed", task.error_message
            meta = json.loads(task.output_media_metadata)
            assert abs(meta["duration_difference"]) < .001
            assert meta["has_video"]
            result = {"task_id":task_id,"mode":mode,"metadata":meta}
            results.append(result)
            (ROOT / "full-video-acceptance.json").write_text(json.dumps(results, indent=2))
            print("COMPLETED", json.dumps(result), flush=True)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == fixture["source_sha256"]
    print("ORIGINAL_SHA256_UNCHANGED", flush=True)


if __name__ == "__main__":
    main()
