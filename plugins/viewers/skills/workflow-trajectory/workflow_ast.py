#!/usr/bin/env python3
"""Static AST analyzer for AGY dynamic `run_workflow` Python scripts and workflow.json manifests."""

from __future__ import annotations

import ast
import io
import json
import os
import re
import tokenize
from typing import Any, Dict, List, Optional, Set, Tuple


_SKILL_PATH_RE = re.compile(r"(?:^|[/\\])skills[/\\]([a-zA-Z0-9._-]+)[/\\]SKILL\.md", re.I)
_SKILL_LOAD_RE = re.compile(
    r"(?:\bload\s+(?:the\s+)?|use\s+(?:the\s+)?|follow\s+(?:the\s+)?|read\s+(?:the\s+)?)"
    r"[`'\"]?([a-z][a-z0-9_-]{1,40})[`'\"]?\s+skill\b",
    re.I,
)
_SLASH_SKILL_RE = re.compile(r"(?:^|\s)/([a-z][a-z0-9_-]{2,40})(?:\b|$)")
_EDIT_HINT_RE = re.compile(
    r"\b(fix|edit|write|implement|refactor|modify|patch|create|update|migrate|delete)\b",
    re.I,
)
_NEGATED_EDIT_RE = re.compile(
    r"\b(?:do\s+not|don't|never|read[- ]only|without)\s+(?:make\s+any\s+)?(?:fix|edit|write|implement|refactor|modify|patch|create|update|migrate|delete|change)",
    re.I,
)
_READ_ONLY_TYPES = frozenset(
    {
        "research",
        "architect",
        "visual-architect",
        "auditor",
        "agent-architect",
        "agent-verifier",
        "plan-validator",
        "spec-validator",
        "implementation-validator",
    }
)
_VERIFY_HINT_RE = re.compile(
    r"\b(verif\w*|audit\w*|validat\w*|review\w*|check\w*|test\w*|qa|lint\w*|skeptic\w*)\b",
    re.I,
)


def _wrap_for_top_level_await(source: str) -> str:
    """Wrap script lines inside an async def so stdlib ast.parse supports top-level await.

    Preserves 1-based line offsets (node.lineno - 1 == original lineno) while avoiding
    corrupting multiline string tokens when indenting.
    """
    lines = source.splitlines(keepends=True)
    if not lines:
        return "async def __workflow_entry__():\n    pass\n"

    # Identify lines that are continuations inside multiline strings so we do not
    # inject leading spaces inside string literals.
    no_indent_lines: Set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.STRING and tok.start[0] < tok.end[0]:
                for ln in range(tok.start[0] + 1, tok.end[0] + 1):
                    no_indent_lines.add(ln)
    except (tokenize.TokenError, IndentationError):
        pass

    out = ["async def __workflow_entry__():\n"]
    for idx, line in enumerate(lines, start=1):
        if idx in no_indent_lines or not line.strip():
            out.append(line if line.endswith("\n") else line + "\n")
        else:
            out.append("    " + (line if line.endswith("\n") else line + "\n"))
    return "".join(out)


def parse_workflow_ast(source: str) -> Tuple[Optional[ast.Module], int, Optional[str]]:
    """Parse a workflow script (handling top-level await).

    Returns (ast_module, line_offset, parse_error).
    Original 1-based line number = node.lineno - line_offset.
    """
    if not source or not source.strip():
        return None, 0, None
    try:
        return ast.parse(source), 0, None
    except SyntaxError:
        pass
    try:
        wrapped = _wrap_for_top_level_await(source)
        return ast.parse(wrapped), 1, None
    except SyntaxError as exc:
        line_no = max(1, (exc.lineno or 1) - 1)
        return None, 0, f"SyntaxError at line {line_no}: {exc.msg}"


def _const_str(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: List[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                try:
                    parts.append("{" + ast.unparse(v.value) + "}")
                except Exception:
                    parts.append("{...}")
        return "".join(parts)
    return None


def _safe_unparse(node: Optional[ast.AST], max_len: int = 120) -> str:
    if node is None:
        return ""
    try:
        txt = ast.unparse(node)
    except Exception:
        return ""
    if len(txt) > max_len:
        return txt[: max_len - 1] + "…"
    return txt


def _summarize_schema(node: Optional[ast.AST]) -> Dict[str, Any]:
    if node is None:
        return {"type": "unknown", "fields": [], "raw": ""}
    raw = _safe_unparse(node, max_len=240)
    try:
        val = ast.literal_eval(node)
    except Exception:
        return {"type": "dynamic", "fields": [], "raw": raw}
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except Exception:
            return {"type": "string_schema", "fields": [], "raw": val[:240]}
    if isinstance(val, dict):
        stype = str(val.get("type") or "object")
        props = val.get("properties")
        fields = list(props.keys()) if isinstance(props, dict) else []
        req = val.get("required") if isinstance(val.get("required"), list) else []
        return {"type": stype, "fields": fields, "required": req, "raw": json.dumps(val)}
    return {"type": type(val).__name__, "fields": [], "raw": raw}


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _extract_agent_kwargs(call: ast.Call) -> Dict[str, Any]:
    """Extract positional & keyword arguments for `agent(...)`."""
    # Signature: agent(prompt=None, schema=None, role=None, type_name="self", workspace="inherit", model=None)
    pos_names = ["prompt", "schema", "role", "type_name", "workspace", "model"]
    kw: Dict[str, ast.AST] = {}
    for idx, arg in enumerate(call.args):
        if idx < len(pos_names):
            kw[pos_names[idx]] = arg
    for k in call.keywords:
        if k.arg:
            kw[k.arg] = k.value

    prompt_val = _const_str(kw.get("prompt")) or _safe_unparse(kw.get("prompt"), 220)
    role_val = _const_str(kw.get("role")) or _safe_unparse(kw.get("role"), 80)
    type_val = _const_str(kw.get("type_name")) or _safe_unparse(kw.get("type_name"), 40) or "self"
    ws_val = _const_str(kw.get("workspace")) or _safe_unparse(kw.get("workspace"), 40) or "inherit"
    model_val = _const_str(kw.get("model")) or _safe_unparse(kw.get("model"), 40) or "inherit"
    schema_info = _summarize_schema(kw.get("schema"))

    return {
        "prompt_preview": (prompt_val or "").strip()[:260],
        "role": (role_val or "").strip(),
        "type_name": type_val.strip() or "self",
        "workspace": ws_val.strip() or "inherit",
        "model": model_val.strip() or "inherit",
        "schema": schema_info,
    }


def _extract_skills_from_text(text: str) -> List[str]:
    found: Set[str] = set()
    if not text:
        return []
    for m in _SKILL_PATH_RE.finditer(text):
        found.add(m.group(1).strip())
    for m in _SKILL_LOAD_RE.finditer(text):
        cand = m.group(1).strip()
        if cand.lower() not in {"a", "an", "the", "this", "that", "your", "any"}:
            found.add(cand)
    for m in _SLASH_SKILL_RE.finditer(text):
        cand = m.group(1).strip()
        # Ignore common file paths like /usr, /tmp, /bin, /etc, /var, /api
        if cand.lower() not in {
            "usr", "tmp", "bin", "etc", "var", "opt", "home", "users", "dev", "api", "src", "app", "lib"
        } and "-" in cand:
            found.add(cand)
    return sorted(found)


def load_workflow_manifest(script_path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Load sibling `workflow.json` if `script_path` belongs to a saved workflow directory."""
    if not script_path:
        return None
    parent = os.path.dirname(os.path.abspath(script_path))
    cand = os.path.join(parent, "workflow.json")
    if not os.path.isfile(cand):
        return None
    try:
        with open(cand, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data["_manifest_path"] = cand
            return data
    except Exception:
        return None
    return None


def analyze_workflow_script(
    source: str,
    script_path: Optional[str] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Statically analyze a `run_workflow` Python script into a structured blueprint."""
    if manifest is None:
        manifest = load_workflow_manifest(script_path)

    tree, line_offset, parse_error = parse_workflow_ast(source)
    lines = source.splitlines() if source else []

    if tree is None:
        return {
            "available": bool(source.strip()),
            "script_path": script_path or "",
            "line_count": len(lines),
            "parse_error": parse_error,
            "manifest": manifest,
            "imports": [],
            "helpers": [],
            "args_keys": [],
            "phases": [],
            "agents": [],
            "tools": [],
            "trajectory_calls": [],
            "skills_declared": [],
            "warnings": (
                [{"severity": "error", "code": "syntax_error", "message": parse_error, "line": 1}]
                if parse_error
                else []
            ),
            "counts": {
                "phases": 0,
                "agents": 0,
                "parallel_blocks": 0,
                "pipeline_blocks": 0,
                "tool_calls": 0,
                "trajectory_calls": 0,
                "helpers": 0,
            },
        }

    # Unwrap synthetic entry function if we wrapped top-level await.
    if line_offset == 1 and tree.body and isinstance(tree.body[0], ast.AsyncFunctionDef):
        entry_body = tree.body[0].body
    else:
        entry_body = tree.body

    def orig_line(node: ast.AST) -> int:
        return max(1, (getattr(node, "lineno", 1) or 1) - line_offset)

    imports: List[str] = []
    helpers: List[Dict[str, Any]] = []
    args_keys: Set[str] = set()
    skills_declared: Set[str] = set()
    tools_declared: List[Dict[str, Any]] = []
    trajectory_calls: List[Dict[str, Any]] = []
    agent_defs: List[Dict[str, Any]] = []
    agent_vars: Dict[str, Dict[str, Any]] = {}
    awaited_agent_ids: Set[int] = set()
    called_agent_vars: Set[str] = set()

    parallel_count = 0
    pipeline_count = 0

    phases: List[Dict[str, Any]] = []
    current_phase: Dict[str, Any] = {
        "index": 0,
        "name": "(Setup / Top-Level)",
        "explicit": False,
        "line": 1,
        "steps": [],
    }
    phases.append(current_phase)

    def ensure_phase(name: str, lineno: int) -> Dict[str, Any]:
        nonlocal current_phase
        # If initial implicit phase has no steps yet, replace it cleanly.
        if len(phases) == 1 and not phases[0]["explicit"] and not phases[0]["steps"]:
            phases[0]["name"] = name
            phases[0]["explicit"] = True
            phases[0]["line"] = lineno
            current_phase = phases[0]
            return current_phase
        ph = {
            "index": len(phases),
            "name": name,
            "explicit": True,
            "line": lineno,
            "steps": [],
        }
        phases.append(ph)
        current_phase = ph
        return ph

    # First pass across whole AST for args keys, imports, and prompt skill mentions.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = ", ".join(a.name for a in node.names)
            imports.append(f"{mod}: {names}" if mod else names)
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "args"
                and node.func.attr == "get"
                and node.args
            ):
                k = _const_str(node.args[0])
                if k:
                    args_keys.add(k)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "args":
                k = _const_str(node.slice)
                if k:
                    args_keys.add(k)

    # Helper lookup for async def functions defined in the script
    helper_nodes: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for stmt in entry_body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            helper_nodes[stmt.name] = stmt
            helpers.append(
                {
                    "name": stmt.name,
                    "is_async": isinstance(stmt, ast.AsyncFunctionDef),
                    "args": [a.arg for a in stmt.args.args],
                    "line": orig_line(stmt),
                }
            )

    def register_agent(
        call: ast.Call,
        mode: str,
        var_name: Optional[str] = None,
        is_awaited: bool = False,
        target_phase: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        info = _extract_agent_kwargs(call)
        lineno = orig_line(call)
        aid = len(agent_defs) + 1
        rec = {
            "id": f"agent_{aid}",
            "line": lineno,
            "phase": (target_phase or current_phase)["name"],
            "mode": mode,  # single | parallel | pipeline | stateful
            "var_name": var_name or "",
            "role": info["role"] or f"Agent #{aid}",
            "has_explicit_role": bool(info["role"]),
            "type_name": info["type_name"],
            "model": info["model"],
            "workspace": info["workspace"],
            "schema": info["schema"],
            "prompt_preview": info["prompt_preview"],
            "turn_calls": 0,
            "is_awaited": is_awaited,
        }
        agent_defs.append(rec)
        if is_awaited:
            awaited_agent_ids.add(aid)
        if var_name:
            agent_vars[var_name] = rec
        for sk in _extract_skills_from_text(info["prompt_preview"]):
            skills_declared.add(sk)
        if info["type_name"] and info["type_name"] != "self":
            skills_declared.add(f"agent:{info['type_name']}")
        return rec

    def inspect_expr(
        node: ast.AST,
        mode_context: str = "single",
        is_awaited: bool = False,
        assigned_var: Optional[str] = None,
        visited_helpers: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Recursively inspect an expression and return structured step items."""
        nonlocal parallel_count, pipeline_count
        if visited_helpers is None:
            visited_helpers = set()
        items: List[Dict[str, Any]] = []

        if isinstance(node, ast.Await):
            return inspect_expr(
                node.value,
                mode_context=mode_context,
                is_awaited=True,
                assigned_var=assigned_var,
                visited_helpers=visited_helpers,
            )

        if isinstance(node, ast.Call):
            cname = _call_name(node)
            lineno = orig_line(node)

            if cname == "phase" and node.args:
                pname = _const_str(node.args[0]) or _safe_unparse(node.args[0], 60) or "Phase"
                ensure_phase(pname, lineno)
                return []

            if cname in ("parallel", "pipeline"):
                if cname == "parallel":
                    parallel_count += 1
                else:
                    pipeline_count += 1
                items_expr = _safe_unparse(node.args[0], 80) if node.args else ""
                children: List[Dict[str, Any]] = []
                if len(node.args) >= 2:
                    fn_arg = node.args[1]
                    if isinstance(fn_arg, ast.Lambda):
                        children = inspect_expr(
                            fn_arg.body,
                            mode_context=cname,
                            is_awaited=True,
                            visited_helpers=visited_helpers,
                        )
                    elif isinstance(fn_arg, ast.Name) and fn_arg.id in helper_nodes and fn_arg.id not in visited_helpers:
                        hnode = helper_nodes[fn_arg.id]
                        for hstmt in hnode.body:
                            children.extend(
                                inspect_stmt(
                                    hstmt,
                                    mode_context=cname,
                                    append_to_phase=False,
                                    visited_helpers=visited_helpers | {fn_arg.id},
                                )
                            )
                step_item = {
                    "kind": cname,
                    "line": lineno,
                    "items_expr": items_expr,
                    "children": children,
                }
                items.append(step_item)
                return items

            if cname == "agent":
                mode = "stateful" if (assigned_var and not is_awaited) else mode_context
                rec = register_agent(
                    node,
                    mode=mode,
                    var_name=assigned_var,
                    is_awaited=is_awaited,
                )
                items.append(
                    {
                        "kind": "agent",
                        "line": lineno,
                        "agent_id": rec["id"],
                        "role": rec["role"],
                        "type_name": rec["type_name"],
                        "model": rec["model"],
                        "workspace": rec["workspace"],
                        "mode": rec["mode"],
                        "schema_type": rec["schema"]["type"],
                    }
                )
                return items

            if isinstance(node.func, ast.Name) and node.func.id in agent_vars:
                vname = node.func.id
                rec = agent_vars[vname]
                rec["turn_calls"] += 1
                rec["is_awaited"] = rec["is_awaited"] or is_awaited
                called_agent_vars.add(vname)
                prompt_val = ""
                if node.args:
                    prompt_val = _const_str(node.args[0]) or _safe_unparse(node.args[0], 180)
                for sk in _extract_skills_from_text(prompt_val):
                    skills_declared.add(sk)
                items.append(
                    {
                        "kind": "agent_turn",
                        "line": lineno,
                        "agent_id": rec["id"],
                        "role": rec["role"],
                        "type_name": rec["type_name"],
                        "model": rec["model"],
                        "turn_number": rec["turn_calls"],
                        "prompt_preview": prompt_val[:180],
                    }
                )
                return items

            if cname == "call_tool":
                tname = (
                    _const_str(node.args[0])
                    if node.args
                    else _const_str(next((k.value for k in node.keywords if k.arg == "name"), None))
                ) or "dynamic_tool"
                arg_keys = [k.arg for k in node.keywords if k.arg and k.arg != "name"]
                trec = {
                    "name": tname,
                    "line": lineno,
                    "phase": current_phase["name"],
                    "mode": mode_context,
                    "arg_keys": arg_keys,
                }
                tools_declared.append(trec)
                items.append({"kind": "call_tool", "line": lineno, "tool": tname, "arg_keys": arg_keys})
                return items

            if cname == "trajectory":
                filter_tools: List[str] = []
                for k in node.keywords:
                    if k.arg == "tools":
                        try:
                            val = ast.literal_eval(k.value)
                            if isinstance(val, (list, tuple)):
                                filter_tools = [str(x) for x in val]
                        except Exception:
                            pass
                tcall = {
                    "line": lineno,
                    "phase": current_phase["name"],
                    "tools": filter_tools,
                    "raw": _safe_unparse(node, 140),
                }
                trajectory_calls.append(tcall)
                items.append({"kind": "trajectory", "line": lineno, "tools": filter_tools})
                return items

            if cname in helper_nodes and cname not in visited_helpers:
                hnode = helper_nodes[cname]
                for hstmt in hnode.body:
                    items.extend(
                        inspect_stmt(
                            hstmt,
                            mode_context=mode_context,
                            append_to_phase=False,
                            visited_helpers=visited_helpers | {cname},
                        )
                    )
                return items

        # Check sub-expressions (e.g., list comprehensions or ternary expressions)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Call, ast.Await)):
                items.extend(
                    inspect_expr(
                        child,
                        mode_context=mode_context,
                        is_awaited=False,
                        visited_helpers=visited_helpers,
                    )
                )
        return items

    def inspect_stmt(
        stmt: ast.stmt,
        mode_context: str = "single",
        append_to_phase: bool = True,
        visited_helpers: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        if isinstance(stmt, ast.Expr):
            collected = inspect_expr(stmt.value, mode_context=mode_context, visited_helpers=visited_helpers)
        elif isinstance(stmt, ast.Assign):
            vname = stmt.targets[0].id if (stmt.targets and isinstance(stmt.targets[0], ast.Name)) else None
            collected = inspect_expr(
                stmt.value,
                mode_context=mode_context,
                assigned_var=vname,
                visited_helpers=visited_helpers,
            )
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            vname = stmt.target.id if isinstance(stmt.target, ast.Name) else None
            collected = inspect_expr(
                stmt.value,
                mode_context=mode_context,
                assigned_var=vname,
                visited_helpers=visited_helpers,
            )
        elif isinstance(stmt, ast.Return) and stmt.value is not None:
            collected = inspect_expr(stmt.value, mode_context=mode_context, visited_helpers=visited_helpers)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.If, ast.Try)):
            sub_stmts: List[ast.stmt] = []
            for attr in ("body", "orelse", "finalbody"):
                sub = getattr(stmt, attr, None)
                if isinstance(sub, list):
                    sub_stmts.extend(sub)
            for h in getattr(stmt, "handlers", []) or []:
                sub_stmts.extend(h.body)
            for sub_s in sub_stmts:
                collected.extend(
                    inspect_stmt(
                        sub_s,
                        mode_context=mode_context,
                        append_to_phase=append_to_phase,
                        visited_helpers=visited_helpers,
                    )
                )
            return collected

        if append_to_phase and collected:
            current_phase["steps"].extend(collected)
        return collected

    for stmt in entry_body:
        inspect_stmt(stmt, mode_context="single", append_to_phase=True)

    # Pre-flight static warnings (helpful BEFORE starting a run!)
    warnings: List[Dict[str, Any]] = []
    has_verify_phase_or_agent = any(
        _VERIFY_HINT_RE.search(p["name"]) for p in phases
    ) or any(
        _VERIFY_HINT_RE.search(f"{a['role']} {a['type_name']}") for a in agent_defs
    )

    for a in agent_defs:
        if not a["is_awaited"] and a["turn_calls"] == 0:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "unawaited_agent",
                    "line": a["line"],
                    "message": f"Agent '{a['role']}' (line {a['line']}) is defined but never awaited or called — it will never run.",
                }
            )
        if (
            a["mode"] == "parallel"
            and a["workspace"] == "inherit"
            and (a.get("type_name") or "").lower() not in _READ_ONLY_TYPES
            and _EDIT_HINT_RE.search(a["prompt_preview"])
            and not _NEGATED_EDIT_RE.search(a["prompt_preview"])
        ):
            warnings.append(
                {
                    "severity": "warning",
                    "code": "parallel_inherit_write",
                    "line": a["line"],
                    "message": (
                        f"Parallel agent '{a['role']}' (line {a['line']}) uses workspace='inherit' with an edit-like prompt; "
                        "consider workspace='branch' or 'share' to avoid concurrent edit collisions."
                    ),
                }
            )
        if not a["has_explicit_role"]:
            warnings.append(
                {
                    "severity": "info",
                    "code": "missing_role",
                    "line": a["line"],
                    "message": f"Agent on line {a['line']} has no explicit role=; setting role= makes cards and reports clearer.",
                }
            )
        if a["mode"] == "parallel" and a["model"] == "inherit":
            warnings.append(
                {
                    "severity": "info",
                    "code": "parallel_default_model",
                    "line": a["line"],
                    "message": (
                        f"Parallel fan-out '{a['role']}' (line {a['line']}) inherits the parent model; "
                        "for simple high-fan-out tasks, model='flash' or 'flash_lite' lowers latency and token cost."
                    ),
                }
            )

    if agent_defs and not has_verify_phase_or_agent:
        warnings.append(
            {
                "severity": "info",
                "code": "no_verify_stage",
                "line": 1,
                "message": "No explicit verification/audit phase or verifier agent detected in the script.",
            }
        )

    # Deduplicate identical warnings emitted when a helper is expanded from multiple call sites.
    dedup_warnings: List[Dict[str, Any]] = []
    seen_warnings: Set[Tuple[str, int, str]] = set()
    for w in warnings:
        key = (w["code"], int(w.get("line") or 0), w["message"])
        if key not in seen_warnings:
            seen_warnings.add(key)
            dedup_warnings.append(w)
    warnings = dedup_warnings

    # Filter out empty implicit setup phase if explicit phases exist
    clean_phases = [
        p for p in phases if p["explicit"] or p["steps"] or len(phases) == 1
    ]

    return {
        "available": True,
        "script_path": script_path or "",
        "line_count": len(lines),
        "parse_error": None,
        "manifest": manifest,
        "imports": sorted(set(imports)),
        "helpers": helpers,
        "args_keys": sorted(args_keys),
        "phases": clean_phases,
        "agents": agent_defs,
        "tools": tools_declared,
        "trajectory_calls": trajectory_calls,
        "skills_declared": sorted(skills_declared),
        "warnings": warnings,
        "counts": {
            "phases": len([p for p in clean_phases if p["explicit"]]) or len(clean_phases),
            "agents": len(agent_defs),
            "parallel_blocks": parallel_count,
            "pipeline_blocks": pipeline_count,
            "tool_calls": len(tools_declared),
            "trajectory_calls": len(trajectory_calls),
            "helpers": len(helpers),
        },
    }
