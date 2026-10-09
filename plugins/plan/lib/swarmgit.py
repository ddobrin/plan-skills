#!/usr/bin/env python3
"""Shared git, store, and ledger helpers for the plan-swarm control plane.

The store holds approval nonces, commit tickets, tag allowances, the heartbeat,
and the activation marker. It lives in the repository's git common directory
(.git/plan-swarm/), outside the working tree, so it is never committed, is
shared by every worktree, and is readable by the git hooks, which run outside
Antigravity. PLAN_SWARM_STORE overrides the location only when PLAN_SWARM_TEST=1
(the test suite), so a committer's environment cannot redirect the git hooks.

Readers tolerate malformed files (they are skipped, never trusted); writers use
unique temporary files so parallel hooks cannot collide.

Standard library only.
"""
import datetime as dt
import json
import os
import re
import secrets
import subprocess
import tempfile

MONIKER = r"[a-z0-9][a-z0-9._-]*"
LEDGER_HEADER = (
    "# Approvals ledger\n\n"
    "Written only by the plan-swarm approval hook (`lib/approve.py`) when a human types an\n"
    "approval phrase. Agents cannot edit this file.\n\n"
    "| when (UTC) | who | kind | milestone | group | tier | mode | HEAD | nonce |\n"
    "|---|---|---|---|---|---|---|---|---|\n"
)
LEDGER_COLUMNS = ("when", "who", "kind", "milestone", "group", "tier", "mode", "head", "nonce")
HEARTBEAT_FRESH_SECONDS = 600
TICKET_SECONDS = 60


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    """Parse our timestamp format; None for anything else."""
    try:
        return dt.datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def age_seconds(s):
    t = parse_iso(s)
    return None if t is None else (now() - t).total_seconds()


def git(*args, cwd=None, check=False, strip=True):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip() if strip else proc.stdout


def git_ok(*args, cwd=None):
    """True when the git command exits 0 (for predicates such as merge-base --is-ancestor)."""
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True).returncode == 0


def repo_root(cwd=None):
    return git("rev-parse", "--show-toplevel", cwd=cwd) or os.path.abspath(cwd or os.getcwd())


def head(cwd=None):
    """Full SHA of HEAD, or "" on an unborn branch or outside a repository."""
    return git("rev-parse", "--verify", "--quiet", "HEAD", cwd=cwd)


def branch(cwd=None):
    return git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=cwd)


def default_branch(cwd=None):
    ref = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=cwd)
    return ref.split("/", 1)[1] if "/" in ref else ""


def is_default_branch(name, cwd=None):
    return bool(name) and (name in ("main", "master") or name == default_branch(cwd))


def common_dir(cwd=None):
    common = git("rev-parse", "--git-common-dir", cwd=cwd)
    if not common:
        return ""
    if not os.path.isabs(common):
        common = os.path.join(cwd or os.getcwd(), common)
    return os.path.realpath(common)


def is_linked_worktree(cwd=None):
    """True inside a `git worktree add` checkout (its git dir differs from the common dir)."""
    gd = git("rev-parse", "--absolute-git-dir", cwd=cwd)
    cd = common_dir(cwd)
    return bool(gd and cd) and os.path.realpath(gd) != cd


def changed_paths(cwd=None, include_unstaged=False):
    """Staged paths, plus unstaged and untracked paths when include_unstaged."""
    paths = set(filter(None, git("diff", "--cached", "--name-only", cwd=cwd).splitlines()))
    if include_unstaged:
        # porcelain lines start with a two-letter status that may begin with a space: never strip
        for line in git("status", "--porcelain", "--untracked-files=all", cwd=cwd, strip=False).splitlines():
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            paths.add(path.strip('"'))
    return paths


def user_email(cwd=None):
    return git("config", "user.email", cwd=cwd) or os.environ.get("USER", "unknown")


# --------------------------------------------------------------------------
# swarm branch names

def swarm_branch(name):
    """('m', None) for swarm/m, ('m', 'task') for swarm-wip/m/task, else (None, None).

    Worktree branches live under swarm-wip/ because git cannot hold both a ref
    swarm/m and refs below it (swarm/m/...)."""
    m = re.fullmatch(rf"swarm/({MONIKER})", name or "")
    if m:
        return m.group(1), None
    m = re.fullmatch(rf"swarm-wip/({MONIKER})/([A-Za-z0-9._-]+)", name or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def wip_branch(moniker, task):
    return f"swarm-wip/{moniker}/{task}"


# --------------------------------------------------------------------------
# store

def store_dir(cwd=None, create=True):
    """The store directory, created on demand; "" outside a git repository.

    With create=False the path is returned without touching the disk, so an
    activity probe leaves repositories that never opted in untouched."""
    override = os.environ.get("PLAN_SWARM_STORE") if os.environ.get("PLAN_SWARM_TEST") == "1" else None
    if override:
        path = override
    else:
        common = common_dir(cwd)
        if not common:
            return ""
        path = os.path.join(common, "plan-swarm")
    if create:
        os.makedirs(os.path.join(path, "nonces"), exist_ok=True)
    return path


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write(path, obj):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def nonce_key(kind, moniker=None, group=None, version=None):
    parts = [kind, moniker or version or "-"]
    if group is not None:
        parts.append(f"g{group}")
    return "-".join(parts)


def mint_nonce(store, record):
    record = dict(record, used=False)
    record.setdefault("id", "n_" + secrets.token_hex(6))
    key = nonce_key(record["kind"], record.get("moniker"), record.get("group"), record.get("version"))
    _write(os.path.join(store, "nonces", key + ".json"), record)
    return record


def _nonce_files(store):
    folder = os.path.join(store, "nonces") if store else ""
    if not folder or not os.path.isdir(folder):
        return []
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.endswith(".json")]


def _well_formed(rec):
    return (isinstance(rec, dict) and isinstance(rec.get("kind"), str) and isinstance(rec.get("id"), str)
            and parse_iso(rec.get("expires")) is not None and isinstance(rec.get("head"), str))


def valid_nonces(store, head_sha, kinds=None):
    """Unused, unexpired, well-formed nonces bound to exactly head_sha."""
    out = []
    if not head_sha:
        return out
    for path in _nonce_files(store):
        rec = _read(path)
        if not _well_formed(rec) or rec.get("used"):
            continue
        if kinds and rec["kind"] not in kinds:
            continue
        if parse_iso(rec["expires"]) < now() or rec["head"] != head_sha:
            continue
        rec["_path"] = path
        out.append(rec)
    return out


def stale_reason(store, head_sha, kinds):
    """Explain why no nonce of these kinds is usable, for deny messages."""
    reasons = []
    for path in _nonce_files(store):
        rec = _read(path)
        if not _well_formed(rec) or rec["kind"] not in kinds:
            continue
        label = nonce_key(rec["kind"], rec.get("moniker"), rec.get("group"), rec.get("version"))
        if rec.get("used"):
            reasons.append(f"{label} was already used")
        elif parse_iso(rec["expires"]) < now():
            reasons.append(f"{label} expired")
        elif rec["head"] != head_sha:
            reasons.append(f"{label} is stale (HEAD moved since approval)")
    return "; ".join(reasons)


class NonceTaken(Exception):
    pass


def consume(rec):
    """Atomically claim a nonce: the first process to rename the file wins."""
    path = rec.pop("_path")
    claimed = path[:-5] + f".claimed-{os.getpid()}-{secrets.token_hex(3)}"
    try:
        os.rename(path, claimed)
    except OSError as err:
        raise NonceTaken("this approval was just used by another command") from err
    current = _read(claimed)
    if not _well_formed(current) or current.get("used") or current.get("id") != rec.get("id"):
        os.rename(claimed, path)
        raise NonceTaken("this approval was already used")
    rec["used"] = True
    rec["used_at"] = iso(now())
    _write(path, rec)
    try:
        os.remove(claimed)
    except OSError:
        pass
    return rec


def write_ticket(store, head_sha, nonce, plans_only):
    _write(os.path.join(store, "ticket.json"), {
        "head": head_sha, "nonce": nonce.get("id"), "kind": nonce.get("kind"),
        "moniker": nonce.get("moniker"), "plans_only": bool(plans_only),
        "expires": iso(now() + dt.timedelta(seconds=TICKET_SECONDS))})


def take_ticket(store, head_sha):
    """Return and delete the ticket if it is fresh and bound to head_sha, else None."""
    path = os.path.join(store, "ticket.json")
    rec = _read(path)
    if not rec:
        return None
    try:
        os.remove(path)
    except OSError:
        return None
    expires = parse_iso(rec.get("expires"))
    if not head_sha or rec.get("head") != head_sha or expires is None or expires < now():
        return None
    return rec


def allowance(store, name, seconds=None):
    """Create (seconds given) or check a short-lived named allowance."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    path = os.path.join(store, f"allow-{safe}.json")
    if seconds is not None:
        _write(path, {"expires": iso(now() + dt.timedelta(seconds=seconds))})
        return True
    rec = _read(path) or {}
    expires = parse_iso(rec.get("expires"))
    return expires is not None and expires >= now()


def touch_heartbeat(store, **extra):
    path = os.path.join(store, "heartbeat.json")
    rec = _read(path) or {}
    rec.update(extra, updated=iso(now()))
    if parse_iso(rec.get("started")) is None:
        rec["started"] = rec["updated"]
    _write(path, rec)
    return rec


def heartbeat(store):
    return _read(os.path.join(store, "heartbeat.json")) if store else None


def heartbeat_fresh(store, seconds=HEARTBEAT_FRESH_SECONDS):
    age = age_seconds((heartbeat(store) or {}).get("updated"))
    return age is not None and age <= seconds


def mark_active(store):
    """Record that this repository is plan-swarm managed (see gate.load)."""
    path = os.path.join(store, "active")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("plan-swarm is active in this repository. Only a person removes this file.\n")


def is_active(store):
    return bool(store) and os.path.exists(os.path.join(store, "active"))


# --------------------------------------------------------------------------
# milestones and the ledger

def milestone_dir(root, moniker):
    return os.path.join(root, "plans", "active_milestones", moniker)


def ledger_path(root, moniker=None):
    if moniker:
        return os.path.join(milestone_dir(root, moniker), "approvals.md")
    return os.path.join(root, "plans", "approvals.md")


def append_ledger(root, moniker, row):
    path = ledger_path(root, moniker)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fresh = not os.path.exists(path)
    cells = [row.get(k, "") or "" for k in LEDGER_COLUMNS]
    with open(path, "a", encoding="utf-8") as fh:
        if fresh:
            fh.write(LEDGER_HEADER)
        fh.write("| " + " | ".join(str(c) for c in cells) + " |\n")
    return path


def parse_ledger(text):
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 9 and re.match(r"\d{4}-\d\d-\d\dT", cells[0]):
            rows.append(dict(zip(LEDGER_COLUMNS, cells)))
    return rows


def read_ledger(root, moniker=None):
    try:
        with open(ledger_path(root, moniker), encoding="utf-8") as fh:
            return parse_ledger(fh.read())
    except OSError:
        return []


def confirmed_tier(root, moniker):
    tier = ""
    for row in read_ledger(root, moniker):
        if row["kind"] == "plan" and row["tier"]:
            tier = row["tier"]
    return tier
