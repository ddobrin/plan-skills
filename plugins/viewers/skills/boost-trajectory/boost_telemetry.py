#!/usr/bin/env python3
"""Telemetry discovery and 3-tier /boost parsing for AGY live runs."""

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
    compute_boost_worker_concurrency,
    compute_gantt_layout,
    format_duration,
    format_local_clock,
    get_local_tz_label,
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

BOOST_TIER2_NAMES = {"DeepCoder", "DeepInvestigator"}
BOOST_TIER3_NAMES = {
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
    """Score how closely a conversation's workspace_uris matches workspace_root."""
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


def _extract_user_request_text(content: str) -> str:
    """Extract readable user request text from a USER_INPUT step."""
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
    text = m.group(1) if m else content
    text = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ORCHESTRATOR>.*?</ORCHESTRATOR>", "", text, flags=re.DOTALL)
    text = re.sub(r"<USER_SETTINGS_CHANGE>.*?</USER_SETTINGS_CHANGE>", "", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", text).strip()


def _is_boost_user_input(content: str) -> bool:
    """Return True if a USER_INPUT step explicitly carries /boost or <ORCHESTRATOR>."""
    if "<ORCHESTRATOR>" in content:
        return True
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
    user_req = m.group(1) if m else content
    return bool(re.match(r"^\s*/boost(?=$|\s|/boost)", user_req, re.IGNORECASE))


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
    """Parse invoke_subagent calls (both batched Subagents and flat args) and Created blocks."""
    spawns: Dict[str, Dict[str, Any]] = {}
    pending_calls: List[Dict[str, Any]] = []

    for step in steps:
        step_type = step.get("type")
        step_idx = step.get("step_index")
        step_ts = parse_iso_timestamp(step.get("created_at"))
        if step_type == "USER_INPUT":
            pending_calls.clear()

        tool_calls = step.get("tool_calls") or []
        has_invoke = any(tc.get("name") == "invoke_subagent" for tc in tool_calls)
        if has_invoke and pending_calls:
            # A new invoke_subagent batch starts after prior unresolved calls; drop stale entries.
            pending_calls.clear()

        for tc in tool_calls:
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


def _extract_sent_recipients(steps: Sequence[Dict[str, Any]]) -> Set[str]:
    recipients: Set[str] = set()
    for step in steps:
        for tc in step.get("tool_calls") or []:
            if tc.get("name") != "send_message":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            rec = _clean_arg_str(args.get("Recipient"))
            if rec:
                recipients.add(rec)
    return recipients


def _extract_settings_model_changes(steps: Sequence[Dict[str, Any]]) -> List[Tuple[int, str]]:
    """Extract (step_index, model_name) entries from USER_INPUT <USER_SETTINGS_CHANGE> blocks."""
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


def _parse_dispatch_header(steps: Sequence[Dict[str, Any]]) -> Tuple[Optional[datetime], Optional[str], str]:
    """Extract spawn timestamp, parent sender ID, and initial prompt from early steps.

    Handles both Tier-3 workers (dispatch at steps[0]) and Tier-2 delegates
    where steps[0] is a SYSTEM_SDK periodic reminder and steps[1] is the
    [Message] dispatch header.
    """
    if not steps:
        return None, None, ""

    first = steps[0]
    if first.get("type") == "USER_INPUT":
        return parse_iso_timestamp(first.get("created_at")), None, _extract_user_request_text(str(first.get("content") or ""))

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


def _parse_markdown_report(message_text: str, agent_family: str = "") -> Dict[str, Any]:
    """Parse structured sections and Skepticism Disclaimer from a send_message payload."""
    text = (message_text or "").strip()
    lines = text.splitlines()

    disclaimer_lines: List[str] = []
    body_lines: List[str] = []
    in_disclaimer = False
    for line in lines:
        stripped = line.strip()
        if not in_disclaimer and (
            (stripped.startswith(">") and "skepticism disclaimer" in stripped.lower())
            or ("[WARNING]" in stripped or "[!WARNING]" in stripped) and "skepticism disclaimer" in stripped.lower()
        ):
            in_disclaimer = True
            cleaned = re.sub(r"^>\s*", "", stripped)
            cleaned = re.sub(
                r"(?:\[!WARNING\]\s*)?(?:\*\*)?Skepticism Disclaimer(?:\*\*)?:?\s*",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned:
                disclaimer_lines.append(cleaned)
            continue
        if in_disclaimer:
            if stripped.startswith(">"):
                cleaned = re.sub(r"^>\s*", "", stripped)
                if cleaned:
                    disclaimer_lines.append(cleaned)
                continue
            if stripped == "":
                in_disclaimer = False
                continue
            in_disclaimer = False
        body_lines.append(line)

    sections: List[Dict[str, str]] = []
    cur_title = ""
    cur_buf: List[str] = []
    in_code = False

    for line in body_lines:
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            cur_buf.append(line)
            continue
        if not in_code:
            hm = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
            if hm:
                if cur_title or any(x.strip() for x in cur_buf):
                    body = "\n".join(cur_buf).strip()
                    if cur_title or body:
                        sections.append({
                            "title": cur_title or "Overview",
                            "body": body,
                        })
                cur_title = hm.group(2).strip()
                cur_buf = []
                continue
        cur_buf.append(line)

    if cur_title or any(x.strip() for x in cur_buf):
        body = "\n".join(cur_buf).strip()
        if cur_title or body:
            sections.append({
                "title": cur_title or "Summary",
                "body": body,
            })

    disclaimer = " ".join(disclaimer_lines).strip()
    lower = text.lower()
    heading_titles = [s["title"].lower() for s in sections]
    has_inv_heading = bool(
        re.search(r"^#{1,3}\s+.*investigation report", lower, re.MULTILINE)
        or any(
            "investigation report" in t
            or t in ("executive summary", "findings", "remaining questions & gaps", "remaining questions", "open questions")
            for t in heading_titles
        )
    )
    has_coding_heading = any(
        "what i changed" in t
        or "what the prior attempt got wrong" in t
        or "verification record" in t
        or "known issues" in t
        for t in heading_titles
    )

    if "pipeline completed" in lower and not has_inv_heading and not has_coding_heading:
        kind = "pipeline"
    elif has_inv_heading or (agent_family == "investigator" and ("investigation report" in lower or not has_coding_heading)):
        kind = "investigation"
    elif disclaimer or has_coding_heading or (
        agent_family == "coder"
        and any(k in lower for k in ("what i changed", "verification record", "known issues", "what the prior attempt got wrong"))
    ):
        kind = "coding"
    elif "executive summary" in lower or "remaining questions" in lower:
        kind = "investigation"
    elif any(k in lower for k in ("what i changed", "verification record", "known issues", "what the prior attempt got wrong")):
        kind = "coding"
    elif "pipeline completed" in lower:
        kind = "pipeline"
    else:
        kind = "message"

    known_issue_text = "\n".join(
        s["body"] for s in sections if "known issues" in s["title"].lower() or "remaining" in s["title"].lower()
    )
    flag_search_text = known_issue_text if known_issue_text else (text if kind == "coding" else "")
    issue_flags: List[str] = []
    for flag in ("Fatal Functional Bug", "Shallow Verification", "Minor Robustness Risk"):
        if flag_search_text and flag in flag_search_text:
            issue_flags.append(flag)

    return {
        "kind": kind,
        "skepticism_disclaimer": disclaimer,
        "issue_flags": issue_flags,
        "sections": sections[:30],
        "raw_preview": text[:4000],
        "char_count": len(text),
    }


def _extract_send_messages(
    steps: Sequence[Dict[str, Any]],
    name_lookup: Dict[str, str],
    agent_family: str = "",
) -> List[Dict[str, Any]]:
    """Extract structured send_message report cards from an agent's transcript."""
    reports: List[Dict[str, Any]] = []
    for step in steps:
        ts_iso = step.get("created_at") or ""
        ts_dt = parse_iso_timestamp(ts_iso)
        for tc in step.get("tool_calls") or []:
            if tc.get("name") != "send_message":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            recipient = _clean_arg_str(args.get("Recipient"))
            message = _clean_arg_str(args.get("Message"))
            if not message:
                continue
            parsed = _parse_markdown_report(message, agent_family=agent_family)
            reports.append({
                "timestamp_iso": ts_iso,
                "timestamp_local": format_local_clock(ts_dt),
                "recipient_id": recipient,
                "recipient_name": name_lookup.get(recipient, recipient[:8] if recipient else "parent"),
                **parsed,
            })
    return reports


def _extract_produced_docs(steps: Sequence[Dict[str, Any]], workspace_root: str) -> List[Dict[str, str]]:
    """Extract created or edited file paths from transcript tool calls."""
    seen: Set[str] = set()
    docs: List[Dict[str, str]] = []
    ws_norm = os.path.normpath(os.path.abspath(workspace_root))

    for step in steps:
        for tc in step.get("tool_calls") or []:
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
            if abs_path in seen:
                continue
            seen.add(abs_path)
            if abs_path.startswith(ws_norm + os.sep):
                rel = os.path.relpath(abs_path, ws_norm)
            else:
                rel = abs_path
            docs.append({"name": rel, "path": f"file://{abs_path}"})
    return docs


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


def _extract_summary(
    steps: Sequence[Dict[str, Any]],
    reports: Sequence[Dict[str, Any]],
    status: str,
) -> str:
    """Extract a readable summary from PLANNER_RESPONSE or send_message report."""
    for step in reversed(steps):
        if step.get("type") == "PLANNER_RESPONSE":
            txt = str(step.get("content") or "").strip()
            if txt:
                cleaned = re.sub(r"```[\s\S]*?```", "[code/json output]", txt)
                cleaned = re.sub(r"(?m)^>\s*", "", cleaned)
                cleaned = re.sub(r"[#*`]+", "", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if len(cleaned) > 280:
                    return cleaned[:277].rstrip() + "..."
                return cleaned
    if reports:
        last = reports[-1]
        text = last.get("skepticism_disclaimer") or (
            last["sections"][0]["body"] if last.get("sections") else last.get("raw_preview", "")
        )
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) > 280:
            return cleaned[:277].rstrip() + "..."
        if cleaned:
            return cleaned
    if status in ("running", "killed"):
        return f"Interrupted / {status} before recording a final summary."
    return f"Completed ({status})." if status else "No planner summary recorded."


def _resolve_model(
    steps: Sequence[Dict[str, Any]],
    requested_model: str,
    inherited_model: str,
    settings_model: str,
) -> Tuple[str, str]:
    """Return (resolved_model, model_source)."""
    seen_models: List[str] = []
    for step in steps:
        m = step.get("model")
        if m and isinstance(m, str) and m not in seen_models:
            seen_models.append(m)
    if seen_models:
        return ", ".join(seen_models), "planner_response"
    req = (requested_model or "").strip()
    if req and req.lower() not in ("inherit", "default", "none"):
        return req, "requested"
    if inherited_model and inherited_model.lower() not in ("inherit", "default", "unknown"):
        return inherited_model, "inherited"
    if settings_model:
        return settings_model, "user_settings"
    return req or "default", "fallback"


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


def _has_boost_descendants(
    root_id: str,
    by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
) -> Tuple[bool, int]:
    """Return (has_boost_tier2_or_tier3, total_descendant_count)."""
    has_boost = False
    count = 0
    stack = list(children_by_parent.get(root_id, []))
    seen = {root_id}
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        count += 1
        info = by_id.get(cid) or {}
        aname = info.get("agent_name") or ""
        if aname in BOOST_TIER2_NAMES or aname in BOOST_TIER3_NAMES:
            has_boost = True
        stack.extend(children_by_parent.get(cid, []))
    return has_boost, count


def _is_boost_child(
    cid: str,
    spawn_meta: Dict[str, Any],
    by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
) -> bool:
    req_type = spawn_meta.get("requested_type") or ""
    db_name = (by_id.get(cid) or {}).get("agent_name") or ""
    if req_type in BOOST_TIER2_NAMES or db_name in BOOST_TIER2_NAMES:
        return True
    for gc in children_by_parent.get(cid, []):
        gc_name = (by_id.get(gc) or {}).get("agent_name") or ""
        if gc_name in BOOST_TIER3_NAMES:
            return True
    return False


def _segment_boost_invocations(
    root_id: str,
    root_steps: Sequence[Dict[str, Any]],
    by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """Partition root_steps into individual /boost invocation pipelines."""
    user_indices = [i for i, s in enumerate(root_steps) if s.get("type") == "USER_INPUT"]
    settings_changes = _extract_settings_model_changes(root_steps)

    def _settings_model_at(step_pos: int) -> str:
        chosen = ""
        for idx, model_name in settings_changes:
            if idx <= step_pos:
                chosen = model_name
        return chosen

    segments: List[Tuple[int, int, Sequence[Dict[str, Any]]]] = []
    for pos, start_idx in enumerate(user_indices):
        end_idx = user_indices[pos + 1] if pos + 1 < len(user_indices) else len(root_steps)
        segments.append((start_idx, end_idx, root_steps[start_idx:end_idx]))

    invocations: List[Dict[str, Any]] = []
    claimed_children: Set[str] = set()

    for start_idx, end_idx, seg_steps in segments:
        first_content = str(seg_steps[0].get("content") or "")
        spawns = _extract_subagent_spawns(seg_steps)
        sent_recipients = _extract_sent_recipients(seg_steps)

        boost_children: Set[str] = {
            cid for cid, meta in spawns.items()
            if _is_boost_child(cid, meta, by_id, children_by_parent)
        }
        is_explicit_boost = _is_boost_user_input(first_content)
        spawns_boost_tier2 = len(boost_children) > 0

        if is_explicit_boost or spawns_boost_tier2:
            child_ids = list(spawns.keys())
            claimed_children.update(child_ids)
            invocations.append({
                "start_pos": start_idx,
                "end_pos": end_idx,
                "steps": list(seg_steps),
                "prompt": _extract_user_request_text(first_content),
                "spawns": dict(spawns),
                "child_ids": child_ids,
                "boost_tier2_ids": set(boost_children) or set(child_ids),
                "settings_model": _settings_model_at(end_idx - 1),
            })
        elif invocations and (sent_recipients & invocations[-1]["boost_tier2_ids"]):
            # Unmarked follow-up redirecting an active Tier-2 delegate (e.g. TASK CHANGED)
            inv = invocations[-1]
            inv["end_pos"] = end_idx
            inv["steps"].extend(seg_steps)
            inv["spawns"].update({k: v for k, v in spawns.items() if k not in inv["spawns"]})
            for cid in spawns.keys():
                if cid not in inv["child_ids"]:
                    inv["child_ids"].append(cid)
                claimed_children.add(cid)
            inv["boost_tier2_ids"].update(boost_children)
            inv["settings_model"] = _settings_model_at(end_idx - 1) or inv["settings_model"]

    # Attach any DB-recorded Tier-2 children of root_id not matched via transcript generics
    unclaimed_db_boost = [
        cid for cid in children_by_parent.get(root_id, [])
        if cid not in claimed_children and _is_boost_child(cid, {}, by_id, children_by_parent)
    ]
    if unclaimed_db_boost:
        if invocations:
            inv_starts = [
                parse_iso_timestamp(inv["steps"][0].get("created_at")) if inv["steps"] else None
                for inv in invocations
            ]
            for cid in unclaimed_db_boost:
                child_dt = parse_iso_timestamp((by_id.get(cid) or {}).get("last_modified_time"))
                target_inv = invocations[-1]
                if child_dt is not None:
                    for idx_inv, inv in enumerate(invocations):
                        s_dt = inv_starts[idx_inv]
                        e_dt = inv_starts[idx_inv + 1] if idx_inv + 1 < len(inv_starts) else None
                        if s_dt is not None and child_dt >= s_dt and (e_dt is None or child_dt < e_dt):
                            target_inv = inv
                            break
                if cid not in target_inv["child_ids"]:
                    target_inv["child_ids"].append(cid)
                target_inv["boost_tier2_ids"].add(cid)
        else:
            invocations.append({
                "start_pos": 0,
                "end_pos": len(root_steps),
                "steps": list(root_steps),
                "prompt": "(unmarked /boost delegation session)",
                "spawns": {},
                "child_ids": list(unclaimed_db_boost),
                "boost_tier2_ids": set(unclaimed_db_boost),
                "settings_model": _settings_model_at(max(0, len(root_steps) - 1)),
            })

    return invocations


def list_boost_runs(agy_dir: str, workspace_root: str) -> List[Dict[str, Any]]:
    """Return root AGY conversations containing /boost runs for workspace_root."""
    by_id, children_by_parent = _load_db_metadata(agy_dir)
    if not by_id:
        return []

    runs: List[Dict[str, Any]] = []
    for cid, row in by_id.items():
        if row["parent_id"]:
            continue
        score = _match_workspace_score(row["workspace_uris"], workspace_root)
        if score == 0:
            continue
        has_boost_desc, desc_count = _has_boost_descendants(cid, by_id, children_by_parent)
        step_count = int(row["db_step_count"] or 0)
        if step_count == 0 and desc_count == 0:
            continue

        steps, _ = _read_transcript(agy_dir, cid)
        invocations = _segment_boost_invocations(cid, steps, by_id, children_by_parent)
        if not invocations and not has_boost_desc:
            continue

        has_delegation = has_boost_desc or any(bool(inv["child_ids"]) for inv in invocations)
        latest_routine = "delegation" if (invocations and invocations[-1]["child_ids"]) else (
            "delegation" if has_boost_desc else "solo"
        )
        runs.append({
            "conversation_id": cid,
            "title": row["title"] or "(untitled)",
            "agent_name": row["agent_name"] or "Orchestrator",
            "step_count": max(step_count, len(steps)),
            "last_modified_time": row["last_modified_time"] or "",
            "status": row["status"] or "",
            "subagent_count": desc_count,
            "boost_invocation_count": len(invocations),
            "has_delegation": has_delegation,
            "routine": "delegation" if has_delegation else "solo",
            "latest_routine": latest_routine,
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
    """Walk parent_conversation_id / dispatch sender pointers up to the root conversation."""
    cur = cid
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = by_id.get(cur)
        parent = (row or {}).get("parent_id") or ""
        if not parent:
            steps, _ = _read_transcript(agy_dir, cur)
            _, sender_id, _ = _parse_dispatch_header(steps)
            if sender_id and sender_id not in seen and (sender_id in by_id or os.path.isdir(os.path.join(agy_dir, "brain", sender_id))):
                parent = sender_id
        if not parent:
            break
        cur = parent
    return cur


def select_boost_run(
    agy_dir: str,
    workspace_root: str,
    conversation_id: Optional[str] = None,
) -> Optional[str]:
    """Select target root conversation ID, preferring Delegation /boost runs."""
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

    runs = list_boost_runs(agy_dir, workspace_root)
    delegation = [r for r in runs if r["has_delegation"]]
    if delegation:
        return delegation[0]["conversation_id"]
    if runs:
        return runs[0]["conversation_id"]
    return None


def _classify_boost_agent(agent_name: str, req_type: str, depth: int) -> Dict[str, Any]:
    """Return tier, family, and worker stage metadata for a /boost agent."""
    if depth == 0:
        return {
            "tier": 1,
            "tier_label": "Tier 1 · Orchestrator",
            "boost_family": "orchestrator",
            "worker_stage": "orchestrator",
            "display_name": "Orchestrator",
        }
    raw = (agent_name or req_type or "subagent").strip()
    low = raw.lower()
    if depth == 1:
        family = "investigator" if "investigator" in low else ("coder" if "coder" in low else "delegate")
        return {
            "tier": 2,
            "tier_label": "Tier 2 · Delegate",
            "boost_family": family,
            "worker_stage": "delegate",
            "display_name": raw,
        }
    family = "investigator" if "investigator" in low else ("coder" if "coder" in low else "worker")
    if "improvement" in low:
        stage = "improvement"
    elif "workerl0" in low or low.endswith("l0"):
        stage = "l0"
    else:
        stage = "worker"
    return {
        "tier": 3,
        "tier_label": "Tier 3 · Worker",
        "boost_family": family,
        "worker_stage": stage,
        "display_name": raw,
    }


def _collect_invocation_tree(
    agy_dir: str,
    root_id: str,
    inv: Dict[str, Any],
    by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
) -> Dict[str, Dict[str, Any]]:
    """Collect root (scoped to invocation steps) + all Tier-2/Tier-3 descendants."""
    nodes: Dict[str, Dict[str, Any]] = {}
    root_db = by_id.get(root_id) or {}
    nodes[root_id] = {
        "conversation_id": root_id,
        "title": root_db.get("title") or "Orchestrator",
        "agent_name": "Orchestrator",
        "parent_id": "",
        "depth": 0,
        "db_step_count": len(inv["steps"]),
        "last_modified_time": root_db.get("last_modified_time") or "",
        "status": root_db.get("status") or "CASCADE_RUN_STATUS_IDLE",
        "killed": bool(root_db.get("killed")),
        "steps": inv["steps"],
        "transcript_path": os.path.join(agy_dir, "brain", root_id, ".system_generated", "logs", "transcript_full.jsonl"),
        "spawns": inv["spawns"],
        "spawn_meta": {
            "prompt": inv["prompt"],
            "requested_type": "Orchestrator",
            "requested_role": "Boost Orchestrator",
            "requested_model": "default",
        },
    }
    if not os.path.exists(nodes[root_id]["transcript_path"]):
        alt = os.path.join(agy_dir, "brain", root_id, ".system_generated", "logs", "transcript.jsonl")
        nodes[root_id]["transcript_path"] = alt if os.path.exists(alt) else None

    queue: List[Tuple[str, str, int, Dict[str, Any]]] = []
    for cid in inv["child_ids"]:
        queue.append((cid, root_id, 1, inv["spawns"].get(cid) or {}))

    seen: Set[str] = {root_id}
    while queue:
        cid, parent_id, fallback_depth, spawn_meta = queue.pop(0)
        if cid in seen:
            continue
        seen.add(cid)

        db_info = by_id.get(cid) or {}
        steps, tpath = _read_transcript(agy_dir, cid)
        spawns = _extract_subagent_spawns(steps)
        depth = int(db_info.get("depth") or fallback_depth)
        nodes[cid] = {
            "conversation_id": cid,
            "title": db_info.get("title") or "",
            "agent_name": db_info.get("agent_name") or spawn_meta.get("requested_type") or "",
            "parent_id": db_info.get("parent_id") or parent_id,
            "depth": depth,
            "db_step_count": int(db_info.get("db_step_count") or 0),
            "last_modified_time": db_info.get("last_modified_time") or "",
            "status": db_info.get("status") or "",
            "killed": bool(db_info.get("killed")),
            "steps": steps,
            "transcript_path": tpath,
            "spawns": spawns,
            "spawn_meta": spawn_meta,
        }

        discovered_children: List[str] = list(children_by_parent.get(cid, []))
        for scid in spawns.keys():
            db_parent = (by_id.get(scid) or {}).get("parent_id") or ""
            if db_parent and db_parent != cid:
                continue
            if scid not in discovered_children:
                discovered_children.append(scid)
        for scid in discovered_children:
            db_parent = (by_id.get(scid) or {}).get("parent_id") or ""
            meta = spawns.get(scid) or {}
            if db_parent and db_parent != cid:
                meta = {}
            queue.append((scid, cid, depth + 1, meta))

    return nodes


def _tree_order_agents(agents: List[Dict[str, Any]], root_id: str) -> List[Dict[str, Any]]:
    """Order agents depth-first in chronological sibling order (T1 -> T2 -> T3)."""
    by_parent: Dict[str, List[Dict[str, Any]]] = {}
    by_id = {a["conv_id"]: a for a in agents}
    for a in agents:
        pid = a.get("parent_id") or ""
        by_parent.setdefault(pid, []).append(a)
    for sibs in by_parent.values():
        sibs.sort(key=lambda x: (x.get("wall_start_ms") or 0, x.get("tier") or 0, x.get("name") or ""))

    ordered: List[Dict[str, Any]] = []
    visited: Set[str] = set()

    def walk(cid: str) -> None:
        if cid in visited or cid not in by_id:
            return
        visited.add(cid)
        ordered.append(by_id[cid])
        for child in by_parent.get(cid, []):
            walk(child["conv_id"])

    walk(root_id)
    for a in agents:
        if a["conv_id"] not in visited:
            ordered.append(a)
    return ordered


def _build_invocation_payload(
    agy_dir: str,
    root_id: str,
    workspace_root: str,
    inv: Dict[str, Any],
    inv_index: int,
    total_invocations: int,
    by_id: Dict[str, Dict[str, Any]],
    children_by_parent: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Parse one /boost invocation into a full 3-tier pipeline telemetry object."""
    nodes = _collect_invocation_tree(agy_dir, root_id, inv, by_id, children_by_parent)
    settings_model = inv.get("settings_model") or ""

    # Preliminary name lookup for send_message recipient labels
    name_lookup: Dict[str, str] = {}
    for cid, node in nodes.items():
        if cid == root_id:
            name_lookup[cid] = "Orchestrator"
        else:
            meta = node.get("spawn_meta") or {}
            name_lookup[cid] = node.get("agent_name") or meta.get("requested_type") or cid[:8]

    # Resolve models top-down (root -> T2 -> T3) so 'inherit' resolves meaningfully
    resolved_models: Dict[str, Tuple[str, str]] = {}
    for depth_pass in sorted({n["depth"] for n in nodes.values()}):
        for cid, node in nodes.items():
            if node["depth"] != depth_pass:
                continue
            pid = node.get("parent_id") or ""
            parent_model = resolved_models.get(pid, ("", ""))[0] if pid else ""
            req_model = (node.get("spawn_meta") or {}).get("requested_model") or ""
            resolved_models[cid] = _resolve_model(
                node["steps"],
                req_model,
                parent_model,
                settings_model,
            )

    agents: List[Dict[str, Any]] = []
    for cid, node in nodes.items():
        steps = node["steps"]
        depth = node["depth"]
        spawn_meta = node.get("spawn_meta") or {}
        dispatch_ts, dispatch_sender, dispatch_prompt = _parse_dispatch_header(steps)
        spawn_ts = spawn_meta.get("spawn_call_ts") or dispatch_ts
        turns = segment_active_turns(steps, spawn_ts=spawn_ts)

        wall_start_dt = parse_iso_timestamp(turns[0]["start_iso"]) if turns else spawn_ts
        wall_end_dt = parse_iso_timestamp(turns[-1]["end_iso"]) if turns else parse_iso_timestamp(node["last_modified_time"])
        wall_span_s = max(0.0, (wall_end_dt - wall_start_dt).total_seconds()) if (wall_start_dt and wall_end_dt) else 0.0
        active_duration_s = sum(t["duration_s"] for t in turns)

        req_type = spawn_meta.get("requested_type") or node["agent_name"] or ("Orchestrator" if depth == 0 else "subagent")
        role = spawn_meta.get("requested_role") or ""
        cls = _classify_boost_agent(node["agent_name"], req_type, depth)

        tool_count, tool_breakdown = _summarize_tool_calls(steps)
        tokens = _compute_tokens(steps)
        docs = _extract_produced_docs(steps, workspace_root)
        reports = _extract_send_messages(steps, name_lookup, agent_family=cls["boost_family"])

        status_raw = node["status"] or ("DONE" if steps else "UNKNOWN")
        status_clean = status_raw.replace("CASCADE_RUN_STATUS_", "").lower()
        if node["killed"]:
            status_clean = "killed"
        elif not steps and depth > 0:
            status_clean = "empty"

        prompt_text = spawn_meta.get("prompt") or dispatch_prompt or inv.get("prompt") or ""
        task_preview = re.sub(r"\s+", " ", prompt_text).strip()
        if len(task_preview) > 320:
            task_preview = task_preview[:317].rstrip() + "..."

        resolved_model, model_source = resolved_models.get(cid, ("default", "fallback"))
        req_model = spawn_meta.get("requested_model") or ("default" if depth == 0 else "inherit")

        parent_id = "" if cid == root_id else (node["parent_id"] or dispatch_sender or root_id)
        summary = _extract_summary(steps, reports, status_clean)

        agents.append({
            "id": cid,
            "conv_id": cid,
            "parent_id": parent_id,
            "parent_name": name_lookup.get(parent_id, "") if parent_id else "",
            "depth": depth,
            "tier": cls["tier"],
            "tier_label": cls["tier_label"],
            "boost_family": cls["boost_family"],
            "worker_stage": cls["worker_stage"],
            "name": cls["display_name"],
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
            "summary": summary,
            "reports": reports,
            "has_report": len(reports) > 0,
            "incomplete_report": (cls["tier"] >= 2 and len(reports) == 0),
            "docs": docs,
            "transcript_uri": f"file://{node['transcript_path']}" if node.get("transcript_path") else "",
            "step_count": len(steps) if cid == root_id else max(node["db_step_count"], len(steps)),
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

    by_conv = {a["conv_id"]: a for a in agents}
    siblings_by_parent: Dict[str, List[Dict[str, Any]]] = {}
    for a in agents:
        pid = a["parent_id"]
        if pid and pid in by_conv:
            by_conv[pid]["children_count"] += 1
            siblings_by_parent.setdefault(pid, []).append(a)
            a["parent_name"] = by_conv[pid]["name"]

    # Detect sibling parallelism (ignoring tiny <=3s handoff overlaps)
    for pid, sibs in siblings_by_parent.items():
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
            a_s = a.get("wall_start_ms")
            a_e = a.get("wall_end_ms")
            if a_s is None or a_e is None:
                continue
            for j, b in enumerate(sibs):
                if i == j:
                    continue
                b_s = b.get("wall_start_ms")
                b_e = b.get("wall_end_ms")
                if b_s is None or b_e is None:
                    continue
                overlap_s = (min(a_e, b_e) - max(a_s, b_s)) / 1000.0
                if overlap_s > HANDOFF_OVERLAP_TOLERANCE_S:
                    a["mode"] = "parallel"
                    break

    agents = _tree_order_agents(agents, root_id)

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
    worker_turn_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in agents
        if a["tier"] == 3 or (a["tier"] == 2 and a["children_count"] == 0)
        for t in a["turns"]
    ]

    active_wall_s = total_merged_duration(all_turn_intervals)
    subagent_active_wall_s = total_merged_duration(subagent_turn_intervals)
    subagent_cumulative_s = sum(a["active_duration_s"] for a in agents if a["depth"] > 0)
    worker_active_wall_s = total_merged_duration(worker_turn_intervals)
    worker_cumulative_s = sum(
        a["active_duration_s"] for a in agents
        if a["tier"] == 3 or (a["tier"] == 2 and a["children_count"] == 0)
    )
    speedup = round(worker_cumulative_s / worker_active_wall_s, 2) if worker_active_wall_s > 0 else 1.0
    peak_conc = compute_boost_worker_concurrency(agents)

    gantt = compute_gantt_layout(agents)
    root_agent = by_conv[root_id]
    routine = "delegation" if any(a["depth"] > 0 for a in agents) else "solo"
    delegates = []
    for a in agents:
        if a["tier"] == 2 and a["name"] not in delegates:
            delegates.append(a["name"])
    models_used: List[str] = []
    for a in agents:
        for part in [p.strip() for p in str(a.get("model") or "").split(",") if p.strip()]:
            if part not in models_used:
                models_used.append(part)

    total_tokens = {
        "input": sum(a["tokens"]["input"] for a in agents),
        "cache_read": sum(a["tokens"]["cache_read"] for a in agents),
        "output": sum(a["tokens"]["output"] for a in agents),
        "total": sum(a["tokens"]["total"] for a in agents),
    }

    prompt_preview = re.sub(r"\s+", " ", inv.get("prompt") or "").strip()
    if len(prompt_preview) > 220:
        prompt_preview = prompt_preview[:217].rstrip() + "..."

    return {
        "invocation_index": inv_index,
        "total_invocations": total_invocations,
        "routine": routine,
        "delegates": delegates,
        "prompt": inv.get("prompt") or "",
        "prompt_preview": prompt_preview or "(no prompt recorded)",
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
            "worker_active_wall_s": round(worker_active_wall_s, 3),
            "worker_active_wall_label": format_duration(worker_active_wall_s),
            "worker_cumulative_s": round(worker_cumulative_s, 3),
            "worker_cumulative_label": format_duration(worker_cumulative_s),
            "parallelism_speedup": speedup,
            "peak_concurrency": peak_conc,
            "total_agents": len(agents),
            "subagent_count": sum(1 for a in agents if a["depth"] > 0),
            "tier1_count": sum(1 for a in agents if a["tier"] == 1),
            "tier2_count": sum(1 for a in agents if a["tier"] == 2),
            "tier3_count": sum(1 for a in agents if a["tier"] == 3),
            "parallel_agents": sum(1 for a in agents if a["mode"] == "parallel"),
            "max_depth": max((a["depth"] for a in agents), default=0),
            "total_steps": sum(a["step_count"] for a in agents),
            "total_tool_calls": sum(a["tool_call_count"] for a in agents),
            "report_count": sum(len(a["reports"]) for a in agents),
            "models_used": models_used,
            "tokens": total_tokens,
        },
        "gantt": gantt,
        "agents": agents,
    }


def _rollup_session_summary(pipelines: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute top-level summary across one or more /boost pipelines."""
    if len(pipelines) == 1:
        return dict(pipelines[0]["summary"])

    all_agents = [a for p in pipelines for a in p["agents"]]
    all_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in all_agents
        for t in a["turns"]
    ]
    sub_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in all_agents if a["depth"] > 0
        for t in a["turns"]
    ]
    worker_intervals = [
        (t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in all_agents
        if a["tier"] == 3 or (a["tier"] == 2 and a["children_count"] == 0)
        for t in a["turns"]
    ]
    starts = [a["wall_start_ms"] for a in all_agents if a["wall_start_ms"] is not None]
    ends = [a["wall_end_ms"] for a in all_agents if a["wall_end_ms"] is not None]
    span_s = max(0.0, (max(ends) - min(starts)) / 1000.0) if (starts and ends) else 0.0
    start_dt = datetime.fromtimestamp(min(starts) / 1000.0, tz=timezone.utc) if starts else None
    end_dt = datetime.fromtimestamp(max(ends) / 1000.0, tz=timezone.utc) if ends else None

    active_wall_s = total_merged_duration(all_intervals)
    sub_active_s = total_merged_duration(sub_intervals)
    sub_cum_s = sum(a["active_duration_s"] for a in all_agents if a["depth"] > 0)
    worker_active_s = total_merged_duration(worker_intervals)
    worker_cum_s = sum(
        a["active_duration_s"] for a in all_agents
        if a["tier"] == 3 or (a["tier"] == 2 and a["children_count"] == 0)
    )
    speedup = round(worker_cum_s / worker_active_s, 2) if worker_active_s > 0 else 1.0
    models_used: List[str] = []
    for p in pipelines:
        for m in p["summary"].get("models_used") or []:
            if m not in models_used:
                models_used.append(m)

    return {
        "wall_start_local": format_local_clock(start_dt, include_date=True),
        "wall_end_local": format_local_clock(end_dt, include_date=True),
        "wall_span_s": round(span_s, 3),
        "wall_span_label": format_duration(span_s),
        "active_wall_s": round(active_wall_s, 3),
        "active_wall_label": format_duration(active_wall_s),
        "subagent_active_wall_s": round(sub_active_s, 3),
        "subagent_active_wall_label": format_duration(sub_active_s),
        "subagent_cumulative_s": round(sub_cum_s, 3),
        "subagent_cumulative_label": format_duration(sub_cum_s),
        "worker_active_wall_s": round(worker_active_s, 3),
        "worker_active_wall_label": format_duration(worker_active_s),
        "worker_cumulative_s": round(worker_cum_s, 3),
        "worker_cumulative_label": format_duration(worker_cum_s),
        "parallelism_speedup": speedup,
        "peak_concurrency": max((p["summary"]["peak_concurrency"] for p in pipelines), default=1),
        "total_agents": len(all_agents),
        "subagent_count": sum(1 for a in all_agents if a["depth"] > 0),
        "tier1_count": sum(1 for a in all_agents if a["tier"] == 1),
        "tier2_count": sum(1 for a in all_agents if a["tier"] == 2),
        "tier3_count": sum(1 for a in all_agents if a["tier"] == 3),
        "parallel_agents": sum(1 for a in all_agents if a["mode"] == "parallel"),
        "max_depth": max((a["depth"] for a in all_agents), default=0),
        "total_steps": sum(a["step_count"] for a in all_agents),
        "total_tool_calls": sum(a["tool_call_count"] for a in all_agents),
        "report_count": sum(len(a["reports"]) for a in all_agents),
        "models_used": models_used,
        "tokens": {
            "input": sum(a["tokens"]["input"] for a in all_agents),
            "cache_read": sum(a["tokens"]["cache_read"] for a in all_agents),
            "output": sum(a["tokens"]["output"] for a in all_agents),
            "total": sum(a["tokens"]["total"] for a in all_agents),
        },
    }


def parse_boost_run(
    agy_dir: str,
    root_id: str,
    workspace_root: str,
    all_invocations: bool = False,
) -> Dict[str, Any]:
    """Parse a root AGY conversation into a /boost 3-tier trajectory payload."""
    by_id, children_by_parent = _load_db_metadata(agy_dir)
    root_steps, root_tpath = _read_transcript(agy_dir, root_id)
    has_boost_desc, _ = _has_boost_descendants(root_id, by_id, children_by_parent)

    if not root_steps and not has_boost_desc:
        raise ValueError(f"Conversation '{root_id}' has no transcript or /boost subagents under {agy_dir}")

    invocations = _segment_boost_invocations(root_id, root_steps, by_id, children_by_parent)
    if not invocations:
        raise ValueError(f"Conversation '{root_id}' contains no /boost invocations.")

    total_invocations = len(invocations)
    if all_invocations:
        selected_pairs = list(enumerate(invocations, start=1))
    else:
        selected_pairs = [(total_invocations, invocations[-1])]

    pipelines = [
        _build_invocation_payload(
            agy_dir=agy_dir,
            root_id=root_id,
            workspace_root=workspace_root,
            inv=inv,
            inv_index=idx,
            total_invocations=total_invocations,
            by_id=by_id,
            children_by_parent=children_by_parent,
        )
        for idx, inv in selected_pairs
    ]

    root_title = (by_id.get(root_id) or {}).get("title") or "/boost Execution Trajectory"
    routines_present = sorted({p["routine"] for p in pipelines})
    session_routine = (
        "mixed" if len(routines_present) > 1
        else (routines_present[0] if routines_present else "solo")
    )

    return {
        "source": "agy-boost",
        "tz_label": get_local_tz_label(),
        "workspace_root": workspace_root,
        "root_conversation_id": root_id,
        "root_transcript_uri": f"file://{root_tpath}" if root_tpath else "",
        "run_title": root_title,
        "scope_mode": "all" if all_invocations else "latest",
        "session_routine": session_routine,
        "total_boost_invocations": total_invocations,
        "selected_invocation_indices": [idx for idx, _ in selected_pairs],
        "summary": _rollup_session_summary(pipelines),
        "pipelines": pipelines,
    }
