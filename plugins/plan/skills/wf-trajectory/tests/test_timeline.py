from wf_model import AgentNode
from wf_timeline import compute_timeline


def _agent(idx, qa, sa, dur, state="done"):
    return AgentNode(
        index=idx, label=f"a{idx}", phase_index=0, phase_title="P", agent_id=f"id{idx}",
        model="m", state=state, queued_at=qa, started_at=sa, duration_ms=dur,
        last_progress_at=None, tokens=1, tool_calls=1, last_tool_name=None,
        prompt_preview="", result_preview="",
    )


def test_two_overlapping_agents_anchor_and_overlap():
    # t0 = 100 (earliest queue); span = end(300) - 100 = 200
    a = _agent(0, 100, 100, 200)   # active 100..300
    b = _agent(1, 100, 150, 100)   # active 150..250
    bars = compute_timeline([a, b])
    assert len(bars) == 2
    assert bars[0].active_left == 0.0            # (100-100)/200
    assert abs(bars[0].active_width - 100.0) < 0.01  # 200/200
    assert abs(bars[1].active_left - 25.0) < 0.01    # (150-100)/200
    assert abs(bars[1].active_width - 50.0) < 0.01   # 100/200
    # overlap: b starts before a ends
    assert bars[1].active_left < 100.0


def test_queued_segment_precedes_active():
    a = _agent(0, 100, 200, 100)   # queued 100..200, active 200..300
    bars = compute_timeline([a])
    assert bars[0].queued_left == 0.0
    assert bars[0].queued_width > 0.0
    assert bars[0].active_left >= bars[0].queued_left + bars[0].queued_width - 0.01


def test_missing_timing_does_not_crash():
    a = _agent(0, None, None, None)
    bars = compute_timeline([a])
    assert bars[0].active_width >= 0.0


def test_empty_input():
    assert compute_timeline([]) == []
