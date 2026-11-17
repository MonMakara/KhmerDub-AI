import hashlib
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class ScheduledPiece:
    """Represents a scheduled speech segment on the dubbing timeline."""
    idx: int
    segment_order: int
    segment_id: str
    start_time: float
    end_time: float
    orig_duration: float
    raw_duration: float
    audio_path: Optional[Path] = None
    allocated_start: float = 0.0
    available_window: float = 0.0
    effective_window: float = 0.0
    required_tempo: float = 1.0
    applied_tempo: float = 1.0
    status: str = "natural"  # "natural", "speed_adjusted", "needs_optimization"
    overflow_seconds: float = 0.0
    khmer_text: str = ""
    english_text: str = ""
    is_manually_edited: bool = False
    trimmed_duration: float = 0.0
    trim_start: float = 0.0
    trim_end: float = 0.0
    has_boundary_trim: bool = False
    processed_audio_path: Optional[Path] = None
    processed_duration: float = 0.0
    scheduled_start: float = 0.0
    scheduled_end: float = 0.0
    local_overflow_seconds: float = 0.0
    alignment_delay_seconds: float = 0.0


@dataclass
class ScheduledGroup:
    """Represents a conversational phrase group sharing timeline flexibility."""
    group_index: int
    pieces: List[ScheduledPiece] = field(default_factory=list)
    group_start: float = 0.0
    group_limit: float = 0.0
    group_avail: float = 0.0
    group_speech_window: float = 0.0
    sum_raw: float = 0.0
    group_required_tempo: float = 1.0
    group_applied_tempo: float = 1.0
    group_status: str = "natural"
    group_overflow: float = 0.0


class TimelineScheduler:
    """Pure deterministic scheduling engine that partitions speech segments into
    conversational phrase groups, leverages leading/trailing inter-sentence pauses,
    adaptively calculates pitch-preserving tempo factors, and distributes group slack
    to minimize timing conflicts while strictly preserving complete speech.
    """

    def __init__(
        self,
        max_tempo: float = 1.25,
        min_pause_seconds: float = 0.08,
        safety_margin_seconds: float = 0.05,
        max_lead_borrow_seconds: float = 0.50,
        max_group_gap_seconds: float = 1.5,
        max_group_pieces: int = 20,
        max_group_span_seconds: float = 75.0,
        speech_guard: Optional[Any] = None,
    ):
        self.max_tempo = max_tempo
        self.min_pause_seconds = min_pause_seconds
        self.safety_margin_seconds = safety_margin_seconds
        self.max_lead_borrow_seconds = max_lead_borrow_seconds
        self.max_group_gap_seconds = max_group_gap_seconds
        self.max_group_pieces = max_group_pieces
        self.max_group_span_seconds = max_group_span_seconds
        self._speech_guard = speech_guard

    @property
    def speech_guard(self):
        if self._speech_guard is None:
            from app.services.dubbing.speech_guard import SpeechGuardService
            self._speech_guard = SpeechGuardService(safety_margin_seconds=0.06)
        return self._speech_guard

    def _measure_variant(
        self, item: Dict[str, Any], tempo: float, trim_active: bool,
    ) -> Tuple[Optional[Path], Optional[float]]:
        """Render once from the raw master; share exact bytes with the mixer."""
        source = item.get("audio_path")
        if not source or not Path(source).is_file():
            return None, None
        from app.services.dubbing.synchronizer import AudioSynchronizationService

        source = Path(source)
        stat = source.stat()
        signature = repr((str(source.resolve()), stat.st_size, stat.st_mtime_ns,
                          tempo, trim_active, item.get("trim_start"), item.get("trim_end")))
        digest = hashlib.sha256(signature.encode()).hexdigest()[:24]
        cache = source.parent / "timing_variants"
        cache.mkdir(parents=True, exist_ok=True)
        destination = cache / f"{digest}.wav"
        sync = AudioSynchronizationService()
        if not destination.exists():
            staging = cache / f".{digest}.{uuid.uuid4().hex}.wav"
            sync.render_speech_piece(
                source, staging, tempo_factor=tempo, apply_micro_fade=True,
                trim_start=item.get("trim_start") if trim_active else None,
                trim_end=item.get("trim_end") if trim_active else None,
            )
            staging.replace(destination)
        measured = sync.video_processor.get_audio_duration(destination)
        if measured <= 0:
            raise ValueError(f"Processed speech has no measurable duration: {destination}")
        return destination, measured

    def schedule_timeline(
        self,
        items: List[Dict[str, Any]],
        target_duration: float,
        max_tempo: Optional[float] = None,
        fill_mode: str = "natural",
    ) -> List[ScheduledGroup]:
        """Group speech items, compute timeline bounds, and calculate optimal
        adaptive speeds and timing budgets using quality-first boundary trimming
        and conversational phrase-group scheduling.
        """
        if not items:
            return []

        active_max_tempo = float(max_tempo) if max_tempo is not None else (float(self.max_tempo) if self.max_tempo is not None else 1.25)
        active_max_tempo = min(1.25, max(1.0, active_max_tempo))
        p_min = self.min_pause_seconds
        margin = self.safety_margin_seconds

        # Sort chronologically by start time and segment order
        sorted_items = sorted(
            items,
            key=lambda x: (float(x.get("start_time", 0.0)), int(x.get("segment_order", 0)))
        )

        # 1. Partition into conversational phrase groups
        raw_groups: List[List[Dict[str, Any]]] = []
        curr_g: List[Dict[str, Any]] = []

        for item in sorted_items:
            start_t = max(0.0, float(item.get("start_time", 0.0)))
            end_t = max(start_t, float(item.get("end_time", start_t + 1.0)))
            raw_dur = float(item.get("raw_duration", 0.0))
            orig_dur = max(0.1, float(item.get("orig_duration", end_t - start_t)))

            enriched_item = dict(item)
            enriched_item["start_time"] = start_t
            enriched_item["end_time"] = end_t
            enriched_item["orig_duration"] = orig_dur
            enriched_item["raw_duration"] = raw_dur

            # Safe boundary detection for TTS speech audio
            audio_p = item.get("audio_path")
            if (
                item.get("has_boundary_trim") is not None
                and item.get("trimmed_duration") is not None
            ):
                enriched_item["trimmed_duration"] = float(item["trimmed_duration"])
                enriched_item["trim_start"] = float(item.get("trim_start", 0.0))
                enriched_item["trim_end"] = float(item.get("trim_end", raw_dur))
                enriched_item["has_boundary_trim"] = bool(item["has_boundary_trim"])
            elif audio_p and Path(audio_p).exists() and Path(audio_p).is_file():
                try:
                    bound = self.speech_guard.detect_speech_boundaries(Path(audio_p))
                    if bound.raw_duration > 0:
                        enriched_item["raw_duration"] = bound.raw_duration
                    enriched_item["trimmed_duration"] = bound.trimmed_duration
                    enriched_item["trim_start"] = bound.trim_start
                    enriched_item["trim_end"] = bound.trim_end
                    enriched_item["has_boundary_trim"] = bound.has_trimming
                except Exception:
                    enriched_item["trimmed_duration"] = raw_dur
                    enriched_item["trim_start"] = 0.0
                    enriched_item["trim_end"] = raw_dur
                    enriched_item["has_boundary_trim"] = False
            else:
                enriched_item["trimmed_duration"] = raw_dur
                enriched_item["trim_start"] = 0.0
                enriched_item["trim_end"] = raw_dur
                enriched_item["has_boundary_trim"] = False

            if not curr_g:
                curr_g.append(enriched_item)
            else:
                prev_end = curr_g[-1]["end_time"]
                gap = start_t - prev_end
                span = end_t - curr_g[0]["start_time"]

                # Group if within conversational gap and bounded size.
                # Never artificially split continuous speech where gap <= min_pause_seconds unless hard ceiling reached.
                is_continuous = (gap <= self.min_pause_seconds)
                exceeds_soft_capacity = (
                    len(curr_g) >= self.max_group_pieces
                    or span > self.max_group_span_seconds
                    or gap > self.max_group_gap_seconds
                )
                exceeds_hard_capacity = (span > 85.0 or len(curr_g) >= 16)

                if (not exceeds_soft_capacity) or (is_continuous and not exceeds_hard_capacity):
                    curr_g.append(enriched_item)
                else:
                    raw_groups.append(curr_g)
                    curr_g = [enriched_item]

        if curr_g:
            raw_groups.append(curr_g)

        # 2. Analyze bounds and schedule each group with forward timeline simulation
        scheduled_groups: List[ScheduledGroup] = []
        current_timeline = 0.0

        for g_idx, g_items in enumerate(raw_groups):
            t_orig_start = g_items[0]["start_time"]
            t_orig_end = g_items[-1]["end_time"]

            # Previous and next group boundaries
            if g_idx < len(raw_groups) - 1:
                t_next_boundary = float(raw_groups[g_idx + 1][0]["start_time"])
                if target_duration > 0:
                    t_next_boundary = min(t_next_boundary, target_duration)
            else:
                t_next_boundary = target_duration if target_duration > 0 else t_orig_end

            g_start = round(t_orig_start, 3)
            g_limit = round(max(g_start + 0.1, t_next_boundary), 3)
            g_avail = round(max(0.1, g_limit - g_start), 3)
            g_deadline = max(g_start + 0.05, g_limit - margin)

            k = len(g_items)
            p_total = (k - 1) * p_min
            sum_raw = sum(s["raw_duration"] for s in g_items)
            sum_trimmed = sum(s["trimmed_duration"] for s in g_items)
            g_speech_window = max(0.05, round(g_avail - p_total - margin, 3))
            req_tempo = round(sum_trimmed / g_speech_window, 3) if g_speech_window > 0 else 1.0

            # Forward-simulated placement and adaptive tempo adjustment
            if current_timeline <= g_start:
                safe_lead_gap = max(0.0, g_start - current_timeline)
                lead_borrow = min(self.max_lead_borrow_seconds, safe_lead_gap)
                actual_g_start = max(current_timeline + (p_min if current_timeline > 0 else 0.0), g_start - lead_borrow)
            else:
                actual_g_start = current_timeline + p_min

            # Quality-first initial tempo and trimming selection per item:
            # Priority A: Raw fits slot -> 1.0x, no trimming
            # Priority B: Trimmed fits slot -> 1.0x, conservative boundary trimming
            # Priority C: Pitch-preserving speed adjustment (up to 1.25x)
            tempos: Dict[int, float] = {}
            use_trim: Dict[int, bool] = {}

            for s_idx, it in enumerate(g_items):
                ord_id = int(it.get("segment_order", 0))
                raw = float(it.get("raw_duration", 0.0))
                trimmed = float(it.get("trimmed_duration", raw))
                has_trim = bool(it.get("has_boundary_trim", False))
                is_outdated = bool(it.get("is_outdated", False))
                is_missing = bool(it.get("is_missing", False)) or (raw <= 0.0)

                # Local available window before next segment or group limit
                if s_idx < k - 1:
                    local_limit = float(g_items[s_idx + 1]["start_time"])
                else:
                    local_limit = g_limit
                local_avail = round(max(0.1, local_limit - float(it["start_time"])), 2)
                local_eff = max(0.05, round(local_avail - margin, 2))

                # Safe preceding silence gap that can be borrowed without colliding with previous segment
                if s_idx > 0:
                    prev_item_end = float(g_items[s_idx - 1]["end_time"])
                    lead_gap = max(0.0, float(it["start_time"]) - prev_item_end)
                elif g_idx > 0:
                    prev_group_end = float(raw_groups[g_idx - 1][-1]["end_time"])
                    lead_gap = max(0.0, g_start - prev_group_end)
                else:
                    lead_gap = g_start
                item_lead_borrow = min(self.max_lead_borrow_seconds, lead_gap)
                tot_eff = local_eff + item_lead_borrow

                if is_outdated or is_missing:
                    tempos[ord_id] = 1.0
                    use_trim[ord_id] = False
                elif raw <= local_avail:
                    # Priority A: natural speech, untouched boundaries
                    if fill_mode == "stretch" and it.get("orig_duration", 0.0) > 0.2:
                        ratio = round(raw / float(it["orig_duration"]), 2)
                        tempos[ord_id] = max(0.50, min(1.0, ratio))
                    else:
                        tempos[ord_id] = 1.0
                    use_trim[ord_id] = False
                elif has_trim and trimmed <= local_avail:
                    # Priority B: safe boundary trimming preserves 1.0x natural speed!
                    tempos[ord_id] = 1.0
                    use_trim[ord_id] = True
                else:
                    # Priority C: gentle pitch-preserving speed adjustment
                    use_trim[ord_id] = has_trim
                    base_dur = trimmed if has_trim else raw
                    needed = round(base_dur / tot_eff, 2)
                    tempos[ord_id] = min(active_max_tempo, max(1.01, needed))

            # Iterative refinement to fit within g_deadline
            group_lead_borrow = 0.0
            t_sim_refined = actual_g_start
            for _ in range(12):
                t_sim = actual_g_start
                for s_idx, it in enumerate(g_items):
                    ord_id = int(it.get("segment_order", 0))
                    raw = float(it.get("raw_duration", 0.0))
                    trimmed = float(it.get("trimmed_duration", raw))
                    active_dur = trimmed if use_trim[ord_id] else raw
                    spd = tempos[ord_id]
                    dur = (active_dur / spd) if spd > 0 else 0.0

                    st = max(it["start_time"] - group_lead_borrow, t_sim if s_idx == 0 else (t_sim + p_min))
                    t_sim = st + dur

                t_sim_refined = t_sim
                if t_sim > g_deadline:
                    if group_lead_borrow < self.max_lead_borrow_seconds:
                        group_lead_borrow = min(self.max_lead_borrow_seconds, round(group_lead_borrow + 0.10, 2))
                    else:
                        # As last resort, enable boundary trimming on items that support it
                        can_trim = [
                            it for it in g_items
                            if it.get("has_boundary_trim") and not use_trim[int(it.get("segment_order", 0))]
                        ]
                        if can_trim:
                            for it in can_trim:
                                use_trim[int(it.get("segment_order", 0))] = True
                        else:
                            can_speed_up = [
                                it for it in g_items
                                if 1.0 < tempos[int(it.get("segment_order", 0))] < active_max_tempo
                            ]
                            if can_speed_up:
                                for it in can_speed_up:
                                    ord_id = int(it.get("segment_order", 0))
                                    tempos[ord_id] = min(active_max_tempo, round(tempos[ord_id] + 0.05, 2))
                            else:
                                break
                else:
                    break

            # Final simulation and piece creation
            pieces: List[ScheduledPiece] = []
            t_sim = actual_g_start
            g_overflow = max(0.0, round(t_sim_refined - g_deadline, 2)) if t_sim_refined > g_deadline else 0.0
            total_excess_active = sum(
                max(0.0, (it["trimmed_duration"] if use_trim[int(it.get("segment_order", 0))] else float(it.get("raw_duration", 0.0))) - float(it.get("orig_duration", 0.0)))
                for it in g_items
            )

            for s_idx, it in enumerate(g_items):
                ord_id = int(it.get("segment_order", s_idx + 1))
                raw = float(it.get("raw_duration", 0.0))
                trimmed = float(it.get("trimmed_duration", raw))
                trim_active = use_trim[ord_id]
                active_dur = trimmed if trim_active else raw
                orig = float(it.get("orig_duration", 0.1))
                spd = tempos[ord_id]
                dur = round((active_dur / spd) if spd > 0 else 0.0, 3)

                variant_path, measured_duration = self._measure_variant(it, spd, trim_active)
                if measured_duration is not None:
                    dur = measured_duration

                st = round(max(it["start_time"] - group_lead_borrow, t_sim if s_idx == 0 else (t_sim + p_min)) * 44100) / 44100
                local_limit = float(g_items[s_idx + 1]["start_time"]) if s_idx < k - 1 else g_limit
                actual_window = max(0.05, local_limit - margin - st)
                if dur > actual_window + 0.05 and 1.0 < spd < active_max_tempo:
                    # Hypothetical leading slack is unavailable when the previous
                    # measured take occupies it. Fit the actual allocated window.
                    spd = min(active_max_tempo, max(spd, math.ceil(active_dur / actual_window * 100) / 100))
                    variant_path, measured_duration = self._measure_variant(it, spd, trim_active)
                    dur = measured_duration if measured_duration is not None else active_dur / spd
                end_t = st + dur
                t_sim = end_t

                if s_idx < k - 1:
                    local_limit = float(g_items[s_idx + 1]["start_time"])
                else:
                    local_limit = g_limit
                local_avail = round(max(0.1, local_limit - float(it["start_time"])), 2)
                local_eff = max(0.05, round(local_avail - margin, 2))

                prev_t = float(g_items[s_idx - 1]["end_time"]) if s_idx > 0 else (float(raw_groups[g_idx - 1][-1]["end_time"]) if g_idx > 0 else 0.0)
                item_lead_borrow = min(self.max_lead_borrow_seconds, max(0.0, float(it["start_time"]) - prev_t))
                tot_eff = round(local_eff + item_lead_borrow, 2)
                item_req = round(active_dur / local_eff, 2) if local_eff > 0 else 1.0

                is_outdated = bool(it.get("is_outdated", False))
                is_missing = bool(it.get("is_missing", False)) or (raw <= 0.0)

                is_overflowing_item = False
                item_overflow = 0.0
                if not is_outdated and not is_missing:
                    # Placement already includes safely borrowed preceding slack.
                    # A raw/local ratio falsely flags speech that actually finishes
                    # before the next source boundary after allocation.
                    item_excess = max(0.0, end_t - (local_limit - margin))
                    if item_excess > 0.05:
                        is_overflowing_item = True
                        item_overflow = round(item_excess, 2)
                    elif g_overflow > 0.05 and item_excess > 0.03:
                        is_overflowing_item = True
                        item_overflow = round(item_excess, 2)

                if is_outdated:
                    status = "outdated"
                    overflow = 0.0
                elif is_missing:
                    status = "missing"
                    overflow = 0.0
                elif is_overflowing_item:
                    status = "needs_optimization"
                    overflow = max(0.06, item_overflow)
                elif active_dur <= local_avail and spd <= 1.01:
                    status = "natural"
                    overflow = 0.0
                else:
                    status = "speed_adjusted"
                    overflow = 0.0

                pieces.append(
                    ScheduledPiece(
                        idx=it.get("idx", s_idx),
                        segment_order=ord_id,
                        segment_id=str(it.get("segment_id", "")),
                        start_time=round(it["start_time"], 2),
                        end_time=round(it["end_time"], 2),
                        orig_duration=round(orig, 2),
                        raw_duration=round(raw, 2),
                        audio_path=it.get("audio_path"),
                        allocated_start=st,
                        available_window=local_avail,
                        effective_window=local_eff,
                        required_tempo=item_req,
                        applied_tempo=spd,
                        status=status,
                        overflow_seconds=overflow,
                        khmer_text=it.get("khmer_text", "") or "",
                        english_text=it.get("english_text", "") or "",
                        is_manually_edited=bool(it.get("is_manually_edited", False)),
                        trimmed_duration=round(trimmed, 3),
                        trim_start=it.get("trim_start", 0.0),
                        trim_end=it.get("trim_end", raw),
                        has_boundary_trim=trim_active,
                        processed_audio_path=variant_path,
                        processed_duration=dur,
                        scheduled_start=st,
                        scheduled_end=end_t,
                        local_overflow_seconds=round(max(0.0, end_t - (local_limit - margin)), 3),
                        alignment_delay_seconds=round(st - float(it["start_time"]), 3),
                    )
                )

            # Use measured placement rather than the prediction from refinement.
            g_overflow = max(0.0, round(t_sim - g_deadline, 2))

            # Original per-phrase slots are soft boundaries inside a group.
            # Preserve alignment warnings, while export readiness follows the
            # complete measured, non-overlapping schedule and its hard deadline.
            if g_overflow <= 0.05:
                for piece in pieces:
                    if piece.status == "needs_optimization":
                        piece.status = "speed_adjusted" if piece.applied_tempo > 1 else "natural"
                        piece.overflow_seconds = 0.0

            # Honest group overflow attribution: if whole group overflows deadline,
            # at least one valid piece MUST be marked with needs_optimization to prevent false export readiness!
            if g_overflow > 0.05 and not any(p.status == "needs_optimization" for p in pieces):
                valid_candidates = [
                    p for p in pieces
                    if p.status not in ("outdated", "missing")
                ]
                if valid_candidates:
                    overflow_candidates = sorted(
                        valid_candidates,
                        key=lambda p: (p.raw_duration - p.orig_duration),
                        reverse=True,
                    )
                    target_p = overflow_candidates[0]
                    target_p.status = "needs_optimization"
                    target_p.overflow_seconds = round(g_overflow, 2)

            current_timeline = t_sim
            g_overflow = max(0.0, round(t_sim - g_deadline, 2)) if t_sim > g_deadline else 0.0
            g_status = "needs_optimization" if g_overflow > 0.05 else ("speed_adjusted" if any(p.applied_tempo > 1.01 for p in pieces) else "natural")

            scheduled_groups.append(
                ScheduledGroup(
                    group_index=g_idx,
                    pieces=pieces,
                    group_start=g_start,
                    group_limit=g_limit,
                    group_avail=g_avail,
                    group_speech_window=g_speech_window,
                    sum_raw=round(sum_raw, 2),
                    group_required_tempo=round(req_tempo, 2),
                    group_applied_tempo=round(max((p.applied_tempo for p in pieces), default=1.0), 2),
                    group_status=g_status,
                    group_overflow=g_overflow,
                )
            )

        return scheduled_groups
