#!/usr/bin/env python3
"""Generate an interactive dark-mode HTML trajectory dashboard for AGY swarm runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from telemetry import (  # noqa: E402
    list_agy_runs,
    parse_agy_run,
    parse_legacy_agents_dir,
    resolve_agy_dir,
    resolve_workspace_root,
    select_agy_run,
)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Teamwork Swarm - Trajectory Trace</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0f1d;
      --panel-dark: rgba(16, 22, 38, 0.78);
      --panel-elevated: rgba(22, 30, 50, 0.88);
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

      --gradient-primary: linear-gradient(135deg, #7c3aed, #0284c7);
      --gradient-parallel: linear-gradient(135deg, #db2777, #7c3aed);
      --gradient-serial: linear-gradient(135deg, #0284c7, #0d9488);
      --gradient-verification: linear-gradient(135deg, #0d9488, #10b981);
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
      padding: 28px 20px 22px;
      text-align: center;
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(14px);
      background-color: rgba(10, 15, 29, 0.72);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-content { max-width: 1280px; margin: 0 auto; }

    .badge-row {
      display: flex;
      justify-content: center;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 10px;
    }

    .badge-swarm {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(124, 58, 237, 0.16);
      border: 1px solid rgba(124, 58, 237, 0.35);
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.9px;
      color: #c4b5fd;
    }

    .badge-meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 11px;
      border-radius: 20px;
      font-family: 'Fira Code', monospace;
      font-size: 0.76rem;
      color: var(--text-muted);
      cursor: pointer;
    }
    .badge-meta:hover { border-color: var(--border-glowing); color: var(--text-main); }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.2rem;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 30%, #c084fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 6px;
      letter-spacing: -0.6px;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 0.95rem;
      max-width: 860px;
      margin: 0 auto 18px;
      font-weight: 400;
    }

    .controls {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 8px;
      max-width: 1120px;
      margin: 0 auto;
    }

    .search-container { position: relative; flex: 1 1 260px; max-width: 340px; }

    .search-input {
      width: 100%;
      background: rgba(16, 22, 38, 0.9);
      border: 1px solid var(--border-color);
      padding: 9px 14px 9px 38px;
      border-radius: 10px;
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      font-size: 0.88rem;
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
      font-size: 0.84rem;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .filter-btn:hover, .filter-btn.active {
      color: var(--text-main);
      background: rgba(124, 58, 237, 0.18);
      border-color: var(--glow-purple);
    }

    .container { max-width: 1280px; margin: 28px auto 0; padding: 0 20px; }

    /* Summary Timing Strip */
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 14px;
      margin-bottom: 26px;
    }

    .kpi-card {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 16px 18px;
      backdrop-filter: blur(12px);
    }

    .kpi-label {
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }

    .kpi-value {
      font-family: 'Outfit', sans-serif;
      font-size: 1.55rem;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.2;
    }

    .kpi-sub {
      margin-top: 4px;
      font-family: 'Fira Code', monospace;
      font-size: 0.74rem;
      color: var(--text-muted);
    }

    /* Gantt Waterfall */
    .gantt-panel {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 32px;
      backdrop-filter: blur(12px);
    }

    .gantt-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 16px;
    }

    .gantt-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.15rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .gantt-controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

    .mode-pill {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 5px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
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
      grid-template-columns: 270px 1fr 150px;
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
      position: relative;
      height: 18px;
    }

    .gantt-rows { display: flex; flex-direction: column; gap: 6px; }

    .gantt-row {
      display: grid;
      grid-template-columns: 270px 1fr 150px;
      gap: 12px;
      align-items: center;
      padding: 5px 8px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.15s ease;
    }

    .gantt-row:hover { background: rgba(255, 255, 255, 0.04); }

    .gantt-label {
      display: flex;
      align-items: center;
      gap: 6px;
      min-width: 0;
      font-size: 0.82rem;
      font-weight: 600;
    }

    .gantt-label-text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .gantt-model-chip {
      font-family: 'Fira Code', monospace;
      font-size: 0.66rem;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      padding: 1px 5px;
      border-radius: 5px;
      flex-shrink: 0;
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
    .bar-orchestration { background: linear-gradient(90deg, #7c3aed, #a855f7); }
    .bar-discovery { background: linear-gradient(90deg, #0284c7, #38bdf8); }
    .bar-planning { background: linear-gradient(90deg, #6366f1, #818cf8); }
    .bar-construction { background: linear-gradient(90deg, #db2777, #f472b6); }
    .bar-verification { background: linear-gradient(90deg, #0d9488, #10b981); }

    .gantt-timing {
      text-align: right;
      font-family: 'Fira Code', monospace;
      font-size: 0.72rem;
      color: var(--text-muted);
      white-space: nowrap;
    }

    .gantt-timing strong { color: var(--text-main); }

    /* Timeline */
    .timeline { position: relative; margin-top: 24px; }

    .timeline::before {
      content: '';
      position: absolute;
      left: 31px;
      top: 0;
      bottom: 0;
      width: 2px;
      background: linear-gradient(180deg,
        rgba(124, 58, 237, 0.8) 0%,
        rgba(2, 132, 199, 0.8) 25%,
        rgba(13, 148, 136, 0.8) 50%,
        rgba(219, 39, 119, 0.8) 75%,
        rgba(16, 185, 129, 0.8) 100%
      );
    }

    .timeline-phase { margin-bottom: 46px; position: relative; }

    .phase-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin-left: 55px;
      margin-bottom: 22px;
    }

    .phase-title-group { display: flex; align-items: center; gap: 14px; }

    .phase-number {
      background: var(--gradient-primary);
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Outfit', sans-serif;
      font-weight: 700;
      font-size: 0.95rem;
      box-shadow: 0 0 14px rgba(124, 58, 237, 0.45);
    }

    .phase-title { font-family: 'Outfit', sans-serif; font-size: 1.45rem; font-weight: 700; }

    .phase-timing-pill {
      font-family: 'Fira Code', monospace;
      font-size: 0.76rem;
      color: var(--text-muted);
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--border-color);
      padding: 4px 11px;
      border-radius: 999px;
    }

    .timeline-item {
      position: relative;
      margin-left: 55px;
      margin-bottom: 20px;
      display: flex;
      flex-direction: column;
      transition: all 0.25s ease;
    }

    .timeline-dot {
      position: absolute;
      left: -33px;
      top: 24px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--bg-dark);
      border: 3px solid var(--glow-blue);
      z-index: 10;
      box-shadow: 0 0 8px var(--glow-blue);
    }

    .node-verifier .timeline-dot {
      border-color: var(--glow-green);
      box-shadow: 0 0 8px var(--glow-green);
    }

    .agent-box {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 20px 22px;
      backdrop-filter: blur(12px);
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      cursor: pointer;
    }

    .agent-box:hover {
      border-color: var(--border-glowing);
      transform: translateY(-2px);
      box-shadow: 0 10px 28px rgba(124, 58, 237, 0.1);
    }

    .agent-box.highlighted {
      border-color: #38bdf8;
      box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.35);
    }

    .parallel-group-container {
      background: rgba(255, 255, 255, 0.015);
      border: 1px dashed rgba(219, 39, 119, 0.28);
      padding: 18px;
      border-radius: 18px;
      margin-bottom: 22px;
      margin-left: 55px;
      position: relative;
    }

    .parallel-group-badge {
      position: absolute;
      top: -11px;
      right: 18px;
      background: var(--glow-pink);
      color: white;
      font-size: 0.66rem;
      font-weight: 800;
      padding: 2px 10px;
      border-radius: 10px;
      letter-spacing: 0.8px;
    }

    .parallel-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
      gap: 16px;
    }

    .agent-meta {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .agent-identity { display: flex; align-items: center; gap: 10px; }

    .agent-avatar {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1rem;
      font-weight: 700;
      flex-shrink: 0;
    }

    .avatar-worker { background: rgba(2, 132, 199, 0.16); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.32); }
    .avatar-critic { background: rgba(219, 39, 119, 0.16); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.32); }
    .avatar-auditor { background: rgba(13, 148, 136, 0.16); color: #2dd4bf; border: 1px solid rgba(13, 148, 136, 0.32); }
    .avatar-reviewer { background: rgba(234, 88, 12, 0.16); color: #fb923c; border: 1px solid rgba(234, 88, 12, 0.32); }
    .avatar-orchestrator { background: rgba(124, 58, 237, 0.18); color: #c4b5fd; border: 1px solid rgba(124, 58, 237, 0.35); }

    .agent-name-role { display: flex; flex-direction: column; }
    .agent-name { font-family: 'Outfit', sans-serif; font-size: 1.08rem; font-weight: 700; }
    .agent-role-badge {
      font-size: 0.72rem;
      text-transform: uppercase;
      font-weight: 600;
      color: var(--text-muted);
      letter-spacing: 0.4px;
    }

    .badge-cluster { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

    .execution-badge {
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 9px;
      border-radius: 8px;
    }

    .status-badge {
      font-size: 0.67rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 8px;
    }
    .st-completed, .st-complete, .st-idle, .st-done { background: rgba(16, 185, 129, 0.14); color: #6ee7b7; border: 1px solid rgba(16, 185, 129, 0.3); }
    .st-running { background: rgba(245, 158, 11, 0.16); color: #fcd34d; border: 1px solid rgba(245, 158, 11, 0.35); }
    .st-killed, .st-empty, .st-error, .st-unknown { background: rgba(239, 68, 68, 0.16); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.35); }

    .badge-serial { background: rgba(2, 132, 199, 0.15); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.3); }
    .badge-parallel { background: rgba(219, 39, 119, 0.15); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.3); }
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

    .telemetry-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
      font-family: 'Fira Code', monospace;
      font-size: 0.73rem;
      color: var(--text-muted);
    }

    .telemetry-pill {
      background: rgba(255, 255, 255, 0.035);
      border: 1px solid var(--border-color);
      padding: 2px 8px;
      border-radius: 6px;
    }

    .handoff-summary { font-size: 0.9rem; color: #cbd5e1; margin-bottom: 8px; }

    .box-expand-details {
      display: none;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--border-color);
      animation: fadeIn 0.2s ease;
    }

    .box-expand-details.active { display: block; }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }

    .detail-label {
      font-size: 0.72rem;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }

    .detail-value { font-size: 0.86rem; }

    .turns-table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'Fira Code', monospace;
      font-size: 0.74rem;
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
      font-size: 0.78rem;
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
      padding: 5px 10px;
      border-radius: 8px;
      font-family: 'Fira Code', monospace;
      font-size: 0.76rem;
      text-decoration: none;
      color: #38bdf8;
    }
    .doc-link-item:hover { background: rgba(56, 189, 248, 0.12); border-color: #38bdf8; }

    .copied-toast {
      position: fixed;
      bottom: 26px;
      right: 26px;
      background: var(--gradient-primary);
      padding: 10px 20px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.9rem;
      box-shadow: 0 10px 25px rgba(124, 58, 237, 0.4);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.25s ease;
      z-index: 1000;
    }

    .copied-toast.show { transform: translateY(0); opacity: 1; }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 900px) {
      .gantt-axis, .gantt-row { grid-template-columns: 180px 1fr 110px; }
    }

    @media (max-width: 720px) {
      h1 { font-size: 1.7rem; }
      .timeline::before { left: 16px; }
      .timeline-dot { left: -23px; }
      .timeline-item, .phase-header, .parallel-group-container { margin-left: 35px; }
      .gantt-axis, .gantt-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div class="header-content">
      <div class="badge-row">
        <div class="badge-swarm">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          <span id="sourceBadge">AGY Swarm Telemetry</span>
        </div>
        <div class="badge-meta" id="tzBadge"></div>
        <div class="badge-meta" id="rootIdBadge" title="Click to copy root conversation ID"></div>
      </div>
      <h1 id="runTitle">Reasoning Trajectory Trace</h1>
      <p class="subtitle" id="runSubtitle">Wall-clock execution timeline, concurrency waterfall, turn durations, and document lineage.</p>

      <div class="controls">
        <div class="search-container">
          <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search role, model, ID, or file..." oninput="filterSwarm()">
        </div>
        <button class="filter-btn active" onclick="filterPhase('all', this)">All Phases</button>
        <button class="filter-btn" onclick="filterPhase('orchestration', this)">Orchestration</button>
        <button class="filter-btn" onclick="filterPhase('discovery', this)">Discovery</button>
        <button class="filter-btn" onclick="filterPhase('planning', this)">Planning</button>
        <button class="filter-btn" onclick="filterPhase('construction', this)">Building</button>
        <button class="filter-btn" onclick="filterPhase('verification', this)">Audit &amp; Verify</button>
      </div>
    </div>
  </header>

  <div class="container">
    <section class="summary-grid" id="summaryGrid"></section>
    <section class="gantt-panel" id="ganttPanel"></section>
    <div class="timeline" id="trajectoryTimeline"></div>
  </div>

  <div class="copied-toast" id="copiedToast">Copied to clipboard!</div>

  <script>
    const telemetry = __TELEMETRY_DATA_PLACEHOLDER__;
    const agentsData = telemetry.agents || [];
    let ganttMode = (telemetry.gantt && telemetry.gantt.has_compressed_gaps) ? 'compressed' : 'true';
    let activePhaseFilter = 'all';

    const phaseConfig = {
      orchestration: { num: '0', title: 'Orchestration & Root Supervisor' },
      discovery: { num: '1', title: 'Phase 1: Discovery & Specification' },
      planning: { num: '2', title: 'Phase 2: Technical Planning & Validation' },
      construction: { num: '3', title: 'Phase 3: Codebase Implementation' },
      verification: { num: '4', title: 'Phase 4: Audit, Review & Verification' }
    };

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
      document.getElementById('sourceBadge').textContent = telemetry.source === 'agy' ? 'AGY Live Telemetry' : 'Legacy .agents/ Telemetry';
      document.getElementById('tzBadge').textContent = telemetry.tz_label || 'LOCAL';
      const rootBadge = document.getElementById('rootIdBadge');
      const cid = telemetry.root_conversation_id || 'unknown';
      rootBadge.textContent = 'Run: ' + cid.slice(0, 8);
      rootBadge.onclick = (e) => copyId(cid, e);
      document.getElementById('runTitle').textContent = telemetry.run_title || 'Reasoning Trajectory Trace';
      document.getElementById('runSubtitle').textContent =
        `${telemetry.workspace_root || ''} • Wall-clock ${s.wall_start_local || '—'} → ${s.wall_end_local || '—'}`;
    }

    function renderSummary() {
      const s = telemetry.summary || {};
      const tok = s.tokens || {};
      const models = (s.models_used || []).join(', ') || 'default';
      const cards = [
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
          sub: `Across ${s.subagent_count || 0} subagent(s)`
        },
        {
          label: 'Parallelism Speedup',
          value: `${s.parallelism_speedup || 1}x`,
          sub: `Peak concurrent: ${s.peak_concurrency || 1} • Parallel: ${s.parallel_agents || 0}`
        },
        {
          label: 'Agents & Nesting',
          value: String(s.total_agents || 0),
          sub: `Max depth: ${s.max_depth || 0} • Direct+nested`
        },
        {
          label: 'Models, Steps & Tokens',
          value: `${s.total_steps || 0} steps`,
          sub: `${models} • ${s.total_tool_calls || 0} tools • ${formatTokens(tok.total)} tok (${formatTokens(tok.output)} out)`
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

    const agentsByKey = {};
    agentsData.forEach((a, idx) => {
      const base = a.id || a.conv_id || ('agent-' + idx);
      const key = Object.prototype.hasOwnProperty.call(agentsByKey, base) ? (base + '-' + idx) : base;
      a._domKey = key;
      agentsByKey[key] = a;
    });

    function agentMatchesFilter(agent, query) {
      if (activePhaseFilter !== 'all' && agent.phase !== activePhaseFilter) return false;
      if (!query) return true;
      const docsText = (agent.docs || []).map(d => d.name).join(' ');
      const hay = [
        agent.name, agent.type, agent.role, agent.model, agent.requested_model,
        agent.conv_id, agent.status, agent.summary, agent.task, agent.parent_name, docsText
      ].join(' ').toLowerCase();
      return hay.includes(query);
    }

    function renderGantt() {
      const panel = document.getElementById('ganttPanel');
      const g = telemetry.gantt || {};
      if (!g.has_timing) {
        panel.innerHTML = '<div class="gantt-title">Wall-Clock Gantt Waterfall</div><p class="kpi-sub">No timestamped turns available for this run.</p>';
        return;
      }

      const showCompressed = ganttMode === 'compressed' && g.has_compressed_gaps;
      const gapOverlay = showCompressed
        ? (g.gaps || []).map(gap => `
            <div class="gantt-gap-band" style="left:${gap.left_pct}%;width:${gap.width_pct}%;" title="Idle / Human pause: ${escapeHtml(gap.pause_label)}">
              ⏸ ${escapeHtml(gap.pause_label)}
            </div>
          `).join('')
        : '';

      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const rowsHtml = agentsData.map(agent => {
        if (!agentMatchesFilter(agent, query)) return '';
        const indent = (agent.depth || 0) * 14;
        const prefix = agent.depth > 0 ? '↳ ' : '';
        const modelLabel = agent.model || agent.requested_model || 'inherit';
        const barsHtml = (agent.turns || []).map(turn => {
          const left = showCompressed ? turn.gantt_comp_left_pct : turn.gantt_true_left_pct;
          const width = showCompressed ? turn.gantt_comp_width_pct : turn.gantt_true_width_pct;
          const tip = `${agent.name} • ${turn.label}\\nModel: ${modelLabel}\\nLocal: ${turn.start_local_full} → ${turn.end_local_full}\\nUTC: ${turn.start_iso} → ${turn.end_iso}\\nDuration: ${turn.duration_label} • Steps: ${turn.steps} • Tools: ${turn.tool_calls}`;
          return `<div class="gantt-bar bar-${escapeHtml(agent.phase)}" style="left:${left}%;width:${width}%;" title="${escapeHtml(tip)}"></div>`;
        }).join('');

        return `
          <div class="gantt-row" data-agent-key="${escapeHtml(agent._domKey)}" data-conv-id="${escapeHtml(agent.conv_id)}" onclick="jumpToAgent(this.dataset.agentKey)">
            <div class="gantt-label" style="padding-left:${indent}px;" title="${escapeHtml(agent.name)} (${escapeHtml(agent.role)} · ${escapeHtml(modelLabel)})">
              <span class="gantt-label-text">${escapeHtml(prefix + agent.name)}</span>
              <span class="gantt-model-chip">${escapeHtml(modelLabel)}</span>
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
        ? `<button class="mode-pill ${showCompressed ? 'active' : ''}" onclick="setGanttMode('compressed')">Compressed Pauses</button>`
        : '';

      panel.innerHTML = `
        <div class="gantt-header">
          <div class="gantt-title">Wall-Clock Execution Waterfall</div>
          <div class="gantt-controls">
            ${gapBtn}
            <button class="mode-pill ${!showCompressed ? 'active' : ''}" onclick="setGanttMode('true')">True Wall-Clock</button>
          </div>
        </div>
        <div class="gantt-axis">
          <div>Agent (tree depth &amp; model)</div>
          <div class="gantt-axis-track">
            <span>${escapeHtml(g.start_local || '')}</span>
            <span>${escapeHtml(showCompressed ? 'Active clusters (human pauses compressed)' : 'Linear wall-clock (' + (g.true_span_label || '') + ')')}</span>
            <span>${escapeHtml(g.end_local || '')}</span>
          </div>
          <div style="text-align:right;">Active · Start</div>
        </div>
        <div class="gantt-rows">${rowsHtml || '<div class="kpi-sub">No agents match the active filter.</div>'}</div>
      `;
    }

    function setGanttMode(mode) {
      ganttMode = mode;
      renderGantt();
    }

    function agentsShareWave(group, candidate) {
      return group.some(member => {
        if (
          member.parent_id && candidate.parent_id &&
          member.parent_id === candidate.parent_id &&
          member.spawn_step_index != null && candidate.spawn_step_index != null &&
          member.spawn_step_index === candidate.spawn_step_index
        ) {
          return true;
        }
        const mTurns = member.turns || [];
        const cTurns = candidate.turns || [];
        for (const mt of mTurns) {
          for (const ct of cTurns) {
            const overlapMs = Math.min(mt.end_ms, ct.end_ms) - Math.max(mt.start_ms, ct.start_ms);
            if (overlapMs > 3000) return true;
            if (mt.start_ms === mt.end_ms && ct.start_ms === ct.end_ms && Math.abs(mt.start_ms - ct.start_ms) <= 3000) {
              return true;
            }
          }
        }
        return false;
      });
    }

    function renderTimeline(data) {
      const container = document.getElementById('trajectoryTimeline');
      container.innerHTML = '';

      const phases = ['orchestration', 'discovery', 'planning', 'construction', 'verification'];
      const rollups = telemetry.phase_rollups || {};

      phases.forEach(phase => {
        const phaseAgents = data.filter(a => a.phase === phase);
        if (phaseAgents.length === 0) return;

        const phaseSection = document.createElement('div');
        phaseSection.className = 'timeline-phase';
        phaseSection.setAttribute('data-phase', phase);

        const r = rollups[phase] || {};
        const timingText = r.start_local
          ? `${r.start_local} → ${r.end_local} · Active ${r.active_label} · ${r.agent_count} agent(s)`
          : `${phaseAgents.length} agent(s)`;

        const pHeader = document.createElement('div');
        pHeader.className = 'phase-header';
        pHeader.innerHTML = `
          <div class="phase-title-group">
            <div class="phase-number">${escapeHtml(phaseConfig[phase].num)}</div>
            <h2 class="phase-title">${escapeHtml(phaseConfig[phase].title)}</h2>
          </div>
          <div class="phase-timing-pill">${escapeHtml(timingText)}</div>
        `;
        phaseSection.appendChild(pHeader);

        let i = 0;
        while (i < phaseAgents.length) {
          const agent = phaseAgents[i];
          if (agent.mode === 'parallel') {
            const parallelGroup = [agent];
            i++;
            while (i < phaseAgents.length && phaseAgents[i].mode === 'parallel' && agentsShareWave(parallelGroup, phaseAgents[i])) {
              parallelGroup.push(phaseAgents[i]);
              i++;
            }
            if (parallelGroup.length > 1) {
              const pGroupContainer = document.createElement('div');
              pGroupContainer.className = 'parallel-group-container';
              pGroupContainer.setAttribute('data-search', parallelGroup.map(a => `${a.name} ${a.type} ${a.role} ${a.model || ''} ${a.requested_model}`).join(' '));
              const badge = document.createElement('div');
              badge.className = 'parallel-group-badge';
              badge.textContent = `PARALLEL GROUP · ${parallelGroup.length} CONCURRENT`;
              pGroupContainer.appendChild(badge);

              const pGrid = document.createElement('div');
              pGrid.className = 'parallel-grid';
              parallelGroup.forEach(pAgent => pGrid.appendChild(createAgentBox(pAgent)));
              pGroupContainer.appendChild(pGrid);
              phaseSection.appendChild(pGroupContainer);
            } else {
              const soloPar = parallelGroup[0];
              const timelineItem = document.createElement('div');
              timelineItem.className = 'timeline-item ' + (phase === 'verification' ? 'node-verifier' : 'node-serial');
              timelineItem.setAttribute('data-agent-key', soloPar._domKey || '');
              timelineItem.setAttribute('data-conv-id', soloPar.conv_id || '');
              timelineItem.setAttribute('data-search', `${soloPar.name} ${soloPar.type} ${soloPar.role} ${soloPar.model || ''} ${soloPar.requested_model}`);
              const dot = document.createElement('div');
              dot.className = 'timeline-dot';
              timelineItem.appendChild(dot);
              timelineItem.appendChild(createAgentBox(soloPar));
              phaseSection.appendChild(timelineItem);
            }
          } else {
            const timelineItem = document.createElement('div');
            timelineItem.className = 'timeline-item ' + (phase === 'verification' ? 'node-verifier' : 'node-serial');
            timelineItem.setAttribute('data-agent-key', agent._domKey || '');
            timelineItem.setAttribute('data-conv-id', agent.conv_id || '');
            timelineItem.setAttribute('data-search', `${agent.name} ${agent.type} ${agent.role} ${agent.model || ''} ${agent.requested_model}`);
            const dot = document.createElement('div');
            dot.className = 'timeline-dot';
            timelineItem.appendChild(dot);
            timelineItem.appendChild(createAgentBox(agent));
            phaseSection.appendChild(timelineItem);
            i++;
          }
        }
        container.appendChild(phaseSection);
      });
      applyTimelineFilter();
    }

    function createAgentBox(agent) {
      const box = document.createElement('div');
      box.className = 'agent-box';
      box.id = 'agent-' + (agent._domKey || agent.conv_id);
      box.setAttribute('data-agent-key', agent._domKey || '');
      box.setAttribute('data-conv-id', agent.conv_id || '');
      box.onclick = () => toggleDetails(box);

      const initials = escapeHtml(
        String(agent.name || 'AG')
          .split(/[_\\-\\s]+/)
          .filter(Boolean)
          .map(n => n[0].toUpperCase())
          .join('')
          .substring(0, 2) || 'AG'
      );

      let avatarClass = 'avatar-worker';
      const nLow = (agent.name || '').toLowerCase();
      if (agent.depth === 0 || nLow.includes('supervisor') || nLow.includes('orchestrator')) avatarClass = 'avatar-orchestrator';
      else if (nLow.includes('validator') || nLow.includes('critic')) avatarClass = 'avatar-critic';
      else if (nLow.includes('auditor')) avatarClass = 'avatar-auditor';
      else if (nLow.includes('deliberator') || nLow.includes('reviewer')) avatarClass = 'avatar-reviewer';

      const modeClass = agent.mode === 'parallel' ? 'badge-parallel' : 'badge-serial';
      const statusText = agent.status || 'unknown';
      const statusClass = 'st-' + escapeHtml(statusText.toLowerCase());
      const safeConvId = escapeHtml(agent.conv_id || 'unknown');
      const tok = agent.tokens || {};

      const docsHTML = (agent.docs || []).map(doc =>
        `<a class="doc-link-item" href="${escapeHtml(doc.path)}" onclick="event.stopPropagation()">${escapeHtml(doc.name)}</a>`
      ).join('');

      const turnsHTML = (agent.turns || []).length > 0
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

      const toolsHTML = (agent.tool_breakdown || []).map(t =>
        `<span class="telemetry-pill">${escapeHtml(t.name)}: ${escapeHtml(t.count)}</span>`
      ).join('');

      const parentChip = agent.parent_name
        ? `<span class="telemetry-pill">Parent: ${escapeHtml(agent.parent_name)} (depth ${escapeHtml(agent.depth)})</span>`
        : `<span class="telemetry-pill">Depth ${escapeHtml(agent.depth)}</span>`;

      const transcriptName = agent.transcript_uri ? agent.transcript_uri.split('/').pop() : 'transcript.jsonl';
      const transcriptLink = agent.transcript_uri
        ? `<a class="doc-link-item" href="${escapeHtml(agent.transcript_uri)}" onclick="event.stopPropagation()">Open ${escapeHtml(transcriptName)}</a>`
        : '';

      const rawModel = agent.model || agent.requested_model || 'inherit';
      const modelMeta = agent.model_source === 'inherited' || agent.model_source === 'user_settings'
        ? `${rawModel} (${agent.model_source})`
        : rawModel;

      box.innerHTML = `
        <div class="agent-meta">
          <div class="agent-identity">
            <div class="agent-avatar ${avatarClass}">${initials}</div>
            <div class="agent-name-role">
              <div class="agent-name">${escapeHtml(agent.name)}</div>
              <div class="agent-role-badge">${escapeHtml(agent.role || agent.type)} · model: ${escapeHtml(modelMeta)}</div>
            </div>
          </div>
          <div class="badge-cluster">
            <span class="badge-clock" title="Wall span: ${escapeHtml(agent.wall_span_label)} (${escapeHtml(agent.wall_start_iso)} → ${escapeHtml(agent.wall_end_iso)})">
              ${escapeHtml(agent.wall_start_local)}–${escapeHtml(agent.wall_end_local)} · ${escapeHtml(agent.active_duration_label)}
            </span>
            <span class="status-badge ${statusClass}">${escapeHtml(statusText)}</span>
            <span class="execution-badge ${modeClass}">${escapeHtml(agent.mode)}</span>
          </div>
        </div>
        <div class="telemetry-strip">
          ${parentChip}
          <span class="telemetry-pill">Steps: ${escapeHtml(agent.step_count)}</span>
          <span class="telemetry-pill">Tools: ${escapeHtml(agent.tool_call_count)}</span>
          <span class="telemetry-pill">Tokens: ${escapeHtml(formatTokens(tok.total))} (${escapeHtml(formatTokens(tok.output))} out)</span>
          <span class="telemetry-pill">Rounds: ${escapeHtml((agent.turns || []).length)}</span>
        </div>
        <div class="handoff-summary">${escapeHtml(agent.summary)}</div>
        <div class="box-expand-details">
          <div class="detail-grid">
            <div>
              <div class="detail-label">Conversation ID &amp; Transcript</div>
              <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
                <div class="id-tag" data-conv-id="${safeConvId}" onclick="copyId(this.dataset.convId, event)">
                  ID: ${safeConvId}
                </div>
                ${transcriptLink}
              </div>
            </div>
            <div>
              <div class="detail-label">Initial Prompt / Task</div>
              <div class="detail-value" style="color: var(--text-muted);">${escapeHtml(agent.task)}</div>
            </div>
          </div>
          ${turnsHTML}
          ${toolsHTML ? `<div style="margin-bottom:14px;"><div class="detail-label">Tool Calls</div><div class="telemetry-strip">${toolsHTML}</div></div>` : ''}
          <div>
            <div class="detail-label">Produced / Modified Files</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              ${docsHTML || '<span style="font-size:0.8rem; color:var(--text-muted);">None recorded</span>'}
            </div>
          </div>
        </div>
      `;

      return box;
    }

    function toggleDetails(element) {
      const details = element.querySelector('.box-expand-details');
      if (details) details.classList.toggle('active');
    }

    function jumpToAgent(agentKey) {
      const el = document.getElementById('agent-' + agentKey);
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

    function applyTimelineFilter() {
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      document.querySelectorAll('.timeline-phase').forEach(phaseEl => {
        const phase = phaseEl.getAttribute('data-phase');
        if (activePhaseFilter !== 'all' && phase !== activePhaseFilter) {
          phaseEl.style.display = 'none';
          return;
        }
        let phaseVisible = 0;
        phaseEl.querySelectorAll('.timeline-item').forEach(item => {
          const key = item.getAttribute('data-agent-key') || item.getAttribute('data-conv-id') || '';
          const agent = agentsByKey[key];
          const match = agent
            ? agentMatchesFilter(agent, query)
            : (!query || ((item.getAttribute('data-search') || '') + ' ' + item.textContent).toLowerCase().includes(query));
          item.style.display = match ? 'flex' : 'none';
          if (match) phaseVisible++;
        });
        phaseEl.querySelectorAll('.parallel-group-container').forEach(container => {
          let groupVisible = 0;
          container.querySelectorAll('.agent-box').forEach(child => {
            const key = child.getAttribute('data-agent-key') || child.getAttribute('data-conv-id') || '';
            const agent = agentsByKey[key];
            const match = agent
              ? agentMatchesFilter(agent, query)
              : (!query || child.textContent.toLowerCase().includes(query));
            child.style.display = match ? 'block' : 'none';
            if (match) groupVisible++;
          });
          container.style.display = groupVisible > 0 ? 'block' : 'none';
          phaseVisible += groupVisible;
        });
        phaseEl.style.display = phaseVisible > 0 ? 'block' : 'none';
      });
    }

    function filterPhase(phase, btn) {
      activePhaseFilter = phase;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyTimelineFilter();
      renderGantt();
    }

    function filterSwarm() {
      applyTimelineFilter();
      renderGantt();
    }

    renderHeader();
    renderSummary();
    renderGantt();
    renderTimeline(agentsData);
  </script>
</body>
</html>"""


def render_html(telemetry: Dict[str, Any]) -> str:
    """Inject telemetry JSON safely into HTML_TEMPLATE."""
    payload = json.dumps(telemetry, indent=2).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__TELEMETRY_DATA_PLACEHOLDER__", payload)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an interactive AGY swarm trajectory dashboard with wall-clock & timing."
    )
    parser.add_argument("-c", "--conversation-id", help="Root AGY conversation ID (or unique prefix) to render.")
    parser.add_argument("-l", "--list", action="store_true", help="List matching AGY conversations for the workspace and exit.")
    parser.add_argument("-o", "--output", help="Output HTML path (default: <workspace>/.agents/trajectory.html).")
    parser.add_argument("-w", "--workspace", help="Project workspace root (default: auto-detected from cwd).")
    parser.add_argument("--agy-dir", help="Override AGY CLI data directory (default: ~/.gemini/antigravity-cli).")
    parser.add_argument("--legacy", action="store_true", help="Force legacy .agents/ BRIEFING.md/handoff.md parser.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    workspace_root = os.path.abspath(args.workspace) if args.workspace else resolve_workspace_root()
    agy_dir = resolve_agy_dir(args.agy_dir)

    if args.list:
        runs = list_agy_runs(agy_dir, workspace_root)
        if not runs:
            print(f"No AGY conversations found matching workspace: {workspace_root}")
            return 0
        print(f"AGY runs for {workspace_root} (data dir: {agy_dir}):")
        for r in runs:
            print(
                f"  {r['conversation_id']}  subagents={r['subagent_count']:<3} "
                f"steps={r['step_count']:<5} updated={r['last_modified_time'][:19]}  {r['title']}"
            )
        return 0

    telemetry: Optional[Dict[str, Any]] = None
    try:
        if not args.legacy:
            selected_id = select_agy_run(agy_dir, workspace_root, args.conversation_id)
            if selected_id:
                telemetry = parse_agy_run(agy_dir, selected_id, workspace_root)
            elif args.conversation_id:
                sys.stderr.write(f"Error: conversation '{args.conversation_id}' not found under {agy_dir}\n")
                return 1

        if telemetry is None:
            agents_dir = os.path.join(workspace_root, ".agents")
            if os.path.isdir(agents_dir):
                telemetry = parse_legacy_agents_dir(agents_dir, workspace_root)
            else:
                sys.stderr.write(
                    f"Error: no AGY runs found for workspace '{workspace_root}' in '{agy_dir}' "
                    f"and no legacy '{agents_dir}' directory exists.\n"
                )
                return 1
    except ValueError as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1

    default_out = os.path.join(workspace_root, ".agents", "trajectory.html")
    output_path = os.path.abspath(args.output or default_out)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    html = render_html(telemetry)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    s = telemetry["summary"]
    print(
        f"Trajectory generated ({telemetry['source']}): {output_path}\n"
        f"  Run: {telemetry['run_title']} ({telemetry['root_conversation_id']})\n"
        f"  Wall-clock: {s['wall_start_local']} -> {s['wall_end_local']} "
        f"(span {s['wall_span_label']}, active {s['active_wall_label']}, "
        f"subagent sum {s['subagent_cumulative_label']}, speedup {s['parallelism_speedup']}x)\n"
        f"  Agents: {s['total_agents']} ({s['subagent_count']} subagents), "
        f"steps: {s['total_steps']}, tools: {s['total_tool_calls']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
