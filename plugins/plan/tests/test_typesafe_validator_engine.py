#!/usr/bin/env python3
"""
Unit tests for TypeSafe System One Validator Engine.
Tests both offline fallback heuristics and mocked TypeSafe System One API responses.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add parent directories to sys.path so we can import the engine
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from typesafe_validator_engine import (
    FirstDominoRanker,
    PreflightSieve,
    SemanticDeduplicator,
    SeverityCalibrator,
    TailTriager,
    TypeSafeClient,
    generate_markdown_report,
)


class TestTypeSafeValidatorEngineOffline(unittest.TestCase):
    """Tests all engine components when TYPESAFE_API_KEY is unset (offline fallback mode)."""

    def setUp(self):
        # Explicitly disable TypeSafeClient
        self.client = TypeSafeClient(api_key=None)
        self.assertFalse(self.client.enabled)

    def test_offline_dedup_and_quorum(self):
        dedup = SemanticDeduplicator(self.client)

        skeptic_lists = [
            ("skeptic-1", [
                {"id": "timeout-missing", "failure": "No network timeout configured on client request.", "severity": "high"},
                {"id": "sql-injection-risk", "failure": "Raw SQL query concatenation in findUser.", "severity": "critical"}
            ]),
            ("skeptic-2", [
                {"id": "timeout-unspecified", "failure": "Missing timeout on network client call causes hanging.", "severity": "high"},
                {"id": "typo-in-docs", "failure": "Spelling mistake in readme.", "severity": "low"}
            ]),
            ("skeptic-3", [
                {"id": "client-timeout-gap", "failure": "Network client has no timeout defined.", "severity": "medium"}
            ])
        ]

        clusters = dedup.cluster_findings(skeptic_lists)
        # Should have clusters
        self.assertTrue(len(clusters) >= 2)

        # Timeout finding should be clustered across multiple skeptics
        timeout_cluster = next((c for c in clusters if "timeout" in c["id"].lower()), None)
        self.assertIsNotNone(timeout_cluster)
        self.assertTrue(timeout_cluster["vote_count"] >= 2)
        self.assertTrue(timeout_cluster["is_confirmed"])

    def test_offline_severity_calibration(self):
        calibrator = SeverityCalibrator(self.client)
        cluster = {
            "id": "timeout-issue",
            "representative": {"failure": "Client hangs", "evidence": "client.py:42"},
            "findings": [
                {"severity": "high"},
                {"severity": "high"},
                {"severity": "critical"}
            ]
        }
        res = calibrator.calibrate(cluster)
        self.assertEqual(res["source"], "offline-fallback")
        self.assertIn(res["label"], ["high", "critical"])
        self.assertGreaterEqual(res["score"], 2.5)

    def test_offline_tail_triage(self):
        triager = TailTriager(self.client)
        high_cluster = {
            "id": "solo-critical-catch",
            "representative": {"failure": "Memory leak", "confidence": "high"}
        }
        low_cluster = {
            "id": "solo-nitpick",
            "representative": {"failure": "Indent issue", "confidence": "low"}
        }
        res_high = triager.triage(high_cluster)
        res_low = triager.triage(low_cluster)

        self.assertGreaterEqual(res_high["probability_defect"], 0.6)
        self.assertLessEqual(res_low["probability_defect"], 0.4)
        self.assertEqual(res_low["verdict"], "discarded")

    def test_offline_preflight_spec(self):
        sieve = PreflightSieve(self.client)
        vague_spec = "# Spec\nSystem must be blazingly fast and ultra-scalable. Users log in."
        res = sieve.screen_spec(vague_spec)
        self.assertFalse(res["passed"])
        self.assertGreater(res["warning_count"], 0)
        checks = [w["check"] for w in res["warnings"]]
        self.assertIn("has_untestable_buzzwords", checks)

    def test_offline_preflight_plan(self):
        sieve = PreflightSieve(self.client)
        vague_plan = "# Plan\nStep 1: Write code.\nStep 2: Verify it works properly."
        res = sieve.screen_plan(vague_plan)
        self.assertFalse(res["passed"])
        self.assertGreater(res["warning_count"], 0)
        checks = [w["check"] for w in res["warnings"]]
        self.assertIn("has_unverifiable_steps", checks)

    def test_offline_first_domino(self):
        ranker = FirstDominoRanker(self.client)
        clusters = [
            {"id": "step4-bug", "representative": {"step": "Step 4", "failure": "Method missing"}},
            {"id": "step2-schema-bug", "representative": {"step": "Step 2", "failure": "Table missing"}},
        ]
        res = ranker.rank(clusters)
        self.assertEqual(res["first_domino"], "step2-schema-bug")


class TestTypeSafeValidatorEngineMocked(unittest.TestCase):
    """Tests engine when TypeSafe System One API returns answers."""

    def setUp(self):
        self.client = TypeSafeClient(api_key="mock-api-key")
        self.assertTrue(self.client.enabled)

    @patch("urllib.request.urlopen")
    def test_typesafe_semantic_dedup(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "model": "jev-latest",
            "answers": {
                "relationship": {
                    "type": "choice",
                    "choice": "same_defect",
                    "confidence": 0.95
                }
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        dedup = SemanticDeduplicator(self.client)
        f1 = {"id": "timeout-omitted", "failure": "Request never times out."}
        f2 = {"id": "missing-request-deadline", "failure": "No deadline set on socket connection."}

        same, conf = dedup.are_same_root_cause(f1, f2)
        self.assertTrue(same)
        self.assertGreaterEqual(conf, 0.9)

    @patch("urllib.request.urlopen")
    def test_typesafe_tail_triage_promoted(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "model": "jev-latest",
            "answers": {
                "is_genuine_defect": {
                    "type": "noul",
                    "noul": 0.92,
                    "confidence": 0.88
                }
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        triager = TailTriager(self.client)
        cluster = {
            "id": "critical-race-condition",
            "representative": {"failure": "Data race on cache access under load."}
        }
        res = triager.triage(cluster)
        self.assertEqual(res["verdict"], "promoted")
        self.assertEqual(res["probability_defect"], 0.92)

    @patch("urllib.request.urlopen")
    def test_typesafe_severity_calibration(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "model": "jev-latest",
            "answers": {
                "calibrated_severity": {
                    "type": "score",
                    "score": 3.42,
                    "confidence": 0.91,
                    "probabilities": [0.01, 0.04, 0.45, 0.50]
                }
            }
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        calibrator = SeverityCalibrator(self.client)
        cluster = {
            "id": "data-corruption",
            "representative": {"failure": "Corrupts user records"},
            "findings": [{"severity": "critical"}]
        }
        res = calibrator.calibrate(cluster)
        self.assertEqual(res["label"], "critical")
        self.assertEqual(res["score"], 3.42)
        self.assertEqual(res["source"], "typesafe-score")

    def test_generate_markdown_report(self):
        confirmed = [{
            "id": "step2-missing-column",
            "vote_count": 2,
            "reporters": ["skeptic-1", "skeptic-2"],
            "representative": {
                "step": "Step 2",
                "failure": "Missing column in schema",
                "evidence": "schema.sql:10",
                "fix": "Add column definition"
            }
        }]
        unconfirmed = [{
            "id": "minor-comment",
            "vote_count": 1,
            "reporters": ["skeptic-3"],
            "representative": {
                "failure": "Formatting inconsistency",
                "evidence": "main.py:1"
            }
        }]
        calibrated = {
            "step2-missing-column": {"score": 3.0, "label": "high"}
        }

        md = generate_markdown_report(
            stage="plan",
            target_path="plans/milestone-1/plan.md",
            confirmed_clusters=confirmed,
            unconfirmed_clusters=unconfirmed,
            calibrated_severities=calibrated,
            first_domino="step2-missing-column",
        )

        self.assertIn("# Adversarial Plan Validation Report", md)
        self.assertIn("First Domino", md)
        self.assertIn("step2-missing-column", md)
        self.assertIn("HIGH / Score: 3.0", md)
        self.assertIn("minor-comment", md)


if __name__ == "__main__":
    unittest.main()
