#!/usr/bin/env python3
"""Wall-clock, active-turn, worker concurrency, and Gantt geometry helpers for workflow-trajectory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


IDLE_GAP_THRESHOLD_MS = 120_000  # 2 minutes idle pause splits active turns
GANTT_COMPRESS_GAP_MS = 180_000  # 3 minutes idle cluster gap compresses on Gantt
GANTT_GAP_FRACTION = 0.02


def parse_iso_ms(ts: Optional[str]) -> Optional[int]:
    """Parse an ISO-8601 or SQLite timestamp string into UTC epoch milliseconds."""
    if not ts:
        return None
    s = str(ts).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if " " in s and "T" not in s:
        s = s.replace(" ", "T", 1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def local_tz_label() -> str:
    """Return local timezone abbreviation (e.g., EST/EDT/UTC)."""
    return datetime.now().astimezone().tzname() or "LOCAL"


def format_clock_local(ms: Optional[int], include_date: bool = False) -> str:
    """Format epoch ms in local wall-clock time."""
    if ms is None:
        return "—"
    dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S" if include_date else "%H:%M:%S")


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds into a compact human label."""
    if seconds is None or seconds < 0:
        return "0s"
    total = int(round(seconds))
    if total == 0:
        return "0s"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    parts: List[str] = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping or adjacent [start_ms, end_ms] intervals."""
    clean = sorted((min(a, b), max(a, b)) for a, b in intervals if a is not None and b is not None)
    if not clean:
        return []
    merged = [clean[0]]
    for start, end in clean[1:]:
        prev_s, prev_e = merged[-1]
        if start <= prev_e:
            merged[-1] = (prev_s, max(prev_e, end))
        else:
            merged.append((start, end))
    return merged


def sum_intervals_ms(intervals: List[Tuple[int, int]]) -> int:
    return sum(max(0, e - s) for s, e in merge_intervals(intervals))


def segment_worker_turns(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Segment a workflow worker's transcript steps into execution turns.

    Workflow agents receive one `USER_INPUT` per `await a(...)` call (1 turn for one-shot
    agents, N turns for stateful multi-turn agents), plus split on long idle pauses.
    """
    timed: List[Tuple[int, Dict[str, Any]]] = []
    for st in steps:
        ms = parse_iso_ms(st.get("created_at"))
        if ms is not None:
            timed.append((ms, st))
    if not timed:
        return []
    timed.sort(key=lambda x: (x[0], x[1].get("step_index") or 0))

    groups: List[List[Tuple[int, Dict[str, Any]]]] = []
    cur: List[Tuple[int, Dict[str, Any]]] = []
    prev_ms: Optional[int] = None

    for ms, st in timed:
        stype = st.get("type") or ""
        if cur:
            is_new_turn_input = stype == "USER_INPUT"
            is_idle_gap = prev_ms is not None and (ms - prev_ms) >= IDLE_GAP_THRESHOLD_MS
            if is_new_turn_input or is_idle_gap:
                groups.append(cur)
                cur = []
        cur.append((ms, st))
        prev_ms = ms
    if cur:
        groups.append(cur)

    turns: List[Dict[str, Any]] = []
    for idx, grp in enumerate(groups, start=1):
        s_ms = grp[0][0]
        e_ms = max(grp[-1][0], s_ms + 1000)
        tool_count = 0
        tok_in = 0
        tok_out = 0
        tok_cache = 0
        prompt_preview = ""
        for _, st in grp:
            if st.get("type") == "USER_INPUT" and not prompt_preview:
                raw = str(st.get("content") or "")
                raw = raw.replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
                prompt_preview = raw[:220]
            tcs = st.get("tool_calls") or []
            tool_count += len(tcs)
            tok_in += int(st.get("input_tokens") or 0)
            tok_out += int(st.get("output_tokens") or 0)
            tok_cache += int(st.get("cache_read_tokens") or 0)
        dur_s = round(max(1.0, (e_ms - s_ms) / 1000.0), 1)
        turns.append(
            {
                "index": idx,
                "label": f"Turn {idx}",
                "start_ms": s_ms,
                "end_ms": e_ms,
                "start_local": format_clock_local(s_ms),
                "end_local": format_clock_local(e_ms),
                "duration_s": dur_s,
                "duration_label": format_duration(dur_s),
                "step_count": len(grp),
                "tool_call_count": tool_count,
                "prompt_preview": prompt_preview,
                "tokens": {
                    "input": tok_in,
                    "output": tok_out,
                    "cache_read": tok_cache,
                    "total": tok_in + tok_out + tok_cache,
                },
            }
        )
    return turns


def compute_worker_concurrency(workers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute peak simultaneous workflow workers and parallelism speedup."""
    events: List[Tuple[int, int]] = []
    all_intervals: List[Tuple[int, int]] = []
    cum_worker_ms = 0

    for w in workers:
        for t in w.get("turns") or []:
            s, e = t.get("start_ms"), t.get("end_ms")
            if s is not None and e is not None and e > s:
                events.append((s, 1))
                events.append((e, -1))
                all_intervals.append((s, e))
                cum_worker_ms += e - s

    events.sort(key=lambda x: (x[0], x[1]))
    cur = 0
    peak = 0
    for _, delta in events:
        cur += delta
        if cur > peak:
            peak = cur

    merged_ms = sum_intervals_ms(all_intervals)
    speedup = round(cum_worker_ms / merged_ms, 2) if merged_ms > 0 else 1.0
    return {
        "peak_concurrency": peak,
        "merged_active_s": round(merged_ms / 1000.0, 1),
        "cumulative_worker_s": round(cum_worker_ms / 1000.0, 1),
        "parallelism_speedup": speedup,
    }


def _build_compressed_clusters(
    intervals: List[Tuple[int, int]],
    gap_threshold_ms: int = GANTT_COMPRESS_GAP_MS,
) -> Tuple[List[Dict[str, Any]], bool]:
    merged = merge_intervals(intervals)
    if not merged:
        return [], False
    clusters: List[Tuple[int, int]] = [merged[0]]
    for s, e in merged[1:]:
        ps, pe = clusters[-1]
        if s - pe >= gap_threshold_ms:
            clusters.append((s, e))
        else:
            clusters[-1] = (ps, max(pe, e))
    if len(clusters) <= 1:
        return [], False

    total_active = sum(max(1, e - s) for s, e in clusters)
    gap_total = GANTT_GAP_FRACTION * (len(clusters) - 1)
    avail = max(0.5, 1.0 - gap_total)

    out: List[Dict[str, Any]] = []
    cursor = 0.0
    prev_end: Optional[int] = None
    for s, e in clusters:
        gap_lbl = format_duration((s - prev_end) / 1000.0) if prev_end is not None else ""
        w = (max(1, e - s) / total_active) * avail
        out.append(
            {
                "start_ms": s,
                "end_ms": e,
                "left_pct": round(cursor * 100.0, 4),
                "width_pct": round(w * 100.0, 4),
                "start_local": format_clock_local(s),
                "end_local": format_clock_local(e),
                "gap_before_label": gap_lbl,
            }
        )
        cursor += w + GANTT_GAP_FRACTION
        prev_end = e
    return out, True


def _map_compressed_pct(ms: int, clusters: List[Dict[str, Any]]) -> float:
    for c in clusters:
        if ms <= c["start_ms"]:
            return c["left_pct"]
        if ms <= c["end_ms"]:
            span = max(1, c["end_ms"] - c["start_ms"])
            return c["left_pct"] + ((ms - c["start_ms"]) / span) * c["width_pct"]
    last = clusters[-1]
    return last["left_pct"] + last["width_pct"]


def build_gantt_model(
    workers: List[Dict[str, Any]],
    wall_start_ms: Optional[int],
    wall_end_ms: Optional[int],
) -> Dict[str, Any]:
    """Build dual-scale (Compressed Pauses + True Wall-Clock) Gantt geometry."""
    all_intervals: List[Tuple[int, int]] = []
    for w in workers:
        for t in w.get("turns") or []:
            if t.get("start_ms") is not None and t.get("end_ms") is not None:
                all_intervals.append((t["start_ms"], t["end_ms"]))

    if wall_start_ms is None and all_intervals:
        wall_start_ms = min(a for a, _ in all_intervals)
    if wall_end_ms is None and all_intervals:
        wall_end_ms = max(b for _, b in all_intervals)
    if wall_start_ms is None or wall_end_ms is None:
        return {
            "wall_start_local": "—",
            "wall_end_local": "—",
            "has_compressed_gaps": False,
            "clusters": [],
            "rows": [],
        }

    total_span = max(1000, wall_end_ms - wall_start_ms)
    clusters, has_gaps = _build_compressed_clusters(all_intervals)

    def to_true(s: int, e: int) -> Tuple[float, float]:
        left = max(0.0, min(100.0, ((s - wall_start_ms) / total_span) * 100.0))
        right = max(left, min(100.0, ((e - wall_start_ms) / total_span) * 100.0))
        return round(left, 3), round(max(0.4, right - left), 3)

    def to_comp(s: int, e: int) -> Tuple[float, float]:
        if not has_gaps:
            return to_true(s, e)
        l = _map_compressed_pct(s, clusters)
        r = _map_compressed_pct(e, clusters)
        return round(l, 3), round(max(0.4, r - l), 3)

    rows: List[Dict[str, Any]] = []
    for w in workers:
        turns_true = []
        turns_comp = []
        for t in w.get("turns") or []:
            s, e = t.get("start_ms"), t.get("end_ms")
            if s is None or e is None:
                continue
            lt, wt = to_true(s, e)
            lc, wc = to_comp(s, e)
            base = {
                "label": t["label"],
                "start_local": t["start_local"],
                "end_local": t["end_local"],
                "duration_label": t["duration_label"],
                "tokens": t["tokens"]["total"],
            }
            turns_true.append({**base, "left_pct": lt, "width_pct": wt})
            turns_comp.append({**base, "left_pct": lc, "width_pct": wc})

        rows.append(
            {
                "conv_id": w["conv_id"],
                "name": w["role"],
                "phase": w["phase"],
                "type_name": w["type_name"],
                "role_category": w["role_category"],
                "status": w["status"],
                "active_duration_label": w["active_duration_label"],
                "turns_true": turns_true,
                "turns_comp": turns_comp,
            }
        )

    return {
        "wall_start_ms": wall_start_ms,
        "wall_end_ms": wall_end_ms,
        "wall_start_local": format_clock_local(wall_start_ms),
        "wall_end_local": format_clock_local(wall_end_ms),
        "has_compressed_gaps": has_gaps,
        "clusters": clusters,
        "rows": rows,
    }
