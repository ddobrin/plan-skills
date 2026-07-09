#!/usr/bin/env python3
"""Thin wrapper: GEAP remote adversarial plan validator (3 skeptics + synthesis)."""
import os
import sys

# The shared core lives at <plugin>/lib/geap_validator_core. Try relative to this
# file first (checkout), then CLAUDE_PLUGIN_ROOT (installed plugin).
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
for cand in [os.path.join(os.path.dirname(os.path.dirname(SKILL_DIR)), "lib"),
             os.path.join(os.environ.get("CLAUDE_PLUGIN_ROOT", ""), "lib")]:
    if os.path.isdir(os.path.join(cand, "geap_validator_core")):
        sys.path.insert(0, cand)
        break

from geap_validator_core.stages import PLAN_STAGE
from geap_validator_core.runner import main

if __name__ == "__main__":
    main(PLAN_STAGE, sys.argv[1:])
