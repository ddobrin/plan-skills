#!/usr/bin/env python3
"""Telemetry discovery and parser for AGY dynamic `run_workflow` executions and static scripts."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote

from workflow_ast import analyze_workflow_script, load_workflow_manifest
from workflow_timeline import (
    build_gantt_model,
    compute_worker_concurrency,
    format_clock_local,
    format_duration,
    local_tz_label,
    parse_iso_ms,
    segment_worker_turns,
    sum_intervals_ms,
)


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_PHASE_LOG_RE = re.compile(r"^-\s+\[phase\]\s+(.+?)\s*$")
_AGENT_LOG_RE = re.compile(
    r"^-\s+\[agent:([^\]]+)\]\s+(.+?):\s+([a-zA-Z0-9_-]+)(?:,\s*turn\s+(\d+))?\s+\(("
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\)(?::\s*(.*))?$",
    re.I,
)
_TASK_ID_RE = re.compile(r"background task with task id:\s*([^\s]+)")
_TASK_LOG_URI_RE = re.compile(r"Task logs are available at:\s*file://([^\s]+)")
_MSG_RESULT_RE = re.compile(r'Task id\s+"([^"]+)"\s+finished with result:\s*(.*)', re.S)
_EXIT_CODE_RE = re.compile(r"Command exited with code\s+(-?\d+)")
_SKILL_FILE_RE = re.compile(r"(?:^|[/\\])skills[/\\]([a-zA-Z0-9._-]+)[/\\]SKILL\.md$", re.I)
_VERIFIER_NAME_RE = re.compile(r"\b(verif|audit|validat|review|qa|test|check|skeptic)\w*", re.I)
_RESEARCH_NAME_RE = re.compile(r"\b(research|discover|inspect|investigat|plan|architect|analy|explor)\w*", re.I)
_AUTHOR_NAME_RE = re.compile(r"\b(author|engineer|build|implement|fix|coder|refactor|migrat|edit|write)\w*", re.I)
_CHECK_CMD_RE = re.compile(
    r"\b(pytest|unittest|npm\s+test|pnpm\s+test|yarn\s+test|vitest|jest|cargo\s+test|go\s+test|"
    r"mypy|ruff|flake8|eslint|tsc|mvn\s+test|gradle\s+test|agy\s+plugin\s+validate|node\s+--check)\b",
    re.I,
)


def resolve_agy_dir(override: Optional[str] = None) -> str:
    if override:
        return os.path.abspath(os.path.expanduser(override))
    env = os.environ.get("AGY_DATA_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/.gemini/antigravity-cli"))


def resolve_workspace_root(override: Optional[str] = None) -> str:
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.abspath(os.getcwd())


def _normalize_uri_path(uri: str) -> str:
    s = uri.strip()
    if s.startswith("file://"):
        s = unquote(s[len("file://") :])
    return os.path.normpath(os.path.abspath(s))


def _workspace_matches(workspace_uris_raw: str, target_root: str) -> bool:
    if not target_root:
        return True
    target = os.path.normpath(os.path.abspath(target_root))
    try:
        uris = json.loads(workspace_uris_raw) if workspace_uris_raw else []
    except Exception:
        uris = []
    for u in uris:
        if not isinstance(u, str):
            continue
        p = _normalize_uri_path(u)
        if p == target or target.startswith(p + os.sep) or p.startswith(target + os.sep):
            return True
    return False


def _decode_arg(val: Any) -> Any:
    """Decode compact transcript JSON-encoded tool argument strings cleanly."""
    if not isinstance(val, str):
        return val
    s = val.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "{" and s[-1] == "}") or (s[0] == "[" and s[-1] == "]")):
        try:
            return json.loads(s)
        except Exception:
            return val
    return val


def _transcript_paths(agy_dir: str, conv_id: str) -> Tuple[Optional[str], Optional[str]]:
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    full_p = os.path.join(logs_dir, "transcript_full.jsonl")
    compact_p = os.path.join(logs_dir, "transcript.jsonl")
    return (full_p if os.path.isfile(full_p) else None, compact_p if os.path.isfile(compact_p) else None)


def _read_transcript(agy_dir: str, conv_id: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    full_p, compact_p = _transcript_paths(agy_dir, conv_id)
    chosen = full_p or compact_p
    if not chosen:
        return [], None
    steps: List[Dict[str, Any]] = []
    try:
        with open(chosen, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    steps.append(json.loads(line))
                except Exception:
                    continue
    except OSError:
        return [], chosen
    return steps, chosen


def _load_db_rows(agy_dir: str) -> Dict[str, Dict[str, Any]]:
    db_path = os.path.join(agy_dir, "conversation_summaries.db")
    if not os.path.isfile(db_path):
        return {}
    rows: Dict[str, Dict[str, Any]] = {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                "SELECT conversation_id, title, agent_name, parent_conversation_id, "
                "nesting_depth, step_count, last_modified_time, workspace_uris, status, killed "
                "FROM conversation_summaries"
            )
            for r in cur.fetchall():
                rows[r["conversation_id"]] = dict(r)
        finally:
            conn.close()
    except Exception:
        return {}
    return rows


def _parse_workflow_log_text(raw_text: str) -> Dict[str, Any]:
    """Parse `Logs:` / `task-<N>.log` text into phases, agent runs, log lines, and stdout Output."""
    lines = raw_text.splitlines()
    entries: List[Dict[str, Any]] = []
    phase_order: List[str] = []
    agent_runs: List[Dict[str, Any]] = []
    current_phase = "(Default)"
    output_lines: List[str] = []
    in_output = False
    log_uri = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Log: file://"):
            log_uri = stripped[len("Log: ") :].strip()
            continue
        if stripped == "Output:":
            in_output = True
            continue
        if in_output:
            output_lines.append(line)
            continue
        if stripped == "Logs:" or not stripped:
            continue
        if stripped.startswith("Workflow ") and (stripped.endswith("completed.") or "failed" in stripped.lower()):
            continue

        pm = _PHASE_LOG_RE.match(stripped)
        if pm:
            current_phase = pm.group(1).strip()
            if current_phase not in phase_order:
                phase_order.append(current_phase)
            entries.append({"kind": "phase", "phase": current_phase, "text": current_phase})
            continue

        am = _AGENT_LOG_RE.match(stripped)
        if am:
            type_name = am.group(1).strip()
            role = am.group(2).strip()
            status = am.group(3).strip().lower()
            turn_num = int(am.group(4)) if am.group(4) else None
            conv_id = am.group(5).strip()
            preview = (am.group(6) or "").strip()
            if current_phase not in phase_order:
                phase_order.append(current_phase)
            rec = {
                "type_name": type_name,
                "role": role,
                "status": status,
                "turn": turn_num,
                "conv_id": conv_id,
                "phase": current_phase,
                "preview": preview,
            }
            agent_runs.append(rec)
            entries.append(
                {
                    "kind": "agent",
                    "phase": current_phase,
                    "type_name": type_name,
                    "role": role,
                    "status": status,
                    "turn": turn_num,
                    "conv_id": conv_id,
                    "text": stripped[2:].strip() if stripped.startswith("- ") else stripped,
                }
            )
            continue

        # Regular script log() line or error line
        body = stripped[2:].strip() if stripped.startswith("- ") else stripped
        kind = "error" if any(k in body.lower() for k in ("traceback", "error:", "exception", "failed")) else "log"
        entries.append({"kind": kind, "phase": current_phase, "text": body})

    return {
        "phase_order": phase_order,
        "agent_runs": agent_runs,
        "entries": entries,
        "output": "\n".join(output_lines).strip(),
        "log_uri": log_uri,
    }


def _extract_workflow_invocations(
    agy_dir: str,
    conv_id: str,
    steps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Extract all `run_workflow` calls and their results/logs from a parent transcript."""
    invocations: List[Dict[str, Any]] = []

    # Map background task completions from SYSTEM_MESSAGE steps
    task_results: Dict[str, Tuple[Optional[int], str]] = {}
    for st in steps:
        if st.get("type") != "SYSTEM_MESSAGE":
            continue
        content = str(st.get("content") or "")
        m = _MSG_RESULT_RE.search(content)
        if m:
            tid = m.group(1).strip()
            body = m.group(2).strip()
            # Trim trailing </SYSTEM_MESSAGE> if present
            if "</SYSTEM_MESSAGE>" in body:
                body = body.split("</SYSTEM_MESSAGE>", 1)[0].strip()
            task_results[tid] = (parse_iso_ms(st.get("created_at")), body)

    step_by_idx = {int(s.get("step_index", i)): s for i, s in enumerate(steps)}

    for pos, st in enumerate(steps):
        if st.get("type") != "PLANNER_RESPONSE":
            continue
        tcs = st.get("tool_calls") or []
        if not tcs:
            continue
        wf_tcs = [tc for tc in tcs if tc.get("name") == "run_workflow"]
        if not wf_tcs:
            continue

        start_ms = parse_iso_ms(st.get("created_at"))
        base_step = int(st.get("step_index", pos))

        # Locate subsequent GENERIC tool response steps belonging to this planner turn
        generic_after: List[Dict[str, Any]] = []
        for nxt in steps[pos + 1 :]:
            ntype = nxt.get("type")
            if ntype == "PLANNER_RESPONSE" or ntype == "USER_INPUT":
                break
            if ntype == "GENERIC":
                generic_after.append(nxt)

        for tc_idx, tc in enumerate(wf_tcs):
            raw_args = tc.get("args") or {}
            script_inline = _decode_arg(raw_args.get("Script")) or ""
            script_path = _decode_arg(raw_args.get("ScriptPath")) or ""
            description = _decode_arg(raw_args.get("Description")) or ""
            wf_args = _decode_arg(raw_args.get("Args"))
            if not isinstance(wf_args, dict):
                wf_args = {}
            cwd = _decode_arg(raw_args.get("Cwd")) or ""

            # Match corresponding GENERIC step: prefer one containing task id / Workflow / Description
            matched_gen: Optional[Dict[str, Any]] = None
            for g in generic_after:
                gtxt = str(g.get("content") or "")
                if (
                    (description and description in gtxt)
                    or "Workflow " in gtxt
                    or "background task with task id:" in gtxt
                ):
                    matched_gen = g
                    break
            if matched_gen is None and tc_idx < len(generic_after):
                matched_gen = generic_after[tc_idx]

            task_id = ""
            task_log_path = ""
            result_text = ""
            end_ms: Optional[int] = None
            status = "running"
            error_text = ""

            if matched_gen is not None:
                gtxt = str(matched_gen.get("content") or "")
                g_status = str(matched_gen.get("status") or "").upper()
                g_ms = parse_iso_ms(matched_gen.get("created_at"))
                tm = _TASK_ID_RE.search(gtxt)
                if tm:
                    task_id = tm.group(1).strip()
                lm = _TASK_LOG_URI_RE.search(gtxt)
                if lm:
                    task_log_path = unquote(lm.group(1).strip())
                elif task_id and "/" in task_id:
                    tshort = task_id.split("/", 1)[1]
                    cand_log = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "tasks", f"{tshort}.log")
                    if os.path.isfile(cand_log):
                        task_log_path = cand_log

                if task_id and task_id in task_results:
                    end_ms, result_text = task_results[task_id]
                    lower_r = result_text.lower()
                    if "completed." in lower_r and "failed" not in lower_r.splitlines()[0]:
                        status = "completed"
                    elif any(w in lower_r for w in ("failed", "error", "traceback", "exception")):
                        status = "failed"
                        error_text = result_text
                    else:
                        status = "completed"
                elif not task_id:
                    # Synchronous completion
                    result_text = gtxt
                    end_ms = g_ms
                    if g_status == "ERROR" or "encountered error" in gtxt.lower() or "failed" in gtxt.lower():
                        status = "failed"
                        error_text = gtxt
                    else:
                        status = "completed"
                else:
                    # Background task not yet completed (or interrupted before notification)
                    status = "running"

            # Prefer full task log file on disk if available for Logs/Output parsing
            disk_log_text = ""
            if task_log_path and os.path.isfile(task_log_path):
                try:
                    with open(task_log_path, encoding="utf-8", errors="replace") as lf:
                        disk_log_text = lf.read()
                except OSError:
                    disk_log_text = ""

            log_source = disk_log_text if disk_log_text.strip() else result_text
            parsed_log = _parse_workflow_log_text(log_source)

            # Read ScriptPath source if inline Script was not provided
            script_source = str(script_inline) if isinstance(script_inline, str) else ""
            if not script_source and script_path and os.path.isfile(script_path):
                try:
                    with open(script_path, encoding="utf-8", errors="replace") as sf:
                        script_source = sf.read()
                except OSError:
                    script_source = ""

            invocations.append(
                {
                    "invocation_index": len(invocations) + 1,
                    "step_index": base_step,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "description": str(description) or (os.path.basename(script_path) if script_path else f"Workflow #{len(invocations) + 1}"),
                    "script_path": str(script_path),
                    "script_source": script_source,
                    "args": wf_args,
                    "cwd": str(cwd),
                    "task_id": task_id,
                    "task_log_path": task_log_path,
                    "status": status,
                    "error_text": error_text,
                    "result_text": result_text,
                    "parsed_log": parsed_log,
                }
            )
    return invocations


def list_workflow_runs(
    agy_dir: str,
    workspace_root: Optional[str] = None,
    all_workspaces: bool = False,
) -> List[Dict[str, Any]]:
    """Discover conversations containing actual `run_workflow` tool calls."""
    db_rows = _load_db_rows(agy_dir)
    brain_dir = os.path.join(agy_dir, "brain")
    if not os.path.isdir(brain_dir):
        return []

    candidate_ids: List[str] = []
    if db_rows:
        for cid, row in db_rows.items():
            if not all_workspaces and workspace_root and not _workspace_matches(row.get("workspace_uris", ""), workspace_root):
                continue
            candidate_ids.append(cid)
    else:
        for name in os.listdir(brain_dir):
            if _UUID_RE.fullmatch(name):
                candidate_ids.append(name)

    runs: List[Dict[str, Any]] = []
    for cid in candidate_ids:
        full_p, compact_p = _transcript_paths(agy_dir, cid)
        probe_p = compact_p or full_p
        if not probe_p:
            continue
        try:
            with open(probe_p, encoding="utf-8", errors="replace") as f:
                if '"run_workflow"' not in f.read():
                    continue
        except OSError:
            continue

        steps, _ = _read_transcript(agy_dir, cid)
        invocations = _extract_workflow_invocations(agy_dir, cid, steps)
        if not invocations:
            continue
        latest = invocations[-1]
        row = db_rows.get(cid, {})
        unique_workers = {a["conv_id"] for a in latest["parsed_log"]["agent_runs"]}
        runs.append(
            {
                "conversation_id": cid,
                "title": row.get("title") or latest["description"],
                "latest_description": latest["description"],
                "invocation_count": len(invocations),
                "worker_count": len(unique_workers),
                "status": latest["status"],
                "last_modified_time": row.get("last_modified_time") or format_clock_local(latest["end_ms"] or latest["start_ms"], include_date=True),
                "workspace_uris": row.get("workspace_uris") or "",
                "invocations": invocations,
            }
        )

    runs.sort(key=lambda r: r.get("last_modified_time") or "", reverse=True)
    return runs


def select_workflow_run(
    agy_dir: str,
    workspace_root: Optional[str],
    conv_id: Optional[str] = None,
) -> Optional[str]:
    """Select a parent conversation containing `run_workflow`.

    If `conv_id` is a spawned workflow worker ID (or prefix), resolves upward to its
    parent workflow conversation.
    """
    if conv_id:
        needle = conv_id.strip().lower()
        all_runs = list_workflow_runs(agy_dir, workspace_root=None, all_workspaces=True)
        for r in all_runs:
            if r["conversation_id"].lower().startswith(needle):
                return r["conversation_id"]
        # Resolve upward from a spawned workflow agent ID
        for r in all_runs:
            for inv in r["invocations"]:
                for ar in inv["parsed_log"]["agent_runs"]:
                    if ar["conv_id"].lower().startswith(needle):
                        return r["conversation_id"]
        return None

    ws_runs = list_workflow_runs(agy_dir, workspace_root=workspace_root, all_workspaces=False)
    if not ws_runs:
        return None
    # Prefer completed runs with spawned workers over empty/failed attempts if timestamps are close,
    # otherwise newest run for the workspace.
    completed = [r for r in ws_runs if r["status"] == "completed"]
    return completed[0]["conversation_id"] if completed else ws_runs[0]["conversation_id"]


def _format_finish_result(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val, indent=2, ensure_ascii=False)
    except Exception:
        return str(val)


def _extract_structured_verdict(val: Any) -> Optional[Tuple[bool, str]]:
    """Inspect a verifier/auditor agent's structured `finish` payload for an explicit verdict."""
    if not isinstance(val, dict):
        return None
    for key in ("passed", "ok", "approved", "verified", "success"):
        if isinstance(val.get(key), bool):
            notes = str(val.get("notes") or val.get("summary") or val.get("reason") or "")
            return val[key], notes
    verdict_val = val.get("verdict") or val.get("status")
    if isinstance(verdict_val, str):
        u = verdict_val.strip().upper()
        notes = str(val.get("notes") or val.get("summary") or val.get("reason") or "")
        if u in ("PASS", "PASSED", "VERIFIED", "APPROVED", "OK", "GREEN", "SUCCESS"):
            return True, notes
        if u in ("FAIL", "FAILED", "REJECTED", "RED", "ERROR"):
            return False, notes
    return None


def _classify_role(role: str, type_name: str, has_edits: bool, finish_values: List[Any]) -> Tuple[str, str]:
    text = f"{role} {type_name}"
    if _VERIFIER_NAME_RE.search(text) or any(_extract_structured_verdict(v) is not None for v in finish_values):
        return "verifier", "Verifier"
    if has_edits or _AUTHOR_NAME_RE.search(text):
        return "author", "Author"
    if type_name.lower() == "research" or _RESEARCH_NAME_RE.search(text):
        return "research", "Research & Analysis"
    return "worker", "Worker"


def _rel_display_path(path: str, workspace_root: str) -> str:
    if not path:
        return ""
    try:
        abs_p = os.path.abspath(path)
        abs_ws = os.path.abspath(workspace_root)
        if abs_p.startswith(abs_ws + os.sep):
            return os.path.relpath(abs_p, abs_ws)
    except Exception:
        pass
    return path


def _parse_worker_transcript(
    agy_dir: str,
    worker_meta: Dict[str, Any],
    workspace_root: str,
    db_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Parse one workflow agent's transcript for tokens, turns, skills, tools, files, and finish outputs."""
    cid = worker_meta["conv_id"]
    steps, tpath = _read_transcript(agy_dir, cid)
    turns = segment_worker_turns(steps)

    tok_in = 0
    tok_out = 0
    tok_cache = 0
    models_seen: List[str] = []
    tool_counts: Dict[str, int] = {}
    skills_loaded: Set[str] = set()
    docs_map: Dict[str, Dict[str, Any]] = {}
    last_edit_ms: Optional[int] = None
    commands_run: List[Dict[str, Any]] = []
    finish_results: List[Any] = []
    pending_bg_cmds: Dict[str, Dict[str, Any]] = {}
    prompts: List[str] = []

    for pos, st in enumerate(steps):
        stype = st.get("type") or ""
        ts_ms = parse_iso_ms(st.get("created_at"))

        if stype == "USER_INPUT":
            raw = str(st.get("content") or "")
            raw = raw.replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
            if raw:
                prompts.append(raw)
            continue

        if stype == "SYSTEM_MESSAGE":
            content = str(st.get("content") or "")
            m = _MSG_RESULT_RE.search(content)
            if m and m.group(1) in pending_bg_cmds:
                rec = pending_bg_cmds.pop(m.group(1))
                em = _EXIT_CODE_RE.search(m.group(2))
                if em:
                    code = int(em.group(1))
                    rec["exit_code"] = code
                    rec["status"] = "passed" if code == 0 else "failed"
                else:
                    rec["status"] = "passed"
                if ts_ms is not None:
                    rec["ts_ms"] = ts_ms
                    rec["ts_local"] = format_clock_local(ts_ms)
            continue

        if stype != "PLANNER_RESPONSE":
            continue

        model = st.get("model")
        if model and model not in models_seen:
            models_seen.append(str(model))
        tok_in += int(st.get("input_tokens") or 0)
        tok_out += int(st.get("output_tokens") or 0)
        tok_cache += int(st.get("cache_read_tokens") or 0)

        tcs = st.get("tool_calls") or []
        if not tcs:
            continue

        # Gather immediately following GENERIC responses for command exit codes
        gen_after: List[Dict[str, Any]] = []
        for nxt in steps[pos + 1 :]:
            if nxt.get("type") in ("PLANNER_RESPONSE", "USER_INPUT"):
                break
            if nxt.get("type") == "GENERIC":
                gen_after.append(nxt)

        for tc_i, tc in enumerate(tcs):
            tname = str(tc.get("name") or "")
            if not tname:
                continue
            tool_counts[tname] = tool_counts.get(tname, 0) + 1
            targs = tc.get("args") or {}

            if tname == "finish":
                res_val = _decode_arg(targs.get("result"))
                finish_results.append(res_val)

            elif tname == "read_file":
                p = str(_decode_arg(targs.get("Path")) or "")
                sm = _SKILL_FILE_RE.search(p)
                if sm:
                    skills_loaded.add(sm.group(1))

            elif tname in ("write_file", "edit_file"):
                p = str(_decode_arg(targs.get("Path")) or "")
                if p:
                    rel = _rel_display_path(p, workspace_root)
                    action = "Created" if tname == "write_file" else "Edited"
                    docs_map[rel] = {
                        "name": rel,
                        "path": f"file://{os.path.abspath(p)}",
                        "action": action,
                    }
                    if ts_ms is not None and (last_edit_ms is None or ts_ms > last_edit_ms):
                        last_edit_ms = ts_ms

            elif tname == "run_command":
                cmdline = str(_decode_arg(targs.get("CommandLine")) or "").strip()
                summary = str(_decode_arg(targs.get("toolSummary")) or "").strip()
                rec = {
                    "agent": worker_meta["role"],
                    "step_index": int(st.get("step_index", pos)),
                    "command": cmdline,
                    "summary": summary,
                    "exit_code": None,
                    "status": "unknown",
                    "task_id": "",
                    "ts_ms": ts_ms,
                    "ts_local": format_clock_local(ts_ms),
                }
                if tc_i < len(gen_after):
                    gtxt = str(gen_after[tc_i].get("content") or "")
                    tm = _TASK_ID_RE.search(gtxt)
                    if tm:
                        rec["task_id"] = tm.group(1).strip()
                        rec["status"] = "background"
                        pending_bg_cmds[rec["task_id"]] = rec
                    else:
                        em = _EXIT_CODE_RE.search(gtxt)
                        if em:
                            code = int(em.group(1))
                            rec["exit_code"] = code
                            rec["status"] = "passed" if code == 0 else "failed"
                        elif str(gen_after[tc_i].get("status") or "").upper() == "ERROR":
                            rec["exit_code"] = 1
                            rec["status"] = "failed"
                commands_run.append(rec)

    if worker_meta["type_name"] and worker_meta["type_name"] != "self":
        skills_loaded.add(f"agent:{worker_meta['type_name']}")

    fresh = tok_in + tok_out
    total_tok = fresh + tok_cache
    cache_hit = round((tok_cache / (tok_in + tok_cache)) * 100.0, 1) if (tok_in + tok_cache) > 0 else 0.0

    wall_start_ms = turns[0]["start_ms"] if turns else None
    wall_end_ms = turns[-1]["end_ms"] if turns else None
    active_ms = sum_intervals_ms([(t["start_ms"], t["end_ms"]) for t in turns])
    active_s = round(active_ms / 1000.0, 1)

    docs = list(docs_map.values())
    role_category, role_label = _classify_role(
        worker_meta["role"], worker_meta["type_name"], bool(docs), finish_results
    )

    final_result = finish_results[-1] if finish_results else None
    deliverable_text = (
        _format_finish_result(final_result)
        if final_result is not None
        else worker_meta.get("latest_preview", "")
    )

    tool_breakdown = [
        {"name": k, "count": v}
        for k, v in sorted(tool_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return {
        "conv_id": cid,
        "role": worker_meta["role"],
        "phase": worker_meta["phase"],
        "phases": worker_meta["phases"],
        "type_name": worker_meta["type_name"],
        "role_category": role_category,
        "role_label": role_label,
        "status": worker_meta["status"],
        "turn_entries": worker_meta["turn_entries"],
        "model": models_seen[-1] if models_seen else "unknown",
        "models_seen": models_seen,
        "step_count": len(steps) or int((db_row or {}).get("step_count") or 0),
        "tool_call_count": sum(tool_counts.values()),
        "tool_breakdown": tool_breakdown,
        "skills_loaded": sorted(skills_loaded),
        "wall_start_ms": wall_start_ms,
        "wall_end_ms": wall_end_ms,
        "wall_start_local": format_clock_local(wall_start_ms),
        "wall_end_local": format_clock_local(wall_end_ms),
        "active_duration_s": active_s,
        "active_duration_label": format_duration(active_s),
        "turns": turns,
        "prompts": prompts,
        "finish_results": finish_results,
        "deliverable_text": deliverable_text,
        "docs": docs,
        "last_edit_ms": last_edit_ms,
        "commands_run": commands_run,
        "transcript_uri": f"file://{tpath}" if tpath else "",
        "tokens": {
            "input": tok_in,
            "output": tok_out,
            "cache_read": tok_cache,
            "fresh": fresh,
            "total": total_tok,
            "cache_hit_pct": cache_hit,
        },
    }


def _build_verification_audit(workers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Audit whether the workflow's output was verified via verifier verdicts and/or check commands."""
    verifiers = [w for w in workers if w["role_category"] == "verifier"]
    authors = [w for w in workers if w["role_category"] == "author" or w["docs"]]

    last_author_edit_ms: Optional[int] = None
    for a in authors:
        if a["last_edit_ms"] is not None and (last_author_edit_ms is None or a["last_edit_ms"] > last_author_edit_ms):
            last_author_edit_ms = a["last_edit_ms"]

    verifier_cmds: List[Dict[str, Any]] = []
    structured_verdicts: List[Dict[str, Any]] = []
    verifier_last_ms: Optional[int] = None

    for v in verifiers:
        verifier_cmds.extend(v["commands_run"])
        if v["wall_end_ms"] is not None and (verifier_last_ms is None or v["wall_end_ms"] > verifier_last_ms):
            verifier_last_ms = v["wall_end_ms"]
        for c in v["commands_run"]:
            if c["ts_ms"] is not None and (verifier_last_ms is None or c["ts_ms"] > verifier_last_ms):
                verifier_last_ms = c["ts_ms"]
        for res in v["finish_results"]:
            sv = _extract_structured_verdict(res)
            if sv is not None:
                structured_verdicts.append(
                    {
                        "agent": v["role"],
                        "passed": sv[0],
                        "notes": sv[1],
                        "raw": _format_finish_result(res),
                        "start_ms": v.get("wall_start_ms") or 0,
                        "ts_ms": v.get("wall_end_ms") or 0,
                        "remediated": False,
                    }
                )

    author_check_cmds: List[Dict[str, Any]] = []
    for w in workers:
        if w["role_category"] == "verifier":
            continue
        for c in w["commands_run"]:
            if _CHECK_CMD_RE.search(c["command"]):
                author_check_cmds.append(c)

    ordered_after_edits = True
    if last_author_edit_ms is not None and verifier_last_ms is not None:
        ordered_after_edits = verifier_last_ms >= last_author_edit_ms

    passed_v = [c for c in verifier_cmds if c["status"] == "passed"]
    failed_v = [c for c in verifier_cmds if c["status"] == "failed"]
    last_pass_key = max(((c.get("ts_ms") or 0, c.get("step_index") or 0) for c in passed_v), default=(-1, -1))
    unresolved_failures = [c for c in failed_v if (c.get("ts_ms") or 0, c.get("step_index") or 0) > last_pass_key]
    resolved_earlier = len(failed_v) - len(unresolved_failures)

    sv_passed = [sv for sv in structured_verdicts if sv["passed"]]
    sv_failed_all = [sv for sv in structured_verdicts if not sv["passed"]]
    sv_failed: List[Dict[str, Any]] = []
    sv_remediated = 0
    for sv in sv_failed_all:
        # An earlier review failure is considered remediated ONLY if a subsequent passing
        # verifier started strictly after this failing verifier ended (e.g. a later
        # Remediation & Re-Verification phase), not merely a concurrent sibling reviewer.
        fail_end = sv.get("ts_ms") or 0
        superseded = fail_end > 0 and any(
            (p.get("start_ms") or 0) >= fail_end and p["agent"] != sv["agent"]
            for p in sv_passed
        )
        if superseded:
            sv["remediated"] = True
            sv_remediated += 1
        else:
            sv_failed.append(sv)
    verifiers_done = [v for v in verifiers if v["status"] == "done"]

    if verifiers:
        if sv_failed or unresolved_failures or (failed_v and not passed_v):
            verdict = "FAILED"
            verdict_label = "Checks Failed"
        elif not ordered_after_edits:
            verdict = "STALE"
            verdict_label = "Stale Verification (edits after last check)"
        elif sv_passed or (verifiers_done and (passed_v or any(v["deliverable_text"] for v in verifiers_done))):
            verdict = "VERIFIED"
            verdict_label = "Verified & Passed"
        elif passed_v:
            verdict = "PARTIAL"
            verdict_label = "Partially Checked"
        else:
            verdict = "UNVERIFIED"
            verdict_label = "Unverified (no completed checks)"
    elif author_check_cmds and any(c["status"] == "passed" for c in author_check_cmds):
        if any(c["status"] == "failed" for c in author_check_cmds):
            verdict = "FAILED"
            verdict_label = "Author Self-Checks Failed"
        else:
            verdict = "SELF_CHECKED"
            verdict_label = "Author Self-Checks Only (no dedicated verifier)"
    else:
        verdict = "UNVERIFIED"
        verdict_label = "Unverified (no verifier or test commands)"

    latest_report = verifiers_done[-1]["deliverable_text"] if verifiers_done else ""

    return {
        "verdict": verdict,
        "verdict_label": verdict_label,
        "has_verifier": bool(verifiers),
        "verifier_names": [v["role"] for v in verifiers],
        "ordered_after_edits": ordered_after_edits,
        "last_author_edit_local": format_clock_local(last_author_edit_ms) if last_author_edit_ms else "—",
        "verifier_last_local": format_clock_local(verifier_last_ms) if verifier_last_ms else "—",
        "passed_count": len(passed_v) + len(sv_passed),
        "failed_count": len(failed_v) + len(sv_failed_all),
        "unresolved_failure_count": len(unresolved_failures) + len(sv_failed),
        "resolved_earlier_failure_count": resolved_earlier + sv_remediated,
        "structured_verdicts": structured_verdicts,
        "verifier_commands": verifier_cmds,
        "author_check_commands": author_check_cmds,
        "latest_verifier_report": latest_report,
    }


def _capture_git_snapshot(workspace_root: str) -> Dict[str, Any]:
    try:
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if st.returncode != 0:
            return {"available": False}
        modified: List[str] = []
        untracked: List[str] = []
        for line in st.stdout.splitlines():
            if not line.strip():
                continue
            if line.startswith("??"):
                untracked.append(line[3:].strip())
            else:
                modified.append(line[3:].strip())
        ds = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {
            "available": True,
            "modified": modified,
            "untracked": untracked,
            "diffstat": ds.stdout.strip() if ds.returncode == 0 else "",
        }
    except Exception:
        return {"available": False}


def _build_rollups_and_insights(
    workers: List[Dict[str, Any]],
    phase_order: List[str],
    blueprint: Dict[str, Any],
    summary: Dict[str, Any],
    verification: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    total_tok = max(1, summary["tokens"]["total"])

    # Phase rollups
    ordered_phases = list(phase_order)
    for w in workers:
        if w["phase"] not in ordered_phases:
            ordered_phases.append(w["phase"])

    phase_rollups: List[Dict[str, Any]] = []
    for pname in ordered_phases:
        pw = [w for w in workers if w["phase"] == pname]
        if not pw:
            continue
        p_tok_total = sum(w["tokens"]["total"] for w in pw)
        p_tok_fresh = sum(w["tokens"]["fresh"] for w in pw)
        p_tok_out = sum(w["tokens"]["output"] for w in pw)
        p_act_s = round(sum(w["active_duration_s"] for w in pw), 1)
        p_starts = [w["wall_start_ms"] for w in pw if w["wall_start_ms"] is not None]
        p_ends = [w["wall_end_ms"] for w in pw if w["wall_end_ms"] is not None]
        span_s = round((max(p_ends) - min(p_starts)) / 1000.0, 1) if (p_starts and p_ends) else p_act_s
        phase_rollups.append(
            {
                "phase": pname,
                "worker_count": len(pw),
                "done_count": sum(1 for w in pw if w["status"] == "done"),
                "failed_count": sum(1 for w in pw if w["status"] not in ("done", "running")),
                "wall_span_s": span_s,
                "wall_span_label": format_duration(span_s),
                "active_duration_s": p_act_s,
                "active_duration_label": format_duration(p_act_s),
                "tokens_total": p_tok_total,
                "tokens_fresh": p_tok_fresh,
                "tokens_output": p_tok_out,
                "token_share_pct": round((p_tok_total / total_tok) * 100.0, 1),
            }
        )

    # Model rollups
    model_map: Dict[str, Dict[str, Any]] = {}
    for w in workers:
        m = w["model"] or "unknown"
        rec = model_map.setdefault(
            m,
            {"model": m, "input": 0, "output": 0, "cache_read": 0, "total": 0, "active_s": 0.0, "workers": []},
        )
        rec["input"] += w["tokens"]["input"]
        rec["output"] += w["tokens"]["output"]
        rec["cache_read"] += w["tokens"]["cache_read"]
        rec["total"] += w["tokens"]["total"]
        rec["active_s"] = round(rec["active_s"] + w["active_duration_s"], 1)
        rec["workers"].append(w["role"])
    model_rollups = sorted(model_map.values(), key=lambda x: -x["total"])

    # Tools & skills inventory (Declared in Script vs Observed at Runtime)
    observed_tools: Dict[str, int] = {}
    observed_skills: Set[str] = set()
    for w in workers:
        for tb in w["tool_breakdown"]:
            observed_tools[tb["name"]] = observed_tools.get(tb["name"], 0) + tb["count"]
        for sk in w["skills_loaded"]:
            observed_skills.add(sk)

    script_tools: Dict[str, int] = {}
    for st_tool in blueprint.get("tools") or []:
        tname = st_tool["name"]
        script_tools[tname] = script_tools.get(tname, 0) + 1

    inventory = {
        "skills_declared": blueprint.get("skills_declared") or [],
        "skills_observed": sorted(observed_skills),
        "script_tools": [{"name": k, "count": v} for k, v in sorted(script_tools.items(), key=lambda kv: (-kv[1], kv[0]))],
        "agent_tools": [{"name": k, "count": v} for k, v in sorted(observed_tools.items(), key=lambda kv: (-kv[1], kv[0]))],
    }

    # Insights
    insights: List[Dict[str, Any]] = []
    if workers:
        top_tok = max(workers, key=lambda w: w["tokens"]["total"])
        share = round((top_tok["tokens"]["total"] / total_tok) * 100.0, 1)
        insights.append(
            {
                "kind": "tokens",
                "title": f"Top Token Consumer: {top_tok['role']}",
                "detail": f"{top_tok['tokens']['total']:,} tokens ({share}% of workflow total, {top_tok['tokens']['cache_hit_pct']}% cache hit) on {top_tok['model']}.",
            }
        )
        slowest = max(workers, key=lambda w: w["active_duration_s"])
        insights.append(
            {
                "kind": "timing",
                "title": f"Longest Worker: {slowest['role']} ({slowest['active_duration_label']})",
                "detail": f"Peak worker concurrency {summary['peak_worker_concurrency']} with {summary['parallelism_speedup']}x speedup across {len(workers)} worker(s).",
            }
        )
    if verification["verdict"] != "VERIFIED":
        insights.append(
            {
                "kind": "warning",
                "title": f"Verification Gate: {verification['verdict_label']}",
                "detail": (
                    f"{verification['passed_count']} passed, {verification['unresolved_failure_count']} unresolved failure(s)."
                ),
            }
        )
    else:
        insights.append(
            {
                "kind": "ok",
                "title": "Verification Passed",
                "detail": f"{verification['passed_count']} check(s) passed with 0 unresolved failures ({', '.join(verification['verifier_names'])}).",
            }
        )
    for w in (blueprint.get("warnings") or [])[:2]:
        insights.append(
            {
                "kind": "warning" if w["severity"] in ("warning", "error") else "overhead",
                "title": f"Script Check (line {w['line']})",
                "detail": w["message"],
            }
        )

    return phase_rollups, model_rollups, inventory, insights


def parse_workflow_run(
    agy_dir: str,
    conv_id: str,
    workspace_root: str,
    run_index: int = -1,
    include_git: bool = True,
) -> Dict[str, Any]:
    """Build complete post-run (or in-progress) workflow telemetry + static script blueprint."""
    db_rows = _load_db_rows(agy_dir)
    steps, parent_transcript_path = _read_transcript(agy_dir, conv_id)
    invocations = _extract_workflow_invocations(agy_dir, conv_id, steps)
    if not invocations:
        raise ValueError(f"Conversation '{conv_id}' has no run_workflow invocations.")

    if run_index < 0:
        inv = invocations[-1]
    else:
        idx = max(0, min(len(invocations) - 1, run_index - 1))
        inv = invocations[idx]

    blueprint = analyze_workflow_script(inv["script_source"], script_path=inv["script_path"] or None)
    parsed_log = inv["parsed_log"]

    # Deduplicate stateful multi-turn agents sharing one UUID
    worker_order: List[str] = []
    worker_meta_map: Dict[str, Dict[str, Any]] = {}
    for ar in parsed_log["agent_runs"]:
        wcid = ar["conv_id"]
        if wcid not in worker_meta_map:
            worker_order.append(wcid)
            worker_meta_map[wcid] = {
                "conv_id": wcid,
                "role": ar["role"],
                "type_name": ar["type_name"],
                "phase": ar["phase"],
                "phases": [ar["phase"]],
                "status": ar["status"],
                "latest_preview": ar["preview"],
                "turn_entries": [ar],
            }
        else:
            meta = worker_meta_map[wcid]
            meta["status"] = ar["status"]
            if ar["preview"]:
                meta["latest_preview"] = ar["preview"]
            if ar["phase"] not in meta["phases"]:
                meta["phases"].append(ar["phase"])
            meta["turn_entries"].append(ar)

    workers = [
        _parse_worker_transcript(agy_dir, worker_meta_map[wcid], workspace_root, db_rows.get(wcid))
        for wcid in worker_order
    ]

    conc = compute_worker_concurrency(workers)
    worker_starts = [w["wall_start_ms"] for w in workers if w["wall_start_ms"] is not None]
    worker_ends = [w["wall_end_ms"] for w in workers if w["wall_end_ms"] is not None]
    wall_start_ms = min([x for x in [inv["start_ms"], *worker_starts] if x is not None], default=None)
    wall_end_ms = max([x for x in [inv["end_ms"], *worker_ends] if x is not None], default=None)
    wall_span_s = round(max(0.0, (wall_end_ms - wall_start_ms) / 1000.0), 1) if (wall_start_ms and wall_end_ms) else conc["merged_active_s"]

    tok_in = sum(w["tokens"]["input"] for w in workers)
    tok_out = sum(w["tokens"]["output"] for w in workers)
    tok_cache = sum(w["tokens"]["cache_read"] for w in workers)
    tok_fresh = tok_in + tok_out
    tok_total = tok_fresh + tok_cache
    cache_hit_pct = round((tok_cache / (tok_in + tok_cache)) * 100.0, 1) if (tok_in + tok_cache) > 0 else 0.0

    unique_files = sorted({d["name"] for w in workers for d in w["docs"]})
    models_used = sorted({w["model"] for w in workers if w["model"] and w["model"] != "unknown"})
    done_workers = sum(1 for w in workers if w["status"] == "done")
    failed_workers = sum(1 for w in workers if w["status"] not in ("done", "running"))

    outcome_map = {
        "completed": ("completed", "Completed"),
        "failed": ("failed", "Failed"),
        "running": ("running", "In Progress"),
    }
    outcome, outcome_label = outcome_map.get(inv["status"], ("completed", "Completed"))

    summary = {
        "mode": "post_run" if inv["status"] != "running" else "in_progress",
        "mode_label": "Post-Run Audit" if inv["status"] != "running" else "In-Progress Run",
        "outcome": outcome,
        "outcome_label": outcome_label,
        "invocation_index": inv["invocation_index"],
        "invocation_total": len(invocations),
        "wall_start_local": format_clock_local(wall_start_ms, include_date=True),
        "wall_end_local": format_clock_local(wall_end_ms),
        "wall_span_s": wall_span_s,
        "wall_span_label": format_duration(wall_span_s),
        "merged_active_s": conc["merged_active_s"],
        "merged_active_label": format_duration(conc["merged_active_s"]),
        "cumulative_worker_s": conc["cumulative_worker_s"],
        "cumulative_worker_label": format_duration(conc["cumulative_worker_s"]),
        "parallelism_speedup": conc["parallelism_speedup"],
        "peak_worker_concurrency": conc["peak_concurrency"],
        "worker_count": len(workers),
        "done_workers": done_workers,
        "failed_workers": failed_workers,
        "total_turns": sum(len(w["turns"]) for w in workers),
        "total_steps": sum(w["step_count"] for w in workers),
        "total_tool_calls": sum(w["tool_call_count"] for w in workers),
        "unique_file_count": len(unique_files),
        "models_used": models_used,
        "tokens": {
            "input": tok_in,
            "output": tok_out,
            "cache_read": tok_cache,
            "fresh": tok_fresh,
            "total": tok_total,
            "cache_hit_pct": cache_hit_pct,
        },
    }

    verification = _build_verification_audit(workers)
    phase_rollups, model_rollups, inventory, insights = _build_rollups_and_insights(
        workers, parsed_log["phase_order"], blueprint, summary, verification
    )
    gantt = build_gantt_model(workers, wall_start_ms, wall_end_ms)
    git_snapshot = _capture_git_snapshot(workspace_root) if include_git else {"available": False}

    return {
        "source": "agy_run_workflow",
        "mode": summary["mode"],
        "run_title": inv["description"],
        "root_conversation_id": conv_id,
        "parent_transcript_uri": f"file://{parent_transcript_path}" if parent_transcript_path else "",
        "workspace_root": workspace_root,
        "tz_label": local_tz_label(),
        "workflow": {
            "step_index": inv["step_index"],
            "task_id": inv["task_id"],
            "task_log_uri": f"file://{inv['task_log_path']}" if inv["task_log_path"] else parsed_log["log_uri"],
            "script_path": inv["script_path"],
            "script_source": inv["script_source"],
            "args": inv["args"],
            "cwd": inv["cwd"],
            "output": parsed_log["output"],
            "error_text": inv["error_text"],
            "log_entries": parsed_log["entries"],
        },
        "blueprint": blueprint,
        "summary": summary,
        "verification": verification,
        "insights": insights,
        "phase_rollups": phase_rollups,
        "model_rollups": model_rollups,
        "inventory": inventory,
        "gantt": gantt,
        "workers": workers,
        "unique_files": unique_files,
        "git_snapshot": git_snapshot,
    }


def parse_script_only(
    script_path: str,
    workspace_root: str,
    args_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Pre-Run Static Blueprint report directly from a Python workflow script."""
    abs_path = os.path.abspath(os.path.expanduser(script_path))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Workflow script not found: {abs_path}")
    with open(abs_path, encoding="utf-8", errors="replace") as f:
        source = f.read()

    manifest = load_workflow_manifest(abs_path)
    blueprint = analyze_workflow_script(source, script_path=abs_path, manifest=manifest)
    title = (manifest or {}).get("description") or (manifest or {}).get("name") or os.path.basename(abs_path)

    script_tools: Dict[str, int] = {}
    for st_tool in blueprint.get("tools") or []:
        tname = st_tool["name"]
        script_tools[tname] = script_tools.get(tname, 0) + 1

    insights: List[Dict[str, Any]] = [
        {
            "kind": "overhead",
            "title": "Pre-Run Static Inspection",
            "detail": (
                f"Analyzed {blueprint['line_count']} lines across {blueprint['counts']['phases']} phase(s), "
                f"{blueprint['counts']['agents']} agent definition(s), {blueprint['counts']['parallel_blocks']} parallel fan-out(s), "
                f"and {blueprint['counts']['pipeline_blocks']} pipeline(s)."
            ),
        }
    ]
    for w in blueprint.get("warnings") or []:
        insights.append(
            {
                "kind": "warning" if w["severity"] in ("warning", "error") else "overhead",
                "title": f"Pre-Flight ({w['code']}, line {w['line']})",
                "detail": w["message"],
            }
        )

    return {
        "source": "script_blueprint",
        "mode": "blueprint",
        "run_title": title,
        "root_conversation_id": "pre-run-blueprint",
        "parent_transcript_uri": "",
        "workspace_root": workspace_root,
        "tz_label": local_tz_label(),
        "workflow": {
            "step_index": None,
            "task_id": "",
            "task_log_uri": "",
            "script_path": abs_path,
            "script_source": source,
            "args": args_override or {},
            "cwd": workspace_root,
            "output": "",
            "error_text": blueprint.get("parse_error") or "",
            "log_entries": [],
        },
        "blueprint": blueprint,
        "summary": {
            "mode": "blueprint",
            "mode_label": "Pre-Run Script Blueprint",
            "outcome": "blueprint",
            "outcome_label": "Pre-Run Blueprint",
            "invocation_index": 0,
            "invocation_total": 0,
            "wall_start_local": "Not yet executed",
            "wall_end_local": "—",
            "wall_span_s": 0.0,
            "wall_span_label": "—",
            "merged_active_s": 0.0,
            "merged_active_label": "—",
            "cumulative_worker_s": 0.0,
            "cumulative_worker_label": "—",
            "parallelism_speedup": 1.0,
            "peak_worker_concurrency": 0,
            "worker_count": 0,
            "done_workers": 0,
            "failed_workers": 0,
            "total_turns": 0,
            "total_steps": 0,
            "total_tool_calls": 0,
            "unique_file_count": 0,
            "models_used": sorted({a["model"] for a in blueprint["agents"] if a.get("model")}),
            "tokens": {"input": 0, "output": 0, "cache_read": 0, "fresh": 0, "total": 0, "cache_hit_pct": 0.0},
        },
        "verification": {
            "verdict": "PRE_RUN",
            "verdict_label": "Pre-Run (not yet executed)",
            "has_verifier": any(_VERIFIER_NAME_RE.search(f"{a['role']} {a['type_name']}") for a in blueprint["agents"]),
            "verifier_names": [
                a["role"] for a in blueprint["agents"] if _VERIFIER_NAME_RE.search(f"{a['role']} {a['type_name']}")
            ],
            "ordered_after_edits": True,
            "last_author_edit_local": "—",
            "verifier_last_local": "—",
            "passed_count": 0,
            "failed_count": 0,
            "unresolved_failure_count": 0,
            "resolved_earlier_failure_count": 0,
            "structured_verdicts": [],
            "verifier_commands": [],
            "author_check_commands": [],
            "latest_verifier_report": "",
        },
        "insights": insights,
        "phase_rollups": [],
        "model_rollups": [],
        "inventory": {
            "skills_declared": blueprint.get("skills_declared") or [],
            "skills_observed": [],
            "script_tools": [{"name": k, "count": v} for k, v in sorted(script_tools.items(), key=lambda kv: (-kv[1], kv[0]))],
            "agent_tools": [],
        },
        "gantt": {"wall_start_local": "—", "wall_end_local": "—", "has_compressed_gaps": False, "clusters": [], "rows": []},
        "workers": [],
        "unique_files": [],
        "git_snapshot": {"available": False},
    }
