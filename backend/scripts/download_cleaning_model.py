"""Explicit administrator command, never called by a request or inference path."""
import hashlib
import urllib.request
from pathlib import Path

NAME = "955717e8-8726e21a.th"
DESTINATION = Path("/root/.cache/audio_cleaning") / NAME

if __name__ == "__main__":
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    if DESTINATION.exists():
        with DESTINATION.open("rb") as handle:
            checksum = hashlib.file_digest(handle, "sha256").hexdigest()
        if not checksum.startswith("8726e21a"):
            raise ValueError("Existing checkpoint checksum differs; no file was overwritten")
        print("ALREADY_VERIFIED", DESTINATION.name, checksum)
    else:
        staging = DESTINATION.with_suffix(".download-part")
        try:
            digest = hashlib.sha256()
            total = 0
            with urllib.request.urlopen(f"https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/{NAME}", timeout=60) as response, staging.open("xb") as output:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 100_000_000:
                        raise ValueError("Checkpoint exceeds approved approximate size")
                    digest.update(chunk)
                    output.write(chunk)
            if not digest.hexdigest().startswith("8726e21a"):
                raise ValueError("Official checkpoint checksum did not match")
            staging.replace(DESTINATION)
            print("DOWNLOADED_VERIFIED", total, digest.hexdigest())
        finally:
            staging.unlink(missing_ok=True)
