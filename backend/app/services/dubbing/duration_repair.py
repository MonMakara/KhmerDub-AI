"""Measured, bounded timing repair for machine-generated dubbing translations.

Never replaces manually edited text, cuts audio, changes voices or raises tempo
limits. Candidate text/audio publish together only after duration validation.
"""
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.project import Project, TranslationSegment
from app.services.dubbing.timing_optimizer import TimingOptimizerService
from app.services.translation.registry import get_translation_provider
from app.services.tts.selection import effective_voice, validate_voice
from app.services.tts.registry import get_tts_provider

logger = logging.getLogger(__name__)


def preserves_protected_tokens(previous: str, candidate: str) -> bool:
    """Conservative checks, not a claim of complete semantic equivalence."""
    normalized = lambda text: text.translate(str.maketrans("០១២៣៤៥៦៧៨៩", "0123456789"))
    digits = lambda text: re.findall(r"\d+(?:[.,]\d+)*", normalized(text))
    if sorted(digits(previous)) != sorted(digits(candidate)):
        return False
    identifiers = lambda text: re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", text)
    if sorted(identifiers(previous)) != sorted(identifiers(candidate)):
        return False
    negatives = ("មិន", "ពុំ", "កុំ", "គ្មាន", "អត់")
    return not any(n in previous for n in negatives) or any(n in candidate for n in negatives)


class DurationRepairService:
    def __init__(self, optimizer: Optional[TimingOptimizerService] = None):
        self.optimizer = optimizer or TimingOptimizerService()

    def repair_project(self, project_id: str, db: Session, seed: Optional[int] = None,
                       segment_ids: Optional[set[str]] = None) -> dict:
        from app.workers.tts import synthesize_segment_audio

        project = db.get(Project, project_id)
        if project is None:
            raise ValueError("Project not found")
        try:
            provider = get_translation_provider(project.translation_provider or "nllb")
        except Exception:
            logger.warning("Timing rewrite provider unavailable; original speech preserved", exc_info=True)
            return {"attempted": 0, "updated": 0}
        changed = 0
        attempted = 0
        # Repair actual local shortages in source order, rather than rewriting
        # a naturally fitting sentence because an earlier sentence delayed it.
        analyses = self.optimizer.analyze_timeline(project_id, db)
        for item in analyses:
            if segment_ids is not None and item.translation_segment_id not in segment_ids:
                continue
            if item.raw_duration <= 0 or item.effective_window <= 0:
                continue
            # Prefer ordinary speech with modest acceleration; export retains
            # the scheduler's existing hard 1.25x limit as a final safeguard.
            budget = item.effective_window * 1.15
            if item.trimmed_duration <= budget + .05:
                continue
            segment = db.get(TranslationSegment, item.translation_segment_id)
            if not segment or segment.is_manually_edited or segment.is_outdated:
                continue
            original = segment.khmer_text
            source = item.english_text
            if not original or not source:
                continue
            observed_rate = len(original) / item.raw_duration
            char_target = max(1, int(observed_rate * budget * .92))
            # Do not hold a database read transaction through network inference.
            db.commit()
            attempted += 1
            try:
                improvement = provider.improve_translation(
                    english_text=source, current_khmer=original, style="short",
                    target_duration=item.effective_window,
                    custom_prompt=(f"Current voice took {item.raw_duration:.2f}s. Aim for about {char_target} "
                        "Khmer characters using compact natural phrasing. Preserve ALL source facts, names, "
                        "numbers, negations, conditions and instructions. Do not truncate or summarize. "
                        "If meaning cannot fit, return the original translation."),
                )
                candidate = improvement.improved_khmer_text.strip()
                if (not candidate or candidate == original or len(candidate) >= len(original)
                        or not preserves_protected_tokens(original, candidate)):
                    continue
                db.refresh(segment)
                db.refresh(project)
                if (segment.is_manually_edited or segment.is_outdated
                        or segment.khmer_text != original):
                    continue
                provider_name, voice = effective_voice(project, segment)
                validate_voice(db, provider_name, voice, legacy=not segment.voice_override_id)
                synthesize_segment_audio(project_id, segment,
                    provider=get_tts_provider(provider_name), db=db, voice=voice, seed=seed,
                    candidate_text=candidate, expected_text=original, max_duration=budget)
                changed += 1
                if project.video:
                    project.video.is_export_outdated = True
                db.commit()
            except NotImplementedError:
                # Offline NLLB has no meaning-aware rewrite API. Keep complete
                # original speech and truthful conflicts rather than regex cuts.
                break
            except Exception:
                db.rollback()
                logger.warning("Automatic timing retry preserved original unit %s", item.segment_order, exc_info=True)
        return {"attempted": attempted, "updated": changed}
