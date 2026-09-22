#!/usr/bin/env python3
"""
TypeSafe System One Validator Engine for Antigravity (AGY CLI).

Provides fast, typed judgments, calibrated probabilities, semantic deduplication,
1-vote tail triage, citation verification, first-domino ranking, and calibrated
severity scoring for spec, plan, and implementation validators in plugins/plan.

Zero external dependencies: uses Python standard library only (urllib.request, json).
Graceful offline fallback when TYPESAFE_API_KEY is not set or network is unreachable.
"""

import argparse
import dataclasses
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


# ==============================================================================
# TypeSafe System One Client (Zero-Dependency)
# ==============================================================================

class TypeSafeClient:
    """Zero-dependency HTTP client for TypeSafe System One evaluation endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: str = "jev-latest",
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        self.endpoint = endpoint or os.environ.get(
            "TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone"
        )
        self.model = model
        self.timeout = timeout
        self.enabled = bool(self.api_key and self.api_key.strip())

    def ask(self, state: Any, questions: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Sends an evaluation request to the TypeSafe System One API.
        Returns the parsed response dictionary containing answers, or None on failure.
        """
        if not self.enabled:
            return None

        payload = {
            "state": state,
            "model": self.model,
            "questions": questions,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "TypeSafe-PlanValidator/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            sys.stderr.write(f"[TypeSafe] HTTP {e.code} Error: {e.reason} - {error_body}\n")
            return None
        except Exception as e:
            sys.stderr.write(f"[TypeSafe] Request failed: {e}\n")
            return None


# ==============================================================================
# Helper Utilities (String Matching & Fallbacks)
# ==============================================================================

def normalize_text(text: str) -> str:
    """Collapse whitespace, punctuation, and lowercase."""
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(text.split())


def token_similarity(a: str, b: str) -> float:
    """Calculates Jaccard token similarity between two strings."""
    tokens_a = set(normalize_text(a).split())
    tokens_b = set(normalize_text(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return len(intersection) / len(union)


def read_file_safely(path: str) -> str:
    """Reads a file path safely, returning empty string if missing."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


# ==============================================================================
# Pre-Flight Sieve (Fast Screening)
# ==============================================================================

class PreflightSieve:
    """
    Sub-second screening of specs and plans using parallel TypeSafe Nouls.
    Catches untestable criteria, missing error paths, and unverifiable steps.
    """

    def __init__(self, client: TypeSafeClient):
        self.client = client

    def screen_spec(self, spec_text: str) -> Dict[str, Any]:
        """Runs preflight checks on a specification."""
        excerpt = spec_text[:12000]  # First 12k chars captures overview + requirements
        questions = {
            "has_untestable_buzzwords": {
                "type": "noul",
                "instructions": (
                    "Does this specification rely on vague, unquantified buzzwords "
                    "(e.g., 'fast', 'scalable', 'robust', 'ultra-secure', 'modern', 'intuitive') "
                    "without defining measurable thresholds, SLAs, or concrete verification criteria?"
                ),
                "criteria": {
                    "true": "Relies on vague qualitative terms without measurable targets",
                    "false": "Specifies concrete, measurable, or bounded requirements",
                },
            },
            "missing_error_behavior": {
                "type": "noul",
                "instructions": (
                    "Does this specification fail to describe error handling, invalid input behavior, "
                    "or failure modes (focusing almost exclusively on the happy path)?"
                ),
                "criteria": {
                    "true": "Omits error handling, timeouts, or failure path requirements",
                    "false": "Includes explicit error handling, validation, or failure behaviors",
                },
            },
            "untestable_acceptance_criteria": {
                "type": "noul",
                "instructions": (
                    "Does this specification contain acceptance criteria that cannot be objectively "
                    "tested in automated tests or observable manual verification?"
                ),
                "criteria": {
                    "true": "Contains unverifiable or purely subjective acceptance criteria",
                    "false": "Acceptance criteria are testable and unambiguous",
                },
            },
        }

        resp = self.client.ask(state={"document_type": "spec", "content": excerpt}, questions=questions)
        warnings = []
        scores = {}

        if resp and "answers" in resp:
            answers = resp["answers"]
            for q_id, q_ans in answers.items():
                p = q_ans.get("noul", 0.0)
                scores[q_id] = p
                if p >= 0.70:
                    warnings.append({
                        "check": q_id,
                        "probability": round(p, 3),
                        "severity": "high" if p >= 0.85 else "medium",
                        "message": questions[q_id]["instructions"],
                    })
        else:
            # Offline regex fallback
            buzzwords = ["blazingly fast", "ultra-scalable", "robust and secure", "user-friendly"]
            found_bw = [bw for bw in buzzwords if bw in excerpt.lower()]
            if found_bw:
                warnings.append({
                    "check": "has_untestable_buzzwords",
                    "probability": 0.80,
                    "severity": "medium",
                    "message": f"Found unquantified buzzwords: {', '.join(found_bw)}",
                })
            if "error" not in excerpt.lower() and "exception" not in excerpt.lower() and "fail" not in excerpt.lower():
                warnings.append({
                    "check": "missing_error_behavior",
                    "probability": 0.75,
                    "severity": "medium",
                    "message": "Specification appears to omit error handling or failure cases.",
                })

        return {
            "stage": "spec",
            "passed": len(warnings) == 0,
            "warning_count": len(warnings),
            "warnings": warnings,
            "scores": scores,
        }

    def screen_plan(self, plan_text: str) -> Dict[str, Any]:
        """Runs preflight checks on an implementation plan."""
        excerpt = plan_text[:12000]
        questions = {
            "has_unverifiable_steps": {
                "type": "noul",
                "instructions": (
                    "Does the plan contain steps that lack an explicit, executable verification "
                    "command, automated test, or observable signal (e.g. merely saying 'verify it works')?"
                ),
                "criteria": {
                    "true": "Contains steps with vague or missing verification commands",
                    "false": "Steps specify concrete test commands or clear observable criteria",
                },
            },
            "missing_rollback": {
                "type": "noul",
                "instructions": (
                    "Does the plan include potentially destructive or stateful modifications "
                    "(e.g., schema migrations, table drops, data backfills, file removals) "
                    "without specifying a rollback, backup, or undo strategy?"
                ),
                "criteria": {
                    "true": "Destructive or schema changes lack rollback strategy",
                    "false": "No destructive changes or rollbacks are explicitly defined",
                },
            },
            "circular_or_unbounded_steps": {
                "type": "noul",
                "instructions": (
                    "Are there steps whose prerequisites or scope appear unbounded or circularly dependent?"
                ),
                "criteria": {
                    "true": "Contains unbounded or circularly dependent steps",
                    "false": "Steps have clear, bounded linear or parallel sequencing",
                },
            },
        }

        resp = self.client.ask(state={"document_type": "plan", "content": excerpt}, questions=questions)
        warnings = []
        scores = {}

        if resp and "answers" in resp:
            answers = resp["answers"]
            for q_id, q_ans in answers.items():
                p = q_ans.get("noul", 0.0)
                scores[q_id] = p
                if p >= 0.70:
                    warnings.append({
                        "check": q_id,
                        "probability": round(p, 3),
                        "severity": "high" if p >= 0.85 else "medium",
                        "message": questions[q_id]["instructions"],
                    })
        else:
            # Offline regex fallback
            if "verify" in excerpt.lower() and not re.search(r"(pytest|npm test|mvn test|go test|cargo test|bash|curl|python3)", excerpt):
                warnings.append({
                    "check": "has_unverifiable_steps",
                    "probability": 0.75,
                    "severity": "medium",
                    "message": "Plan mentions verification but lacks explicit test execution commands.",
                })

        return {
            "stage": "plan",
            "passed": len(warnings) == 0,
            "warning_count": len(warnings),
            "warnings": warnings,
            "scores": scores,
        }


# ==============================================================================
# Citation Verification (Source Grounding)
# ==============================================================================

class CitationVerifier:
    """Verifies that skeptic file:line evidence exists and supports the defect claim."""

    def __init__(self, client: TypeSafeClient, repo_root: str):
        self.client = client
        self.repo_root = repo_root

    def verify_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """Checks if the finding's cited evidence is verified, contradicted, or missing."""
        evidence_str = finding.get("evidence", "")
        file_path = finding.get("file", "")
        loc_str = str(finding.get("location", ""))

        # Extract file:line if not split
        if not file_path and ":" in evidence_str:
            match = re.search(r"([\w\-./\\]+\.[a-zA-Z0-9]+):(\d+)", evidence_str)
            if match:
                file_path = match.group(1)
                loc_str = match.group(2)

        if not file_path:
            return {"status": "unverified", "reason": "No file:line cited in evidence"}

        full_path = os.path.join(self.repo_root, file_path)
        if not os.path.exists(full_path):
            return {"status": "fabricated", "reason": f"Cited file {file_path} does not exist in repository"}

        content = read_file_safely(full_path)
        if not content:
            return {"status": "fabricated", "reason": f"Cited file {file_path} is empty or unreadable"}

        lines = content.splitlines()
        line_num = None
        try:
            line_num = int(loc_str.split("-")[0].split(":")[0].strip())
        except Exception:
            pass

        snippet = ""
        if line_num and 1 <= line_num <= len(lines):
            start = max(0, line_num - 5)
            end = min(len(lines), line_num + 5)
            snippet = "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end))
        else:
            snippet = "\n".join(lines[:20])

        # If TypeSafe is available, check semantic support
        questions = {
            "relation": {
                "type": "choice",
                "instructions": "How does the source code snippet relate to the skeptic's defect claim?",
                "criteria": {
                    "supports": "The source code snippet supports or directly confirms the defect/omission asserted.",
                    "contradicts": "The source code already implements the check or contradicts the claim of a defect.",
                    "says_nothing": "The source code does not address what the defect claim asserts.",
                },
            }
        }
        resp = self.client.ask(
            state={
                "defect_claim": finding.get("failure") or finding.get("title") or finding.get("interpretation"),
                "source_snippet": snippet,
                "cited_file": file_path,
                "cited_line": line_num,
            },
            questions=questions,
        )

        if resp and "answers" in resp:
            choice_ans = resp["answers"].get("relation", {})
            choice = choice_ans.get("choice")
            conf = choice_ans.get("confidence", 0.5)
            if choice == "supports":
                return {"status": "verified", "confidence": conf, "snippet": snippet}
            elif choice == "contradicts":
                return {"status": "contradicted", "confidence": conf, "reason": "Source code contradicts defect assertion"}
            else:
                return {"status": "unsupported", "confidence": conf, "reason": "Context does not substantiate claim"}

        # Offline fallback
        return {"status": "verified", "confidence": 0.6, "snippet": snippet}


# ==============================================================================
# Semantic Deduplication & Quorum Clustering
# ==============================================================================

class SemanticDeduplicator:
    """
    Clusters findings across 3 independent skeptics by semantic root cause.
    Replaces brittle exact kebab-case slug matching with TypeSafe alignment.
    """

    def __init__(self, client: TypeSafeClient):
        self.client = client

    def are_same_root_cause(self, f1: Dict[str, Any], f2: Dict[str, Any]) -> Tuple[bool, float]:
        """Returns True and confidence if f1 and f2 describe the same root defect."""
        # Fast equality checks
        id1, id2 = f1.get("id", "").strip().lower(), f2.get("id", "").strip().lower()
        if id1 and id1 == id2:
            return True, 1.0

        desc1 = f"{f1.get('id', '')} {f1.get('failure', '')} {f1.get('title', '')} {f1.get('clause', '')}"
        desc2 = f"{f2.get('id', '')} {f2.get('failure', '')} {f2.get('title', '')} {f2.get('clause', '')}"

        token_sim = token_similarity(desc1, desc2)
        if token_sim >= 0.70:
            return True, token_sim

        # If TypeSafe is available, test semantic equivalence
        questions = {
            "relationship": {
                "type": "choice",
                "instructions": (
                    "Do these two findings from independent adversarial reviewers describe "
                    "the same underlying defect, gap, or failure scenario, even if worded differently?"
                ),
                "criteria": {
                    "same_defect": "Both describe the same root-cause flaw, hole, or vulnerability.",
                    "related_subcase": "They touch the same component but identify distinct, separate issues.",
                    "distinct": "They describe completely different problems.",
                },
            }
        }
        resp = self.client.ask(state={"finding_a": f1, "finding_b": f2}, questions=questions)
        if resp and "answers" in resp:
            choice_ans = resp["answers"].get("relationship", {})
            choice = choice_ans.get("choice")
            conf = choice_ans.get("confidence", 0.5)
            if choice == "same_defect" and conf >= 0.65:
                return True, conf

        # Offline fallback: slug keyword overlap or description token similarity
        stopwords = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "is", "no", "not"}
        slug1_tokens = set(normalize_text(id1).split()) - stopwords
        slug2_tokens = set(normalize_text(id2).split()) - stopwords
        if slug1_tokens and slug2_tokens and (slug1_tokens & slug2_tokens):
            return True, 0.75

        # Check description token overlap
        if token_sim >= 0.28:
            return True, token_sim

        return False, token_sim

    def cluster_findings(
        self, skeptic_lists: List[Tuple[str, List[Dict[str, Any]]]]
    ) -> List[Dict[str, Any]]:
        """
        Groups findings from multiple skeptics into clusters.
        skeptic_lists is a list of (skeptic_name, [findings]).
        """
        clusters: List[Dict[str, Any]] = []

        for skeptic_name, findings in skeptic_lists:
            for f in findings:
                f_entry = dict(f)
                f_entry["_reporter"] = skeptic_name
                matched_cluster = None

                for cluster in clusters:
                    representative = cluster["findings"][0]
                    # Check if matching
                    same, conf = self.are_same_root_cause(representative, f_entry)
                    if same:
                        matched_cluster = cluster
                        break

                if matched_cluster:
                    matched_cluster["findings"].append(f_entry)
                    matched_cluster["reporters"].add(skeptic_name)
                else:
                    clusters.append({
                        "id": f_entry.get("id") or f"defect-{len(clusters)+1}",
                        "findings": [f_entry],
                        "reporters": {skeptic_name},
                    })

        # Synthesize each cluster
        result = []
        for c in clusters:
            vote_count = len(c["reporters"])
            primary = c["findings"][0]
            result.append({
                "id": primary.get("id", c["id"]),
                "vote_count": vote_count,
                "reporters": sorted(list(c["reporters"])),
                "is_confirmed": vote_count >= 2,
                "findings": c["findings"],
                "representative": primary,
            })

        return result


# ==============================================================================
# 1-Vote Tail SDE Cascade Triager
# ==============================================================================

class TailTriager:
    """
    SDE Cascade triage for 1-vote tail findings.
    Uses calibrated P(defect) Noul to auto-promote real solo catches
    and discard false positives without expensive multi-agent deliberation.
    """

    def __init__(self, client: TypeSafeClient):
        self.client = client

    def triage(self, cluster: Dict[str, Any], context_doc: str = "") -> Dict[str, Any]:
        """Evaluates a 1-vote tail cluster."""
        primary = cluster["representative"]
        finding_desc = json.dumps(primary, indent=2)

        questions = {
            "is_genuine_defect": {
                "type": "noul",
                "instructions": (
                    "Is this reported finding a genuine, actionable defect, ambiguity, or failure path "
                    "violating correctness, safety, or requirements, rather than a cosmetic preference or non-issue?"
                ),
                "criteria": {
                    "true": "A genuine, code-grounded or spec-grounded defect that should be fixed.",
                    "false": "A harmless stylistic comment, invalid interpretation, or non-issue.",
                },
            }
        }
        resp = self.client.ask(
            state={
                "finding": finding_desc,
                "document_context": context_doc[:8000] if context_doc else "",
            },
            questions=questions,
        )

        p = 0.5
        if resp and "answers" in resp:
            p = resp["answers"].get("is_genuine_defect", {}).get("noul", 0.5)
        else:
            # Fallback heuristic: check confidence field
            conf = primary.get("confidence", "medium").lower()
            if conf == "high":
                p = 0.70
            elif conf == "low":
                p = 0.30

        if p >= 0.85:
            verdict = "promoted"
            action = "Promote to Confirmed (High-confidence solo catch)"
        elif p < 0.40:
            verdict = "discarded"
            action = "Filtered as False Positive"
        else:
            verdict = "fyi"
            action = "Retain as Unconfirmed FYI"

        return {
            "id": cluster["id"],
            "probability_defect": round(p, 3),
            "verdict": verdict,
            "action": action,
            "cluster": cluster,
        }


# ==============================================================================
# Severity Calibrator (Continuous Score Rubric)
# ==============================================================================

class SeverityCalibrator:
    """
    Evaluates confirmed defects against an objective 4-level descriptive ordinal rubric.
    Produces a continuous probability-weighted score (1.0 to 4.0) and confidence.
    """

    def __init__(self, client: TypeSafeClient):
        self.client = client

    def calibrate(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """Calibrates severity for a finding cluster."""
        primary = cluster["representative"]
        finding_desc = (
            f"Title/Failure: {primary.get('failure') or primary.get('title') or primary.get('harm')}\n"
            f"Evidence: {primary.get('evidence')}\n"
            f"Reported Severities: {[f.get('severity') or f.get('correctedSeverity') for f in cluster['findings']]}"
        )

        questions = {
            "calibrated_severity": {
                "type": "score",
                "instructions": "Rate the operational severity and blast radius of this confirmed defect.",
                "criteria": [
                    "low: Minor cosmetic flaw, documentation gap, or non-fatal deviation with trivial workaround.",
                    "medium: Real functional defect with limited blast radius or graceful degradation under narrow conditions.",
                    "high: Serious operational failure, broken major capability, or data corruption under conditional load/concurrency.",
                    "critical: Immediate, unconditional data loss, security compromise, or complete system crash on every execution.",
                ],
            }
        }

        resp = self.client.ask(state={"defect": finding_desc}, questions=questions)
        if resp and "answers" in resp:
            score_ans = resp["answers"].get("calibrated_severity", {})
            score = score_ans.get("score", 2.0)
            conf = score_ans.get("confidence", 0.7)
            probs = score_ans.get("probabilities", [])

            if score >= 3.25:
                label = "critical"
            elif score >= 2.50:
                label = "high"
            elif score >= 1.75:
                label = "medium"
            else:
                label = "low"

            return {
                "score": round(score, 2),
                "label": label,
                "confidence": round(conf, 2),
                "probabilities": probs,
                "source": "typesafe-score",
            }

        # Offline fallback: mode of reported severities
        severities = [
            (f.get("severity") or f.get("correctedSeverity") or "medium").lower()
            for f in cluster["findings"]
        ]
        tier_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        weights = [tier_weights.get(s, 2) for s in severities]
        avg_weight = sum(weights) / len(weights) if weights else 2.0

        if avg_weight >= 3.25:
            lbl = "critical"
        elif avg_weight >= 2.50:
            lbl = "high"
        elif avg_weight >= 1.75:
            lbl = "medium"
        else:
            lbl = "low"

        return {
            "score": round(avg_weight, 2),
            "label": lbl,
            "confidence": 0.60,
            "probabilities": [],
            "source": "offline-fallback",
        }


# ==============================================================================
# First-Domino Cascading Impact Ranker (Plan Validator)
# ==============================================================================

class FirstDominoRanker:
    """Ranks plan findings by cascading failure risk to find the true first domino."""

    def __init__(self, client: TypeSafeClient):
        self.client = client

    def rank(self, confirmed_clusters: List[Dict[str, Any]], plan_text: str = "") -> Dict[str, Any]:
        """Ranks confirmed clusters and identifies the root domino."""
        if not confirmed_clusters:
            return {"first_domino": None, "ranked_findings": []}

        scored = []
        for c in confirmed_clusters:
            rep = c["representative"]
            step_str = str(rep.get("step", "1"))
            match = re.search(r"\d+", step_str)
            step_idx = int(match.group(0)) if match else 1

            questions = {
                "cascade_risk": {
                    "type": "score",
                    "instructions": "How severely does this step failure invalidate or topple subsequent plan steps?",
                    "criteria": [
                        "isolated: The failure affects only this step; subsequent steps can still proceed.",
                        "group_level: Breaks the current execution group or milestone component, blocking adjacent steps.",
                        "systemic_domino: Invalidates core architecture, schemas, or prerequisites, toppling almost all subsequent steps.",
                    ],
                }
            }
            resp = self.client.ask(
                state={
                    "step": step_str,
                    "failure": rep.get("failure"),
                    "plan_context": plan_text[:6000] if plan_text else "",
                },
                questions=questions,
            )

            cascade_score = 2.0
            if resp and "answers" in resp:
                cascade_score = resp["answers"].get("cascade_risk", {}).get("score", 2.0)

            # Lower composite score = earlier step with higher cascading impact
            # We want earliest step (step_idx) with maximum cascade (cascade_score / 3.0)
            composite_rank = step_idx - (cascade_score * 0.5)

            scored.append({
                "cluster": c,
                "step_index": step_idx,
                "cascade_score": round(cascade_score, 2),
                "composite_rank": round(composite_rank, 2),
                "id": c["id"],
            })

        scored.sort(key=lambda x: (x["composite_rank"], x["step_index"]))
        first_domino = scored[0]["id"] if scored else None

        return {
            "first_domino": first_domino,
            "ranked_findings": scored,
        }


# ==============================================================================
# Review Report Synthesizer
# ==============================================================================

def generate_markdown_report(
    stage: str,
    target_path: str,
    confirmed_clusters: List[Dict[str, Any]],
    unconfirmed_clusters: List[Dict[str, Any]],
    calibrated_severities: Dict[str, Dict[str, Any]],
    first_domino: Optional[str] = None,
    preflight_results: Optional[Dict[str, Any]] = None,
) -> str:
    """Generates the standardized review Markdown report matching the swarm specifications."""
    total_findings = len(confirmed_clusters) + len(unconfirmed_clusters)
    status_badge = "FAIL" if len(confirmed_clusters) > 0 else "PASS"

    lines = [
        f"# Adversarial {stage.capitalize()} Validation Report",
        "",
        f"- **Target:** `{target_path}`",
        f"- **Verdict:** **{status_badge}** ({len(confirmed_clusters)} confirmed, {len(unconfirmed_clusters)} unconfirmed)",
        f"- **Validation Engine:** TypeSafe System One (Jev) + Hybrid Skeptic Quorum",
    ]

    if first_domino:
        lines.append(f"- **First Domino:** `{first_domino}` (earliest step toppling downstream tasks)")

    lines.append("")

    # Pre-Flight Section
    if preflight_results:
        lines.extend([
            "## Pre-Flight Sieve Results",
            "",
            f"- **Passed:** {'Yes' if preflight_results.get('passed') else 'Warnings Flagged'}",
            f"- **Advisory Warnings:** {preflight_results.get('warning_count', 0)}",
        ])
        for w in preflight_results.get("warnings", []):
            lines.append(f"  - `[{w.get('severity', 'medium').upper()}]` **{w.get('check')}**: {w.get('message')}")
        lines.append("")

    # Confirmed Findings
    lines.extend([
        "## Confirmed Findings (Quorum >= 2 or Promoted)",
        "",
    ])
    if not confirmed_clusters:
        lines.append("_Zero confirmed findings. Quorum criteria satisfied._\n")
    else:
        for idx, c in enumerate(confirmed_clusters, 1):
            rep = c["representative"]
            cid = c["id"]
            cal = calibrated_severities.get(cid, {})
            cal_score = cal.get("score", 2.0)
            cal_label = cal.get("label", "medium").upper()
            reporters = ", ".join(c.get("reporters", []))

            lines.extend([
                f"### {idx}. `{cid}` — [{cal_label} / Score: {cal_score}]",
                f"- **Step / Clause / Location:** `{rep.get('step') or rep.get('clause') or rep.get('location') or 'General'}`",
                f"- **Confirmed by Skeptics:** {reporters} (Votes: {c.get('vote_count', 2)})",
                f"- **Failure / Harm:** {rep.get('failure') or rep.get('harm') or rep.get('title')}",
                f"- **Evidence:** `{rep.get('evidence')}`",
                f"- **Recommended Fix / Tightening:** {rep.get('fix') or rep.get('tightening') or 'Review and patch implementation.'}",
                "",
            ])

    # Unconfirmed Tail
    lines.extend([
        "## Unconfirmed Tail (FYI)",
        "",
    ])
    if not unconfirmed_clusters:
        lines.append("_No unconfirmed tail findings._\n")
    else:
        for idx, c in enumerate(unconfirmed_clusters, 1):
            rep = c["representative"]
            reporters = ", ".join(c.get("reporters", []))
            lines.extend([
                f"### {idx}. `{c['id']}` (1-vote: {reporters})",
                f"- **Observation:** {rep.get('failure') or rep.get('harm') or rep.get('title')}",
                f"- **Evidence:** `{rep.get('evidence')}`",
                "",
            ])

    # Actions Taken Checklist
    lines.extend([
        "## Actions Taken",
        "",
    ])
    if confirmed_clusters:
        for c in confirmed_clusters:
            lines.append(f"- [ ] Fix confirmed defect `{c['id']}`")
    else:
        lines.append("- [x] Ready to proceed — gate passed cleanly.")

    lines.append("")
    return "\n".join(lines)


# ==============================================================================
# CLI Commands
# ==============================================================================

def cmd_preflight(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    sieve = PreflightSieve(client)
    content = read_file_safely(args.file)
    if not content:
        sys.stderr.write(f"Error: Target file not found or empty: {args.file}\n")
        return 1

    if args.stage == "spec":
        res = sieve.screen_spec(content)
    else:
        res = sieve.screen_plan(content)

    print(json.dumps(res, indent=2))
    if args.strict and not res.get("passed", True):
        return 2
    return 0


def cmd_dedup_quorum(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    dedup = SemanticDeduplicator(client)

    raw_data = read_file_safely(args.findings)
    if not raw_data:
        sys.stderr.write(f"Error: Findings file empty or missing: {args.findings}\n")
        return 1

    skeptic_inputs = json.loads(raw_data)
    # Expected format: {"skeptic-1": [...], "skeptic-2": [...], "skeptic-3": [...]}
    skeptic_lists = []
    if isinstance(skeptic_inputs, dict):
        for name, findings in skeptic_inputs.items():
            if isinstance(findings, list):
                skeptic_lists.append((name, findings))
    elif isinstance(skeptic_inputs, list):
        skeptic_lists.append(("all_skeptics", skeptic_inputs))

    clusters = dedup.cluster_findings(skeptic_lists)
    print(json.dumps(clusters, indent=2))
    return 0


def cmd_triage_tail(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    triager = TailTriager(client)
    context_doc = read_file_safely(args.context) if args.context else ""

    raw_data = read_file_safely(args.findings)
    if not raw_data:
        sys.stderr.write(f"Error: Findings file empty: {args.findings}\n")
        return 1

    data = json.loads(raw_data)
    clusters = data if isinstance(data, list) else [data]

    results = []
    for c in clusters:
        res = triager.triage(c, context_doc)
        results.append(res)

    print(json.dumps(results, indent=2))
    return 0


def cmd_calibrate_severity(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    calibrator = SeverityCalibrator(client)

    raw_data = read_file_safely(args.findings)
    if not raw_data:
        sys.stderr.write(f"Error: Findings file empty: {args.findings}\n")
        return 1

    data = json.loads(raw_data)
    clusters = data if isinstance(data, list) else [data]

    results = {}
    for c in clusters:
        cid = c.get("id", "finding")
        res = calibrator.calibrate(c)
        results[cid] = res

    print(json.dumps(results, indent=2))
    return 0


def cmd_first_domino(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    ranker = FirstDominoRanker(client)
    plan_text = read_file_safely(args.plan) if args.plan else ""

    raw_data = read_file_safely(args.findings)
    if not raw_data:
        sys.stderr.write(f"Error: Findings file empty: {args.findings}\n")
        return 1

    data = json.loads(raw_data)
    clusters = data if isinstance(data, list) else [data]
    confirmed = [c for c in clusters if c.get("is_confirmed", True)]

    res = ranker.rank(confirmed, plan_text)
    print(json.dumps(res, indent=2))
    return 0


def cmd_synthesize(args: argparse.Namespace) -> int:
    client = TypeSafeClient()
    dedup = SemanticDeduplicator(client)
    triager = TailTriager(client)
    calibrator = SeverityCalibrator(client)
    ranker = FirstDominoRanker(client)

    # Gather inputs from skeptic files
    skeptic_lists = []
    for fpath in args.skeptics:
        name = os.path.splitext(os.path.basename(fpath))[0]
        content = read_file_safely(fpath)
        if content:
            try:
                parsed = json.loads(content)
                findings = parsed.get("findings", parsed) if isinstance(parsed, dict) else parsed
                if isinstance(findings, list):
                    skeptic_lists.append((name, findings))
            except Exception as e:
                sys.stderr.write(f"Warning: could not parse {fpath}: {e}\n")

    if not skeptic_lists:
        sys.stderr.write("Error: No valid skeptic JSON inputs provided.\n")
        return 1

    clusters = dedup.cluster_findings(skeptic_lists)
    target_content = read_file_safely(args.target) if args.target else ""

    confirmed = [c for c in clusters if c["is_confirmed"]]
    tail = [c for c in clusters if not c["is_confirmed"]]

    # Triage 1-vote tail
    surviving_tail = []
    for c in tail:
        triage_res = triager.triage(c, target_content)
        if triage_res["verdict"] == "promoted":
            c["is_confirmed"] = True
            c["promoted"] = True
            confirmed.append(c)
        elif triage_res["verdict"] == "fyi":
            surviving_tail.append(c)
        # discarded items are dropped

    # Calibrate severity for confirmed
    calibrated_severities = {}
    for c in confirmed:
        cal = calibrator.calibrate(c)
        calibrated_severities[c["id"]] = cal

    # First domino ranking for plan stage
    first_domino = None
    if args.stage == "plan":
        rank_res = ranker.rank(confirmed, target_content)
        first_domino = rank_res.get("first_domino")

    # Generate Markdown report
    report_md = generate_markdown_report(
        stage=args.stage,
        target_path=args.target or "target_document",
        confirmed_clusters=confirmed,
        unconfirmed_clusters=surviving_tail,
        calibrated_severities=calibrated_severities,
        first_domino=first_domino,
    )

    if args.out:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"Report successfully written to {args.out}")
    else:
        print(report_md)

    return 0


# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="TypeSafe System One Validator Engine for Antigravity (AGY CLI)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Preflight
    p_preflight = subparsers.add_parser("preflight", help="Fast screening for specs and plans")
    p_preflight.add_argument("--stage", choices=["spec", "plan"], required=True)
    p_preflight.add_argument("--file", required=True, help="Path to spec.md or plan.md")
    p_preflight.add_argument("--strict", action="store_true", help="Exit non-zero if warnings found")
    p_preflight.set_defaults(func=cmd_preflight)

    # Dedup & Quorum
    p_dedup = subparsers.add_parser("dedup-quorum", help="Semantic finding deduplication across skeptics")
    p_dedup.add_argument("--findings", required=True, help="JSON file containing skeptic findings")
    p_dedup.set_defaults(func=cmd_dedup_quorum)

    # Triage Tail
    p_triage = subparsers.add_parser("triage-tail", help="SDE Cascade triage for 1-vote tail findings")
    p_triage.add_argument("--findings", required=True, help="JSON file containing unconfirmed findings")
    p_triage.add_argument("--context", help="Path to target document context")
    p_triage.set_defaults(func=cmd_triage_tail)

    # Calibrate Severity
    p_cal = subparsers.add_parser("calibrate-severity", help="Calibrate severity using 4-level Score rubric")
    p_cal.add_argument("--findings", required=True, help="JSON file containing confirmed findings")
    p_cal.set_defaults(func=cmd_calibrate_severity)

    # First Domino
    p_dom = subparsers.add_parser("first-domino", help="Rank plan findings by cascading impact")
    p_dom.add_argument("--findings", required=True, help="JSON file containing confirmed plan findings")
    p_dom.add_argument("--plan", help="Path to plan.md")
    p_dom.set_defaults(func=cmd_first_domino)

    # Synthesize
    p_syn = subparsers.add_parser("synthesize", help="End-to-end review report synthesizer")
    p_syn.add_argument("--stage", choices=["spec", "plan", "implementation"], required=True)
    p_syn.add_argument("--target", required=True, help="Path to target artifact (spec.md, plan.md, or diff)")
    p_syn.add_argument("--skeptics", nargs="+", required=True, help="Paths to raw skeptic JSON files")
    p_syn.add_argument("--out", help="Path to write output markdown review report")
    p_syn.set_defaults(func=cmd_synthesize)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
