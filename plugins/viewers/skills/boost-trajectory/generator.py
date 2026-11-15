#!/usr/bin/env python3
"""Generate an interactive dark-mode HTML trajectory dashboard for AGY /boost runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from boost_telemetry import (  # noqa: E402
    list_boost_runs,
    parse_boost_run,
    resolve_agy_dir,
    resolve_workspace_root,
    select_boost_run,
)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>/boost Execution Trajectory</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0f1d;
      --panel-dark: rgba(16, 22, 38, 0.80);
      --panel-elevated: rgba(22, 30, 50, 0.90);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-glowing: rgba(124, 58, 237, 0.45);
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

      --gradient-primary: linear-gradient(135deg, #7c3aed, #0284c7);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background-color: var(--bg-dark);
      background-image:
        radial-gradient(at 0% 0%, rgba(124, 58, 237, 0.16) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(2, 132, 199, 0.14) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(13, 148, 136, 0.08) 0px, transparent 60%);
      background-attachment: fixed;
      font-family: 'Inter', sans-serif;
      color: var(--text-main);
      line-height: 1.6;
      overflow-x: hidden;
      padding-bottom: 80px;
    }

    header {
      padding: 26px 20px 20px;
      text-align: center;
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(14px);
      background-color: rgba(10, 15, 29, 0.78);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-content { max-width: 1320px; margin: 0 auto; }

    .badge-row {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 10px;
    }

    .badge-boost {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(124, 58, 237, 0.18);
      border: 1px solid rgba(124, 58, 237, 0.4);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: #c4b5fd;
    }

    .badge-routine {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 11px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }
    .routine-delegation { background: rgba(2, 132, 199, 0.16); border: 1px solid rgba(2, 132, 199, 0.38); color: #7dd3fc; }
    .routine-solo { background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(16, 185, 129, 0.35); color: #6ee7b7; }
    .routine-mixed { background: rgba(245, 158, 11, 0.16); border: 1px solid rgba(245, 158, 11, 0.35); color: #fcd34d; }

    .badge-meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 11px;
      border-radius: 20px;
      font-family: 'Fira Code', monospace;
      font-size: 0.75rem;
      color: var(--text-muted);
      cursor: pointer;
    }
    .badge-meta:hover { border-color: var(--border-glowing); color: var(--text-main); }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.1rem;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 30%, #38bdf8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 6px;
      letter-spacing: -0.6px;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.92rem;
      max-width: 920px;
      margin: 0 auto 16px;
    }

    .controls {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px;
      max-width: 1180px;
      margin: 0 auto;
    }

    .search-container { position: relative; flex: 1 1 260px; max-width: 360px; }

    .search-input {
      width: 100%;
      background: rgba(16, 22, 38, 0.92);
      border: 1px solid var(--border-color);
      padding: 9px 14px 9px 38px;
      border-radius: 10px;
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      font-size: 0.87rem;
      outline: none;
      transition: all 0.25s ease;
    }
    .search-input:focus {
      border-color: var(--glow-purple);
      box-shadow: 0 0 14px rgba(124, 58, 237, 0.28);
    }

    .search-icon {
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
    }

    .filter-btn {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 8px 14px;
      border-radius: 10px;
      font-weight: 500;
      font-size: 0.83rem;
      cursor: pointer;
      transition: all 0.2s ease;
    }
    .filter-btn:hover, .filter-btn.active {
      color: var(--text-main);
      background: rgba(124, 58, 237, 0.18);
      border-color: var(--glow-purple);
    }

    .container { max-width: 1320px; margin: 26px auto 0; padding: 0 20px; }

    /* KPI Strip */
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(195px, 1fr));
      gap: 14px;
      margin-bottom: 26px;
    }

    .kpi-card {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 15px 17px;
      backdrop-filter: blur(12px);
    }

    .kpi-label {
      font-size: 0.71rem;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }

    .kpi-value {
      font-family: 'Outfit', sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.2;
    }

    .kpi-sub {
      margin-top: 4px;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
    }

    /* Pipeline Section */
    .pipeline-section {
      margin-bottom: 36px;
      border: 1px solid var(--border-color);
      border-radius: 18px;
      background: rgba(12, 17, 30, 0.55);
      padding: 20px;
    }

    .pipeline-banner {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border-color);
    }

    .pipeline-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.25rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .pipeline-prompt {
      margin-top: 6px;
      font-size: 0.88rem;
      color: #cbd5e1;
      max-width: 960px;
    }

    .pipeline-stats-pills {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    /* Gantt Waterfall */
    .gantt-panel {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 24px;
    }

    .gantt-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
    }

    .gantt-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.08rem;
      font-weight: 700;
    }

    .gantt-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

    .mode-pill {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 5px 11px;
      border-radius: 8px;
      font-size: 0.77rem;
      font-weight: 600;
      cursor: pointer;
    }
    .mode-pill.active {
      background: rgba(2, 132, 199, 0.22);
      border-color: var(--glow-blue);
      color: #7dd3fc;
    }

    .gantt-axis {
      display: grid;
      grid-template-columns: 310px 1fr 155px;
      gap: 12px;
      align-items: center;
      font-family: 'Fira Code', monospace;
      font-size: 0.7rem;
      color: var(--text-dim);
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 8px;
    }

    .gantt-axis-track {
      display: flex;
      justify-content: space-between;
      height: 18px;
    }

    .gantt-rows { display: flex; flex-direction: column; gap: 6px; }

    .gantt-row {
      display: grid;
      grid-template-columns: 310px 1fr 155px;
      gap: 12px;
      align-items: center;
      padding: 5px 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .gantt-row:hover { background: rgba(255, 255, 255, 0.045); }

    .gantt-label {
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
      font-size: 0.81rem;
      font-weight: 600;
    }

    .gantt-label-text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .tier-chip {
      font-family: 'Fira Code', monospace;
      font-size: 0.64rem;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 5px;
      flex-shrink: 0;
    }
    .tier-1 { background: rgba(124, 58, 237, 0.22); color: #c4b5fd; border: 1px solid rgba(124, 58, 237, 0.4); }
    .tier-2 { background: rgba(2, 132, 199, 0.22); color: #7dd3fc; border: 1px solid rgba(2, 132, 199, 0.4); }
    .tier-3 { background: rgba(219, 39, 119, 0.22); color: #f9a8d4; border: 1px solid rgba(219, 39, 119, 0.4); }

    .gantt-model-chip {
      font-family: 'Fira Code', monospace;
      font-size: 0.65rem;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      padding: 1px 6px;
      border-radius: 5px;
      flex-shrink: 0;
      max-width: 120px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .gantt-track {
      position: relative;
      height: 22px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 6px;
      overflow: hidden;
    }

    .gantt-gap-band {
      position: absolute;
      top: 0;
      bottom: 0;
      background: repeating-linear-gradient(
        -45deg,
        rgba(245, 158, 11, 0.09),
        rgba(245, 158, 11, 0.09) 4px,
        transparent 4px,
        transparent 8px
      );
      border-left: 1px dashed rgba(245, 158, 11, 0.35);
      border-right: 1px dashed rgba(245, 158, 11, 0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Fira Code', monospace;
      font-size: 0.6rem;
      color: #fbbf24;
      pointer-events: none;
    }

    .gantt-bar {
      position: absolute;
      top: 3px;
      bottom: 3px;
      border-radius: 4px;
      min-width: 3px;
      opacity: 0.92;
      transition: filter 0.15s ease;
    }
    .gantt-bar:hover { filter: brightness(1.25); }
    .bar-t1 { background: linear-gradient(90deg, #7c3aed, #a855f7); }
    .bar-t2-coder { background: linear-gradient(90deg, #0284c7, #38bdf8); }
    .bar-t2-investigator { background: linear-gradient(90deg, #0d9488, #2dd4bf); }
    .bar-t3-l0 { background: linear-gradient(90deg, #db2777, #f472b6); }
    .bar-t3-improvement { background: linear-gradient(90deg, #d97706, #10b981); }

    .gantt-timing {
      text-align: right;
      font-family: 'Fira Code', monospace;
      font-size: 0.71rem;
      color: var(--text-muted);
      white-space: nowrap;
    }
    .gantt-timing strong { color: var(--text-main); }

    /* 3-Tier Hierarchy Layout */
    .hierarchy-tree {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .tier2-branch {
      margin-left: 26px;
      padding-left: 20px;
      border-left: 2px solid rgba(56, 189, 248, 0.32);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .tier3-list {
      margin-left: 24px;
      padding-left: 18px;
      border-left: 2px dashed rgba(244, 114, 182, 0.32);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .tier3-parallel-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 14px;
    }

    .agent-box {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 15px;
      padding: 18px 20px;
      backdrop-filter: blur(12px);
      transition: all 0.22s ease;
      cursor: pointer;
    }
    .agent-box:hover {
      border-color: var(--border-glowing);
      box-shadow: 0 8px 24px rgba(124, 58, 237, 0.12);
    }
    .agent-box.highlighted {
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.38);
    }

    .agent-meta {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .agent-identity { display: flex; align-items: center; gap: 11px; }

    .agent-avatar {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.92rem;
      font-weight: 800;
      flex-shrink: 0;
    }
    .av-t1 { background: rgba(124, 58, 237, 0.2); color: #c4b5fd; border: 1px solid rgba(124, 58, 237, 0.4); }
    .av-t2-coder { background: rgba(2, 132, 199, 0.2); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.4); }
    .av-t2-investigator { background: rgba(13, 148, 136, 0.2); color: #2dd4bf; border: 1px solid rgba(13, 148, 136, 0.4); }
    .av-t3-l0 { background: rgba(219, 39, 119, 0.2); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.4); }
    .av-t3-imp { background: rgba(16, 185, 129, 0.2); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.4); }

    .agent-name { font-family: 'Outfit', sans-serif; font-size: 1.08rem; font-weight: 700; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .agent-role-badge {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-family: 'Fira Code', monospace;
    }

    .badge-cluster { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

    .badge-clock {
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 9px;
      border-radius: 8px;
      background: rgba(16, 185, 129, 0.12);
      color: #6ee7b7;
      border: 1px solid rgba(16, 185, 129, 0.28);
    }

    .status-badge {
      font-size: 0.67rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 8px;
    }
    .st-completed, .st-idle, .st-done { background: rgba(16, 185, 129, 0.14); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
    .st-running { background: rgba(245, 158, 11, 0.16); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.35); }
    .st-killed, .st-empty, .st-error { background: rgba(239, 68, 68, 0.16); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.35); }

    .execution-badge {
      font-size: 0.67rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 8px;
    }
    .badge-serial { background: rgba(2, 132, 199, 0.14); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.3); }
    .badge-parallel { background: rgba(219, 39, 119, 0.15); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.3); }

    .telemetry-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
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

    .handoff-summary { font-size: 0.89rem; color: #cbd5e1; margin-bottom: 10px; }

    /* Structured send_message Report Cards */
    .report-cards {
      margin-top: 10px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .report-card {
      background: rgba(10, 15, 29, 0.72);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 12px;
      padding: 13px 15px;
      cursor: default;
    }

    .report-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }

    .report-card-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.9rem;
      font-weight: 700;
      color: #7dd3fc;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .flag-pill {
      font-family: 'Fira Code', monospace;
      font-size: 0.66rem;
      font-weight: 700;
      padding: 2px 7px;
      border-radius: 6px;
    }
    .flag-fatal { background: rgba(239, 68, 68, 0.18); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4); }
    .flag-shallow { background: rgba(245, 158, 11, 0.18); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.4); }
    .flag-minor { background: rgba(56, 189, 248, 0.16); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.35); }

    .disclaimer-box {
      background: rgba(245, 158, 11, 0.10);
      border-left: 3px solid var(--glow-amber);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.83rem;
      color: #fde68a;
      margin-bottom: 10px;
    }
    .disclaimer-box strong { color: #fbbf24; }

    .report-sections {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .report-sec {
      border: 1px solid var(--border-color);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.02);
      overflow: hidden;
    }

    .report-sec summary {
      padding: 7px 11px;
      font-size: 0.81rem;
      font-weight: 600;
      color: var(--text-main);
      cursor: pointer;
      list-style: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .report-sec summary:hover { background: rgba(255, 255, 255, 0.04); }
    .report-sec[open] summary { border-bottom: 1px solid var(--border-color); color: #c4b5fd; }

    .report-sec-body {
      padding: 9px 12px;
      font-size: 0.8rem;
      color: #cbd5e1;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: 'Inter', sans-serif;
      max-height: 280px;
      overflow-y: auto;
    }

    .incomplete-notice {
      margin-top: 8px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(239, 68, 68, 0.10);
      border: 1px dashed rgba(239, 68, 68, 0.35);
      font-size: 0.8rem;
      color: #fca5a5;
    }

    /* Expandable Technical Details */
    .box-expand-details {
      display: none;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--border-color);
    }
    .box-expand-details.active { display: block; }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }

    .detail-label {
      font-size: 0.71rem;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }

    .detail-value { font-size: 0.85rem; }

    .turns-table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'Fira Code', monospace;
      font-size: 0.73rem;
      margin-bottom: 14px;
    }
    .turns-table th, .turns-table td {
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid var(--border-color);
    }
    .turns-table th { color: var(--text-muted); font-weight: 600; }

    .id-tag {
      font-family: 'Fira Code', monospace;
      font-size: 0.77rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      padding: 4px 10px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
    }
    .id-tag:hover { background: rgba(255, 255, 255, 0.1); }

    .doc-link-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      padding: 4px 10px;
      border-radius: 8px;
      font-family: 'Fira Code', monospace;
      font-size: 0.75rem;
      text-decoration: none;
      color: #38bdf8;
    }
    .doc-link-item:hover { background: rgba(56, 189, 248, 0.12); border-color: #38bdf8; }

    .copied-toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: var(--gradient-primary);
      padding: 10px 20px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.88rem;
      box-shadow: 0 10px 25px rgba(124, 58, 237, 0.4);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s ease;
      z-index: 1000;
    }
    .copied-toast.show { transform: translateY(0); opacity: 1; }

    @media (max-width: 920px) {
      .gantt-axis, .gantt-row { grid-template-columns: 210px 1fr 115px; }
    }
    @media (max-width: 720px) {
      h1 { font-size: 1.65rem; }
      .gantt-axis, .gantt-row { grid-template-columns: 1fr; }
      .tier2-branch, .tier3-list { margin-left: 10px; padding-left: 12px; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div class="badge-row">
        <div class="badge-boost">AGY /boost Telemetry</div>
        <div class="badge-routine" id="routineBadge"></div>
        <div class="badge-meta" id="scopeBadge"></div>
        <div class="badge-meta" id="tzBadge"></div>
        <div class="badge-meta" id="rootIdBadge" title="Click to copy root conversation ID"></div>
      </div>
      <h1 id="runTitle">/boost Execution Trajectory</h1>
      <p class="subtitle" id="runSubtitle"></p>

      <div class="controls">
        <div class="search-container">
          <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search agent, tier, model, report, or file..." oninput="applyFilters()">
        </div>
        <button class="filter-btn active" onclick="setTierFilter('all', this)">All Tiers</button>
        <button class="filter-btn" onclick="setTierFilter('1', this)">Tier 1 · Orchestrator</button>
        <button class="filter-btn" onclick="setTierFilter('2', this)">Tier 2 · Delegates</button>
        <button class="filter-btn" onclick="setTierFilter('3', this)">Tier 3 · Workers</button>
        <button class="filter-btn" onclick="setTierFilter('reports', this)">Report Cards Only</button>
      </div>
    </div>
  </header>

  <div class="container">
    <section class="summary-grid" id="summaryGrid"></section>
    <div id="pipelinesRoot"></div>
  </div>

  <div class="copied-toast" id="copiedToast">Copied to clipboard!</div>

  <script>
    const telemetry = __TELEMETRY_DATA_PLACEHOLDER__;
    const pipelines = telemetry.pipelines || [];
    const ganttModes = {};
    pipelines.forEach(p => {
      ganttModes[p.invocation_index] = (p.gantt && p.gantt.has_compressed_gaps) ? 'compressed' : 'true';
    });
    let activeTierFilter = 'all';

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

    function renderHeader() {
      const s = telemetry.summary || {};
      const rBadge = document.getElementById('routineBadge');
      const sr = telemetry.session_routine || 'solo';
      rBadge.textContent = sr.toUpperCase() + ' ROUTINE';
      rBadge.className = 'badge-routine routine-' + (sr === 'delegation' ? 'delegation' : (sr === 'mixed' ? 'mixed' : 'solo'));

      const scopeBadge = document.getElementById('scopeBadge');
      if (telemetry.scope_mode === 'all') {
        scopeBadge.textContent = `All ${telemetry.total_boost_invocations} /boost Invocations`;
      } else {
        const idx = (telemetry.selected_invocation_indices || [1])[0];
        scopeBadge.textContent = telemetry.total_boost_invocations > 1
          ? `Latest /boost (#${idx} of ${telemetry.total_boost_invocations})`
          : `Single /boost Run`;
      }

      document.getElementById('tzBadge').textContent = telemetry.tz_label || 'LOCAL';
      const rootBadge = document.getElementById('rootIdBadge');
      const cid = telemetry.root_conversation_id || 'unknown';
      rootBadge.textContent = 'Run: ' + cid.slice(0, 8);
      rootBadge.onclick = (e) => copyId(cid, e);

      document.getElementById('runTitle').textContent = telemetry.run_title || '/boost Execution Trajectory';
      document.getElementById('runSubtitle').textContent =
        `${telemetry.workspace_root || ''} • Wall-clock ${s.wall_start_local || '—'} → ${s.wall_end_local || '—'}`;
    }

    function renderSummary() {
      const s = telemetry.summary || {};
      const tok = s.tokens || {};
      const models = (s.models_used || []).join(', ') || 'default';
      const cards = [
        {
          label: '3-Tier Hierarchy',
          value: `${s.total_agents || 0} agents`,
          sub: `T1:${s.tier1_count || 0} · T2:${s.tier2_count || 0} · T3:${s.tier3_count || 0} · Reports:${s.report_count || 0}`
        },
        {
          label: 'Wall-Clock Span',
          value: s.wall_span_label || '—',
          sub: `${s.wall_start_local || '—'} → ${s.wall_end_local || '—'}`
        },
        {
          label: 'Active Wall-Clock',
          value: s.active_wall_label || '—',
          sub: `Subagents active: ${s.subagent_active_wall_label || '—'}`
        },
        {
          label: 'Cumulative Subagent Time',
          value: s.subagent_cumulative_label || '—',
          sub: `Worker sum: ${s.worker_cumulative_label || '—'}`
        },
        {
          label: 'Worker Concurrency',
          value: `${s.peak_concurrency ?? 0} peak`,
          sub: `Worker speedup: ${s.parallelism_speedup ?? 1}x · Parallel: ${s.parallel_agents ?? 0}`
        },
        {
          label: 'Models, Steps & Tokens',
          value: `${s.total_steps || 0} steps`,
          sub: `${models} · ${s.total_tool_calls || 0} tools · ${formatTokens(tok.total)} tok`
        }
      ];

      document.getElementById('summaryGrid').innerHTML = cards.map(c => `
        <div class="kpi-card">
          <div class="kpi-label">${escapeHtml(c.label)}</div>
          <div class="kpi-value">${escapeHtml(c.value)}</div>
          <div class="kpi-sub">${escapeHtml(c.sub)}</div>
        </div>
      `).join('');
    }

    function ganttBarClass(agent) {
      if (agent.tier === 1) return 'bar-t1';
      if (agent.tier === 2) {
        return agent.boost_family === 'investigator' ? 'bar-t2-investigator' : 'bar-t2-coder';
      }
      return agent.worker_stage === 'improvement' ? 'bar-t3-improvement' : 'bar-t3-l0';
    }

    function matchesFilter(agent, query) {
      if (activeTierFilter === '1' && agent.tier !== 1) return false;
      if (activeTierFilter === '2' && agent.tier !== 2) return false;
      if (activeTierFilter === '3' && agent.tier !== 3) return false;
      if (activeTierFilter === 'reports' && !agent.has_report) return false;
      if (!query) return true;
      const reportsText = (agent.reports || []).map(r =>
        (r.skepticism_disclaimer || '') + ' ' + (r.sections || []).map(s => s.title + ' ' + s.body).join(' ')
      ).join(' ');
      const docsText = (agent.docs || []).map(d => d.name).join(' ');
      const hay = [
        agent.name, agent.tier_label, agent.role, agent.model, agent.requested_model,
        agent.conv_id, agent.status, agent.summary, agent.task, docsText, reportsText
      ].join(' ').toLowerCase();
      return hay.includes(query);
    }

    function renderGanttForPipeline(pipeline) {
      const idx = pipeline.invocation_index;
      const g = pipeline.gantt || {};
      if (!g.has_timing) {
        return '<div class="gantt-panel"><div class="gantt-title">Wall-Clock Execution Waterfall</div><p class="kpi-sub">No timestamped turns available for this invocation.</p></div>';
      }

      const mode = ganttModes[idx] || 'true';
      const showCompressed = mode === 'compressed' && g.has_compressed_gaps;
      const gapOverlay = showCompressed
        ? (g.gaps || []).map(gap => `
            <div class="gantt-gap-band" style="left:${gap.left_pct}%;width:${gap.width_pct}%;" title="Idle / Human pause: ${escapeHtml(gap.pause_label)}">
              ⏸ ${escapeHtml(gap.pause_label)}
            </div>
          `).join('')
        : '';

      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const rowsHtml = (pipeline.agents || []).map(agent => {
        if (!matchesFilter(agent, query)) return '';
        const indent = Math.max(0, (agent.tier - 1)) * 16;
        const prefix = agent.tier > 1 ? '↳ ' : '';
        const barsHtml = (agent.turns || []).map(turn => {
          const left = showCompressed ? turn.gantt_comp_left_pct : turn.gantt_true_left_pct;
          const width = showCompressed ? turn.gantt_comp_width_pct : turn.gantt_true_width_pct;
          const tip = `${agent.name} (${agent.tier_label}) • ${turn.label}\\nModel: ${agent.model}\\nLocal: ${turn.start_local_full} → ${turn.end_local_full}\\nDuration: ${turn.duration_label} • Steps: ${turn.steps} • Tools: ${turn.tool_calls}`;
          return `<div class="gantt-bar ${ganttBarClass(agent)}" style="left:${left}%;width:${width}%;" title="${escapeHtml(tip)}"></div>`;
        }).join('');

        return `
          <div class="gantt-row" data-card-id="${escapeHtml(idx + '-' + agent.conv_id)}" onclick="jumpToAgent(this.dataset.cardId)">
            <div class="gantt-label" style="padding-left:${indent}px;" title="${escapeHtml(agent.name)} (${escapeHtml(agent.model)})">
              <span class="tier-chip tier-${escapeHtml(agent.tier)}">T${escapeHtml(agent.tier)}</span>
              <span class="gantt-label-text">${escapeHtml(prefix + agent.name)}</span>
              <span class="gantt-model-chip">${escapeHtml(agent.model || 'inherit')}</span>
            </div>
            <div class="gantt-track">
              ${gapOverlay}
              ${barsHtml}
            </div>
            <div class="gantt-timing" title="Wall span: ${escapeHtml(agent.wall_span_label)} | ${escapeHtml(agent.wall_start_local_full)} → ${escapeHtml(agent.wall_end_local_full)}">
              <strong>${escapeHtml(agent.active_duration_label)}</strong> · ${escapeHtml(agent.wall_start_local)}
            </div>
          </div>
        `;
      }).join('');

      const gapBtn = g.has_compressed_gaps
        ? `<button class="mode-pill ${showCompressed ? 'active' : ''}" onclick="setGanttMode(${idx}, 'compressed')">Compressed Pauses</button>`
        : '';

      return `
        <div class="gantt-panel" id="gantt-${idx}">
          <div class="gantt-header">
            <div class="gantt-title">Wall-Clock Execution Waterfall</div>
            <div class="gantt-controls">
              ${gapBtn}
              <button class="mode-pill ${!showCompressed ? 'active' : ''}" onclick="setGanttMode(${idx}, 'true')">True Wall-Clock</button>
            </div>
          </div>
          <div class="gantt-axis">
            <div>3-Tier Hierarchy &amp; Model</div>
            <div class="gantt-axis-track">
              <span>${escapeHtml(g.start_local || '')}</span>
              <span>${escapeHtml(showCompressed ? 'Active clusters (human pauses compressed)' : 'Linear wall-clock (' + (g.true_span_label || '') + ')')}</span>
              <span>${escapeHtml(g.end_local || '')}</span>
            </div>
            <div style="text-align:right;">Active · Start</div>
          </div>
          <div class="gantt-rows">${rowsHtml || '<div class="kpi-sub">No agents match the active filter.</div>'}</div>
        </div>
      `;
    }

    function setGanttMode(pipelineIdx, mode) {
      ganttModes[pipelineIdx] = mode;
      renderPipelines();
    }

    function avatarClass(agent) {
      if (agent.tier === 1) return 'av-t1';
      if (agent.tier === 2) return agent.boost_family === 'investigator' ? 'av-t2-investigator' : 'av-t2-coder';
      return agent.worker_stage === 'improvement' ? 'av-t3-imp' : 'av-t3-l0';
    }

    function initialsFor(agent) {
      if (agent.tier === 1) return 'T1';
      if (agent.tier === 2) return agent.boost_family === 'investigator' ? 'DI' : 'DC';
      if (agent.worker_stage === 'improvement') return 'IW';
      if (agent.worker_stage === 'l0') return 'L0';
      return 'T3';
    }

    function flagBadgeHtml(flag) {
      if (flag === 'Fatal Functional Bug') return `<span class="flag-pill flag-fatal">${escapeHtml(flag)}</span>`;
      if (flag === 'Shallow Verification') return `<span class="flag-pill flag-shallow">${escapeHtml(flag)}</span>`;
      return `<span class="flag-pill flag-minor">${escapeHtml(flag)}</span>`;
    }

    function renderReportCardsHtml(agent) {
      const reports = agent.reports || [];
      if (reports.length === 0) {
        if (agent.incomplete_report) {
          return `<div class="incomplete-notice">No structured <code>send_message</code> report recorded (status: ${escapeHtml(agent.status)}).</div>`;
        }
        return '';
      }

      return `<div class="report-cards" onclick="event.stopPropagation()">
        ${reports.map((rep, rIdx) => {
          const flagsHtml = (rep.issue_flags || []).map(flagBadgeHtml).join('');
          const disclaimerHtml = rep.skepticism_disclaimer
            ? `<div class="disclaimer-box"><strong>Skepticism Disclaimer:</strong> ${escapeHtml(rep.skepticism_disclaimer)}</div>`
            : '';
          const sectionsHtml = (rep.sections || []).map((sec, sIdx) => `
            <details class="report-sec" ${sIdx === 0 && rIdx === reports.length - 1 ? 'open' : ''}>
              <summary>
                <span>${escapeHtml(sec.title)}</span>
                <span style="font-family:'Fira Code',monospace;font-size:0.68rem;color:var(--text-dim);">toggle</span>
              </summary>
              <div class="report-sec-body">${escapeHtml(sec.body || '(empty section)')}</div>
            </details>
          `).join('');

          return `
            <div class="report-card">
              <div class="report-card-header">
                <div class="report-card-title">
                  <span>send_message → ${escapeHtml(rep.recipient_name)}</span>
                  <span class="telemetry-pill">${escapeHtml(rep.kind)}</span>
                  ${flagsHtml}
                </div>
                <span class="telemetry-pill">${escapeHtml(rep.timestamp_local || '')} · ${escapeHtml(rep.char_count || 0)} chars</span>
              </div>
              ${disclaimerHtml}
              <div class="report-sections">${sectionsHtml}</div>
            </div>
          `;
        }).join('')}
      </div>`;
    }

    function createAgentCardHtml(pipelineIdx, agent) {
      const safeConvId = escapeHtml(agent.conv_id || 'unknown');
      const cardId = escapeHtml(pipelineIdx + '-' + agent.conv_id);
      const tok = agent.tokens || {};
      const stClass = 'st-' + escapeHtml(agent.status || 'completed');
      const modeClass = agent.mode === 'parallel' ? 'badge-parallel' : 'badge-serial';

      const docsHtml = (agent.docs || []).map(doc =>
        `<a class="doc-link-item" href="${escapeHtml(doc.path)}" onclick="event.stopPropagation()">${escapeHtml(doc.name)}</a>`
      ).join('');

      const turnsHtml = (agent.turns || []).length > 0
        ? `
          <div style="margin-bottom:14px;">
            <div class="detail-label">Turn / Round Wall-Clock Breakdown (${agent.turns.length})</div>
            <table class="turns-table">
              <thead><tr><th>Round</th><th>Start (Local)</th><th>End (Local)</th><th>Duration</th><th>Steps</th><th>Tools</th></tr></thead>
              <tbody>
                ${agent.turns.map(t => `
                  <tr>
                    <td>${escapeHtml(t.label)}</td>
                    <td title="${escapeHtml(t.start_iso)}">${escapeHtml(t.start_local_full)}</td>
                    <td title="${escapeHtml(t.end_iso)}">${escapeHtml(t.end_local_full)}</td>
                    <td><strong>${escapeHtml(t.duration_label)}</strong></td>
                    <td>${escapeHtml(t.steps)}</td>
                    <td>${escapeHtml(t.tool_calls)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `
        : '';

      const toolsHtml = (agent.tool_breakdown || []).map(t =>
        `<span class="telemetry-pill">${escapeHtml(t.name)}: ${escapeHtml(t.count)}</span>`
      ).join('');

      const transcriptName = agent.transcript_uri ? agent.transcript_uri.split('/').pop() : 'transcript.jsonl';
      const transcriptLink = agent.transcript_uri
        ? `<a class="doc-link-item" href="${escapeHtml(agent.transcript_uri)}" onclick="event.stopPropagation()">Open ${escapeHtml(transcriptName)}</a>`
        : '';

      const modelMeta = agent.model_source === 'inherited' || agent.model_source === 'user_settings'
        ? `${agent.model} (${agent.model_source})`
        : agent.model;

      return `
        <div class="agent-box" id="agent-${cardId}" onclick="toggleDetails(this)">
          <div class="agent-meta">
            <div class="agent-identity">
              <div class="agent-avatar ${avatarClass(agent)}">${initialsFor(agent)}</div>
              <div>
                <div class="agent-name">
                  <span>${escapeHtml(agent.name)}</span>
                  <span class="tier-chip tier-${escapeHtml(agent.tier)}">${escapeHtml(agent.tier_label)}</span>
                </div>
                <div class="agent-role-badge">${escapeHtml(agent.role || agent.type)} · model: ${escapeHtml(modelMeta || 'default')}</div>
              </div>
            </div>
            <div class="badge-cluster">
              <span class="badge-clock" title="Wall span: ${escapeHtml(agent.wall_span_label)} (${escapeHtml(agent.wall_start_iso)} → ${escapeHtml(agent.wall_end_iso)})">
                ${escapeHtml(agent.wall_start_local)}–${escapeHtml(agent.wall_end_local)} · ${escapeHtml(agent.active_duration_label)}
              </span>
              <span class="status-badge ${stClass}">${escapeHtml(agent.status)}</span>
              <span class="execution-badge ${modeClass}">${escapeHtml(agent.mode)}</span>
            </div>
          </div>
          <div class="telemetry-strip">
            ${agent.parent_name ? `<span class="telemetry-pill">Parent: ${escapeHtml(agent.parent_name)}</span>` : ''}
            <span class="telemetry-pill">Steps: ${escapeHtml(agent.step_count)}</span>
            <span class="telemetry-pill">Tools: ${escapeHtml(agent.tool_call_count)}</span>
            <span class="telemetry-pill">Tokens: ${escapeHtml(formatTokens(tok.total))} (${escapeHtml(formatTokens(tok.output))} out)</span>
            <span class="telemetry-pill">Rounds: ${escapeHtml((agent.turns || []).length)}</span>
            <span class="telemetry-pill">Files: ${escapeHtml((agent.docs || []).length)}</span>
          </div>
          <div class="handoff-summary">${escapeHtml(agent.summary)}</div>
          ${renderReportCardsHtml(agent)}
          <div class="box-expand-details">
            <div class="detail-grid">
              <div>
                <div class="detail-label">Conversation ID &amp; Transcript</div>
                <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
                  <div class="id-tag" data-conv-id="${safeConvId}" onclick="copyId(this.dataset.convId, event)">ID: ${safeConvId}</div>
                  ${transcriptLink}
                </div>
              </div>
              <div>
                <div class="detail-label">Initial Prompt / Task</div>
                <div class="detail-value" style="color: var(--text-muted);">${escapeHtml(agent.task)}</div>
              </div>
            </div>
            ${turnsHtml}
            ${toolsHtml ? `<div style="margin-bottom:14px;"><div class="detail-label">Tool Calls</div><div class="telemetry-strip">${toolsHtml}</div></div>` : ''}
            <div>
              <div class="detail-label">Produced / Modified Files</div>
              <div style="display:flex;flex-wrap:wrap;gap:8px;">
                ${docsHtml || '<span style="font-size:0.8rem;color:var(--text-muted);">None recorded</span>'}
              </div>
            </div>
          </div>
        </div>
      `;
    }

    function renderHierarchyForPipeline(pipeline) {
      const idx = pipeline.invocation_index;
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const agents = pipeline.agents || [];
      const visibleSet = new Set(agents.filter(a => matchesFilter(a, query)).map(a => a.conv_id));

      const t1 = agents.filter(a => a.tier === 1);
      const t2 = agents.filter(a => a.tier === 2);
      const t3ByParent = {};
      agents.filter(a => a.tier >= 3).forEach(w => {
        const pid = w.parent_id || '';
        if (!t3ByParent[pid]) t3ByParent[pid] = [];
        t3ByParent[pid].push(w);
      });

      const parts = [];
      t1.forEach(rootAgent => {
        if (visibleSet.has(rootAgent.conv_id)) {
          parts.push(createAgentCardHtml(idx, rootAgent));
        }
      });

      if (t2.length > 0) {
        const branchParts = [];
        t2.forEach(delegate => {
          const children = t3ByParent[delegate.conv_id] || [];
          const visChildren = children.filter(c => visibleSet.has(c.conv_id));
          const showDelegate = visibleSet.has(delegate.conv_id);
          if (!showDelegate && visChildren.length === 0) return;

          let childrenHtml = '';
          if (visChildren.length > 0) {
            const anyParallel = visChildren.some(c => c.mode === 'parallel');
            childrenHtml = `<div class="tier3-list ${anyParallel ? 'tier3-parallel-grid' : ''}">
              ${visChildren.map(c => createAgentCardHtml(idx, c)).join('')}
            </div>`;
          }
          branchParts.push(`
            <div class="tier2-branch">
              ${showDelegate ? createAgentCardHtml(idx, delegate) : ''}
              ${childrenHtml}
            </div>
          `);
        });
        if (branchParts.length > 0) {
          parts.push(branchParts.join(''));
        }
      } else {
        // Fallback if any orphan Tier-3 exists without Tier-2
        const orphans = agents.filter(a => a.tier >= 3 && visibleSet.has(a.conv_id));
        if (orphans.length > 0) {
          parts.push(`<div class="tier3-list">${orphans.map(c => createAgentCardHtml(idx, c)).join('')}</div>`);
        }
      }

      if (parts.length === 0) {
        return '<div class="kpi-sub">No agents match the active filter in this invocation.</div>';
      }
      return `<div class="hierarchy-tree">${parts.join('')}</div>`;
    }

    function renderPipelines() {
      const root = document.getElementById('pipelinesRoot');
      root.innerHTML = pipelines.map(pipeline => {
        const ps = pipeline.summary || {};
        const rClass = pipeline.routine === 'delegation' ? 'routine-delegation' : 'routine-solo';
        const delegatesText = (pipeline.delegates || []).length > 0
          ? pipeline.delegates.join(' → ')
          : 'Direct Orchestrator execution';

        return `
          <section class="pipeline-section" id="pipeline-${pipeline.invocation_index}">
            <div class="pipeline-banner">
              <div>
                <div class="pipeline-title">
                  <span>/boost Pipeline #${escapeHtml(pipeline.invocation_index)} of ${escapeHtml(pipeline.total_invocations)}</span>
                  <span class="badge-routine ${rClass}">${escapeHtml(pipeline.routine.toUpperCase())}</span>
                  <span class="telemetry-pill">${escapeHtml(delegatesText)}</span>
                </div>
                <div class="pipeline-prompt">${escapeHtml(pipeline.prompt_preview)}</div>
              </div>
              <div class="pipeline-stats-pills">
                <span class="badge-clock">${escapeHtml(ps.wall_start_local || '—')} → ${escapeHtml(ps.wall_end_local || '—')}</span>
                <span class="telemetry-pill">Span: ${escapeHtml(ps.wall_span_label || '—')}</span>
                <span class="telemetry-pill">Active: ${escapeHtml(ps.active_wall_label || '—')}</span>
                <span class="telemetry-pill">Peak Conc: ${escapeHtml(ps.peak_concurrency ?? 0)}</span>
                <span class="telemetry-pill">Agents: ${escapeHtml(ps.total_agents || 0)}</span>
              </div>
            </div>
            ${renderGanttForPipeline(pipeline)}
            ${renderHierarchyForPipeline(pipeline)}
          </section>
        `;
      }).join('');
    }

    function toggleDetails(element) {
      const details = element.querySelector('.box-expand-details');
      if (details) details.classList.toggle('active');
    }

    function jumpToAgent(cardId) {
      const el = document.getElementById('agent-' + cardId);
      if (!el) return;
      const details = el.querySelector('.box-expand-details');
      if (details && !details.classList.contains('active')) details.classList.add('active');
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

    function setTierFilter(tier, btn) {
      activeTierFilter = tier;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderPipelines();
    }

    function applyFilters() {
      renderPipelines();
    }

    renderHeader();
    renderSummary();
    renderPipelines();
  </script>
</body>
</html>"""


def render_html(telemetry: Dict[str, Any]) -> str:
    """Inject telemetry JSON safely into HTML_TEMPLATE."""
    payload = json.dumps(telemetry, indent=2).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TELEMETRY_DATA_PLACEHOLDER__", payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an interactive AGY /boost 3-tier trajectory dashboard."
    )
    parser.add_argument(
        "-c",
        "--conversation-id",
        help="Root AGY conversation ID (or unique prefix) to render.",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List matching /boost AGY conversations for the workspace and exit.",
    )
    parser.add_argument(
        "--all-invocations",
        "--full-session",
        dest="all_invocations",
        action="store_true",
        help="Render all /boost invocations in the conversation as grouped pipelines (default: latest only).",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output HTML path (default: <workspace>/.agents/boost-trajectory.html).",
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
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    workspace_root = os.path.abspath(args.workspace) if args.workspace else resolve_workspace_root()
    agy_dir = resolve_agy_dir(args.agy_dir)

    if args.list:
        runs = list_boost_runs(agy_dir, workspace_root)
        if not runs:
            print(f"No /boost AGY conversations found matching workspace: {workspace_root}")
            return 0
        print(f"/boost AGY runs for {workspace_root} (data dir: {agy_dir}):")
        for r in runs:
            print(
                f"  {r['conversation_id']}  routine={r['routine']:<10} "
                f"invocations={r['boost_invocation_count']:<2} subagents={r['subagent_count']:<3} "
                f"steps={r['step_count']:<5} updated={r['last_modified_time'][:19]}  {r['title']}"
            )
        return 0

    selected_id = select_boost_run(agy_dir, workspace_root, args.conversation_id)
    if not selected_id:
        if args.conversation_id:
            sys.stderr.write(f"Error: conversation '{args.conversation_id}' not found under {agy_dir}\n")
        else:
            sys.stderr.write(
                f"Error: no /boost AGY runs found for workspace '{workspace_root}' in '{agy_dir}'.\n"
            )
        return 1

    try:
        telemetry = parse_boost_run(
            agy_dir=agy_dir,
            root_id=selected_id,
            workspace_root=workspace_root,
            all_invocations=args.all_invocations,
        )
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    default_out = os.path.join(workspace_root, ".agents", "boost-trajectory.html")
    output_path = os.path.abspath(args.output or default_out)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    html = render_html(telemetry)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    s = telemetry["summary"]
    print(
        f"/boost trajectory generated ({telemetry['scope_mode']}): {output_path}\n"
        f"  Run: {telemetry['run_title']} ({telemetry['root_conversation_id']})\n"
        f"  Routine: {telemetry['session_routine']} | Pipelines: {len(telemetry['pipelines'])} of {telemetry['total_boost_invocations']}\n"
        f"  Wall-clock: {s['wall_start_local']} -> {s['wall_end_local']} "
        f"(span {s['wall_span_label']}, active {s['active_wall_label']}, "
        f"peak concurrency {s['peak_concurrency']}, speedup {s['parallelism_speedup']}x)\n"
        f"  Agents: {s['total_agents']} (T1:{s['tier1_count']} T2:{s['tier2_count']} T3:{s['tier3_count']}), "
        f"reports: {s['report_count']}, steps: {s['total_steps']}, tools: {s['total_tool_calls']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
