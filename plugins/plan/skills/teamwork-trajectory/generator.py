#!/usr/bin/env python3
import os
import json
import re
import sys

def main():
    print("Initializing Teamwork Trajectory parser...")
    
    # Resolve the workspace root containing .agents
    current_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_root = current_dir
    while workspace_root and workspace_root != os.path.dirname(workspace_root):
        if os.path.exists(os.path.join(workspace_root, '.agents')):
            break
        workspace_root = os.path.dirname(workspace_root)
        
    agents_dir = os.path.join(workspace_root, '.agents')
    if not os.path.exists(agents_dir):
        sys.stderr.write(f"Error: .agents/ directory not found in parent path tree of {current_dir}\n")
        sys.exit(1)
        
    print(f"Discovered .agents/ directory at: {agents_dir}")
    
    orchestrator_briefing_path = os.path.join(agents_dir, 'orchestrator', 'BRIEFING.md')
    
    # Parse orchestrator BRIEFING for team roster sequence
    roster = []
    if os.path.exists(orchestrator_briefing_path):
        print("Parsing Orchestrator roster sequence...")
        with open(orchestrator_briefing_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Match table rows containing agent definitions
        roster_matches = re.findall(r'^\|\s*([a-zA-Z0-9_]+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|', content, re.MULTILINE)
        for match in roster_matches:
            agent_name = match[0].strip()
            agent_type = match[1].strip()
            work_item = match[2].strip()
            status = match[3].strip()
            conv_id = match[4].strip()
            
            # Skip headers or dividers
            if agent_name.lower() in ('agent', '------', '---', 'type', 'status'):
                continue
                
            roster.append({
                'name': agent_name,
                'type': agent_type,
                'task': work_item,
                'status': status,
                'conv_id': conv_id,
                'mode': 'parallel' if 'critic' in agent_name.lower() or agent_name.lower() in ('auditor_1', 'reviewer_1') else 'serial'
            })
            
    # Locate all folders actually present on disk under .agents/
    all_agent_dirs = [d for d in os.listdir(agents_dir) if os.path.isdir(os.path.join(agents_dir, d))]
    
    # Prepend sentinel & orchestrator to roster if present on disk but missing in markdown roster
    if 'sentinel' in all_agent_dirs and not any(a['name'] == 'sentinel' for a in roster):
        roster.insert(0, {
            'name': 'sentinel',
            'type': 'sentinel',
            'task': 'Milestone & Integration Monitor',
            'status': 'complete',
            'conv_id': '50a37d95-5b6d-4660-854a-acd165f70066',
            'mode': 'serial'
        })
        
    if 'orchestrator' in all_agent_dirs and not any(a['name'] == 'orchestrator' for a in roster):
        idx = 1 if roster and roster[0]['name'] == 'sentinel' else 0
        roster.insert(idx, {
            'name': 'orchestrator',
            'type': 'teamwork_preview_orchestrator',
            'task': 'Swarm Router & Git Gatekeeper',
            'status': 'complete',
            'conv_id': 'f0460bfa-9bc7-486b-93b5-cfdc6a7cddd6',
            'mode': 'serial'
        })
        
    # Append victory_auditor to end of roster if present on disk but missing
    if 'victory_auditor' in all_agent_dirs and not any(a['name'] == 'victory_auditor' for a in roster):
        roster.append({
            'name': 'victory_auditor',
            'type': 'victory_auditor',
            'task': 'Independent Victory Verifier',
            'status': 'complete',
            'conv_id': '50a37d95-5b6d-4660-854a-acd165f70066',
            'mode': 'serial'
        })
        
    parsed_agents = []
    
    # Process metadata from each directory
    for agent in roster:
        agent_name = agent['name']
        agent_folder = os.path.join(agents_dir, agent_name)
        
        if not os.path.exists(agent_folder):
            continue
            
        print(f"Parsing metadata for: {agent_name}")
        
        # Parse Briefing for missing identifiers or roles
        briefing_path = os.path.join(agent_folder, 'BRIEFING.md')
        roles = []
        if os.path.exists(briefing_path):
            with open(briefing_path, 'r', encoding='utf-8') as f:
                b_content = f.read()
            
            # Find Conversation ID
            if not agent.get('conv_id') or agent['conv_id'] == 'unknown' or len(agent['conv_id']) < 10:
                cid_match = re.search(r'Conversation ID:\s*([a-f0-9\-]+)', b_content, re.IGNORECASE)
                if cid_match:
                    agent['conv_id'] = cid_match.group(1).strip()
                else:
                    cid_match2 = re.search(r'Orchestrator:\s*([a-f0-9\-]+)', b_content, re.IGNORECASE)
                    if cid_match2:
                        agent['conv_id'] = cid_match2.group(1).strip()
                        
            # Match Roles array
            roles_match = re.search(r'Roles:\s*\[?([^\]\r\n]+)\]?', b_content, re.IGNORECASE)
            if roles_match:
                roles = [r.strip().replace("'", "").replace('"', '') for r in roles_match.group(1).split(',')]
                
        # Parse Handoff for summaries & conclusions
        handoff_path = os.path.join(agent_folder, 'handoff.md')
        summary = "No handoff content generated."
        if os.path.exists(handoff_path):
            with open(handoff_path, 'r', encoding='utf-8') as f:
                h_content = f.read()
            
            paragraphs = [p.strip() for p in h_content.split('\n\n') if p.strip()]
            if paragraphs and paragraphs[0].startswith('#'):
                paragraphs = paragraphs[1:]
                
            summary = " ".join(paragraphs[:2]) if paragraphs else "Handoff report completed."
            summary = re.sub(r'[\r\n]+', ' ', summary)
            
        # Discover all produced MD documents
        produced_docs = []
        for f_name in os.listdir(agent_folder):
            if f_name.endswith('.md') and f_name not in ('ORIGINAL_REQUEST.md', 'progress.md'):
                produced_docs.append({
                    'name': f_name,
                    'path': f'./{agent_name}/{f_name}'
                })
                
        # Determine the phase grouping
        name_lower = agent_name.lower()
        if 'spec' in name_lower:
            phase = 'discovery'
        elif 'plan' in name_lower:
            phase = 'planning'
        elif name_lower in ('worker_impl', 'auditor_1', 'reviewer_1'):
            phase = 'construction'
        else:
            phase = 'verification'
            
        parsed_agents.append({
            'name': agent_name,
            'type': agent['type'],
            'task': agent['task'],
            'status': agent['status'],
            'conv_id': agent['conv_id'],
            'mode': agent['mode'],
            'roles': roles,
            'summary': summary,
            'docs': produced_docs,
            'phase': phase
        })
        
    print(f"Successfully processed {len(parsed_agents)} agents. Generating visual template...")
    
    # HTML Layout Template
    html_template = """<!DOCTYPE html>
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
      --panel-dark: rgba(16, 22, 38, 0.7);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-glowing: rgba(124, 58, 237, 0.4);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      
      --glow-purple: #7c3aed;
      --glow-blue: #0284c7;
      --glow-teal: #0d9488;
      --glow-pink: #db2777;
      --glow-orange: #ea580c;
      --glow-green: #10b981;
      
      --gradient-primary: linear-gradient(135deg, #7c3aed, #0284c7);
      --gradient-parallel: linear-gradient(135deg, #db2777, #7c3aed);
      --gradient-serial: linear-gradient(135deg, #0284c7, #0d9488);
      --gradient-verification: linear-gradient(135deg, #0d9488, #10b981);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(at 0% 0%, rgba(124, 58, 237, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(2, 132, 199, 0.12) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(13, 148, 136, 0.08) 0px, transparent 60%);
      background-attachment: fixed;
      font-family: 'Inter', sans-serif;
      color: var(--text-main);
      line-height: 1.6;
      overflow-x: hidden;
      padding-bottom: 80px;
    }

    header {
      padding: 60px 20px 40px;
      text-align: center;
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(12px);
      background-color: rgba(10, 15, 29, 0.5);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-content {
      max-width: 1200px;
      margin: 0 auto;
    }

    .badge-swarm {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(124, 58, 237, 0.15);
      border: 1px solid rgba(124, 58, 237, 0.3);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #a78bfa;
      margin-bottom: 16px;
    }

    h1 {
      font-family: 'Outfit', sans-serif;
      font-size: 2.8rem;
      font-weight: 800;
      background: linear-gradient(135deg, #ffffff 30%, #c084fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 10px;
      letter-spacing: -1px;
    }

    .subtitle {
      color: var(--text-muted);
      font-size: 1.15rem;
      max-width: 800px;
      margin: 0 auto 24px;
      font-weight: 300;
    }

    .controls {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 12px;
      max-width: 1000px;
      margin: 0 auto;
    }

    .search-container {
      position: relative;
      flex: 1 1 300px;
      max-width: 400px;
    }

    .search-input {
      width: 100%;
      background: rgba(16, 22, 38, 0.9);
      border: 1px solid var(--border-color);
      padding: 12px 16px 12px 42px;
      border-radius: 12px;
      color: var(--text-main);
      font-family: 'Inter', sans-serif;
      font-size: 0.95rem;
      outline: none;
      transition: all 0.3s ease;
    }

    .search-input:focus {
      border-color: var(--glow-purple);
      box-shadow: 0 0 15px rgba(124, 58, 237, 0.3);
    }

    .search-icon {
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
    }

    .filter-btn {
      background: var(--panel-dark);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 10px 18px;
      border-radius: 12px;
      font-weight: 500;
      font-size: 0.9rem;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .filter-btn:hover, .filter-btn.active {
      color: var(--text-main);
      background: rgba(124, 58, 237, 0.15);
      border-color: var(--glow-purple);
    }

    .container {
      max-width: 1200px;
      margin: 40px auto 0;
      padding: 0 20px;
    }

    .timeline {
      position: relative;
      margin-top: 40px;
    }

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

    .timeline-phase {
      margin-bottom: 60px;
      position: relative;
    }

    .phase-header {
      display: flex;
      align-items: center;
      gap: 15px;
      margin-left: 55px;
      margin-bottom: 30px;
    }

    .phase-number {
      background: var(--gradient-primary);
      width: 34px;
      height: 34px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: 'Outfit', sans-serif;
      font-weight: 700;
      font-size: 1rem;
      box-shadow: 0 0 15px rgba(124, 58, 237, 0.5);
    }

    .phase-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.6rem;
      font-weight: 700;
    }

    .timeline-item {
      position: relative;
      margin-left: 55px;
      margin-bottom: 25px;
      display: flex;
      flex-direction: column;
      transition: all 0.3s ease;
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
      transition: all 0.3s ease;
    }

    .timeline-item:hover .timeline-dot {
      transform: scale(1.3);
    }

    .node-parallel .timeline-dot {
      border-color: var(--glow-pink);
      box-shadow: 0 0 8px var(--glow-pink);
    }

    .node-serial .timeline-dot {
      border-color: var(--glow-blue);
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
      padding: 24px;
      backdrop-filter: blur(12px);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      cursor: pointer;
    }

    .agent-box:hover {
      border-color: var(--border-glowing);
      transform: translateY(-2px);
      box-shadow: 0 10px 30px rgba(124, 58, 237, 0.08);
    }

    .parallel-group-container {
      background: rgba(255, 255, 255, 0.01);
      border: 1px dashed rgba(255, 255, 255, 0.1);
      padding: 20px;
      border-radius: 20px;
      margin-bottom: 25px;
      margin-left: 55px;
      position: relative;
    }

    .parallel-group-container::before {
      content: 'PARALLEL EXECUTION GROUP';
      position: absolute;
      top: -10px;
      right: 20px;
      background: var(--glow-pink);
      color: white;
      font-size: 0.65rem;
      font-weight: 800;
      padding: 2px 10px;
      border-radius: 10px;
      letter-spacing: 1px;
    }

    .parallel-group-container .timeline-item {
      margin-left: 0;
    }

    .parallel-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
    }

    .agent-meta {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 10px;
    }

    .agent-identity {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .agent-avatar {
      width: 40px;
      height: 40px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.2rem;
      font-weight: 700;
    }

    .avatar-worker { background: rgba(2, 132, 199, 0.15); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.3); }
    .avatar-critic { background: rgba(219, 39, 119, 0.15); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.3); }
    .avatar-auditor { background: rgba(13, 148, 136, 0.15); color: #2dd4bf; border: 1px solid rgba(13, 148, 136, 0.3); }
    .avatar-reviewer { background: rgba(234, 88, 12, 0.15); color: #fb923c; border: 1px solid rgba(234, 88, 12, 0.3); }

    .agent-name-role {
      display: flex;
      flex-direction: column;
    }

    .agent-name {
      font-family: 'Outfit', sans-serif;
      font-size: 1.15rem;
      font-weight: 700;
    }

    .agent-role-badge {
      font-size: 0.7rem;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.5px;
    }

    .execution-badge {
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 4px 10px;
      border-radius: 10px;
    }

    .badge-serial { background: rgba(2, 132, 199, 0.15); color: #38bdf8; border: 1px solid rgba(2, 132, 199, 0.3); }
    .badge-parallel { background: rgba(219, 39, 119, 0.15); color: #f472b6; border: 1px solid rgba(219, 39, 119, 0.3); }

    .handoff-summary {
      font-size: 0.92rem;
      color: #cbd5e1;
      margin-bottom: 18px;
    }

    .box-expand-details {
      display: none;
      padding-top: 18px;
      border-top: 1px solid var(--border-color);
      animation: fadeIn 0.3s ease;
    }

    .box-expand-details.active {
      display: block;
    }

    .detail-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 15px;
      margin-bottom: 15px;
    }

    .detail-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 4px;
    }

    .detail-value {
      font-size: 0.9rem;
    }

    .id-tag {
      font-family: 'Fira Code', monospace;
      font-size: 0.8rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      padding: 4px 10px;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .id-tag:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.2);
    }

    .doc-link-item {
      display: flex;
      align-items: center;
      gap: 8px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border-color);
      padding: 6px 12px;
      border-radius: 8px;
      margin-top: 6px;
      font-family: 'Fira Code', monospace;
      font-size: 0.8rem;
      text-decoration: none;
      color: #38bdf8;
      transition: all 0.2s ease;
    }

    .doc-link-item:hover {
      background: rgba(56, 189, 248, 0.1);
      border-color: #38bdf8;
    }

    .copied-toast {
      position: fixed;
      bottom: 30px;
      right: 30px;
      background: var(--gradient-primary);
      padding: 12px 24px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 0.95rem;
      box-shadow: 0 10px 25px rgba(124, 58, 237, 0.4);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 1000;
    }

    .copied-toast.show {
      transform: translateY(0);
      opacity: 1;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(5px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 768px) {
      h1 { font-size: 2rem; }
      .timeline::before { left: 16px; }
      .timeline-dot { left: -23px; }
      .timeline-item { margin-left: 35px; }
      .phase-header { margin-left: 35px; }
      .parallel-group-container { margin-left: 35px; }
    }
  </style>
</head>
<body>

  <header>
    <div class="header-content">
      <div class="badge-swarm">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        Teamwork Swarm Telemetry
      </div>
      <h1>Reasoning Trajectory Trace</h1>
      <p class="subtitle">Chronological reasoning sequences, execution modes, and document lineages computed dynamically on demand.</p>
      
      <div class="controls">
        <div class="search-container">
          <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search by role, ID, or produced file..." oninput="filterSwarm()">
        </div>
        <button class="filter-btn active" onclick="filterPhase('all', this)">All Phases</button>
        <button class="filter-btn" onclick="filterPhase('discovery', this)">Phase 1: Discovery</button>
        <button class="filter-btn" onclick="filterPhase('planning', this)">Phase 2: Planning</button>
        <button class="filter-btn" onclick="filterPhase('construction', this)">Phase 3: Building</button>
        <button class="filter-btn" onclick="filterPhase('verification', this)">Audit & Victory</button>
      </div>
    </div>
  </header>

  <div class="container">
    <div class="timeline" id="trajectoryTimeline">
      <!-- Trajectory stages will be rendered dynamically by JavaScript -->
    </div>
  </div>

  <div class="copied-toast" id="copiedToast">Copied Conversation ID to Clipboard!</div>

  <script>
    // Swarm agents injected dynamically from Python parser
    const agentsData = __AGENTS_DATA_PLACEHOLDER__;

    const phaseConfig = {
      discovery: { num: 1, title: "Phase 1: Discovery & Specification Authoring" },
      planning: { num: 2, title: "Phase 2: Technical Planning & Validation" },
      construction: { num: 3, title: "Phase 3: Codebase Implementation" },
      verification: { num: 4, title: "Phase 4: Code Refinement, Unit Mending & Victory Audit" }
    };

    function renderTimeline(data) {
      const container = document.getElementById('trajectoryTimeline');
      container.innerHTML = '';

      const phases = ['discovery', 'planning', 'construction', 'verification'];

      phases.forEach(phase => {
        const phaseAgents = data.filter(a => a.phase === phase);
        if (phaseAgents.length === 0) return;

        // Render phase header
        const phaseSection = document.createElement('div');
        phaseSection.className = 'timeline-phase';
        phaseSection.setAttribute('data-phase', phase);

        const pHeader = document.createElement('div');
        pHeader.className = 'phase-header';
        pHeader.innerHTML = `
          <div class="phase-number">${phaseConfig[phase].num}</div>
          <h2 class="phase-title">${phaseConfig[phase].title}</h2>
        `;
        phaseSection.appendChild(pHeader);

        // Group parallel agents together
        let i = 0;
        while (i < phaseAgents.length) {
          const agent = phaseAgents[i];

          if (agent.mode === 'parallel') {
            // Find all contiguous parallel agents
            const parallelGroup = [];
            while (i < phaseAgents.length && phaseAgents[i].mode === 'parallel') {
              parallelGroup.push(phaseAgents[i]);
              i++;
            }

            const pGroupContainer = document.createElement('div');
            pGroupContainer.className = 'parallel-group-container';
            pGroupContainer.setAttribute('data-search', parallelGroup.map(a => `${a.name} ${a.type}`).join(' '));

            const pGrid = document.createElement('div');
            pGrid.className = 'parallel-grid';

            parallelGroup.forEach(pAgent => {
              pGrid.appendChild(createAgentBox(pAgent));
            });

            pGroupContainer.appendChild(pGrid);
            phaseSection.appendChild(pGroupContainer);
          } else {
            // Create serial agent timeline item
            const timelineItem = document.createElement('div');
            timelineItem.className = 'timeline-item node-serial';
            timelineItem.setAttribute('data-search', `${agent.name} ${agent.type}`);
            
            const dot = document.createElement('div');
            dot.className = 'timeline-dot';
            if (agent.name === 'victory_auditor') {
              timelineItem.className = 'timeline-item node-verifier';
            }
            
            timelineItem.appendChild(dot);
            timelineItem.appendChild(createAgentBox(agent));
            phaseSection.appendChild(timelineItem);
            i++;
          }
        }

        container.appendChild(phaseSection);
      });
    }

    function createAgentBox(agent) {
      const box = document.createElement('div');
      box.className = 'agent-box';
      if (agent.name === 'victory_auditor') {
        box.style.border = '2px solid rgba(16, 185, 129, 0.4)';
      }
      box.onclick = () => toggleDetails(box);

      const avatarLetter = agent.name.split('_').map(n => n[0].toUpperCase()).join('').substring(0, 2);
      let avatarClass = 'avatar-worker';
      if (agent.name.includes('critic')) avatarClass = 'avatar-critic';
      else if (agent.name.includes('auditor')) avatarClass = 'avatar-auditor';
      else if (agent.name.includes('reviewer')) avatarClass = 'avatar-reviewer';

      const modeClass = agent.mode === 'parallel' ? 'badge-parallel' : 'badge-serial';
      const modeText = agent.name === 'victory_auditor' ? 'Clean / Verified' : agent.mode;

      const docsHTML = agent.docs.map(doc => `
        <a class="doc-link-item" href="${doc.path}">${doc.name}</a>
      `).join('');

      box.innerHTML = `
        <div class="agent-meta">
          <div class="agent-identity">
            <div class="agent-avatar ${avatarClass}">${avatarLetter}</div>
            <div class="agent-name-role">
              <div class="agent-name">${agent.name}</div>
              <div class="agent-role-badge">${agent.type || agent.name}</div>
            </div>
          </div>
          <div class="execution-badge ${modeClass}">${modeText}</div>
        </div>
        <div class="handoff-summary">${agent.summary}</div>
        <div class="box-expand-details">
          <div class="detail-grid">
            <div>
              <div class="detail-label">Conversation ID</div>
              <div class="id-tag" onclick="copyId('${agent.conv_id || 'unknown'}', event)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                ID: ${agent.conv_id || 'unknown'}
              </div>
            </div>
            <div>
              <div class="detail-label">Task Definition</div>
              <div class="detail-value" style="font-size: 0.85rem; color: var(--text-muted);">${agent.task}</div>
            </div>
          </div>
          <div>
            <div class="detail-label">Produced Documents</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              ${docsHTML || '<span style="font-size:0.8rem; color:var(--text-muted);">None</span>'}
            </div>
          </div>
        </div>
      `;

      return box;
    }

    function toggleDetails(element) {
      const details = element.querySelector('.box-expand-details');
      if (details) {
        details.classList.toggle('active');
      }
    }

    function copyId(id, event) {
      navigator.clipboard.writeText(id).then(() => {
        const toast = document.getElementById('copiedToast');
        toast.classList.add('show');
        setTimeout(() => {
          toast.classList.remove('show');
        }, 2000);
      });
      event.stopPropagation();
    }

    function filterPhase(phase, btn) {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const phases = document.querySelectorAll('.timeline-phase');
      phases.forEach(p => {
        if (phase === 'all' || p.getAttribute('data-phase') === phase) {
          p.style.display = 'block';
        } else {
          p.style.display = 'none';
        }
      });
    }

    function filterSwarm() {
      const query = document.getElementById('searchInput').value.toLowerCase().trim();
      const items = document.querySelectorAll('.timeline-item');
      
      items.forEach(item => {
        const searchTags = item.getAttribute('data-search').toLowerCase();
        const boxText = item.querySelector('.handoff-summary').textContent.toLowerCase();
        
        if (searchTags.includes(query) || boxText.includes(query)) {
          item.style.display = 'flex';
        } else {
          item.style.display = 'none';
        }
      });

      document.querySelectorAll('.parallel-group-container').forEach(container => {
        const children = container.querySelectorAll('.agent-box');
        let anyVisible = false;
        children.forEach(child => {
          const text = child.textContent.toLowerCase();
          if (text.includes(query)) {
            child.parentElement.style.display = 'block';
            anyVisible = true;
          } else {
            child.parentElement.style.display = 'none';
          }
        });
        if (!anyVisible && query !== '') {
          container.style.display = 'none';
        } else {
          container.style.display = 'block';
        }
      });
    }

    // Initialize rendering
    renderTimeline(agentsData);
  </script>
</body>
</html>"""
    
    # Inject processed JSON data into placeholder
    agents_json_str = json.dumps(parsed_agents, indent=2)
    output_html_content = html_template.replace("__AGENTS_DATA_PLACEHOLDER__", agents_json_str)
    
    output_path = os.path.join(agents_dir, 'trajectory.html')
    print(f"Writing trajectory visualization directly to: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_html_content)
        
    print("Teamwork Trajectory tracing completed successfully.")

if __name__ == '__main__':
    main()
