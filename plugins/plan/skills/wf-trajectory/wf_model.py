"""Parse a wf_<runId>.json Workflow run record into a typed model."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentNode:
    index: int
    label: str
    phase_index: int
    phase_title: str
    agent_id: str
    model: str
    state: str
    queued_at: Optional[int]
    started_at: Optional[int]
    duration_ms: Optional[int]
    last_progress_at: Optional[int]
    tokens: Optional[int]
    tool_calls: Optional[int]
    last_tool_name: Optional[str]
    prompt_preview: str
    result_preview: str


@dataclass
class Phase:
    index: int
    title: str
    detail: str
    agents: list = field(default_factory=list)


@dataclass
class RunReport:
    run_id: str
    workflow_name: str
    summary: str
    status: str
    duration_ms: Optional[int]
    agent_count: int
    total_tokens: Optional[int]
    total_tool_calls: Optional[int]
    default_model: str
    timestamp: str
    result: Any
    phases: list
    session_dir: str
    source_path: str

    @property
    def agents(self):
        out = []
        for p in self.phases:
            out.extend(p.agents)
        return out


def _agent_from_record(r: dict) -> AgentNode:
    return AgentNode(
        index=r.get("index", 0),
        label=r.get("label", "(unlabeled)"),
        phase_index=r.get("phaseIndex", 0),
        phase_title=r.get("phaseTitle", ""),
        agent_id=r.get("agentId", ""),
        model=r.get("model", ""),
        state=r.get("state", "unknown"),
        queued_at=r.get("queuedAt"),
        started_at=r.get("startedAt"),
        duration_ms=r.get("durationMs"),
        last_progress_at=r.get("lastProgressAt"),
        tokens=r.get("tokens"),
        tool_calls=r.get("toolCalls"),
        last_tool_name=r.get("lastToolName"),
        prompt_preview=r.get("promptPreview", ""),
        result_preview=r.get("resultPreview", ""),
    )


def parse_run(json_path: str) -> RunReport:
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)

    progress = d.get("workflowProgress", [])
    agents = [_agent_from_record(r) for r in progress if r.get("type") == "workflow_agent"]

    phase_defs = d.get("phases", [])
    by_index: dict = {}
    phases: list = []
    if phase_defs:
        for i, pd in enumerate(phase_defs):
            p = Phase(index=i, title=pd.get("title", f"Phase {i}"), detail=pd.get("detail", ""))
            by_index[i] = p
            phases.append(p)

    for a in sorted(agents, key=lambda x: x.index):
        p = by_index.get(a.phase_index)
        if p is None:
            p = Phase(index=a.phase_index, title=a.phase_title or f"Phase {a.phase_index}", detail="")
            by_index[a.phase_index] = p
            phases.append(p)
        p.agents.append(a)
    phases.sort(key=lambda p: p.index)

    # Remove empty phases (keep only those with agents)
    phases = [p for p in phases if p.agents]

    session_dir = os.path.dirname(os.path.dirname(os.path.abspath(json_path)))
    run_id = d.get("runId") or os.path.splitext(os.path.basename(json_path))[0]

    return RunReport(
        run_id=run_id,
        workflow_name=d.get("workflowName", "(unnamed)"),
        summary=d.get("summary", ""),
        status=d.get("status", "unknown"),
        duration_ms=d.get("durationMs"),
        agent_count=d.get("agentCount", len(agents)),
        total_tokens=d.get("totalTokens"),
        total_tool_calls=d.get("totalToolCalls"),
        default_model=d.get("defaultModel", ""),
        timestamp=d.get("timestamp", ""),
        result=d.get("result"),
        phases=phases,
        session_dir=session_dir,
        source_path=os.path.abspath(json_path),
    )


def transcript_path(report: RunReport, agent: AgentNode) -> str:
    return os.path.join(
        report.session_dir, "subagents", "workflows", report.run_id,
        f"agent-{agent.agent_id}.jsonl",
    )
