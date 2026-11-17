import json
import logging
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.core.timezone import get_cambodia_now_naive
from app.models.project import Project, ProjectSpeaker, TranscriptSegment, TranslationSegment
from app.services.tts.selection import set_unit_voice

logger = logging.getLogger(__name__)

COLOR_PALETTE = [
    "indigo",
    "emerald",
    "amber",
    "rose",
    "cyan",
    "purple",
    "teal",
    "orange",
]


@dataclass
class SpeakerProfileData:
    speaker_label: str
    display_name: str
    detected_gender: str
    average_pitch_hz: Optional[float]
    color: str
    assigned_voice_provider: str
    assigned_voice_id: str
    segment_count: int = 0
    total_duration: float = 0.0


@dataclass
class DiarizationResult:
    speakers: List[SpeakerProfileData]
    segment_assignments: Dict[str, str]  # transcript_segment_id -> speaker_label


class AudioDiarizer:
    """Acoustic feature extraction, clustering, and character profiling service."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg"):
        self.ffmpeg_bin = ffmpeg_bin
        self._mel_filters: Optional[np.ndarray] = None

    def _get_mel_filterbank(
        self, sr: int = 16000, n_fft: int = 512, n_mels: int = 16, fmin: float = 80.0, fmax: float = 7500.0
    ) -> np.ndarray:
        if self._mel_filters is not None and self._mel_filters.shape == (n_mels, n_fft // 2 + 1):
            return self._mel_filters

        def hz_to_mel(hz: float) -> float:
            return 2595.0 * np.log10(1.0 + hz / 700.0)

        def mel_to_hz(mel: float) -> float:
            return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

        mel_min = hz_to_mel(fmin)
        mel_max = hz_to_mel(fmax)
        mel_points = np.linspace(mel_min, mel_max, n_mels + 2)
        hz_points = mel_to_hz(mel_points)
        bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)

        filters = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
        for i in range(1, n_mels + 1):
            f_m_minus = bin_points[i - 1]
            f_m = bin_points[i]
            f_m_plus = bin_points[i + 1]

            for k in range(f_m_minus, f_m):
                if f_m > f_m_minus:
                    filters[i - 1, k] = (k - f_m_minus) / (f_m - f_m_minus)
            for k in range(f_m, f_m_plus):
                if f_m_plus > f_m:
                    filters[i - 1, k] = (f_m_plus - k) / (f_m_plus - f_m)

        self._mel_filters = filters
        return filters

    def extract_audio_slice(
        self, audio_path: Path, start_time: float, duration: float, sr: int = 16000
    ) -> np.ndarray:
        """Extract audio samples as a float32 1D numpy array at the target sample rate."""
        if not audio_path.exists() or duration <= 0.05:
            return np.zeros(0, dtype=np.float32)

        cmd = [
            self.ffmpeg_bin,
            "-ss", f"{max(0.0, start_time):.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(audio_path),
            "-vn",
            "-ac", "1",
            "-ar", str(sr),
            "-f", "f32le",
            "-",
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
            samples = np.frombuffer(res.stdout, dtype=np.float32)
            return samples
        except Exception as e:
            logger.warning("Failed to extract audio slice at %s-t=%s: %s", start_time, duration, e)
            return np.zeros(0, dtype=np.float32)

    def estimate_frame_pitch(
        self, frame: np.ndarray, sr: int = 16000, fmin: float = 65.0, fmax: float = 380.0
    ) -> float:
        """Estimate fundamental frequency (F0) using normalized autocorrelation."""
        if len(frame) < 32 or np.max(np.abs(frame)) < 1e-4:
            return 0.0

        min_lag = int(sr / fmax)
        max_lag = int(sr / fmin)

        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(frame) - 1 :]
        if max_lag >= len(corr):
            max_lag = len(corr) - 1
        if min_lag >= max_lag:
            return 0.0

        search_region = corr[min_lag:max_lag]
        if len(search_region) == 0:
            return 0.0

        peak_idx = int(np.argmax(search_region))
        best_lag = min_lag + peak_idx
        energy0 = corr[0] + 1e-8
        peak_norm = corr[best_lag] / energy0

        # Peak must indicate voiced periodic structure
        if peak_norm < 0.28:
            return 0.0

        pitch = float(sr / best_lag)
        if fmin <= pitch <= fmax:
            return pitch
        return 0.0

    def extract_features(
        self, samples: np.ndarray, sr: int = 16000
    ) -> Tuple[np.ndarray, Optional[float]]:
        """Extract a 39-dimensional acoustic feature vector and estimated pitch for a speech segment.

        Features:
        - pitch mean, pitch std, voiced fraction (3)
        - spectral centroid mean, std (2)
        - spectral rolloff mean, std (2)
        - 16 mel filterbank energies mean (16)
        - 16 mel filterbank energies std (16)
        """
        feature_dim = 39
        if len(samples) < int(sr * 0.15):  # Less than 150ms
            return np.zeros(feature_dim, dtype=np.float32), None

        # Normalize amplitude
        max_abs = np.max(np.abs(samples))
        if max_abs > 1e-5:
            samples = samples / max_abs

        # Frame parameters: 30ms window, 15ms hop
        frame_len = int(sr * 0.030)  # 480 samples
        hop_len = int(sr * 0.015)    # 240 samples
        n_fft = 512

        n_frames = max(1, (len(samples) - frame_len) // hop_len + 1)
        pitches: List[float] = []
        centroids: List[float] = []
        rolloffs: List[float] = []
        mel_energies_list: List[np.ndarray] = []

        mel_filters = self._get_mel_filterbank(sr=sr, n_fft=n_fft, n_mels=16)
        freq_bins = np.linspace(0, sr / 2, n_fft // 2 + 1)

        for i in range(n_frames):
            idx = i * hop_len
            frame = samples[idx : idx + frame_len]
            if len(frame) < frame_len:
                frame = np.pad(frame, (0, frame_len - len(frame)))

            # 1. Pitch
            p = self.estimate_frame_pitch(frame, sr=sr)
            if p > 0.0:
                pitches.append(p)

            # 2. Windowed FFT
            windowed = frame * np.hanning(frame_len)
            spec = np.abs(np.fft.rfft(windowed, n=n_fft))
            total_energy = np.sum(spec) + 1e-8

            # Centroid
            centroid = float(np.sum(freq_bins * spec) / total_energy)
            centroids.append(centroid)

            # Rolloff (85% energy)
            cum_energy = np.cumsum(spec)
            cutoff = 0.85 * total_energy
            rolloff_idx = np.searchsorted(cum_energy, cutoff)
            rolloff = float(freq_bins[min(rolloff_idx, len(freq_bins) - 1)])
            rolloffs.append(rolloff)

            # Mel filterbank
            mels = np.dot(mel_filters, spec)
            log_mels = np.log(mels + 1e-6)
            mel_energies_list.append(log_mels)

        # Voiced stats
        voiced_fraction = len(pitches) / float(n_frames)
        mean_pitch = float(np.median(pitches)) if pitches else 0.0
        std_pitch = float(np.std(pitches)) if len(pitches) > 1 else 0.0

        # Centroid stats
        mean_cent = float(np.mean(centroids)) if centroids else 0.0
        std_cent = float(np.std(centroids)) if len(centroids) > 1 else 0.0

        # Rolloff stats
        mean_roll = float(np.mean(rolloffs)) if rolloffs else 0.0
        std_roll = float(np.std(rolloffs)) if len(rolloffs) > 1 else 0.0

        # Mel stats
        mel_mat = np.array(mel_energies_list) if mel_energies_list else np.zeros((1, 16))
        mean_mels = np.mean(mel_mat, axis=0)
        std_mels = np.std(mel_mat, axis=0) if len(mel_mat) > 1 else np.zeros(16)

        # Scale features to balanced numerical ranges
        feature_vec = np.concatenate([
            [mean_pitch / 400.0, std_pitch / 100.0, voiced_fraction],
            [mean_cent / 4000.0, std_cent / 1500.0],
            [mean_roll / 6000.0, std_roll / 2000.0],
            mean_mels / 10.0,
            std_mels / 5.0,
        ]).astype(np.float32)

        norm = np.linalg.norm(feature_vec)
        if norm > 1e-5:
            feature_vec = feature_vec / norm

        avg_pitch = mean_pitch if mean_pitch > 0.0 else None
        return feature_vec, avg_pitch

    def compute_cosine_distance_matrix(self, features: np.ndarray) -> np.ndarray:
        """Compute pairwise cosine distances between feature vectors."""
        norms = np.linalg.norm(features, axis=1, keepdims=True)
        norms[norms == 0] = 1e-8
        normed = features / norms
        sim = np.dot(normed, normed.T)
        dist = np.clip(1.0 - sim, 0.0, 2.0)
        return dist

    def agglomerative_clustering(self, dist_matrix: np.ndarray, n_clusters: int) -> np.ndarray:
        """Deterministic Agglomerative Hierarchical Clustering with average linkage."""
        n = dist_matrix.shape[0]
        if n_clusters >= n:
            return np.arange(n, dtype=int)
        if n_clusters <= 1:
            return np.zeros(n, dtype=int)

        clusters = [[i] for i in range(n)]

        while len(clusters) > n_clusters:
            min_d = float("inf")
            best_i, best_j = -1, -1
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    c_i = clusters[i]
                    c_j = clusters[j]
                    d = np.mean([dist_matrix[a, b] for a in c_i for b in c_j])
                    if d < min_d:
                        min_d = d
                        best_i, best_j = i, j

            clusters[best_i].extend(clusters[best_j])
            clusters.pop(best_j)

        labels = np.zeros(n, dtype=int)
        for cluster_id, members in enumerate(clusters):
            for m in members:
                labels[m] = cluster_id
        return labels

    def compute_silhouette(self, dist_matrix: np.ndarray, labels: np.ndarray) -> float:
        """Compute mean silhouette score for given cluster labels.
        Singletons (|C_i| = 1) have silhouette 0.0 per standard convention (Rousseeuw 1987).
        """
        n = len(labels)
        unique_labels = np.unique(labels)
        if len(unique_labels) <= 1 or len(unique_labels) >= n:
            return -1.0

        scores: List[float] = []
        for i in range(n):
            same_mask = (labels == labels[i]) & (np.arange(n) != i)
            if np.sum(same_mask) == 0:
                scores.append(0.0)
                continue

            a = float(np.mean(dist_matrix[i, same_mask]))

            b = float("inf")
            for label in unique_labels:
                if label == labels[i]:
                    continue
                other_mask = labels == label
                b = min(b, float(np.mean(dist_matrix[i, other_mask])))

            denom = max(a, b)
            s = 0.0 if denom == 0 else (b - a) / denom
            scores.append(s)

        return float(np.mean(scores))

    def find_optimal_clusters(
        self,
        dist_matrix: np.ndarray,
        pitches: List[Optional[float]],
        min_speakers: int = 1,
        max_speakers: int = 6,
    ) -> np.ndarray:
        """Find the optimal number of speaker clusters using silhouette analysis and pitch bimodality."""
        n = dist_matrix.shape[0]
        if n <= 1:
            return np.zeros(n, dtype=int)

        max_k = min(max_speakers, n)
        min_k = min(min_speakers, max_k)

        if min_k == max_k:
            return self.agglomerative_clustering(dist_matrix, min_k)

        best_score = -1.0
        best_k = 1
        best_labels = np.zeros(n, dtype=int)

        # Baseline score for single cluster
        # If min_k == 1, 1 cluster is an option
        for k in range(max(2, min_k), max_k + 1):
            labels = self.agglomerative_clustering(dist_matrix, k)
            sil = self.compute_silhouette(dist_matrix, labels)

            # Check if clusters have distinct pitch characteristics
            pitch_boost = 0.0
            cluster_pitches: List[float] = []
            for c_id in range(k):
                c_idx = np.where(labels == c_id)[0]
                c_p = [pitches[idx] for idx in c_idx if pitches[idx] is not None and pitches[idx] > 0]
                if c_p:
                    cluster_pitches.append(float(np.median(c_p)))

            if len(cluster_pitches) >= 2:
                pitch_diff = max(cluster_pitches) - min(cluster_pitches)
                if pitch_diff > 45.0:  # Significant vocal range difference (e.g. male vs female)
                    pitch_boost = min(0.20, pitch_diff / 300.0)

            total_score = sil + pitch_boost

            if total_score > best_score:
                best_score = total_score
                best_k = k
                best_labels = labels

        # If best silhouette score is weak (< 0.20) and min_k == 1, prefer 1 speaker
        if min_k == 1 and best_score < 0.20:
            return np.zeros(n, dtype=int)

        return best_labels

    def diarize(
        self,
        segments: List[TranscriptSegment],
        source_audio_path: Path,
        min_speakers: int = 1,
        max_speakers: int = 6,
    ) -> DiarizationResult:
        """Perform acoustic diarization across a list of transcript segments."""
        if not segments:
            return DiarizationResult(speakers=[], segment_assignments={})

        n_segments = len(segments)
        features_list: List[np.ndarray] = []
        pitches_list: List[Optional[float]] = []

        # Extract features for all segments
        for seg in segments:
            duration = max(0.0, seg.end_time - seg.start_time)
            samples = self.extract_audio_slice(source_audio_path, seg.start_time, duration)
            feat, p = self.extract_features(samples)
            features_list.append(feat)
            pitches_list.append(p)

        features = np.array(features_list, dtype=np.float32)

        # Fill silent/empty segments with global average feature
        valid_mask = np.linalg.norm(features, axis=1) > 1e-4
        if np.any(valid_mask):
            mean_valid = np.mean(features[valid_mask], axis=0)
            for i in range(n_segments):
                if not valid_mask[i]:
                    features[i] = mean_valid

        # Clustering
        dist_matrix = self.compute_cosine_distance_matrix(features)
        cluster_labels = self.find_optimal_clusters(
            dist_matrix, pitches_list, min_speakers=min_speakers, max_speakers=max_speakers
        )

        # Rank clusters by total speaking duration so SPEAKER_01 has the most speech
        unique_clusters = np.unique(cluster_labels)
        durations_by_cluster: Dict[int, float] = {}
        for c in unique_clusters:
            idx = np.where(cluster_labels == c)[0]
            durations_by_cluster[int(c)] = sum(segments[i].end_time - segments[i].start_time for i in idx)

        sorted_clusters = sorted(durations_by_cluster.keys(), key=lambda c: durations_by_cluster[c], reverse=True)
        cluster_remap = {old_c: new_idx + 1 for new_idx, old_c in enumerate(sorted_clusters)}

        # Build profiles and assignments
        speakers: List[SpeakerProfileData] = []
        assignments: Dict[str, str] = {}

        for rank_idx, old_c in enumerate(sorted_clusters):
            speaker_num = rank_idx + 1
            speaker_label = f"SPEAKER_{speaker_num:02d}"
            display_name = f"Speaker {speaker_num}"
            color = COLOR_PALETTE[rank_idx % len(COLOR_PALETTE)]

            cluster_member_indices = np.where(cluster_labels == old_c)[0]
            cluster_pitches = [
                pitches_list[i] for i in cluster_member_indices if pitches_list[i] is not None and pitches_list[i] > 0
            ]

            if cluster_pitches:
                avg_pitch = round(float(np.median(cluster_pitches)), 1)
            else:
                avg_pitch = None

            # Detect gender based on pitch
            if avg_pitch is None or avg_pitch == 0.0:
                gender = "unknown"
            elif avg_pitch < 160.0:
                gender = "male"
            else:
                gender = "female"

            # Assign smart default Khmer voice
            if gender == "female":
                assigned_provider = "edge"
                assigned_voice = "km-KH-SreymomNeural"
            else:
                assigned_provider = "edge"
                assigned_voice = "km-KH-PisethNeural"

            tot_dur = durations_by_cluster[old_c]
            seg_cnt = len(cluster_member_indices)

            for i in cluster_member_indices:
                assignments[segments[i].id] = speaker_label

            speakers.append(
                SpeakerProfileData(
                    speaker_label=speaker_label,
                    display_name=display_name,
                    detected_gender=gender,
                    average_pitch_hz=avg_pitch,
                    color=color,
                    assigned_voice_provider=assigned_provider,
                    assigned_voice_id=assigned_voice,
                    segment_count=seg_cnt,
                    total_duration=round(tot_dur, 2),
                )
            )

        return DiarizationResult(speakers=speakers, segment_assignments=assignments)

    def diarize_project(
        self,
        db: Session,
        project_id: str,
        min_speakers: int = 1,
        max_speakers: int = 6,
    ) -> DiarizationResult:
        """Run diarization on all segments of a project and persist speaker mappings."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        # Resolve source audio path
        video = project.video
        audio_path: Optional[Path] = None
        if video and video.extracted_audio_path and Path(video.extracted_audio_path).exists():
            audio_path = Path(video.extracted_audio_path)
        elif video and video.file_path and Path(video.file_path).exists():
            audio_path = Path(video.file_path)
        elif project.original_video_path and Path(project.original_video_path).exists():
            audio_path = Path(project.original_video_path)

        if not audio_path:
            raise FileNotFoundError(f"No source audio file found for project '{project_id}'.")

        transcript_segs = (
            db.query(TranscriptSegment)
            .filter(TranscriptSegment.project_id == project_id)
            .order_by(TranscriptSegment.start_time.asc())
            .all()
        )

        if not transcript_segs:
            return DiarizationResult(speakers=[], segment_assignments={})

        result = self.diarize(
            transcript_segs,
            source_audio_path=audio_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

        # 1. Update TranscriptSegment speaker labels
        for seg in transcript_segs:
            label = result.segment_assignments.get(seg.id)
            if label:
                seg.speaker_label = label

        # 2. Propagate speaker labels to TranslationSegments
        translation_segs = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .all()
        )

        speaker_by_id = {s.speaker_label: s for s in result.speakers}

        for trans in translation_segs:
            assigned_label = None
            if trans.transcript_segment_id and trans.transcript_segment_id in result.segment_assignments:
                assigned_label = result.segment_assignments[trans.transcript_segment_id]
            elif trans.source_segment_ids:
                try:
                    src_ids = json.loads(trans.source_segment_ids)
                    if isinstance(src_ids, list):
                        for sid in src_ids:
                            if sid in result.segment_assignments:
                                assigned_label = result.segment_assignments[sid]
                                break
                except Exception:
                    pass

            if assigned_label:
                trans.speaker_label = assigned_label

        # 3. Replace ProjectSpeaker records
        db.query(ProjectSpeaker).filter(ProjectSpeaker.project_id == project_id).delete(synchronize_session="fetch")

        for spk in result.speakers:
            db_speaker = ProjectSpeaker(
                project_id=project_id,
                speaker_label=spk.speaker_label,
                display_name=spk.display_name,
                detected_gender=spk.detected_gender,
                average_pitch_hz=spk.average_pitch_hz,
                color=spk.color,
                assigned_voice_provider=spk.assigned_voice_provider,
                assigned_voice_id=spk.assigned_voice_id,
                segment_count=spk.segment_count,
                total_duration=spk.total_duration,
                created_at=get_cambodia_now_naive(),
                updated_at=get_cambodia_now_naive(),
            )
            db.add(db_speaker)

        db.commit()
        return result

    def apply_speaker_voice(
        self,
        db: Session,
        project_id: str,
        speaker_label: str,
        provider: str,
        voice_id: str,
    ) -> int:
        """Apply a chosen voice to all translation segments assigned to this speaker."""
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        speaker = (
            db.query(ProjectSpeaker)
            .filter(ProjectSpeaker.project_id == project_id, ProjectSpeaker.speaker_label == speaker_label)
            .first()
        )
        if speaker:
            speaker.assigned_voice_provider = provider
            speaker.assigned_voice_id = voice_id
            speaker.updated_at = get_cambodia_now_naive()

        # Find all translation segments belonging to this speaker
        all_segments = (
            db.query(TranslationSegment)
            .filter(TranslationSegment.project_id == project_id)
            .all()
        )

        matched_segments = []
        for seg in all_segments:
            is_match = (seg.speaker_label == speaker_label)
            if not is_match:
                if seg.transcript_segment and seg.transcript_segment.speaker_label == speaker_label:
                    is_match = True
                    seg.speaker_label = speaker_label
                elif seg.source_segment_ids:
                    try:
                        src_ids = json.loads(seg.source_segment_ids)
                        if isinstance(src_ids, list):
                            t_seg = db.query(TranscriptSegment).filter(
                                TranscriptSegment.id.in_(src_ids),
                                TranscriptSegment.speaker_label == speaker_label
                            ).first()
                            if t_seg:
                                is_match = True
                                seg.speaker_label = speaker_label
                    except Exception:
                        pass
            if is_match:
                matched_segments.append(seg)
                set_unit_voice(db, project, seg, provider, voice_id)

        db.commit()
        return len(matched_segments)
