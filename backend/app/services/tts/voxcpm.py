import json
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.storage import get_voice_profile_audio_path
from app.database.session import SessionLocal
from app.models.voice import VoiceConsent, VoiceProfile
from app.services.tts.base import TTSAudioResult, TTSProvider
from app.services.tts.exceptions import (
    EmptyTextError,
    TTSGenerationError,
    TTSNetworkError,
    VoiceNotSupportedError,
)
from app.services.video.ffmpeg import FFmpegVideoProcessor

logger = logging.getLogger(__name__)


class VoxCPM2TTSProvider(TTSProvider):
    """Concrete implementation of TTSProvider using the local openbmb/VoxCPM2
    GPU inference worker for authorized Khmer voice cloning.
    """

    def __init__(
        self,
        worker_url: Optional[str] = None,
        internal_secret: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        video_processor: Optional[FFmpegVideoProcessor] = None,
    ):
        self.worker_url = (worker_url or settings.VOXCPM_WORKER_URL).rstrip("/")
        self.internal_secret = internal_secret or settings.VOXCPM_INTERNAL_SECRET
        self.timeout_seconds = timeout_seconds or settings.VOXCPM_TIMEOUT_SECONDS
        self.video_processor = video_processor or FFmpegVideoProcessor()

    def get_candidate_worker_urls(self) -> list[str]:
        """Return candidate worker URLs prioritizing configured URL then localhost fallback."""
        urls = [self.worker_url]
        # In case running outside docker during local test suite
        if "172.18.0.1" in self.worker_url or "host.docker.internal" in self.worker_url:
            urls.append("http://127.0.0.1:8002")
        return urls

    def check_worker_health(self) -> Dict[str, Any]:
        """Query GPU worker health status endpoint."""
        for url in self.get_candidate_worker_urls():
            try:
                req = urllib.request.Request(
                    f"{url}/health",
                    headers={"Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        data["url"] = url
                        return data
            except Exception:
                continue

        return {
            "status": "offline",
            "device": "unavailable",
            "model_loaded": False,
            "busy": False,
            "url": self.worker_url,
        }

    def is_worker_online(self) -> bool:
        """Return True if the GPU inference worker is responding to health checks."""
        health = self.check_worker_health()
        return health.get("status") == "online"

    def synthesize(
        self,
        text: str,
        output_path: Path,
        language: str = "km",
        voice: Optional[str] = None,
        slow: bool = False,
        seed: Optional[int] = None,
        **kwargs,
    ) -> TTSAudioResult:
        """Convert Khmer text into speech conditioned on an authorized reference voice profile.

        Args:
            text: Khmer Unicode text to synthesize.
            output_path: Destination path for generated audio (WAV or MP3).
            language: Target language code (must be 'km').
            voice: Voice profile UUID or name of authorized speaker.
            slow: Flag (unused by diffusion model, accepted for interface compatibility).

        Returns:
            TTSAudioResult containing audio_path, duration_seconds, provider_name, and voice.

        Raises:
            EmptyTextError: If text is empty or whitespace.
            VoiceNotSupportedError: If voice profile does not exist or is unauthorized.
            TTSNetworkError: If the GPU worker is offline or fails to respond.
            TTSGenerationError: If inference fails or output cannot be produced.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            raise EmptyTextError("Cannot synthesize speech from empty text.")

        # Ensure proper sentence terminal for natural breathing pause & vocal release
        if not clean_text.endswith(("។", "!", "?", "...", ":")):
            clean_text += "។"

        if not voice or voice.strip().lower() == "default":
            raise VoiceNotSupportedError(
                "VoxCPM2 voice cloning requires an authorized custom voice profile ID as voice parameter."
            )

        target_voice = voice.strip()
        for prefix in ("custom:", "voxcpm:", "voxcpm2:"):
            if target_voice.lower().startswith(prefix):
                target_voice = target_voice[len(prefix):].strip()
                break

        # Step 1: Database Verification of Profile & Legal Authorization
        with SessionLocal() as db:
            profile = (
                db.query(VoiceProfile)
                .filter(
                    (VoiceProfile.id == target_voice) | (VoiceProfile.name == target_voice),
                    VoiceProfile.is_active == 1,
                )
                .first()
            )

            if not profile:
                raise VoiceNotSupportedError(
                    f"Custom voice profile '{target_voice}' not found or is deactivated in Voice Studio."
                )

            consent = (
                db.query(VoiceConsent)
                .filter(
                    VoiceConsent.id == profile.consent_id,
                    VoiceConsent.is_authorized == 1,
                )
                .first()
            )

            if not consent:
                raise VoiceNotSupportedError(
                    f"Voice profile '{profile.name}' (ID: {profile.id}) lacks authorized legal consent. "
                    "Cannot synthesize speech using an unauthorized voice profile."
                )

            profile_id = profile.id
            profile_name = profile.name

        # Step 2: Resolve reference audio path safely via canonical helper
        ref_path = get_voice_profile_audio_path(profile_id)
        if not ref_path.exists() or ref_path.stat().st_size < 44:
            raise TTSGenerationError(
                f"Reference audio missing or corrupted for profile '{profile_name}' at {ref_path}."
            )

        # Step 3: Determine working URLs & Destination Paths
        health = self.check_worker_health()
        if health.get("status") != "online":
            raise TTSNetworkError(
                "VoxCPM2 GPU inference worker is currently offline. "
                "Please start the worker via './scripts/run_voxcpm_worker.sh' or select Google/Edge TTS."
            )

        active_worker_url = health.get("url", self.worker_url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            output_path.parent.chmod(0o777)
        except OSError:
            pass

        # Intermediate WAV path in shared temporary storage (guaranteed accessible across Docker and host)
        settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            settings.TEMP_DIR.chmod(0o777)
        except OSError:
            pass
        temp_wav_path = settings.TEMP_DIR / f"voxcpm_{uuid.uuid4().hex}.wav"

        wants_mp3 = output_path.suffix.lower() == ".mp3"

        payload = {
            "text": clean_text,
            "reference_audio_path": str(ref_path),
            "output_audio_path": str(temp_wav_path),
            "cfg_value": float(kwargs.get("cfg_value", 2.0)),
            "inference_timesteps": int(kwargs.get("inference_timesteps", 10)),
            "trim_silence_vad": bool(kwargs.get("trim_silence_vad", True)),
        }
        if seed is not None:
            payload["seed"] = seed

        req = urllib.request.Request(
            f"{active_worker_url}/synthesize",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Internal-Token": self.internal_secret,
            },
        )

        # Step 4: Execute Synthesis Request against GPU Worker
        try:
            logger.info(
                "Requesting VoxCPM2 speech synthesis for profile '%s' (%d chars) at %s...",
                profile_name,
                len(clean_text),
                active_worker_url,
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as http_err:
            try:
                err_body = json.loads(http_err.read().decode("utf-8"))
                detail = err_body.get("detail", str(http_err))
            except Exception:
                detail = str(http_err)
            logger.error("VoxCPM worker returned HTTP %d: %s", http_err.code, detail)

            # Auto-recovery for VRAM limitation (507): flush worker memory and retry once
            if http_err.code == 507:
                logger.warning(
                    "VoxCPM worker reported 507 VRAM limitation. Requesting cache purge and attempting automatic retry...",
                )
                try:
                    rel_req = urllib.request.Request(
                        f"{active_worker_url}/release_memory",
                        data=json.dumps({"unload_model": False}).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "X-Internal-Token": self.internal_secret,
                        },
                    )
                    with urllib.request.urlopen(rel_req, timeout=10):
                        pass

                    # Immediate single retry
                    with urllib.request.urlopen(req, timeout=self.timeout_seconds) as retry_resp:
                        resp_data = json.loads(retry_resp.read().decode("utf-8"))
                        logger.info("Automatic retry succeeded after worker memory purge.")
                except Exception as retry_err:
                    logger.error("Automatic retry after worker memory purge also failed: %s", retry_err)
                    raise TTSGenerationError(f"VoxCPM2 resource limitation: {detail}")
            elif http_err.code == 503:
                raise TTSGenerationError(f"VoxCPM2 resource limitation: {detail}")
            else:
                raise TTSGenerationError(f"VoxCPM2 synthesis failed: {detail}")
        except urllib.error.URLError as url_err:
            logger.error("Failed to connect to VoxCPM worker: %s", url_err)
            raise TTSNetworkError(
                f"Connection to VoxCPM2 GPU inference worker failed: {url_err}. "
                "Ensure worker process is running on host."
            )
        except Exception as e:
            logger.exception("Unexpected error communicating with VoxCPM worker: %s", e)
            raise TTSGenerationError(f"Inference worker communication error: {e}")

        # Step 5: Verify Generated Audio & Transcode to Output Path
        worker_returned_path_str = resp_data.get("output_audio_path")
        actual_wav_path = temp_wav_path
        if worker_returned_path_str:
            candidate = Path(worker_returned_path_str)
            if candidate.exists():
                actual_wav_path = candidate
            else:
                # In case worker returned host path, map it to container /app/data/...
                clean_c = str(candidate)
                if "/data/" in clean_c:
                    sub = clean_c[clean_c.index("/data/") :]
                    container_p = Path(f"/app{sub}")
                    if container_p.exists():
                        actual_wav_path = container_p

        if not actual_wav_path.exists() or actual_wav_path.stat().st_size < 44:
            raise TTSGenerationError(
                f"Generated audio file missing or empty at {actual_wav_path}."
            )

        try:
            # Retain the lossless synthesis master before conversion.
            shutil.copyfile(actual_wav_path, output_path.with_suffix(".raw.wav"))
            fade_filter = "afade=t=in:ss=0:d=0.010,areverse,afade=t=in:ss=0:d=0.010,areverse"
            if wants_mp3:
                # Transcode 48 kHz WAV to clean 192k MP3 with 10ms boundary smoothing using FFmpeg
                cmd = [
                    self.video_processor.ffmpeg_bin,
                    "-y",
                    "-i", str(actual_wav_path),
                    "-af", fade_filter,
                    "-codec:a", "libmp3lame",
                    "-b:a", "192k",
                    str(output_path),
                ]
            else:
                cmd = [
                    self.video_processor.ffmpeg_bin,
                    "-y",
                    "-i", str(actual_wav_path),
                    "-af", fade_filter,
                    "-c:a", "pcm_s16le",
                    str(output_path),
                ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                if actual_wav_path.resolve() != output_path.resolve():
                    shutil.copyfile(str(actual_wav_path), str(output_path))

            try:
                output_path.chmod(0o666)
            except OSError:
                pass
        finally:
            for p in (actual_wav_path, temp_wav_path):
                if p and p.exists() and p != output_path:
                    try:
                        p.unlink()
                    except OSError:
                        pass

        # Measure actual final duration using FFprobe
        duration = self.video_processor.get_audio_duration(output_path)
        if duration <= 0.0:
            duration = float(resp_data.get("duration_seconds", 1.0))

        cache_hit_str = " (cache hit)" if resp_data.get("cache_hit") else ""
        logger.info(
            "VoxCPM2 synthesized %s (%.2fs) [profile=%s, rtf=%.2fx%s]",
            output_path.name,
            duration,
            profile_name,
            resp_data.get("generation_time_s", 1.0) / max(0.1, duration),
            cache_hit_str,
        )

        return TTSAudioResult(
            audio_path=output_path,
            duration_seconds=duration,
            provider_name="voxcpm",
            voice=profile_id,
            language="km",
        )
