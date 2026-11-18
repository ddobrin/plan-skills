#!/usr/bin/env python3
"""Telemetry discovery and parsing for native AGY /swarm runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urlparse

from swarm_timeline import (
    compute_gantt_layout,
    compute_worker_concurrency,
    format_duration,
    format_local_clock,
    get_local_tz_label,
    parse_iso_timestamp,
    segment_swarm_turns,
    total_merged_duration,
)


WRITE_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}

ROLE_CATEGORY_LABELS = {
    "coordinator": "Coordinator",
    "research_plan": "Research & Architecture",
    "author": "Implementation",
    "verifier": "Verification",
    "monitor": "Monitor",
    "narrator": "Narrator",
}

_NAME_RUNE_RE = re.compile(r"[\w-]", re.UNICODE)


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
    """Score how closely workspace_uris matches workspace_root (3=exact, 2=inside, 1=parent, 0=none)."""
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


def _swarm_dir(agy_dir: str, conv_id: str) -> str:
    return os.path.join(agy_dir, "brain", conv_id, ".system_generated", "swarm")


def _has_swarm_artifacts(agy_dir: str, conv_id: str) -> bool:
    sdir = _swarm_dir(agy_dir, conv_id)
    if not os.path.isdir(sdir):
        return False
    return any(
        os.path.exists(os.path.join(sdir, fname))
        for fname in ("swarm.json", "board.jsonl", "members.json")
    )


def _read_json_safe(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _read_transcript(agy_dir: str, conv_id: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    logs_dir = os.path.join(agy_dir, "brain", conv_id, ".system_generated", "logs")
    for fname in ("transcript_full.jsonl", "transcript.jsonl"):
        fpath = os.path.join(logs_dir, fname)
        if os.path.exists(fpath):
            steps: List[Dict[str, Any]] = []
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            steps.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                return steps, fpath
            except OSError:
                continue
    return [], None


def _parse_board_time(raw_time: Optional[str]) -> Optional[datetime]:
    """Parse board.jsonl timestamps ('YYYY-MM-DD HH:MM:SS' local or ISO) into UTC."""
    if not raw_time or not isinstance(raw_time, str):
        return None
    text = raw_time.strip()
    if not text:
        return None
    if "T" in text or text.endswith("Z"):
        return parse_iso_timestamp(text)
    try:
        naive = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        local_dt = naive.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return local_dt.astimezone(timezone.utc)
    except ValueError:
        return parse_iso_timestamp(text)


def _extract_mentions_and_tags(text: str, member_names: Sequence[str], kind: str = "post") -> Dict[str, Any]:
    """Extract @member mentions, @all, @#channel, #seq refs, and status tags from board text."""
    lower = (text or "").lower()
    mentions: List[str] = []
    for name in member_names:
        nl = name.lower()
        if not nl:
            continue
        # Match @name or @prefix when name is <prefix>-<digits>
        candidates = [nl]
        m_pref = re.match(r"^(.+)-\d+$", nl)
        if m_pref:
            candidates.append(m_pref.group(1))
        matched = False
        for cand in candidates:
            idx = lower.find("@" + cand)
            while idx >= 0:
                before_ok = idx == 0 or not _NAME_RUNE_RE.match(lower[idx - 1])
                after_pos = idx + 1 + len(cand)
                after_ok = after_pos >= len(lower) or not _NAME_RUNE_RE.match(lower[after_pos])
                if before_ok and after_ok:
                    matched = True
                    break
                idx = lower.find("@" + cand, idx + 1)
            if matched:
                break
        if matched:
            mentions.append(name)

    has_all = bool(re.search(r"(?<![\w-])@all(?![\w-])", lower))
    channel_mentions = sorted(set(re.findall(r"(?<![\w-])@#([a-z][a-z0-9-]{0,23})(?![\w-])", lower)))
    seq_refs = [int(x) for x in re.findall(r"(?<![\w/])#(\d+)\b", text or "")]

    tags: List[str] = []
    if kind != "brief":
        # Match leading status markers after optional @mentions/@#channel prefixes
        lead = re.match(r"^\s*(?:@(?:all|#?[a-z0-9_-]+)\s+)*((?:\[(?:done|stall|quota|blocked|error|passed|failed)\]\s*)+)", lower)
        if lead:
            tags.extend(re.findall(r"\[(done|stall|quota|blocked|error|passed|failed)\]", lead.group(1)))
        for alert in ("stall", "quota", "blocked", "error"):
            if f"[{alert}]" in lower and alert not in tags:
                tags.append(alert)

    return {
        "mentions": mentions,
        "mention_all": has_all,
        "channel_mentions": channel_mentions,
        "seq_refs": sorted(set(seq_refs)),
        "tags": list(dict.fromkeys(tags)),
    }


def _read_board(agy_dir: str, root_id: str, member_names: Sequence[str]) -> List[Dict[str, Any]]:
    bpath = os.path.join(_swarm_dir(agy_dir, root_id), "board.jsonl")
    if not os.path.exists(bpath):
        return []
    posts: List[Dict[str, Any]] = []
    try:
        with open(bpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = str(raw.get("text") or "")
                kind = str(raw.get("kind") or "post")
                dt = _parse_board_time(raw.get("time"))
                meta = _extract_mentions_and_tags(text, member_names, kind=kind)
                posts.append({
                    "seq": int(raw.get("seq") or len(posts) + 1),
                    "agent": str(raw.get("agent") or ""),
                    "text": text,
                    "time": str(raw.get("time") or ""),
                    "ts_iso": dt.isoformat().replace("+00:00", "Z") if dt else "",
                    "ts_local": format_local_clock(dt) if dt else str(raw.get("time") or ""),
                    "ts_ms": int(dt.timestamp() * 1000) if dt else None,
                    "kind": kind,
                    "channel": str(raw.get("channel") or "main"),
                    "control": raw.get("control"),
                    "mentions": meta["mentions"],
                    "mention_all": meta["mention_all"],
                    "channel_mentions": meta["channel_mentions"],
                    "seq_refs": meta["seq_refs"],
                    "tags": meta["tags"],
                })
    except OSError:
        return []
    posts.sort(key=lambda p: p["seq"])
    return posts


def list_swarm_runs(agy_dir: str, workspace_root: str) -> List[Dict[str, Any]]:
    """List native /swarm runs matching workspace_root, newest first."""
    by_id, children_map = _load_db_metadata(agy_dir)
    runs: List[Dict[str, Any]] = []
    seen_roots: Set[str] = set()

    for cid, meta in by_id.items():
        if meta["parent_id"]:
            continue
        score = _match_workspace_score(meta["workspace_uris"], workspace_root)
        if score <= 0:
            continue
        if not _has_swarm_artifacts(agy_dir, cid):
            continue
        seen_roots.add(cid)
        sdir = _swarm_dir(agy_dir, cid)
        members_data = _read_json_safe(os.path.join(sdir, "members.json")) or {}
        members_map = members_data.get("members") or {}
        member_names = list(members_map.keys())
        board = _read_board(agy_dir, cid, member_names)
        title = str(members_data.get("title") or meta["title"] or "Swarm Run")
        coord_done = any(p["agent"] == "coordinator" and "done" in p["tags"] for p in board)
        verifier_done = any(
            ("verifier" in p["agent"].lower() or "auditor" in p["agent"].lower()) and "done" in p["tags"]
            for p in board
        )
        runs.append({
            "conversation_id": cid,
            "title": title,
            "score": score,
            "member_count": len(members_map) or (1 + len(children_map.get(cid, []))),
            "board_count": len(board),
            "step_count": meta["db_step_count"],
            "last_modified_time": meta["last_modified_time"],
            "completed": coord_done,
            "verified": verifier_done,
        })

    # Fallback: check brain/*/.system_generated/swarm dirs not in DB
    brain_dir = os.path.join(agy_dir, "brain")
    if os.path.isdir(brain_dir):
        for entry in os.listdir(brain_dir):
            if entry in seen_roots or not _has_swarm_artifacts(agy_dir, entry):
                continue
            if entry in by_id and by_id[entry]["parent_id"]:
                continue
            # Check if DB entry exists without matching score vs missing from DB
            if entry in by_id:
                continue
            sdir = _swarm_dir(agy_dir, entry)
            members_data = _read_json_safe(os.path.join(sdir, "members.json")) or {}
            steps, _ = _read_transcript(agy_dir, entry)
            # Match workspace_root in first few steps if DB missed it
            ws_norm = os.path.normpath(os.path.abspath(workspace_root))
            matched = any(ws_norm in str(s.get("content") or "") for s in steps[:5])
            if not matched:
                continue
            members_map = members_data.get("members") or {}
            board = _read_board(agy_dir, entry, list(members_map.keys()))
            mtime = datetime.fromtimestamp(os.path.getmtime(sdir), tz=timezone.utc).isoformat()
            runs.append({
                "conversation_id": entry,
                "title": str(members_data.get("title") or "Swarm Run"),
                "score": 2,
                "member_count": len(members_map),
                "board_count": len(board),
                "step_count": len(steps),
                "last_modified_time": mtime,
                "completed": any(p["agent"] == "coordinator" and "done" in p["tags"] for p in board),
                "verified": any("verifier" in p["agent"].lower() and "done" in p["tags"] for p in board),
            })

    runs.sort(key=lambda r: (r["score"], r["last_modified_time"]), reverse=True)
    return runs


def select_swarm_run(
    agy_dir: str,
    workspace_root: str,
    explicit_id: Optional[str] = None,
) -> Optional[str]:
    """Select a swarm root conversation ID by explicit ID/prefix or newest workspace swarm."""
    by_id, _ = _load_db_metadata(agy_dir)
    if explicit_id:
        needle = explicit_id.strip().lower()
        # Check DB conversation IDs (root or worker -> walk upward)
        matches = [cid for cid in by_id if cid.lower() == needle or cid.lower().startswith(needle)]
        # Also check brain/*/swarm dirs directly
        brain_dir = os.path.join(agy_dir, "brain")
        if os.path.isdir(brain_dir):
            for entry in os.listdir(brain_dir):
                if (entry.lower() == needle or entry.lower().startswith(needle)) and _has_swarm_artifacts(agy_dir, entry):
                    if entry not in matches:
                        matches.append(entry)
        if not matches:
            return None
        chosen = matches[0]
        seen = {chosen}
        cur = chosen
        while cur in by_id and by_id[cur]["parent_id"]:
            parent = by_id[cur]["parent_id"]
            if parent in seen:
                break
            seen.add(parent)
            cur = parent
        if _has_swarm_artifacts(agy_dir, cur):
            return cur
        # Fallback: scan members.json files if DB lacked parent link
        if os.path.isdir(brain_dir):
            for entry in os.listdir(brain_dir):
                mp = os.path.join(_swarm_dir(agy_dir, entry), "members.json")
                mdata = _read_json_safe(mp) or {}
                for mem in (mdata.get("members") or {}).values():
                    mcid = str(mem.get("conversation_id") or "")
                    if mcid.lower() == needle or mcid.lower().startswith(needle):
                        return entry
        return cur if _has_swarm_artifacts(agy_dir, cur) else None

    runs = list_swarm_runs(agy_dir, workspace_root)
    return runs[0]["conversation_id"] if runs else None


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


def _is_failed_tool_result(content: str) -> bool:
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


def _extract_produced_docs(steps: Sequence[Dict[str, Any]], workspace_root: str) -> Tuple[List[Dict[str, str]], Optional[int]]:
    """Extract created/modified file paths and the latest edit timestamp (ms)."""
    seen: Set[str] = set()
    docs: List[Dict[str, str]] = []
    latest_edit_ms: Optional[int] = None
    ws_norm = os.path.normpath(os.path.abspath(workspace_root))
    n_steps = len(steps)

    for idx, step in enumerate(steps):
        tcs = step.get("tool_calls") or []
        write_entries: List[Tuple[int, str, str, str]] = []
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
            action = "created" if tname in ("write_file", "write_to_file") else "edited"
            write_entries.append((tc_idx, raw_path, abs_path, action))

        if not write_entries:
            continue

        generic_results: List[str] = []
        j = idx + 1
        while j < n_steps and steps[j].get("type") == "GENERIC":
            generic_results.append(str(steps[j].get("content") or ""))
            j += 1

        all_failed = bool(generic_results) and all(_is_failed_tool_result(g) for g in generic_results)
        dt = parse_iso_timestamp(step.get("created_at"))
        step_ms = int(dt.timestamp() * 1000) if dt else None

        for tc_idx, raw_path, abs_path, action in write_entries:
            if generic_results:
                if len(tcs) == 1 and _is_failed_tool_result(generic_results[0]):
                    continue
                if all_failed:
                    continue
                if any(_is_failed_tool_result(g) and (abs_path in g or raw_path in g) for g in generic_results):
                    continue
                if len(generic_results) == len(tcs) and _is_failed_tool_result(generic_results[tc_idx]):
                    continue

            if step_ms is not None and (latest_edit_ms is None or step_ms > latest_edit_ms):
                latest_edit_ms = step_ms

            if abs_path in seen:
                continue
            seen.add(abs_path)
            rel = os.path.relpath(abs_path, ws_norm) if abs_path.startswith(ws_norm + os.sep) else abs_path
            docs.append({
                "name": rel,
                "action": action,
                "path": f"file://{abs_path}",
            })
    return docs, latest_edit_ms


def _extract_exit_code(text: str) -> Optional[int]:
    m = re.search(r"Command exited with code\s+(-?\d+)", text or "")
    return int(m.group(1)) if m else None


def _extract_commands(steps: Sequence[Dict[str, Any]], conv_id: str) -> List[Dict[str, Any]]:
    """Extract run_command invocations with their sync or background-task exit codes."""
    commands: List[Dict[str, Any]] = []
    bg_by_task_id: Dict[str, Dict[str, Any]] = {}
    n_steps = len(steps)

    # Pre-index background task completion SYSTEM_MESSAGEs
    task_results: Dict[str, Tuple[Optional[int], str, Optional[str]]] = {}
    for st in steps:
        if st.get("type") != "SYSTEM_MESSAGE":
            continue
        cnt = str(st.get("content") or "")
        m_tid = re.search(r'Task id "([^"]+)" finished with result:\s*(.*)', cnt, re.DOTALL)
        if m_tid:
            tid = m_tid.group(1)
            res_body = m_tid.group(2)
            task_results[tid] = (_extract_exit_code(res_body), res_body[:400], st.get("created_at"))

    for idx, step in enumerate(steps):
        if step.get("type") != "PLANNER_RESPONSE":
            continue
        tcs = step.get("tool_calls") or []
        run_entries: List[Tuple[int, str, str]] = []
        for tc_idx, tc in enumerate(tcs):
            if tc.get("name") != "run_command":
                continue
            args = tc.get("args") or tc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            cmd = _clean_arg_str(args.get("CommandLine") or "")
            summary = _clean_arg_str(args.get("toolSummary") or "")
            if cmd:
                run_entries.append((tc_idx, cmd, summary))
        if not run_entries:
            continue

        generic_results: List[str] = []
        j = idx + 1
        while j < n_steps and steps[j].get("type") == "GENERIC":
            generic_results.append(str(steps[j].get("content") or ""))
            j += 1

        dt = parse_iso_timestamp(step.get("created_at"))
        ts_ms = int(dt.timestamp() * 1000) if dt else None

        for tc_idx, cmd, summary in run_entries:
            res_text = ""
            if len(generic_results) == len(tcs):
                res_text = generic_results[tc_idx]
            elif len(run_entries) == 1 and generic_results:
                res_text = generic_results[0]

            exit_code = _extract_exit_code(res_text)
            task_id = ""
            finished_ts = step.get("created_at")
            m_bg = re.search(r"with task id:\s*([^\s\n]+)", res_text)
            if m_bg:
                task_id = m_bg.group(1).strip()
                if task_id in task_results:
                    bg_code, _, bg_ts = task_results[task_id]
                    if bg_code is not None:
                        exit_code = bg_code
                    if bg_ts:
                        finished_ts = bg_ts

            fin_dt = parse_iso_timestamp(finished_ts) or dt
            fin_ms = int(fin_dt.timestamp() * 1000) if fin_dt else ts_ms
            if exit_code is None:
                status = "background" if task_id else "unknown"
            elif exit_code == 0:
                status = "passed"
            else:
                status = "failed"

            entry = {
                "step_index": step.get("step_index"),
                "command": cmd,
                "summary": summary,
                "exit_code": exit_code,
                "status": status,
                "task_id": task_id,
                "ts_local": format_local_clock(fin_dt) if fin_dt else "",
                "ts_ms": fin_ms,
            }
            commands.append(entry)
            if task_id:
                bg_by_task_id[task_id] = entry

        # Also inspect manage_task status outputs for truncated background task results
        for tc in tcs:
            if tc.get("name") == "manage_task":
                for g in generic_results:
                    m_id = re.search(r"Task\s+([a-f0-9-]+/task-\d+)", g)
                    if m_id and m_id.group(1) in bg_by_task_id:
                        code = _extract_exit_code(g)
                        if code is not None:
                            rec = bg_by_task_id[m_id.group(1)]
                            rec["exit_code"] = code
                            rec["status"] = "passed" if code == 0 else "failed"

    return commands


def _compute_tokens_and_models(steps: Sequence[Dict[str, Any]], fallback_model: str) -> Dict[str, Any]:
    in_tok = out_tok = cache_tok = 0
    models_seen: List[str] = []
    by_model: Dict[str, Dict[str, int]] = {}

    for s in steps:
        if s.get("type") != "PLANNER_RESPONSE":
            continue
        si = int(s.get("input_tokens") or 0)
        so = int(s.get("output_tokens") or 0)
        sc = int(s.get("cache_read_tokens") or 0)
        in_tok += si
        out_tok += so
        cache_tok += sc
        m = str(s.get("model") or fallback_model or "default").strip()
        if m and m not in models_seen:
            models_seen.append(m)
        bucket = by_model.setdefault(m, {"input": 0, "output": 0, "cache_read": 0, "total": 0, "turns": 0})
        bucket["input"] += si
        bucket["output"] += so
        bucket["cache_read"] += sc
        bucket["total"] += si + so + sc
        bucket["turns"] += 1

    if not models_seen and fallback_model:
        models_seen = [fallback_model]

    total_tok = in_tok + out_tok + cache_tok
    fresh_tok = in_tok + out_tok
    denom = in_tok + cache_tok
    cache_hit_pct = round((cache_tok / denom) * 100.0, 1) if denom > 0 else 0.0

    return {
        "input": in_tok,
        "output": out_tok,
        "cache_read": cache_tok,
        "fresh": fresh_tok,
        "total": total_tok,
        "cache_hit_pct": cache_hit_pct,
        "models": models_seen,
        "primary_model": models_seen[-1] if models_seen else (fallback_model or "default"),
        "switched": len(models_seen) > 1,
        "by_model": by_model,
    }


def _summarize_tool_calls(steps: Sequence[Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
    counts: Dict[str, int] = {}
    total = 0
    for s in steps:
        for tc in s.get("tool_calls") or []:
            name = str(tc.get("name") or "unknown")
            counts[name] = counts.get(name, 0) + 1
            total += 1
    breakdown = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return total, breakdown


def _classify_role(name: str, member_role: str, brief: str) -> str:
    nl = (name or "").lower()
    rl = (member_role or "").lower()
    bl = (brief or "")[:500].lower()

    if rl == "coordinator" or nl == "coordinator":
        return "coordinator"
    if rl == "narrator" or re.match(r"^narrator(?:-\d+)?$", nl):
        return "narrator"
    if rl == "monitor" or re.match(r"^monitor(?:-\d+)?$", nl):
        return "monitor"
    if any(k in nl for k in ("verifier", "auditor", "validator", "reviewer", "qa")):
        return "verifier"
    if any(k in nl for k in ("researcher", "architect", "planner", "explorer", "investigator", "expert")):
        return "research_plan"
    if "read-only verifier" in bl or "you own verification" in bl:
        return "verifier"
    if "read-only researcher" in bl or "read-only architect" in bl or "do not edit any" in bl:
        return "research_plan"
    return "author"


def _extract_user_request(steps: Sequence[Dict[str, Any]]) -> str:
    for st in steps:
        if st.get("type") == "USER_INPUT":
            raw = str(st.get("content") or "")
            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
            txt = (m.group(1) if m else raw).strip()
            if txt:
                return txt
    return ""


def _extract_last_planner_text(steps: Sequence[Dict[str, Any]]) -> str:
    for st in reversed(steps):
        if st.get("type") == "PLANNER_RESPONSE":
            txt = str(st.get("content") or "").strip()
            if txt:
                return txt
    return ""


def _read_narrator_view(agy_dir: str, root_id: str, members_map: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sdir = _swarm_dir(agy_dir, root_id)
    v = _read_json_safe(os.path.join(sdir, "view.json"))
    if v:
        return v
    for name, m in members_map.items():
        if re.match(r"^narrator(?:-\d+)?$", name) or m.get("role") == "narrator":
            cid = m.get("conversation_id")
            if cid:
                alt = _read_json_safe(os.path.join(agy_dir, "brain", cid, "swarm_view", "view.json"))
                if alt:
                    return alt
    return None


def _collect_git_snapshot(workspace_root: str) -> Dict[str, Any]:
    """Safely capture read-only git status & diffstat if workspace_root is a git repo."""
    if not os.path.isdir(os.path.join(workspace_root, ".git")):
        return {"available": False, "modified": [], "untracked": [], "diffstat": ""}
    try:
        st_res = subprocess.run(
            ["git", "-C", workspace_root, "status", "--short"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        diff_res = subprocess.run(
            ["git", "-C", workspace_root, "diff", "--stat"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if st_res.returncode != 0:
            return {"available": False, "modified": [], "untracked": [], "diffstat": ""}
        modified: List[str] = []
        untracked: List[str] = []
        for ln in st_res.stdout.splitlines():
            if not ln.strip():
                continue
            code = ln[:2]
            path = ln[3:].strip()
            if code == "??":
                untracked.append(path)
            else:
                modified.append(ln.strip())
        return {
            "available": True,
            "modified": modified,
            "untracked": untracked,
            "diffstat": diff_res.stdout.strip() if diff_res.returncode == 0 else "",
        }
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "modified": [], "untracked": [], "diffstat": ""}


def _build_verification_audit(
    agents: Sequence[Dict[str, Any]],
    board: Sequence[Dict[str, Any]],
    last_author_edit_ms: Optional[int],
) -> Dict[str, Any]:
    """Evaluate whether the swarm result was checked, by whom, when, and with what outcome."""
    verifiers = [a for a in agents if a["role_category"] == "verifier"]
    authors = [a for a in agents if a["role_category"] in ("author", "research_plan")]

    verifier_cmds: List[Dict[str, Any]] = []
    for v in verifiers:
        for cmd in v["commands_run"]:
            verifier_cmds.append({"agent": v["name"], **cmd})

    author_check_cmds: List[Dict[str, Any]] = []
    for a in authors:
        for cmd in a["commands_run"]:
            low = cmd["command"].lower()
            if any(k in low for k in ("test", "pytest", "unittest", "adk run", "validate", "lint", "mypy", "check")):
                author_check_cmds.append({"agent": a["name"], **cmd})

    verifier_done_posts = [
        p for p in board
        if any(p["agent"] == v["name"] for v in verifiers) and "done" in p["tags"]
    ]
    verifier_last_ms: Optional[int] = None
    for v in verifiers:
        for cmd in v["commands_run"]:
            if cmd["ts_ms"] is not None and (verifier_last_ms is None or cmd["ts_ms"] > verifier_last_ms):
                verifier_last_ms = cmd["ts_ms"]
        if v["wall_end_ms"] is not None and (verifier_last_ms is None or v["wall_end_ms"] > verifier_last_ms):
            verifier_last_ms = v["wall_end_ms"]

    ordered_after_edits = True
    if last_author_edit_ms is not None and verifier_last_ms is not None:
        ordered_after_edits = verifier_last_ms >= last_author_edit_ms

    passed_v = [c for c in verifier_cmds if c["status"] == "passed"]
    failed_v = [c for c in verifier_cmds if c["status"] == "failed"]
    pending_v = [c for c in verifier_cmds if c["status"] == "background"]

    last_pass_key = max(((c.get("ts_ms") or 0, c.get("step_index") or 0) for c in passed_v), default=(-1, -1))
    unresolved_failures = [c for c in failed_v if (c.get("ts_ms") or 0, c.get("step_index") or 0) > last_pass_key]
    resolved_earlier_failures = len(failed_v) - len(unresolved_failures)

    if verifiers and verifier_done_posts:
        if unresolved_failures or (failed_v and not passed_v):
            verdict = "FAILED"
            verdict_label = "Checks Failed"
        elif not ordered_after_edits:
            verdict = "STALE"
            verdict_label = "Stale Verification (edits after last check)"
        else:
            verdict = "VERIFIED"
            verdict_label = "Verified & Passed"
    elif verifiers and failed_v:
        verdict = "FAILED"
        verdict_label = "Checks Failed"
    elif verifiers and (passed_v or pending_v):
        verdict = "PARTIAL"
        verdict_label = "Partially Checked (no verifier [done])"
    elif author_check_cmds and any(c["status"] == "passed" for c in author_check_cmds):
        verdict = "SELF_CHECKED"
        verdict_label = "Author Self-Checks Only (no verifier)"
    else:
        verdict = "UNVERIFIED"
        verdict_label = "Unverified (no checks completed)"

    latest_verifier_report = verifier_done_posts[-1]["text"] if verifier_done_posts else ""

    return {
        "verdict": verdict,
        "verdict_label": verdict_label,
        "has_verifier": bool(verifiers),
        "verifier_names": [v["name"] for v in verifiers],
        "verifier_done_count": len(verifier_done_posts),
        "ordered_after_edits": ordered_after_edits,
        "last_author_edit_local": format_local_clock(
            datetime.fromtimestamp(last_author_edit_ms / 1000.0, tz=timezone.utc)
        ) if last_author_edit_ms else "—",
        "verifier_last_local": format_local_clock(
            datetime.fromtimestamp(verifier_last_ms / 1000.0, tz=timezone.utc)
        ) if verifier_last_ms else "—",
        "passed_count": len(passed_v),
        "failed_count": len(failed_v),
        "unresolved_failure_count": len(unresolved_failures),
        "resolved_earlier_failure_count": resolved_earlier_failures,
        "pending_count": len(pending_v),
        "verifier_commands": verifier_cmds,
        "author_check_commands": author_check_cmds,
        "latest_verifier_report": latest_verifier_report,
    }


def _build_insights(
    agents: Sequence[Dict[str, Any]],
    board: Sequence[Dict[str, Any]],
    verification: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Produce concise, factual post-run diagnostic callouts from telemetry."""
    insights: List[Dict[str, str]] = []
    total_tok = summary["tokens"]["total"] or 1

    # 1. Top token consumer
    work_agents = [a for a in agents if a["role_category"] not in ("monitor", "narrator")]
    if work_agents:
        top_tok = max(work_agents, key=lambda a: a["tokens"]["total"])
        pct = round((top_tok["tokens"]["total"] / total_tok) * 100.0, 1)
        insights.append({
            "kind": "tokens",
            "title": f"Top Token Consumer: {top_tok['name']}",
            "detail": f"{pct}% of swarm tokens ({top_tok['tokens']['total']:,} total · {top_tok['tokens']['output']:,} output · {top_tok['tool_call_count']} tools).",
        })

    # 2. Biggest worker wait/sleep bottleneck (exclude coordinator, whose job is to wait)
    worker_sleepers = [a for a in agents if a["role_category"] in ("research_plan", "author", "verifier") and a["wait_duration_s"] >= 30.0]
    if worker_sleepers:
        top_sleep = max(worker_sleepers, key=lambda a: a["wait_duration_s"])
        life = max(1.0, top_sleep["active_duration_s"] + top_sleep["wait_duration_s"])
        sleep_pct = round((top_sleep["wait_duration_s"] / life) * 100.0, 1)
        insights.append({
            "kind": "timing",
            "title": f"Longest Worker Wait: {top_sleep['name']}",
            "detail": f"Parked {top_sleep['wait_duration_label']} ({sleep_pct}% of its lifespan) waiting for board handoffs vs {top_sleep['active_duration_label']} active work.",
        })

    # 3. Observer / Monitor overhead
    observers = [a for a in agents if a["role_category"] in ("monitor", "narrator")]
    if observers:
        obs_tok = sum(a["tokens"]["total"] for a in observers)
        obs_pct = round((obs_tok / total_tok) * 100.0, 1)
        stalls = sum(1 for p in board if "stall" in p["tags"])
        obs_names = ", ".join(a["name"] for a in observers)
        insights.append({
            "kind": "overhead",
            "title": f"Observer Overhead ({obs_names})",
            "detail": f"{obs_pct}% of swarm tokens ({obs_tok:,}) across {sum(len(a['turns']) for a in observers)} wakeups; {stalls} [stall] alert(s) posted.",
        })

    # 4. Delivery & verification completion
    deliverers = [a for a in agents if a["role_category"] in ("research_plan", "author", "verifier")]
    done_count = sum(1 for a in deliverers if a["lifecycle_state"] in ("completed_retired", "completed_active"))
    retired_count = sum(1 for a in deliverers if a["lifecycle_state"] == "completed_retired")
    insights.append({
        "kind": "verification" if verification["verdict"] == "VERIFIED" else "warning",
        "title": f"Delivery & Verification: {verification['verdict_label']}",
        "detail": f"{done_count}/{len(deliverers)} worker/verifier roles posted [done] ({retired_count} cleanly retired after completion).",
    })

    return insights


def parse_swarm_run(
    agy_dir: str,
    root_id: str,
    workspace_root: str,
    include_git: bool = True,
) -> Dict[str, Any]:
    """Parse a complete native /swarm run into a structured post-run telemetry payload."""
    sdir = _swarm_dir(agy_dir, root_id)
    if not _has_swarm_artifacts(agy_dir, root_id):
        raise ValueError(f"Conversation '{root_id}' has no native /swarm artifacts under {sdir}")

    by_id, _ = _load_db_metadata(agy_dir)
    swarm_meta = _read_json_safe(os.path.join(sdir, "swarm.json")) or {}
    members_data = _read_json_safe(os.path.join(sdir, "members.json")) or {}
    channels_data = _read_json_safe(os.path.join(sdir, "channels.json")) or {}
    members_map: Dict[str, Dict[str, Any]] = members_data.get("members") or {}

    # Ensure coordinator is present even on partial members.json
    if "coordinator" not in members_map:
        members_map = {
            "coordinator": {
                "conversation_id": root_id,
                "role": "coordinator",
                "killed": False,
                "model": "",
                "workspace_mode": "inherit",
            },
            **members_map,
        }

    member_names = list(members_map.keys())
    board = _read_board(agy_dir, root_id, member_names)
    narrator_view = _read_narrator_view(agy_dir, root_id, members_map)

    # Index board posts by agent and briefs targeting each agent
    posts_by_agent: Dict[str, List[Dict[str, Any]]] = {}
    brief_by_agent: Dict[str, str] = {}
    handoffs: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for p in board:
        posts_by_agent.setdefault(p["agent"], []).append(p)
        if p["kind"] == "brief":
            for m in p["mentions"]:
                brief_by_agent.setdefault(m, p["text"])
        if p["agent"] and p["mentions"]:
            for target in p["mentions"]:
                if target == p["agent"]:
                    continue
                edge = handoffs.setdefault((p["agent"], target), {"from": p["agent"], "to": target, "count": 0, "seqs": []})
                edge["count"] += 1
                edge["seqs"].append(p["seq"])

    agents: List[Dict[str, Any]] = []
    last_author_edit_ms: Optional[int] = None
    coord_steps_cache: List[Dict[str, Any]] = []

    for name, mem in members_map.items():
        cid = str(mem.get("conversation_id") or (root_id if name == "coordinator" else ""))
        db_row = by_id.get(cid) or {}
        steps, transcript_path = _read_transcript(agy_dir, cid) if cid else ([], None)
        if name == "coordinator":
            coord_steps_cache = steps

        brief = brief_by_agent.get(name, "")
        if not brief and name == "coordinator":
            brief = _extract_user_request(steps)

        role_category = _classify_role(name, str(mem.get("role") or ""), brief)

        # Spawn / start hint from board brief time or step 0
        brief_post = next((p for p in board if p["kind"] == "brief" and name in p["mentions"]), None)
        spawn_ts = parse_iso_timestamp(brief_post["ts_iso"]) if (brief_post and brief_post["ts_iso"]) else None

        turns, waits = segment_swarm_turns(steps, spawn_ts=spawn_ts)
        active_duration_s = sum(t["duration_s"] for t in turns)
        wait_duration_s = sum(w["duration_s"] for w in waits)
        swarm_wait_s = sum(w["duration_s"] for w in waits if w["reason"] == "swarm_wait")

        wall_start_dt = parse_iso_timestamp(turns[0]["start_iso"]) if turns else spawn_ts
        wall_end_dt = parse_iso_timestamp(turns[-1]["end_iso"]) if turns else parse_iso_timestamp(db_row.get("last_modified_time"))
        wall_span_s = max(0.0, (wall_end_dt - wall_start_dt).total_seconds()) if (wall_start_dt and wall_end_dt) else 0.0

        fallback_model = str(mem.get("applied_model") or mem.get("model") or mem.get("desired_model") or "")
        tokens = _compute_tokens_and_models(steps, fallback_model)
        tool_count, tool_breakdown = _summarize_tool_calls(steps)
        docs, member_edit_ms = _extract_produced_docs(steps, workspace_root)
        if role_category in ("author", "research_plan") and member_edit_ms is not None:
            if last_author_edit_ms is None or member_edit_ms > last_author_edit_ms:
                last_author_edit_ms = member_edit_ms

        commands = _extract_commands(steps, cid)
        agent_posts = posts_by_agent.get(name, [])
        done_posts = [p for p in agent_posts if "done" in p["tags"]]
        killed = bool(mem.get("killed") or db_row.get("killed"))

        if role_category == "coordinator":
            if done_posts or any(p["agent"] == "coordinator" and "done" in p["tags"] for p in board):
                lifecycle_state = "completed_active"
                lifecycle_label = "Coordinator · Done"
            elif steps:
                lifecycle_state = "active"
                lifecycle_label = "Coordinator · Active"
            else:
                lifecycle_state = "not_started"
                lifecycle_label = "Coordinator · Empty"
        elif role_category in ("monitor", "narrator"):
            lifecycle_state = "observer_retired" if killed else "observer_active"
            lifecycle_label = f"{ROLE_CATEGORY_LABELS[role_category]} · {'Retired' if killed else 'Observer'}"
        else:
            if done_posts:
                lifecycle_state = "completed_retired" if killed else "completed_active"
                lifecycle_label = "Completed · Retired" if killed else "Completed"
            elif killed:
                lifecycle_state = "killed_incomplete"
                lifecycle_label = "Killed (No [done])"
            elif steps:
                lifecycle_state = "waiting_incomplete"
                lifecycle_label = "Incomplete / Waiting"
            else:
                lifecycle_state = "not_started"
                lifecycle_label = "Never Started"

        if done_posts:
            deliverable_text = done_posts[-1]["text"]
            deliverable_seq = done_posts[-1]["seq"]
        elif agent_posts:
            non_brief = [p for p in agent_posts if p["kind"] != "brief"]
            deliverable_text = non_brief[-1]["text"] if non_brief else ""
            deliverable_seq = non_brief[-1]["seq"] if non_brief else None
        elif role_category == "coordinator":
            deliverable_text = _extract_last_planner_text(steps)
            deliverable_seq = None
        else:
            deliverable_text = _extract_last_planner_text(steps)
            deliverable_seq = None

        agents.append({
            "conv_id": cid,
            "name": name,
            "role": str(mem.get("role") or "worker"),
            "role_category": role_category,
            "role_label": ROLE_CATEGORY_LABELS.get(role_category, "Worker"),
            "killed": killed,
            "lifecycle_state": lifecycle_state,
            "lifecycle_label": lifecycle_label,
            "workspace_mode": str(mem.get("workspace_mode") or "inherit"),
            "channels": mem.get("channels") or ["main"],
            "model": tokens["primary_model"],
            "models_used": tokens["models"],
            "model_switched": tokens["switched"],
            "tokens": tokens,
            "brief": brief,
            "deliverable_text": deliverable_text,
            "deliverable_seq": deliverable_seq,
            "board_posts": agent_posts,
            "board_post_count": len(agent_posts),
            "done_count": len(done_posts),
            "docs": docs,
            "commands_run": commands,
            "step_count": max(int(db_row.get("db_step_count") or 0), len(steps)),
            "tool_call_count": tool_count,
            "tool_breakdown": tool_breakdown[:10],
            "turns": turns,
            "waits": waits,
            "active_duration_s": round(active_duration_s, 3),
            "active_duration_label": format_duration(active_duration_s),
            "wait_duration_s": round(wait_duration_s, 3),
            "wait_duration_label": format_duration(wait_duration_s),
            "swarm_wait_s": round(swarm_wait_s, 3),
            "swarm_wait_label": format_duration(swarm_wait_s),
            "wall_span_s": round(wall_span_s, 3),
            "wall_span_label": format_duration(wall_span_s),
            "wall_start_ms": int(wall_start_dt.timestamp() * 1000) if wall_start_dt else None,
            "wall_end_ms": int(wall_end_dt.timestamp() * 1000) if wall_end_dt else None,
            "wall_start_local": format_local_clock(wall_start_dt),
            "wall_end_local": format_local_clock(wall_end_dt),
            "transcript_uri": f"file://{transcript_path}" if transcript_path else "",
        })

    # Order: coordinator first, then chronological by start time
    category_order = {"coordinator": 0, "research_plan": 1, "author": 2, "verifier": 3, "narrator": 4, "monitor": 5}
    agents.sort(key=lambda a: (0 if a["role_category"] == "coordinator" else 1, a["wall_start_ms"] or 0, category_order.get(a["role_category"], 9), a["name"]))

    # Wall-clock & concurrency rollups
    all_turn_ivs = [(t["start_ms"] / 1000.0, t["end_ms"] / 1000.0) for a in agents for t in a["turns"]]
    core_agents = [a for a in agents if a["role_category"] not in ("monitor", "narrator")]
    core_turn_ivs = [(t["start_ms"] / 1000.0, t["end_ms"] / 1000.0) for a in core_agents for t in a["turns"]]
    worker_ivs = [
        (a["conv_id"], t["start_ms"] / 1000.0, t["end_ms"] / 1000.0)
        for a in agents
        if a["role_category"] in ("research_plan", "author", "verifier")
        for t in a["turns"]
    ]

    all_starts = [a["wall_start_ms"] for a in agents if a["wall_start_ms"] is not None]
    all_ends = [a["wall_end_ms"] for a in agents if a["wall_end_ms"] is not None]
    core_starts = [a["wall_start_ms"] for a in core_agents if a["wall_start_ms"] is not None]
    core_ends = [a["wall_end_ms"] for a in core_agents if a["wall_end_ms"] is not None]

    wall_start_ms = min(all_starts) if all_starts else 0
    wall_end_ms = max(all_ends) if all_ends else 0
    core_start_ms = min(core_starts) if core_starts else wall_start_ms
    core_end_ms = max(core_ends) if core_ends else wall_end_ms

    core_span_s = max(0.0, (core_end_ms - core_start_ms) / 1000.0) if core_end_ms > core_start_ms else 0.0
    full_span_s = max(0.0, (wall_end_ms - wall_start_ms) / 1000.0) if wall_end_ms > wall_start_ms else 0.0
    monitor_tail_s = max(0.0, (wall_end_ms - core_end_ms) / 1000.0) if wall_end_ms > core_end_ms else 0.0

    merged_active_s = total_merged_duration(core_turn_ivs)
    cumulative_active_s = sum(a["active_duration_s"] for a in agents)
    cumulative_worker_active_s = sum(a["active_duration_s"] for a in agents if a["role_category"] in ("research_plan", "author", "verifier"))
    cumulative_wait_s = sum(a["wait_duration_s"] for a in core_agents)
    speedup = round(cumulative_active_s / merged_active_s, 2) if merged_active_s > 0 else 1.0
    peak_worker_conc = compute_worker_concurrency(worker_ivs)

    # Token rollups
    tot_in = sum(a["tokens"]["input"] for a in agents)
    tot_out = sum(a["tokens"]["output"] for a in agents)
    tot_cache = sum(a["tokens"]["cache_read"] for a in agents)
    tot_all = tot_in + tot_out + tot_cache
    tot_fresh = tot_in + tot_out
    denom = tot_in + tot_cache
    tot_cache_pct = round((tot_cache / denom) * 100.0, 1) if denom > 0 else 0.0

    # Role rollups (Where Time & Tokens Went)
    role_rollups: List[Dict[str, Any]] = []
    for cat in ("coordinator", "research_plan", "author", "verifier", "narrator", "monitor"):
        cat_agents = [a for a in agents if a["role_category"] == cat]
        if not cat_agents:
            continue
        cat_tok = sum(a["tokens"]["total"] for a in cat_agents)
        cat_fresh = sum(a["tokens"]["fresh"] for a in cat_agents)
        cat_out = sum(a["tokens"]["output"] for a in cat_agents)
        cat_active = sum(a["active_duration_s"] for a in cat_agents)
        cat_wait = sum(a["wait_duration_s"] for a in cat_agents)
        role_rollups.append({
            "category": cat,
            "label": ROLE_CATEGORY_LABELS[cat],
            "agent_count": len(cat_agents),
            "tokens_total": cat_tok,
            "tokens_fresh": cat_fresh,
            "tokens_output": cat_out,
            "token_share_pct": round((cat_tok / tot_all) * 100.0, 1) if tot_all else 0.0,
            "active_duration_s": round(cat_active, 1),
            "active_duration_label": format_duration(cat_active),
            "wait_duration_s": round(cat_wait, 1),
            "wait_duration_label": format_duration(cat_wait),
        })

    # Per-model rollups
    model_rollup_map: Dict[str, Dict[str, Any]] = {}
    for a in agents:
        for m, mstats in a["tokens"]["by_model"].items():
            b = model_rollup_map.setdefault(m, {"model": m, "input": 0, "output": 0, "cache_read": 0, "total": 0, "agents": []})
            b["input"] += mstats["input"]
            b["output"] += mstats["output"]
            b["cache_read"] += mstats["cache_read"]
            b["total"] += mstats["total"]
            if a["name"] not in b["agents"]:
                b["agents"].append(a["name"])
    models_summary = sorted(model_rollup_map.values(), key=lambda x: -x["total"])

    # Board markers for Gantt
    board_markers = [
        {
            "seq": p["seq"],
            "agent": p["agent"],
            "kind": "done" if "done" in p["tags"] else ("stall" if "stall" in p["tags"] else p["kind"]),
            "label": f"#{p['seq']} {p['agent']}" + (" [done]" if "done" in p["tags"] else (" [stall]" if "stall" in p["tags"] else "")),
            "ts_ms": p["ts_ms"],
        }
        for p in board
        if ("done" in p["tags"] or "stall" in p["tags"] or "quota" in p["tags"])
    ]
    gantt = compute_gantt_layout(agents, board_markers=board_markers)

    verification = _build_verification_audit(agents, board, last_author_edit_ms)
    unique_files: List[Dict[str, str]] = []
    seen_files: Set[str] = set()
    for a in agents:
        for d in a["docs"]:
            if d["name"] not in seen_files:
                seen_files.add(d["name"])
                unique_files.append({**d, "by": a["name"]})

    coord_done = any(p["agent"] == "coordinator" and "done" in p["tags"] for p in board)
    run_title = str(members_data.get("title") or (by_id.get(root_id) or {}).get("title") or "Swarm Run")
    user_prompt = _extract_user_request(coord_steps_cache)

    channels_list: List[str] = ["main"]
    for p in board:
        if p["channel"] and p["channel"] not in channels_list:
            channels_list.append(p["channel"])
    for ch in (channels_data.get("channels") or []):
        cname = ch.get("name") if isinstance(ch, dict) else str(ch)
        if cname and cname not in channels_list:
            channels_list.append(cname)

    summary = {
        "outcome": "completed" if coord_done else "incomplete",
        "outcome_label": "Completed" if coord_done else "Incomplete / Stopped",
        "wall_start_local": format_local_clock(datetime.fromtimestamp(core_start_ms / 1000.0, tz=timezone.utc), include_date=True) if core_start_ms else "—",
        "wall_end_local": format_local_clock(datetime.fromtimestamp(core_end_ms / 1000.0, tz=timezone.utc)) if core_end_ms else "—",
        "core_wall_span_s": round(core_span_s, 1),
        "core_wall_span_label": format_duration(core_span_s),
        "full_wall_span_s": round(full_span_s, 1),
        "full_wall_span_label": format_duration(full_span_s),
        "monitor_tail_s": round(monitor_tail_s, 1),
        "monitor_tail_label": format_duration(monitor_tail_s) if monitor_tail_s >= 5.0 else "",
        "merged_active_s": round(merged_active_s, 1),
        "merged_active_label": format_duration(merged_active_s),
        "cumulative_active_s": round(cumulative_active_s, 1),
        "cumulative_active_label": format_duration(cumulative_active_s),
        "cumulative_worker_active_s": round(cumulative_worker_active_s, 1),
        "cumulative_worker_active_label": format_duration(cumulative_worker_active_s),
        "cumulative_wait_s": round(cumulative_wait_s, 1),
        "cumulative_wait_label": format_duration(cumulative_wait_s),
        "parallelism_speedup": speedup,
        "peak_worker_concurrency": peak_worker_conc,
        "total_agents": len(agents),
        "worker_count": sum(1 for a in agents if a["role_category"] in ("research_plan", "author", "verifier")),
        "completed_workers": sum(1 for a in agents if a["role_category"] in ("research_plan", "author", "verifier") and a["lifecycle_state"] in ("completed_retired", "completed_active")),
        "retired_workers": sum(1 for a in agents if a["lifecycle_state"] == "completed_retired"),
        "total_steps": sum(a["step_count"] for a in agents),
        "total_tool_calls": sum(a["tool_call_count"] for a in agents),
        "board_message_count": len(board),
        "done_post_count": sum(1 for p in board if "done" in p["tags"]),
        "stall_count": sum(1 for p in board if "stall" in p["tags"]),
        "quota_count": sum(1 for p in board if "quota" in p["tags"]),
        "unique_file_count": len(unique_files),
        "models_used": [m["model"] for m in models_summary],
        "tokens": {
            "input": tot_in,
            "output": tot_out,
            "cache_read": tot_cache,
            "fresh": tot_fresh,
            "total": tot_all,
            "cache_hit_pct": tot_cache_pct,
        },
    }

    insights = _build_insights(agents, board, verification, summary)
    git_snapshot = _collect_git_snapshot(workspace_root) if include_git else {"available": False, "modified": [], "untracked": [], "diffstat": ""}

    handoff_list = sorted(handoffs.values(), key=lambda h: (-h["count"], h["from"], h["to"]))

    return {
        "source": "agy-swarm",
        "tz_label": get_local_tz_label(),
        "workspace_root": workspace_root,
        "root_conversation_id": root_id,
        "run_title": run_title,
        "user_prompt": user_prompt,
        "swarm_backend": str(swarm_meta.get("backend") or "local"),
        "channels": channels_list,
        "summary": summary,
        "verification": verification,
        "role_rollups": role_rollups,
        "model_rollups": models_summary,
        "insights": insights,
        "gantt": gantt,
        "agents": agents,
        "unique_files": unique_files,
        "board": board,
        "handoffs": handoff_list,
        "narrator_view": narrator_view,
        "git_snapshot": git_snapshot,
    }
