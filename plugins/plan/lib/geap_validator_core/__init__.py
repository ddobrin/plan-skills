"""Shared core for the GEAP remote adversarial validator skills.

Used by the geap-spec-validator and geap-plan-validator skill wrappers under
plugins/plan/skills/. Runs 3 configurable skeptic models in parallel on
Vertex AI plus a synthesis model, then computes a programmatic 2-of-3
(+synthesis) quorum.
"""

__version__ = "1.0.0"
