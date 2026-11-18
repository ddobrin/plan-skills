#!/usr/bin/env python3
"""Wall-clock, swarm_wait-aware turn segmentation, concurrency, and Gantt geometry for /swarm runs."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


DEFAULT_IDLE_GAP_S = 120.0
DEFAULT_GANTT_CLUSTER_GAP_S = 300.0
HANDOFF_OVERLAP_TOLERANCE_S = 3.0


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


def _is_sdk_reminder(step: Dict[str, Any]) -> bool:
    return step.get("type") == "SYSTEM_MESSAGE" and step.get("source") == "SYSTEM_SDK"


def _is_system_notice(step: Dict[str, Any]) -> bool:
    if step.get("type") == "SYSTEM_MESSAGE" and step.get("source") == "SYSTEM":
        content = str(step.get("content") or "")
        header = content.split("content=", 1)[0]
        sender_match = re.search(r"\bsender=([^\s]+)", header)
        sender_id = sender_match.group(1).strip() if sender_match else ""
        if sender_id.lower() == "system":
            return True
        if "[Notice]" in header and not sender_id:
            return True
    return False


def _is_agent_wakeup(step: Dict[str, Any]) -> bool:
    if step.get("type") == "USER_INPUT":
        return True
    if step.get("type") == "SYSTEM_MESSAGE" and step.get("source") == "SYSTEM":
        if _is_system_notice(step):
            return False
        content = str(step.get("content") or "")
        return "sender=" in content or "[Message]" in content or "[swarm]" in content or "[board]" in content
    return False


def _infer_swarm_turn_label(turn_index: int, first_step: Dict[str, Any]) -> str:
    """Infer a concise label for a /swarm agent wakeup turn."""
    st = first_step.get("type", "")
    content = str(first_step.get("content") or "")
    if st == "USER_INPUT":
        m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", content, re.DOTALL)
        raw = m.group(1) if m else content
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            return f"User: {line[:42]}..." if len(line) > 45 else f"User: {line}"
        return "Initial User Request" if turn_index == 1 else f"User Follow-up #{turn_index}"
    if "You have just started" in content or "Your assignment (recorded on the board" in content:
        return "Initial Brief"
    m_board = re.search(r"\[swarm\]\s+new board message\s+(#\d+)", content)
    if m_board:
        return f"Board wake ({m_board.group(1)})"
    m_latest = re.search(r"\[board\]\s+the latest message is\s+(#\d+)", content)
    if m_latest:
        return f"Board sync ({m_latest.group(1)})"
    if "/task-" in content or 'Task id "' in content:
        m_task = re.search(r"/(task-\d+)", content)
        return f"Task done ({m_task.group(1)})" if m_task else "Background task done"
    if "sender=" in content:
        return "Timer / Wakeup" if turn_index > 1 else "Initial Dispatch"
    return "Initial Execution" if turn_index == 1 else f"Turn {turn_index}"


def _step_tokens(steps: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    in_tok = out_tok = cache_tok = 0
    for s in steps:
        if s.get("type") != "PLANNER_RESPONSE":
            continue
        in_tok += int(s.get("input_tokens") or 0)
        out_tok += int(s.get("output_tokens") or 0)
        cache_tok += int(s.get("cache_read_tokens") or 0)
    return {
        "input": in_tok,
        "output": out_tok,
        "cache_read": cache_tok,
        "total": in_tok + out_tok + cache_tok,
    }


def _finalize_turn(
    index: int,
    start_dt: datetime,
    end_dt: datetime,
    steps: Sequence[Dict[str, Any]],
    label: str,
) -> Dict[str, Any]:
    dur_s = max(0.0, (end_dt - start_dt).total_seconds())
    tool_calls = sum(len(s.get("tool_calls") or []) for s in steps)
    tokens = _step_tokens(steps)
    return {
        "index": index,
        "label": label,
        "start_iso": start_dt.isoformat().replace("+00:00", "Z"),
        "end_iso": end_dt.isoformat().replace("+00:00", "Z"),
        "start_local": format_local_clock(start_dt),
        "end_local": format_local_clock(end_dt),
        "start_ms": int(start_dt.timestamp() * 1000),
        "end_ms": int(end_dt.timestamp() * 1000),
        "duration_s": round(dur_s, 3),
        "duration_label": format_duration(dur_s),
        "step_count": len(steps),
        "tool_call_count": tool_calls,
        "tokens": tokens,
    }


def _finalize_wait(
    index: int,
    start_dt: datetime,
    end_dt: datetime,
    reason: str,
) -> Dict[str, Any]:
    dur_s = max(0.0, (end_dt - start_dt).total_seconds())
    return {
        "index": index,
        "reason": reason,
        "start_iso": start_dt.isoformat().replace("+00:00", "Z"),
        "end_iso": end_dt.isoformat().replace("+00:00", "Z"),
        "start_local": format_local_clock(start_dt),
        "end_local": format_local_clock(end_dt),
        "start_ms": int(start_dt.timestamp() * 1000),
        "end_ms": int(end_dt.timestamp() * 1000),
        "duration_s": round(dur_s, 3),
        "duration_label": format_duration(dur_s),
    }


def segment_swarm_turns(
    steps: Sequence[Dict[str, Any]],
    spawn_ts: Optional[datetime] = None,
    idle_gap_s: float = DEFAULT_IDLE_GAP_S,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split a /swarm agent transcript into active turns and parked wait intervals.

    Recognizes ``swarm_wait`` tool calls as explicit board-parking boundaries so
    free sleeping time does not inflate active execution duration, while also
    distinguishing background shell waits and idle pauses.
    """
    timed_steps: List[Tuple[datetime, Dict[str, Any]]] = []
    for step in steps:
        dt = parse_iso_timestamp(step.get("created_at"))
        if dt is not None:
            timed_steps.append((dt, step))

    if not timed_steps:
        if spawn_ts is not None:
            return [_finalize_turn(1, spawn_ts, spawn_ts, [], "Initial Brief")], []
        return [], []

    turns: List[Dict[str, Any]] = []
    waits: List[Dict[str, Any]] = []

    cur_start: Optional[datetime] = None
    cur_end: Optional[datetime] = None
    cur_steps: List[Dict[str, Any]] = []
    cur_label = "Turn 1"

    idle_since_dt: Optional[datetime] = None
    idle_reason = "idle"
    pending_sdk_steps: List[Tuple[datetime, Dict[str, Any]]] = []

    # Track pending GENERIC outputs after a PLANNER_RESPONSE that called swarm_wait
    pending_wait_generics = 0
    saw_background_task = False

    for dt, step in timed_steps:
        step_type = step.get("type", "")
        is_passive_system = _is_sdk_reminder(step) or _is_system_notice(step)
        is_wakeup = _is_agent_wakeup(step)

        if is_passive_system and (cur_start is None or idle_since_dt is not None):
            pending_sdk_steps.append((dt, step))
            continue

        should_split = False
        if cur_start is not None:
            if step_type == "USER_INPUT" and (dt - (cur_end or cur_start)).total_seconds() >= 1.0:
                should_split = True
            elif idle_since_dt is not None:
                gap_s = (dt - idle_since_dt).total_seconds()
                if idle_reason == "swarm_wait" and gap_s >= 1.0:
                    should_split = True
                elif is_wakeup and gap_s >= 0.5:
                    should_split = True
                elif gap_s >= idle_gap_s:
                    should_split = True

        if should_split and cur_start is not None and cur_end is not None:
            wait_origin = idle_since_dt or cur_end
            wait_gap = (dt - wait_origin).total_seconds()
            if wait_gap >= 1.0:
                waits.append(_finalize_wait(len(waits) + 1, wait_origin, dt, idle_reason))
            turns.append(_finalize_turn(len(turns) + 1, cur_start, cur_end, cur_steps, cur_label))
            cur_start = dt
            cur_end = dt
            cur_steps = [s for _, s in pending_sdk_steps] + [step]
            cur_label = _infer_swarm_turn_label(len(turns) + 1, step)
            pending_sdk_steps.clear()
            idle_since_dt = None
            idle_reason = "idle"
            pending_wait_generics = 0
        else:
            if cur_start is None:
                cur_start = (
                    spawn_ts
                    if (spawn_ts is not None and spawn_ts < dt and (dt - spawn_ts).total_seconds() <= 60.0)
                    else dt
                )
                cur_end = dt
                cur_label = _infer_swarm_turn_label(1, step)
            if pending_sdk_steps:
                for p_dt, p_step in pending_sdk_steps:
                    cur_steps.append(p_step)
                    if cur_end is None or p_dt > cur_end:
                        cur_end = p_dt
                pending_sdk_steps.clear()
            if cur_end is None or dt >= cur_end:
                cur_end = dt
            cur_steps.append(step)

        # Update parking state after appending step
        if step_type == "PLANNER_RESPONSE":
            tcs = step.get("tool_calls") or []
            tc_names = [str(tc.get("name") or "") for tc in tcs]
            if "swarm_wait" in tc_names:
                pending_wait_generics = len(tcs)
                idle_since_dt = None
            elif len(tcs) == 0:
                idle_since_dt = dt
                txt_low = str(step.get("content") or "").lower()
                if saw_background_task and ("waiting for" in txt_low or "task-" in txt_low):
                    idle_reason = "background_task"
                else:
                    idle_reason = "idle"
                pending_wait_generics = 0
            else:
                idle_since_dt = None
                pending_wait_generics = 0
        elif step_type == "GENERIC":
            cnt = str(step.get("content") or "")
            if "Tool is running as a background task" in cnt:
                saw_background_task = True
            if pending_wait_generics > 0:
                pending_wait_generics -= 1
                if pending_wait_generics == 0 or "Waiting for " in cnt:
                    idle_since_dt = dt
                    idle_reason = "swarm_wait"
                    pending_wait_generics = 0
        elif not is_passive_system:
            if not (idle_since_dt is not None and is_wakeup and (dt - idle_since_dt).total_seconds() < 0.5):
                idle_since_dt = None

    if cur_start is None and pending_sdk_steps:
        cur_start = (
            spawn_ts
            if (spawn_ts is not None and spawn_ts < pending_sdk_steps[0][0] and (pending_sdk_steps[0][0] - spawn_ts).total_seconds() <= 60.0)
            else pending_sdk_steps[0][0]
        )
        cur_end = pending_sdk_steps[-1][0]
        cur_steps = [s for _, s in pending_sdk_steps]
        cur_label = _infer_swarm_turn_label(1, cur_steps[0])
        pending_sdk_steps.clear()
    elif pending_sdk_steps and cur_start is not None and cur_end is not None:
        for p_dt, p_step in pending_sdk_steps:
            if idle_since_dt is None or (p_dt - idle_since_dt).total_seconds() <= 5.0:
                cur_steps.append(p_step)
                if p_dt > cur_end:
                    cur_end = p_dt

    if cur_start is not None and cur_end is not None:
        turns.append(_finalize_turn(len(turns) + 1, cur_start, cur_end, cur_steps, cur_label))

    return turns, waits


def merge_intervals(intervals: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Merge overlapping [start, end] intervals (in epoch seconds)."""
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
    """Return total duration across the union of [start, end] intervals."""
    return sum(max(0.0, e - s) for s, e in merge_intervals(intervals))


def compute_worker_concurrency(
    worker_intervals: Sequence[Tuple[str, float, float]],
    overlap_tolerance_s: float = HANDOFF_OVERLAP_TOLERANCE_S,
) -> int:
    """Compute peak simultaneous active workers, ignoring brief <=3s handoff overlaps."""
    if not worker_intervals:
        return 0
    by_agent: Dict[str, List[Tuple[float, float]]] = {}
    for cid, start_s, end_s in worker_intervals:
        by_agent.setdefault(cid, []).append((min(start_s, end_s), max(start_s, end_s)))

    agent_ids = list(by_agent.keys())
    if len(agent_ids) == 1:
        return 1

    # Check exact overlap > overlap_tolerance_s via sweep-line over trimmed/raw intervals
    points: Set[float] = set()
    for segs in by_agent.values():
        for s, e in segs:
            points.add(s)
            points.add(e)
    sorted_pts = sorted(points)
    peak = 1
    for i in range(len(sorted_pts) - 1):
        a = sorted_pts[i]
        b = sorted_pts[i + 1]
        if b - a <= 0:
            continue
        mid = (a + b) / 2.0
        active_here: List[Tuple[str, float, float]] = []
        for cid, segs in by_agent.items():
            for s, e in segs:
                if s <= mid <= e:
                    active_here.append((cid, s, e))
                    break
        if len(active_here) <= peak:
            continue
        # Only count agents whose overlap with at least one other active agent exceeds tolerance
        # (Wait: compute largest clique of pairwise > tolerance, or filter transient <= tolerance edges)
        if b - a > overlap_tolerance_s:
            peak = max(peak, len(active_here))
        else:
            # Check if every pair in active_here overlaps > tolerance in their full interval
            confirmed = 0
            for idx_x, (cx, sx, ex) in enumerate(active_here):
                has_real = any(
                    idx_x != idx_y and (min(ex, ey) - max(sx, sy)) > overlap_tolerance_s
                    for idx_y, (_, sy, ey) in enumerate(active_here)
                )
                if has_real:
                    confirmed += 1
            peak = max(peak, confirmed or 1)
    return peak


def _build_compressed_mapper(
    active_intervals_ms: Sequence[Tuple[int, int]],
    global_start_ms: int,
    global_end_ms: int,
    cluster_gap_s: float = DEFAULT_GANTT_CLUSTER_GAP_S,
) -> Tuple[List[Dict[str, Any]], float, bool]:
    """Build piecewise-linear clusters that compress dead pauses >= cluster_gap_s."""
    if not active_intervals_ms or global_end_ms <= global_start_ms:
        return [
            {
                "raw_start_ms": global_start_ms,
                "raw_end_ms": global_end_ms,
                "comp_start_ms": 0.0,
                "comp_end_ms": max(1000.0, float(global_end_ms - global_start_ms)),
                "gap_before_s": 0.0,
            }
        ], max(1000.0, float(global_end_ms - global_start_ms)), False

    sorted_ivs = sorted((min(a, b), max(a, b)) for a, b in active_intervals_ms)
    merged: List[Tuple[int, int]] = [sorted_ivs[0]]
    for s, e in sorted_ivs[1:]:
        ps, pe = merged[-1]
        if s <= pe + int(cluster_gap_s * 1000):
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))

    has_compressed_gaps = len(merged) > 1
    clusters: List[Dict[str, Any]] = []
    cursor_comp = 0.0
    gap_visual_ms = 25000.0  # Fixed modest visual gap between compressed clusters

    for idx, (s, e) in enumerate(merged):
        gap_before_s = 0.0
        if idx > 0:
            gap_before_s = max(0.0, (s - merged[idx - 1][1]) / 1000.0)
            cursor_comp += gap_visual_ms
        span = max(1000.0, float(e - s))
        clusters.append(
            {
                "raw_start_ms": s,
                "raw_end_ms": e,
                "comp_start_ms": cursor_comp,
                "comp_end_ms": cursor_comp + span,
                "gap_before_s": round(gap_before_s, 1),
            }
        )
        cursor_comp += span

    return clusters, max(1000.0, cursor_comp), has_compressed_gaps


def _map_ms_to_pct(
    ts_ms: int,
    clusters: Sequence[Dict[str, Any]],
    comp_total_ms: float,
) -> float:
    for cl in clusters:
        rs = cl["raw_start_ms"]
        re_ = cl["raw_end_ms"]
        if ts_ms <= rs:
            return round((cl["comp_start_ms"] / comp_total_ms) * 100.0, 4)
        if ts_ms <= re_:
            frac = 0.0 if re_ <= rs else (ts_ms - rs) / (re_ - rs)
            pos = cl["comp_start_ms"] + frac * (cl["comp_end_ms"] - cl["comp_start_ms"])
            return round((pos / comp_total_ms) * 100.0, 4)
    last = clusters[-1]
    return round((last["comp_end_ms"] / comp_total_ms) * 100.0, 4)


def compute_gantt_layout(
    agents: Sequence[Dict[str, Any]],
    board_markers: Sequence[Dict[str, Any]] = (),
    cluster_gap_s: float = DEFAULT_GANTT_CLUSTER_GAP_S,
) -> Dict[str, Any]:
    """Compute True Wall-Clock and Compressed Gantt coordinates for active turns, wait spans, and board markers."""
    all_starts: List[int] = []
    all_ends: List[int] = []
    active_ivs_ms: List[Tuple[int, int]] = []

    for a in agents:
        for t in a.get("turns") or []:
            all_starts.append(t["start_ms"])
            all_ends.append(t["end_ms"])
            active_ivs_ms.append((t["start_ms"], t["end_ms"]))
        for w in a.get("waits") or []:
            all_starts.append(w["start_ms"])
            all_ends.append(w["end_ms"])
        if a.get("wall_start_ms") is not None:
            all_starts.append(a["wall_start_ms"])
        if a.get("wall_end_ms") is not None:
            all_ends.append(a["wall_end_ms"])

    if not all_starts or not all_ends:
        return {
            "wall_start_ms": 0,
            "wall_end_ms": 0,
            "has_compressed_gaps": False,
            "clusters": [],
            "rows": [],
            "markers": [],
        }

    global_start_ms = min(all_starts)
    global_end_ms = max(all_ends)
    total_span_ms = max(1, global_end_ms - global_start_ms)

    clusters, comp_total_ms, has_compressed_gaps = _build_compressed_mapper(
        active_ivs_ms, global_start_ms, global_end_ms, cluster_gap_s=cluster_gap_s
    )

    def _pct_true(ms: int) -> float:
        return round(((ms - global_start_ms) / total_span_ms) * 100.0, 4)

    def _pct_comp(ms: int) -> float:
        return _map_ms_to_pct(ms, clusters, comp_total_ms)

    rows: List[Dict[str, Any]] = []
    for a in agents:
        turn_bars_true: List[Dict[str, Any]] = []
        turn_bars_comp: List[Dict[str, Any]] = []
        for t in a.get("turns") or []:
            l_true = _pct_true(t["start_ms"])
            r_true = _pct_true(t["end_ms"])
            turn_bars_true.append({
                "left_pct": l_true,
                "width_pct": round(max(0.45, r_true - l_true), 4),
                "label": t["label"],
                "start_local": t["start_local"],
                "end_local": t["end_local"],
                "duration_label": t["duration_label"],
                "tokens": t.get("tokens", {}).get("total", 0),
            })
            l_comp = _pct_comp(t["start_ms"])
            r_comp = _pct_comp(t["end_ms"])
            turn_bars_comp.append({
                "left_pct": l_comp,
                "width_pct": round(max(0.45, r_comp - l_comp), 4),
                "label": t["label"],
                "start_local": t["start_local"],
                "end_local": t["end_local"],
                "duration_label": t["duration_label"],
                "tokens": t.get("tokens", {}).get("total", 0),
            })

        wait_bars_true: List[Dict[str, Any]] = []
        wait_bars_comp: List[Dict[str, Any]] = []
        for w in a.get("waits") or []:
            l_true = _pct_true(w["start_ms"])
            r_true = _pct_true(w["end_ms"])
            wait_bars_true.append({
                "left_pct": l_true,
                "width_pct": round(max(0.35, r_true - l_true), 4),
                "reason": w["reason"],
                "start_local": w["start_local"],
                "end_local": w["end_local"],
                "duration_label": w["duration_label"],
            })
            l_comp = _pct_comp(w["start_ms"])
            r_comp = _pct_comp(w["end_ms"])
            if r_comp - l_comp > 0.1:
                wait_bars_comp.append({
                    "left_pct": l_comp,
                    "width_pct": round(r_comp - l_comp, 4),
                    "reason": w["reason"],
                    "start_local": w["start_local"],
                    "end_local": w["end_local"],
                    "duration_label": w["duration_label"],
                })

        rows.append({
            "conv_id": a["conv_id"],
            "name": a["name"],
            "role": a["role"],
            "role_category": a["role_category"],
            "lifecycle_state": a["lifecycle_state"],
            "active_duration_label": a["active_duration_label"],
            "wait_duration_label": a["wait_duration_label"],
            "turns_true": turn_bars_true,
            "turns_comp": turn_bars_comp,
            "waits_true": wait_bars_true,
            "waits_comp": wait_bars_comp,
        })

    markers_out: List[Dict[str, Any]] = []
    for mk in board_markers:
        ms = mk.get("ts_ms")
        if ms is None:
            continue
        markers_out.append({
            "seq": mk["seq"],
            "agent": mk["agent"],
            "kind": mk["kind"],
            "label": mk["label"],
            "left_true_pct": _pct_true(ms),
            "left_comp_pct": _pct_comp(ms),
        })

    cluster_markers = []
    for cl in clusters:
        rs_dt = datetime.fromtimestamp(cl["raw_start_ms"] / 1000.0, tz=timezone.utc)
        re_dt = datetime.fromtimestamp(cl["raw_end_ms"] / 1000.0, tz=timezone.utc)
        cluster_markers.append({
            "left_pct": round((cl["comp_start_ms"] / comp_total_ms) * 100.0, 4),
            "width_pct": round(((cl["comp_end_ms"] - cl["comp_start_ms"]) / comp_total_ms) * 100.0, 4),
            "start_local": format_local_clock(rs_dt),
            "end_local": format_local_clock(re_dt),
            "gap_before_label": format_duration(cl["gap_before_s"]) if cl["gap_before_s"] > 0 else "",
        })

    return {
        "wall_start_ms": global_start_ms,
        "wall_end_ms": global_end_ms,
        "wall_start_local": format_local_clock(datetime.fromtimestamp(global_start_ms / 1000.0, tz=timezone.utc)),
        "wall_end_local": format_local_clock(datetime.fromtimestamp(global_end_ms / 1000.0, tz=timezone.utc)),
        "has_compressed_gaps": has_compressed_gaps,
        "clusters": cluster_markers,
        "rows": rows,
        "markers": markers_out,
    }
