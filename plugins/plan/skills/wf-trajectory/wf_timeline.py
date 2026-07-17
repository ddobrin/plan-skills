"""Compute CSS-Gantt geometry (percentages) from agent timing telemetry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Bar:
    agent_id: str
    label: str
    state: str
    phase_title: str
    queued_left: float
    queued_width: float
    active_left: float
    active_width: float
    duration_ms: Optional[int]


def _start(a):
    return a.started_at if a.started_at is not None else a.queued_at


def _end(a):
    s = _start(a)
    if s is None:
        return None
    if a.duration_ms is not None:
        return s + a.duration_ms
    if a.last_progress_at is not None:
        return a.last_progress_at
    return s


def _empty_bar(a) -> Bar:
    return Bar(a.agent_id, a.label, a.state, a.phase_title, 0.0, 0.0, 0.0, 0.0, a.duration_ms)


def compute_timeline(agents: list[AgentNode]) -> list[Bar]:
    if not agents:
        return []
    starts = [s for s in ((a.queued_at if a.queued_at is not None else a.started_at) for a in agents) if s is not None]
    if not starts:
        return [_empty_bar(a) for a in agents]
    t0 = min(starts)
    ends = [e for e in (_end(a) for a in agents) if e is not None]
    span = max((max(ends) - t0) if ends else 1, 1)

    def pct(t):
        return max(0.0, min(100.0, (t - t0) / span * 100.0))

    bars = []
    for a in agents:
        s = _start(a)
        if s is None:
            bars.append(_empty_bar(a))
            continue
        q = a.queued_at
        e = _end(a)
        if q is not None and q < s:
            q_left, q_width = pct(q), pct(s) - pct(q)
        else:
            q_left, q_width = pct(s), 0.0
        a_left = pct(s)
        a_width = max(pct(e) - pct(s), 0.5) if e is not None else 0.5
        a_width = min(a_width, max(0.0, 100.0 - a_left))  # never overflow the track
        bars.append(Bar(a.agent_id, a.label, a.state, a.phase_title, q_left, q_width, a_left, a_width, a.duration_ms))
    return bars
