#!/usr/bin/env python3
"""Generate an interactive dark-mode HTML post-run report for native AGY /swarm runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from swarm_telemetry import (  # noqa: E402
    list_swarm_runs,
    parse_swarm_run,
    resolve_agy_dir,
    resolve_workspace_root,
    select_swarm_run,
)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Swarm Post-Run Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0f1d;
      --panel-dark: rgba(16, 22, 38, 0.80);
      --panel-elevated: rgba(22, 30, 50, 0.90);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-glowing: rgba(13, 148, 136, 0.50);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;

      --glow-purple: #7c3aed;
      --glow-blue: #0284c7;
      --glow-teal: #0d9488;
      --glow-pink: #db2777;
      --glow-orange: #ea580c;
      --glow-green: #10b981;
      --glow-amber: #f59e0b;
      --glow-red: #ef4444;

      --gradient-primary: linear-gradient(135deg, #0d9488, #0284c7);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(at 0% 0%, rgba(13, 148, 136, 0.16) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(2, 132, 199, 0.14) 0px, transparent 50%),
        radial-gradient(at 50% 45%, rgba(124, 58, 237, 0.09) 0px, transparent 60%);
      background-attachment: fixed;
      font-family: 'Inter', sans-serif;
      color: var(--text-main);
      line-height: 1.55;
      overflow-x: hidden;
      padding-bottom: 80px;
    }

    header {
      padding: 24px 20px 18px;
      text-align: center;
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(14px);
      background-color: rgba(10, 15, 29, 0.80);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-content { max-width: 1340px; margin: 0 auto; }

    .badge-row {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }

    .badge-swarm {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(13, 148, 136, 0.18);
      border: 1px solid rgba(13, 148, 136, 0.45);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #5eead4;
    }

    .badge-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 11px;
      border-radius: 20px;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .pill-ok { background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(16, 185, 129, 0.38); color: #6ee7b7; }
    .pill-warn { background: rgba(245, 158, 11, 0.16); border: 1px solid rgba(245, 158, 11, 0.38); color: #fcd34d; }
    .pill-fail { background: rgba(239, 68, 68, 0.16); border: 1px solid rgba(239, 68, 68, 0.38); color: #fca5a5; }
    .pill-info { background: rgba(2, 132, 199, 0.16); border: 1px solid rgba(2, 132, 199, 0.38); color: #7dd3fc; }

    .badge-meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 11px;
      border-radius: 20px;
      font-family: 'Fira Code', monospace;
      font-size: 0.74rem;
      color: var(--text-muted);
      cursor: pointer;
    }
    .badge-meta:hover { border-color: var(--border-glowing); color: var(--text-main); }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.05rem;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 30%, #5eead4 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 5px;
      letter-spacing: -0.6px;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.9rem;
      max-width: 960px;
      margin: 0 auto 14px;
    }

    .controls {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px;
      max-width: 1200px;
      margin: 0 auto;
    }

    .search-container { position: relative; flex: 1 1 260px; max-width: 360px; }

    .search-input {
      width: 100%;
      background: rgba(16, 22, 38, 0.92);
      border: 1px solid var(--border-color);
      padding: 8px 14px 8px 36px;
      border-radius: 10px;
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      font-size: 0.86rem;
      outline: none;
      transition: all 0.2s ease;
    }
    .search-input:focus {
      border-color: var(--glow-teal);
      box-shadow: 0 0 14px rgba(13, 148, 136, 0.28);
    }

    .search-icon {
      position: absolute;
      left: 11px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
    }

    .filter-btn {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 7px 13px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 0.81rem;
      font-weight: 500;
      transition: all 0.2s ease;
    }
    .filter-btn:hover { background: rgba(255, 255, 255, 0.08); color: var(--text-main); }
    .filter-btn.active {
      background: var(--gradient-primary);
      border-color: transparent;
      color: white;
      box-shadow: 0 4px 12px rgba(13, 148, 136, 0.35);
    }

    .filter-banner {
      display: none;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin: 10px auto 0;
      padding: 6px 14px;
      max-width: 960px;
      border-radius: 10px;
      background: rgba(13, 148, 136, 0.12);
      border: 1px solid rgba(13, 148, 136, 0.35);
      font-size: 0.78rem;
      color: #ccfbf1;
    }
    .filter-banner.visible { display: flex; }
    .clear-filter-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #f8fafc;
      padding: 2px 9px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-weight: 600;
      cursor: pointer;
    }
    .clear-filter-btn:hover { background: rgba(255, 255, 255, 0.16); }
    .metric-hi { color: #5eead4 !important; font-weight: 700 !important; }

    .container {
      max-width: 1340px;
      margin: 26px auto;
      padding: 0 20px;
    }

    /* Summary KPI Grid */
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 13px;
      margin-bottom: 18px;
    }

    .kpi-card {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 15px 17px;
      backdrop-filter: blur(10px);
    }
    .kpi-label {
      font-size: 0.71rem;
      text-transform: uppercase;
      letter-spacing: 0.7px;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 5px;
    }
    .kpi-value {
      font-family: 'Outfit', sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.2;
    }
    .kpi-sub {
      font-size: 0.76rem;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: 'Fira Code', monospace;
    }

    /* Insights Strip */
    .insights-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }
    .insight-card {
      background: rgba(16, 22, 38, 0.65);
      border: 1px solid var(--border-color);
      border-left: 3px solid var(--glow-teal);
      border-radius: 10px;
      padding: 11px 14px;
    }
    .insight-card.kind-tokens { border-left-color: var(--glow-purple); }
    .insight-card.kind-timing { border-left-color: var(--glow-amber); }
    .insight-card.kind-overhead { border-left-color: var(--glow-blue); }
    .insight-card.kind-warning { border-left-color: var(--glow-red); }
    .insight-title { font-size: 0.82rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
    .insight-detail { font-size: 0.78rem; color: var(--text-muted); }

    /* Section Panels */
    .section-panel {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 20px 22px;
      margin-bottom: 24px;
      backdrop-filter: blur(12px);
    }

    .section-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 14px;
    }
    .section-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.15rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .section-sub { font-size: 0.81rem; color: var(--text-muted); }

    .toggle-group {
      display: inline-flex;
      background: rgba(10, 15, 29, 0.85);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 3px;
      gap: 3px;
    }
    .toggle-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.76rem;
      font-weight: 600;
      padding: 5px 11px;
      border-radius: 7px;
      cursor: pointer;
    }
    .toggle-btn.active { background: var(--gradient-primary); color: #ffffff; }

    /* Verification Gate */
    .verify-banner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      padding: 13px 16px;
      border-radius: 12px;
      margin-bottom: 14px;
      background: rgba(10, 15, 29, 0.70);
      border: 1px solid var(--border-color);
    }
    .verify-banner.verdict-VERIFIED { border-color: rgba(16, 185, 129, 0.42); background: rgba(16, 185, 129, 0.08); }
    .verify-banner.verdict-STALE, .verify-banner.verdict-PARTIAL, .verify-banner.verdict-SELF_CHECKED, .verify-banner.verdict-VERIFIED_WITH_CAVEATS {
      border-color: rgba(245, 158, 11, 0.42); background: rgba(245, 158, 11, 0.08);
    }
    .verify-banner.verdict-FAILED, .verify-banner.verdict-UNVERIFIED {
      border-color: rgba(239, 68, 68, 0.42); background: rgba(239, 68, 68, 0.08);
    }

    .cmd-table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'Fira Code', monospace;
      font-size: 0.74rem;
    }
    .cmd-table th, .cmd-table td {
      text-align: left;
      padding: 7px 10px;
      border-bottom: 1px solid var(--border-color);
      vertical-align: top;
    }
    .cmd-table th { color: var(--text-muted); font-weight: 600; font-family: 'Inter', sans-serif; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .cmd-code { max-width: 560px; word-break: break-word; color: #e2e8f0; }

    /* Resource Breakdown Bars */
    .breakdown-grid {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 18px;
      margin-bottom: 16px;
    }
    @media (max-width: 920px) { .breakdown-grid { grid-template-columns: 1fr; } }

    .bar-list { display: flex; flex-direction: column; gap: 9px; }
    .bar-row {
      display: grid;
      grid-template-columns: 170px 1fr 125px;
      align-items: center;
      gap: 10px;
      font-size: 0.79rem;
    }
    .bar-label { font-family: 'Fira Code', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-main); cursor: pointer; }
    .bar-label:hover { color: #5eead4; }
    .bar-track {
      height: 16px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
    }
    .bar-seg-in { background: #38bdf8; height: 100%; }
    .bar-seg-out { background: #c084fc; height: 100%; }
    .bar-seg-cache { background: rgba(13, 148, 136, 0.65); height: 100%; }
    .bar-seg-active { background: linear-gradient(90deg, #0d9488, #10b981); height: 100%; }
    .bar-seg-wait { background: rgba(245, 158, 11, 0.35); height: 100%; }
    .bar-val { font-family: 'Fira Code', monospace; font-size: 0.73rem; text-align: right; color: var(--text-muted); }

    .legend-row {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      font-size: 0.74rem;
      color: var(--text-muted);
      margin-top: 8px;
    }
    .legend-item { display: inline-flex; align-items: center; gap: 6px; }
    .legend-dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }

    /* Gantt Waterfall */
    .gantt-axis {
      display: grid;
      grid-template-columns: 230px 1fr 130px;
      gap: 12px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-dim);
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 8px;
    }
    .gantt-axis-track { position: relative; height: 22px; display: flex; justify-content: space-between; align-items: flex-end; }
    .gantt-marker-pin {
      position: absolute;
      top: 0;
      transform: translateX(-50%);
      font-size: 0.66rem;
      padding: 1px 5px;
      border-radius: 4px;
      background: rgba(16, 185, 129, 0.16);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #6ee7b7;
      white-space: nowrap;
      cursor: default;
    }
    .gantt-marker-pin.mk-stall {
      background: rgba(245, 158, 11, 0.18);
      border-color: rgba(245, 158, 11, 0.45);
      color: #fcd34d;
    }

    .gantt-rows { display: flex; flex-direction: column; gap: 7px; }
    .gantt-row {
      display: grid;
      grid-template-columns: 230px 1fr 130px;
      gap: 12px;
      align-items: center;
      padding: 5px 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .gantt-row:hover { background: rgba(255, 255, 255, 0.04); }
    .gantt-label { display: flex; align-items: center; gap: 7px; overflow: hidden; }
    .gantt-name { font-size: 0.81rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .gantt-track {
      position: relative;
      height: 22px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 6px;
      overflow: hidden;
    }
    .gantt-wait-bar {
      position: absolute;
      top: 6px;
      height: 10px;
      border-radius: 3px;
      background: repeating-linear-gradient(
        -45deg,
        rgba(148, 163, 184, 0.14),
        rgba(148, 163, 184, 0.14) 4px,
        rgba(148, 163, 184, 0.04) 4px,
        rgba(148, 163, 184, 0.04) 8px
      );
      border: 1px dashed rgba(148, 163, 184, 0.28);
    }
    .gantt-turn-bar {
      position: absolute;
      top: 3px;
      height: 16px;
      border-radius: 4px;
      min-width: 3px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
    }
    .bar-cat-coordinator { background: linear-gradient(90deg, #7c3aed, #6366f1); }
    .bar-cat-research_plan { background: linear-gradient(90deg, #0284c7, #38bdf8); }
    .bar-cat-author { background: linear-gradient(90deg, #db2777, #a855f7); }
    .bar-cat-verifier { background: linear-gradient(90deg, #0d9488, #10b981); }
    .bar-cat-monitor, .bar-cat-narrator { background: linear-gradient(90deg, #64748b, #94a3b8); }
    .gantt-dur { font-family: 'Fira Code', monospace; font-size: 0.72rem; text-align: right; color: var(--text-muted); }

    /* Worker Deliverable Cards */
    .cards-grid { display: flex; flex-direction: column; gap: 14px; }
    .agent-card {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 15px;
      padding: 18px 20px;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .agent-card:hover { border-color: var(--border-glowing); }
    .agent-card.highlighted { border-color: #5eead4; box-shadow: 0 0 24px rgba(13, 148, 136, 0.38); }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 10px;
    }
    .card-title-group { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
    .agent-name { font-family: 'Outfit', sans-serif; font-size: 1.15rem; font-weight: 700; color: #fff; }

    .role-tag {
      font-size: 0.69rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 7px;
      letter-spacing: 0.4px;
    }
    .rt-coordinator { background: rgba(124, 58, 237, 0.20); color: #c4b5fd; border: 1px solid rgba(124, 58, 237, 0.40); }
    .rt-research_plan { background: rgba(2, 132, 199, 0.18); color: #7dd3fc; border: 1px solid rgba(2, 132, 199, 0.40); }
    .rt-author { background: rgba(219, 39, 119, 0.18); color: #f9a8d4; border: 1px solid rgba(219, 39, 119, 0.40); }
    .rt-verifier { background: rgba(16, 185, 129, 0.18); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.40); }
    .rt-monitor, .rt-narrator { background: rgba(100, 116, 139, 0.22); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.35); }

    .life-pill {
      font-size: 0.69rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 7px;
    }
    .lp-completed_retired, .lp-completed_active { background: rgba(16, 185, 129, 0.14); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.32); }
    .lp-observer_active, .lp-observer_retired, .lp-active { background: rgba(56, 189, 248, 0.14); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.32); }
    .lp-waiting_incomplete, .lp-not_started { background: rgba(245, 158, 11, 0.16); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.35); }
    .lp-killed_incomplete { background: rgba(239, 68, 68, 0.16); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.35); }

    .model-badge {
      font-family: 'Fira Code', monospace;
      font-size: 0.71rem;
      padding: 3px 8px;
      border-radius: 7px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      color: #cbd5e1;
    }

    .telemetry-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 10px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
    }
    .telemetry-pill {
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid var(--border-color);
      padding: 2px 8px;
      border-radius: 6px;
    }

    .deliverable-box {
      background: rgba(10, 15, 29, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.07);
      border-radius: 10px;
      padding: 12px 14px;
      margin-bottom: 10px;
    }
    .deliverable-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #5eead4;
    }
    .deliverable-text {
      font-size: 0.83rem;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 280px;
      overflow-y: auto;
    }

    .sub-details {
      border: 1px solid var(--border-color);
      border-radius: 9px;
      background: rgba(255, 255, 255, 0.02);
      margin-top: 8px;
      overflow: hidden;
    }
    .sub-details summary {
      padding: 7px 12px;
      font-size: 0.79rem;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
    }
    .sub-details summary:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.03); }
    .sub-details-body { padding: 10px 12px; border-top: 1px solid var(--border-color); font-size: 0.8rem; }

    .files-strip { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .doc-link-item {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(56, 189, 248, 0.07);
      border: 1px solid rgba(56, 189, 248, 0.25);
      padding: 3px 9px;
      border-radius: 7px;
      font-family: 'Fira Code', monospace;
      font-size: 0.73rem;
      text-decoration: none;
      color: #7dd3fc;
    }
    .doc-link-item:hover { background: rgba(56, 189, 248, 0.16); border-color: #38bdf8; }

    /* Board Archive */
    .board-post {
      background: rgba(10, 15, 29, 0.66);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 11px 14px;
      margin-bottom: 8px;
    }
    .board-post-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 5px;
      font-size: 0.78rem;
    }
    .board-seq { font-family: 'Fira Code', monospace; color: #5eead4; font-weight: 700; }
    .board-body {
      font-size: 0.81rem;
      color: #cbd5e1;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 220px;
      overflow-y: auto;
    }

    .handoff-chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 10px;
      border-radius: 8px;
      font-family: 'Fira Code', monospace;
      font-size: 0.73rem;
      color: #cbd5e1;
    }

    .copied-toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--gradient-primary);
      padding: 10px 18px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.86rem;
      color: white;
      box-shadow: 0 10px 25px rgba(13, 148, 136, 0.4);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s ease;
      z-index: 1000;
    }
    .copied-toast.show { transform: translateY(0); opacity: 1; }

    @media (max-width: 820px) {
      .gantt-axis, .gantt-row { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 130px 1fr 100px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div class="badge-row">
        <div class="badge-swarm">AGY /swarm Post-Run Report</div>
        <div class="badge-pill" id="outcomeBadge"></div>
        <div class="badge-pill" id="verifyBadge"></div>
        <div class="badge-meta" id="tzBadge"></div>
        <div class="badge-meta" id="rootIdBadge" title="Click to copy swarm conversation ID"></div>
      </div>
      <h1 id="runTitle">Swarm Execution Report</h1>
      <p class="subtitle" id="runSubtitle"></p>
      <div class="controls">
        <div class="search-container">
          <svg class="search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search worker, deliverable, #seq, file, command, or model...">
        </div>
        <button type="button" class="filter-btn active" data-action="role-filter" data-role="all">All Members</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="author">Authors</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="research_plan">Research &amp; Plan</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="verifier">Verifiers</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="coordinator">Coordinator</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="observers">Monitor / Narrator</button>
      </div>
      <div class="filter-banner" id="filterBanner"></div>
    </div>
  </header>

  <div class="container">
    <section class="summary-grid" id="summaryGrid"></section>
    <section class="insights-grid" id="insightsGrid"></section>
    <section class="section-panel" id="verificationPanel"></section>
    <section class="section-panel" id="resourcesPanel"></section>
    <section class="section-panel" id="ganttPanel"></section>
    <section class="section-panel" id="deliverablesPanel"></section>
    <section class="section-panel" id="boardPanel"></section>
  </div>

  <div class="copied-toast" id="copiedToast">Copied to clipboard!</div>

  <script>
    const telemetry = __TELEMETRY_DATA_PLACEHOLDER__;
    let activeRoleFilter = 'all';
    let resourceMetric = 'total_tokens';
    let ganttScaleMode = (telemetry.gantt && telemetry.gantt.has_compressed_gaps) ? 'compressed' : 'true';
    let ganttShowWaits = true;
    let boardFilter = 'all';
    let boardChannelFilter = 'all';

    function escapeHtml(val) {
      return String(val == null ? '' : val)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function formatTokens(n) {
      const v = Number(n || 0);
      if (v >= 1_000_000) return (v / 1_000_000).toFixed(2) + 'M';
      if (v >= 1_000) return (v / 1_000).toFixed(1) + 'k';
      return String(v);
    }

    function formatSecs(s) {
      const v = Math.round(Number(s || 0));
      if (v <= 0) return '0s';
      const h = Math.floor(v / 3600);
      const m = Math.floor((v % 3600) / 60);
      const sec = v % 60;
      const parts = [];
      if (h) parts.push(h + 'h');
      if (m) parts.push(m + 'm');
      if (sec) parts.push(sec + 's');
      return parts.join(' ');
    }

    function renderHeader() {
      const s = telemetry.summary || {};
      const v = telemetry.verification || {};

      const oBadge = document.getElementById('outcomeBadge');
      oBadge.textContent = (s.outcome_label || 'Completed');
      oBadge.className = 'badge-pill ' + (s.outcome === 'completed' ? 'pill-ok' : 'pill-warn');

      const vBadge = document.getElementById('verifyBadge');
      vBadge.textContent = v.verdict_label || 'Unverified';
      vBadge.className = 'badge-pill ' + (
        v.verdict === 'VERIFIED' ? 'pill-ok' :
        (v.verdict === 'FAILED' || v.verdict === 'UNVERIFIED' ? 'pill-fail' : 'pill-warn')
      );

      document.getElementById('tzBadge').textContent = telemetry.tz_label || 'LOCAL';
      const rootBadge = document.getElementById('rootIdBadge');
      const cid = telemetry.root_conversation_id || 'unknown';
      rootBadge.textContent = 'Swarm: ' + cid.slice(0, 8);
      rootBadge.onclick = (e) => copyId(cid, e);

      document.getElementById('runTitle').textContent = telemetry.run_title || 'Swarm Execution Report';
      const tailNote = s.monitor_tail_label ? ` (+${s.monitor_tail_label} monitor tail)` : '';
      document.getElementById('runSubtitle').textContent =
        `${telemetry.workspace_root || ''} • ${s.wall_start_local || '—'} → ${s.wall_end_local || '—'} (${s.core_wall_span_label || '—'}${tailNote})`;
    }

    function renderSummary() {
      const s = telemetry.summary || {};
      const v = telemetry.verification || {};
      const tok = s.tokens || {};
      const models = (s.models_used || []).join(', ') || 'default';

      const cards = [
        {
          label: 'Workers Delivered',
          value: `${s.completed_workers || 0}/${s.worker_count || 0}`,
          sub: `${s.retired_workers || 0} retired cleanly · ${s.done_post_count || 0} [done] posts`
        },
        {
          label: 'Wall-Clock Span',
          value: s.core_wall_span_label || '0s',
          sub: `Active work ${s.cumulative_active_label || '0s'} · Parked ${s.cumulative_wait_label || '0s'}`
        },
        {
          label: 'Parallelism & Speedup',
          value: `${s.parallelism_speedup || 1}x`,
          sub: `Peak active workers: ${s.peak_worker_concurrency || 0} · Merged: ${s.merged_active_label || '0s'}`
        },
        {
          label: 'Total Tokens',
          value: formatTokens(tok.total),
          sub: `In ${formatTokens(tok.input)} · Out ${formatTokens(tok.output)} · Cache ${formatTokens(tok.cache_read)} (${tok.cache_hit_pct || 0}%)`
        },
        {
          label: 'Agents & Models',
          value: `${s.total_agents || 0} Members`,
          sub: `${models} · ${s.total_tool_calls || 0} tool calls`
        },
        {
          label: 'Verification & Files',
          value: v.verdict === 'VERIFIED' ? 'CHECKED ✓' : (v.verdict || 'UNVERIFIED'),
          sub: `${v.passed_count || 0} passed · ${v.unresolved_failure_count || 0} unresolved · ${s.unique_file_count || 0} files`
        }
      ];

      document.getElementById('summaryGrid').innerHTML = cards.map(c => `
        <div class="kpi-card">
          <div class="kpi-label">${escapeHtml(c.label)}</div>
          <div class="kpi-value">${escapeHtml(c.value)}</div>
          <div class="kpi-sub">${escapeHtml(c.sub)}</div>
        </div>
      `).join('');

      const ins = telemetry.insights || [];
      document.getElementById('insightsGrid').innerHTML = ins.map(item => `
        <div class="insight-card kind-${escapeHtml(item.kind)}">
          <div class="insight-title">${escapeHtml(item.title)}</div>
          <div class="insight-detail">${escapeHtml(item.detail)}</div>
        </div>
      `).join('');
    }

    function matchesRoleOnly(a) {
      if (!a) return false;
      if (activeRoleFilter === 'observers') {
        return a.role_category === 'monitor' || a.role_category === 'narrator';
      }
      if (activeRoleFilter !== 'all') {
        return a.role_category === activeRoleFilter;
      }
      return true;
    }

    function getSearchQuery() {
      const inp = document.getElementById('searchInput');
      return (inp && inp.value ? inp.value : '').trim().toLowerCase();
    }

    function getFilteredAgents() {
      return (telemetry.agents || []).filter(a => matchesFilter(a.conv_id));
    }

    function filterVerificationCommands(cmds) {
      const q = getSearchQuery();
      const allowedNames = new Set((telemetry.agents || []).filter(matchesRoleOnly).map(a => a.name));
      return (cmds || []).filter(c => {
        if (activeRoleFilter !== 'all' && c.agent && !allowedNames.has(c.agent)) return false;
        if (!q) return true;
        const hay = `${c.agent || ''} ${c.command || ''} ${c.status || ''} ${c.ts_local || ''}`.toLowerCase();
        return hay.includes(q);
      });
    }

    function renderVerification() {
      const v = telemetry.verification || {};
      const allCmds = (v.verifier_commands && v.verifier_commands.length > 0)
        ? v.verifier_commands
        : (v.author_check_commands || []);
      const cmds = filterVerificationCommands(allCmds);
      const q = getSearchQuery();
      const isFiltered = activeRoleFilter !== 'all' || q !== '';

      const pillCls = v.verdict === 'VERIFIED' ? 'pill-ok' : (v.verdict === 'FAILED' || v.verdict === 'UNVERIFIED' ? 'pill-fail' : 'pill-warn');
      const orderNote = v.ordered_after_edits
        ? `Ordered after last author edit (${v.last_author_edit_local || '—'} ≤ ${v.verifier_last_local || '—'})`
        : `Warning: edits occurred at ${v.last_author_edit_local || '—'} after last check (${v.verifier_last_local || '—'})`;

      const earlierNote = v.resolved_earlier_failure_count > 0
        ? ` · ${v.resolved_earlier_failure_count} earlier probe(s) resolved before final pass`
        : '';

      const reportText = v.latest_verifier_report || '';
      const reportMatches = !q || reportText.toLowerCase().includes(q) || (v.verifier_names || []).some(n => n.toLowerCase().includes(q));
      const reportBlock = (reportText && (activeRoleFilter === 'all' || activeRoleFilter === 'verifier') && reportMatches) ? `
        <details class="sub-details" ${q ? 'open' : ''}>
          <summary>Verifier Final Report (${escapeHtml((v.verifier_names || []).join(', ') || 'verifier')}) — click to expand full report</summary>
          <div class="sub-details-body">
            <div class="deliverable-text" style="max-height:220px;">${escapeHtml(reportText)}</div>
          </div>
        </details>` : '';

      const countLabel = isFiltered ? `${cmds.length} of ${allCmds.length} matching` : `${allCmds.length} total`;
      const cmdRows = allCmds.length ? `
        <details class="sub-details" ${(v.verdict !== 'VERIFIED' || q) ? 'open' : ''}>
          <summary>Executed Check Commands (${countLabel} · ${v.passed_count || 0} passed · ${v.failed_count || 0} failed${escapeHtml(earlierNote)})</summary>
          <div class="sub-details-body" style="overflow-x:auto;">
            ${cmds.length ? `<table class="cmd-table">
              <thead>
                <tr><th>Time</th><th>Agent</th><th>Status</th><th>Command</th></tr>
              </thead>
              <tbody>
                ${cmds.map(c => {
                  const stPill = c.status === 'passed' ? 'pill-ok' : (c.status === 'failed' ? 'pill-fail' : 'pill-warn');
                  const stTxt = c.status === 'passed' ? 'PASS (0)' : (c.status === 'failed' ? `FAIL (${c.exit_code})` : c.status.toUpperCase());
                  return `<tr>
                    <td>${escapeHtml(c.ts_local || '—')}</td>
                    <td>${escapeHtml(c.agent || '')}</td>
                    <td><span class="badge-pill ${stPill}" style="font-size:0.65rem;padding:2px 7px;">${escapeHtml(stTxt)}</span></td>
                    <td class="cmd-code">${escapeHtml(c.command)}</td>
                  </tr>`;
                }).join('')}
              </tbody>
            </table>` : '<div class="section-sub">No check commands match the active search or role filter.</div>'}
          </div>
        </details>` : '<div class="section-sub">No verification commands were recorded in transcripts.</div>';

      document.getElementById('verificationPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Verification &amp; Quality Gate <span class="badge-pill ${pillCls}">${escapeHtml(v.verdict_label || 'Unverified')}</span></div>
            <div class="section-sub">${escapeHtml(orderNote)}</div>
          </div>
        </div>
        <div class="verify-banner verdict-${escapeHtml(v.verdict || 'UNVERIFIED')}">
          <div>
            <strong>Verifiers:</strong> ${escapeHtml((v.verifier_names || []).join(', ') || 'None assigned')} ·
            <strong>[done] reports:</strong> ${escapeHtml(v.verifier_done_count || 0)} ·
            <strong>Checks:</strong> ${escapeHtml(v.passed_count || 0)} passed, ${escapeHtml(v.unresolved_failure_count || 0)} unresolved failures${escapeHtml(earlierNote)}
          </div>
        </div>
        ${reportBlock}
        ${cmdRows}
      `;
    }

    function setResourceMetric(metric, btn) {
      resourceMetric = metric;
      renderResources();
    }

    function renderResources() {
      const allAgents = telemetry.agents || [];
      const agents = getFilteredAgents();
      const q = getSearchQuery();
      const isFiltered = activeRoleFilter !== 'all' || q !== '';
      const roles = (telemetry.role_rollups || []).filter(r => {
        if (activeRoleFilter === 'observers') return r.category === 'monitor' || r.category === 'narrator';
        if (activeRoleFilter !== 'all') return r.category === activeRoleFilter;
        return agents.some(a => a.role_category === r.category);
      });
      const totTokens = (telemetry.summary && telemetry.summary.tokens && telemetry.summary.tokens.total) || 1;

      function metricValue(a) {
        if (resourceMetric === 'fresh_tokens') return a.tokens.fresh || 0;
        if (resourceMetric === 'output_tokens') return a.tokens.output || 0;
        if (resourceMetric === 'active_time') return a.active_duration_s || 0;
        if (resourceMetric === 'wait_time') return a.wait_duration_s || 0;
        return a.tokens.total || 0;
      }

      const sorted = [...agents].sort((a, b) => metricValue(b) - metricValue(a));
      const maxVal = Math.max(1, ...sorted.map(metricValue));

      const barsHtml = sorted.length ? sorted.map(a => {
        const val = metricValue(a);
        const pct = Math.max(1, (val / maxVal) * 100);
        let segs = '';
        let rightLabel = '';
        if (resourceMetric === 'active_time' || resourceMetric === 'wait_time') {
          const actW = (a.active_duration_s / maxVal) * 100;
          const waitW = (a.wait_duration_s / maxVal) * 100;
          if (resourceMetric === 'active_time') {
            segs = `<div class="bar-seg-active" style="width:${pct.toFixed(2)}%" title="Active: ${escapeHtml(a.active_duration_label)}"></div>`;
            rightLabel = `${a.active_duration_label}`;
          } else {
            segs = `<div class="bar-seg-active" style="width:${actW.toFixed(2)}%" title="Active: ${escapeHtml(a.active_duration_label)}"></div><div class="bar-seg-wait" style="width:${waitW.toFixed(2)}%" title="Wait: ${escapeHtml(a.wait_duration_label)}"></div>`;
            rightLabel = `${a.wait_duration_label} wait (${a.active_duration_label} act)`;
          }
        } else if (resourceMetric === 'output_tokens') {
          segs = `<div class="bar-seg-out" style="width:${pct.toFixed(2)}%"></div>`;
          rightLabel = formatTokens(val);
        } else if (resourceMetric === 'fresh_tokens') {
          const inW = (a.tokens.input / maxVal) * 100;
          const outW = (a.tokens.output / maxVal) * 100;
          segs = `<div class="bar-seg-in" style="width:${inW.toFixed(2)}%"></div><div class="bar-seg-out" style="width:${outW.toFixed(2)}%"></div>`;
          rightLabel = `${formatTokens(val)} (in ${formatTokens(a.tokens.input)} + out ${formatTokens(a.tokens.output)})`;
        } else {
          const inW = (a.tokens.input / maxVal) * 100;
          const outW = (a.tokens.output / maxVal) * 100;
          const cacheW = (a.tokens.cache_read / maxVal) * 100;
          segs = `<div class="bar-seg-in" style="width:${inW.toFixed(2)}%"></div><div class="bar-seg-out" style="width:${outW.toFixed(2)}%"></div><div class="bar-seg-cache" style="width:${cacheW.toFixed(2)}%"></div>`;
          rightLabel = `${formatTokens(val)} (${((val / totTokens) * 100).toFixed(1)}%)`;
        }
        return `<div class="bar-row">
          <div class="bar-label" data-action="jump-agent" data-conv-id="${escapeHtml(a.conv_id)}" title="Jump to ${escapeHtml(a.name)}">${escapeHtml(a.name)}</div>
          <div class="bar-track">${segs}</div>
          <div class="bar-val">${escapeHtml(rightLabel)}</div>
        </div>`;
      }).join('') : '<div class="section-sub">No members match current search or role filter.</div>';

      const hiAct = resourceMetric === 'active_time' ? 'metric-hi' : '';
      const hiWait = resourceMetric === 'wait_time' ? 'metric-hi' : '';
      const hiFresh = resourceMetric === 'fresh_tokens' ? 'metric-hi' : '';
      const hiOut = resourceMetric === 'output_tokens' ? 'metric-hi' : '';
      const hiTot = resourceMetric === 'total_tokens' ? 'metric-hi' : '';

      const roleRows = roles.map(r => `
        <tr>
          <td><strong>${escapeHtml(r.label)}</strong> (${r.agent_count})</td>
          <td class="${hiAct}">${escapeHtml(r.active_duration_label)}</td>
          <td class="${hiWait}">${escapeHtml(r.wait_duration_label)}</td>
          <td class="${hiOut}">${escapeHtml(formatTokens(r.tokens_output))}</td>
          <td class="${hiFresh}">${escapeHtml(formatTokens(r.tokens_fresh))}</td>
          <td class="${hiTot}">${escapeHtml(formatTokens(r.tokens_total))} (${r.token_share_pct}%)</td>
        </tr>
      `).join('');

      const fullTable = sorted.map(a => `
        <tr>
          <td><a href="#agent-${escapeHtml(a.conv_id)}" data-action="jump-agent" data-conv-id="${escapeHtml(a.conv_id)}" style="color:#7dd3fc;text-decoration:none;">${escapeHtml(a.name)}</a></td>
          <td>${escapeHtml(a.role_label)}</td>
          <td>${escapeHtml(a.model)}</td>
          <td class="${hiAct}">${escapeHtml(a.active_duration_label)}</td>
          <td class="${hiWait}">${escapeHtml(a.wait_duration_label)}</td>
          <td>${a.turns.length}</td>
          <td>${escapeHtml(formatTokens(a.tokens.input))}</td>
          <td class="${hiOut}">${escapeHtml(formatTokens(a.tokens.output))}</td>
          <td>${escapeHtml(formatTokens(a.tokens.cache_read))} (${a.tokens.cache_hit_pct}%)</td>
          <td class="${hiTot}"><strong>${escapeHtml(formatTokens(a.tokens.total))}</strong> (${((a.tokens.total / totTokens) * 100).toFixed(1)}%)</td>
        </tr>
      `).join('');

      const scopeTxt = isFiltered ? ` (${agents.length} / ${allAgents.length} members shown)` : '';

      document.getElementById('resourcesPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Where Time &amp; Tokens Went${escapeHtml(scopeTxt)}</div>
            <div class="section-sub">Active execution vs free board parking (swarm_wait) and per-agent token consumption</div>
          </div>
          <div class="toggle-group" id="resToggles">
            <button type="button" class="toggle-btn ${resourceMetric === 'total_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="total_tokens">Total Tokens</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'fresh_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="fresh_tokens">Fresh (In+Out)</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'output_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="output_tokens">Output Tokens</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'active_time' ? 'active' : ''}" data-action="res-metric" data-metric="active_time">Active Time</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'wait_time' ? 'active' : ''}" data-action="res-metric" data-metric="wait_time">Wait vs Work</button>
          </div>
        </div>
        <div class="breakdown-grid">
          <div>
            <div class="bar-list">${barsHtml}</div>
            <div class="legend-row">
              <span class="legend-item"><span class="legend-dot" style="background:#38bdf8"></span>Input</span>
              <span class="legend-item"><span class="legend-dot" style="background:#c084fc"></span>Output</span>
              <span class="legend-item"><span class="legend-dot" style="background:rgba(13,148,136,0.75)"></span>Cache Read</span>
              <span class="legend-item"><span class="legend-dot" style="background:#10b981"></span>Active Work</span>
              <span class="legend-item"><span class="legend-dot" style="background:rgba(245,158,11,0.55)"></span>Parked Wait</span>
            </div>
          </div>
          <div style="overflow-x:auto;">
            <table class="cmd-table">
              <thead><tr><th>Role Group</th><th>Active</th><th>Parked</th><th>Output</th><th>In+Out</th><th>Total (%)</th></tr></thead>
              <tbody>${roleRows || '<tr><td colspan="6">No matching role groups</td></tr>'}</tbody>
            </table>
          </div>
        </div>
        <details class="sub-details">
          <summary>Per-Agent Resource Matrix (${agents.length} of ${allAgents.length} members)</summary>
          <div class="sub-details-body" style="overflow-x:auto;">
            <table class="cmd-table">
              <thead><tr><th>Member</th><th>Role</th><th>Model</th><th>Active</th><th>Parked</th><th>Turns</th><th>Input</th><th>Output</th><th>Cache (Hit)</th><th>Total (%)</th></tr></thead>
              <tbody>${fullTable}</tbody>
            </table>
          </div>
        </details>
      `;
    }

    function setGanttScale(mode) {
      ganttScaleMode = mode;
      renderGantt();
    }
    function toggleGanttWaits() {
      ganttShowWaits = !ganttShowWaits;
      renderGantt();
    }

    function renderGantt() {
      const g = telemetry.gantt || {};
      const allRows = g.rows || [];
      const rows = allRows.filter(r => matchesFilter(r.conv_id));
      const isComp = ganttScaleMode === 'compressed' && g.has_compressed_gaps;
      const markers = g.markers || [];

      const markerHtml = markers.map(mk => {
        const left = isComp ? mk.left_comp_pct : mk.left_true_pct;
        const cls = mk.kind === 'stall' ? 'mk-stall' : '';
        return `<div class="gantt-marker-pin ${cls}" style="left:${left}%" title="${escapeHtml(mk.label)}">#${escapeHtml(mk.seq)}</div>`;
      }).join('');

      const rowsHtml = rows.map(r => {
        const turns = isComp ? r.turns_comp : r.turns_true;
        const waits = isComp ? r.waits_comp : r.waits_true;
        const waitHtml = ganttShowWaits ? waits.map(w =>
          `<div class="gantt-wait-bar" style="left:${w.left_pct}%;width:${w.width_pct}%" title="Parked (${escapeHtml(w.reason)}): ${escapeHtml(w.start_local)} → ${escapeHtml(w.end_local)} (${escapeHtml(w.duration_label)})"></div>`
        ).join('') : '';
        const turnHtml = turns.map(t =>
          `<div class="gantt-turn-bar bar-cat-${escapeHtml(r.role_category)}" style="left:${t.left_pct}%;width:${t.width_pct}%" title="${escapeHtml(t.label)}: ${escapeHtml(t.start_local)} → ${escapeHtml(t.end_local)} (${escapeHtml(t.duration_label)}, ${formatTokens(t.tokens)} tok)"></div>`
        ).join('');

        return `<div class="gantt-row" data-action="jump-agent" data-conv-id="${escapeHtml(r.conv_id)}">
          <div class="gantt-label">
            <span class="role-tag rt-${escapeHtml(r.role_category)}" style="font-size:0.61rem;padding:2px 6px;">${escapeHtml(r.role_category === 'research_plan' ? 'PLAN' : r.role_category.toUpperCase().slice(0, 5))}</span>
            <span class="gantt-name">${escapeHtml(r.name)}</span>
          </div>
          <div class="gantt-track">${waitHtml}${turnHtml}</div>
          <div class="gantt-dur">${escapeHtml(r.active_duration_label)} · ${escapeHtml(r.wait_duration_label)}w</div>
        </div>`;
      }).join('');

      const scopeTxt = rows.length !== allRows.length ? ` (${rows.length} / ${allRows.length})` : '';

      document.getElementById('ganttPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Execution Gantt Waterfall${escapeHtml(scopeTxt)}</div>
            <div class="section-sub">Solid bars = active work turns · Dashed bars = free swarm_wait / background waits · Pins = #seq board milestones</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <button type="button" class="filter-btn ${ganttShowWaits ? 'active' : ''}" data-action="gantt-waits">${ganttShowWaits ? 'Hide Wait Spans' : 'Show Wait Spans'}</button>
            ${g.has_compressed_gaps ? `
              <div class="toggle-group">
                <button type="button" class="toggle-btn ${isComp ? 'active' : ''}" data-action="gantt-scale" data-mode="compressed">Compressed Pauses</button>
                <button type="button" class="toggle-btn ${!isComp ? 'active' : ''}" data-action="gantt-scale" data-mode="true">True Wall-Clock</button>
              </div>` : ''}
          </div>
        </div>
        <div class="gantt-axis">
          <div>Member</div>
          <div class="gantt-axis-track">
            <span>${escapeHtml(g.wall_start_local || '')}</span>
            ${markerHtml}
            <span>${escapeHtml(g.wall_end_local || '')}</span>
          </div>
          <div style="text-align:right;">Active · Wait</div>
        </div>
        <div class="gantt-rows">${rowsHtml || '<div class="section-sub">No members match current filter.</div>'}</div>
      `;
    }

    function matchesFilter(convId) {
      const a = (telemetry.agents || []).find(x => x.conv_id === convId);
      if (!matchesRoleOnly(a)) return false;
      const q = getSearchQuery();
      if (!q) return true;
      const hay = [
        a.name, a.role, a.role_label, a.model, a.brief, a.deliverable_text,
        ...(a.docs || []).map(d => d.name),
        ...(a.commands_run || []).map(c => c.command),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    }

    function renderDeliverables() {
      const agents = (telemetry.agents || []).filter(a => matchesFilter(a.conv_id));
      const cardsHtml = agents.map(a => {
        const filesHtml = (a.docs || []).length ? `
          <div class="files-strip">
            ${a.docs.map(d => `<a class="doc-link-item" href="${escapeHtml(d.path)}">${escapeHtml(d.action)}: ${escapeHtml(d.name)}</a>`).join('')}
          </div>` : '';

        const cmdsSummary = (a.commands_run || []).length ? (() => {
          const passed = a.commands_run.filter(c => c.status === 'passed').length;
          const failed = a.commands_run.filter(c => c.status === 'failed').length;
          return `<span class="telemetry-pill">cmds: ${a.commands_run.length} (${passed} pass${failed ? ', ' + failed + ' fail' : ''})</span>`;
        })() : '';

        const turnsRows = (a.turns || []).map(t => `
          <tr>
            <td>#${t.index}</td>
            <td>${escapeHtml(t.label)}</td>
            <td>${escapeHtml(t.start_local)} → ${escapeHtml(t.end_local)}</td>
            <td>${escapeHtml(t.duration_label)}</td>
            <td>${t.tool_call_count}</td>
            <td>${escapeHtml(formatTokens(t.tokens.total))}</td>
          </tr>
        `).join('');

        const delivTitle = a.deliverable_seq ? `Delivered (#${a.deliverable_seq})` : 'Output Summary';

        return `<article class="agent-card" id="agent-${escapeHtml(a.conv_id)}">
          <div class="card-top">
            <div class="card-title-group">
              <span class="agent-name">${escapeHtml(a.name)}</span>
              <span class="role-tag rt-${escapeHtml(a.role_category)}">${escapeHtml(a.role_label)}</span>
              <span class="life-pill lp-${escapeHtml(a.lifecycle_state)}">${escapeHtml(a.lifecycle_label)}</span>
              <span class="model-badge">${escapeHtml(a.model)}${a.model_switched ? ' (switched)' : ''}</span>
              ${a.workspace_mode !== 'inherit' ? `<span class="telemetry-pill">ws: ${escapeHtml(a.workspace_mode)}</span>` : ''}
            </div>
            <div class="telemetry-strip" style="margin-bottom:0;">
              <span class="telemetry-pill">${escapeHtml(a.wall_start_local)} → ${escapeHtml(a.wall_end_local)}</span>
              <span class="telemetry-pill">active: ${escapeHtml(a.active_duration_label)}</span>
              <span class="telemetry-pill">wait: ${escapeHtml(a.wait_duration_label)}</span>
            </div>
          </div>
          <div class="telemetry-strip">
            <span class="telemetry-pill">tokens: ${escapeHtml(formatTokens(a.tokens.total))} (in ${escapeHtml(formatTokens(a.tokens.input))} · out ${escapeHtml(formatTokens(a.tokens.output))} · cache ${escapeHtml(formatTokens(a.tokens.cache_read))})</span>
            <span class="telemetry-pill">turns: ${a.turns.length} · steps: ${a.step_count} · tools: ${a.tool_call_count}</span>
            <span class="telemetry-pill">board posts: ${a.board_post_count}</span>
            ${cmdsSummary}
          </div>
          ${a.deliverable_text ? `
            <div class="deliverable-box">
              <div class="deliverable-header">
                <span>${escapeHtml(delivTitle)}</span>
                <span>${a.docs.length} file(s)</span>
              </div>
              <div class="deliverable-text">${escapeHtml(a.deliverable_text)}</div>
              ${filesHtml}
            </div>` : filesHtml}
          ${a.brief ? `
            <details class="sub-details">
              <summary>Assignment Brief</summary>
              <div class="sub-details-body"><div class="deliverable-text">${escapeHtml(a.brief)}</div></div>
            </details>` : ''}
          <details class="sub-details">
            <summary>Execution Turns (${a.turns.length}) &amp; Tools (${a.tool_call_count})</summary>
            <div class="sub-details-body">
              <div style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px;">
                ${(a.tool_breakdown || []).map(tb => `<span class="telemetry-pill">${escapeHtml(tb.name)}: ${tb.count}</span>`).join('')}
                ${a.transcript_uri ? `<a class="doc-link-item" href="${escapeHtml(a.transcript_uri)}">Open Transcript</a>` : ''}
              </div>
              ${turnsRows ? `<table class="cmd-table"><thead><tr><th>#</th><th>Wakeup</th><th>Clock</th><th>Active</th><th>Tools</th><th>Tokens</th></tr></thead><tbody>${turnsRows}</tbody></table>` : ''}
            </div>
          </details>
        </article>`;
      }).join('');

      document.getElementById('deliverablesPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Worker Deliverables &amp; Activity (${agents.length})</div>
            <div class="section-sub">What each member was assigned, what it posted, files created/edited, and per-wakeup turn breakdown</div>
          </div>
        </div>
        <div class="cards-grid">${cardsHtml || '<div class="section-sub">No members match current filter.</div>'}</div>
      `;
    }

    function setBoardFilter(kind) {
      boardFilter = kind;
      renderFilterBanner();
      renderBoard();
    }
    function setBoardChannel(ch) {
      boardChannelFilter = ch;
      renderFilterBanner();
      renderBoard();
    }

    function getFilteredBoard() {
      const board = telemetry.board || [];
      const q = getSearchQuery();
      const roleMemberNames = new Set((telemetry.agents || []).filter(matchesRoleOnly).map(a => a.name));
      return board.filter(p => {
        if (activeRoleFilter !== 'all') {
          const authorMatch = roleMemberNames.has(p.agent);
          const mentionMatch = (p.mentions || []).some(m => roleMemberNames.has(m));
          if (!authorMatch && !mentionMatch) return false;
        }
        if (boardChannelFilter !== 'all' && p.channel !== boardChannelFilter) return false;
        if (boardFilter === 'done' && !(p.tags || []).includes('done')) return false;
        if (boardFilter === 'brief' && p.kind !== 'brief') return false;
        if (boardFilter === 'alerts' && !(p.tags || []).some(t => ['stall', 'quota', 'blocked', 'error'].includes(t))) return false;
        if (q) {
          const hay = `#${p.seq} ${p.agent} ${p.channel} ${(p.mentions || []).join(' ')} ${p.text}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });
    }

    function renderBoard() {
      const board = telemetry.board || [];
      const handoffs = telemetry.handoffs || [];
      const channels = telemetry.channels || ['main'];
      const git = telemetry.git_snapshot || {};
      const filtered = getFilteredBoard();

      const handoffHtml = handoffs.slice(0, 14).map(h =>
        `<span class="handoff-chip">${escapeHtml(h.from)} → ${escapeHtml(h.to)} (${h.seqs.map(s => '#' + s).join(', ')})</span>`
      ).join('');

      const gitHtml = git.available ? `
        <details class="sub-details" style="margin-bottom:14px;">
          <summary>Workspace Git Snapshot (${(git.modified || []).length} tracked changes · ${(git.untracked || []).length} untracked)</summary>
          <div class="sub-details-body">
            <div class="deliverable-text" style="font-family:'Fira Code',monospace;font-size:0.75rem;">${escapeHtml(git.diffstat || '')}${git.untracked && git.untracked.length ? '\n\nUntracked:\n' + escapeHtml(git.untracked.join('\n')) : ''}</div>
          </div>
        </details>` : '';

      const chControls = channels.length > 1 ? `
        <div class="toggle-group">
          <button type="button" class="toggle-btn ${boardChannelFilter === 'all' ? 'active' : ''}" data-action="board-channel" data-channel="all">All Channels</button>
          ${channels.map(ch => `<button type="button" class="toggle-btn ${boardChannelFilter === ch ? 'active' : ''}" data-action="board-channel" data-channel="${escapeHtml(ch)}">#${escapeHtml(ch)}</button>`).join('')}
        </div>` : '';

      const postsHtml = filtered.map(p => {
        const tagBadges = (p.tags || []).map(t => {
          const cls = t === 'done' ? 'pill-ok' : (t === 'stall' || t === 'quota' ? 'pill-warn' : 'pill-fail');
          return `<span class="badge-pill ${cls}" style="font-size:0.64rem;padding:2px 7px;">[${escapeHtml(t)}]</span>`;
        }).join(' ');
        return `<div class="board-post">
          <div class="board-post-head">
            <div>
              <span class="board-seq">#${escapeHtml(p.seq)}</span>
              <strong style="margin-left:6px;">${escapeHtml(p.agent)}</strong>
              ${p.channel && p.channel !== 'main' ? `<span class="telemetry-pill">#${escapeHtml(p.channel)}</span>` : ''}
              ${p.kind === 'brief' ? '<span class="telemetry-pill">brief</span>' : ''}
              ${tagBadges}
            </div>
            <span class="telemetry-pill">${escapeHtml(p.ts_local || p.time)}</span>
          </div>
          <div class="board-body">${escapeHtml(p.text)}</div>
        </div>`;
      }).join('');

      document.getElementById('boardPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Board Handoff Ledger (${filtered.length} / ${board.length} posts)</div>
            <div class="section-sub">Archived message board (board.jsonl) preserved inside this self-contained report</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            ${chControls}
            <div class="toggle-group">
              <button type="button" class="toggle-btn ${boardFilter === 'all' ? 'active' : ''}" data-action="board-filter" data-kind="all">All</button>
              <button type="button" class="toggle-btn ${boardFilter === 'done' ? 'active' : ''}" data-action="board-filter" data-kind="done">[done]</button>
              <button type="button" class="toggle-btn ${boardFilter === 'brief' ? 'active' : ''}" data-action="board-filter" data-kind="brief">Briefs</button>
              <button type="button" class="toggle-btn ${boardFilter === 'alerts' ? 'active' : ''}" data-action="board-filter" data-kind="alerts">Alerts</button>
            </div>
          </div>
        </div>
        ${handoffHtml ? `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;">${handoffHtml}</div>` : ''}
        ${gitHtml}
        <div>${postsHtml || '<div class="section-sub">No board posts match current filter.</div>'}</div>
      `;
    }

    function renderFilterBanner() {
      const banner = document.getElementById('filterBanner');
      if (!banner) return;
      const q = getSearchQuery();
      const isFiltered = activeRoleFilter !== 'all' || q !== '' || boardFilter !== 'all' || boardChannelFilter !== 'all';
      if (!isFiltered) {
        banner.classList.remove('visible');
        banner.innerHTML = '';
        return;
      }
      const totalAgents = (telemetry.agents || []).length;
      const shownAgents = getFilteredAgents().length;
      const totalBoard = (telemetry.board || []).length;
      const shownBoard = getFilteredBoard().length;
      const v = telemetry.verification || {};
      const allCmds = (v.verifier_commands && v.verifier_commands.length > 0)
        ? v.verifier_commands
        : (v.author_check_commands || []);
      const shownCmds = filterVerificationCommands(allCmds).length;

      const roleLabels = {
        all: 'All Members',
        author: 'Authors',
        research_plan: 'Research & Plan',
        verifier: 'Verifiers',
        coordinator: 'Coordinator',
        observers: 'Monitor / Narrator',
      };
      const parts = [];
      if (activeRoleFilter !== 'all') parts.push(`Role: ${roleLabels[activeRoleFilter] || activeRoleFilter}`);
      if (q) parts.push(`Search: "${q}"`);
      if (boardFilter !== 'all') parts.push(`Board: ${boardFilter}`);
      if (boardChannelFilter !== 'all') parts.push(`Channel: #${boardChannelFilter}`);

      banner.innerHTML = `
        <span><strong>Active Filter</strong> (${escapeHtml(parts.join(' · '))}) — Showing <strong>${shownAgents}/${totalAgents}</strong> members · <strong>${shownCmds}/${allCmds.length}</strong> check commands · <strong>${shownBoard}/${totalBoard}</strong> board posts</span>
        <button type="button" class="clear-filter-btn" data-action="reset-filters">Reset</button>
      `;
      banner.classList.add('visible');
    }

    function setRoleFilter(role, btn) {
      activeRoleFilter = role;
      document.querySelectorAll('.controls .filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset ? b.dataset.role === role : b === btn);
      });
      applyFilters();
    }

    function resetAllFilters() {
      activeRoleFilter = 'all';
      boardFilter = 'all';
      boardChannelFilter = 'all';
      const inp = document.getElementById('searchInput');
      if (inp) inp.value = '';
      document.querySelectorAll('.controls .filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset && b.dataset.role === 'all');
      });
      applyFilters();
    }

    function applyFilters() {
      renderFilterBanner();
      renderVerification();
      renderResources();
      renderGantt();
      renderDeliverables();
      renderBoard();
    }

    function jumpToAgent(convId) {
      const el = document.getElementById('agent-' + convId);
      if (!el) return;
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('highlighted');
      setTimeout(() => el.classList.remove('highlighted'), 1800);
    }

    function copyId(id, event) {
      if (event) event.stopPropagation();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(id).then(showToast).catch(() => {});
      } else {
        showToast();
      }
    }

    function showToast() {
      const toast = document.getElementById('copiedToast');
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 1800);
    }

    document.addEventListener('click', (e) => {
      const target = e.target && e.target.closest ? e.target.closest('[data-action]') : null;
      if (!target) return;
      const action = target.dataset.action;
      if (action === 'role-filter') {
        setRoleFilter(target.dataset.role || 'all', target);
      } else if (action === 'res-metric') {
        setResourceMetric(target.dataset.metric || 'total_tokens', target);
      } else if (action === 'gantt-waits') {
        toggleGanttWaits();
      } else if (action === 'gantt-scale') {
        setGanttScale(target.dataset.mode || 'compressed');
      } else if (action === 'board-filter') {
        setBoardFilter(target.dataset.kind || 'all');
      } else if (action === 'board-channel') {
        setBoardChannel(target.dataset.channel || 'all');
      } else if (action === 'jump-agent') {
        if (e.preventDefault) e.preventDefault();
        jumpToAgent(target.dataset.convId || '');
      } else if (action === 'reset-filters') {
        resetAllFilters();
      }
    });

    const searchEl = document.getElementById('searchInput');
    if (searchEl) {
      searchEl.addEventListener('input', applyFilters);
      searchEl.addEventListener('search', applyFilters);
    }

    renderHeader();
    renderSummary();
    applyFilters();
  </script>
</body>
</html>"""


def render_html(telemetry: Dict[str, Any]) -> str:
    """Inject telemetry JSON safely into HTML_TEMPLATE."""
    payload = json.dumps(telemetry, indent=2).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TELEMETRY_DATA_PLACEHOLDER__", payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an interactive AGY /swarm post-run HTML report."
    )
    parser.add_argument(
        "-c",
        "--conversation-id",
        help="Swarm coordinator or worker conversation ID (or unique prefix) to render.",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List matching native /swarm runs for the workspace and exit.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output HTML path (default: <workspace>/.agents/swarm-trajectory.html).",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        help="Project workspace root (default: auto-detected from cwd).",
    )
    parser.add_argument(
        "--agy-dir",
        help="Override AGY CLI data directory (default: ~/.gemini/antigravity-cli).",
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip capturing workspace git status/diffstat snapshot.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    workspace_root = os.path.abspath(args.workspace) if args.workspace else resolve_workspace_root()
    agy_dir = resolve_agy_dir(args.agy_dir)

    if args.list:
        runs = list_swarm_runs(agy_dir, workspace_root)
        if not runs:
            print(f"No native /swarm runs found matching workspace: {workspace_root}")
            return 0
        print(f"Native /swarm runs for {workspace_root} (data dir: {agy_dir}):")
        for r in runs:
            status_tag = "done+verified" if (r["completed"] and r["verified"]) else ("done" if r["completed"] else "incomplete")
            print(
                f"  {r['conversation_id']}  status={status_tag:<14} "
                f"members={r['member_count']:<3} board={r['board_count']:<4} "
                f"steps={r['step_count']:<5} updated={r['last_modified_time'][:19]}  {r['title']}"
            )
        return 0

    selected_id = select_swarm_run(agy_dir, workspace_root, args.conversation_id)
    if not selected_id:
        if args.conversation_id:
            sys.stderr.write(f"Error: swarm conversation '{args.conversation_id}' not found under {agy_dir}\n")
        else:
            sys.stderr.write(
                f"Error: no native /swarm runs found for workspace '{workspace_root}' in '{agy_dir}'.\n"
            )
        return 1

    try:
        telemetry = parse_swarm_run(
            agy_dir=agy_dir,
            root_id=selected_id,
            workspace_root=workspace_root,
            include_git=not args.no_git,
        )
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    default_out = os.path.join(workspace_root, ".agents", "swarm-trajectory.html")
    output_path = os.path.abspath(args.output or default_out)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    html = render_html(telemetry)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    s = telemetry["summary"]
    v = telemetry["verification"]
    tok = s["tokens"]
    print(
        f"/swarm report generated: {output_path}\n"
        f"  Run: {telemetry['run_title']} ({telemetry['root_conversation_id']})\n"
        f"  Outcome: {s['outcome_label']} | Verification: {v['verdict_label']} ({v['passed_count']} passed, {v['unresolved_failure_count']} unresolved)\n"
        f"  Wall-clock: {s['wall_start_local']} -> {s['wall_end_local']} "
        f"(core {s['core_wall_span_label']}, active {s['cumulative_active_label']}, parked {s['cumulative_wait_label']}, peak workers {s['peak_worker_concurrency']}, speedup {s['parallelism_speedup']}x)\n"
        f"  Members: {s['total_agents']} ({s['completed_workers']}/{s['worker_count']} delivered, {s['retired_workers']} retired), "
        f"tokens: {tok['total']:,} (in {tok['input']:,}, out {tok['output']:,}, cache {tok['cache_read']:,}), files: {s['unique_file_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
