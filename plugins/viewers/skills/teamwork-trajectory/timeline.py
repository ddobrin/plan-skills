#!/usr/bin/env python3
"""Wall-clock, turn segmentation, concurrency, and Gantt geometry helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_IDLE_GAP_S = 120.0
DEFAULT_GANTT_CLUSTER_GAP_S = 300.0


def parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_duration(seconds: Optional[float]) -> str:
    """Format a duration in seconds into a concise human-readable string."""
    if seconds is None:
        return "—"
    secs = max(0.0, float(seconds))
    if secs < 1.0:
        return "<1s" if secs > 0 else "0s"
    total = int(round(secs))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, sec = divmod(rem, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec and not days:
        parts.append(f"{sec}s")
    return " ".join(parts) if parts else "0s"


def format_local_clock(dt: Optional[datetime], include_date: bool = False) -> str:
    """Format a UTC datetime in the machine's local timezone."""
    if dt is None:
        return "—"
    local_dt = dt.astimezone()
    if include_date:
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    return local_dt.strftime("%H:%M:%S")


def get_local_tz_label() -> str:
    """Return a concise local timezone label such as 'EST (UTC-05:00)'."""
    now_local = datetime.now().astimezone()
    tz_name = now_local.tzname() or "LOCAL"
    offset = now_local.utcoffset()
    if offset is None:
        return tz_name
    total_mins = int(offset.total_seconds() // 60)
    sign = "+" if total_mins >= 0 else "-"
    abs_mins = abs(total_mins)
    hh, mm = divmod(abs_mins, 60)
    return f"{tz_name} (UTC{sign}{hh:02d}:{mm:02d})"


def segment_active_turns(
    steps: Sequence[Dict[str, Any]],
    spawn_ts: Optional[datetime] = None,
    idle_gap_s: float = DEFAULT_IDLE_GAP_S,
) -> List[Dict[str, Any]]:
    """Split a conversation's transcript steps into active execution turns.

    A new turn begins on:
    - the first step,
    - a USER_INPUT step (after any prior step), or
    - a SYSTEM_MESSAGE arriving from a parent/sender after an idle boundary
      (previous step was a final PLANNER_RESPONSE without tool_calls, or the gap
      between steps exceeds ``idle_gap_s`` while no tool is executing).
    """
    timed_steps: List[Tuple[datetime, Dict[str, Any]]] = []
    for step in steps:
        dt = parse_iso_timestamp(step.get("created_at"))
        if dt is not None:
            timed_steps.append((dt, step))

    if not timed_steps:
        if spawn_ts is not None:
            return [_finalize_turn(1, spawn_ts, spawn_ts, [], "Initial dispatch")]
        return []

    turns: List[Dict[str, Any]] = []
    cur_start: Optional[datetime] = None
    cur_end: Optional[datetime] = None
    cur_steps: List[Dict[str, Any]] = []
    cur_label = "Turn 1"
    prev_dt: Optional[datetime] = None
    prev_idle_boundary = False

    for dt, step in timed_steps:
        step_type = step.get("type", "")
        source = step.get("source", "")
        content = str(step.get("content") or "")
        is_wakeup = step_type == "USER_INPUT" or (
            step_type == "SYSTEM_MESSAGE"
            and source == "SYSTEM"
            and ("sender=" in content or "[Message]" in content)
        )
        gap = (dt - prev_dt).total_seconds() if prev_dt is not None else 0.0
        should_split = False

        if cur_start is not None:
            if step_type == "USER_INPUT" and prev_dt is not None and gap >= 1.0:
                should_split = True
            elif is_wakeup and prev_idle_boundary and gap >= 5.0:
                should_split = True
            elif prev_idle_boundary and gap >= idle_gap_s:
                should_split = True

        if should_split and cur_start is not None and cur_end is not None:
            turns.append(_finalize_turn(len(turns) + 1, cur_start, cur_end, cur_steps, cur_label))
            cur_start = dt
            cur_end = dt
            cur_steps = [step]
            cur_label = _infer_turn_label(len(turns) + 1, step)
        else:
            if cur_start is None:
                cur_start = spawn_ts if (spawn_ts is not None and spawn_ts < dt and (dt - spawn_ts).total_seconds() <= 60.0) else dt
                cur_label = _infer_turn_label(1, step)
            cur_end = dt if cur_end is None or dt >= cur_end else cur_end
            cur_steps.append(step)

        tool_calls = step.get("tool_calls") or []
        prev_idle_boundary = step_type == "PLANNER_RESPONSE" and len(tool_calls) == 0
        prev_dt = dt

    if cur_start is not None and cur_end is not None:
        turns.append(_finalize_turn(len(turns) + 1, cur_start, cur_end, cur_steps, cur_label))

    return turns


def _infer_turn_label(turn_num: int, first_step: Dict[str, Any]) -> str:
    if turn_num == 1:
        return "Initial run"
    if first_step.get("type") == "USER_INPUT":
        return f"Round {turn_num} (user prompt)"
    content = str(first_step.get("content") or "")
    if "sender=" in content:
        return f"Round {turn_num} (message wakeup)"
    return f"Round {turn_num}"


def _finalize_turn(
    index: int,
    start_dt: datetime,
    end_dt: datetime,
    steps: Sequence[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    duration_s = max(0.0, (end_dt - start_dt).total_seconds())
    tool_calls = sum(len(s.get("tool_calls") or []) for s in steps)
    in_tok = sum(int(s.get("input_tokens") or 0) for s in steps)
    cache_tok = sum(int(s.get("cache_read_tokens") or 0) for s in steps)
    out_tok = sum(int(s.get("output_tokens") or 0) for s in steps)
    return {
        "index": index,
        "label": label,
        "start_iso": start_dt.isoformat().replace("+00:00", "Z"),
        "end_iso": end_dt.isoformat().replace("+00:00", "Z"),
        "start_ms": int(start_dt.timestamp() * 1000),
        "end_ms": int(end_dt.timestamp() * 1000),
        "start_local": format_local_clock(start_dt),
        "end_local": format_local_clock(end_dt),
        "start_local_full": format_local_clock(start_dt, include_date=True),
        "end_local_full": format_local_clock(end_dt, include_date=True),
        "duration_s": round(duration_s, 3),
        "duration_label": format_duration(duration_s),
        "steps": len(steps),
        "tool_calls": tool_calls,
        "tokens": in_tok + cache_tok + out_tok,
    }


def merge_intervals(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Merge overlapping [start, end] numeric intervals."""
    if not intervals:
        return []
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged: List[Tuple[float, float]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def total_merged_duration(intervals: Sequence[Tuple[float, float]]) -> float:
    """Return total duration across merged intervals."""
    return sum(max(0.0, end - start) for start, end in merge_intervals(intervals))


def compute_peak_concurrency(intervals: Sequence[Tuple[float, float]]) -> int:
    """Compute maximum number of simultaneously active intervals."""
    events: List[Tuple[float, int]] = []
    for start, end in intervals:
        if end <= start:
            # Point-in-time single-step call still counts as 1
            events.append((start, 1))
            events.append((start + 0.001, -1))
        else:
            events.append((start, 1))
            events.append((end, -1))
    # Process ends (-1) before starts (+1) at identical timestamps
    events.sort(key=lambda item: (item[0], item[1]))
    cur = 0
    peak = 0
    for _, delta in events:
        cur += delta
        if cur > peak:
            peak = cur
    return peak


def compute_gantt_layout(
    agents: Sequence[Dict[str, Any]],
    cluster_gap_s: float = DEFAULT_GANTT_CLUSTER_GAP_S,
) -> Dict[str, Any]:
    """Compute true wall-clock and gap-compressed Gantt coordinates for all agents."""
    raw_intervals: List[Tuple[float, float]] = []
    min_ms: Optional[int] = None
    max_ms: Optional[int] = None

    for agent in agents:
        for turn in agent.get("turns") or []:
            s_ms = turn["start_ms"]
            e_ms = max(s_ms, turn["end_ms"])
            raw_intervals.append((s_ms / 1000.0, e_ms / 1000.0))
            if min_ms is None or s_ms < min_ms:
                min_ms = s_ms
            if max_ms is None or e_ms > max_ms:
                max_ms = e_ms

    if min_ms is None or max_ms is None:
        return {
            "has_timing": False,
            "has_compressed_gaps": False,
            "clusters": [],
            "gaps": [],
            "true_span_s": 0.0,
            "true_span_label": "0s",
        }

    true_span_ms = max(1000, max_ms - min_ms)
    true_span_s = max(0.0, (max_ms - min_ms) / 1000.0)

    # Build active clusters by joining intervals closer than cluster_gap_s
    merged = merge_intervals(raw_intervals)
    clusters: List[Tuple[float, float]] = []
    for start_s, end_s in merged:
        if not clusters:
            clusters.append((start_s, max(end_s, start_s + 1.0)))
        else:
            prev_s, prev_e = clusters[-1]
            if start_s - prev_e <= cluster_gap_s:
                clusters[-1] = (prev_s, max(prev_e, end_s, start_s + 1.0))
            else:
                clusters.append((start_s, max(end_s, start_s + 1.0)))

    gap_count = max(0, len(clusters) - 1)
    gap_pct_each = 4.0 if gap_count > 0 else 0.0
    if gap_count * gap_pct_each > 36.0:
        gap_pct_each = 36.0 / gap_count
    active_pct_budget = 100.0 - gap_count * gap_pct_each
    total_cluster_s = sum(max(1.0, c_end - c_start) for c_start, c_end in clusters)

    cluster_bands: List[Dict[str, Any]] = []
    gap_bands: List[Dict[str, Any]] = []
    cursor_pct = 0.0

    for idx, (c_start, c_end) in enumerate(clusters):
        c_dur = max(1.0, c_end - c_start)
        c_width = (c_dur / total_cluster_s) * active_pct_budget
        cluster_bands.append({
            "index": idx,
            "start_s": c_start,
            "end_s": c_end,
            "left_pct": round(cursor_pct, 4),
            "width_pct": round(c_width, 4),
            "start_local": format_local_clock(datetime.fromtimestamp(c_start, tz=timezone.utc), include_date=True),
            "end_local": format_local_clock(datetime.fromtimestamp(c_end, tz=timezone.utc), include_date=True),
        })
        cursor_pct += c_width
        if idx < len(clusters) - 1:
            next_start = clusters[idx + 1][0]
            pause_s = max(0.0, next_start - c_end)
            gap_bands.append({
                "after_cluster": idx,
                "pause_s": round(pause_s, 1),
                "pause_label": format_duration(pause_s),
                "left_pct": round(cursor_pct, 4),
                "width_pct": round(gap_pct_each, 4),
            })
            cursor_pct += gap_pct_each

    def map_compressed(t_s: float) -> float:
        for band in cluster_bands:
            if t_s <= band["end_s"] or band["index"] == len(cluster_bands) - 1:
                clamped = min(max(t_s, band["start_s"]), band["end_s"])
                span = max(1.0, band["end_s"] - band["start_s"])
                frac = (clamped - band["start_s"]) / span
                return band["left_pct"] + frac * band["width_pct"]
        return 100.0

    for agent in agents:
        for turn in agent.get("turns") or []:
            s_ms = turn["start_ms"]
            e_ms = turn["end_ms"]
            # True wall-clock coordinates
            true_left = ((s_ms - min_ms) / true_span_ms) * 100.0
            true_width = max(0.6, ((e_ms - s_ms) / true_span_ms) * 100.0)
            if true_left + true_width > 100.0:
                true_width = max(0.4, 100.0 - true_left)

            # Compressed-gap coordinates
            comp_left = map_compressed(s_ms / 1000.0)
            comp_right = map_compressed(e_ms / 1000.0)
            comp_width = max(0.8, comp_right - comp_left)
            if comp_left + comp_width > 100.0:
                comp_width = max(0.5, 100.0 - comp_left)

            turn["gantt_true_left_pct"] = round(true_left, 4)
            turn["gantt_true_width_pct"] = round(true_width, 4)
            turn["gantt_comp_left_pct"] = round(comp_left, 4)
            turn["gantt_comp_width_pct"] = round(comp_width, 4)

    return {
        "has_timing": True,
        "has_compressed_gaps": len(gap_bands) > 0,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "true_span_s": round(true_span_s, 3),
        "true_span_label": format_duration(true_span_s),
        "start_local": format_local_clock(datetime.fromtimestamp(min_ms / 1000.0, tz=timezone.utc), include_date=True),
        "end_local": format_local_clock(datetime.fromtimestamp(max_ms / 1000.0, tz=timezone.utc), include_date=True),
        "clusters": cluster_bands,
        "gaps": gap_bands,
    }
