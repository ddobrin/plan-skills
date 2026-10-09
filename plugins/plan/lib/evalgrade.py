#!/usr/bin/env python3
"""Behavioral eval helper for the plan plugin in Antigravity (standard library only).

Usage:
    evalgrade.py list    [--evals DIR]
    evalgrade.py prompt  CASE [--evals DIR]
    evalgrade.py scaffold CASE DIR [--evals DIR]
    evalgrade.py grade   CASE --repo DIR --transcript PATH [--judge CMD] [--strict] [--json] [--evals DIR]

A case is a folder under evals/:

    case.yaml      schema_version + context.scaffold_script
    scaffold.sh    builds the throwaway repository (run with bash inside DIR)
    prompt.md      front matter (name, tags, runs, max_turns, timeout_seconds, allowed_tools) + one instruction
    graders/*.md   one grader per file (front matter + optional body); every grader must pass

Run a case: `scaffold` it into an empty folder, open that folder as an Antigravity workspace,
send the `prompt` text as the first message of a new conversation, and when the agent
is done, `grade` it with that conversation's transcript
(~/.gemini/antigravity/brain/<conversation-id>/.system_generated/logs/transcript.jsonl).

Grader types:
    tool_used    tool calls whose name fully matches `tool` (a regex) and whose
                 arguments match `input_match` (a regex), counted between `min`
                 (default 1) and `max` (default unlimited). Counts calls in the
                 conversation and in every subagent it started (`scope: top` for the
                 top-level conversation only). A call the gate denied still counts:
                 the grader checks what the agent tried.
    regex        `pattern` searched in the final reply, or in a file of the repository
                 with `target: { source: file, path: ... }`.
    file_exists  `path` (a glob, relative to the repository) exists; `exists: false`
                 inverts it.
    llm          the body is a PASS/FAIL rule for a judge. With `--judge CMD` the rule
                 and the final reply are piped to CMD, which must print PASS or FAIL
                 first; without a judge the grader is reported as skipped (a failure
                 with `--strict`).

Exit status: 0 when every grader passed (skipped llm graders allowed unless --strict),
1 when one failed, 2 for usage errors.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

EVALS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals")


class CaseError(ValueError):
    pass


# --------------------------------------------------------------------------
# a small YAML subset: `key: scalar`, flow lists [a, b], flow maps { k: v }

def _split_flow(text):
    parts, depth, quote, cur = [], 0, None, []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote and (quote == "'" or len(cur) < 2 or cur[-2] != "\\"):
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def scalar(text):
    text = text.strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return json.loads(text)
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith("[") and text.endswith("]"):
        return [scalar(p) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        out = {}
        for part in _split_flow(text[1:-1]):
            key, _, value = part.partition(":")
            out[key.strip()] = scalar(value)
        return out
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if text in ("", "null", "~"):
        return None
    return text


def front_matter(text, name="file"):
    """(fields, body) for a document that starts with a --- front-matter block."""
    if not text.startswith("---"):
        raise CaseError(f"{name}: missing front matter")
    end = text.find("\n---", 3)
    if end < 0:
        raise CaseError(f"{name}: unterminated front matter")
    fields = {}
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise CaseError(f"{name}: cannot read front-matter line {line!r}")
        fields[key.strip()] = scalar(value)
    return fields, text[end + 4:].lstrip("\n")


# --------------------------------------------------------------------------
# cases

def case_dir(case, evals=EVALS):
    path = case if os.path.isdir(case) else os.path.join(evals, case)
    if not os.path.isfile(os.path.join(path, "prompt.md")):
        raise CaseError(f"no eval case at {path}")
    return path


def load_case(case, evals=EVALS):
    path = case_dir(case, evals)
    with open(os.path.join(path, "prompt.md"), encoding="utf-8") as fh:
        meta, prompt = front_matter(fh.read(), "prompt.md")
    graders = []
    for gpath in sorted(glob.glob(os.path.join(path, "graders", "*.md"))):
        with open(gpath, encoding="utf-8") as fh:
            fields, body = front_matter(fh.read(), os.path.basename(gpath))
        fields["name"] = os.path.basename(gpath)[:-3]
        fields["body"] = body.strip()
        if fields.get("type") not in ("tool_used", "regex", "file_exists", "llm"):
            raise CaseError(f"{gpath}: unknown grader type {fields.get('type')!r}")
        for key in ("tool", "input_match", "pattern"):
            if key in fields:
                try:
                    re.compile(str(fields[key]))
                except re.error as err:
                    raise CaseError(f"{gpath}: bad {key} regex: {err}") from err
        graders.append(fields)
    if not graders:
        raise CaseError(f"{path}: no graders")
    return {"path": path, "meta": meta, "prompt": prompt.strip(), "graders": graders}


def list_cases(evals=EVALS):
    out = []
    for name in sorted(os.listdir(evals)):
        if os.path.isfile(os.path.join(evals, name, "prompt.md")):
            out.append(load_case(name, evals))
    return out


def scaffold(case, dest, evals=EVALS):
    path = case_dir(case, evals)
    os.makedirs(dest, exist_ok=True)
    if os.listdir(dest):
        raise CaseError(f"{dest} is not empty")
    script = os.path.join(path, "scaffold.sh")
    proc = subprocess.run(["bash", script], cwd=dest, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CaseError(f"scaffold failed ({proc.returncode}): {proc.stderr.strip()}")
    return dest


# --------------------------------------------------------------------------
# transcripts

def read_steps(path):
    steps = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                step = json.loads(line)
            except ValueError:
                continue
            if isinstance(step, dict):
                steps.append(step)
    return steps


def _decode(value):
    """transcript.jsonl stores each argument JSON-encoded; transcript_full.jsonl does not."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def tool_calls(steps):
    for step in steps:
        for call in step.get("tool_calls") or []:
            if isinstance(call, dict):
                args = call.get("args") or {}
                args = {k: _decode(v) for k, v in args.items()} if isinstance(args, dict) else {}
                yield str(call.get("name") or ""), args


def final_reply(steps):
    """The last model text: a PLANNER_RESPONSE's content, or the last send_message to the parent."""
    for step in reversed(steps):
        if step.get("type") == "PLANNER_RESPONSE" and (step.get("content") or "").strip():
            return step["content"]
    return ""


def conversation_id(transcript):
    """brain/<id>/.system_generated/logs/transcript.jsonl → <id>."""
    parts = os.path.abspath(transcript).split(os.sep)
    return parts[-4] if len(parts) >= 4 else ""


def subagent_transcripts(transcript, _seen=None):
    """Transcripts of the conversations this one started, recursively (found by the
    `sender=<id>` of their first message)."""
    seen = _seen if _seen is not None else {os.path.abspath(transcript)}
    conv = conversation_id(transcript)
    brain = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(transcript)))))
    name = os.path.basename(transcript)
    found = []
    if not conv or not os.path.isdir(brain):
        return found
    for other in sorted(os.listdir(brain)):
        path = os.path.join(brain, other, ".system_generated", "logs", name)
        if path in seen or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                head = fh.read(16384)
        except OSError:
            continue
        if f"sender={conv}" in head:
            seen.add(path)
            found.append(path)
            found.extend(subagent_transcripts(path, seen))
    return found


# --------------------------------------------------------------------------
# graders

def _args_text(args):
    strings = [v for v in args.values() if isinstance(v, str)]
    return "\n".join(strings) + "\n" + json.dumps(args, ensure_ascii=False, sort_keys=True)


def grade_tool_used(g, ctx):
    steps = ctx["steps"] if g.get("scope") == "top" else ctx["all_steps"]
    tool = re.compile(str(g.get("tool", ".*")))
    match = re.compile(str(g.get("input_match", "")))
    count = sum(1 for name, args in tool_calls(steps)
                if tool.fullmatch(name) and match.search(_args_text(args)))
    lo, hi = int(g.get("min", 1)), g.get("max")
    ok = count >= lo and (hi is None or count <= int(hi))
    return ok, f"{count} matching call(s), expected {lo}..{'∞' if hi is None else hi}"


def grade_regex(g, ctx):
    target = g.get("target") or {}
    if isinstance(target, dict) and target.get("source") == "file":
        path = os.path.join(ctx["repo"], target.get("path", ""))
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            return False, f"{target.get('path')} does not exist"
        where = target.get("path")
    else:
        text, where = ctx["reply"], "the final reply"
    ok = re.search(str(g["pattern"]), text) is not None
    return ok, f"pattern {'found' if ok else 'not found'} in {where}"


def grade_file_exists(g, ctx):
    hits = glob.glob(os.path.join(ctx["repo"], g["path"]), recursive=True)
    want = g.get("exists", True)
    ok = bool(hits) == bool(want)
    return ok, f"{len(hits)} match(es) for {g['path']}, expected {'some' if want else 'none'}"


def grade_llm(g, ctx):
    if not ctx.get("judge"):
        return None, "skipped: needs --judge"
    stdin = f"RULE:\n{g['body']}\n\nFINAL REPLY:\n{ctx['reply']}\n\nAnswer PASS or FAIL first, then one line of reasons.\n"
    proc = subprocess.run(ctx["judge"], shell=True, input=stdin, capture_output=True, text=True)
    verdict = proc.stdout.strip()
    return verdict.upper().startswith("PASS"), f"judge: {verdict.splitlines()[0] if verdict else proc.stderr.strip()}"


GRADERS = {"tool_used": grade_tool_used, "regex": grade_regex, "file_exists": grade_file_exists, "llm": grade_llm}


def grade(case, repo, transcript, judge=None, strict=False, evals=EVALS):
    loaded = load_case(case, evals)
    steps = read_steps(transcript)
    all_steps = list(steps)
    for sub in subagent_transcripts(transcript):
        all_steps.extend(read_steps(sub))
    ctx = {"repo": repo, "steps": steps, "all_steps": all_steps, "reply": final_reply(steps), "judge": judge}
    results = []
    for g in loaded["graders"]:
        ok, detail = GRADERS[g["type"]](g, ctx)
        results.append({"grader": g["name"], "type": g["type"], "passed": ok, "detail": detail})
    passed = all(r["passed"] or (r["passed"] is None and not strict) for r in results)
    return {"case": loaded["meta"].get("name", os.path.basename(loaded["path"])), "passed": passed,
            "results": results}


# --------------------------------------------------------------------------

def main(argv):
    ap = argparse.ArgumentParser(prog="evalgrade.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("list", "prompt", "scaffold", "grade"))
    ap.add_argument("case", nargs="?")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--evals", default=EVALS)
    ap.add_argument("--repo")
    ap.add_argument("--transcript")
    ap.add_argument("--judge")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.command == "list":
            for c in list_cases(args.evals):
                print(f"{os.path.basename(c['path']):<36} {','.join(c['meta'].get('tags') or [])}")
            return 0
        if not args.case:
            ap.error("CASE is required")
        if args.command == "prompt":
            print(load_case(args.case, args.evals)["prompt"])
            return 0
        if args.command == "scaffold":
            if not args.dest:
                ap.error("DIR is required")
            print(scaffold(args.case, args.dest, args.evals))
            return 0
        if not args.repo or not args.transcript:
            ap.error("grade needs --repo and --transcript")
        result = grade(args.case, args.repo, args.transcript, args.judge, args.strict, args.evals)
    except (CaseError, OSError) as err:
        print(f"evalgrade.py: {err}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for r in result["results"]:
            mark = {True: "PASS", False: "FAIL", None: "SKIP"}[r["passed"]]
            print(f"{mark}  {r['grader']:<24} {r['detail']}")
        print(f"{'PASS' if result['passed'] else 'FAIL'}  {result['case']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
