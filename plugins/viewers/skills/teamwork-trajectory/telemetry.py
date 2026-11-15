#!/usr/bin/env python3
"""Telemetry discovery and parsing for AGY live runs and legacy .agents/ directories."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urlparse

from timeline import (
    HANDOFF_OVERLAP_TOLERANCE_S,
    compute_gantt_layout,
    compute_peak_concurrency,
    compute_worker_concurrency,
    format_duration,
    format_local_clock,
    get_local_tz_label,
    merge_intervals,
    parse_iso_timestamp,
    segment_active_turns,
    total_merged_duration,
)


WRITE_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}

LEGACY_AGENT_PLACEHOLDERS = {"orchestrator", "sentinel", "victory_auditor"}

BOOST_AGENT_NAMES = {
    "DeepCoder",
    "DeepInvestigator",
    "DeepCoderWorkerL0",
    "DeepCoderImprovementWorker",
    "DeepInvestigatorWorkerL0",
    "DeepInvestigatorImprovementWorker",
}


def resolve_workspace_root(start_dir: Optional[str] = None) -> str:
    """Resolve the project workspace root starting from start_dir (default cwd)."""
    start = os.path.abspath(start_dir or os.getcwd())
    cur = start
    while cur and cur != os.path.dirname(cur):
        for marker in (".git", ".agents", "plans"):
            if os.path.exists(os.path.join(cur, marker)):
                return cur
        cur = os.path.dirname(cur)
    return start


def resolve_agy_dir(explicit_dir: Optional[str] = None) -> str:
    """Resolve the AGY CLI data directory."""
    if explicit_dir:
        return os.path.abspath(os.path.expanduser(explicit_dir))
    env_dir = os.environ.get("AGY_DATA_DIR")
    if env_dir:
        return os.path.abspath(os.path.expanduser(env_dir))
    return os.path.expanduser("~/.gemini/antigravity-cli")


def decode_file_uri(uri: str) -> str:
    """Convert a file:// URI to a normalized filesystem path."""
    if not uri:
        return ""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        return os.path.normpath(unquote(parsed.path))
    return os.path.normpath(uri)


def _match_workspace_score(workspace_uris_json: str, workspace_root: str) -> int:
    """Score how closely a conversation's workspace_uris matches workspace_root.

    Returns 3 for exact match, 2 for workspace_root inside URI, 1 for URI inside workspace_root, 0 otherwise.
    """
    target = os.path.normpath(os.path.abspath(workspace_root))
    try:
        uris = json.loads(workspace_uris_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return 0
    best = 0
    for uri in uris:
        path = decode_file_uri(str(uri))
        if not path:
            continue
        if path == target:
            return 3
        if target.startswith(path + os.sep):
            best = max(best, 2)
        elif path.startswith(target + os.sep):
            best = max(best, 1)
    return best


def _open_db_readonly(db_path: str) -> Optional[sqlite3.Connection]:
    """Open conversation_summaries.db in read-only mode if present."""
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error:
            return None


def _load_db_metadata(agy_dir: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """Load all rows and parent->children map from conversation_summaries.db."""
    db_path = os.path.join(agy_dir, "conversation_summaries.db")
    conn = _open_db_readonly(db_path)
    by_id: Dict[str, Dict[str, Any]] = {}
    children_by_parent: Dict[str, List[str]] = {}
    if conn is None:
        return by_id, children_by_parent
    try:
        rows = conn.execute(
            """
            SELECT conversation_id, title, agent_name, parent_conversation_id,
                   nesting_depth, step_count, last_modified_time, workspace_uris, status, killed
            FROM conversation_summaries
            ORDER BY last_modified_time DESC
            """
        ).fetchall()
        for row in rows:
            cid = row["conversation_id"]
            pid = row["parent_conversation_id"] or ""
            by_id[cid] = {
                "conversation_id": cid,
                "title": row["title"] or "",
                "agent_name": row["agent_name"] or "",
                "parent_id": pid,
                "depth": int(row["nesting_depth"] or 0),
                "db_step_count": int(row["step_count"] or 0),
                "last_modified_time": row["last_modified_time"] or "",
                "workspace_uris": row["workspace_uris"] or "[]",
                "status": row["status"] or "",
                "killed": bool(row["killed"]),
            }
            if pid:
                children_by_parent.setdefault(pid, []).append(cid)
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return by_id, children_by_parent


def _collect_descendants(children_map: Dict[str, List[str]], root_id: str) -> List[str]:
    descendants: List[str] = []
    stack = list(children_map.get(root_id, []))
    seen: Set[str] = {root_id}
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        descendants.append(cid)
        stack.extend(children_map.get(cid, []))
    return descendants


def _is_boost_only_run(
    agy_dir: str,
    root_id: str,
    by_id: Dict[str, Dict[str, Any]],
    children_map: Dict[str, List[str]],
    descendants: Sequence[str],
) -> bool:
    """Return True if a root conversation is a /boost-only run (deprioritized behind swarm runs)."""
    if descendants:
        names = [(by_id.get(d) or {}).get("agent_name") or "" for d in descendants]
        non_empty = [n for n in names if n]
        if non_empty:
            return all(n in BOOST_AGENT_NAMES for n in non_empty)
    steps, _ = _read_transcript(agy_dir, root_id)
    if not steps:
        return False
    spawns = _extract_subagent_spawns(steps)
    if spawns:
        types = [meta.get("requested_type") or "" for meta in spawns.values() if meta.get("requested_type")]
        if types:
            return all(t in BOOST_AGENT_NAMES for t in types)
    for st in steps:
        if st.get("type") == "USER_INPUT":
            content = str(st.get("content") or "")
            if "<ORCHESTRATOR>" in content:
                return True
            m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
            user_req = m.group(1) if m else content
            if re.match(r"^\s*/boost(?=$|\s|/boost)", user_req, re.IGNORECASE):
                return True
    return False


def list_agy_runs(agy_dir: str, workspace_root: str) -> List[Dict[str, Any]]:
    """Return root AGY conversations matching workspace_root, newest first."""
    by_id, children_map = _load_db_metadata(agy_dir)
    if not by_id:
        return []

    runs: List[Dict[str, Any]] = []
    for cid, row in by_id.items():
        if row["parent_id"]:
            continue
        score = _match_workspace_score(row["workspace_uris"], workspace_root)
        if score == 0:
            continue
        descendants = _collect_descendants(children_map, cid)
        subagent_count = len(descendants)
        step_count = int(row["db_step_count"] or 0)
        if step_count == 0 and subagent_count == 0:
            continue
        is_boost_only = _is_boost_only_run(agy_dir, cid, by_id, children_map, descendants)
        runs.append({
            "conversation_id": cid,
            "title": row["title"] or "(untitled)",
            "agent_name": row["agent_name"] or "root",
            "step_count": step_count,
            "last_modified_time": row["last_modified_time"] or "",
            "status": row["status"] or "",
            "subagent_count": subagent_count,
            "is_boost_only": is_boost_only,
            "match_score": score,
        })

    exact_or_child = [r for r in runs if r["match_score"] in (3, 1)]
    if exact_or_child:
        runs = exact_or_child

    runs.sort(key=lambda r: (r["match_score"], r["last_modified_time"]), reverse=True)
    return runs


def _resolve_root_conversation(
    agy_dir: str,
    cid: str,
    by_id: Dict[str, Dict[str, Any]],
) -> str:
    """Walk parent_conversation_id / dispatch sender pointers upward to the root conversation."""
    cur = cid
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = by_id.get(cur)
        parent = (row or {}).get("parent_id") or ""
        if not parent:
            steps, _ = _read_transcript(agy_dir, cur)
            _, sender_id, _ = _parse_step0_header(steps)
            if (
                sender_id
                and sender_id not in seen
                and (sender_id in by_id or os.path.isdir(os.path.join(agy_dir, "brain", sender_id)))
            ):
                parent = sender_id
        if not parent:
            break
        cur = parent
    return cur


def select_agy_run(
    agy_dir: str,
    workspace_root: str,
    conversation_id: Optional[str] = None,
) -> Optional[str]:
    """Select the target root conversation ID from AGY telemetry.

    Deprioritizes /boost-only runs behind non-/boost multi-agent swarm runs,
    while preserving /boost runs as a fallback or when explicitly targeted via -c.
    """
    if conversation_id:
        prefix = conversation_id.strip()
        by_id, _ = _load_db_metadata(agy_dir)
        brain_dir = os.path.join(agy_dir, "brain")
        matched: Optional[str] = None
        if prefix in by_id or os.path.isdir(os.path.join(brain_dir, prefix)):
            matched = prefix
        else:
            db_path = os.path.join(agy_dir, "conversation_summaries.db")
            conn = _open_db_readonly(db_path)
            if conn is not None:
                try:
                    matches = conn.execute(
                        """
                        SELECT conversation_id, nesting_depth, last_modified_time
                        FROM conversation_summaries
                        WHERE substr(conversation_id, 1, length(?)) = ?
                        ORDER BY nesting_depth ASC, last_modified_time DESC
                        """,
                        (prefix, prefix),
                    ).fetchall()
                    if matches:
                        matched = matches[0]["conversation_id"]
                finally:
                    conn.close()
            if not matched and os.path.isdir(brain_dir):
                dir_matches = sorted(d for d in os.listdir(brain_dir) if d.startswith(prefix))
                if len(dir_matches) == 1:
                    matched = dir_matches[0]
        if matched:
            return _resolve_root_conversation(agy_dir, matched, by_id)
        return None

    runs = list_agy_runs(agy_dir, workspace_root)
    non_boost_multi = [r for r in runs if r["subagent_count"] > 0 and not r.get("is_boost_only")]
    if non_boost_multi:
        return non_boost_multi[0]["conversation_id"]
    multi_agent = [r for r in runs if r["subagent_count"] > 0]
    if multi_agent:
        return multi_agent[0]["conversation_id"]
    non_boost = [r for r in runs if not r.get("is_boost_only")]
    if non_boost:
        return non_boost[0]["conversation_id"]
    if runs:
        return runs[0]["conversation_id"]
    return None


def _read_transcript(agy_dir: str, conv_id: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Read transcript_full.jsonl (preferred) or transcript.jsonl for a conversation."""
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    for fname in ("transcript_full.jsonl", "transcript.jsonl"):
        fpath = os.path.join(logs_dir, fname)
        if os.path.exists(fpath):
            steps: List[Dict[str, Any]] = []
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        steps.append(json.loads(raw))
                    except json.JSONDecodeError:
                        continue
            return steps, fpath
    return [], None


def _extract_user_request_text(content: str) -> str:
    """Extract readable user request text from a USER_INPUT step, stripping XML wrappers."""
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
    text = m.group(1) if m else content
    text = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ORCHESTRATOR>.*?</ORCHESTRATOR>", "", text, flags=re.DOTALL)
    text = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()


def _parse_step0_header(steps: Sequence[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[str], str]:
    """Extract spawn timestamp, parent sender ID, and initial prompt from early steps.

    Skips SYSTEM_SDK periodic reminders and sender=system [Notice] steps, and
    strips XML wrappers from USER_INPUT root prompts.
    """
    if not steps:
        return None, None, ""

    first = steps[0]
    if first.get("type") == "USER_INPUT":
        return (
            parse_iso_timestamp(first.get("created_at")),
            None,
            _extract_user_request_text(str(first.get("content") or "")),
        )

    for step in steps[:6]:
        if step.get("type") == "USER_INPUT":
            return (
                parse_iso_timestamp(step.get("created_at")),
                None,
                _extract_user_request_text(str(step.get("content") or "")),
            )
        if step.get("type") == "SYSTEM_MESSAGE" and step.get("source") == "SYSTEM_SDK":
            continue
        if step.get("type") not in (None, "SYSTEM_MESSAGE"):
            continue
        content = str(step.get("content") or "")
        header = content.split("content=", 1)[0]
        sender_match = re.search(r"\bsender=([^\s]+)", header)
        sender_id = sender_match.group(1).strip() if sender_match else None
        if sender_id and sender_id.lower() == "system":
            continue
        if "[Notice]" in header and not sender_id:
            continue
        if "sender=" in content or "[Message]" in content:
            ts_match = re.search(r"timestamp=([^\s]+)", content)
            if not sender_id:
                sender_match = re.search(r"\bsender=([^\s]+)", content)
                sender_id = sender_match.group(1).strip() if sender_match else None
                if sender_id and sender_id.lower() == "system":
                    continue
            msg_match = re.search(r"content=(.*)", content, re.DOTALL)
            spawn_dt = (
                parse_iso_timestamp(ts_match.group(1))
                if ts_match
                else parse_iso_timestamp(step.get("created_at"))
            )
            prompt = ""
            if msg_match:
                prompt = msg_match.group(1).strip()
                if prompt.endswith("</SYSTEM_MESSAGE>"):
                    prompt = prompt[: -len("</SYSTEM_MESSAGE>")].strip()
            return spawn_dt, sender_id, prompt

    return parse_iso_timestamp(first.get("created_at")), None, ""


def _extract_json_objects_with_key(content: str, key: str) -> List[Dict[str, Any]]:
    """Extract JSON dicts containing `key` from mixed text, supporting nested braces."""
    results: List[Dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    length = len(content)
    while idx < length:
        brace = content.find("{", idx)
        if brace == -1:
            break
        try:
            obj, end = decoder.raw_decode(content, brace)
        except json.JSONDecodeError:
            idx = brace + 1
            continue
        if isinstance(obj, dict) and key in obj:
            results.append(obj)
        idx = max(end, brace + 1)
    return results


def _extract_subagent_spawns(steps: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Parse invoke_subagent calls and Created subagent JSON blocks from parent steps."""
    spawns: Dict[str, Dict[str, Any]] = {}
    pending_calls: List[Dict[str, Any]] = []

    for list_idx, step in enumerate(steps):
        step_type = step.get("type")
        step_idx = step.get("step_index")
        step_ts = parse_iso_timestamp(step.get("created_at"))
        if step_type == "USER_INPUT":
            pending_calls.clear()

        tcs = step.get("tool_calls") or []
        if any(tc.get("name") == "invoke_subagent" for tc in tcs) and pending_calls:
            pending_calls.clear()

        for tc in tcs:
            if tc.get("name") != "invoke_subagent":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            subagents_batch = args.get("Subagents")
            if isinstance(subagents_batch, str):
                try:
                    subagents_batch = ast.literal_eval(subagents_batch)
                except (ValueError, SyntaxError):
                    subagents_batch = None
            if isinstance(subagents_batch, list):
                for entry in subagents_batch:
                    if isinstance(entry, dict):
                        pending_calls.append({
                            "spawn_step_index": step_idx,
                            "spawn_list_index": list_idx,
                            "spawn_call_ts": step_ts,
                            "requested_type": _clean_arg_str(entry.get("TypeName")),
                            "requested_role": _clean_arg_str(entry.get("Role")),
                            "requested_model": _clean_arg_str(entry.get("Model")),
                            "workspace_mode": _clean_arg_str(entry.get("Workspace")),
                            "prompt": _clean_arg_str(entry.get("Prompt")),
                        })
            else:
                pending_calls.append({
                    "spawn_step_index": step_idx,
                    "spawn_list_index": list_idx,
                    "spawn_call_ts": step_ts,
                    "requested_type": _clean_arg_str(args.get("TypeName")),
                    "requested_role": _clean_arg_str(args.get("Role")),
                    "requested_model": _clean_arg_str(args.get("Model")),
                    "workspace_mode": _clean_arg_str(args.get("Workspace")),
                    "prompt": _clean_arg_str(args.get("Prompt")),
                })

        if step_type == "GENERIC":
            content = str(step.get("content") or "")
            if pending_calls and "Created the following subagent" in content:
                for info in _extract_json_objects_with_key(content, "conversationId"):
                    if not pending_calls:
                        break
                    cid = info.get("conversationId")
                    if not cid:
                        continue
                    call_meta = pending_calls.pop(0)
                    if cid not in spawns:
                        spawns[cid] = {
                            **call_meta,
                            "log_uri": info.get("logAbsoluteUri") or "",
                            "spawn_completed_ts": step_ts,
                        }
            elif pending_calls and any(
                tok in content.lower() for tok in ("encountered error", "failed", "error", "rejected")
            ):
                pending_calls.clear()
    return spawns


def _clean_arg_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s[1:-1]
    return s


def _extract_settings_model_changes(steps: Sequence[Dict[str, Any]]) -> List[Tuple[int, str]]:
    """Extract (list_index, model_name) entries from USER_INPUT <USER_SETTINGS_CHANGE> blocks."""
    changes: List[Tuple[int, str]] = []
    for idx, step in enumerate(steps):
        if step.get("type") != "USER_INPUT":
            continue
        content = str(step.get("content") or "")
        if "<USER_SETTINGS_CHANGE>" not in content:
            continue
        for block in re.findall(r"<USER_SETTINGS_CHANGE>(.*?)</USER_SETTINGS_CHANGE>", content, re.DOTALL):
            m = re.search(
                r"Model Selection`?\s+from\s+.+?\s+to\s+(.+?)(?=\.(?:\s|$|<)|[\n<]|$)",
                block,
                re.IGNORECASE,
            )
            if m:
                changes.append((idx, m.group(1).strip()))
    return changes


def _settings_model_at(
    steps: Sequence[Dict[str, Any]],
    spawn_list_index: Optional[int] = None,
    spawn_step_index: Optional[Any] = None,
) -> str:
    """Return the settings model active at a parent step position."""
    changes = _extract_settings_model_changes(steps)
    if not changes:
        return ""
    pos: Optional[int] = spawn_list_index
    if pos is None and spawn_step_index is not None:
        for idx, st in enumerate(steps):
            if st.get("step_index") == spawn_step_index:
                pos = idx
                break
    if pos is None:
        pos = len(steps) - 1
    chosen = ""
    for idx, model_name in changes:
        if idx <= pos:
            chosen = model_name
    return chosen


def _resolve_model(
    steps: Sequence[Dict[str, Any]],
    requested_model: str,
    inherited_model: str,
    inherited_source: str,
    settings_at_spawn: str,
    fallback_settings_model: str,
) -> Tuple[str, str]:
    """Return (resolved_model, model_source) using PLANNER_RESPONSE, settings, and inheritance."""
    seen_models: List[str] = []
    for step in steps:
        if step.get("type") != "PLANNER_RESPONSE":
            continue
        m = step.get("model")
        if m and isinstance(m, str) and m not in seen_models:
            seen_models.append(m)
    if seen_models:
        return ", ".join(seen_models), "planner_response"
    req = (requested_model or "").strip()
    if req and req.lower() not in ("inherit", "default", "none"):
        return req, "requested"
    if inherited_source == "planner_response" and inherited_model and inherited_model.lower() not in ("inherit", "default", "unknown"):
        return inherited_model, "inherited"
    if settings_at_spawn:
        return settings_at_spawn, "user_settings"
    if inherited_model and inherited_model.lower() not in ("inherit", "default", "unknown"):
        return inherited_model, "inherited"
    if fallback_settings_model:
        return fallback_settings_model, "user_settings"
    return req or "default", "fallback"


def _is_failed_tool_result(content: str) -> bool:
    """Return True if a GENERIC tool output indicates an error / failed tool call."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    body_lines = [
        ln for ln in lines
        if not ln.startswith("Created At:") and not ln.startswith("Completed At:")
    ]
    body = "\n".join(body_lines).strip().lower()
    if not body:
        return False
    return (
        body.startswith("error")
        or body.startswith("encountered error")
        or body.startswith("failed")
        or body.startswith("rejected")
        or "error invalid tool call" in body
        or "encountered error in step execution" in body
    )


def _extract_produced_docs(steps: Sequence[Dict[str, Any]], workspace_root: str) -> List[Dict[str, str]]:
    """Extract created or edited file paths from successful transcript write tool calls."""
    seen: Set[str] = set()
    docs: List[Dict[str, str]] = []
    ws_norm = os.path.normpath(os.path.abspath(workspace_root))
    n_steps = len(steps)

    for idx, step in enumerate(steps):
        tcs = step.get("tool_calls") or []
        write_entries: List[Tuple[int, str, str]] = []
        for tc_idx, tc in enumerate(tcs):
            tname = tc.get("name") or ""
            if tname not in WRITE_TOOL_NAMES:
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            raw_path = _clean_arg_str(args.get("Path") or args.get("TargetFile") or "")
            if not raw_path:
                continue
            abs_path = os.path.normpath(raw_path if os.path.isabs(raw_path) else os.path.join(ws_norm, raw_path))
            write_entries.append((tc_idx, raw_path, abs_path))

        if not write_entries:
            continue

        generic_results: List[str] = []
        j = idx + 1
        while j < n_steps and steps[j].get("type") == "GENERIC":
            generic_results.append(str(steps[j].get("content") or ""))
            j += 1

        all_failed = bool(generic_results) and all(_is_failed_tool_result(g) for g in generic_results)

        for tc_idx, raw_path, abs_path in write_entries:
            if generic_results:
                if len(tcs) == 1 and _is_failed_tool_result(generic_results[0]):
                    continue
                if all_failed:
                    continue
                matched_failed = any(
                    _is_failed_tool_result(g) and (abs_path in g or raw_path in g)
                    for g in generic_results
                )
                if matched_failed:
                    continue
                if len(generic_results) == len(tcs) and _is_failed_tool_result(generic_results[tc_idx]):
                    continue

            if abs_path in seen:
                continue
            seen.add(abs_path)
            if abs_path.startswith(ws_norm + os.sep):
                rel = os.path.relpath(abs_path, ws_norm)
            else:
                rel = abs_path
            docs.append({
                "name": rel,
                "path": f"file://{abs_path}",
            })
    return docs


def _clean_summary_text(txt: str) -> str:
    prose_only = re.sub(r"```[\s\S]*?```", "", txt)
    prose_cleaned = re.sub(r"(?m)^>\s*", "", prose_only)
    prose_cleaned = re.sub(r"[#*`]+", "", prose_cleaned)
    prose_cleaned = re.sub(r"\s+", " ", prose_cleaned).strip()
    if len(prose_cleaned) >= 30:
        cleaned = re.sub(r"```[\s\S]*?```", "[code/json output]", txt)
    else:
        cleaned = re.sub(r"```[a-zA-Z0-9_-]*\s*", "", txt)
        cleaned = cleaned.replace("```", "")
    cleaned = re.sub(r"(?m)^>\s*", "", cleaned)
    cleaned = re.sub(r"[#*`]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 280:
        return cleaned[:277].rstrip() + "..."
    return cleaned


def _extract_summary(steps: Sequence[Dict[str, Any]], status: str) -> str:
    """Extract a readable summary from the last meaningful PLANNER_RESPONSE or send_message."""
    for step in reversed(steps):
        if step.get("type") == "PLANNER_RESPONSE":
            txt = str(step.get("content") or "").strip()
            if txt:
                cleaned = _clean_summary_text(txt)
                if cleaned:
                    return cleaned
    for step in reversed(steps):
        for tc in reversed(step.get("tool_calls") or []):
            if tc.get("name") != "send_message":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            msg = _clean_arg_str(args.get("Message"))
            if msg:
                cleaned = _clean_summary_text(msg)
                if cleaned:
                    return cleaned
    if status in ("running", "killed"):
        return f"Interrupted / {status} before recording a final summary."
    return f"Completed ({status})." if status else "No planner summary recorded."


def _infer_phase(
    agent_name: str,
    role: str,
    prompt: str,
    docs: Sequence[Dict[str, str]],
    depth: int,
    parent_phase: str = "",
    parent_label: str = "",
) -> str:
    """Classify an AGY agent into a plan-swarm lifecycle phase."""
    if depth == 0:
        return "orchestration"

    parent_low = (parent_label or "").lower()
    if any(
        k in parent_low
        for k in (
            "spec-validator",
            "spec-deliberator",
            "plan-validator",
            "plan-deliberator",
            "implementation-validator",
            "deepcoder",
            "deepinvestigator",
        )
    ):
        if parent_phase in ("discovery", "planning", "construction", "verification"):
            return parent_phase

    label = f"{agent_name} {role}".lower()
    doc_names = " ".join(d["name"].lower() for d in docs)
    prompt_head = prompt[:600].lower()

    if any(k in label for k in ("supervisor", "starter", "orchestrator", "coordinator")):
        return "orchestration"
    if any(
        k in label
        for k in ("spec-validator", "spec-deliberator", "spec reviewer", "spec skeptic", "deepinvestigator", "boost investigator")
    ):
        return "discovery"
    if any(
        k in label
        for k in ("plan-validator", "plan-deliberator", "plan skeptic", "plan reviewer")
    ):
        return "planning"
    if any(
        k in label
        for k in ("implementation-validator", "implementation skeptic", "implementation reviewer", "visual-implementation-recap", "victory")
    ):
        return "verification"
    if any(k in label for k in ("deepcoder", "boost coder")):
        return "construction"

    if any(k in prompt_head for k in ("spec reviewer", "spec skeptic", "adversarial spec")):
        return "discovery"
    if any(k in prompt_head for k in ("plan skeptic", "plan reviewer", "adversarial plan")):
        return "planning"
    if any(k in prompt_head for k in ("implementation skeptic", "implementation reviewer")) or (
        "adversarially validate the" in prompt_head and "implementation" in prompt_head
    ):
        return "verification"

    if "auditor" in label:
        return "verification"
    if any(k in label for k in ("engineer", "simplifier", "worker_impl", "builder")):
        return "construction"
    if any(k in label for k in ("architect", "visual-architect", "planner")):
        return "planning"
    if any(k in label for k in ("product-owner", "visual-product-owner", "research")):
        return "discovery"

    # Prompt & produced-document heuristics for generic `self` / `subagent` dispatches
    if "implementation-review" in doc_names or "audit_" in doc_names:
        return "verification"
    if "plan-review" in doc_names or "plan.md" in doc_names or "implementation plan" in prompt_head:
        return "planning"
    if "spec-review" in doc_names or "spec.md" in doc_names or "plans/research/" in doc_names:
        return "discovery"
    return "construction" if docs else "discovery"


def _summarize_tool_calls(steps: Sequence[Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
    counts: Dict[str, int] = {}
    total = 0
    for step in steps:
        for tc in step.get("tool_calls") or []:
            name = tc.get("name") or "unknown"
            counts[name] = counts.get(name, 0) + 1
            total += 1
    top = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return total, top


def _compute_tokens(steps: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    in_tok = sum(int(s.get("input_tokens") or 0) for s in steps)
    cache_tok = sum(int(s.get("cache_read_tokens") or 0) for s in steps)
    out_tok = sum(int(s.get("output_tokens") or 0) for s in steps)
    return {
        "input": in_tok,
        "cache_read": cache_tok,
        "output": out_tok,
        "total": in_tok + cache_tok + out_tok,
    }


def _collect_tree_rows(agy_dir: str, root_id: str) -> Dict[str, Dict[str, Any]]:
    """Collect metadata for root_id and all descendants from DB + transcripts."""
    by_id, children_by_parent = _load_db_metadata(agy_dir)

    # BFS from root_id, also discovering children from transcript invoke_subagent results
    ordered_nodes: Dict[str, Dict[str, Any]] = {}
    queue: List[Tuple[str, str, int]] = [(root_id, "", 0)]
    seen: Set[str] = set()

    while queue:
        cid, fallback_parent, fallback_depth = queue.pop(0)
        if cid in seen:
            continue
        seen.add(cid)

        node = dict(by_id.get(cid) or {
            "conversation_id": cid,
            "title": "",
            "agent_name": "",
            "parent_id": fallback_parent,
            "depth": fallback_depth,
            "db_step_count": 0,
            "last_modified_time": "",
            "status": "",
            "killed": False,
        })
        if cid == root_id:
            node["depth"] = 0
            node["parent_id"] = ""
        else:
            if not node.get("parent_id"):
                node["parent_id"] = fallback_parent
            if node.get("depth", 0) == 0:
                node["depth"] = fallback_depth
        steps, transcript_path = _read_transcript(agy_dir, cid)
        node["steps"] = steps
        node["transcript_path"] = transcript_path
        node["spawns"] = _extract_subagent_spawns(steps)
        ordered_nodes[cid] = node

        discovered_children = list(children_by_parent.get(cid, []))
        for child_id in node["spawns"].keys():
            db_parent = (by_id.get(child_id) or {}).get("parent_id") or ""
            if db_parent and db_parent != cid:
                continue
            if child_id not in discovered_children:
                discovered_children.append(child_id)
        for child_id in discovered_children:
            queue.append((child_id, cid, node["depth"] + 1))

    return ordered_nodes


def parse_agy_run(agy_dir: str, root_id: str, workspace_root: str) -> Dict[str, Any]:
    """Parse a complete AGY multi-agent conversation tree into telemetry payload."""
    nodes = _collect_tree_rows(agy_dir, root_id)
    if root_id not in nodes or (not nodes[root_id]["steps"] and len(nodes) == 1):
        raise ValueError(f"Conversation '{root_id}' has no transcript or subagents under {agy_dir}")

    # Attach parent spawn metadata to children (protecting true parent metadata from descendant overwrites)
    for cid, node in nodes.items():
        for child_id, spawn_meta in node["spawns"].items():
            if child_id not in nodes or child_id == root_id:
                continue
            child_node = nodes[child_id]
            db_parent = child_node.get("parent_id") or ""
            if db_parent and db_parent != cid:
                continue
            if child_node["depth"] <= node["depth"]:
                continue
            if "spawn_meta" not in child_node:
                child_node["spawn_meta"] = spawn_meta

    # Resolve models top-down (root -> child -> grandchild)
    root_latest_settings = _settings_model_at(nodes[root_id]["steps"])
    resolved_models: Dict[str, Tuple[str, str]] = {}
    for depth_pass in sorted({n["depth"] for n in nodes.values()}):
        for cid, node in nodes.items():
            if node["depth"] != depth_pass:
                continue
            pid = node.get("parent_id") or ""
            parent_model, parent_source = resolved_models.get(pid, ("", "")) if pid else ("", "")
            spawn_meta = node.get("spawn_meta") or {}
            req_model = spawn_meta.get("requested_model") or ""
            parent_steps = nodes[pid]["steps"] if (pid and pid in nodes) else []
            settings_at_spawn = (
                _settings_model_at(
                    parent_steps,
                    spawn_list_index=spawn_meta.get("spawn_list_index"),
                    spawn_step_index=spawn_meta.get("spawn_step_index"),
                )
                if parent_steps
                else ""
            )
            fallback_settings = _settings_model_at(node["steps"]) if cid == root_id else (settings_at_spawn or root_latest_settings)
            resolved_models[cid] = _resolve_model(
                node["steps"],
                req_model,
                parent_model,
                parent_source,
                settings_at_spawn,
                fallback_settings,
            )

    # First build agent payloads in depth order so validator/deliberator children can inherit parent phase
    agents: List[Dict[str, Any]] = []
    phase_by_id: Dict[str, str] = {}
    label_by_id: Dict[str, str] = {}

    for depth_pass in sorted({n["depth"] for n in nodes.values()}):
        for cid, node in nodes.items():
            if node["depth"] != depth_pass:
                continue
            steps = node["steps"]
            depth = node["depth"]
            spawn_meta = node.get("spawn_meta") or {}
            step0_ts, step0_sender, step0_prompt = _parse_step0_header(steps)

            spawn_ts = spawn_meta.get("spawn_call_ts") or step0_ts
            turns = segment_active_turns(steps, spawn_ts=spawn_ts)

            wall_start_dt = parse_iso_timestamp(turns[0]["start_iso"]) if turns else spawn_ts
            wall_end_dt = parse_iso_timestamp(turns[-1]["end_iso"]) if turns else parse_iso_timestamp(node["last_modified_time"])
            wall_span_s = max(0.0, (wall_end_dt - wall_start_dt).total_seconds()) if (wall_start_dt and wall_end_dt) else 0.0
            active_duration_s = sum(t["duration_s"] for t in turns)

            tool_count, tool_breakdown = _summarize_tool_calls(steps)
            tokens = _compute_tokens(steps)
            docs = _extract_produced_docs(steps, workspace_root)
            prompt = spawn_meta.get("prompt") or step0_prompt
            if depth == 0 and not prompt:
                for st in steps:
                    if st.get("type") == "USER_INPUT":
                        prompt = _extract_user_request_text(str(st.get("content") or ""))
                        break

            role = spawn_meta.get("requested_role") or ""
            req_type = spawn_meta.get("requested_type") or node["agent_name"] or ("supervisor" if depth == 0 else "subagent")
            display_name = node["agent_name"] or req_type
            if depth == 0:
                display_name = node["title"] or "root-orchestrator"

            parent_id = "" if cid == root_id else (node["parent_id"] or step0_sender or "")
            parent_phase = phase_by_id.get(parent_id, "")
            parent_label = label_by_id.get(parent_id, "")

            phase = _infer_phase(
                node["agent_name"] or req_type,
                role,
                prompt,
                docs,
                depth,
                parent_phase=parent_phase,
                parent_label=parent_label,
            )
            phase_by_id[cid] = phase
            label_by_id[cid] = f"{display_name} {req_type} {role}".strip()

            status_raw = node["status"] or ("DONE" if steps else "UNKNOWN")
            status_clean = status_raw.replace("CASCADE_RUN_STATUS_", "").lower()
            if node["killed"]:
                status_clean = "killed"
            elif not steps and depth > 0:
                status_clean = "empty"

            summary = _extract_summary(steps, status_clean)
            task_preview = re.sub(r"\s+", " ", prompt).strip()
            if len(task_preview) > 280:
                task_preview = task_preview[:277].rstrip() + "..."

            resolved_model, model_source = resolved_models.get(cid, ("default", "fallback"))
            req_model = spawn_meta.get("requested_model") or ("default" if depth == 0 else "inherit")

            agents.append({
                "id": cid,
                "conv_id": cid,
                "parent_id": parent_id,
                "depth": depth,
                "name": display_name,
                "type": req_type,
                "role": role or req_type,
                "model": resolved_model,
                "model_source": model_source,
                "requested_model": req_model,
                "workspace_mode": spawn_meta.get("workspace_mode") or "inherit",
                "task": task_preview or "(no task prompt recorded)",
                "status": status_clean,
                "mode": "serial",
                "spawn_step_index": spawn_meta.get("spawn_step_index"),
                "roles": [role] if role else [],
                "summary": summary,
                "docs": docs,
                "phase": phase,
                "transcript_uri": f"file://{node['transcript_path']}" if node.get("transcript_path") else "",
                "step_count": max(node["db_step_count"], len(steps)),
                "tool_call_count": tool_count,
                "tool_breakdown": tool_breakdown[:8],
                "tokens": tokens,
                "turns": turns,
                "wall_start_ms": int(wall_start_dt.timestamp() * 1000) if wall_start_dt else None,
                "wall_end_ms": int(wall_end_dt.timestamp() * 1000) if wall_end_dt else None,
                "wall_start_iso": wall_start_dt.isoformat().replace("+00:00", "Z") if wall_start_dt else "",
                "wall_end_iso": wall_end_dt.isoformat().replace("+00:00", "Z") if wall_end_dt else "",
                "wall_start_local": format_local_clock(wall_start_dt),
                "wall_end_local": format_local_clock(wall_end_dt),
                "wall_start_local_full": format_local_clock(wall_start_dt, include_date=True),
                "wall_end_local_full": format_local_clock(wall_end_dt, include_date=True),
                "wall_span_s": round(wall_span_s, 3),
                "wall_span_label": format_duration(wall_span_s),
                "active_duration_s": round(active_duration_s, 3),
                "active_duration_label": format_duration(active_duration_s),
                "children_count": 0,
            })

    # Sort chronologically by start time, keeping root first
    agents.sort(key=lambda a: (0 if a["depth"] == 0 else 1, a["wall_start_ms"] or 0, a["depth"]))

    # Annotate children_count and parallel execution mode
    by_conv = {a["conv_id"]: a for a in agents}
    siblings_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for a in agents:
        pid = a["parent_id"]
        if pid and pid in by_conv:
            by_conv[pid]["children_count"] += 1
            siblings_by_parent.setdefault(pid, []).append(a)
        a["parent_name"] = by_conv[pid]["name"] if pid and pid in by_conv else ""

    def _turns_overlap(turns_a: Sequence[Dict[str, Any]], turns_b: Sequence[Dict[str, Any]]) -> bool:
        for ta in turns_a:
            a_s = ta["start_ms"]
            a_e = ta["end_ms"]
            for tb in turns_b:
                b_s = tb["start_ms"]
                b_e = tb["end_ms"]
                overlap_s = (min(a_e, b_e) - max(a_s, b_s)) / 1000.0
                if overlap_s > HANDOFF_OVERLAP_TOLERANCE_S:
                    return True
        return False

    for pid, sibs in siblings_by_parent.items():
        # Detect parallelism: shared spawn_step_index OR overlapping active turn intervals
        step_counts: Dict[Any, int] = {}
        for s in sibs:
            idx = s.get("spawn_step_index")
            if idx is not None:
                step_counts[idx] = step_counts.get(idx, 0) + 1
        for i, a in enumerate(sibs):
            idx = a.get("spawn_step_index")
            if idx is not None and step_counts.get(idx, 0) > 1:
                a["mode"] = "parallel"
                continue
            a_turns = a.get("turns") or []
            if not a_turns:
                continue
            for j, b in enumerate(sibs):
                if i == j:
                    continue
                b_turns = b.get("turns") or []
                if b_turns and _turns_overlap(a_turns, b_turns):
                    a["mode"] = "parallel"
                    break

    # Summary timing rollups
    all_turn_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in agents
        for t in a["turns"]
    ]
    subagent_turn_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in agents
        if a["depth"] > 0
        for t in a["turns"]
    ]

    active_wall_s = total_merged_duration(all_turn_intervals)
    subagent_active_wall_s = total_merged_duration(subagent_turn_intervals)
    subagent_cumulative_s = sum(a["active_duration_s"] for a in agents if a["depth"] > 0)
    speedup = round(subagent_cumulative_s / subagent_active_wall_s, 2) if subagent_active_wall_s > 0 else 1.0
    peak_conc = compute_worker_concurrency(agents)

    gantt = compute_gantt_layout(agents)
    root_agent = by_conv[root_id]

    models_used: List[str] = []
    for a in agents:
        for part in [p.strip() for p in str(a.get("model") or "").split(",") if p.strip()]:
            if part not in models_used:
                models_used.append(part)

    phase_order = ["orchestration", "discovery", "planning", "construction", "verification"]
    phase_rollups: Dict[str, Dict[str, Any]] = {}
    for ph in phase_order:
        ph_agents = [a for a in agents if a["phase"] == ph]
        if not ph_agents:
            continue
        ph_intervals = [
            (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
            for a in ph_agents
            for t in a["turns"]
        ]
        ph_starts = [a["wall_start_ms"] for a in ph_agents if a["wall_start_ms"] is not None]
        ph_ends = [a["wall_end_ms"] for a in ph_agents if a["wall_end_ms"] is not None]
        ph_active_s = total_merged_duration(ph_intervals)
        ph_cum_s = sum(a["active_duration_s"] for a in ph_agents)
        ph_s_dt = datetime.fromtimestamp(min(ph_starts) / 1000.0, tz=timezone.utc) if ph_starts else None
        ph_e_dt = datetime.fromtimestamp(max(ph_ends) / 1000.0, tz=timezone.utc) if ph_ends else None
        phase_rollups[ph] = {
            "agent_count": len(ph_agents),
            "parallel_count": sum(1 for a in ph_agents if a["mode"] == "parallel"),
            "active_s": round(ph_active_s, 3),
            "active_label": format_duration(ph_active_s),
            "cumulative_s": round(ph_cum_s, 3),
            "cumulative_label": format_duration(ph_cum_s),
            "start_local": format_local_clock(ph_s_dt),
            "end_local": format_local_clock(ph_e_dt),
            "tokens": sum(a["tokens"]["total"] for a in ph_agents),
        }

    total_tokens = {
        "input": sum(a["tokens"]["input"] for a in agents),
        "cache_read": sum(a["tokens"]["cache_read"] for a in agents),
        "output": sum(a["tokens"]["output"] for a in agents),
        "total": sum(a["tokens"]["total"] for a in agents),
    }

    return {
        "source": "agy",
        "tz_label": get_local_tz_label(),
        "workspace_root": workspace_root,
        "root_conversation_id": root_id,
        "run_title": root_agent["name"],
        "summary": {
            "wall_start_local": gantt.get("start_local", root_agent["wall_start_local_full"]),
            "wall_end_local": gantt.get("end_local", root_agent["wall_end_local_full"]),
            "wall_span_s": gantt.get("true_span_s", root_agent["wall_span_s"]),
            "wall_span_label": gantt.get("true_span_label", root_agent["wall_span_label"]),
            "active_wall_s": round(active_wall_s, 3),
            "active_wall_label": format_duration(active_wall_s),
            "subagent_active_wall_s": round(subagent_active_wall_s, 3),
            "subagent_active_wall_label": format_duration(subagent_active_wall_s),
            "subagent_cumulative_s": round(subagent_cumulative_s, 3),
            "subagent_cumulative_label": format_duration(subagent_cumulative_s),
            "parallelism_speedup": speedup,
            "peak_concurrency": peak_conc,
            "total_agents": len(agents),
            "subagent_count": sum(1 for a in agents if a["depth"] > 0),
            "parallel_agents": sum(1 for a in agents if a["mode"] == "parallel"),
            "max_depth": max((a["depth"] for a in agents), default=0),
            "total_steps": sum(a["step_count"] for a in agents),
            "total_tool_calls": sum(a["tool_call_count"] for a in agents),
            "models_used": models_used,
            "tokens": total_tokens,
        },
        "phase_rollups": phase_rollups,
        "gantt": gantt,
        "agents": agents,
    }


def parse_legacy_agents_dir(agents_dir: str, workspace_root: str) -> Dict[str, Any]:
    """Fallback parser for legacy .agents/<role>/BRIEFING.md & handoff.md directories."""
    orchestrator_briefing_path = os.path.join(agents_dir, "orchestrator", "BRIEFING.md")
    roster: List[Dict[str, Any]] = []

    if os.path.exists(orchestrator_briefing_path):
        with open(orchestrator_briefing_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        roster_matches = re.findall(
            r"^\|\s*([a-zA-Z0-9_-]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|",
            content,
            re.MULTILINE,
        )
        for match in roster_matches:
            agent_name = match[0].strip()
            if agent_name.lower() in ("agent", "------", "---", "type", "status"):
                continue
            roster.append({
                "name": agent_name,
                "type": match[1].strip(),
                "task": match[2].strip(),
                "status": match[3].strip(),
                "conv_id": match[4].strip(),
                "mode": "parallel" if "critic" in agent_name.lower() or agent_name.lower() in ("auditor_1", "reviewer_1") else "serial",
            })

    all_agent_dirs = [
        d for d in os.listdir(agents_dir)
        if os.path.isdir(os.path.join(agents_dir, d)) and d not in ("agents", "skills", "rules", "plugins")
    ]
    if "sentinel" in all_agent_dirs and not any(a["name"] == "sentinel" for a in roster):
        roster.insert(0, {
            "name": "sentinel",
            "type": "sentinel",
            "task": "Milestone & Integration Monitor",
            "status": "complete",
            "conv_id": "unknown",
            "mode": "serial",
        })
    if "orchestrator" in all_agent_dirs and not any(a["name"] == "orchestrator" for a in roster):
        idx = 1 if roster and roster[0]["name"] == "sentinel" else 0
        roster.insert(idx, {
            "name": "orchestrator",
            "type": "teamwork_preview_orchestrator",
            "task": "Swarm Router & Git Gatekeeper",
            "status": "complete",
            "conv_id": "unknown",
            "mode": "serial",
        })
    if "victory_auditor" in all_agent_dirs and not any(a["name"] == "victory_auditor" for a in roster):
        roster.append({
            "name": "victory_auditor",
            "type": "victory_auditor",
            "task": "Independent Victory Verifier",
            "status": "complete",
            "conv_id": "unknown",
            "mode": "serial",
        })

    parsed_agents: List[Dict[str, Any]] = []
    for entry in roster:
        agent_name = entry["name"]
        agent_folder = os.path.join(agents_dir, agent_name)
        if not os.path.exists(agent_folder):
            continue

        briefing_path = os.path.join(agent_folder, "BRIEFING.md")
        roles: List[str] = []
        if os.path.exists(briefing_path):
            with open(briefing_path, "r", encoding="utf-8", errors="replace") as f:
                b_content = f.read()
            if not entry.get("conv_id") or entry["conv_id"] == "unknown" or len(entry["conv_id"]) < 10:
                cid_match = re.search(r"Conversation ID:\s*([a-f0-9\-]+)", b_content, re.IGNORECASE)
                if cid_match:
                    entry["conv_id"] = cid_match.group(1).strip()
            roles_match = re.search(r"Roles:\s*\[?([^\]\r\n]+)\]?", b_content, re.IGNORECASE)
            if roles_match:
                roles = [r.strip().replace("'", "").replace('"', "") for r in roles_match.group(1).split(",")]

        handoff_path = os.path.join(agent_folder, "handoff.md")
        summary = "No handoff content generated."
        if os.path.exists(handoff_path):
            with open(handoff_path, "r", encoding="utf-8", errors="replace") as f:
                h_content = f.read()
            paragraphs = [p.strip() for p in h_content.split("\n\n") if p.strip()]
            if paragraphs and paragraphs[0].startswith("#"):
                paragraphs = paragraphs[1:]
            summary = " ".join(paragraphs[:2]) if paragraphs else "Handoff report completed."
            summary = re.sub(r"[\r\n]+", " ", summary)

        produced_docs: List[Dict[str, str]] = []
        mtimes: List[float] = []
        for f_name in sorted(os.listdir(agent_folder)):
            fp = os.path.join(agent_folder, f_name)
            if os.path.isfile(fp):
                mtimes.append(os.path.getmtime(fp))
            if f_name.endswith(".md") and f_name not in ("ORIGINAL_REQUEST.md", "progress.md"):
                produced_docs.append({"name": f_name, "path": f"./{agent_name}/{f_name}"})

        start_dt = datetime.fromtimestamp(min(mtimes), tz=timezone.utc) if mtimes else None
        end_dt = datetime.fromtimestamp(max(mtimes), tz=timezone.utc) if mtimes else None
        dur_s = max(0.0, (end_dt - start_dt).total_seconds()) if (start_dt and end_dt) else 0.0
        turns = [{
            "index": 1,
            "label": "Legacy filesystem span (file mtime)",
            "start_iso": start_dt.isoformat().replace("+00:00", "Z"),
            "end_iso": end_dt.isoformat().replace("+00:00", "Z"),
            "start_ms": int(start_dt.timestamp() * 1000),
            "end_ms": int(end_dt.timestamp() * 1000),
            "start_local": format_local_clock(start_dt),
            "end_local": format_local_clock(end_dt),
            "start_local_full": format_local_clock(start_dt, include_date=True),
            "end_local_full": format_local_clock(end_dt, include_date=True),
            "duration_s": round(dur_s, 3),
            "duration_label": format_duration(dur_s),
            "steps": 0,
            "tool_calls": 0,
            "tokens": 0,
        }] if start_dt and end_dt else []

        name_lower = agent_name.lower()
        if name_lower in ("orchestrator", "sentinel"):
            phase = "orchestration"
        elif "spec" in name_lower:
            phase = "discovery"
        elif "plan" in name_lower:
            phase = "planning"
        elif name_lower in ("worker_impl", "auditor_1", "reviewer_1"):
            phase = "construction"
        else:
            phase = "verification"

        raw_cid = entry.get("conv_id") or ""
        unique_id = raw_cid if (raw_cid and raw_cid != "unknown") else f"legacy-{agent_name}"
        parsed_agents.append({
            "id": unique_id,
            "conv_id": raw_cid or "unknown",
            "parent_id": "",
            "parent_name": "",
            "depth": 0 if name_lower in ("orchestrator", "sentinel") else 1,
            "name": agent_name,
            "type": entry["type"],
            "role": roles[0] if roles else entry["type"],
            "model": "legacy",
            "model_source": "legacy",
            "requested_model": "legacy",
            "workspace_mode": "inherit",
            "task": entry["task"],
            "status": entry["status"],
            "mode": entry["mode"],
            "roles": roles,
            "summary": summary,
            "docs": produced_docs,
            "phase": phase,
            "transcript_uri": "",
            "step_count": 0,
            "tool_call_count": 0,
            "tool_breakdown": [],
            "tokens": {"input": 0, "cache_read": 0, "output": 0, "total": 0},
            "turns": turns,
            "wall_start_ms": int(start_dt.timestamp() * 1000) if start_dt else None,
            "wall_end_ms": int(end_dt.timestamp() * 1000) if end_dt else None,
            "wall_start_iso": start_dt.isoformat().replace("+00:00", "Z") if start_dt else "",
            "wall_end_iso": end_dt.isoformat().replace("+00:00", "Z") if end_dt else "",
            "wall_start_local": format_local_clock(start_dt),
            "wall_end_local": format_local_clock(end_dt),
            "wall_start_local_full": format_local_clock(start_dt, include_date=True),
            "wall_end_local_full": format_local_clock(end_dt, include_date=True),
            "wall_span_s": round(dur_s, 3),
            "wall_span_label": format_duration(dur_s),
            "active_duration_s": round(dur_s, 3),
            "active_duration_label": format_duration(dur_s),
            "children_count": 0,
        })

    if not parsed_agents:
        raise ValueError(f"No AGY telemetry or legacy .agents/ briefing records found for {workspace_root}")

    gantt = compute_gantt_layout(parsed_agents)
    intervals = [(t["start_ms"] / 1000.0, t["end_ms"] / 1000.0) for a in parsed_agents for t in a["turns"]]
    active_s = total_merged_duration(intervals)
    cum_s = sum(a["active_duration_s"] for a in parsed_agents)

    return {
        "source": "legacy",
        "tz_label": get_local_tz_label(),
        "workspace_root": workspace_root,
        "root_conversation_id": parsed_agents[0]["conv_id"],
        "run_title": "Legacy .agents/ Trajectory",
        "summary": {
            "wall_start_local": gantt.get("start_local", "—"),
            "wall_end_local": gantt.get("end_local", "—"),
            "wall_span_s": gantt.get("true_span_s", 0.0),
            "wall_span_label": gantt.get("true_span_label", "0s"),
            "active_wall_s": round(active_s, 3),
            "active_wall_label": format_duration(active_s),
            "subagent_active_wall_s": round(active_s, 3),
            "subagent_active_wall_label": format_duration(active_s),
            "subagent_cumulative_s": round(cum_s, 3),
            "subagent_cumulative_label": format_duration(cum_s),
            "parallelism_speedup": round(cum_s / active_s, 2) if active_s > 0 else 1.0,
            "peak_concurrency": compute_peak_concurrency(intervals),
            "total_agents": len(parsed_agents),
            "subagent_count": max(0, len(parsed_agents) - 1),
            "parallel_agents": sum(1 for a in parsed_agents if a["mode"] == "parallel"),
            "max_depth": 1,
            "total_steps": 0,
            "total_tool_calls": 0,
            "models_used": ["legacy"],
            "tokens": {"input": 0, "cache_read": 0, "output": 0, "total": 0},
        },
        "phase_rollups": {},
        "gantt": gantt,
        "agents": parsed_agents,
    }
