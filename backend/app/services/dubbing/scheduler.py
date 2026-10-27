import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


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
        min_pause_seconds: float = 0.12,
        safety_margin_seconds: float = 0.05,
        max_lead_borrow_seconds: float = 0.50,
        max_group_gap_seconds: float = 2.0,
        max_group_pieces: int = 8,
        max_group_span_seconds: float = 60.0,
    ):
        self.max_tempo = max_tempo
        self.min_pause_seconds = min_pause_seconds
        self.safety_margin_seconds = safety_margin_seconds
        self.max_lead_borrow_seconds = max_lead_borrow_seconds
        self.max_group_gap_seconds = max_group_gap_seconds
        self.max_group_pieces = max_group_pieces
        self.max_group_span_seconds = max_group_span_seconds

    def schedule_timeline(
        self,
        items: List[Dict[str, Any]],
        target_duration: float,
        max_tempo: Optional[float] = None,
    ) -> List[ScheduledGroup]:
        """Group speech items, compute timeline bounds, and calculate optimal
        adaptive speeds and timing budgets.
        """
        if not items:
            return []

        active_max_tempo = float(max_tempo) if max_tempo is not None else self.max_tempo
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

            if not curr_g:
                curr_g.append(enriched_item)
            else:
                prev_end = curr_g[-1]["end_time"]
                gap = start_t - prev_end
                span = end_t - curr_g[0]["start_time"]

                # Group if within conversational gap and bounded size
                if (
                    gap <= self.max_group_gap_seconds
                    and len(curr_g) < self.max_group_pieces
                    and span <= self.max_group_span_seconds
                ):
                    curr_g.append(enriched_item)
                else:
                    raw_groups.append(curr_g)
                    curr_g = [enriched_item]

        if curr_g:
            raw_groups.append(curr_g)

        # 2. Analyze bounds and schedule each group
        scheduled_groups: List[ScheduledGroup] = []

        for g_idx, g_items in enumerate(raw_groups):
            t_orig_start = g_items[0]["start_time"]
            t_orig_end = g_items[-1]["end_time"]

            # Previous and next group boundaries
            t_prev_boundary = 0.0 if g_idx == 0 else raw_groups[g_idx - 1][-1]["end_time"]
            if g_idx < len(raw_groups) - 1:
                t_next_boundary = float(raw_groups[g_idx + 1][0]["start_time"])
                if target_duration > 0:
                    t_next_boundary = min(t_next_boundary, target_duration)
            else:
                t_next_boundary = target_duration if target_duration > 0 else t_orig_end

            # Safe group boundaries: Speech starts at the group's earliest speech onset
            # and extends forward through internal gaps and trailing silence
            k = len(g_items)
            p_total = (k - 1) * p_min
            sum_raw = sum(s["raw_duration"] for s in g_items)

            g_start = round(t_orig_start, 3)
            g_limit = round(max(g_start + 0.1, t_next_boundary), 3)
            g_avail = round(max(0.1, g_limit - g_start), 3)
            g_speech_window = max(0.05, round(g_avail - p_total - margin, 3))

            req_tempo = round(sum_raw / g_speech_window, 3) if g_speech_window > 0 else 1.0

            # Determine group status and applied tempos
            if (sum_raw + p_total) <= g_avail:
                g_status = "natural"
                g_applied_tempo = 1.0
                g_overflow = 0.0
            elif req_tempo <= active_max_tempo:
                g_status = "speed_adjusted"
                g_applied_tempo = round(req_tempo, 2)
                g_overflow = 0.0
            else:
                g_status = "needs_optimization"
                g_applied_tempo = active_max_tempo
                g_overflow = round((sum_raw / active_max_tempo) - g_speech_window, 2)

            # 3. Schedule individual pieces within group
            pieces: List[ScheduledPiece] = []
            
            # Sub-allocation of tempo per segment:
            # If group fits adaptively (req_tempo <= active_max_tempo):
            # Segments that already fit at 1.0x stay at 1.0x to avoid unnecessary acceleration.
            # Long segments absorb the remaining window up to active_max_tempo.
            if g_status == "speed_adjusted":
                short_segs = [s for s in g_items if s["raw_duration"] <= max(0.1, s["orig_duration"])]
                long_segs = [s for s in g_items if s["raw_duration"] > max(0.1, s["orig_duration"])]

                sum_short_raw = sum(s["raw_duration"] for s in short_segs)
                sum_long_raw = sum(s["raw_duration"] for s in long_segs)
                rem_speech_win = max(0.05, g_speech_window - sum_short_raw)
                long_req_tempo = round(sum_long_raw / rem_speech_win, 3) if rem_speech_win > 0 else req_tempo

                can_keep_short_natural = (long_req_tempo <= active_max_tempo and len(short_segs) > 0 and len(long_segs) > 0)
            else:
                can_keep_short_natural = False
                long_req_tempo = g_applied_tempo

            for s_idx, item in enumerate(g_items):
                slot_dur = item["orig_duration"]
                raw_dur = item["raw_duration"]
                start_t = item["start_time"]

                # Determine local available window
                if s_idx < k - 1:
                    next_start = float(g_items[s_idx + 1]["start_time"])
                    local_avail = max(0.1, next_start - start_t)
                else:
                    local_avail = max(0.1, g_limit - start_t)

                item_avail_window = round(local_avail, 2)
                item_effective_window = max(0.05, round(local_avail - margin, 2))
                item_req_tempo = round(raw_dur / item_effective_window, 2) if item_effective_window > 0 else 1.0

                if raw_dur <= item_avail_window or item_req_tempo <= 1.02:
                    item_tempo = 1.0
                    item_status = "natural"
                    item_overflow = 0.0
                elif item_req_tempo <= active_max_tempo:
                    item_tempo = min(active_max_tempo, max(1.0, item_req_tempo))
                    item_status = "speed_adjusted"
                    item_overflow = 0.0
                else:
                    item_tempo = active_max_tempo
                    item_status = "needs_optimization"
                    item_overflow = round((raw_dur / active_max_tempo) - item_effective_window, 2)
                    if item_overflow <= 0.05:
                        item_overflow = 0.06

                pieces.append(
                    ScheduledPiece(
                        idx=item.get("idx", s_idx),
                        segment_order=int(item.get("segment_order", s_idx + 1)),
                        segment_id=str(item.get("segment_id", "")),
                        start_time=round(item["start_time"], 2),
                        end_time=round(item["end_time"], 2),
                        orig_duration=round(slot_dur, 2),
                        raw_duration=round(raw_dur, 2),
                        audio_path=item.get("audio_path"),
                        allocated_start=g_start,
                        available_window=item_avail_window,
                        effective_window=item_effective_window,
                        required_tempo=item_req_tempo,
                        applied_tempo=item_tempo,
                        status=item_status,
                        overflow_seconds=item_overflow,
                        khmer_text=item.get("khmer_text", "") or "",
                        english_text=item.get("english_text", "") or "",
                        is_manually_edited=bool(item.get("is_manually_edited", False)),
                    )
                )

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
                    group_applied_tempo=g_applied_tempo,
                    group_status=g_status,
                    group_overflow=g_overflow,
                )
            )

        return scheduled_groups
