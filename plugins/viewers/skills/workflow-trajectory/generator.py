#!/usr/bin/env python3
"""Generate an interactive dark-mode HTML blueprint & post-run report for AGY `run_workflow` runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from workflow_telemetry import (  # noqa: E402
    list_workflow_runs,
    parse_script_only,
    parse_workflow_run,
    resolve_agy_dir,
    resolve_workspace_root,
    select_workflow_run,
)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Workflow Blueprint &amp; Trajectory Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0f1d;
      --panel-dark: rgba(16, 22, 38, 0.82);
      --panel-elevated: rgba(22, 30, 50, 0.92);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-glowing: rgba(99, 102, 241, 0.50);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;

      --glow-indigo: #6366f1;
      --glow-purple: #8b5cf6;
      --glow-blue: #0284c7;
      --glow-teal: #0d9488;
      --glow-pink: #db2777;
      --glow-green: #10b981;
      --glow-amber: #f59e0b;
      --glow-red: #ef4444;

      --gradient-primary: linear-gradient(135deg, #6366f1, #0d9488);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.16) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(13, 148, 136, 0.14) 0px, transparent 50%),
        radial-gradient(at 50% 45%, rgba(2, 132, 199, 0.08) 0px, transparent 60%);
      background-attachment: fixed;
      font-family: 'Inter', sans-serif;
      color: var(--text-main);
      line-height: 1.55;
      overflow-x: hidden;
      padding-bottom: 80px;
    }

    header {
      padding: 12px 20px 10px;
      text-align: center;
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(14px);
      background-color: rgba(10, 15, 29, 0.88);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-content { max-width: 1360px; margin: 0 auto; }

    .badge-row {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 7px;
      margin-bottom: 6px;
    }

    .badge-workflow {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(99, 102, 241, 0.18);
      border: 1px solid rgba(99, 102, 241, 0.45);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #a5b4fc;
    }

    .badge-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 11px;
      border-radius: 20px;
      font-size: 0.73rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .pill-ok { background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(16, 185, 129, 0.38); color: #6ee7b7; }
    .pill-warn { background: rgba(245, 158, 11, 0.16); border: 1px solid rgba(245, 158, 11, 0.38); color: #fcd34d; }
    .pill-fail { background: rgba(239, 68, 68, 0.16); border: 1px solid rgba(239, 68, 68, 0.38); color: #fca5a5; }
    .pill-info { background: rgba(56, 189, 248, 0.16); border: 1px solid rgba(56, 189, 248, 0.38); color: #7dd3fc; }

    .badge-meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 11px;
      border-radius: 20px;
      font-family: 'Fira Code', monospace;
      font-size: 0.73rem;
      color: var(--text-muted);
      cursor: pointer;
    }
    .badge-meta:hover { border-color: var(--border-glowing); color: var(--text-main); }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 1.48rem;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 70%, #5eead4 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 3px;
      letter-spacing: -0.4px;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.80rem;
      max-width: 1120px;
      margin: 0 auto 9px;
    }

    .controls {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 7px;
      max-width: 1260px;
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
      font-size: 0.85rem;
      outline: none;
      transition: all 0.2s ease;
    }
    .search-input:focus {
      border-color: var(--glow-indigo);
      box-shadow: 0 0 14px rgba(99, 102, 241, 0.28);
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
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 7px 12px;
      border-radius: 10px;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 500;
      transition: all 0.2s ease;
    }
    .filter-btn:hover { background: rgba(255, 255, 255, 0.09); color: var(--text-main); }
    .filter-btn.active {
      background: var(--gradient-primary);
      border-color: transparent;
      color: white;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
    }

    .phase-select {
      background: rgba(16, 22, 38, 0.94);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 7px 12px;
      border-radius: 10px;
      font-family: 'Inter', sans-serif;
      font-size: 0.80rem;
      font-weight: 500;
      max-width: 320px;
      cursor: pointer;
      outline: none;
    }
    .phase-select:focus, .phase-select.active {
      border-color: var(--glow-indigo);
      box-shadow: 0 0 10px rgba(99, 102, 241, 0.28);
    }

    .view-tabs {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 6px;
      margin: 8px auto 0;
      padding-top: 8px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      max-width: 1260px;
    }
    .view-tab {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 5px 11px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.77rem;
      font-weight: 600;
      transition: all 0.16s ease;
    }
    .view-tab:hover { color: var(--text-main); background: rgba(255, 255, 255, 0.05); }
    .view-tab.active {
      color: #e0e7ff;
      background: rgba(99, 102, 241, 0.18);
      border-color: rgba(99, 102, 241, 0.48);
    }

    .kpi-card.kpi-filtered {
      border-color: rgba(99, 102, 241, 0.50);
      box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.18);
    }
    .kpi-tag {
      display: inline-block;
      margin-left: 6px;
      padding: 1px 6px;
      border-radius: 5px;
      font-size: 0.60rem;
      background: rgba(99, 102, 241, 0.24);
      color: #c7d2fe;
      vertical-align: middle;
    }
    .cmd-scroll-wrap {
      max-height: 360px;
      overflow-y: auto;
      overflow-x: auto;
    }

    .filter-banner {
      display: none;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin: 10px auto 0;
      padding: 6px 14px;
      max-width: 1020px;
      border-radius: 10px;
      background: rgba(99, 102, 241, 0.14);
      border: 1px solid rgba(99, 102, 241, 0.38);
      font-size: 0.78rem;
      color: #e0e7ff;
    }
    .filter-banner.visible { display: flex; }
    .clear-filter-btn {
      background: rgba(255, 255, 255, 0.09);
      border: 1px solid rgba(255, 255, 255, 0.20);
      color: #f8fafc;
      padding: 2px 9px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-weight: 600;
      cursor: pointer;
    }
    .clear-filter-btn:hover { background: rgba(255, 255, 255, 0.18); }
    .metric-hi { color: #5eead4 !important; font-weight: 700 !important; }

    .container {
      max-width: 1360px;
      margin: 22px auto;
      padding: 0 20px;
    }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 13px;
      margin-bottom: 16px;
    }

    .kpi-card {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 14px 16px;
      backdrop-filter: blur(10px);
    }
    .kpi-label {
      font-size: 0.70rem;
      text-transform: uppercase;
      letter-spacing: 0.7px;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }
    .kpi-value {
      font-family: 'Outfit', sans-serif;
      font-size: 1.45rem;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.2;
    }
    .kpi-sub {
      font-size: 0.74rem;
      color: var(--text-muted);
      margin-top: 4px;
      font-family: 'Fira Code', monospace;
    }

    .insights-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(270px, 1fr));
      gap: 11px;
      margin-bottom: 20px;
    }
    .insight-card {
      background: rgba(16, 22, 38, 0.68);
      border: 1px solid var(--border-color);
      border-left: 3px solid var(--glow-indigo);
      border-radius: 10px;
      padding: 10px 14px;
    }
    .insight-card.kind-tokens { border-left-color: var(--glow-purple); }
    .insight-card.kind-timing { border-left-color: var(--glow-amber); }
    .insight-card.kind-ok { border-left-color: var(--glow-green); }
    .insight-card.kind-overhead { border-left-color: var(--glow-blue); }
    .insight-card.kind-warning { border-left-color: var(--glow-red); }
    .insight-title { font-size: 0.81rem; font-weight: 700; color: var(--text-main); margin-bottom: 2px; }
    .insight-detail { font-size: 0.77rem; color: var(--text-muted); }

    .section-panel {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 18px 22px;
      margin-bottom: 22px;
      backdrop-filter: blur(12px);
    }
    .section-panel.hidden { display: none; }

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
      font-size: 1.14rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 9px;
    }
    .section-sub { font-size: 0.80rem; color: var(--text-muted); }

    .toggle-group {
      display: inline-flex;
      background: rgba(10, 15, 29, 0.85);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 3px;
      gap: 3px;
      flex-wrap: wrap;
    }
    .toggle-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 5px 10px;
      border-radius: 7px;
      cursor: pointer;
    }
    .toggle-btn.active { background: var(--gradient-primary); color: #ffffff; }

    /* Blueprint DAG Flow */
    .dag-flow {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 16px;
    }
    .phase-box {
      background: rgba(10, 15, 29, 0.72);
      border: 1px solid rgba(99, 102, 241, 0.28);
      border-radius: 12px;
      padding: 12px 15px;
    }
    .phase-box-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }
    .phase-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(99, 102, 241, 0.20);
      border: 1px solid rgba(99, 102, 241, 0.45);
      color: #c7d2fe;
      font-family: 'Outfit', sans-serif;
      font-weight: 700;
      font-size: 0.85rem;
      padding: 3px 10px;
      border-radius: 8px;
    }
    .phase-steps {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: stretch;
    }
    .bp-node {
      flex: 1 1 240px;
      background: rgba(22, 30, 50, 0.82);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 0.79rem;
    }
    .bp-node.kind-parallel { border-color: rgba(13, 148, 136, 0.45); background: rgba(13, 148, 136, 0.08); }
    .bp-node.kind-pipeline { border-color: rgba(2, 132, 199, 0.45); background: rgba(2, 132, 199, 0.08); }
    .bp-node.kind-tool { border-color: rgba(245, 158, 11, 0.40); background: rgba(245, 158, 11, 0.07); }
    .bp-node-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 5px;
      font-weight: 700;
      color: #f8fafc;
    }
    .bp-children {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 6px;
      padding-left: 10px;
      border-left: 2px solid rgba(255, 255, 255, 0.14);
    }

    .inventory-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .inv-card {
      background: rgba(10, 15, 29, 0.65);
      border: 1px solid var(--border-color);
      border-radius: 11px;
      padding: 12px 14px;
    }
    .inv-title {
      font-size: 0.76rem;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: #a5b4fc;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .chip-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(255, 255, 255, 0.045);
      border: 1px solid var(--border-color);
      padding: 3px 9px;
      border-radius: 7px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: #cbd5e1;
    }
    .chip-skill { background: rgba(139, 92, 246, 0.15); border-color: rgba(139, 92, 246, 0.38); color: #ddd6fe; }
    .chip-tool { background: rgba(13, 148, 136, 0.14); border-color: rgba(13, 148, 136, 0.36); color: #99f6e4; }
    .chip-warn { background: rgba(245, 158, 11, 0.15); border-color: rgba(245, 158, 11, 0.38); color: #fde68a; }

    /* Verification */
    .verify-banner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      padding: 12px 15px;
      border-radius: 12px;
      margin-bottom: 12px;
      background: rgba(10, 15, 29, 0.70);
      border: 1px solid var(--border-color);
    }
    .verify-banner.verdict-VERIFIED { border-color: rgba(16, 185, 129, 0.45); background: rgba(16, 185, 129, 0.09); }
    .verify-banner.verdict-STALE, .verify-banner.verdict-PARTIAL, .verify-banner.verdict-SELF_CHECKED, .verify-banner.verdict-PRE_RUN {
      border-color: rgba(245, 158, 11, 0.42); background: rgba(245, 158, 11, 0.08);
    }
    .verify-banner.verdict-FAILED, .verify-banner.verdict-UNVERIFIED {
      border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.09);
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
    .cmd-table th { color: var(--text-muted); font-weight: 600; font-family: 'Inter', sans-serif; font-size: 0.71rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .cmd-code { max-width: 560px; word-break: break-word; color: #e2e8f0; }

    /* Breakdown bars */
    .breakdown-grid {
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 18px;
      margin-bottom: 14px;
    }
    @media (max-width: 920px) { .breakdown-grid { grid-template-columns: 1fr; } }

    .bar-list { display: flex; flex-direction: column; gap: 9px; }
    .bar-row {
      display: grid;
      grid-template-columns: 180px 1fr 145px;
      align-items: center;
      gap: 10px;
      font-size: 0.78rem;
    }
    .bar-label { font-family: 'Fira Code', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text-main); cursor: pointer; }
    .bar-label:hover { color: #a5b4fc; }
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
    .bar-seg-active { background: linear-gradient(90deg, #6366f1, #10b981); height: 100%; }
    .bar-val { font-family: 'Fira Code', monospace; font-size: 0.72rem; text-align: right; color: var(--text-muted); }

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

    /* Gantt */
    .gantt-axis {
      display: grid;
      grid-template-columns: 250px 1fr 110px;
      gap: 12px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-dim);
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 8px;
    }
    .gantt-axis-track { display: flex; justify-content: space-between; align-items: center; }
    .gantt-rows { display: flex; flex-direction: column; gap: 7px; }
    .gantt-row {
      display: grid;
      grid-template-columns: 250px 1fr 110px;
      gap: 12px;
      align-items: center;
      padding: 5px 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .gantt-row:hover { background: rgba(255, 255, 255, 0.045); }
    .gantt-label { display: flex; align-items: center; gap: 7px; overflow: hidden; }
    .gantt-name { font-size: 0.80rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .gantt-track {
      position: relative;
      height: 22px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 6px;
      overflow: hidden;
    }
    .gantt-turn-bar {
      position: absolute;
      top: 3px;
      height: 16px;
      border-radius: 4px;
      min-width: 4px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
    }
    .bar-cat-author { background: linear-gradient(90deg, #db2777, #a855f7); }
    .bar-cat-research { background: linear-gradient(90deg, #0284c7, #38bdf8); }
    .bar-cat-verifier { background: linear-gradient(90deg, #0d9488, #10b981); }
    .bar-cat-worker { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .gantt-dur { font-family: 'Fira Code', monospace; font-size: 0.72rem; text-align: right; color: var(--text-muted); }

    /* Worker Cards */
    .cards-grid { display: flex; flex-direction: column; gap: 14px; }
    .agent-card {
      background: rgba(12, 18, 32, 0.86);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 16px 18px;
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
      margin-bottom: 9px;
    }
    .card-title-group { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }
    .agent-name { font-family: 'Outfit', sans-serif; font-size: 1.10rem; font-weight: 700; color: #fff; }

    .role-tag {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 7px;
      letter-spacing: 0.4px;
    }
    .rt-author { background: rgba(219, 39, 119, 0.18); color: #f9a8d4; border: 1px solid rgba(219, 39, 119, 0.40); }
    .rt-research { background: rgba(2, 132, 199, 0.18); color: #7dd3fc; border: 1px solid rgba(2, 132, 199, 0.40); }
    .rt-verifier { background: rgba(16, 185, 129, 0.18); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.40); }
    .rt-worker { background: rgba(99, 102, 241, 0.20); color: #c7d2fe; border: 1px solid rgba(99, 102, 241, 0.40); }

    .telemetry-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 9px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
    }
    .telemetry-pill {
      background: rgba(255, 255, 255, 0.038);
      border: 1px solid var(--border-color);
      padding: 2px 8px;
      border-radius: 6px;
    }

    .deliverable-box {
      background: rgba(10, 15, 29, 0.70);
      border: 1px solid rgba(255, 255, 255, 0.07);
      border-radius: 10px;
      padding: 11px 13px;
      margin-bottom: 9px;
    }
    .deliverable-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
      font-size: 0.73rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #5eead4;
    }
    .deliverable-text {
      font-size: 0.81rem;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 240px;
      overflow-y: auto;
      font-family: 'Fira Code', monospace;
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

    .code-box {
      font-family: 'Fira Code', monospace;
      font-size: 0.74rem;
      line-height: 1.5;
      background: rgba(6, 10, 20, 0.88);
      border-radius: 8px;
      padding: 10px 12px;
      overflow-x: auto;
      max-height: 360px;
      overflow-y: auto;
      white-space: pre;
      color: #cbd5e1;
    }

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
      font-size: 0.72rem;
      text-decoration: none;
      color: #7dd3fc;
    }
    .doc-link-item:hover { background: rgba(56, 189, 248, 0.16); border-color: #38bdf8; }

    .log-row {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      padding: 6px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      font-family: 'Fira Code', monospace;
      font-size: 0.75rem;
    }
    .log-row.kind-phase { background: rgba(99, 102, 241, 0.10); color: #c7d2fe; font-weight: 700; }
    .log-row.kind-error { background: rgba(239, 68, 68, 0.10); color: #fca5a5; }
    .log-text { flex: 1; white-space: pre-wrap; word-break: break-word; color: #e2e8f0; }

    .copied-toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--gradient-primary);
      padding: 10px 18px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.85rem;
      color: white;
      box-shadow: 0 10px 25px rgba(99, 102, 241, 0.4);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s ease;
      z-index: 1000;
    }
    .copied-toast.show { transform: translateY(0); opacity: 1; }

    .hidden { display: none !important; }

    @media (max-width: 820px) {
      .gantt-axis, .gantt-row { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 130px 1fr 110px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div class="badge-row">
        <div class="badge-workflow" id="modeBadge">AGY run_workflow Report</div>
        <div class="badge-pill" id="outcomeBadge"></div>
        <div class="badge-pill" id="verifyBadge"></div>
        <div class="badge-meta" id="tzBadge"></div>
        <div class="badge-meta" id="rootIdBadge" title="Click to copy conversation ID"></div>
      </div>
      <h1 id="runTitle">Workflow Execution Report</h1>
      <p class="subtitle" id="runSubtitle"></p>
      <div class="controls" id="controlsBar">
        <div class="search-container">
          <svg class="search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search phase, worker, agent, skill, tool, file, or deliverable...">
        </div>
        <button type="button" class="filter-btn active" data-action="role-filter" data-role="all">All</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="author">Authors</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="research">Research</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="verifier">Verifiers</button>
        <button type="button" class="filter-btn" data-action="role-filter" data-role="worker">Workers</button>
        <select id="phaseFilterSelect" class="phase-select hidden" aria-label="Filter by phase"></select>
      </div>
      <div class="view-tabs" id="viewTabsBar"></div>
      <div class="filter-banner" id="filterBanner"></div>
    </div>
  </header>

  <div class="container" id="mainContainer" style="display:flex;flex-direction:column;">
    <section class="summary-grid" id="summaryGrid"></section>
    <section class="insights-grid" id="insightsGrid"></section>
    <section class="section-panel" id="deliverablesPanel"></section>
    <section class="section-panel" id="ganttPanel"></section>
    <section class="section-panel" id="resourcesPanel"></section>
    <section class="section-panel" id="verificationPanel"></section>
    <section class="section-panel" id="blueprintPanel"></section>
    <section class="section-panel" id="logsPanel"></section>
  </div>

  <div class="copied-toast" id="copiedToast">Copied to clipboard!</div>

  <script>
    const telemetry = __TELEMETRY_DATA_PLACEHOLDER__;
    let activeRoleFilter = 'all';
    let activePhaseFilter = 'all';
    let activeViewTab = 'all';
    let resourceMetric = 'total_tokens';
    let ganttScaleMode = (telemetry.gantt && telemetry.gantt.has_compressed_gaps) ? 'compressed' : 'true';
    let logKindFilter = 'all';

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
      if (v >= 1000000) return (v / 1000000).toFixed(2) + 'M';
      if (v >= 1000) return (v / 1000).toFixed(1) + 'k';
      return String(v);
    }

    function formatDurationSec(sec) {
      const s = Math.max(0, Math.round(Number(sec || 0)));
      if (s < 60) return s + 's';
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const r = s % 60;
      if (h > 0) return m > 0 ? `${h}h ${m}m` : (r > 0 ? `${h}h ${r}s` : `${h}h`);
      return r > 0 ? `${m}m ${r}s` : `${m}m`;
    }

    function isAnyFilterActive() {
      return activeRoleFilter !== 'all' || activePhaseFilter !== 'all' || getSearchQuery() !== '' || logKindFilter !== 'all';
    }

    function getSearchQuery() {
      const inp = document.getElementById('searchInput');
      return (inp && inp.value ? inp.value : '').trim().toLowerCase();
    }

    function matchesWorker(w) {
      if (!w) return false;
      if (activeRoleFilter !== 'all' && w.role_category !== activeRoleFilter) return false;
      if (activePhaseFilter !== 'all' && w.phase !== activePhaseFilter && !(w.phases || []).includes(activePhaseFilter)) return false;
      const q = getSearchQuery();
      if (!q) return true;
      const hay = [
        w.role, w.phase, w.type_name, w.role_label, w.model, w.status, w.deliverable_text,
        ...(w.skills_loaded || []),
        ...(w.tool_breakdown || []).map(t => t.name),
        ...(w.docs || []).map(d => d.name),
        ...(w.commands_run || []).map(c => c.command),
      ].join(' ').toLowerCase();
      return hay.includes(q);
    }

    function getFilteredWorkers() {
      return (telemetry.workers || []).filter(matchesWorker);
    }

    function getFilteredCommands() {
      const v = telemetry.verification || {};
      const allCmds = (v.verifier_commands && v.verifier_commands.length > 0)
        ? v.verifier_commands
        : (v.author_check_commands || []);
      const q = getSearchQuery();
      const allowedRoles = new Set(getFilteredWorkers().map(w => w.role));
      const roleActive = activeRoleFilter !== 'all' || activePhaseFilter !== 'all';
      return allCmds.filter(c => {
        if (roleActive && c.agent && !allowedRoles.has(c.agent)) return false;
        if (!q) return true;
        const hay = `${c.agent || ''} ${c.command || ''} ${c.status || ''} ${c.ts_local || ''}`.toLowerCase();
        return hay.includes(q);
      });
    }

    function getFilteredLogs() {
      const entries = (telemetry.workflow && telemetry.workflow.log_entries) || [];
      const q = getSearchQuery();
      const filteredW = getFilteredWorkers();
      const allowedConvIds = new Set(filteredW.map(w => w.conv_id));
      const allowedRoles = new Set(filteredW.map(w => w.role));
      const allowedPhases = new Set();
      filteredW.forEach(w => {
        if (w.phase) allowedPhases.add(w.phase);
        (w.phases || []).forEach(p => allowedPhases.add(p));
      });
      return entries.filter(e => {
        if (activePhaseFilter !== 'all' && e.phase !== activePhaseFilter) return false;
        if (activeRoleFilter !== 'all') {
          if (e.kind === 'agent') {
            const matchId = e.conv_id && allowedConvIds.has(e.conv_id);
            const matchRole = e.role && allowedRoles.has(e.role);
            if (!matchId && !matchRole) return false;
          } else if (e.phase && !allowedPhases.has(e.phase)) {
            return false;
          }
        }
        if (logKindFilter !== 'all' && e.kind !== logKindFilter) return false;
        if (q) {
          const hay = `${e.phase || ''} ${e.role || ''} ${e.type_name || ''} ${e.text || ''}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });
    }

    function renderHeader() {
      const s = telemetry.summary || {};
      const v = telemetry.verification || {};
      const wf = telemetry.workflow || {};
      const workers = telemetry.workers || [];
      const isBP = s.mode === 'blueprint';

      document.getElementById('modeBadge').textContent = 'AGY run_workflow · ' + (s.mode_label || 'Report');

      const oBadge = document.getElementById('outcomeBadge');
      oBadge.textContent = s.outcome_label || 'Completed';
      oBadge.className = 'badge-pill ' + (
        s.outcome === 'completed' ? 'pill-ok' :
        s.outcome === 'failed' ? 'pill-fail' :
        s.outcome === 'blueprint' ? 'pill-info' : 'pill-warn'
      );

      const vBadge = document.getElementById('verifyBadge');
      vBadge.textContent = v.verdict_label || 'Unverified';
      vBadge.className = 'badge-pill ' + (
        v.verdict === 'VERIFIED' ? 'pill-ok' :
        (v.verdict === 'FAILED' || v.verdict === 'UNVERIFIED') ? 'pill-fail' : 'pill-warn'
      );

      document.getElementById('tzBadge').textContent = telemetry.tz_label || 'LOCAL';
      const rootBadge = document.getElementById('rootIdBadge');
      const cid = telemetry.root_conversation_id || 'blueprint';
      const invSuffix = s.invocation_total > 1 ? ` · Run ${s.invocation_index}/${s.invocation_total}` : '';
      rootBadge.textContent = (cid === 'pre-run-blueprint' ? 'Static Script' : 'Conv: ' + cid.slice(0, 8)) + invSuffix;
      rootBadge.onclick = (e) => copyId(cid, e);

      document.getElementById('runTitle').textContent = telemetry.run_title || 'Workflow Execution Report';
      const scriptName = wf.script_path ? wf.script_path.split('/').pop() : 'inline Script';
      document.getElementById('runSubtitle').textContent =
        isBP
          ? `${wf.script_path || ''} • Static AST analysis before execution`
          : `${telemetry.workspace_root || ''} • ${scriptName} • ${s.wall_start_local || '—'} → ${s.wall_end_local || '—'} (${s.wall_span_label || '—'})`;

      // Update role buttons with live counts & hide 0-count roles so every button has real matches.
      const roleCounts = { all: workers.length, author: 0, research: 0, verifier: 0, worker: 0 };
      workers.forEach(w => {
        if (roleCounts[w.role_category] !== undefined) roleCounts[w.role_category] += 1;
      });
      const roleLabels = { all: 'All', author: 'Authors', research: 'Research', verifier: 'Verifiers', worker: 'Workers' };
      document.querySelectorAll('[data-action="role-filter"]').forEach(btn => {
        const r = btn.dataset.role || 'all';
        if (isBP) {
          btn.classList.add('hidden');
          return;
        }
        const c = roleCounts[r] || 0;
        if (r !== 'all' && c === 0) {
          btn.classList.add('hidden');
        } else {
          btn.classList.remove('hidden');
          btn.textContent = `${roleLabels[r] || r} (${c})`;
        }
      });

      // Build compact Phase dropdown (excludes unexecuted {var} templates in post-run mode).
      const phaseWorkerCount = {};
      workers.forEach(w => {
        if (w.phase) phaseWorkerCount[w.phase] = (phaseWorkerCount[w.phase] || 0) + 1;
      });
      const logPhaseSet = new Set(((wf.log_entries) || []).map(e => e.phase).filter(Boolean));
      const phases = [];
      ((telemetry.blueprint && telemetry.blueprint.phases) || []).forEach(p => {
        if (!p.name || phases.includes(p.name)) return;
        if (!isBP && /\{[^}]+\}/.test(p.name) && !phaseWorkerCount[p.name] && !logPhaseSet.has(p.name)) return;
        phases.push(p.name);
      });
      (telemetry.phase_rollups || []).forEach(p => {
        if (p.phase && !phases.includes(p.phase)) phases.push(p.phase);
      });

      const phSel = document.getElementById('phaseFilterSelect');
      if (phSel) {
        if (phases.length > 1) {
          phSel.classList.remove('hidden');
          const opts = [`<option value="all">All Phases (${phases.length})</option>`].concat(
            phases.map(p => {
              const cnt = phaseWorkerCount[p] || 0;
              const suffix = isBP ? '' : ` (${cnt} worker${cnt === 1 ? '' : 's'})`;
              const shortName = p.length > 44 ? p.slice(0, 42) + '…' : p;
              return `<option value="${escapeHtml(p)}">${escapeHtml(shortName + suffix)}</option>`;
            })
          );
          phSel.innerHTML = opts.join('');
          phSel.value = activePhaseFilter;
        } else {
          phSel.classList.add('hidden');
        }
      }

      // In Pre-Run Blueprint mode, order Blueprint before Verification.
      const bpPanel = document.getElementById('blueprintPanel');
      if (bpPanel) {
        bpPanel.style.order = isBP ? '-1' : '';
      }
    }

    function renderViewTabs() {
      const bar = document.getElementById('viewTabsBar');
      if (!bar) return;
      const isBP = telemetry.mode === 'blueprint';
      const allW = (telemetry.workers || []).length;
      const filtW = getFilteredWorkers().length;
      const allL = ((telemetry.workflow && telemetry.workflow.log_entries) || []).length;
      const filtL = getFilteredLogs().length;
      const filtCmds = getFilteredCommands().length;

      const tabs = isBP ? [
        { id: 'all', label: 'All Sections' },
        { id: 'blueprint', label: 'Blueprint & Source' },
        { id: 'verification', label: 'Pre-Flight & Verification' },
      ] : [
        { id: 'all', label: 'All Sections' },
        { id: 'deliverables', label: `Deliverables (${filtW === allW ? allW : filtW + '/' + allW})` },
        { id: 'gantt', label: `Gantt (${filtW})` },
        { id: 'resources', label: 'Time & Tokens' },
        { id: 'verification', label: `Verification (${filtCmds})` },
        { id: 'blueprint', label: 'Blueprint & Code' },
        { id: 'logs', label: `Logs (${filtL === allL ? allL : filtL + '/' + allL})` },
      ];

      bar.innerHTML = tabs.map(t =>
        `<button type="button" class="view-tab ${activeViewTab === t.id ? 'active' : ''}" data-action="view-tab" data-tab="${escapeHtml(t.id)}">${escapeHtml(t.label)}</button>`
      ).join('');
    }

    function applyViewTabVisibility() {
      const isBP = telemetry.mode === 'blueprint';
      const map = {
        deliverables: 'deliverablesPanel',
        gantt: 'ganttPanel',
        resources: 'resourcesPanel',
        verification: 'verificationPanel',
        blueprint: 'blueprintPanel',
        logs: 'logsPanel',
      };
      Object.entries(map).forEach(([tabId, panelId]) => {
        const el = document.getElementById(panelId);
        if (!el) return;
        const bpHidden = isBP && ['deliverables', 'gantt', 'resources', 'logs'].includes(tabId);
        const tabHidden = activeViewTab !== 'all' && activeViewTab !== tabId;
        el.classList.toggle('hidden', bpHidden || tabHidden);
      });
    }

    function renderSummary() {
      const s = telemetry.summary || {};
      const v = telemetry.verification || {};
      const bp = telemetry.blueprint || {};
      const cnt = bp.counts || {};
      const inv = telemetry.inventory || {};
      const tok = s.tokens || {};
      const isBP = s.mode === 'blueprint';
      const allWorkers = telemetry.workers || [];
      const filtWorkers = getFilteredWorkers();
      const filtered = !isBP && isAnyFilterActive();

      let cards;
      if (isBP) {
        cards = [
          {
            label: 'Script Phases',
            value: `${cnt.phases || 0} Phases`,
            sub: `${bp.line_count || 0} lines · ${cnt.helpers || 0} helper fn(s)`
          },
          {
            label: 'Orchestration Graph',
            value: `${cnt.parallel_blocks || 0} Parallel · ${cnt.pipeline_blocks || 0} Pipe`,
            sub: `${cnt.agents || 0} agent def(s) · ${cnt.tool_calls || 0} call_tool()`
          },
          {
            label: 'Skills & Agent Types',
            value: `${(inv.skills_declared || []).length} Declared`,
            sub: ((inv.skills_declared || []).slice(0, 3).join(', ') || 'No explicit skills')
          },
          {
            label: 'Model Tiers Configured',
            value: `${(s.models_used || []).length || 1} Tier(s)`,
            sub: (s.models_used || ['inherit']).join(', ')
          },
          {
            label: 'Script Inputs (Args)',
            value: `${(bp.args_keys || []).length} Arg Key(s)`,
            sub: (bp.args_keys || []).join(', ') || 'No args.get() keys'
          },
          {
            label: 'Pre-Flight Checks',
            value: `${(bp.warnings || []).length} Note(s)`,
            sub: v.has_verifier ? `Verifier planned: ${v.verifier_names.join(', ')}` : 'No verifier phase detected'
          }
        ];
      } else if (filtered) {
        const doneF = filtWorkers.filter(w => w.status === 'done').length;
        const turnsF = filtWorkers.reduce((a, w) => a + (w.turns ? w.turns.length : 0), 0);
        const activeSecF = filtWorkers.reduce((a, w) => a + (w.active_duration_s || 0), 0);
        const tokTotF = filtWorkers.reduce((a, w) => a + ((w.tokens && w.tokens.total) || 0), 0);
        const tokInF = filtWorkers.reduce((a, w) => a + ((w.tokens && w.tokens.input) || 0), 0);
        const tokOutF = filtWorkers.reduce((a, w) => a + ((w.tokens && w.tokens.output) || 0), 0);
        const tokPct = tok.total > 0 ? ((tokTotF / tok.total) * 100).toFixed(1) : '0.0';
        const toolsF = filtWorkers.reduce((a, w) => a + (w.tool_call_count || 0), 0);
        const skillSet = new Set();
        const toolSet = new Set();
        const fileSet = new Set();
        const phaseSet = new Set();
        filtWorkers.forEach(w => {
          if (w.phase) phaseSet.add(w.phase);
          (w.skills_loaded || []).forEach(sk => skillSet.add(sk));
          (w.tool_breakdown || []).forEach(tb => toolSet.add(tb.name));
          (w.docs || []).forEach(d => fileSet.add(d.name));
        });
        const filtCmds = getFilteredCommands();
        const filtPassed = filtCmds.filter(c => c.status === 'passed').length;
        const filtFailed = filtCmds.filter(c => c.status === 'failed').length;

        cards = [
          {
            label: 'Matching Workers',
            filtered: true,
            value: `${filtWorkers.length} / ${allWorkers.length}`,
            sub: `${doneF} done · ${turnsF} turn(s) · ${phaseSet.size} phase(s)`
          },
          {
            label: 'Filtered Worker Time',
            filtered: true,
            value: formatDurationSec(activeSecF),
            sub: `Run wall-clock ${s.wall_span_label || '0s'} (${s.parallelism_speedup || 1}x speedup)`
          },
          {
            label: 'Filtered Tokens',
            filtered: true,
            value: `${formatTokens(tokTotF)} (${tokPct}%)`,
            sub: `In ${formatTokens(tokInF)} · Out ${formatTokens(tokOutF)} · of ${formatTokens(tok.total)}`
          },
          {
            label: 'Phases Matched',
            filtered: true,
            value: `${phaseSet.size} Phase(s)`,
            sub: Array.from(phaseSet).slice(0, 2).join(', ') || 'None matched'
          },
          {
            label: 'Filtered Skills & Tools',
            filtered: true,
            value: `${skillSet.size} Skills · ${toolSet.size} Tools`,
            sub: `${toolsF} agent tool call(s) in matching workers`
          },
          {
            label: 'Filtered Checks & Files',
            filtered: true,
            value: `${fileSet.size} Files · ${filtCmds.length} Cmds`,
            sub: `${filtPassed} passed · ${filtFailed} failed · overall ${v.verdict || 'UNVERIFIED'}`
          }
        ];
      } else {
        cards = [
          {
            label: 'Workers Completed',
            value: `${s.done_workers || 0}/${s.worker_count || 0}`,
            sub: `${s.total_turns || 0} turn(s) · ${s.failed_workers || 0} failed · ${cnt.phases || (telemetry.phase_rollups || []).length} phase(s)`
          },
          {
            label: 'Wall-Clock & Speedup',
            value: `${s.wall_span_label || '0s'} (${s.parallelism_speedup || 1}x)`,
            sub: `Worker sum ${s.cumulative_worker_label || '0s'} · Peak parallel: ${s.peak_worker_concurrency || 0}`
          },
          {
            label: 'Total Tokens',
            value: formatTokens(tok.total),
            sub: `In ${formatTokens(tok.input)} · Out ${formatTokens(tok.output)} · Cache ${formatTokens(tok.cache_read)} (${tok.cache_hit_pct || 0}%)`
          },
          {
            label: 'Script Components',
            value: `${cnt.agents || 0} Defs · ${cnt.parallel_blocks || 0} Par`,
            sub: `${cnt.pipeline_blocks || 0} pipeline · ${cnt.tool_calls || 0} call_tool · ${bp.line_count || 0} LOC`
          },
          {
            label: 'Skills & Tools Used',
            value: `${(inv.skills_observed || []).length} Skills · ${(inv.agent_tools || []).length} Tools`,
            sub: `${s.total_tool_calls || 0} agent calls · ${(s.models_used || []).join(', ') || 'unknown'}`
          },
          {
            label: 'Verification & Files',
            value: v.verdict === 'VERIFIED' ? 'CHECKED ✓' : (v.verdict || 'UNVERIFIED'),
            sub: `${v.passed_count || 0} passed · ${v.unresolved_failure_count || 0} unresolved · ${s.unique_file_count || 0} files`
          }
        ];
      }

      document.getElementById('summaryGrid').innerHTML = cards.map(c => `
        <div class="kpi-card ${c.filtered ? 'kpi-filtered' : ''}">
          <div class="kpi-label">${escapeHtml(c.label)}${c.filtered ? '<span class="kpi-tag">FILTERED</span>' : ''}</div>
          <div class="kpi-value">${escapeHtml(c.value)}</div>
          <div class="kpi-sub">${escapeHtml(c.sub)}</div>
        </div>
      `).join('');

      let ins;
      if (filtered) {
        ins = [];
        if (filtWorkers.length > 0) {
          const topTok = [...filtWorkers].sort((a, b) => (b.tokens.total || 0) - (a.tokens.total || 0))[0];
          const topDur = [...filtWorkers].sort((a, b) => (b.active_duration_s || 0) - (a.active_duration_s || 0))[0];
          const sliceTot = Math.max(1, filtWorkers.reduce((a, w) => a + (w.tokens.total || 0), 0));
          ins.push({
            kind: 'token',
            title: `Top Filtered Token Consumer: ${topTok.role}`,
            detail: `${formatTokens(topTok.tokens.total)} tokens (${((topTok.tokens.total / sliceTot) * 100).toFixed(1)}% of filtered slice, ${topTok.tokens.cache_hit_pct}% cache hit) on ${topTok.model}.`,
          });
          ins.push({
            kind: 'time',
            title: `Longest Filtered Worker: ${topDur.role} (${topDur.active_duration_label})`,
            detail: `Phase: ${topDur.phase} · ${(topDur.docs || []).length} file(s) · ${topDur.tool_call_count} tool call(s).`,
          });
        } else {
          ins.push({
            kind: 'warn',
            title: 'No Workers Match Current Filter',
            detail: 'Click Reset in the filter bar or select a different role/phase/search query.',
          });
        }
      } else {
        ins = telemetry.insights || [];
      }

      document.getElementById('insightsGrid').innerHTML = ins.map(item => `
        <div class="insight-card kind-${escapeHtml(item.kind)}">
          <div class="insight-title">${escapeHtml(item.title)}</div>
          <div class="insight-detail">${escapeHtml(item.detail)}</div>
        </div>
      `).join('');
    }

    function renderStepNode(step) {
      if (step.kind === 'parallel' || step.kind === 'pipeline') {
        const cls = step.kind === 'parallel' ? 'kind-parallel' : 'kind-pipeline';
        const label = step.kind === 'parallel' ? 'PARALLEL FAN-OUT' : 'SEQUENTIAL PIPELINE';
        const inner = (step.children || []).map(renderStepNode).join('');
        return `<div class="bp-node ${cls}">
          <div class="bp-node-head">
            <span>${label}</span>
            <span class="telemetry-pill">line ${step.line} · over ${escapeHtml(step.items_expr || 'items')}</span>
          </div>
          <div class="bp-children">${inner || '<span class="section-sub">Dynamic callable</span>'}</div>
        </div>`;
      }
      if (step.kind === 'agent' || step.kind === 'agent_turn') {
        const turnTag = step.kind === 'agent_turn' ? ` · turn #${step.turn_number}` : ` · ${step.mode}`;
        return `<div class="bp-node">
          <div class="bp-node-head">
            <span>${escapeHtml(step.role)}</span>
            <span class="telemetry-pill">L${step.line}${escapeHtml(turnTag)}</span>
          </div>
          <div class="chip-wrap">
            <span class="chip chip-skill">type: ${escapeHtml(step.type_name || 'self')}</span>
            <span class="chip">model: ${escapeHtml(step.model || 'inherit')}</span>
            ${step.workspace && step.workspace !== 'inherit' ? `<span class="chip chip-warn">ws: ${escapeHtml(step.workspace)}</span>` : ''}
            ${step.schema_type ? `<span class="chip">schema: ${escapeHtml(step.schema_type)}</span>` : ''}
          </div>
        </div>`;
      }
      if (step.kind === 'call_tool') {
        return `<div class="bp-node kind-tool">
          <div class="bp-node-head">
            <span>call_tool("${escapeHtml(step.tool)}")</span>
            <span class="telemetry-pill">L${step.line}</span>
          </div>
          <div class="section-sub">args: ${escapeHtml((step.arg_keys || []).join(', ') || 'none')}</div>
        </div>`;
      }
      if (step.kind === 'trajectory') {
        return `<div class="bp-node kind-tool">
          <div class="bp-node-head">
            <span>trajectory()</span>
            <span class="telemetry-pill">L${step.line}</span>
          </div>
          <div class="section-sub">tools filter: ${escapeHtml((step.tools || []).join(', ') || 'all steps')}</div>
        </div>`;
      }
      return '';
    }

    function renderBlueprint() {
      const bp = telemetry.blueprint || {};
      const wf = telemetry.workflow || {};
      const inv = telemetry.inventory || {};
      const rollups = telemetry.phase_rollups || [];
      const rollupByPhase = {};
      rollups.forEach(r => { rollupByPhase[r.phase] = r; });

      const q = getSearchQuery();
      const filteredW = getFilteredWorkers();
      const allowedPhasesByRole = new Set();
      filteredW.forEach(w => {
        if (w.phase) allowedPhasesByRole.add(w.phase);
        (w.phases || []).forEach(p => allowedPhasesByRole.add(p));
      });
      const allPhases = bp.phases || [];
      const phases = allPhases.filter(p => {
        if (activePhaseFilter !== 'all' && p.name !== activePhaseFilter) return false;
        if (telemetry.mode !== 'blueprint' && activeRoleFilter !== 'all' && !allowedPhasesByRole.has(p.name)) return false;
        if (!q) return true;
        return JSON.stringify(p).toLowerCase().includes(q);
      });

      const flowHtml = phases.length ? phases.map((p, idx) => {
        const pr = rollupByPhase[p.name];
        const liveBadge = pr
          ? `<span class="telemetry-pill">${pr.done_count}/${pr.worker_count} done · ${escapeHtml(pr.wall_span_label)} · ${formatTokens(pr.tokens_total)} tok</span>`
          : `<span class="telemetry-pill">line ${p.line} · ${(p.steps || []).length} op(s)</span>`;
        return `<div class="phase-box">
          <div class="phase-box-head">
            <span class="phase-badge">Phase ${idx + 1}: ${escapeHtml(p.name)}</span>
            ${liveBadge}
          </div>
          <div class="phase-steps">
            ${(p.steps || []).map(renderStepNode).join('') || '<div class="section-sub">Script-only logic / logs in this phase.</div>'}
          </div>
        </div>`;
      }).join('') : '<div class="section-sub">No static script phases matched the active filter (or script source was unavailable).</div>';

      const skillsDeclared = inv.skills_declared || [];
      const skillsObserved = inv.skills_observed || [];
      const scriptTools = inv.script_tools || [];
      const agentTools = inv.agent_tools || [];

      const filterText = (s) => !q || String(s).toLowerCase().includes(q);
      const skillChips = [
        ...skillsObserved.filter(filterText).map(s => `<span class="chip chip-skill">✓ ${escapeHtml(s)}</span>`),
        ...skillsDeclared.filter(s => !skillsObserved.includes(s) && filterText(s)).map(s => `<span class="chip">declared: ${escapeHtml(s)}</span>`),
      ].join('') || '<span class="section-sub">None detected</span>';

      const toolChips = [
        ...scriptTools.filter(t => filterText(t.name)).map(t => `<span class="chip chip-warn">script:${escapeHtml(t.name)} (${t.count})</span>`),
        ...agentTools.filter(t => filterText(t.name)).map(t => `<span class="chip chip-tool">${escapeHtml(t.name)} (${t.count})</span>`),
      ].join('') || '<span class="section-sub">None recorded</span>';

      const agentDefChips = (bp.agents || []).filter(a => {
        if (activePhaseFilter !== 'all' && a.phase !== activePhaseFilter) return false;
        return !q || `${a.role} ${a.type_name} ${a.model} ${a.workspace} ${a.phase}`.toLowerCase().includes(q);
      }).map(a => `<span class="chip">${escapeHtml(a.role)} [${escapeHtml(a.type_name)} · ${escapeHtml(a.model)} · ${escapeHtml(a.mode)}]</span>`).join('') || '<span class="section-sub">No matching agent defs</span>';

      const numberedSource = wf.script_source
        ? wf.script_source.split('\n').map((ln, i) => `${String(i + 1).padStart(3, ' ')} | ${ln}`).join('\n')
        : '';

      const argsJson = wf.args && Object.keys(wf.args).length ? JSON.stringify(wf.args, null, 2) : '';

      document.getElementById('blueprintPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Script Blueprint &amp; Component Architecture</div>
            <div class="section-sub">Static AST topology (phases, parallel fan-outs, pipelines, agents, call_tool) joined with runtime skill &amp; tool inventory</div>
          </div>
          <div class="chip-wrap">
            ${wf.script_path ? `<span class="telemetry-pill">${escapeHtml(wf.script_path.split('/').pop())} (${bp.line_count || 0} LOC)</span>` : '<span class="telemetry-pill">Inline Script</span>'}
            ${(bp.imports || []).length ? `<span class="telemetry-pill">imports: ${escapeHtml(bp.imports.join(', '))}</span>` : ''}
          </div>
        </div>
        <div class="dag-flow">${flowHtml}</div>
        <div class="inventory-grid">
          <div class="inv-card">
            <div class="inv-title">Agents Defined in Script (${(bp.agents || []).length})</div>
            <div class="chip-wrap">${agentDefChips}</div>
          </div>
          <div class="inv-card">
            <div class="inv-title">Skills &amp; Agent Types (Loaded vs Declared)</div>
            <div class="chip-wrap">${skillChips}</div>
          </div>
          <div class="inv-card">
            <div class="inv-title">Tools Used (Script call_tool + Agent Tools)</div>
            <div class="chip-wrap">${toolChips}</div>
          </div>
        </div>
        ${argsJson ? `
          <details class="sub-details">
            <summary>Workflow Input Args (${Object.keys(wf.args).length} key(s))${bp.manifest ? ' + workflow.json Manifest' : ''}</summary>
            <div class="sub-details-body"><div class="code-box">${escapeHtml(argsJson)}${bp.manifest ? '\n\n// workflow.json\n' + escapeHtml(JSON.stringify(bp.manifest, null, 2)) : ''}</div></div>
          </details>` : ''}
        ${numberedSource ? `
          <details class="sub-details" ${telemetry.mode === 'blueprint' ? 'open' : ''}>
            <summary>Workflow Python Script Source (${bp.line_count || 0} lines)</summary>
            <div class="sub-details-body"><div class="code-box">${escapeHtml(numberedSource)}</div></div>
          </details>` : ''}
      `;
    }

    function renderVerification() {
      const v = telemetry.verification || {};
      const allCmds = (v.verifier_commands && v.verifier_commands.length > 0)
        ? v.verifier_commands
        : (v.author_check_commands || []);
      const cmds = getFilteredCommands();
      const q = getSearchQuery();
      const isFiltered = activeRoleFilter !== 'all' || activePhaseFilter !== 'all' || q !== '';

      const pillCls = v.verdict === 'VERIFIED' ? 'pill-ok' : ((v.verdict === 'FAILED' || v.verdict === 'UNVERIFIED') ? 'pill-fail' : 'pill-warn');
      const orderNote = telemetry.mode === 'blueprint'
        ? (v.has_verifier ? `Verifier agent(s) planned in script: ${v.verifier_names.join(', ')}` : 'No explicit verifier/audit stage defined in script')
        : (v.ordered_after_edits
          ? `Verification ordered after last author edit (${v.last_author_edit_local || '—'} ≤ ${v.verifier_last_local || '—'})`
          : `Warning: author edits at ${v.last_author_edit_local || '—'} occurred after last verification (${v.verifier_last_local || '—'})`);

      const allowedRoles = new Set(getFilteredWorkers().map(w => w.role));
      const rolePhaseActive = activeRoleFilter !== 'all' || activePhaseFilter !== 'all';
      const allSvs = v.structured_verdicts || [];
      const svs = allSvs.filter(sv => {
        if (rolePhaseActive && sv.agent && !allowedRoles.has(sv.agent)) return false;
        if (q) {
          const hay = `${sv.agent || ''} ${sv.notes || ''} ${sv.raw || ''}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      const svHtml = svs.length ? `
        <div class="cards-grid" style="margin-bottom:10px;">
          ${svs.map(sv => {
            const svPillCls = sv.passed ? 'pill-ok' : (sv.remediated ? 'pill-warn' : 'pill-fail');
            const svPillTxt = sv.passed ? 'PASSED' : (sv.remediated ? 'REMEDIATED' : 'FAILED');
            return `
            <div class="deliverable-box" style="margin-bottom:0;">
              <div class="deliverable-header">
                <span>Structured Verdict · ${escapeHtml(sv.agent)}</span>
                <span class="badge-pill ${svPillCls}" style="font-size:0.65rem;padding:2px 8px;">${svPillTxt}</span>
              </div>
              <div class="deliverable-text" style="max-height:140px;">${escapeHtml(sv.notes || sv.raw)}</div>
            </div>`;
          }).join('')}
        </div>` : '';

      const failedCmds = cmds.filter(c => c.status !== 'passed');
      const passedCmds = cmds.filter(c => c.status === 'passed');
      const renderCmdTable = (list) => `<div class="cmd-scroll-wrap"><table class="cmd-table">
        <thead><tr><th>Time</th><th>Worker</th><th>Status</th><th>Command</th></tr></thead>
        <tbody>
          ${list.map(c => {
            const stPill = c.status === 'passed' ? 'pill-ok' : (c.status === 'failed' ? 'pill-fail' : 'pill-warn');
            const stTxt = c.status === 'passed' ? 'PASS (0)' : (c.status === 'failed' ? `FAIL (${c.exit_code})` : String(c.status || 'unknown').toUpperCase());
            return `<tr>
              <td>${escapeHtml(c.ts_local || '—')}</td>
              <td>${escapeHtml(c.agent || '')}</td>
              <td><span class="badge-pill ${stPill}" style="font-size:0.65rem;padding:2px 7px;">${escapeHtml(stTxt)}</span></td>
              <td class="cmd-code">${escapeHtml(c.command)}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;

      const failedBlock = failedCmds.length ? `
        <details class="sub-details" ${v.verdict === 'FAILED' ? 'open' : ''}>
          <summary>Non-Passing / Earlier Failed Commands (${failedCmds.length})</summary>
          <div class="sub-details-body">${renderCmdTable(failedCmds)}</div>
        </details>` : '';

      const cmdRows = allCmds.length ? `
        ${failedBlock}
        <details class="sub-details" ${(q && cmds.length <= 20) ? 'open' : ''}>
          <summary>Passed Check Commands (${passedCmds.length}${isFiltered ? ` of ${allCmds.length} total` : ''})</summary>
          <div class="sub-details-body">
            ${passedCmds.length ? renderCmdTable(passedCmds) : '<div class="section-sub">No passed check commands match current filter.</div>'}
          </div>
        </details>` : '';

      document.getElementById('verificationPanel').innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Verification &amp; Quality Gate <span class="badge-pill ${pillCls}">${escapeHtml(v.verdict_label || 'Unverified')}</span></div>
            <div class="section-sub">${escapeHtml(orderNote)}</div>
          </div>
        </div>
        <div class="verify-banner verdict-${escapeHtml(v.verdict || 'UNVERIFIED')}">
          <div>
            <strong>Verifiers:</strong> ${escapeHtml((v.verifier_names || []).join(', ') || 'None')} ·
            <strong>Checks:</strong> ${escapeHtml(v.passed_count || 0)} passed, ${escapeHtml(v.unresolved_failure_count || 0)} unresolved failures
            ${v.resolved_earlier_failure_count ? ` · ${v.resolved_earlier_failure_count} earlier failure(s) resolved` : ''}
          </div>
        </div>
        ${svHtml}
        ${cmdRows}
      `;
    }

    function renderResources() {
      const panel = document.getElementById('resourcesPanel');
      if (telemetry.mode === 'blueprint') {
        panel.classList.add('hidden');
        return;
      }
      panel.classList.remove('hidden');

      const allWorkers = telemetry.workers || [];
      const workers = getFilteredWorkers();
      const matchedPhaseSet = new Set();
      workers.forEach(w => {
        if (w.phase) matchedPhaseSet.add(w.phase);
        (w.phases || []).forEach(p => matchedPhaseSet.add(p));
      });
      const roleOrSearch = activeRoleFilter !== 'all' || getSearchQuery() !== '';
      const phases = (telemetry.phase_rollups || []).filter(p => {
        if (activePhaseFilter !== 'all' && p.phase !== activePhaseFilter) return false;
        if (roleOrSearch && !matchedPhaseSet.has(p.phase)) return false;
        return true;
      });
      const totTokens = Math.max(1, (telemetry.summary && telemetry.summary.tokens && telemetry.summary.tokens.total) || 1);

      function metricVal(w) {
        if (resourceMetric === 'fresh_tokens') return w.tokens.fresh || 0;
        if (resourceMetric === 'output_tokens') return w.tokens.output || 0;
        if (resourceMetric === 'active_time') return w.active_duration_s || 0;
        if (resourceMetric === 'tool_calls') return w.tool_call_count || 0;
        return w.tokens.total || 0;
      }

      const sorted = [...workers].sort((a, b) => metricVal(b) - metricVal(a));
      const maxVal = Math.max(1, ...sorted.map(metricVal));

      const barsHtml = sorted.length ? sorted.map(w => {
        const val = metricVal(w);
        const pct = Math.max(1.5, (val / maxVal) * 100);
        let segs = '';
        let lbl = '';
        if (resourceMetric === 'active_time') {
          segs = `<div class="bar-seg-active" style="width:${pct.toFixed(2)}%"></div>`;
          lbl = w.active_duration_label;
        } else if (resourceMetric === 'tool_calls') {
          segs = `<div class="bar-seg-active" style="width:${pct.toFixed(2)}%"></div>`;
          lbl = `${val} tool(s)`;
        } else if (resourceMetric === 'output_tokens') {
          segs = `<div class="bar-seg-out" style="width:${pct.toFixed(2)}%"></div>`;
          lbl = formatTokens(val);
        } else if (resourceMetric === 'fresh_tokens') {
          const inW = (w.tokens.input / maxVal) * 100;
          const outW = (w.tokens.output / maxVal) * 100;
          segs = `<div class="bar-seg-in" style="width:${inW.toFixed(2)}%"></div><div class="bar-seg-out" style="width:${outW.toFixed(2)}%"></div>`;
          lbl = formatTokens(val);
        } else {
          const inW = (w.tokens.input / maxVal) * 100;
          const outW = (w.tokens.output / maxVal) * 100;
          const cacheW = (w.tokens.cache_read / maxVal) * 100;
          segs = `<div class="bar-seg-in" style="width:${inW.toFixed(2)}%"></div><div class="bar-seg-out" style="width:${outW.toFixed(2)}%"></div><div class="bar-seg-cache" style="width:${cacheW.toFixed(2)}%"></div>`;
          lbl = `${formatTokens(val)} (${((val / totTokens) * 100).toFixed(1)}%)`;
        }
        return `<div class="bar-row">
          <div class="bar-label" data-action="jump-agent" data-conv-id="${escapeHtml(w.conv_id)}" title="Jump to ${escapeHtml(w.role)}">${escapeHtml(w.role)}</div>
          <div class="bar-track">${segs}</div>
          <div class="bar-val">${escapeHtml(lbl)}</div>
        </div>`;
      }).join('') : '<div class="section-sub">No workers match current filter.</div>';

      const hiAct = resourceMetric === 'active_time' ? 'metric-hi' : '';
      const hiOut = resourceMetric === 'output_tokens' ? 'metric-hi' : '';
      const hiFresh = resourceMetric === 'fresh_tokens' ? 'metric-hi' : '';
      const hiTot = resourceMetric === 'total_tokens' ? 'metric-hi' : '';

      const phaseRows = phases.map(p => `
        <tr>
          <td><strong>${escapeHtml(p.phase)}</strong> (${p.done_count}/${p.worker_count})</td>
          <td>${escapeHtml(p.wall_span_label)}</td>
          <td class="${hiAct}">${escapeHtml(p.active_duration_label)}</td>
          <td class="${hiOut}">${escapeHtml(formatTokens(p.tokens_output))}</td>
          <td class="${hiFresh}">${escapeHtml(formatTokens(p.tokens_fresh))}</td>
          <td class="${hiTot}">${escapeHtml(formatTokens(p.tokens_total))} (${p.token_share_pct}%)</td>
        </tr>
      `).join('');

      const matrixRows = sorted.map(w => `
        <tr>
          <td><a href="#worker-${escapeHtml(w.conv_id)}" data-action="jump-agent" data-conv-id="${escapeHtml(w.conv_id)}" style="color:#7dd3fc;text-decoration:none;">${escapeHtml(w.role)}</a></td>
          <td>${escapeHtml(w.phase)}</td>
          <td>${escapeHtml(w.type_name)}</td>
          <td>${escapeHtml(w.model)}</td>
          <td class="${hiAct}">${escapeHtml(w.active_duration_label)}</td>
          <td>${w.tool_call_count}</td>
          <td>${escapeHtml(formatTokens(w.tokens.input))}</td>
          <td class="${hiOut}">${escapeHtml(formatTokens(w.tokens.output))}</td>
          <td>${escapeHtml(formatTokens(w.tokens.cache_read))} (${w.tokens.cache_hit_pct}%)</td>
          <td class="${hiTot}"><strong>${escapeHtml(formatTokens(w.tokens.total))}</strong></td>
        </tr>
      `).join('');

      const scope = workers.length !== allWorkers.length ? ` (${workers.length} / ${allWorkers.length} workers)` : '';

      panel.innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Where Time &amp; Tokens Went${escapeHtml(scope)}</div>
            <div class="section-sub">Per-worker and per-phase execution time, tool count, and token breakdown</div>
          </div>
          <div class="toggle-group" id="resToggles">
            <button type="button" class="toggle-btn ${resourceMetric === 'total_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="total_tokens">Total Tokens</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'fresh_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="fresh_tokens">Fresh (In+Out)</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'output_tokens' ? 'active' : ''}" data-action="res-metric" data-metric="output_tokens">Output</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'active_time' ? 'active' : ''}" data-action="res-metric" data-metric="active_time">Active Time</button>
            <button type="button" class="toggle-btn ${resourceMetric === 'tool_calls' ? 'active' : ''}" data-action="res-metric" data-metric="tool_calls">Tool Calls</button>
          </div>
        </div>
        <div class="breakdown-grid">
          <div>
            <div class="bar-list">${barsHtml}</div>
            <div class="legend-row">
              <span class="legend-item"><span class="legend-dot" style="background:#38bdf8"></span>Input</span>
              <span class="legend-item"><span class="legend-dot" style="background:#c084fc"></span>Output</span>
              <span class="legend-item"><span class="legend-dot" style="background:rgba(13,148,136,0.75)"></span>Cache Read</span>
              <span class="legend-item"><span class="legend-dot" style="background:#6366f1"></span>Time / Tools</span>
            </div>
          </div>
          <div style="overflow-x:auto;">
            <table class="cmd-table">
              <thead><tr><th>Phase</th><th>Span</th><th>Active</th><th>Out</th><th>In+Out</th><th>Total (%)</th></tr></thead>
              <tbody>${phaseRows || '<tr><td colspan="6">No phases recorded</td></tr>'}</tbody>
            </table>
          </div>
        </div>
        <details class="sub-details">
          <summary>Per-Worker Resource Matrix (${workers.length} of ${allWorkers.length})</summary>
          <div class="sub-details-body" style="overflow-x:auto;">
            <table class="cmd-table">
              <thead><tr><th>Worker</th><th>Phase</th><th>Type</th><th>Model</th><th>Active</th><th>Tools</th><th>Input</th><th>Output</th><th>Cache (Hit)</th><th>Total</th></tr></thead>
              <tbody>${matrixRows}</tbody>
            </table>
          </div>
        </details>
      `;
    }

    function renderGantt() {
      const panel = document.getElementById('ganttPanel');
      if (telemetry.mode === 'blueprint') {
        panel.classList.add('hidden');
        return;
      }
      panel.classList.remove('hidden');

      const g = telemetry.gantt || {};
      const allowedIds = new Set(getFilteredWorkers().map(w => w.conv_id));
      const allRows = g.rows || [];
      const rows = allRows.filter(r => allowedIds.has(r.conv_id));
      const isComp = ganttScaleMode === 'compressed' && g.has_compressed_gaps;

      const rowsHtml = rows.map(r => {
        const turns = isComp ? r.turns_comp : r.turns_true;
        const turnHtml = turns.map(t =>
          `<div class="gantt-turn-bar bar-cat-${escapeHtml(r.role_category)}" style="left:${t.left_pct}%;width:${t.width_pct}%" title="${escapeHtml(t.label)}: ${escapeHtml(t.start_local)} → ${escapeHtml(t.end_local)} (${escapeHtml(t.duration_label)}, ${formatTokens(t.tokens)} tok)"></div>`
        ).join('');
        return `<div class="gantt-row" data-action="jump-agent" data-conv-id="${escapeHtml(r.conv_id)}">
          <div class="gantt-label">
            <span class="role-tag rt-${escapeHtml(r.role_category)}" style="font-size:0.60rem;padding:2px 6px;">${escapeHtml(r.phase.slice(0, 8))}</span>
            <span class="gantt-name">${escapeHtml(r.name)}</span>
          </div>
          <div class="gantt-track">${turnHtml}</div>
          <div class="gantt-dur">${escapeHtml(r.active_duration_label)}</div>
        </div>`;
      }).join('');

      panel.innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Execution Gantt Waterfall (${rows.length} / ${allRows.length})</div>
            <div class="section-sub">Parallel fan-outs overlap vertically; click any row to jump to its deliverable card</div>
          </div>
          ${g.has_compressed_gaps ? `
            <div class="toggle-group">
              <button type="button" class="toggle-btn ${isComp ? 'active' : ''}" data-action="gantt-scale" data-mode="compressed">Compressed Pauses</button>
              <button type="button" class="toggle-btn ${!isComp ? 'active' : ''}" data-action="gantt-scale" data-mode="true">True Wall-Clock</button>
            </div>` : ''}
        </div>
        <div class="gantt-axis">
          <div>Phase · Worker</div>
          <div class="gantt-axis-track">
            <span>${escapeHtml(g.wall_start_local || '—')}</span>
            <span>${escapeHtml(g.wall_end_local || '—')}</span>
          </div>
          <div style="text-align:right;">Active</div>
        </div>
        <div class="gantt-rows">${rowsHtml || '<div class="section-sub">No workers match current filter.</div>'}</div>
      `;
    }

    function renderDeliverables() {
      const panel = document.getElementById('deliverablesPanel');
      if (telemetry.mode === 'blueprint') {
        panel.classList.add('hidden');
        return;
      }
      panel.classList.remove('hidden');

      const allWorkers = telemetry.workers || [];
      const workers = getFilteredWorkers();

      const cardsHtml = workers.map(w => {
        const stPill = w.status === 'done' ? 'pill-ok' : (w.status === 'running' ? 'pill-warn' : 'pill-fail');
        const filesHtml = (w.docs || []).length ? `
          <div class="files-strip">
            ${w.docs.map(d => `<a class="doc-link-item" href="${escapeHtml(d.path)}">${escapeHtml(d.action)}: ${escapeHtml(d.name)}</a>`).join('')}
          </div>` : '';

        const skillsHtml = (w.skills_loaded || []).map(s => `<span class="chip chip-skill">${escapeHtml(s)}</span>`).join('');
        const toolsHtml = (w.tool_breakdown || []).map(tb => `<span class="chip chip-tool">${escapeHtml(tb.name)}: ${tb.count}</span>`).join('');

        const turnRows = (w.turns || []).map(t => `
          <tr>
            <td>#${t.index}</td>
            <td>${escapeHtml(t.start_local)} → ${escapeHtml(t.end_local)}</td>
            <td>${escapeHtml(t.duration_label)}</td>
            <td>${t.tool_call_count}</td>
            <td>${escapeHtml(formatTokens(t.tokens.total))}</td>
            <td>${escapeHtml(t.prompt_preview || '—')}</td>
          </tr>
        `).join('');

        return `<article class="agent-card" id="worker-${escapeHtml(w.conv_id)}">
          <div class="card-top">
            <div class="card-title-group">
              <span class="agent-name">${escapeHtml(w.role)}</span>
              <span class="phase-badge" style="font-size:0.70rem;padding:2px 8px;">${escapeHtml(w.phase)}</span>
              <span class="role-tag rt-${escapeHtml(w.role_category)}">${escapeHtml(w.role_label)}</span>
              <span class="badge-pill ${stPill}" style="font-size:0.65rem;padding:2px 8px;">${escapeHtml(w.status)}</span>
              <span class="telemetry-pill">type: ${escapeHtml(w.type_name)}</span>
              <span class="telemetry-pill">${escapeHtml(w.model)}</span>
            </div>
            <div class="telemetry-strip" style="margin-bottom:0;">
              <span class="telemetry-pill">${escapeHtml(w.wall_start_local)} → ${escapeHtml(w.wall_end_local)}</span>
              <span class="telemetry-pill">active: ${escapeHtml(w.active_duration_label)}</span>
            </div>
          </div>
          <div class="telemetry-strip">
            <span class="telemetry-pill">tokens: ${escapeHtml(formatTokens(w.tokens.total))} (in ${escapeHtml(formatTokens(w.tokens.input))} · out ${escapeHtml(formatTokens(w.tokens.output))} · cache ${escapeHtml(formatTokens(w.tokens.cache_read))}, ${w.tokens.cache_hit_pct}% hit)</span>
            <span class="telemetry-pill">turns: ${(w.turns || []).length} · steps: ${w.step_count} · tools: ${w.tool_call_count}</span>
            ${w.transcript_uri ? `<a class="doc-link-item" href="${escapeHtml(w.transcript_uri)}">Open Transcript</a>` : ''}
          </div>
          ${(skillsHtml || toolsHtml) ? `<div class="chip-wrap" style="margin-bottom:9px;">${skillsHtml}${toolsHtml}</div>` : ''}
          ${w.deliverable_text ? `
            <div class="deliverable-box">
              <div class="deliverable-header">
                <span>Structured finish() Deliverable</span>
                <span>${(w.docs || []).length} file(s) touched</span>
              </div>
              <div class="deliverable-text">${escapeHtml(w.deliverable_text)}</div>
              ${filesHtml}
            </div>` : filesHtml}
          <details class="sub-details">
            <summary>Prompts &amp; Execution Turns (${(w.turns || []).length})</summary>
            <div class="sub-details-body" style="overflow-x:auto;">
              ${turnRows ? `<table class="cmd-table"><thead><tr><th>#</th><th>Clock</th><th>Active</th><th>Tools</th><th>Tokens</th><th>Prompt Preview</th></tr></thead><tbody>${turnRows}</tbody></table>` : '<div class="section-sub">No turn details available.</div>'}
            </div>
          </details>
        </article>`;
      }).join('');

      panel.innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Worker Deliverables &amp; Structured Outputs (${workers.length} / ${allWorkers.length})</div>
            <div class="section-sub">Full finish() payloads, skills loaded, tools called, files modified, and per-turn prompt history</div>
          </div>
        </div>
        <div class="cards-grid">${cardsHtml || '<div class="section-sub">No workers match current filter.</div>'}</div>
      `;
    }

    function renderLogs() {
      const panel = document.getElementById('logsPanel');
      if (telemetry.mode === 'blueprint') {
        panel.classList.add('hidden');
        return;
      }
      panel.classList.remove('hidden');

      const wf = telemetry.workflow || {};
      const git = telemetry.git_snapshot || {};
      const allEntries = wf.log_entries || [];
      const entries = getFilteredLogs();

      const rowsHtml = entries.map(e => `
        <div class="log-row kind-${escapeHtml(e.kind)}">
          <span class="telemetry-pill" style="min-width:90px;text-align:center;">${escapeHtml(e.phase || '—')}</span>
          <span class="telemetry-pill" style="min-width:58px;text-align:center;">${escapeHtml(e.kind)}</span>
          <div class="log-text">${escapeHtml(e.text)}</div>
        </div>
      `).join('');

      const gitHtml = git.available ? `
        <details class="sub-details" style="margin-bottom:12px;">
          <summary>Workspace Git Snapshot (${(git.modified || []).length} tracked · ${(git.untracked || []).length} untracked)</summary>
          <div class="sub-details-body">
            <div class="code-box">${escapeHtml(git.diffstat || '(no tracked diff)')}${git.untracked && git.untracked.length ? '\n\nUntracked:\n' + escapeHtml(git.untracked.join('\n')) : ''}</div>
          </div>
        </details>` : '';

      panel.innerHTML = `
        <div class="section-header">
          <div>
            <div class="section-title">Workflow Logs &amp; Script Output (${entries.length} / ${allEntries.length})</div>
            <div class="section-sub">Archived phase logs, log() statements, and script stdout/stderr</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            ${wf.task_log_uri ? `<a class="doc-link-item" href="${escapeHtml(wf.task_log_uri)}">Open task log</a>` : ''}
            <div class="toggle-group">
              <button type="button" class="toggle-btn ${logKindFilter === 'all' ? 'active' : ''}" data-action="log-filter" data-kind="all">All</button>
              <button type="button" class="toggle-btn ${logKindFilter === 'phase' ? 'active' : ''}" data-action="log-filter" data-kind="phase">Phases</button>
              <button type="button" class="toggle-btn ${logKindFilter === 'agent' ? 'active' : ''}" data-action="log-filter" data-kind="agent">Agents</button>
              <button type="button" class="toggle-btn ${logKindFilter === 'log' ? 'active' : ''}" data-action="log-filter" data-kind="log">Script log()</button>
              <button type="button" class="toggle-btn ${logKindFilter === 'error' ? 'active' : ''}" data-action="log-filter" data-kind="error">Errors</button>
            </div>
          </div>
        </div>
        ${wf.output ? `
          <div class="deliverable-box">
            <div class="deliverable-header"><span>Script Output (stdout / repr)</span></div>
            <div class="deliverable-text">${escapeHtml(wf.output)}</div>
          </div>` : ''}
        ${wf.error_text ? `
          <div class="deliverable-box" style="border-color:rgba(239,68,68,0.45);">
            <div class="deliverable-header" style="color:#fca5a5;"><span>Workflow Error</span></div>
            <div class="deliverable-text">${escapeHtml(wf.error_text)}</div>
          </div>` : ''}
        ${gitHtml}
        <div>${rowsHtml || '<div class="section-sub">No workflow log lines match current filter.</div>'}</div>
      `;
    }

    function renderFilterBanner() {
      const banner = document.getElementById('filterBanner');
      if (!banner) return;
      const q = getSearchQuery();
      const isFiltered = activeRoleFilter !== 'all' || activePhaseFilter !== 'all' || q !== '' || logKindFilter !== 'all';
      if (!isFiltered) {
        banner.classList.remove('visible');
        banner.innerHTML = '';
        return;
      }
      const parts = [];
      if (activeRoleFilter !== 'all') parts.push(`Role: ${activeRoleFilter}`);
      if (activePhaseFilter !== 'all') parts.push(`Phase: ${activePhaseFilter}`);
      if (q) parts.push(`Search: "${q}"`);
      if (logKindFilter !== 'all') parts.push(`Logs: ${logKindFilter}`);

      const totalW = (telemetry.workers || []).length;
      const shownW = getFilteredWorkers().length;
      const totalL = ((telemetry.workflow && telemetry.workflow.log_entries) || []).length;
      const shownL = getFilteredLogs().length;

      banner.innerHTML = `
        <span><strong>Active Filter</strong> (${escapeHtml(parts.join(' · '))}) — Showing <strong>${shownW}/${totalW}</strong> workers · <strong>${shownL}/${totalL}</strong> log entries</span>
        <button type="button" class="clear-filter-btn" data-action="reset-filters">Reset</button>
      `;
      banner.classList.add('visible');
    }

    function setRoleFilter(role) {
      activeRoleFilter = role;
      document.querySelectorAll('[data-action="role-filter"]').forEach(b => {
        b.classList.toggle('active', b.dataset.role === role);
      });
      applyFilters();
    }

    function setPhaseFilter(phase) {
      activePhaseFilter = phase || 'all';
      const sel = document.getElementById('phaseFilterSelect');
      if (sel) {
        sel.value = activePhaseFilter;
        sel.classList.toggle('active', activePhaseFilter !== 'all');
      }
      applyFilters();
    }

    function setViewTab(tab) {
      activeViewTab = tab || 'all';
      renderViewTabs();
      applyViewTabVisibility();
    }

    function resetAllFilters() {
      activeRoleFilter = 'all';
      activePhaseFilter = 'all';
      logKindFilter = 'all';
      const inp = document.getElementById('searchInput');
      if (inp) inp.value = '';
      const sel = document.getElementById('phaseFilterSelect');
      if (sel) {
        sel.value = 'all';
        sel.classList.remove('active');
      }
      document.querySelectorAll('[data-action="role-filter"]').forEach(b => {
        b.classList.toggle('active', b.dataset.role === 'all');
      });
      applyFilters();
    }

    function applyFilters() {
      renderSummary();
      renderViewTabs();
      renderFilterBanner();
      renderBlueprint();
      renderVerification();
      renderResources();
      renderGantt();
      renderDeliverables();
      renderLogs();
      applyViewTabVisibility();
    }

    function jumpToWorker(convId) {
      if (activeViewTab !== 'all' && activeViewTab !== 'deliverables') {
        setViewTab('deliverables');
      }
      const el = document.getElementById('worker-' + convId);
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
        setRoleFilter(target.dataset.role || 'all');
      } else if (action === 'phase-filter') {
        setPhaseFilter(target.dataset.phase || 'all');
      } else if (action === 'view-tab') {
        setViewTab(target.dataset.tab || 'all');
      } else if (action === 'res-metric') {
        resourceMetric = target.dataset.metric || 'total_tokens';
        renderResources();
      } else if (action === 'gantt-scale') {
        ganttScaleMode = target.dataset.mode || 'compressed';
        renderGantt();
      } else if (action === 'log-filter') {
        logKindFilter = target.dataset.kind || 'all';
        renderViewTabs();
        renderFilterBanner();
        renderLogs();
      } else if (action === 'jump-agent') {
        if (e.preventDefault) e.preventDefault();
        jumpToWorker(target.dataset.convId || '');
      } else if (action === 'reset-filters') {
        resetAllFilters();
      }
    });

    const phaseSelEl = document.getElementById('phaseFilterSelect');
    if (phaseSelEl) {
      phaseSelEl.addEventListener('change', (e) => setPhaseFilter(e.target.value || 'all'));
    }

    const searchEl = document.getElementById('searchInput');
    if (searchEl) {
      searchEl.addEventListener('input', applyFilters);
      searchEl.addEventListener('search', applyFilters);
    }

    renderHeader();
    applyFilters();
  </script>
</body>
</html>"""


def render_html(telemetry: Dict[str, Any]) -> str:
    """Safely embed telemetry JSON into HTML_TEMPLATE."""
    payload = json.dumps(telemetry, indent=2).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TELEMETRY_DATA_PLACEHOLDER__", payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an interactive AGY `run_workflow` blueprint & post-run HTML report."
    )
    parser.add_argument(
        "-s",
        "--script",
        help="Analyze a Python workflow script directly in Pre-Run Static Blueprint mode (no prior execution required).",
    )
    parser.add_argument(
        "-c",
        "--conversation-id",
        help="Parent conversation ID or spawned workflow worker conversation ID (or unique prefix) to render.",
    )
    parser.add_argument(
        "--run-index",
        type=int,
        default=-1,
        help="1-based `run_workflow` invocation index inside a conversation (default: latest).",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List matching `run_workflow` runs for the workspace and exit.",
    )
    parser.add_argument(
        "--all-workspaces",
        action="store_true",
        help="Include all workspaces when used with --list.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output HTML path (default: <workspace>/.agents/workflow-trajectory.html).",
    )
    parser.add_argument(
        "-w",
        "--workspace",
        help="Project workspace root (default: cwd).",
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
    workspace_root = resolve_workspace_root(args.workspace)
    agy_dir = resolve_agy_dir(args.agy_dir)

    if args.list:
        runs = list_workflow_runs(agy_dir, workspace_root, all_workspaces=args.all_workspaces)
        if not runs:
            print(f"No run_workflow executions found matching workspace: {workspace_root}")
            return 0
        print(f"run_workflow runs for {workspace_root} (data dir: {agy_dir}):")
        for r in runs:
            print(
                f"  {r['conversation_id']}  status={r['status']:<10} "
                f"runs={r['invocation_count']:<3} workers={r['worker_count']:<3} "
                f"updated={str(r['last_modified_time'])[:19]}  {r['latest_description']}"
            )
        return 0

    if args.script:
        telemetry = parse_script_only(args.script, workspace_root)
    else:
        selected_id = select_workflow_run(agy_dir, workspace_root, args.conversation_id)
        if not selected_id:
            if args.conversation_id:
                print(
                    f"Error: Conversation or workflow worker '{args.conversation_id}' not found with run_workflow telemetry under {agy_dir}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Error: No run_workflow runs found for workspace {workspace_root}. "
                    "Pass --script <workflow.py> for pre-run blueprint mode, or --list --all-workspaces.",
                    file=sys.stderr,
                )
            return 1
        try:
            telemetry = parse_workflow_run(
                agy_dir,
                selected_id,
                workspace_root,
                run_index=args.run_index,
                include_git=not args.no_git,
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    out_path = os.path.abspath(args.output) if args.output else os.path.join(workspace_root, ".agents", "workflow-trajectory.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_html(telemetry))

    s = telemetry["summary"]
    v = telemetry["verification"]
    bp = telemetry["blueprint"]
    if s["mode"] == "blueprint":
        print(f"Workflow blueprint generated: {out_path}")
        print(f"  Script: {telemetry['workflow']['script_path']} ({bp['line_count']} lines)")
        print(
            f"  Components: {bp['counts']['phases']} phase(s), {bp['counts']['agents']} agent def(s), "
            f"{bp['counts']['parallel_blocks']} parallel, {bp['counts']['pipeline_blocks']} pipeline, "
            f"{bp['counts']['tool_calls']} call_tool, {len(bp['warnings'])} pre-flight note(s)"
        )
    else:
        tok = s["tokens"]
        print(f"Workflow report generated: {out_path}")
        print(f"  Run: {telemetry['run_title']} ({telemetry['root_conversation_id']})")
        print(
            f"  Outcome: {s['outcome_label']} | Verification: {v['verdict_label']} "
            f"({v['passed_count']} passed, {v['unresolved_failure_count']} unresolved)"
        )
        print(
            f"  Wall-clock: {s['wall_start_local']} -> {s['wall_end_local']} "
            f"(span {s['wall_span_label']}, worker sum {s['cumulative_worker_label']}, "
            f"peak parallel {s['peak_worker_concurrency']}, speedup {s['parallelism_speedup']}x)"
        )
        print(
            f"  Workers: {s['done_workers']}/{s['worker_count']} done ({s['total_turns']} turns), "
            f"tokens: {tok['total']:,} (in {tok['input']:,}, out {tok['output']:,}, cache {tok['cache_read']:,}), "
            f"files: {s['unique_file_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
