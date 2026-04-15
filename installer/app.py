"""
OpenClaw Workspace — Web Dashboard + Setup Wizard
Single-file FastAPI app. No framework dependencies beyond fastapi + uvicorn.

Usage:
  pip install fastapi uvicorn
  python3 installer/app.py
  Open: http://localhost:8181
"""

import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import uvicorn

app = FastAPI(title="OpenClaw Workspace", version="2.0.0")

TEMPLATE_DIR = Path(__file__).parent.parent
OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_DIR", Path.home() / ".openclaw"))

# ── In-memory session store ────────────────────────────────
SESSIONS: dict = {}

def get_session(session_id: Optional[str]) -> dict:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    return {}

def save_session(session_id: str, data: dict):
    SESSIONS[session_id] = data

# ── OpenClaw CLI helpers ───────────────────────────────────
def run_cmd(cmd: list, timeout=10) -> tuple[str, str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except Exception as e:
        return "", str(e), 1

def openclaw_status() -> dict:
    out, err, code = run_cmd(["openclaw", "status"])
    return {"running": code == 0, "output": out or err}

def openclaw_agents() -> list:
    out, err, code = run_cmd(["openclaw", "agents", "list"])
    if code != 0:
        return []
    agents = []
    for line in out.strip().splitlines():
        if line.strip():
            agents.append({"id": line.strip(), "status": "registered"})
    return agents

def openclaw_cron() -> list:
    cron_file = OPENCLAW_DIR / "cron" / "jobs.json"
    if cron_file.exists():
        try:
            return json.loads(cron_file.read_text())
        except Exception:
            pass
    return []

def read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def read_text_safe(path: Path, max_lines=100) -> str:
    try:
        lines = path.read_text().splitlines()
        return "\n".join(lines[:max_lines])
    except Exception:
        return ""

def get_cost_data() -> dict:
    f = OPENCLAW_DIR / "workspace" / "ops" / "cost-tracker.json"
    return read_json_safe(f)

def get_memory() -> str:
    f = OPENCLAW_DIR / "workspace" / "MEMORY.md"
    return read_text_safe(f)

def get_today_log() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    f = OPENCLAW_DIR / "workspace" / "memory" / f"{today}.md"
    return read_text_safe(f, max_lines=50)

def is_openclaw_configured() -> bool:
    return (OPENCLAW_DIR / "openclaw.json").exists()

# ── CSS / JS shared ────────────────────────────────────────
SHARED_CSS = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0a0a14; --surface: #12121f; --card: #1a1a2e;
  --border: #2a2a45; --purple: #7c3aed; --purple-light: #a855f7;
  --green: #22c55e; --red: #ef4444; --yellow: #f59e0b;
  --text: #e2e8f0; --muted: #64748b; --subtle: #334155;
}
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
       background: var(--bg); color: var(--text); min-height: 100vh; font-size: 14px; }
a { color: var(--purple-light); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Layout */
.app { display: flex; min-height: 100vh; }
.sidebar { width: 220px; background: var(--surface); border-right: 1px solid var(--border);
           padding: 20px 0; display: flex; flex-direction: column; flex-shrink: 0;
           position: fixed; top: 0; left: 0; height: 100vh; z-index: 100; }
.main { margin-left: 220px; flex: 1; padding: 28px 32px; }

/* Sidebar */
.sidebar-logo { padding: 0 20px 20px; border-bottom: 1px solid var(--border); }
.sidebar-logo h2 { font-size: 16px; font-weight: 700; color: var(--purple-light); }
.sidebar-logo span { font-size: 11px; color: var(--muted); }
.nav { padding: 16px 0; flex: 1; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 20px;
            color: var(--muted); cursor: pointer; transition: all 0.15s;
            border-left: 3px solid transparent; font-size: 13px; font-weight: 500; }
.nav-item:hover { color: var(--text); background: var(--card); }
.nav-item.active { color: var(--purple-light); background: rgba(124,58,237,0.1);
                   border-left-color: var(--purple); }
.nav-item svg { width: 16px; height: 16px; flex-shrink: 0; }
.sidebar-footer { padding: 16px 20px; border-top: 1px solid var(--border); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
.dot-red { background: var(--red); box-shadow: 0 0 6px var(--red); }
.dot-yellow { background: var(--yellow); }

/* Cards */
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px;
        padding: 24px; margin-bottom: 20px; }
.card-sm { padding: 16px; }
.card h3 { font-size: 15px; font-weight: 600; margin-bottom: 4px; }
.card .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
               color: var(--muted); margin-bottom: 12px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }

/* Stats */
.stat { display: flex; flex-direction: column; }
.stat .num { font-size: 28px; font-weight: 700; color: var(--purple-light); line-height: 1; }
.stat .desc { font-size: 12px; color: var(--muted); margin-top: 4px; }

/* Badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px;
         font-weight: 600; letter-spacing: 0.02em; }
.badge-green { background: rgba(34,197,94,0.15); color: var(--green); }
.badge-red { background: rgba(239,68,68,0.15); color: var(--red); }
.badge-yellow { background: rgba(245,158,11,0.15); color: var(--yellow); }
.badge-purple { background: rgba(124,58,237,0.15); color: var(--purple-light); }
.badge-muted { background: var(--subtle); color: var(--muted); }

/* Table */
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
     color: var(--muted); padding: 0 12px 10px; font-weight: 600; }
td { padding: 12px; border-top: 1px solid var(--border); font-size: 13px; vertical-align: middle; }
tr:hover td { background: rgba(255,255,255,0.02); }
td:first-child, th:first-child { padding-left: 0; }

/* Buttons */
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px;
       border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer;
       border: none; transition: all 0.15s; text-decoration: none; white-space: nowrap; }
.btn-primary { background: var(--purple); color: white; }
.btn-primary:hover { background: #6d28d9; text-decoration: none; }
.btn-ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
.btn-ghost:hover { color: var(--text); border-color: var(--subtle); text-decoration: none; }
.btn-green { background: rgba(34,197,94,0.15); color: var(--green); border: 1px solid rgba(34,197,94,0.3); }
.btn-green:hover { background: rgba(34,197,94,0.25); }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-row { display: flex; gap: 10px; align-items: center; }

/* Forms */
.form-group { margin-bottom: 18px; }
label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; font-weight: 500; }
input[type=text], input[type=email], input[type=password], input[type=time],
input[type=number], select, textarea {
  width: 100%; padding: 9px 13px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; color: var(--text); font-size: 13px; outline: none; transition: border 0.15s; }
input:focus, select:focus, textarea:focus { border-color: var(--purple); }
.hint { font-size: 11px; color: var(--muted); margin-top: 5px; }
.section-sep { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
               color: var(--muted); padding: 16px 0 8px; border-top: 1px solid var(--border); margin-top: 16px; }

/* Progress bar */
.progress-bar { display: flex; gap: 4px; margin-bottom: 32px; }
.progress-step { flex: 1; height: 3px; border-radius: 2px; background: var(--border); }
.progress-step.done { background: var(--green); }
.progress-step.active { background: var(--purple); }

/* Code / pre */
pre, code { font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace; }
pre { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
      padding: 16px; font-size: 12px; color: #94a3b8; overflow-x: auto; white-space: pre-wrap;
      word-break: break-all; line-height: 1.6; }
.inline-code { background: var(--surface); padding: 2px 6px; border-radius: 4px;
               font-size: 12px; color: var(--purple-light); }

/* Page title */
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; }
.page-header p { color: var(--muted); margin-top: 4px; font-size: 13px; }

/* Agent grid */
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.agent-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
              padding: 14px 16px; transition: border-color 0.15s; }
.agent-card:hover { border-color: var(--purple); }
.agent-card h4 { font-size: 13px; font-weight: 600; margin-bottom: 3px; }
.agent-card p { font-size: 11px; color: var(--muted); }
.agent-card .model { font-size: 10px; color: var(--purple-light); margin-top: 6px; }

/* Scrollable code block */
.log-box { background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
           padding: 16px; font-family: monospace; font-size: 12px; color: #94a3b8;
           max-height: 340px; overflow-y: auto; line-height: 1.7; white-space: pre-wrap; }

/* Toggle */
.toggle { position: relative; display: inline-block; width: 36px; height: 20px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
          background: var(--border); border-radius: 20px; transition: .2s; }
.slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px;
                 bottom: 3px; background: white; border-radius: 50%; transition: .2s; }
input:checked + .slider { background: var(--purple); }
input:checked + .slider:before { transform: translateX(16px); }

/* Responsive */
@media (max-width: 768px) {
  .sidebar { transform: translateX(-100%); }
  .main { margin-left: 0; padding: 20px; }
  .grid-4 { grid-template-columns: repeat(2, 1fr); }
}

/* Alert/notice */
.notice { padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 16px; }
.notice-yellow { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.3); color: var(--yellow); }
.notice-green { background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); color: var(--green); }
.notice-red { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: var(--red); }
.notice-blue { background: rgba(124,58,237,0.1); border: 1px solid rgba(124,58,237,0.4); color: var(--purple-light); }
</style>
"""

SIDEBAR_JS = """
<script>
function setTab(tab) {
  document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const target = document.getElementById('tab-' + tab);
  if (target) target.style.display = 'block';
  const nav = document.querySelector('.nav-item[data-tab="' + tab + '"]');
  if (nav) nav.classList.add('active');
}
function runCron(id) {
  fetch('/api/cron/run/' + id, {method: 'POST'})
    .then(r => r.json()).then(d => alert(d.message || 'Triggered'));
}
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    const el = event.target;
    el.textContent = 'Copied!';
    setTimeout(() => el.textContent = 'Copy', 1500);
  });
}
// Auto-detect Telegram chat ID
async function fetchChatId() {
  const token = document.getElementById('bot_token')?.value;
  if (!token || token.length < 20) { alert('Enter bot token first'); return; }
  try {
    const resp = await fetch(`https://api.telegram.org/bot${token}/getUpdates`);
    const data = await resp.json();
    if (data.result?.length > 0) {
      const msg = data.result[data.result.length - 1];
      const chatId = msg.message?.chat?.id || msg.callback_query?.message?.chat?.id;
      if (chatId) {
        document.getElementById('telegram_chat_id').value = chatId;
        document.getElementById('chat_id_hint').textContent = 'Auto-detected: ' + chatId;
      } else { alert('No messages found. Send any message to your bot first.'); }
    } else { alert('No updates found. Send /start to your bot first.'); }
  } catch(e) { alert('Error: ' + e.message); }
}
</script>
"""

def sidebar(active_tab: str = "overview") -> str:
    configured = is_openclaw_configured()
    daemon_status = openclaw_status() if configured else {"running": False}
    dot = "dot-green" if daemon_status["running"] else "dot-red"
    status_label = "Running" if daemon_status["running"] else "Stopped"

    tabs = [
        ("overview", "Overview", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>"""),
        ("agents", "Agents", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>"""),
        ("cron", "Cron Jobs", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>"""),
        ("recruiter", "Recruiter", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/><rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/></svg>"""),
        ("memory", "Memory", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>"""),
        ("costs", "Costs", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>"""),
        ("setup", "Setup Wizard", """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>"""),
    ]

    nav_html = ""
    for tab_id, label, icon in tabs:
        cls = "active" if tab_id == active_tab else ""
        nav_html += f'<div class="nav-item {cls}" data-tab="{tab_id}" onclick="setTab(\'{tab_id}\')">{icon} {label}</div>'

    return f"""
<div class="sidebar">
  <div class="sidebar-logo">
    <h2>🦞 OpenClaw</h2>
    <span>Workspace Dashboard</span>
  </div>
  <nav class="nav">{nav_html}</nav>
  <div class="sidebar-footer">
    <span class="status-dot {dot}"></span>
    <span style="font-size:12px;color:var(--muted)">Daemon: {status_label}</span>
  </div>
</div>
"""

def shell(html: str, active_tab: str = "overview") -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenClaw Workspace</title>
{SHARED_CSS}
</head>
<body>
<div class="app">
  {sidebar(active_tab)}
  <main class="main">
    {html}
  </main>
</div>
{SIDEBAR_JS}
</body>
</html>""")

# ── OVERVIEW TAB ───────────────────────────────────────────
def render_overview() -> str:
    configured = is_openclaw_configured()
    daemon = openclaw_status() if configured else {"running": False}
    agents = openclaw_agents() if configured else []
    cron_jobs = openclaw_cron()
    costs = get_cost_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_log = get_today_log()

    # Stats
    total_cost = costs.get("totalCostUSD", 0)
    sessions = costs.get("sessions", [])
    today_sessions = [s for s in sessions if s.get("timestamp","").startswith(today)]
    today_cost = sum(s.get("costUSD",0) for s in today_sessions)
    active_crons = sum(1 for j in cron_jobs if isinstance(j, dict) and j.get("enabled", True))

    # BeReach status
    bereach_cfg = OPENCLAW_DIR / "workspace" / "config" / "bereach.json"
    bereach_ok = bereach_cfg.exists() and "brc_" in bereach_cfg.read_text() if bereach_cfg.exists() else False

    # Placeholders check
    oc_json_path = OPENCLAW_DIR / "openclaw.json"
    has_placeholders = False
    if oc_json_path.exists():
        content = oc_json_path.read_text()
        has_placeholders = "{{" in content

    notice = ""
    if not configured:
        notice = '<div class="notice notice-yellow">⚠️ OpenClaw not configured. Use the Setup Wizard to get started.</div>'
    elif has_placeholders:
        notice = '<div class="notice notice-yellow">⚠️ openclaw.json still has unsubstituted {{PLACEHOLDER}} values. Complete setup first.</div>'
    elif not daemon["running"]:
        notice = '<div class="notice notice-red">🔴 OpenClaw daemon is not running. Run: <code class="inline-code">openclaw start</code></div>'

    agent_count = len(agents) if agents else "—"
    daemon_badge = '<span class="badge badge-green">Running</span>' if daemon["running"] else '<span class="badge badge-red">Stopped</span>'
    bereach_badge = '<span class="badge badge-green">Connected</span>' if bereach_ok else '<span class="badge badge-muted">Not configured</span>'

    # Quick actions
    recent_log_html = f'<div class="log-box">{today_log or "No activity logged today yet."}</div>'

    return f"""
<div class="page-header">
  <h1>Overview</h1>
  <p>Live status of your OpenClaw workspace — {datetime.now().strftime("%A, %B %d %Y")}</p>
</div>

{notice}

<div class="grid-4" style="margin-bottom:20px">
  <div class="card card-sm">
    <div class="label">Daemon</div>
    {daemon_badge}
  </div>
  <div class="card card-sm">
    <div class="label">Agents</div>
    <div class="stat"><span class="num">{agent_count}</span><span class="desc">registered</span></div>
  </div>
  <div class="card card-sm">
    <div class="label">Cron Jobs</div>
    <div class="stat"><span class="num">{active_crons}</span><span class="desc">active jobs</span></div>
  </div>
  <div class="card card-sm">
    <div class="label">Today's Cost</div>
    <div class="stat"><span class="num">${today_cost:.4f}</span><span class="desc">USD ({len(today_sessions)} sessions)</span></div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="label">System Status</div>
    <table>
      <tr><td>OpenClaw daemon</td><td>{daemon_badge}</td></tr>
      <tr><td>Config path</td><td><code class="inline-code">{OPENCLAW_DIR}</code></td></tr>
      <tr><td>BeReach API</td><td>{bereach_badge}</td></tr>
      <tr><td>Total AI cost</td><td><span style="color:var(--purple-light)">${total_cost:.4f} USD</span></td></tr>
    </table>
    <div class="btn-row" style="margin-top:16px">
      <button class="btn btn-ghost btn-sm" onclick="window.location.reload()">↻ Refresh</button>
      <button class="btn btn-green btn-sm" onclick="runCron('agent-doctor')">Run Doctor Check</button>
    </div>
  </div>

  <div class="card">
    <div class="label">Today's Activity</div>
    {recent_log_html}
  </div>
</div>

<div class="card">
  <div class="label">Quick Actions</div>
  <div class="btn-row" style="flex-wrap:wrap;gap:10px">
    <button class="btn btn-ghost btn-sm" onclick="setTab('agents')">👁 View Agents</button>
    <button class="btn btn-ghost btn-sm" onclick="setTab('cron')">⏱ Manage Cron</button>
    <button class="btn btn-ghost btn-sm" onclick="setTab('recruiter')">🔗 LinkedIn Recruiter</button>
    <button class="btn btn-ghost btn-sm" onclick="setTab('memory')">🧠 View Memory</button>
    <button class="btn btn-ghost btn-sm" onclick="setTab('costs')">💰 Cost Report</button>
    <button class="btn btn-primary btn-sm" onclick="setTab('setup')">⚙ Setup Wizard</button>
  </div>
</div>
"""

# ── AGENTS TAB ─────────────────────────────────────────────
def render_agents() -> str:
    oc_path = OPENCLAW_DIR / "openclaw.json"
    agent_list = []
    if oc_path.exists():
        try:
            cfg = json.loads(oc_path.read_text())
            agent_list = cfg.get("agents", {}).get("list", [])
        except Exception:
            pass

    core_agents = [a for a in agent_list if not a.get("_comment","").startswith("Creative") and not a.get("_comment","").startswith("Development")]
    sub_creative = [a for a in agent_list if "creative" in str(a.get("agentDir","")).lower()]
    sub_dev = [a for a in agent_list if "development" in str(a.get("agentDir","")).lower()]

    def agent_row(a):
        aid = a.get("id","?")
        name = a.get("name", aid)
        model = a.get("model","—")
        model_short = model.split("/")[-1] if "/" in model else model
        soul_path = Path(a.get("agentDir","").replace("agent","").rstrip("/")) / "SOUL.md"
        has_soul = "✓" if soul_path.exists() else "✗"
        return f"""<tr>
          <td><strong>{name}</strong></td>
          <td><code class="inline-code" style="font-size:11px">{model_short}</code></td>
          <td><span class="badge badge-{'green' if has_soul == '✓' else 'red'}">{has_soul} SOUL.md</span></td>
          <td><span class="badge badge-purple">{aid}</span></td>
        </tr>"""

    core_html = "".join(agent_row(a) for a in core_agents) if core_agents else "<tr><td colspan=4 style='color:var(--muted)'>No agents configured — run Setup Wizard</td></tr>"
    creative_html = "".join(f'<div class="agent-card"><h4>{a.get("name",a.get("id"))}</h4><p class="model">{a.get("model","").split("/")[-1]}</p></div>' for a in sub_creative)
    dev_html = "".join(f'<div class="agent-card"><h4>{a.get("name",a.get("id"))}</h4><p class="model">{a.get("model","").split("/")[-1]}</p></div>' for a in sub_dev)

    return f"""
<div class="page-header">
  <h1>Agents</h1>
  <p>{len(agent_list)} agents total — {len(core_agents)} core · {len(sub_creative)} creative · {len(sub_dev)} development</p>
</div>

<div class="card">
  <div class="label">Core Agents</div>
  <table>
    <tr><th>Name</th><th>Model</th><th>Identity</th><th>ID</th></tr>
    {core_html}
  </table>
</div>

<div class="card">
  <div class="label">Creative Sub-Agents ({len(sub_creative)})</div>
  <div class="agent-grid">{creative_html or '<p style="color:var(--muted);font-size:13px">None registered</p>'}</div>
</div>

<div class="card">
  <div class="label">Development Sub-Agents ({len(sub_dev)})</div>
  <div class="agent-grid">{dev_html or '<p style="color:var(--muted);font-size:13px">None registered</p>'}</div>
</div>
"""

# ── CRON TAB ───────────────────────────────────────────────
def render_cron() -> str:
    jobs = openclaw_cron()
    if not jobs:
        return """
<div class="page-header"><h1>Cron Jobs</h1></div>
<div class="card"><p style="color:var(--muted)">No cron jobs found. Check cron/jobs.json exists.</p></div>"""

    rows = ""
    for j in jobs:
        if not isinstance(j, dict) or j.get("_comment"):
            continue
        jid = j.get("id","?")
        name = j.get("name","?")
        schedule = j.get("schedule","?")
        agent = j.get("agent","?")
        enabled = j.get("enabled", True)
        model = j.get("payload",{}).get("model","—").split("/")[-1]
        en_badge = '<span class="badge badge-green">Active</span>' if enabled else '<span class="badge badge-muted">Disabled</span>'
        rows += f"""<tr>
          <td><strong>{name}</strong><br><span style="color:var(--muted);font-size:11px">{jid}</span></td>
          <td><code class="inline-code" style="font-size:11px">{schedule}</code></td>
          <td>{agent}</td>
          <td><span style="font-size:11px;color:var(--purple-light)">{model}</span></td>
          <td>{en_badge}</td>
          <td><button class="btn btn-ghost btn-sm" onclick="runCron('{jid}')">▶ Run now</button></td>
        </tr>"""

    return f"""
<div class="page-header">
  <h1>Cron Jobs</h1>
  <p>{len([j for j in jobs if isinstance(j,dict) and not j.get('_comment')])} scheduled jobs</p>
</div>
<div class="card">
  <table>
    <tr><th>Job</th><th>Schedule</th><th>Agent</th><th>Model</th><th>Status</th><th>Action</th></tr>
    {rows}
  </table>
</div>
<div class="notice notice-blue">
  💡 Edit cron/jobs.json to change schedules. Run <code class="inline-code">openclaw restart</code> to apply changes.
</div>
"""

# ── RECRUITER TAB ─────────────────────────────────────────
def render_recruiter() -> str:
    cfg_path = OPENCLAW_DIR / "workspace" / "config" / "bereach.json"
    pipeline_path = OPENCLAW_DIR / "workspace" / "recruiter" / "pipeline.json"
    log_path = OPENCLAW_DIR / "workspace" / "logs" / f"bereach-{datetime.now().strftime('%Y-%m-%d')}.log"

    bereach_key = ""
    if cfg_path.exists():
        try:
            bereach_key = json.loads(cfg_path.read_text()).get("apiKey","")
        except Exception:
            pass

    is_configured = bereach_key.startswith("brc_") and bereach_key != "BEREACH_API_KEY_HERE"

    pipeline = []
    if pipeline_path.exists():
        try:
            pipeline = json.loads(pipeline_path.read_text())
        except Exception:
            pass

    from collections import Counter
    status_counts = Counter(c.get("status","unknown") for c in pipeline) if pipeline else {}

    log_content = read_text_safe(log_path, max_lines=40) if log_path.exists() else "No activity logged today."

    status_html = "".join(f'<tr><td>{s}</td><td><strong>{c}</strong></td></tr>' for s,c in sorted(status_counts.items()))
    pipeline_total = len(pipeline)

    if not is_configured:
        setup_notice = """
<div class="notice notice-yellow">
  ⚠️ BeReach API not configured.
  <ol style="margin-top:8px;padding-left:20px;line-height:2">
    <li>Get your free API key at <a href="https://berea.ch/account" target="_blank">berea.ch/account</a></li>
    <li>Save to <code class="inline-code">workspace/config/bereach.json</code>: <code class="inline-code">{"apiKey": "brc_..."}</code></li>
    <li>The recruiter agent is ready — enable its cron jobs in cron/jobs.json</li>
  </ol>
</div>"""
    else:
        setup_notice = '<div class="notice notice-green">✓ BeReach API configured — key starts with brc_...</div>'

    key_masked = (bereach_key[:10] + "..." + bereach_key[-6:]) if len(bereach_key) > 20 else bereach_key

    limits_display = """
<div style="color:var(--muted);font-size:12px">
Check limits: <code class="inline-code">bash workspace/scripts/bereach.sh limits</code>
</div>"""

    return f"""
<div class="page-header">
  <h1>LinkedIn Recruiter</h1>
  <p>Autonomous LinkedIn outreach powered by BeReach API</p>
</div>

{setup_notice}

<div class="grid-2">
  <div class="card">
    <div class="label">API Status</div>
    <table>
      <tr><td>API Key</td><td><code class="inline-code" style="font-size:11px">{key_masked or 'Not set'}</code></td></tr>
      <tr><td>Daily connections</td><td>30 / day · 200 / week</td></tr>
      <tr><td>Daily messages</td><td>100 / day · 400 / week</td></tr>
      <tr><td>Profile visits</td><td>350 / day</td></tr>
      <tr><td>Scraping</td><td>300 / day</td></tr>
    </table>
    {limits_display}
  </div>

  <div class="card">
    <div class="label">Pipeline Summary ({pipeline_total} candidates)</div>
    {'<table><tr><th>Status</th><th>Count</th></tr>' + status_html + '</table>' if pipeline else '<p style="color:var(--muted);font-size:13px">No pipeline data yet. Run a search to populate.</p>'}
  </div>
</div>

<div class="card">
  <div class="label">CLI Quick Reference</div>
  <pre>
# Check limits
bash workspace/scripts/bereach.sh limits

# Search candidates
bash workspace/scripts/bereach.sh search-people \\
  --title "Senior Engineer" --location "Kuala Lumpur" --limit 20

# Visit and validate a profile
bash workspace/scripts/bereach.sh visit-profile --url "https://linkedin.com/in/username"

# Connect with personalized note
bash workspace/scripts/bereach.sh connect \\
  --url "https://linkedin.com/in/username" \\
  --message "Hi Sarah, noticed your work at Grab — let's connect."

# Check inbox for replies
bash workspace/scripts/bereach.sh inbox --limit 30
  </pre>
</div>

<div class="card">
  <div class="label">Today's Recruiter Log</div>
  <div class="log-box">{log_content}</div>
</div>

<div class="card">
  <div class="label">Autonomous Agent Controls</div>
  <p style="color:var(--muted);font-size:13px;margin-bottom:16px">
    The recruiter agent runs automatically via cron. Enable the jobs below to activate.
  </p>
  <div class="btn-row">
    <button class="btn btn-green btn-sm" onclick="runCron('recruiter-morning-sweep')">▶ Run Morning Sweep</button>
    <button class="btn btn-ghost btn-sm" onclick="runCron('recruiter-weekly-report')">📊 Weekly Report</button>
    <button class="btn btn-ghost btn-sm" onclick="setTab('cron')">⏱ Manage Cron Jobs</button>
  </div>
</div>
"""

# ── MEMORY TAB ────────────────────────────────────────────
def render_memory() -> str:
    memory_content = get_memory()
    today_log = get_today_log()
    today = datetime.now().strftime("%Y-%m-%d")

    # List recent memory files
    mem_dir = OPENCLAW_DIR / "workspace" / "memory"
    recent_files = []
    if mem_dir.exists():
        recent_files = sorted(mem_dir.glob("*.md"), reverse=True)[:7]

    file_links = "".join(f'<div style="font-size:12px;color:var(--muted);padding:4px 0">{f.name} · {f.stat().st_size} bytes</div>' for f in recent_files)

    return f"""
<div class="page-header">
  <h1>Memory</h1>
  <p>Agent knowledge base — curated facts, rules, and session logs</p>
</div>

<div class="grid-2">
  <div class="card">
    <div class="label">Long-term Memory (MEMORY.md)</div>
    <div class="log-box">{memory_content or 'MEMORY.md is empty or not found.'}</div>
  </div>
  <div class="card">
    <div class="label">Today's Session ({today})</div>
    <div class="log-box">{today_log or 'No session activity logged today yet.'}</div>
  </div>
</div>

<div class="card">
  <div class="label">Recent Memory Files</div>
  {file_links or '<p style="color:var(--muted);font-size:13px">No memory files found at workspace/memory/</p>'}
  <div class="notice notice-blue" style="margin-top:12px">
    Memory files at <code class="inline-code">workspace/memory/YYYY-MM-DD.md</code>.
    Long-term memory at <code class="inline-code">workspace/MEMORY.md</code> (max 200 lines).
    Run <code class="inline-code">openclaw cron run weekly-memory-compaction</code> to compact.
  </div>
</div>
"""

# ── COSTS TAB ─────────────────────────────────────────────
def render_costs() -> str:
    data = get_cost_data()
    total = data.get("totalCostUSD", 0)
    sessions = data.get("sessions", [])
    by_agent = data.get("byAgent", {})
    by_model = data.get("byModel", {})
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    today_sessions = [s for s in sessions if s.get("timestamp","").startswith(today)]
    month_sessions = [s for s in sessions if s.get("timestamp","").startswith(month)]
    today_cost = sum(s.get("costUSD",0) for s in today_sessions)
    month_cost = sum(s.get("costUSD",0) for s in month_sessions)

    agent_rows = "".join(f'<tr><td>{a}</td><td>{s.get("sessions",0)}</td><td>${s.get("totalCostUSD",0):.4f}</td></tr>' for a,s in sorted(by_agent.items(), key=lambda x: x[1].get("totalCostUSD",0), reverse=True))
    model_rows = "".join(f'<tr><td><code class="inline-code" style="font-size:11px">{m}</code></td><td>{s.get("sessions",0)}</td><td>${s.get("totalCostUSD",0):.4f}</td></tr>' for m,s in sorted(by_model.items(), key=lambda x: x[1].get("totalCostUSD",0), reverse=True))
    recent_rows = "".join(f'<tr><td>{s.get("agent","")}</td><td>{s.get("model","").split("/")[-1]}</td><td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{s.get("task","")[:40]}</td><td>${s.get("costUSD",0):.6f}</td></tr>' for s in sessions[-10:])

    if not data:
        return '<div class="card"><p style="color:var(--muted)">No cost tracking data. Run: <code class="inline-code">bash workspace/scripts/cost-tracker.sh init</code></p></div>'

    return f"""
<div class="page-header">
  <h1>Cost Tracking</h1>
  <p>AI API spend by agent, model, and task</p>
</div>

<div class="grid-3" style="margin-bottom:20px">
  <div class="card card-sm">
    <div class="label">Today</div>
    <div class="stat"><span class="num">${today_cost:.4f}</span><span class="desc">{len(today_sessions)} sessions</span></div>
  </div>
  <div class="card card-sm">
    <div class="label">This Month</div>
    <div class="stat"><span class="num">${month_cost:.4f}</span><span class="desc">{len(month_sessions)} sessions</span></div>
  </div>
  <div class="card card-sm">
    <div class="label">All Time</div>
    <div class="stat"><span class="num">${total:.4f}</span><span class="desc">{len(sessions)} total sessions</span></div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="label">By Agent</div>
    <table><tr><th>Agent</th><th>Sessions</th><th>Cost</th></tr>{agent_rows or '<tr><td colspan=3 style="color:var(--muted)">No data</td></tr>'}</table>
  </div>
  <div class="card">
    <div class="label">By Model</div>
    <table><tr><th>Model</th><th>Sessions</th><th>Cost</th></tr>{model_rows or '<tr><td colspan=3 style="color:var(--muted)">No data</td></tr>'}</table>
  </div>
</div>

<div class="card">
  <div class="label">Recent Sessions (last 10)</div>
  <table><tr><th>Agent</th><th>Model</th><th>Task</th><th>Cost</th></tr>{recent_rows or '<tr><td colspan=4 style="color:var(--muted)">No sessions logged yet</td></tr>'}</table>
</div>

<div class="notice notice-blue">
  Log a session: <code class="inline-code">bash workspace/scripts/cost-tracker.sh log &lt;agent&gt; &lt;model&gt; &lt;in_tokens&gt; &lt;out_tokens&gt; "task"</code>
</div>
"""

# ── SETUP WIZARD ──────────────────────────────────────────
WIZARD_STEPS = ["identity", "telegram", "keys", "linkedin", "recruiter", "review", "done"]

def wizard_bar(current: str) -> str:
    idx = WIZARD_STEPS.index(current) if current in WIZARD_STEPS else 0
    return "".join(f'<div class="progress-step {"done" if i < idx else "active" if i == idx else ""}"></div>' for i in range(len(WIZARD_STEPS)))

def render_setup(step: str = "identity", data: dict = {}, message: str = "") -> str:
    bar = wizard_bar(step)
    msg_html = f'<div class="notice notice-green">{message}</div>' if message else ""

    if step == "identity":
        body = f"""
<form method="post" action="/setup/identity">
  <div class="form-group"><label>Your Full Name</label>
    <input type="text" name="your_name" value="{data.get('your_name','')}" placeholder="Alex Johnson" required></div>
  <div class="form-group"><label>Company / Project Name</label>
    <input type="text" name="your_company" value="{data.get('your_company','')}" placeholder="Acme Corp" required></div>
  <div class="form-group"><label>Your Role / Title</label>
    <input type="text" name="your_role" value="{data.get('your_role','')}" placeholder="Founder & CEO" required></div>
  <div class="form-group"><label>Your Handle (no @)</label>
    <input type="text" name="your_handle" value="{data.get('your_handle','')}" placeholder="alexj"></div>
  <div class="form-group"><label>Your Email</label>
    <input type="email" name="your_email" value="{data.get('your_email','')}" placeholder="alex@acme.com"></div>
  <div class="form-group"><label>Timezone</label>
    <select name="your_timezone">
      {"".join(f'<option value="{tz}" {"selected" if data.get("your_timezone")==tz else ""}>{label}</option>' for tz, label in [
        ("Asia/Kuala_Lumpur","Asia/Kuala_Lumpur (MYT +8)"),
        ("America/New_York","America/New_York (ET)"),
        ("America/Los_Angeles","America/Los_Angeles (PT)"),
        ("America/Chicago","America/Chicago (CT)"),
        ("Europe/London","Europe/London (GMT)"),
        ("Europe/Berlin","Europe/Berlin (CET)"),
        ("Asia/Singapore","Asia/Singapore (SGT +8)"),
        ("Asia/Tokyo","Asia/Tokyo (JST +9)"),
        ("Asia/Dubai","Asia/Dubai (GST +4)"),
        ("Australia/Sydney","Australia/Sydney (AEST)"),
        ("UTC","UTC"),
      ])}
    </select></div>
  <div class="form-group"><label>Main Agent Name</label>
    <input type="text" name="agent_name" value="{data.get('agent_name','Atlas')}" placeholder="Atlas, Sage, Vance...">
    <div class="hint">What your main AI agent is called</div></div>
  <div class="btn-row" style="margin-top:24px">
    <div></div>
    <button type="submit" class="btn btn-primary">Next: Telegram →</button>
  </div>
</form>"""
    elif step == "telegram":
        body = f"""
<form method="post" action="/setup/telegram">
  <div class="notice notice-blue">
    Create a Telegram bot: message <strong>@BotFather</strong> → /newbot → copy the token
  </div>
  <div class="form-group"><label>Telegram Bot Token</label>
    <input id="bot_token" type="text" name="telegram_bot_token" value="{data.get('telegram_bot_token','')}" placeholder="1234567890:AABB..." required></div>
  <div class="form-group"><label>Your Telegram Chat ID</label>
    <input id="telegram_chat_id" type="text" name="telegram_chat_id" value="{data.get('telegram_chat_id','')}" placeholder="1234567890" required>
    <div class="hint" id="chat_id_hint">
      Send any message to your bot, then
      <button type="button" onclick="fetchChatId()" style="background:none;border:none;color:var(--purple-light);cursor:pointer;font-size:12px;padding:0">
        Auto-detect →
      </button>
      or message @userinfobot
    </div></div>
  <div class="btn-row" style="margin-top:24px">
    <button type="button" class="btn btn-ghost" onclick="setTab('setup'); document.getElementById('tab-setup').innerHTML = ''">← Back</button>
    <button type="submit" class="btn btn-primary">Next: API Keys →</button>
  </div>
</form>"""
    elif step == "keys":
        body = f"""
<form method="post" action="/setup/keys">
  <div class="notice notice-blue">Free models are zero-cost. Paid keys are optional.</div>
  <div class="form-group"><label>OpenCode Go API Key <span class="badge badge-green">Free</span></label>
    <input type="text" name="opencode_api_key" value="{data.get('opencode_api_key','')}" placeholder="your opencode api key">
    <div class="hint">From opencode.ai — powers kimi-k2.5, glm-5, minimax-m2.5</div></div>
  <div class="section-sep">MCP Integrations</div>
  <div class="form-group"><label>Composio API Key <span class="badge badge-purple">Gmail · Drive · Calendar</span></label>
    <input type="text" name="composio_api_key" value="{data.get('composio_api_key','')}" placeholder="ck_xxx...">
    <div class="hint">From app.composio.dev</div></div>
  <div class="form-group"><label>Supabase Project Ref</label>
    <input type="text" name="supabase_project_ref" value="{data.get('supabase_project_ref','')}" placeholder="lrwzlujomukzjykafmic">
    <div class="hint">From app.supabase.com → Project Settings</div></div>
  <div class="section-sep">Optional Paid</div>
  <div class="form-group"><label>Anthropic API Key <span class="badge badge-yellow">Paid — Claude agents</span></label>
    <input type="text" name="anthropic_api_key" value="{data.get('anthropic_api_key','')}" placeholder="sk-ant-...">
    <div class="hint">For claude-automation + claude-code-agent only</div></div>
  <div class="btn-row" style="margin-top:24px">
    <div></div>
    <button type="submit" class="btn btn-primary">Next: LinkedIn →</button>
  </div>
</form>"""
    elif step == "linkedin":
        body = f"""
<form method="post" action="/setup/linkedin">
  <div class="form-group"><label>PostIz API Key <span class="badge badge-purple">LinkedIn auto-posting</span></label>
    <input type="text" name="postiz_api_key" value="{data.get('postiz_api_key','')}" placeholder="pz_xxx...">
    <div class="hint">From app.postiz.com → Settings → API Key</div></div>
  <div class="form-group"><label>LinkedIn Personal Channel ID</label>
    <input type="text" name="postiz_personal_channel" value="{data.get('postiz_personal_channel','')}" placeholder="from PostIz Channels"></div>
  <div class="form-group"><label>LinkedIn Brand Channel ID <span style="color:var(--muted);font-size:11px">(optional)</span></label>
    <input type="text" name="postiz_brand_channel" value="{data.get('postiz_brand_channel','')}" placeholder="second LinkedIn account"></div>
  <div class="btn-row" style="margin-top:24px">
    <div></div>
    <button type="submit" class="btn btn-primary">Next: Recruiter →</button>
  </div>
</form>"""
    elif step == "recruiter":
        body = f"""
<form method="post" action="/setup/recruiter">
  <div class="notice notice-blue">
    BeReach powers autonomous LinkedIn recruiting — free tier included.
    Get your key at <a href="https://berea.ch/account" target="_blank">berea.ch/account</a>
  </div>
  <div class="form-group"><label>BeReach API Key <span class="badge badge-green">Free tier</span></label>
    <input type="text" name="bereach_api_key" value="{data.get('bereach_api_key','')}" placeholder="brc_...">
    <div class="hint">30 connections/day · 100 messages/day · 350 profile visits/day — all free</div></div>
  <div class="form-group"><label>Enable Recruiter Morning Sweep (08:00 Mon–Fri)</label>
    <select name="enable_recruiter_cron">
      <option value="no" {"selected" if data.get("enable_recruiter_cron")=="no" else ""}>No — I'll trigger manually</option>
      <option value="yes" {"selected" if data.get("enable_recruiter_cron")=="yes" else ""}>Yes — run automatically every weekday</option>
    </select></div>
  <div class="btn-row" style="margin-top:24px">
    <div></div>
    <button type="submit" class="btn btn-primary">Next: Review →</button>
  </div>
</form>"""
    elif step == "review":
        # Show summary and generate button
        rows = [
            ("Name", data.get("your_name","—")),
            ("Company", data.get("your_company","—")),
            ("Timezone", data.get("your_timezone","—")),
            ("Agent Name", data.get("agent_name","—")),
            ("Telegram Bot", "✓ Set" if data.get("telegram_bot_token") else "✗ Missing"),
            ("Chat ID", data.get("telegram_chat_id","—")),
            ("OpenCode Go", "✓ Set" if data.get("opencode_api_key") else "✗ Not set"),
            ("Composio", "✓ Set" if data.get("composio_api_key") else "— Skipped"),
            ("PostIz", "✓ Set" if data.get("postiz_api_key") else "— Skipped"),
            ("BeReach", "✓ Set" if data.get("bereach_api_key","").startswith("brc_") else "— Skipped"),
            ("Anthropic", "✓ Set" if data.get("anthropic_api_key") else "— Skipped"),
        ]
        table = "".join(f"<tr><td style='color:var(--muted);width:180px'>{k}</td><td><strong>{v}</strong></td></tr>" for k,v in rows)
        body = f"""
<table style="margin-bottom:24px">{table}</table>
<div class="notice notice-blue" style="margin-bottom:20px">
  Clicking Install will write all config files to <code class="inline-code">{OPENCLAW_DIR}</code> and attempt to restart OpenClaw.
</div>
<form method="post" action="/setup/install">
  <input type="hidden" name="confirmed" value="yes">
  <div class="btn-row">
    <div></div>
    <button type="submit" class="btn btn-primary">⚡ Install Now</button>
  </div>
</form>"""
    elif step == "done":
        body = f"""
<div class="notice notice-green" style="margin-bottom:20px">
  ✅ Installation complete! Your OpenClaw workspace is ready.
</div>
<pre>Installed to: {OPENCLAW_DIR}

Next steps:
1. openclaw restart
2. openclaw agents list
3. openclaw cron list
4. Send a message to your Telegram bot
5. bash workspace/scripts/doctor.sh
</pre>
<div class="btn-row" style="margin-top:20px">
  <button class="btn btn-primary" onclick="setTab('overview')">Go to Dashboard →</button>
</div>"""
    else:
        body = f'<p>Unknown step: {step}</p>'

    step_labels = {"identity":"Identity","telegram":"Telegram","keys":"API Keys","linkedin":"LinkedIn","recruiter":"Recruiter","review":"Review","done":"Done"}
    label = step_labels.get(step, step.title())

    return f"""
<div class="page-header">
  <h1>Setup Wizard — {label}</h1>
  <p>Step {WIZARD_STEPS.index(step)+1 if step in WIZARD_STEPS else '?'} of {len(WIZARD_STEPS)}</p>
</div>
<div class="progress-bar">{bar}</div>
{msg_html}
<div class="card">
  {body}
</div>
"""

# ── MAIN PAGE ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(session_id: Optional[str] = Cookie(None)):
    tabs = f"""
<div id="tab-overview" class="tab-content">{render_overview()}</div>
<div id="tab-agents" class="tab-content" style="display:none">{render_agents()}</div>
<div id="tab-cron" class="tab-content" style="display:none">{render_cron()}</div>
<div id="tab-recruiter" class="tab-content" style="display:none">{render_recruiter()}</div>
<div id="tab-memory" class="tab-content" style="display:none">{render_memory()}</div>
<div id="tab-costs" class="tab-content" style="display:none">{render_costs()}</div>
<div id="tab-setup" class="tab-content" style="display:none">{render_setup("identity")}</div>
<script>
// Set first tab based on URL hash
const hash = window.location.hash.replace('#','') || 'overview';
setTab(hash);
document.querySelectorAll('.nav-item').forEach(el => {{
  el.addEventListener('click', () => {{
    window.location.hash = el.dataset.tab;
  }});
}});
</script>
"""
    return shell(tabs, "overview")

# ── SETUP WIZARD ROUTES ───────────────────────────────────
@app.get("/setup/{step}", response_class=HTMLResponse)
async def get_setup_step(step: str, session_id: Optional[str] = Cookie(None)):
    data = get_session(session_id)
    content = render_setup(step, data)
    tabs = build_tabs_with_active("setup", content)
    return shell(tabs, "setup")

@app.post("/setup/{step}", response_class=HTMLResponse)
async def post_setup_step(step: str, request: Request, session_id: Optional[str] = Cookie(None)):
    form = dict(await request.form())

    # Create or retrieve session
    if not session_id or session_id not in SESSIONS:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = {}

    # Merge form data into session
    SESSIONS[session_id].update(form)
    data = SESSIONS[session_id]

    # Advance to next step
    next_map = {
        "identity": "telegram", "telegram": "keys", "keys": "linkedin",
        "linkedin": "recruiter", "recruiter": "review"
    }
    next_step = next_map.get(step, "review")

    if step == "review" or form.get("confirmed"):
        # Actually write config files
        msg = install_config(data)
        next_step = "done"
        content = render_setup(next_step, data, msg)
    else:
        content = render_setup(next_step, data)

    tabs = build_tabs_with_active("setup", content)
    response = shell(tabs, "setup")
    if isinstance(response, HTMLResponse):
        response.set_cookie("session_id", session_id, max_age=3600)
    return response

def build_tabs_with_active(active: str, active_content: str) -> str:
    tab_renders = {
        "overview": render_overview,
        "agents": render_agents,
        "cron": render_cron,
        "recruiter": render_recruiter,
        "memory": render_memory,
        "costs": render_costs,
    }
    html = ""
    for tab_id, fn in tab_renders.items():
        display = "block" if tab_id == active else "none"
        try:
            content = fn() if tab_id != active else fn()
        except Exception:
            content = "<p>Error loading tab</p>"
        html += f'<div id="tab-{tab_id}" class="tab-content" style="display:{display}">{content}</div>'
    html += f'<div id="tab-setup" class="tab-content" style="display:{"block" if active=="setup" else "none"}">{active_content}</div>'
    html += f"""<script>
const hash = window.location.hash.replace('#','') || '{active}';
setTab(hash);
document.querySelectorAll('.nav-item').forEach(el => {{
  el.addEventListener('click', () => window.location.hash = el.dataset.tab);
}});
</script>"""
    return html

# ── CONFIG INSTALLER ──────────────────────────────────────
def install_config(data: dict) -> str:
    msgs = []
    try:
        OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "workspace" / "config").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "workspace" / "scripts").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "workspace" / "memory").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "workspace" / "ops").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "workspace" / "recruiter").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "cron").mkdir(parents=True, exist_ok=True)
        (OPENCLAW_DIR / "config").mkdir(parents=True, exist_ok=True)

        # Generate openclaw.json from template
        tpl = TEMPLATE_DIR / "openclaw.json.template"
        if tpl.exists():
            content = tpl.read_text()
            replacements = {
                "{{OPENCLAW_DIR}}": str(OPENCLAW_DIR),
                "{{TELEGRAM_BOT_TOKEN}}": data.get("telegram_bot_token",""),
                "{{TELEGRAM_CHAT_ID}}": data.get("telegram_chat_id",""),
                "{{COMPOSIO_API_KEY}}": data.get("composio_api_key",""),
                "{{SUPABASE_PROJECT_REF}}": data.get("supabase_project_ref",""),
                "{{OPENCODE_GO_API_KEY}}": data.get("opencode_api_key",""),
                "{{ANTHROPIC_API_KEY}}": data.get("anthropic_api_key",""),
                "{{GOOGLE_AI_API_KEY}}": "",
                "{{OPENAI_API_KEY}}": "",
                "{{GOOGLECHAT_AUDIENCE_URL}}": "",
                "{{TIMEZONE}}": data.get("your_timezone","UTC"),
                "{{PERSONA_NAME}}": data.get("agent_name","NOVA"),
                "{{INSTALL_DATE}}": datetime.utcnow().isoformat() + "Z",
            }
            for k, v in replacements.items():
                content = content.replace(k, v)
            (OPENCLAW_DIR / "openclaw.json").write_text(content)
            msgs.append("✓ openclaw.json generated")

        # Generate cron jobs
        cron_tpl = TEMPLATE_DIR / "cron" / "jobs.template.json"
        if cron_tpl.exists():
            content = cron_tpl.read_text().replace("{{TELEGRAM_CHAT_ID}}", data.get("telegram_chat_id",""))
            if data.get("enable_recruiter_cron") == "yes":
                content = content.replace('"id": "recruiter-morning-sweep",\n    "enabled": false', '"id": "recruiter-morning-sweep",\n    "enabled": true')
            (OPENCLAW_DIR / "cron" / "jobs.json").write_text(content)
            msgs.append("✓ cron/jobs.json generated")

        # Write BeReach config
        if data.get("bereach_api_key","").startswith("brc_"):
            bereach_cfg = {"apiKey": data["bereach_api_key"], "baseUrl": "https://api.bereach.ai"}
            (OPENCLAW_DIR / "workspace" / "config" / "bereach.json").write_text(json.dumps(bereach_cfg, indent=2))
            msgs.append("✓ BeReach config saved")

        # Write PostIz config
        if data.get("postiz_api_key"):
            postiz_cfg = {
                "apiKey": data["postiz_api_key"],
                "baseUrl": "https://api.postiz.com/public/v1",
                "channels": {
                    "personal": data.get("postiz_personal_channel",""),
                    "brand": data.get("postiz_brand_channel","")
                }
            }
            (OPENCLAW_DIR / "workspace" / "config" / "postiz.json").write_text(json.dumps(postiz_cfg, indent=2))
            msgs.append("✓ PostIz config saved")

        # Copy agent files from template
        agents_src = TEMPLATE_DIR / "agents"
        agents_dst = OPENCLAW_DIR / "agents"
        if agents_src.exists():
            import shutil
            for src_file in agents_src.rglob("*.md"):
                rel = src_file.relative_to(agents_src)
                dst_file = agents_dst / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                content = src_file.read_text()
                for k, v in {
                    "{{YOUR_NAME}}": data.get("your_name",""),
                    "{{YOUR_COMPANY}}": data.get("your_company",""),
                    "{{YOUR_HANDLE}}": data.get("your_handle",""),
                    "{{YOUR_EMAIL}}": data.get("your_email",""),
                    "{{AGENT_NAME}}": data.get("agent_name","Atlas"),
                    "{{PERSONA_NAME}}": data.get("agent_name","NOVA"),
                    "{{TIMEZONE}}": data.get("your_timezone","UTC"),
                    "{{OPENCLAW_DIR}}": str(OPENCLAW_DIR),
                }.items():
                    content = content.replace(k, v)
                dst_file.write_text(content)
            msgs.append("✓ Agent files installed (SOUL.md, HEARTBEAT.md, TOOLS.md for all agents)")

        # Copy workspace scripts
        scripts_src = TEMPLATE_DIR / "workspace" / "scripts"
        scripts_dst = OPENCLAW_DIR / "workspace" / "scripts"
        if scripts_src.exists():
            scripts_dst.mkdir(parents=True, exist_ok=True)
            import shutil
            for f in scripts_src.glob("*.sh"):
                shutil.copy2(f, scripts_dst / f.name)
                (scripts_dst / f.name).chmod(0o755)
            msgs.append("✓ Workspace scripts installed")

        # Copy workspace MD files
        for fname in ["HEARTBEAT.md", "MEMORY.md", "OPERATIONS.md"]:
            src = TEMPLATE_DIR / "workspace" / fname
            if src.exists():
                (OPENCLAW_DIR / "workspace" / fname).write_text(src.read_text())

        # Copy mcporter config
        mcporter_tpl = TEMPLATE_DIR / "config" / "mcporter.json.template"
        if mcporter_tpl.exists():
            content = mcporter_tpl.read_text().replace("{{COMPOSIO_API_KEY}}", data.get("composio_api_key","")).replace("{{SUPABASE_PROJECT_REF}}", data.get("supabase_project_ref",""))
            (OPENCLAW_DIR / "config" / "mcporter.json").write_text(content)
            msgs.append("✓ MCP server config saved")

        # Copy AGENTS.md
        agents_md = TEMPLATE_DIR / "AGENTS.md"
        if agents_md.exists():
            (OPENCLAW_DIR / "AGENTS.md").write_text(agents_md.read_text())

        # Try openclaw restart
        out, err, code = run_cmd(["openclaw", "restart"], timeout=15)
        if code == 0:
            msgs.append("✓ OpenClaw restarted successfully")
        else:
            msgs.append("⚠ openclaw restart failed — run manually: openclaw restart")

    except Exception as e:
        msgs.append(f"✗ Error: {e}")

    return " · ".join(msgs)

# ── API ROUTES ────────────────────────────────────────────
@app.get("/api/status")
async def api_status():
    return JSONResponse({
        "daemon": openclaw_status(),
        "agents": len(openclaw_agents()),
        "cron_jobs": len(openclaw_cron()),
    })

@app.post("/api/cron/run/{job_id}")
async def api_run_cron(job_id: str):
    out, err, code = run_cmd(["openclaw", "cron", "run", job_id], timeout=30)
    return JSONResponse({"ok": code == 0, "message": out or err or f"Triggered: {job_id}"})

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "openclaw_dir": str(OPENCLAW_DIR)}

# ── MAIN ──────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8181))
    print(f"\n🦞 OpenClaw Workspace Dashboard v2.0")
    print(f"   Open: http://localhost:{PORT}")
    print(f"   OpenClaw dir: {OPENCLAW_DIR}")
    print(f"   Press Ctrl+C to stop\n")
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
