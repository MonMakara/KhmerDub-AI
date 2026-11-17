import re
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DubbingGroupDefinition:
    """Represents a grouped dubbing unit combining one or more transcript segments."""
    unit_order: int
    start_time: float
    end_time: float
    duration: float
    source_segment_ids: List[str] = field(default_factory=list)
    source_segment_orders: List[int] = field(default_factory=list)
    combined_english_text: str = ""
    voice_override: tuple[str, str] | None = None


class DubbingGrouper:
    """Deterministic grouping service that groups short English transcript segments
    into coherent, dubbing-optimized speech-generation units without altering the
    underlying transcript segments or their word-level timestamps.
    """

    def __init__(
        self,
        min_duration: float = 1.2,
        target_duration: float = 3.6,
        max_duration: float = 4.8,
        max_merge_pause: float = 0.40,
    ):
        self.min_duration = min_duration
        self.target_duration = target_duration
        self.max_duration = max_duration
        self.max_merge_pause = max_merge_pause

    def group_segments(self, segments: List[Any]) -> List[DubbingGroupDefinition]:
        """Group a list of transcript segment models or dicts into dubbing units."""
        if not segments:
            return []

        # Convert to uniform dict format and sort chronologically
        norm_segs: List[Dict[str, Any]] = []
        for s in segments:
            if isinstance(s, dict):
                norm_segs.append(s)
            else:
                norm_segs.append({
                    "id": getattr(s, "id", ""),
                    "segment_order": int(getattr(s, "segment_order", 0)),
                    "start_time": float(getattr(s, "start_time", 0.0)),
                    "end_time": float(getattr(s, "end_time", 0.0)),
                    "text": str(getattr(s, "text", "") or "").strip(),
                })

        norm_segs.sort(key=lambda x: (x["start_time"], x["segment_order"]))

        groups_of_segs: List[List[Dict[str, Any]]] = []
        curr_group: List[Dict[str, Any]] = [norm_segs[0]]

        for seg in norm_segs[1:]:
            prev = curr_group[-1]
            pause = seg["start_time"] - prev["end_time"]
            curr_dur = prev["end_time"] - curr_group[0]["start_time"]
            seg_dur = seg["end_time"] - seg["start_time"]
            new_dur = seg["end_time"] - curr_group[0]["start_time"]

            # Evaluate grouping criteria
            should_merge = False
            if pause <= self.max_merge_pause and new_dur <= self.max_duration:
                # 1. Standalone unit is too short for natural independent Khmer TTS
                if curr_dur < self.min_duration:
                    should_merge = True
                # 2. Next segment is too short to stand alone
                elif seg_dur < self.min_duration:
                    should_merge = True
                # 3. Both are short enough to form a comfortable narrative phrase,
                # but only if at least one segment is short (< 2.5s) to avoid conglomerating long units
                elif new_dur <= self.target_duration and pause <= (self.max_merge_pause * 0.8):
                    if curr_dur < 2.5 or seg_dur < 2.5:
                        should_merge = True

            if seg.get("_voice_key") != prev.get("_voice_key"):
                should_merge = False

            if should_merge:
                curr_group.append(seg)
            else:
                groups_of_segs.append(curr_group)
                curr_group = [seg]

        if curr_group:
            groups_of_segs.append(curr_group)

        # Build DubbingGroupDefinition objects
        definitions: List[DubbingGroupDefinition] = []
        for idx, g in enumerate(groups_of_segs, start=1):
            g_start = round(g[0]["start_time"], 3)
            g_end = round(g[-1]["end_time"], 3)
            g_dur = round(max(0.1, g_end - g_start), 3)
            src_ids = [s["id"] for s in g]
            src_orders = [s["segment_order"] for s in g]
            
            # Combine English sentences cleanly
            combined_texts = [s["text"] for s in g if s["text"]]
            combined_en = " ".join(combined_texts)
            combined_en = re.sub(r"\s+", " ", combined_en).strip()

            definitions.append(
                DubbingGroupDefinition(
                    unit_order=idx,
                    start_time=g_start,
                    end_time=g_end,
                    duration=g_dur,
                    source_segment_ids=src_ids,
                    source_segment_orders=src_orders,
                    combined_english_text=combined_en,
                    voice_override=g[0].get("_voice_key"),
                )
            )

        return definitions
