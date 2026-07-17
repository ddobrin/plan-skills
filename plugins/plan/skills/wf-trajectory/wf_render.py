"""Render a RunReport into self-contained HTML using the template."""
from __future__ import annotations

import html
import json
import os

from wf_model import RunReport, AgentNode, transcript_path
from wf_timeline import compute_timeline


def _esc(s) -> str:
    return html.escape("" if s is None else str(s))


def _fmt_ms(ms) -> str:
    if ms is None:
        return "—"
    return f"{ms}ms" if ms < 1000 else f"{ms/1000:.1f}s"


def _fmt_int(n) -> str:
    return "—" if n is None else f"{n:,}"


def _fmt_tokens(n) -> str:
    if n is None:
        return "—"
    return f"{n/1000:.0f}k" if n >= 1000 else str(n)


def _status_class(status: str) -> str:
    s = (status or "").lower()
    if s in ("completed", "pass", "done"):
        return "ok"
    if s in ("failed", "fail", "error"):
        return "fail"
    return "run"


def render_summary(report: RunReport) -> str:
    cells = [
        ("duration", _fmt_ms(report.duration_ms)),
        ("agents", str(report.agent_count)),
        ("tokens", _fmt_tokens(report.total_tokens)),
        ("tool calls", _fmt_int(report.total_tool_calls)),
        ("model", _esc(report.default_model)),
    ]
    return "".join(
        f'<div class="stat"><span class="k">{k}</span><span class="v">{v}</span></div>'
        for k, v in cells
    )


def _agent_row(report: RunReport, a: AgentNode) -> str:
    link = "file://" + transcript_path(report, a)
    return (
        f'<details class="agent state-{_esc(a.state)}">'
        f'<summary><span class="dot"></span><span class="label">{_esc(a.label)}</span>'
        f'<span class="meta">{_esc(a.model)} · {_fmt_ms(a.duration_ms)} · '
        f'{_fmt_tokens(a.tokens)} · {_fmt_int(a.tool_calls)} tools · {_esc(a.state)}</span></summary>'
        f'<div class="body">'
        f'<div class="kv"><b>prompt</b><pre>{_esc(a.prompt_preview)}</pre></div>'
        f'<div class="kv"><b>result</b><pre>{_esc(a.result_preview)}</pre></div>'
        f'<a class="tlink" href="{_esc(link)}">open full transcript ↗</a>'
        f'</div></details>'
    )


def render_tree(report: RunReport) -> str:
    blocks = []
    for p in report.phases:
        rows = "".join(_agent_row(report, a) for a in p.agents)
        blocks.append(
            f'<details class="phase" open>'
            f'<summary><span class="ptitle">{_esc(p.title)}</span>'
            f'<span class="pdetail">{_esc(p.detail)}</span>'
            f'<span class="pcount">{len(p.agents)} agent(s)</span></summary>'
            f'<div class="agents">{rows}</div></details>'
        )
    return "".join(blocks)


def render_timeline(report: RunReport) -> str:
    bars = compute_timeline(report.agents)
    rows = []
    for b in bars:
        rows.append(
            f'<div class="trow"><span class="tlabel">{_esc(b.label)}</span>'
            f'<span class="track">'
            f'<span class="seg queued" style="left:{b.queued_left:.2f}%;width:{b.queued_width:.2f}%"></span>'
            f'<span class="seg active state-{_esc(b.state)}" '
            f'style="left:{b.active_left:.2f}%;width:{b.active_width:.2f}%" '
            f'title="{_fmt_ms(b.duration_ms)}"></span>'
            f'</span></div>'
        )
    return "".join(rows)


def render_html(report: RunReport, template: str) -> str:
    result_json = json.dumps(report.result, indent=2) if report.result is not None else "(no result)"
    repl = {
        "{{TITLE}}": _esc(f"{report.workflow_name} · {report.run_id}"),
        "{{STATUS_CLASS}}": _status_class(report.status),
        "{{STATUS}}": _esc(report.status),
        "{{SUMMARY}}": render_summary(report),
        "{{TIMELINE}}": render_timeline(report),
        "{{TREE}}": render_tree(report),
        "{{RESULT_JSON}}": _esc(result_json),
        "{{TIMESTAMP}}": _esc(report.timestamp),
    }
    out = template
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def load_template() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "assets", "template.html"), "r", encoding="utf-8") as f:
        return f.read()
