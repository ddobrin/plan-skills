#!/usr/bin/env python3
"""Read machine-readable blocks out of the swarm's Markdown files.

The swarm keeps configuration in Markdown with exactly one fenced JSON block,
found by its info-string tag:

    ```json swarm-config          plans/swarm.md
    ```json plan-swarm-topology   plugins/plan/topology.md
    ```json bands-config          bands.md (future)

The prose around the block explains the values; scripts read only the block.
Standard library only, because the hooks that import this module must run on
whatever python3 the user has.

Usage:
    swarmdoc.py FILE TAG      print the parsed block as JSON (exit 2 on error)
    swarmdoc.py --config [ROOT]   print plans/swarm.md merged with defaults
"""
import copy
import json
import os
import re
import sys


class SwarmDocError(ValueError):
    pass


def extract(text, tag):
    """Return the JSON value of the single ```json <tag> block in text."""
    pattern = re.compile(
        r"^```json[ \t]+" + re.escape(tag) + r"[ \t]*\n(.*?)^```[ \t]*$",
        re.DOTALL | re.MULTILINE,
    )
    blocks = pattern.findall(text)
    if not blocks:
        raise SwarmDocError(f"no ```json {tag} block found")
    if len(blocks) > 1:
        raise SwarmDocError(f"{len(blocks)} ```json {tag} blocks found; exactly one is allowed")
    try:
        return json.loads(blocks[0])
    except json.JSONDecodeError as err:
        raise SwarmDocError(f"```json {tag} block is not valid JSON: {err}") from err


def extract_file(path, tag):
    try:
        with open(path, encoding="utf-8") as fh:
            return extract(fh.read(), tag)
    except OSError as err:
        raise SwarmDocError(f"cannot read {path}: {err.strerror}") from err
    except SwarmDocError as err:
        raise SwarmDocError(f"{path}: {err}") from err


# --------------------------------------------------------------------------
# plans/swarm.md

CONFIG_PATH = os.path.join("plans", "swarm.md")
CONFIG_TAG = "swarm-config"
TIERS = ("routine", "elevated", "critical")

DEFAULTS = {
    "version": 1,
    "delivery": {"mode": "pr", "host": "github"},
    "engineers": {"max_concurrent": 5},
    "audit": {"max_path_a_rounds": 3},
    "approvals": {"nonce_ttl_minutes": 15},
    "policies": [],
    "tiers": {},
}


def _int(value, where, low, high):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise SwarmDocError(f"{where} must be an integer from {low} to {high}")
    return value


def _strings(value, where):
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise SwarmDocError(f"{where} must be a list of non-empty strings")
    return value


def validate_config(raw):
    """Merge a parsed swarm-config block with defaults and check every field."""
    if not isinstance(raw, dict):
        raise SwarmDocError("swarm-config must be a JSON object")
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise SwarmDocError(f"unknown swarm-config keys: {', '.join(sorted(unknown))}")
    cfg = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if isinstance(cfg[key], dict) and key != "tiers":
            if not isinstance(value, dict):
                raise SwarmDocError(f"{key} must be an object")
            extra = set(value) - set(cfg[key])
            if extra:
                raise SwarmDocError(f"unknown {key} keys: {', '.join(sorted(extra))}")
            cfg[key].update(value)
        else:
            cfg[key] = value

    if cfg["version"] != 1:
        raise SwarmDocError("version must be 1")
    if cfg["delivery"]["mode"] not in ("pr", "local"):
        raise SwarmDocError('delivery.mode must be "pr" or "local"')
    if cfg["delivery"]["host"] != "github":
        raise SwarmDocError('delivery.host must be "github" (the only supported host)')
    _int(cfg["engineers"]["max_concurrent"], "engineers.max_concurrent", 1, 10)
    _int(cfg["audit"]["max_path_a_rounds"], "audit.max_path_a_rounds", 1, 10)
    _int(cfg["approvals"]["nonce_ttl_minutes"], "approvals.nonce_ttl_minutes", 1, 120)
    _strings(cfg["policies"], "policies")

    tiers = cfg["tiers"]
    if not isinstance(tiers, dict):
        raise SwarmDocError("tiers must be an object")
    for name, rule in tiers.items():
        if name not in ("elevated", "critical"):
            raise SwarmDocError(f'tiers.{name}: only "elevated" and "critical" take rules')
        if not isinstance(rule, dict):
            raise SwarmDocError(f"tiers.{name} must be an object")
        extra = set(rule) - {"paths", "keywords", "diff_lines_over"}
        if extra:
            raise SwarmDocError(f"unknown tiers.{name} keys: {', '.join(sorted(extra))}")
        rule.setdefault("paths", [])
        rule.setdefault("keywords", [])
        _strings(rule["paths"], f"tiers.{name}.paths")
        _strings(rule["keywords"], f"tiers.{name}.keywords")
        if "diff_lines_over" in rule:
            _int(rule["diff_lines_over"], f"tiers.{name}.diff_lines_over", 1, 10**7)
    return cfg


def find_root(start=None):
    """Nearest ancestor of start (default cwd) containing .git, else start."""
    here = os.path.abspath(start or os.getcwd())
    probe = here
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            return here
        probe = parent


def load_config(root=None):
    """Load plans/swarm.md under the repository root. Raises SwarmDocError."""
    root = find_root(root)
    raw = extract_file(os.path.join(root, CONFIG_PATH), CONFIG_TAG)
    return validate_config(raw)


# --------------------------------------------------------------------------
# path globs: ** crosses directories, * and ? stay within one segment

def glob_to_regex(pattern):
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def path_matches(path, pattern):
    while path.startswith("./"):
        path = path[2:]
    return bool(glob_to_regex(pattern).match(path))


def main(argv):
    try:
        if argv and argv[0] == "--config":
            print(json.dumps(load_config(argv[1] if len(argv) > 1 else None), indent=2))
            return 0
        if len(argv) != 2:
            print(__doc__, file=sys.stderr)
            return 2
        print(json.dumps(extract_file(argv[0], argv[1]), indent=2))
        return 0
    except SwarmDocError as err:
        print(f"swarmdoc.py: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
