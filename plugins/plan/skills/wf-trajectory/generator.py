#!/usr/bin/env python3
"""wf-trajectory: render a completed Workflow run as self-contained HTML."""
from __future__ import annotations

import os
import sys

from wf_locator import locate_run, LocatorError
from wf_model import parse_run
from wf_render import load_template, render_html

OUT_DIR = "wf-trajectory"
GITIGNORE_ENTRY = "wf-trajectory/"


def ensure_gitignore(root: str = ".") -> None:
    gi = os.path.join(root, ".gitignore")
    existing = ""
    if os.path.exists(gi):
        with open(gi, "r", encoding="utf-8") as f:
            existing = f.read()
        if GITIGNORE_ENTRY in existing.split():
            return
    with open(gi, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(GITIGNORE_ENTRY + "\n")


def write_output(report, html_text: str, root: str = ".") -> str:
    out_dir = os.path.join(root, OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{report.run_id}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out_path


def main(argv) -> int:
    run_id = argv[1] if len(argv) > 1 else None
    try:
        json_path = locate_run(os.getcwd(), run_id)
    except LocatorError as e:
        print(f"wf-trajectory: {e}", file=sys.stderr)
        return 2
    report = parse_run(json_path)
    html_text = render_html(report, load_template())
    out_path = write_output(report, html_text)
    ensure_gitignore()
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
