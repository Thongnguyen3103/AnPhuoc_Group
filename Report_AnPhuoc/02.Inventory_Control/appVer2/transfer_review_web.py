import io, os, sys, webbrowser, socket, subprocess, threading, time, urllib.parse, json
from pathlib import Path
from datetime import datetime, timedelta
import logging

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Silence Flask/Werkzeug request logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

_D = Path(__file__).resolve().parent
if str(_D) not in sys.path: sys.path.insert(0, str(_D))
os.chdir(_D)

import pandas as pd
import numpy as np
from flask import Flask, redirect, request, session, send_file, flash, Response, jsonify

from inventory_core import (
    load_users, check_password_hash, generate_password_hash, save_users,
    load_inventory, build_summary, load_transfer_orders, merge_transfer_with_review,
    update_review, recent_audit_rows, STATUS_LABELS, ROLE_LABELS, get_db_source, DATA_DIR,
    set_db_lock, is_db_rebuilding
)

app = Flask(__name__)
app.secret_key = "inv_key_premium_2026"
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

TRACKING_FILE = Path(r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Analysis_data\1.Processed_data\1.Data_Tracking.xlsx")

# Thread-safe pipeline logs
_pipeline_logs = []
_pipeline_running = False
_pipeline_progress = 0

def add_log(msg):
    _pipeline_logs.append(f"[{datetime.now():%H:%M:%S}] {msg}")
    print(f"[Pipeline] {msg}")

def user(): return session.get("u")
def is_admin(): return user() and user().get("role") == "admin"
def can_review(): return user() and user().get("role") in ("admin", "reviewer")
def is_viewer(): return user() and user().get("role") == "viewer"

def fmt(v):
    try:
        n = float(v)
        return f"{n:,.0f}" if n == int(n) else f"{n:,.1f}"
    except Exception:
        return str(v) if v else ""

# Premium Glassmorphic Styles
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
:root {
  --bg: #030712;
  --panel: rgba(17, 24, 39, 0.7);
  --panel-solid: #0f172a;
  --border: rgba(255, 255, 255, 0.08);
  --border-glow: rgba(99, 102, 241, 0.25);
  
  --ac: #6366f1;
  --ac-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
  --cyan-gradient: linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%);
  
  --ok: #10b981;
  --w: #f59e0b;
  --err: #f43f5e;
  
  --t: #f3f4f6;
  --t2: #9ca3af;
  --sub: #6b7280;
  
  --f: 'Plus Jakarta Sans', system-ui, sans-serif;
  --shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
  --radius: 12px;
  --radius-lg: 20px;
  --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--t);
  font: 14px/1.6 var(--f);
  display: flex;
  height: 100vh;
  overflow: hidden;
  background-image: 
    radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.1) 0%, transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(168, 85, 247, 0.07) 0%, transparent 40%);
}

a { color: #818cf8; text-decoration: none; transition: var(--transition); }
a:hover { color: #a5b4fc; }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 20px; }
::-webkit-scrollbar-thumb:hover { background: var(--ac); }

/* SIDEBAR */
.Sidebar {
  width: 260px; flex-shrink: 0; z-index: 20;
  background: rgba(10, 15, 30, 0.85);
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 0;
}
.Sidebar-header {
  padding: 24px 20px; border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.05));
}
.Sidebar-logo-row { display: flex; align-items: center; gap: 12px; }
.Sidebar-logo-icon {
  width: 38px; height: 38px; border-radius: 10px;
  background: var(--ac-gradient);
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
}
.Sidebar h1 { font-size: 16px; font-weight: 800; letter-spacing: -0.5px;
  background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.Sidebar .user-menu {
  color: var(--t2); font-size: 12px; padding: 16px 20px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: var(--transition); position: relative;
}
.Sidebar .user-menu:hover { background: rgba(255, 255, 255, 0.03); }
.Sidebar .user-menu::after { content: '▾'; position: absolute; right: 20px; top: 22px; font-size: 14px; color: var(--sub); transition: var(--transition); }
.Sidebar .user-menu.open::after { transform: rotate(180deg); color: var(--ac); }
.Sidebar .user-menu .uname { color: #fff; font-weight: 700; font-size: 13px; display: block; margin-bottom: 2px; }
.Sidebar .user-menu .urole {
  display: inline-block; font-size: 9px; font-weight: 800; letter-spacing: 0.8px;
  padding: 3px 10px; border-radius: 20px; background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.3); text-transform: uppercase;
}
.u-actions { display: none; gap: 8px; margin-top: 12px; flex-direction: column; }
.user-menu.open .u-actions { display: flex; }
.u-actions a {
  font-size: 11px; color: var(--t2); padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03); border: 1px solid var(--border); border-radius: 8px;
  display: flex; align-items: center; gap: 8px;
}
.u-actions a:hover { color: #fff; border-color: var(--ac); background: rgba(99, 102, 241, 0.1); }
.u-actions .u-logout:hover { color: var(--err); border-color: var(--err); background: rgba(244, 63, 94, 0.1); }

.Sidebar nav { flex: 1; padding: 12px 8px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.Sidebar a.nav-item {
  color: var(--t2); padding: 8px 16px; font-size: 13.5px; font-weight: 500;
  display: flex; align-items: center; gap: 12px; border-radius: var(--radius);
  transition: var(--transition);
}
.Sidebar a.nav-item:hover { color: #fff; background: rgba(255, 255, 255, 0.05); }
.Sidebar a.nav-item.on {
  color: #fff; background: var(--ac-gradient); font-weight: 600;
  box-shadow: 0 4px 15px rgba(99, 102, 241, 0.25);
}
.Sidebar a.nav-item .nav-sub {
  font-size: 9.5px; color: rgba(255, 255, 255, 0.35); font-weight: 400; transition: var(--transition);
}
.Sidebar a.nav-item:hover .nav-sub {
  color: rgba(255, 255, 255, 0.6);
}
.Sidebar a.nav-item.on .nav-sub {
  color: rgba(255, 255, 255, 0.75);
}

/* MAIN CONTENT */
.W { flex: 1; overflow: auto; padding: 28px 36px; background: transparent; }

/* PANEL CONTAINER */
.S {
  background: var(--panel);
  backdrop-filter: blur(12px);
  border-radius: var(--radius-lg); padding: 22px 26px; margin: 18px 0;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}
.S h3 { font-size: 16px; font-weight: 700; color: #fff; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }

/* DASHBOARD STATS CARDS */
.G { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 16px 0; }
.C {
  background: var(--panel);
  backdrop-filter: blur(8px);
  border-radius: var(--radius); padding: 18px 22px;
  border: 1px solid var(--border);
  transition: var(--transition); position: relative; overflow: hidden;
}
.C::before {
  content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
  background: var(--ac-gradient);
}
.C:nth-child(2)::before { background: var(--cyan-gradient); }
.C:nth-child(3)::before { background: linear-gradient(135deg, var(--ok) 0%, #059669 100%); }
.C:nth-child(4)::before { background: linear-gradient(135deg, var(--w) 0%, #d97706 100%); }
.C:hover { transform: translateY(-4px); border-color: rgba(255, 255, 255, 0.15); box-shadow: var(--shadow); }
.C .ci { font-size: 24px; position: absolute; right: 20px; top: 20px; opacity: 0.25; }
.C .l { font-size: 11px; color: var(--t2); text-transform: uppercase; letter-spacing: 1px; font-weight: 600; margin-bottom: 6px; }
.C .v { font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -0.5px; }

/* FILTERS */
.F {
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(10px);
  padding: 20px 24px; border-radius: var(--radius-lg); margin: 16px 0;
  border: 1px solid var(--border);
}
.F h3 { font-size: 12px; font-weight: 700; color: var(--ac); margin-bottom: 14px; text-transform: uppercase; letter-spacing: 1px; }
.fg { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }
.fg label { font-size: 11.5px; color: var(--t2); display:block; margin-bottom: 5px; font-weight: 600; }
.fg select, .fg input {
  width: 100%; background: rgba(3, 7, 18, 0.6); color: #fff;
  border: 1px solid var(--border); border-radius: 8px;
  padding: 9px 12px; font-size: 13px; font-family: var(--f);
  transition: var(--transition); outline: none;
}
.fg select:focus, .fg input:focus { border-color: var(--ac); box-shadow: 0 0 10px rgba(99, 102, 241, 0.2); }

/* BUTTONS */
.btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 20px; border-radius: 8px; border: none;
  font-size: 13px; font-weight: 700; cursor: pointer; font-family: var(--f);
  background: var(--ac-gradient); color: #fff;
  transition: var(--transition); box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.btn:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5); filter: brightness(1.1); }
.btn-sec {
  background: rgba(255, 255, 255, 0.05); color: #fff;
  border: 1px solid var(--border); box-shadow: none;
}
.btn-sec:hover { background: rgba(255, 255, 255, 0.1); border-color: rgba(255, 255, 255, 0.2); }

/* TABLES */
.TW { max-height: 55vh; overflow: auto; border-radius: var(--radius); border: 1px solid var(--border); }
table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
thead tr { position: sticky; top: 0; z-index: 3; }
th {
  background: #0f172a; color: #fff; padding: 12px 16px;
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px;
  border-bottom: 2px solid var(--border); white-space: nowrap;
}
td { padding: 11px 16px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); vertical-align: middle; color: var(--t2); }
tr:nth-child(even) td { background: rgba(255, 255, 255, 0.01); }
tr:hover td { background: rgba(99, 102, 241, 0.08); color: #fff; }

/* BADGES */
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.badge-ok { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
.badge-w { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
.badge-err { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }

/* FLASH MESSAGES */
.flash {
  padding: 12px 20px; border-radius: 8px; margin: 12px 0; font-size: 13px; font-weight: 600;
  background: rgba(16, 185, 129, 0.1); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.2);
  display: flex; align-items: center; gap: 10px; border-left: 4px solid var(--ok);
}
.flash::before { content: '✓'; font-weight: bold; }
.flash.e {
  background: rgba(244, 63, 94, 0.1); color: #fb7185; border-color: rgba(244, 63, 94, 0.2);
  border-left-color: var(--err);
}
.flash.e::before { content: '✕'; }

/* LOGIN */
.LB {
  max-width: 420px; margin: 80px auto;
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(20px);
  padding: 40px; border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}
.LB h2 { text-align: center; margin-bottom: 24px; font-size: 24px; font-weight: 800;
  background: linear-gradient(135deg, #fff 0%, #818cf8 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.LB label { display: block; font-size: 11px; color: var(--t2); margin: 16px 0 6px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
.LB input {
  width: 100%; background: rgba(3, 7, 18, 0.5); color: #fff;
  border: 1px solid var(--border); border-radius: 8px; padding: 11px 16px;
  font-size: 14px; outline: none; transition: var(--transition);
}
.LB input:focus { border-color: var(--ac); box-shadow: 0 0 12px rgba(99, 102, 241, 0.2); }

/* TERMINAL FOR PIPELINE RUN */
.terminal {
  background: #020617; border: 1px solid var(--border);
  border-radius: 8px; font-family: monospace; font-size: 12.5px;
  padding: 16px; height: 320px; overflow-y: auto;
  color: #10b981; margin: 14px 0; line-height: 1.5;
}

/* ANIMATIONS */
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.W > * { animation: fadeIn 0.25s ease forwards; }

.chart-box {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 18px; height: 320px;
  display: flex; flex-direction: column;
}
.chart-box h4 { font-size: 12px; color: var(--t2); margin-bottom: 12px; text-align: center; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; }
.chart-container { flex: 1; position: relative; }
.charts-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 20px;
}
@media (max-width: 1200px) {
  .charts-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 768px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}

/* MODAL GLASSMORPHISM */
.modal-overlay {
  position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
  background: rgba(3, 7, 18, 0.6);
  backdrop-filter: blur(12px);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  opacity: 0; pointer-events: none; transition: opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.modal-overlay.open {
  opacity: 1; pointer-events: auto;
}
.modal-container {
  width: 90%; max-width: 1100px; max-height: 85vh;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(25px);
  border: 1px solid var(--border-glow);
  border-radius: var(--radius-lg);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
  display: flex; flex-direction: column;
  transform: translateY(24px) scale(0.97); transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
  overflow: hidden;
}
.modal-overlay.open .modal-container {
  transform: translateY(0) scale(1);
}
.modal-header {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.05));
}
.modal-title {
  font-size: 16px; font-weight: 800; color: #fff;
  display: flex; align-items: center; gap: 10px;
}
.modal-close {
  background: transparent; border: none; color: var(--t2);
  font-size: 24px; cursor: pointer; transition: var(--transition);
  line-height: 1;
}
.modal-close:hover { color: var(--err); transform: scale(1.1); }
.modal-body {
  padding: 24px; overflow-y: auto; flex: 1;
}
.modal-footer {
  padding: 14px 24px; border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end; gap: 12px;
  background: rgba(3, 7, 18, 0.4);
}
.modal-summary-grid {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px;
  margin-bottom: 18px;
}
.size-pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border-radius: 6px; font-size: 11px;
  background: rgba(255,255,255,0.03); border: 1px solid var(--border);
  margin-right: 4px; margin-bottom: 4px;
  color: var(--t2); transition: var(--transition);
}
.size-pill:hover {
  background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.15); color: #fff;
}
.size-pill-chuyen {
  background: rgba(244, 63, 94, 0.12); border-color: rgba(244, 63, 94, 0.35); color: #fb7185;
}
.size-pill-chuyen:hover {
  background: rgba(244, 63, 94, 0.2); border-color: rgba(244, 63, 94, 0.5); color: #fff;
}
.size-pill-nhan {
  background: rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.35); color: #34d399;
}
.size-pill-nhan:hover {
  background: rgba(16, 185, 129, 0.2); border-color: rgba(16, 185, 129, 0.5); color: #fff;
}
</style>
"""

def page(title, body, u=None):
    nav = ""
    if u:
        p = request.path.strip("/") or "dashboard"
        tab_icons = {
            "dashboard": "📊", "reports": "📋", "product": "🏷️", 
            "run_pipeline": "⚡", "transfer": "🔀", "data": "📦",
            "review": "✅", "export": "📥", "audit": "📜", "guide": "📖", "admin": "⚙️"
        }
        
        # Sắp xếp lại thứ tự chuẩn xác 1-9
        tabs = [
            ("dashboard", "Dasboarh"),
            ("reports", "Reports Center"),
            ("product", "Product Finder"),
            ("run_pipeline", "Run Optimizer"),
            ("transfer", "Transfer Board"),
            ("data", "Inventory Details")
        ]
        if can_review():
            tabs.append(("review", "Review Center"))
            tabs.append(("export", "Export File"))
        if is_admin():
            tabs.append(("audit", "Audit Trail"))
            
        # Hướng dẫn sử dụng công khai cho tất cả mọi người
        tabs.append(("guide", "User Guide"))
        
        if is_admin():
            tabs.append(("admin", "Settings"))
            
        tab_subtitles = {
            "dashboard": "Bảng điều khiển chính",
            "reports": "Báo cáo phân tích dữ liệu",
            "product": "Tra cứu & Tìm kiếm sản phẩm",
            "run_pipeline": "Chạy lệnh điều chuyển",
            "transfer": "Bảng đề xuất điều chuyển",
            "data": "Chi tiết tồn kho & size",
            "review": "Duyệt lệnh điều chuyển",
            "export": "Xuất tệp lệnh điều chuyển",
            "audit": "Lịch sử thao tác hệ thống",
            "guide": "Hướng dẫn vận hành hàng hóa",
            "admin": "Cấu hình hệ thống"
        }
            
        ns = "".join(f'<a href="/{t}" class="nav-item {"on" if p==t else ""}"><span style="font-size:18px">{tab_icons.get(t,"•")}</span><div style="display:flex; flex-direction:column; gap:2px; text-align:left;"><span class="nav-title" style="font-size:13px; font-weight:600; display:block;">{l}</span><span class="nav-sub">{tab_subtitles.get(t,"")}</span></div></a>' for t,l in tabs)
        role = ROLE_LABELS.get(u.get("role",""), u.get("role",""))
        nav = (f'<div class="Sidebar">'
              f'<div class="Sidebar-header"><div class="Sidebar-logo-row"><div class="Sidebar-logo-icon">📦</div><h1>Reallocation Pro</h1></div></div>'
              f'<div class="user-menu"><span class="uname">{u.get("display_name","")}</span><span class="urole">{role}</span>'
              f'<div class="u-actions">'
              f'<a href="/profile">🔑 Change Password</a>'
              f'<a href="/logout" class="u-logout">🚪 Logout</a>'
              f'<a href="/shutdown" class="u-logout" style="color:var(--err)" onclick="return confirm(\'Shutdown application?\')">⏻ Exit</a>'
              f'</div></div>'
              f'<nav>{ns}</nav>'
              f'<div class="Sidebar-footer" style="padding:15px; text-align:center; font-size:11.5px; color:var(--t2); border-top:1px solid rgba(255,255,255,0.03); background:rgba(0,0,0,0.1); font-family:\'Outfit\',\'Inter\',sans-serif; letter-spacing:0.3px;">'
              f'  ✍️ Tác giả: <span style="color:#fff; font-weight:700;">Thong.Nguyen</span>'
              f'</div>'
              f'</div>')
    fh = ""
    for c,m in session.pop("_f",[]):
        fh += f'<div class="flash{"" if c=="ok" else " e"}">{m}</div>'
    
    chart_js = '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>' if u else ''
    user_js = '''<script>
    document.addEventListener('DOMContentLoaded', function() {
        const um = document.querySelector('.user-menu');
        if(um) {
            um.addEventListener('click', function(e) {
                if(e.target.tagName === 'A') return;
                this.classList.toggle('open');
            });
        }
    });
    </script>''' if u else ''
    
    # --- Pipeline-running banner (shown on every page for all users) ---
    pipeline_banner = ""
    if _pipeline_running:
        pipeline_banner = (
            '<div style="'
            'position:sticky; top:0; z-index:9999;'
            'background:linear-gradient(90deg,#78350f,#92400e);'
            'border-bottom:2px solid #f59e0b;'
            'padding:10px 20px; display:flex; align-items:center; gap:12px;'
            'font-size:13px; color:#fef3c7; font-weight:500; letter-spacing:0.2px;'
            'box-shadow:0 2px 16px rgba(245,158,11,0.25);'
            '">'
            '<span style="font-size:20px; animation:spin 2s linear infinite; display:inline-block;">&#9881;</span>'
            '<span><b>Hệ thống đang cập nhật database...</b> '
            'Dữ liệu hiển thị là phiên bản cũ hợp lệ. '
            'Vui lòng <b>không thực hiện duyệt lệnh</b> cho đến khi hoàn tất.'
            '</span>'
            '<a href="/run_pipeline" style="margin-left:auto; color:#fde68a; text-decoration:underline; white-space:nowrap;">'
            '→ Xem tiến trình</a>'
            '</div>'
            '<style>@keyframes spin{to{transform:rotate(360deg)}}</style>'
        )

    return (f'<!DOCTYPE html><html lang="vi"><head>'
            f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{title} — Reallocation Pro</title><style>{CSS}</style>{chart_js}{user_js}'
            f'</head><body>{nav}<div class="W">{pipeline_banner}{fh}{body}</div></body></html>')

def flash(m,c="ok"):
    f=session.get("_f",[]);f.append((c,m));session["_f"]=f

# Smart filter options builder
def get_smart_opts(df, fvals, cols):
    opts = {}
    for c in cols:
        temp = df
        for other_c in cols:
            if other_c != c and fvals.get(other_c):
                if other_c in temp.columns:
                    temp = temp[temp[other_c] == fvals[other_c]]
        opts[c] = sorted(temp[c].dropna().unique().astype(str))
    return opts

# Filters for general inventory view
def filt_form(df, fvals, active_tab="region-report"):
    cols = ["Region", "Store_RP", "Report_item_name"]
    opts = get_smart_opts(df, fvals, cols)
            
    reg_map = {}
    if "Region" in df.columns and "Store_RP" in df.columns:
        for r, sdf in df.dropna(subset=["Region", "Store_RP"]).groupby("Region"):
            reg_map[str(r)] = sorted(sdf["Store_RP"].unique().astype(str))
            
    rows = ""
    is_reports = (request.path == "/reports")
    for k,label in [("Region","Region"), ("Store_RP","Store"), ("Report_item_name","Report Item Name")]:
        os_html="".join(f'<option value="{v}" {"selected" if fvals.get(k)==v else ""}>{v}</option>' for v in opts.get(k,[]))
        style_attr = ""
        if is_reports:
            if k == "Store_RP" and active_tab not in ("store-report", "sku-report"):
                style_attr = ' style="display:none;"'
            elif k == "Report_item_name" and active_tab != "sku-report":
                style_attr = ' style="display:none;"'
        rows+=f'<div id="filter-{k}"{style_attr}><label>{label}</label><select name="{k}"><option value="">-- Tất cả --</option>{os_html}</select></div>'
        
    sv = fvals.get("search","")
    search_style = ""
    if is_reports and active_tab != "sku-report":
        search_style = ' style="display:none;"'
    rows += f'<div id="filter-search"{search_style}><label>Search</label><input name="search" value="{sv}" placeholder="Mã hàng, size..."></div>'
    
    js = f"""<script>
    document.addEventListener('DOMContentLoaded', function() {{
        const regMap = {json.dumps(reg_map)};
        const regSel = document.querySelector('select[name="Region"]');
        const storeSel = document.querySelector('select[name="Store_RP"]');
        if(!regSel || !storeSel) return;
        function updateStores() {{
            const r = regSel.value;
            const currentStore = "{fvals.get('Store_RP','')}";
            storeSel.innerHTML = '<option value="">-- Tất cả --</option>';
            let stores = [];
            if(r && regMap[r]) {{
                stores = regMap[r];
            }} else {{
                let allStores = [];
                for (let key in regMap) {{
                    if (regMap.hasOwnProperty(key)) {{
                        allStores = allStores.concat(regMap[key]);
                    }}
                }}
                stores = [...new Set(allStores)].sort();
            }}
            stores.forEach(s => {{
                const opt = document.createElement('option');
                opt.value = s; opt.textContent = s;
                if(s === currentStore) opt.selected = true;
                storeSel.appendChild(opt);
            }});
        }}
        regSel.addEventListener('change', updateStores);
        updateStores(); // Sync on initial page load
    }});
    </script>"""
    clear_url = f"/reports?active_tab={active_tab}" if is_reports else request.path
    return f'<div class="F"><h3>🔍 Inventory Filters</h3><form method="get" id="filterForm"><input type="hidden" name="active_tab" id="activeTabInput" value="{active_tab}"><div class="fg">{rows}</div><div style="margin-top:14px"><button class="btn">Apply Filters</button><a class="btn btn-sec" href="{clear_url}">Clear</a></div></form>{js}</div>'

def apply_f(df, fv):
    r = df.copy()
    for k in ["Region", "Store_RP", "Report_item_name", "Type", "MaHang"]:
        if fv.get(k):
            if k == "MaHang":
                r = r[r[k].str.upper() == str(fv[k]).upper()]
            else:
                r = r[r[k] == fv[k]]
    if fv.get("search"):
        s = fv["search"].upper()
        h = r[["MaHang", "Operation", "Store_RP", "Region", "Report_item_name", "Size"]].fillna("").astype(str).agg(" ".join, axis=1).str.upper()
        r = r[h.str.contains(s, regex=False)]
    return r

def size_sort_key(size_str):
    size_str = str(size_str).strip().upper()
    order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL", "4XL"]
    if size_str in order:
        return (0, order.index(size_str))
    try:
        val = float(size_str)
        return (1, val)
    except ValueError:
        return (2, size_str)

def get_fv():
    return {k: request.args.get(k, "") for k in ["Region", "Store_RP", "Report_item_name", "Type", "MaHang", "search"]}

def tbl(df, cols, limit=200, check=False, id_col="order_id", paginate=False, per_page=100):
    if df.empty: return '<div class="info" style="color:var(--sub)">Không có dữ liệu.</div>'
    
    total_rows = len(df)
    
    if paginate:
        import math
        # Lấy trang hiện tại từ request.args
        page_num = request.args.get("page", 1, type=int)
        total_pages = max(1, math.ceil(total_rows / per_page))
        page_num = max(1, min(page_num, total_pages))
        
        start_idx = (page_num - 1) * per_page
        end_idx = start_idx + per_page
        df_sliced = df.iloc[start_idx:end_idx]
        
        show_str = f"Hiển thị {start_idx+1:,} - {min(end_idx, total_rows):,} trong tổng số {total_rows:,} dòng (Trang {page_num}/{total_pages})"
    else:
        df_sliced = df.head(limit)
        show_str = f"Hiển thị {min(limit, total_rows):,}/{total_rows:,} dòng"

    ths = "<th><input type='checkbox' onclick='document.querySelectorAll(\".rc\").forEach(c=>c.checked=this.checked)'></th>" if check else ""
    ths += "".join(f"<th>{c}</th>" for c in cols)
    
    trs = ""
    for _, row in df_sliced.iterrows():
        tds = f"<td><input type='checkbox' class='rc' name='order_ids' value='{row.get(id_col,'')}'></td>" if check else ""
        for c in cols:
            v = row.get(c, "")
            if c in ("review_status", "Trang thai Nguon", "Trang thai Nhan"): 
                v = STATUS_LABELS.get(str(v), v)
            tds += f"<td>{fmt(v)}</td>"
        trs += f"<tr>{tds}</tr>"

    table_html = f'<div class="info" style="color:var(--t2); margin-bottom: 8px;">{show_str}</div><div class="TW"><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>'
    
    if paginate and total_pages > 1:
        # Xây dựng các link phân trang giữ nguyên các tham số query khác
        def get_url(p):
            args = dict(request.args)
            args["page"] = p
            import urllib.parse
            return f"{request.path}?{urllib.parse.urlencode(args)}"
            
        pag_html = '<div style="display:flex; justify-content:center; align-items:center; gap:6px; margin-top:20px; flex-wrap:wrap;">'
        
        # Nút Đầu & Trước
        if page_num > 1:
            pag_html += f'<a href="{get_url(1)}" class="btn btn-sec" style="font-size:12px; padding:6px 12px;">« Đầu</a>'
            pag_html += f'<a href="{get_url(page_num-1)}" class="btn btn-sec" style="font-size:12px; padding:6px 12px;">‹ Trước</a>'
        else:
            pag_html += '<span class="btn btn-sec" style="font-size:12px; padding:6px 12px; opacity:0.5; pointer-events:none;">« Đầu</span>'
            pag_html += '<span class="btn btn-sec" style="font-size:12px; padding:6px 12px; opacity:0.5; pointer-events:none;">‹ Trước</span>'
            
        # Các trang xung quanh trang hiện tại
        start_page = max(1, page_num - 2)
        end_page = min(total_pages, page_num + 2)
        
        if start_page > 1:
            pag_html += '<span style="color:var(--t2); padding:0 4px;">...</span>'
            
        for p in range(start_page, end_page + 1):
            if p == page_num:
                pag_html += f'<span class="btn" style="font-size:12px; padding:6px 12px; background:var(--ac); color:#fff; pointer-events:none;">{p}</span>'
            else:
                pag_html += f'<a href="{get_url(p)}" class="btn btn-sec" style="font-size:12px; padding:6px 12px;">{p}</a>'
                
        if end_page < total_pages:
            pag_html += '<span style="color:var(--t2); padding:0 4px;">...</span>'
            
        # Nút Sau & Cuối
        if page_num < total_pages:
            pag_html += f'<a href="{get_url(page_num+1)}" class="btn btn-sec" style="font-size:12px; padding:6px 12px;">Sau ›</a>'
            pag_html += f'<a href="{get_url(total_pages)}" class="btn btn-sec" style="font-size:12px; padding:6px 12px;">Cuối »</a>'
        else:
            pag_html += '<span class="btn btn-sec" style="font-size:12px; padding:6px 12px; opacity:0.5; pointer-events:none;">Sau ›</span>'
            pag_html += '<span class="btn btn-sec" style="font-size:12px; padding:6px 12px; opacity:0.5; pointer-events:none;">Cuối »</span>'
            
        pag_html += '</div>'
        table_html += pag_html
        
    return table_html


# --- Helper for dynamic lookups ---
_lookups_cache = None
def get_lookups():
    global _lookups_cache
    if _lookups_cache is not None:
        return _lookups_cache
    try:
        df = pd.read_excel(TRACKING_FILE, sheet_name="D_Category", engine="calamine")
    except Exception:
        try:
            df = pd.read_excel(TRACKING_FILE, sheet_name="D_Category")
        except Exception as e:
            return {"groups": [], "group_map": {}, "error": str(e)}
            
    df.columns = [" ".join(str(c).replace('\ufeff', '').strip().split()) for c in df.columns]
    groups = sorted(df["Group_Report"].dropna().unique().tolist())
    
    group_map = {}
    for g, sdf in df.dropna(subset=["Group_Report", "Report_item_name"]).groupby("Group_Report"):
        group_map[str(g)] = sorted(sdf["Report_item_name"].unique().tolist())
        
    _lookups_cache = {"groups": groups, "group_map": group_map}
    return _lookups_cache


# --- BACKGROUND PIPELINE RUNNER ---
def run_pipeline_thread(selected_items, months, selected_regions):
    global _pipeline_running, _pipeline_logs, _pipeline_progress
    _pipeline_running = True
    _pipeline_progress = 5
    _pipeline_logs = []

    # Acquire DB lock — tells other clients to serve stale cache
    set_db_lock(True)
    add_log("[LOCK] Database lock acquired — other clients will use cached data.")
    add_log("Khoi chay tien trinh toi uu hoa dieu chuyen hang...")
    add_log(f"Tham so nhan duoc: Regions={selected_regions}, Months={months}, Items={selected_items}")

    try:
        # Construct arguments
        cmd = [sys.executable, str(Path("../app/build_database.py").resolve())]
        cmd.extend(["--items", ",".join(selected_items)])
        cmd.extend(["--months", str(months)])
        if selected_regions:
            cmd.extend(["--regions", ",".join(selected_regions)])

        add_log(f"Executing: {' '.join(cmd)}")
        _pipeline_progress = 15

        # Start subprocess
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            cwd=str(Path("..").resolve())
        )

        # Read output in real time
        for line in iter(process.stdout.readline, ""):
            line_clean = line.strip()
            if line_clean:
                add_log(line_clean)

                # Estimate progress based on log outputs
                if "Loading data" in line_clean: _pipeline_progress = 25
                elif "Reading System_sales" in line_clean: _pipeline_progress = 40
                elif "Building Sheet 1" in line_clean: _pipeline_progress = 60
                elif "Building Transfer Orders" in line_clean: _pipeline_progress = 75
                elif "Building Sheet 3" in line_clean: _pipeline_progress = 85
                elif "Saving" in line_clean: _pipeline_progress = 95

        process.stdout.close()
        return_code = process.wait()

        if return_code == 0:
            _pipeline_progress = 100
            add_log("Hoan tat thanh cong! Du lieu moi da duoc nap.")
        else:
            add_log(f"Loi: Tien trinh ket thuc voi ma loi {return_code}")
            _pipeline_progress = 0
    except Exception as e:
        add_log(f"Exception triggered: {e}")
        _pipeline_progress = 0
    finally:
        # Release lock — allow other clients to read the new file
        set_db_lock(False)
        add_log("[LOCK] Database lock released — new data is now available.")
        _pipeline_running = False


# --- ROUTES ---
@app.before_request
def auth():
    if request.path.startswith("/image/"): return
    if request.path not in ("/login", "/register", "/health") and not user():
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        un = request.form.get("username", "").strip()
        pw = request.form.get("password", "")
        users = load_users()
        m = users[users["username"] == un]
        if not m.empty and check_password_hash(m.iloc[0].get("password", ""), pw):
            if str(m.iloc[0].get("approval_status", "")) == "pending":
                flash("Your account is pending admin approval.", "w")
            elif str(m.iloc[0].get("is_active", "")) != "1":
                flash("Your account is inactive.", "err")
            else:
                session.permanent = True
                session["u"] = {"username": un, "display_name": str(m.iloc[0].get("display_name", un)), "role": str(m.iloc[0].get("role", ""))}
                return redirect("/dashboard")
        else: flash("Invalid username or password.", "err")
        return redirect("/login")
    return page("Login", f'<div class="LB"><h2>System Login</h2><form method="post"><label>Username</label><input name="username" required autofocus><label>Password</label><input name="password" type="password" required><button class="btn" style="width:100%;margin-top:20px">Login</button><div style="text-align:center;margin-top:15px"><a href="/register" style="font-size:12px;color:var(--sub)">Don\'t have an account? Sign up</a></div></form><div style="text-align:center;margin-top:24px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);font-size:11.5px;color:var(--t2);">✍️ Tác giả: <span style="color:#fff;font-weight:700;">Thong.Nguyen</span></div></div>')

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        dn = request.form.get("dn", "").strip()
        pw = request.form.get("pw", "")
        if not dn or not pw: flash("Name and password are required.", "err")
        else:
            users = load_users()
            if dn in users["username"].values: flash("Username already exists.", "err")
            else:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                nr = {"username": dn, "display_name": dn, "password": pw, "role": "viewer", "is_active": "0", "approval_status": "pending", "created_at": ts, "updated_at": ts}
                users = pd.concat([users, pd.DataFrame([nr])], ignore_index=True)
                save_users(users)
                flash("Registration successful! Please wait for admin approval.")
                return redirect("/login")
    return page("Register", f'<div class="LB"><h2>Register Account</h2><form method="post"><label>Username</label><input name="dn" required autofocus><label>Password</label><input name="pw" type="password" required><button class="btn" style="width:100%;margin-top:20px;background:var(--ac)">Request Access</button><div style="text-align:center;margin-top:15px"><a href="/login" style="font-size:12px;color:var(--sub)">Back to Login</a></div></form><div style="text-align:center;margin-top:24px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.05);font-size:11.5px;color:var(--t2);">✍️ Tác giả: <span style="color:#fff;font-weight:700;">Thong.Nguyen</span></div></div>')

@app.route("/logout")
def logout(): session.clear(); return redirect("/login")

@app.route("/health")
def health(): return {"status": "ok"}

@app.route("/shutdown")
def shutdown():
    def kill(): time.sleep(0.5); os._exit(0)
    threading.Thread(target=kill).start()
    return "<h3>Hệ thống đang tắt...</h3><p>Bạn có thể đóng cửa sổ trình duyệt này.</p>"

@app.route("/image/<mahang>")
def get_image(mahang):
    import urllib.parse, mimetypes
    mahang = urllib.parse.unquote(mahang).strip().upper()
    
    base_dir = Path(r"\\hovmfs01\PKD\PhanPhoi\Thong.Nguyen\Report_BestSeller\03.Hinh_anh_sp")
    if not base_dir.exists():
        return "Image Directory Not Found", 404
        
    try:
        files = [f for f in base_dir.iterdir() if f.is_file() and f.name.upper().startswith(mahang)]
    except Exception:
        files = []
        
    if files:
        files.sort(key=lambda x: 0 if " t" in x.name.lower() or " t." in x.name.lower() else 1)
        filepath = str(files[0])
        mime, _ = mimetypes.guess_type(filepath)
        return send_file(filepath, mimetype=mime or "image/png")
        
    return "Not Found", 404


@app.route("/")
def idx(): return redirect("/dashboard")

@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    u = user()
    if request.method == "POST":
        old_pw = request.form.get("old_pw", "")
        new_pw = request.form.get("new_pw", "")
        confirm_pw = request.form.get("confirm_pw", "")
        if not new_pw: flash("Mật khẩu mới không được để trống.", "err")
        elif new_pw != confirm_pw: flash("Mật khẩu xác nhận không khớp.", "err")
        else:
            users = load_users()
            idx = users[users["username"] == u["username"]].index
            if not idx.empty:
                if users.at[idx[0], "password"] != old_pw: flash("Incorrect current password.", "err")
                else:
                    users.at[idx[0], "password"] = new_pw
                    save_users(users)
                    flash("Password changed successfully.")
                    return redirect("/profile")
    body = f"""<div class="S" style="max-width:450px;margin:20px auto"><h3>🔑 Change Password</h3><form method="post" class="LB" style="margin:0;padding:0;background:transparent;border:none;box-shadow:none;max-width:100%"><label>Current Password</label><input type="password" name="old_pw" required><label>New Password</label><input type="password" name="new_pw" required><label>Confirm New Password</label><input type="password" name="confirm_pw" required><button class="btn" style="width:100%;margin-top:20px">Update Password</button></form></div>"""
    return page("Change Password", body, u)


# --- DYNAMIC PIPELINE PAGE ---
@app.route("/run_pipeline", methods=["GET", "POST"])
def run_pipeline_page():
    u = user()
    lookups = get_lookups()
    
    if "error" in lookups:
        return page("Error", f'<div class="flash e">Lỗi kết nối tệp Tracking lookups: {lookups["error"]}</div>', u)
        
    if request.method == "POST":
        if _pipeline_running:
            flash("Pipeline đang được chạy bởi người dùng khác. Vui lòng đợi...", "w")
            return redirect("/run_pipeline")
            
        selected_regions = request.form.getlist("regions")
        months = int(request.form.get("months", 3))
        selected_items = request.form.getlist("items")
        
        if not selected_items:
            flash("Vui lòng chọn ít nhất một tên mặt hàng (Report Item).", "err")
            return redirect("/run_pipeline")
            
        # Start background job
        threading.Thread(target=run_pipeline_thread, args=(selected_items, months, selected_regions)).start()
        return redirect("/run_pipeline")
        
    # Render Form
    region_icons = {
        "Hà Nội": "🏛️",
        "Miền Tây": "🌴",
        "Miền Trung - TN": "⛰️",
        "TP. HCM": "🏙️",
        "Miền Đông": "🏞️"
    }
    regions_html = "".join(f'<div class="option-card active"><input type="checkbox" name="regions" value="{r}" checked id="reg_{r}"><label for="reg_{r}">{region_icons.get(r, "📍")} {r}</label></div>' 
                           for r in ["Hà Nội", "Miền Tây", "Miền Trung - TN", "TP. HCM", "Miền Đông"])
                           
    months_opts = "".join(f'<option value="{m}" {"selected" if m==3 else ""}>{m} tháng gần nhất</option>' for m in [1, 3, 6, 9, 12, 15, 18])
    
    # Render Group selector
    groups_html = "".join(f'<div class="option-card"><input type="checkbox" class="grp-chk" value="{g}" id="grp_{i}"><label for="grp_{i}">📂 {g}</label></div>' 
                          for i, g in enumerate(lookups["groups"]))
                          
    body = f"""
    <div class="S">
        <h3>⚡ Reallocation Optimizer Engine</h3>
        <p style="color:var(--t2);margin-bottom:24px;">Tạo gợi ý điều chuyển hàng thông minh dựa trên dữ liệu bán, tồn kho hệ thống và trạng thái tiêu thụ.</p>
        
        <form method="post" id="optForm" style="display: {'none' if _pipeline_running else 'block'};">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:0;">
                <div class="step-card">
                    <h4><span class="step-num">1</span> Chọn khu vực phân phối</h4>
                    <div class="option-grid" style="grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));">
                        {regions_html}
                    </div>
                </div>
                <div class="step-card">
                    <h4><span class="step-num">2</span> Chọn mốc thời gian bán</h4>
                    <div class="custom-select-wrapper" style="margin-top: 10px;">
                        <select name="months" class="custom-select">
                            {months_opts}
                        </select>
                    </div>
                    <span style="font-size:11.5px;color:var(--sub);display:block;margin-top:14px;">📅 Mốc thời gian khuyến nghị: 3 tháng gần nhất để dự báo đứt size ổn định.</span>
                </div>
            </div>
            
            <div class="step-card">
                <h4><span class="step-num">3</span> Chọn Nhóm báo cáo (Group_Report)</h4>
                <div class="option-grid" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
                    {groups_html}
                </div>
            </div>
            
            <div class="step-card">
                <h4><span class="step-num">4</span> Chọn Tên mặt hàng báo cáo (Report Item Name)</h4>
                <span style="font-size:11.5px;color:var(--sub);display:block;margin-bottom:14px;margin-top:-6px;">🏷️ Danh sách tự động cập nhật khớp với các Nhóm báo cáo đã chọn ở trên</span>
                
                <div style="display:flex;gap:10px;margin-bottom:14px;">
                    <button type="button" class="btn btn-sec" onclick="selectAllItems(true)" style="padding:6px 12px;font-size:11px;">✨ Chọn tất cả</button>
                    <button type="button" class="btn btn-sec" onclick="selectAllItems(false)" style="padding:6px 12px;font-size:11px;">❌ Bỏ chọn tất cả</button>
                </div>
                
                <div id="item-list-container" class="option-grid list-wrapper" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));">
                    <div style="grid-column: 1 / -1; color:var(--sub); text-align:center; padding:20px; font-size:13px;">Hãy chọn ít nhất 1 Nhóm báo cáo ở bước 3 để tải danh mục sản phẩm</div>
                </div>
            </div>
            
            <button class="btn" style="width:100%;padding:14px;font-size:15px;margin-top:10px;justify-content:center;">🚀 Khởi chạy tối ưu hóa phân bổ</button>
        </form>
        
        <div id="runningState" style="display: {'block' if _pipeline_running else 'none'};">
            <h4 style="color:#10b981;margin-bottom:8px;display:flex;align-items:center;gap:10px;">
                <span class="spinner" style="border: 3px solid rgba(16,185,129,0.2); border-top: 3px solid #10b981; border-radius: 50%; width: 20px; height: 20px; display:inline-block; animation: spin 1s linear infinite;"></span>
                Đang tính toán điều phối hàng...
            </h4>
            <div style="background:rgba(255,255,255,0.05);height:6px;border-radius:10px;margin-bottom:14px;overflow:hidden;">
                <div id="progressBar" style="background:#10b981;width:{_pipeline_progress}%;height:100%;transition:width 0.4s;"></div>
            </div>
            <div class="terminal" id="terminalBox">
                {''.join(f'<div>{line}</div>' for line in _pipeline_logs)}
            </div>
            <div id="completionActions" style="display:none;margin-top:14px;">
                <a href="/dashboard" class="btn" style="background:var(--ok)">📊 Vào Dashboard xem kết quả</a>
            </div>
        </div>
    </div>
    
    <style>
    @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
    
    .step-card {{
        background: rgba(255, 255, 255, 0.015);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 20px;
        margin-bottom: 24px;
        transition: var(--transition);
        position: relative;
    }}
    .step-card:hover {{
        border-color: rgba(99, 102, 241, 0.15);
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    }}
    .step-card h4 {{
        font-size: 14.5px;
        font-weight: 700;
        color: #fff;
        margin-top: 0;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .step-card h4 span.step-num {{
        background: var(--ac-gradient);
        color: #fff;
        font-size: 11px;
        font-weight: 800;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.45);
    }}
    
    .option-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
    }}
    .option-card {{
        display: flex;
        align-items: center;
        gap: 10px;
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--border);
        padding: 12px 16px;
        border-radius: 8px;
        cursor: pointer;
        transition: var(--transition);
        user-select: none;
    }}
    .option-card:hover {{
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(99, 102, 241, 0.3);
    }}
    .option-card input[type="checkbox"] {{
        width: 16px;
        height: 16px;
        accent-color: var(--ac);
        cursor: pointer;
        margin: 0;
    }}
    .option-card.active {{
        background: rgba(99, 102, 241, 0.08);
        border-color: var(--ac);
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.15);
    }}
    .option-card.active label {{
        color: #fff;
        font-weight: 600;
    }}
    .option-card label {{
        margin: 0;
        cursor: pointer;
        font-size: 13px;
        color: var(--t2);
        flex: 1;
        transition: var(--transition);
    }}
    
    .custom-select-wrapper {{
        position: relative;
    }}
    .custom-select {{
        width: 100%;
        padding: 12px 16px;
        background: rgba(3, 7, 18, 0.6);
        color: #fff;
        border: 1px solid var(--border);
        border-radius: 8px;
        outline: none;
        font-family: var(--f);
        font-size: 13.5px;
        transition: var(--transition);
        appearance: none;
        background-image: url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>");
        background-repeat: no-repeat;
        background-position: right 14px center;
        cursor: pointer;
    }}
    .custom-select:focus {{
        border-color: var(--ac);
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.2);
    }}
    
    .list-wrapper {{
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 16px;
        max-height: 280px;
        overflow-y: auto;
    }}
    </style>
    
    <script>
    const groupMap = {json.dumps(lookups["group_map"])};
    const groupChks = document.querySelectorAll('.grp-chk');
    const listContainer = document.getElementById('item-list-container');
    
    function toggleCardActive(chk) {{
        const card = chk.closest('.option-card');
        if (card) {{
            if (chk.checked) {{
                card.classList.add('active');
            }} else {{
                card.classList.remove('active');
            }}
        }}
    }}

    // Set initial card states on load
    document.querySelectorAll('.grp-chk, input[name="regions"]').forEach(chk => {{
        toggleCardActive(chk);
    }});

    // Handle dynamically checking/unchecking and container clicks using event delegation
    document.addEventListener('change', function(e) {{
        if (e.target && e.target.type === 'checkbox') {{
            toggleCardActive(e.target);
        }}
    }});

    document.addEventListener('click', function(e) {{
        const card = e.target.closest('.option-card');
        if (card && e.target.type !== 'checkbox' && e.target.tagName !== 'LABEL') {{
            const chk = card.querySelector('input[type="checkbox"]');
            if (chk) {{
                chk.click();
            }}
        }}
    }});
    
    function updateItems() {{
        const activeGroups = Array.from(groupChks).filter(c => c.checked).map(c => c.value);
        if(activeGroups.length === 0) {{
            listContainer.innerHTML = '<div style="grid-column: 1 / -1; color:var(--sub); text-align:center; padding:20px; font-size:13px;">Hãy chọn ít nhất 1 Nhóm báo cáo ở bước 3 để tải danh mục sản phẩm</div>';
            return;
        }}
        
        let html = '';
        let index = 0;
        activeGroups.forEach(g => {{
            const items = groupMap[g] || [];
            items.forEach(item => {{
                html += `
                <div class="option-card active" style="padding: 8px 12px; border-radius: 6px;">
                    <input type="checkbox" name="items" value="${{item}}" checked id="itm_${{index}}">
                    <label for="itm_${{index}}" style="font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${{item}}">🏷️ ${{item}}</label>
                </div>`;
                index++;
            }});
        }});
        listContainer.innerHTML = html;
    }}
    
    function selectAllItems(checked) {{
        const chks = listContainer.querySelectorAll('input[type="checkbox"]');
        chks.forEach(c => {{
            c.checked = checked;
            toggleCardActive(c);
        }});
    }}
    
    groupChks.forEach(chk => chk.addEventListener('change', updateItems));
    
    // Live logs polling if running
    let pollInterval = null;
    if ({'true' if _pipeline_running else 'false'}) {{
        pollInterval = setInterval(pollLogs, 1200);
    }}
    
    function pollLogs() {{
        fetch('/pipeline_status_api')
            .then(res => res.json())
            .then(data => {{
                const term = document.getElementById('terminalBox');
                const bar = document.getElementById('progressBar');
                
                bar.style.width = data.progress + '%';
                
                let logHtml = '';
                data.logs.forEach(l => {{
                    logHtml += `<div>${{l}}</div>`;
                }});
                term.innerHTML = logHtml;
                term.scrollTop = term.scrollHeight;
                
                if(!data.running) {{
                    clearInterval(pollInterval);
                    document.getElementById('completionActions').style.display = 'block';
                    if(data.progress === 100) {{
                        bar.style.background = 'var(--ok)';
                    }} else {{
                        bar.style.background = 'var(--err)';
                    }}
                }}
            }});
    }}
    </script>
    """
    return page("Optimizer Control", body, u)

@app.route("/pipeline_status_api")
def pipeline_status_api():
    return jsonify({
        "running": _pipeline_running,
        "progress": _pipeline_progress,
        "logs": _pipeline_logs
    })


# --- DASHBOARD & METRICS ---
@app.route("/dashboard")
def dashboard():
    u = user()
    fv = get_fv()
    try:
        df = load_inventory()
    except Exception as e:
        return page("Database Error", f'<div class="flash e">Lỗi nạp cơ sở dữ liệu Reallocation_Database.xlsx: {e}<br>Vui lòng click <b>Run Optimizer</b> phía bên trái để tạo cơ sở dữ liệu đầu tiên.</div>', u)
        
    filtered = apply_f(df, fv)
    s = build_summary(filtered)

    cards = "".join(f'<div class="C"><div class="ci">{c.get("icon","")}</div><div class="l">{c["label"]}</div><div class="v">{fmt(c["value"])}</div></div>' for c in s["cards"])
    
    def get_chart_data(rows, label_key):
        labels = [r.get(label_key, "") for r in rows]
        ton = [r.get("ton", 0) for r in rows]
        ban = [r.get("ban", 0) for r in rows]
        rate = [round(b / (t + b + 0.0001) * 100, 1) for t, b in zip(ton, ban)]
        return labels, ton, ban, rate

    type_l, type_t, type_b, type_r = get_chart_data(s.get("type_rows",[]), "Type")
    reg_l, reg_t, reg_b, reg_r = get_chart_data(s.get("region_rows",[]), "Region")
    tt_l, tt_t, tt_b, tt_r = get_chart_data(s.get("tt_rows",[]), "Trang_Thai")
    color_l, color_t, color_b, color_r = get_chart_data(s.get("color_rows",[]), "Color_group")
    form_l, form_t, form_b, form_r = get_chart_data(s.get("form_rows",[]), "Form")
    style_l, style_t, style_b, style_r = get_chart_data(s.get("style_rows",[]), "Style")

    # Build size chart data
    if not filtered.empty:
        size_agg = filtered.groupby("Size", dropna=False).agg(
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum")
        ).reset_index()
        size_agg = size_agg[size_agg["Size"] != ""]
        size_agg["sort_key"] = size_agg["Size"].map(size_sort_key)
        size_agg = size_agg.sort_values("sort_key").drop(columns=["sort_key"])
        size_l = size_agg["Size"].tolist()
        size_t = size_agg["ton"].tolist()
        size_b = size_agg["ban"].tolist()
        size_r = [round(b / (t + b + 0.0001) * 100, 1) for t, b in zip(size_t, size_b)]
    else:
        size_l, size_t, size_b, size_r = [], [], [], []

    charts_html = f"""
    <div class="charts-grid">
        <div class="chart-box">
            <h4>Tồn / Bán theo Group hàng</h4>
            <div class="chart-container"><canvas id="typeChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>Tồn / Bán theo Khu vực</h4>
            <div class="chart-container"><canvas id="regChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>Tồn / Bán theo Trạng thái CH</h4>
            <div class="chart-container"><canvas id="ttChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>Tồn / Bán theo Màu sắc</h4>
            <div class="chart-container"><canvas id="colorChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>Tồn / Bán theo Form dáng</h4>
            <div class="chart-container"><canvas id="formChart"></canvas></div>
        </div>
        <div class="chart-box">
            <h4>Tồn / Bán theo Phong cách</h4>
            <div class="chart-container"><canvas id="styleChart"></canvas></div>
        </div>
        <div class="chart-box" style="grid-column: 1 / -1; height: 380px;">
            <h4>Tồn / Bán / Tỷ lệ bán theo Size sản phẩm</h4>
            <div class="chart-container"><canvas id="sizeChart"></canvas></div>
        </div>
    </div>
    
    <script>
    Chart.defaults.color = '#9ca3af';
    Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
    
    const getOpts = () => ({{
        responsive: true, maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 15 }} }} }},
        scales: {{
            y: {{ type: 'linear', display: true, position: 'left', grid: {{ color: 'rgba(255,255,255,0.05)' }} }},
            y1: {{ type: 'linear', display: true, position: 'right', grid: {{ drawOnChartArea: false }}, min: 0, max: 100, ticks: {{ callback: function(v) {{ return v + '%' }} }} }}
        }}
    }});

    function buildData(labels, ton, ban, rate) {{
        return {{
            labels: labels,
            datasets: [
                {{ type: 'line', label: 'Sales Rate %', data: rate, borderColor: '#f59e0b', backgroundColor: '#f59e0b', yAxisID: 'y1', tension: 0.15, borderWidth: 2, pointRadius: 3 }},
                {{ type: 'bar', label: 'Sales Qty', data: ban, backgroundColor: '#10b981', borderRadius: 4, yAxisID: 'y' }},
                {{ type: 'bar', label: 'Stock Qty', data: ton, backgroundColor: '#6366f1', borderRadius: 4, yAxisID: 'y' }}
            ]
        }};
    }}

    new Chart(document.getElementById('typeChart'), {{ type: 'bar', data: buildData({type_l!r}, {type_t!r}, {type_b!r}, {type_r!r}), options: getOpts() }});
    new Chart(document.getElementById('regChart'), {{ type: 'bar', data: buildData({reg_l!r}, {reg_t!r}, {reg_b!r}, {reg_r!r}), options: getOpts() }});
    new Chart(document.getElementById('ttChart'), {{ type: 'bar', data: buildData({tt_l!r}, {tt_t!r}, {tt_b!r}, {tt_r!r}), options: getOpts() }});
    new Chart(document.getElementById('colorChart'), {{ type: 'bar', data: buildData({color_l!r}, {color_t!r}, {color_b!r}, {color_r!r}), options: getOpts() }});
    new Chart(document.getElementById('formChart'), {{ type: 'bar', data: buildData({form_l!r}, {form_t!r}, {form_b!r}, {form_r!r}), options: getOpts() }});
    new Chart(document.getElementById('styleChart'), {{ type: 'bar', data: buildData({style_l!r}, {style_t!r}, {style_b!r}, {style_r!r}), options: getOpts() }});
    new Chart(document.getElementById('sizeChart'), {{ type: 'bar', data: buildData({size_l!r}, {size_t!r}, {size_b!r}, {size_r!r}), options: getOpts() }});
    </script>
    """

    def tbl_row(r):
        t, b = r.get("ton", 0), r.get("ban", 0)
        rate = round(b / (t + b + 0.0001) * 100, 1)
        return f'<td>{fmt(r["count"])}</td><td>{fmt(b)}</td><td>{fmt(t)}</td><td>{rate}%</td>'

    type_t = "<table><tr><th>Group hàng</th><th>Item Count</th><th>Sales Qty</th><th>Stock Qty</th><th>Sales Rate</th></tr>" + "".join(f'<tr><td>{r["Type"]}</td>{tbl_row(r)}</tr>' for r in s["type_rows"]) + "</table>"
    reg_t = "<table><tr><th>Khu vực</th><th>Item Count</th><th>Sales Qty</th><th>Stock Qty</th><th>Sales Rate</th><th>Store Count</th></tr>" + "".join(f'<tr><td>{r["Region"]}</td>{tbl_row(r)}<td>{fmt(r["stores"])}</td></tr>' for r in s["region_rows"]) + "</table>"
    tt_t = "<table><tr><th>Trạng thái</th><th>Item Count</th><th>Sales Qty</th><th>Stock Qty</th><th>Sales Rate</th></tr>" + "".join(f'<tr><td>{r["Trang_Thai"]}</td>{tbl_row(r)}</tr>' for r in s["tt_rows"]) + "</table>"
    pg_t = "<table><tr><th>Tên mặt hàng báo cáo</th><th>Item Count</th><th>Sales Qty</th><th>Stock Qty</th><th>Sales Rate</th></tr>" + "".join(f'<tr><td>{r["Report_item_name"]}</td>{tbl_row(r)}</tr>' for r in s["pg_rows"]) + "</table>"

    body = f"""
    {filt_form(df, fv)}
    <div class="G">{cards}</div>
    {charts_html}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <div class="S"><h3>📊 Group Performance</h3>{type_t}</div>
        <div class="S"><h3>🗺️ Regional Distribution</h3>{reg_t}</div>
        <div class="S"><h3>📈 Store Status Distribution</h3>{tt_t}</div>
        <div class="S"><h3>🏷️ Category Level Breakdown</h3>{pg_t}</div>
    </div>
    """
    return page("Dashboard", body, u)


# --- REPORTS CENTER & EXPORTS ---
@app.route("/reports")
def reports_page():
    u = user()
    fv = get_fv()
    active_tab = request.args.get("active_tab", "region-report")
    
    try:
        df = load_inventory()
    except Exception as e:
        return page("Database Error", f'<div class="flash e">Lỗi nạp cơ sở dữ liệu Reallocation_Database.xlsx: {e}</div>', u)
        
    filtered = apply_f(df, fv)
    
    # Reset filter button if any filters are active
    reset_btn = ""
    if fv.get("Region") or fv.get("Store_RP") or fv.get("search") or fv.get("Report_item_name"):
        reset_btn = f'<a href="/reports?active_tab={active_tab}" class="btn btn-sec" style="font-size:12px;padding:6px 14px;margin-right:8px;">🔄 Đặt lại bộ lọc</a>'
    
    # 1. Build Custom KPI Cards for each report type
    card_data = []
    if active_tab == "region-report":
        card_data = [
            {"icon": "🗺️", "label": "Tổng số vùng", "value": filtered["Region"].nunique()},
            {"icon": "🏪", "label": "Tổng số cửa hàng", "value": filtered["Store_RP"].nunique()},
            {"icon": "📦", "label": "Tổng số lượng tồn", "value": filtered["Ton_Size"].sum()},
            {"icon": "💰", "label": "Tổng số lượng bán", "value": filtered["Ban_Size"].sum()},
            {"icon": "📈", "label": "Tỷ lệ bán trung bình", "value": f"{round(filtered['Ban_Size'].sum() / (filtered['Ton_Size'].sum() + filtered['Ban_Size'].sum() + 0.0001) * 100, 1)}%"},
        ]
    elif active_tab == "store-report":
        card_data = [
            {"icon": "🏪", "label": "Tổng số cửa hàng", "value": filtered["Store_RP"].nunique()},
            {"icon": "📦", "label": "Tổng số lượng tồn", "value": filtered["Ton_Size"].sum()},
            {"icon": "💰", "label": "Tổng số lượng bán", "value": filtered["Ban_Size"].sum()},
            {"icon": "🏢", "label": "Tồn trung bình / shop", "value": round(filtered["Ton_Size"].sum() / (filtered["Store_RP"].nunique() or 1))},
            {"icon": "📊", "label": "Tỷ lệ bán trung bình", "value": f"{round(filtered['Ban_Size'].sum() / (filtered['Ton_Size'].sum() + filtered['Ban_Size'].sum() + 0.0001) * 100, 1)}%"},
        ]
    elif active_tab == "sku-report":
        card_data = [
            {"icon": "🏷️", "label": "Tổng số SKU", "value": filtered["MaHang"].nunique()},
            {"icon": "📦", "label": "Tổng số lượng tồn", "value": filtered["Ton_Size"].sum()},
            {"icon": "💰", "label": "Tổng số lượng bán", "value": filtered["Ban_Size"].sum()},
            {"icon": "🗂️", "label": "Số Nhóm hàng", "value": filtered["Group"].nunique()},
            {"icon": "📈", "label": "Tỷ lệ bán trung bình", "value": f"{round(filtered['Ban_Size'].sum() / (filtered['Ton_Size'].sum() + filtered['Ban_Size'].sum() + 0.0001) * 100, 1)}%"},
        ]
    else: # group-report & group-sku-report
        card_data = [
            {"icon": "🗂️", "label": "Tổng nhóm hàng", "value": filtered["Group"].nunique()},
            {"icon": "🏷️", "label": "Tổng số SKU", "value": filtered["MaHang"].nunique()},
            {"icon": "📦", "label": "Tổng số lượng tồn", "value": filtered["Ton_Size"].sum()},
            {"icon": "💰", "label": "Tổng số lượng bán", "value": filtered["Ban_Size"].sum()},
            {"icon": "📈", "label": "Tỷ lệ bán trung bình", "value": f"{round(filtered['Ban_Size'].sum() / (filtered['Ton_Size'].sum() + filtered['Ban_Size'].sum() + 0.0001) * 100, 1)}%"},
        ]
        
    cards_html = "".join(f'<div class="C"><div class="ci">{c.get("icon","")}</div><div class="l">{c["label"]}</div><div class="v">{fmt(c["value"])}</div></div>' for c in card_data)
    
    # 2. Build tab headers
    tab_headers = f"""
    <div style="display:flex;gap:12px;margin-bottom:18px;border-bottom:1px solid var(--border);padding-bottom:10px;">
        <a href="/reports?active_tab=region-report" class="btn {'btn-sec' if active_tab != 'region-report' else ''}" style="font-size:13px;padding:8px 16px;">🗺️ Báo cáo Khu vực</a>
        <a href="/reports?active_tab=store-report" class="btn {'btn-sec' if active_tab != 'store-report' else ''}" style="font-size:13px;padding:8px 16px;">🏪 Báo cáo Cửa hàng</a>
        <a href="/reports?active_tab=sku-report" class="btn {'btn-sec' if active_tab != 'sku-report' else ''}" style="font-size:13px;padding:8px 16px;">🏷️ Báo cáo Mã hàng</a>
        <a href="/reports?active_tab=group-report" class="btn {'btn-sec' if active_tab not in ('group-report', 'group-sku-report') else ''}" style="font-size:13px;padding:8px 16px;">🗂️ Báo cáo Group</a>
    </div>
    """
    
    # 3. Compile table views based on active tab
    table_html = ""
    export_params = f"active_tab={active_tab}&Region={urllib.parse.quote(fv.get('Region',''))}&Store_RP={urllib.parse.quote(fv.get('Store_RP',''))}&Report_item_name={urllib.parse.quote(fv.get('Report_item_name',''))}&search={urllib.parse.quote(fv.get('search',''))}"
    
    if active_tab == "region-report":
        region_agg = filtered.groupby("Region", dropna=False).agg(
            stores=("Store_RP", "nunique"),
            skus=("MaHang", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        region_agg["rate"] = region_agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        region_agg = region_agg.sort_values("ton", ascending=False)
        
        table_rows = ""
        for _, r in region_agg.iterrows():
            reg = str(r["Region"])
            q_reg = urllib.parse.quote(reg)
            table_rows += f"""<tr>
                <td><a href="/reports?active_tab=store-report&Region={q_reg}" style="font-weight:700;color:#818cf8;">🗺️ {reg}</a></td>
                <td>{fmt(r["stores"])}</td>
                <td>{fmt(r["skus"])}</td>
                <td style="color:#60a5fa;font-weight:600;">{fmt(r["ton"])}</td>
                <td style="color:#34d399;font-weight:600;">{fmt(r["ban"])}</td>
                <td style="color:#fbbf24;font-weight:600;">{fmt(r["rate"])}%</td>
                <td style="color:#fb7185;font-weight:600;">{fmt(r["chuyen"])}</td>
                <td style="color:#a78bfa;font-weight:600;">{fmt(r["ton_sau"])}</td>
            </tr>"""
            
        table_html = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="margin:0;">📋 Báo cáo tổng quan theo Khu vực ({len(region_agg):,} vùng)</h3>
            <div style="display:flex;align-items:center;gap:10px;">
                {reset_btn}
                <a href="/export_report?{export_params}" class="btn" style="background:var(--cyan-gradient);font-size:12px;padding:6px 14px;">📥 Xuất Báo Cáo Excel</a>
            </div>
        </div>
        <div class="TW">
            <table>
                <thead>
                    <tr>
                        <th>Khu vực (Click xem shop)</th>
                        <th>Số cửa hàng</th>
                        <th>Số SKU</th>
                        <th>Tổng tồn</th>
                        <th>Tổng bán</th>
                        <th>Tỷ lệ bán</th>
                        <th>SL đề xuất chuyển</th>
                        <th>Tồn sau điều chuyển</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows or '<tr><td colspan="8" style="text-align:center;color:var(--sub)">Không có dữ liệu</td></tr>'}
                </tbody>
            </table>
        </div>
        """
        
    elif active_tab == "store-report":
        store_agg = filtered.groupby(["Region", "Store_RP"], dropna=False).agg(
            Store_rank=("Store_rank", "first"),
            Trang_Thai=("Trang_Thai", "first"),
            skus=("MaHang", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        store_agg["rate"] = store_agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        store_agg = store_agg.sort_values("ton", ascending=False)
        
        table_rows = ""
        for _, r in store_agg.iterrows():
            reg = str(r["Region"])
            st = str(r["Store_RP"])
            q_reg = urllib.parse.quote(reg)
            q_st = urllib.parse.quote(st)
            table_rows += f"""<tr>
                <td>{reg}</td>
                <td><a href="/reports?active_tab=sku-report&Region={q_reg}&Store_RP={q_st}" style="font-weight:700;color:#818cf8;">🏪 {st}</a></td>
                <td>{r["Store_rank"]}</td>
                <td><span class="badge badge-ok">{r["Trang_Thai"]}</span></td>
                <td>{fmt(r["skus"])}</td>
                <td style="color:#60a5fa;font-weight:600;">{fmt(r["ton"])}</td>
                <td style="color:#34d399;font-weight:600;">{fmt(r["ban"])}</td>
                <td style="color:#fbbf24;font-weight:600;">{fmt(r["rate"])}%</td>
                <td style="color:#fb7185;font-weight:600;">{fmt(r["chuyen"])}</td>
                <td style="color:#a78bfa;font-weight:600;">{fmt(r["ton_sau"])}</td>
            </tr>"""
            
        table_html = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="margin:0;">📋 Báo cáo chi tiết theo Cửa hàng ({len(store_agg):,} shop)</h3>
            <div style="display:flex;align-items:center;gap:10px;">
                {reset_btn}
                <a href="/export_report?{export_params}" class="btn" style="background:var(--cyan-gradient);font-size:12px;padding:6px 14px;">📥 Xuất Báo Cáo Excel</a>
            </div>
        </div>
        <div class="TW">
            <table>
                <thead>
                    <tr>
                        <th>Khu vực</th>
                        <th>Cửa hàng (Click xem mã)</th>
                        <th>Hạng CH</th>
                        <th>Trạng thái CH</th>
                        <th>Số SKU</th>
                        <th>Tổng tồn</th>
                        <th>Tổng bán</th>
                        <th>Tỷ lệ bán</th>
                        <th>SL đề xuất chuyển</th>
                        <th>Tồn sau điều chuyển</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows or '<tr><td colspan="10" style="text-align:center;color:var(--sub)">Không có dữ liệu</td></tr>'}
                </tbody>
            </table>
        </div>
        """
        
    elif active_tab == "sku-report":
        sku_agg = filtered.groupby("MaHang", dropna=False).agg(
            Report_item_name=("Report_item_name", "first"),
            Group=("Group", "first"),
            Operation=("Operation", "first"),
            Dist_plan=("Dist_plan", "first"),
            Color_group=("Color_group", "first"),
            Form=("Form", "first"),
            Style=("Style", "first"),
            stores=("Store_RP", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        sku_agg["rate"] = sku_agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        sku_agg = sku_agg.sort_values("ton", ascending=False)
        
        total_skus = len(sku_agg)
        display_df = sku_agg.head(500)
        
        table_rows = ""
        for _, r in display_df.iterrows():
            mh = str(r["MaHang"])
            q_mh = urllib.parse.quote(mh)
            table_rows += f"""<tr>
                <td><a href="/product?search={q_mh}" style="font-weight:700;color:#818cf8;">🏷️ {mh}</a></td>
                <td>{r["Report_item_name"]}</td>
                <td>{r["Group"]}</td>
                <td>{r["Operation"]}</td>
                <td>{r["Dist_plan"]}</td>
                <td>{r["Color_group"]}</td>
                <td>{r["Form"]}</td>
                <td>{r["Style"]}</td>
                <td>{fmt(r["stores"])}</td>
                <td style="color:#60a5fa;font-weight:600;">{fmt(r["ton"])}</td>
                <td style="color:#34d399;font-weight:600;">{fmt(r["ban"])}</td>
                <td style="color:#fbbf24;font-weight:600;">{fmt(r["rate"])}%</td>
                <td style="color:#fb7185;font-weight:600;">{fmt(r["chuyen"])}</td>
                <td style="color:#a78bfa;font-weight:600;">{fmt(r["ton_sau"])}</td>
            </tr>"""
            
        limit_info = ""
        if total_skus > 500:
            limit_info = f'<div style="color:var(--w);margin-bottom:8px;font-size:12px;font-weight:600;">⚠️ Hiển thị tối đa 500/ {total_skus:,} SKU để tối ưu giao diện. Hãy Click nút "Xuất Báo Cáo Excel" để tải đầy đủ thông tin.</div>'
        else:
            limit_info = f'<div style="color:var(--t2);margin-bottom:8px;font-size:12px;">Hiển thị toàn bộ {total_skus:,} SKU.</div>'
            
        table_html = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="margin:0;">📋 Báo cáo tổng hợp theo Mã Hàng (SKU)</h3>
            <div style="display:flex;align-items:center;gap:10px;">
                {reset_btn}
                <a href="/export_report?{export_params}" class="btn" style="background:var(--cyan-gradient);font-size:12px;padding:6px 14px;">📥 Xuất Báo Cáo Excel</a>
            </div>
        </div>
        {limit_info}
        <div class="TW">
            <table>
                <thead>
                    <tr>
                        <th>Mã hàng (Click xem chi tiết)</th>
                        <th>Tên mặt hàng báo cáo</th>
                        <th>Group hàng</th>
                        <th>Operation</th>
                        <th>KHPP / Dis.Plan</th>
                        <th>Màu sắc</th>
                        <th>Form dáng</th>
                        <th>Phong cách</th>
                        <th>Số CH có tồn</th>
                        <th>Tổng tồn</th>
                        <th>Tổng bán</th>
                        <th>Tỷ lệ bán</th>
                        <th>SL đề xuất chuyển</th>
                        <th>Tồn sau điều chuyển</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows or '<tr><td colspan="14" style="text-align:center;color:var(--sub)">Không có dữ liệu</td></tr>'}
                </tbody>
            </table>
        </div>
        """
        
    elif active_tab == "group-report":
        group_agg = filtered.groupby("Group", dropna=False).agg(
            skus=("MaHang", "nunique"),
            stores=("Store_RP", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        group_agg["rate"] = group_agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        group_agg = group_agg.sort_values("ton", ascending=False)
        
        table_rows = ""
        for _, r in group_agg.iterrows():
            grp = str(r["Group"])
            q_grp = urllib.parse.quote(grp)
            table_rows += f"""<tr>
                <td><a href="/reports?active_tab=group-sku-report&Group={q_grp}" style="font-weight:700;color:#818cf8;">🗂️ {grp}</a></td>
                <td>{fmt(r["skus"])}</td>
                <td>{fmt(r["stores"])}</td>
                <td style="color:#60a5fa;font-weight:600;">{fmt(r["ton"])}</td>
                <td style="color:#34d399;font-weight:600;">{fmt(r["ban"])}</td>
                <td style="color:#fbbf24;font-weight:600;">{fmt(r["rate"])}%</td>
                <td style="color:#fb7185;font-weight:600;">{fmt(r["chuyen"])}</td>
                <td style="color:#a78bfa;font-weight:600;">{fmt(r["ton_sau"])}</td>
            </tr>"""
            
        legend_html = f"""
        <div style="background:var(--panel);backdrop-filter:blur(8px);border:1px solid var(--border);border-radius:var(--radius);padding:18px 22px;margin-bottom:20px;border-left:4px solid var(--ac);box-shadow:var(--shadow);">
            <h4 style="margin-bottom:12px;color:#fff;font-size:13.5px;display:flex;align-items:center;gap:8px;">🗂️ Chú thích xếp loại Nhóm hàng (Group Legend)</h4>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;font-size:12.5px;color:var(--t2);">
                <div style="display:flex;gap:8px;align-items:flex-start;">
                    <span class="badge badge-ok" style="font-weight:800;padding:2px 8px;">Group A</span>
                    <span>Sản phẩm <b>bán chạy</b> toàn hệ thống trên 80%.</span>
                </div>
                <div style="display:flex;gap:8px;align-items:flex-start;">
                    <span class="badge" style="background:rgba(99,102,241,0.15);color:#a5b4fc;border:1px solid rgba(99,102,241,0.3);font-weight:800;padding:2px 8px;">Group B</span>
                    <span>Nhóm sản phẩm <b>bán ổn định</b> ở hệ thống (30% - 80%).</span>
                </div>
                <div style="display:flex;gap:8px;align-items:flex-start;">
                    <span class="badge badge-w" style="font-weight:800;padding:2px 8px;">Group C</span>
                    <span>Nhóm sản phẩm <b>bán chậm</b> dưới 30%.</span>
                </div>
                <div style="display:flex;gap:8px;align-items:flex-start;">
                    <span class="badge" style="background:rgba(0,180,216,0.15);color:#00b4d8;border:1px solid rgba(0,180,216,0.3);font-weight:800;padding:2px 8px;">Group D</span>
                    <span>Sản phẩm <b>mới phân phối</b> trong 6 tháng gần nhất.</span>
                </div>
                <div style="display:flex;gap:8px;align-items:flex-start;">
                    <span class="badge badge-err" style="font-weight:800;padding:2px 8px;">Group E</span>
                    <span>Sản phẩm <b>tồn kho dưới 20 cái</b> (pcs) toàn quốc.</span>
                </div>
            </div>
        </div>
        """
        
        table_html = f"""
        {legend_html}
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="margin:0;">📋 Báo cáo tổng hợp theo Nhóm hàng ({len(group_agg):,} nhóm)</h3>
            <div style="display:flex;align-items:center;gap:10px;">
                {reset_btn}
                <a href="/export_report?{export_params}" class="btn" style="background:var(--cyan-gradient);font-size:12px;padding:6px 14px;">📥 Xuất Báo Cáo Excel</a>
            </div>
        </div>
        <div class="TW">
            <table>
                <thead>
                    <tr>
                        <th>Nhóm hàng (Click xem mã)</th>
                        <th>Số SKU</th>
                        <th>Số cửa hàng</th>
                        <th>Tổng tồn</th>
                        <th>Tổng bán</th>
                        <th>Tỷ lệ bán</th>
                        <th>SL đề xuất chuyển</th>
                        <th>Tồn sau điều chuyển</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows or '<tr><td colspan="8" style="text-align:center;color:var(--sub)">Không có dữ liệu</td></tr>'}
                </tbody>
            </table>
        </div>
        """
        
    else: # group-sku-report
        selected_grp = request.args.get("Group", "").strip()
        g_df = filtered if not selected_grp else filtered[filtered["Group"] == selected_grp]
        
        # 1. Aggregate SKU totals
        sku_agg = g_df.groupby("MaHang").agg(
            Report_item_name=("Report_item_name", "first"),
            ton_tot=("Ton_Size", "sum"),
            ban_tot=("Ban_Size", "sum")
        ).reset_index()
        sku_agg = sku_agg.sort_values("ton_tot", ascending=False)
        
        regions_list = ["Hà Nội", "TP. HCM", "Miền Tây", "Miền Đông", "Miền Trung - TN"]
        
        # 2. Pre-fetch regional ton/ban for each SKU to keep it fast
        reg_data = {}
        for reg in regions_list:
            r_df = g_df[g_df["Region"] == reg].groupby("MaHang").agg(
                ton=("Ton_Size", "sum"),
                ban=("Ban_Size", "sum")
            ).reset_index()
            reg_data[reg] = dict(zip(r_df["MaHang"], r_df.to_dict("records")))
            
        total_skus = len(sku_agg)
        display_df = sku_agg.head(300) # limit to 300 for smooth page load
        
        table_rows = ""
        for _, r in display_df.iterrows():
            sku = str(r["MaHang"])
            q_sku = urllib.parse.quote(sku)
            
            reg_cols_html = ""
            for reg in regions_list:
                r_dict = reg_data[reg].get(sku, {"ton": 0, "ban": 0})
                t = r_dict["ton"]
                b = r_dict["ban"]
                rate = round(b / (t + b + 0.0001) * 100, 1)
                reg_cols_html += f"""
                <td style="text-align:center; border-left:1px solid rgba(255,255,255,0.05); border-right:1px solid rgba(255,255,255,0.05);">
                    <span style="color:#60a5fa;font-weight:600;">{fmt(t)}</span> / 
                    <span style="color:#34d399;font-weight:600;">{fmt(b)}</span> / 
                    <span style="color:#fbbf24;font-size:11px;">{fmt(rate)}%</span>
                </td>
                """
                
            rate_tot = round(r["ban_tot"] / (r["ton_tot"] + r["ban_tot"] + 0.0001) * 100, 1)
            
            table_rows += f"""<tr>
                <td><a href="/product?search={q_sku}" style="font-weight:700;color:#818cf8;">🏷️ {sku}</a></td>
                <td style="max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{r['Report_item_name']}">{r['Report_item_name']}</td>
                {reg_cols_html}
                <td style="color:#60a5fa;font-weight:700;text-align:center;">{fmt(r["ton_tot"])}</td>
                <td style="color:#34d399;font-weight:700;text-align:center;">{fmt(r["ban_tot"])}</td>
                <td style="color:#fbbf24;font-weight:700;text-align:center;">{fmt(rate_tot)}%</td>
            </tr>"""
            
        limit_info = ""
        if total_skus > 300:
            limit_info = f'<div style="color:var(--w);margin-bottom:8px;font-size:12px;font-weight:600;">⚠️ Hiển thị tối đa 300/ {total_skus:,} SKU của nhóm "{selected_grp}". Hãy Click "Xuất Báo Cáo Excel" để lấy danh sách đầy đủ.</div>'
        else:
            limit_info = f'<div style="color:var(--t2);margin-bottom:8px;font-size:12px;">Hiển thị toàn bộ {total_skus:,} SKU của nhóm "{selected_grp}".</div>'
            
        # Build headers for regions
        region_headers = "".join(f'<th style="text-align:center;min-width:120px;">{reg}<br><span style="font-size:9px;color:var(--t2);text-transform:none;">Tồn / Bán / TLB</span></th>' for reg in regions_list)
        
        # Add special back link
        back_btn = f'<a href="/reports?active_tab=group-report" class="btn btn-sec" style="font-size:12px;padding:6px 14px;margin-right:8px;">⬅️ Quay lại nhóm</a>'
        
        table_html = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <h3 style="margin:0;">📋 Chi tiết các mã hàng trong Group: <span style="color:var(--ac);">{selected_grp or "Tất cả"}</span></h3>
            <div style="display:flex;align-items:center;gap:10px;">
                {back_btn}
                {reset_btn}
                <a href="/export_report?{export_params}&Group={urllib.parse.quote(selected_grp)}" class="btn" style="background:var(--cyan-gradient);font-size:12px;padding:6px 14px;">📥 Xuất Báo Cáo Excel</a>
            </div>
        </div>
        {limit_info}
        <div class="TW">
            <table>
                <thead>
                    <tr>
                        <th style="min-width:110px;">Mã hàng (Click xem chi tiết)</th>
                        <th style="min-width:160px;">Tên mặt hàng báo cáo</th>
                        {region_headers}
                        <th style="text-align:center;min-width:70px;">Tổng tồn</th>
                        <th style="text-align:center;min-width:70px;">Tổng bán</th>
                        <th style="text-align:center;min-width:75px;">TL bán</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows or '<tr><td colspan="10" style="text-align:center;color:var(--sub)">Không có dữ liệu</td></tr>'}
                </tbody>
            </table>
        </div>
        """
        
    body = f"""
    {tab_headers}
    <div class="G">{cards_html}</div>
    <div class="S">{table_html}</div>
    """
    return page("Reports Center", body, u)


@app.route("/export_report")
def export_report():
    u = user()
    if not u:
        return redirect("/login")
        
    active_tab = request.args.get("active_tab", "region-report")
    fv = get_fv()
    
    try:
        df = load_inventory()
    except Exception as e:
        return f"Error loading database: {e}", 500
        
    filtered = apply_f(df, fv)
    
    if active_tab == "region-report":
        agg = filtered.groupby("Region", dropna=False).agg(
            stores=("Store_RP", "nunique"),
            skus=("MaHang", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        agg["rate"] = agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        agg = agg.sort_values("ton", ascending=False)
        
        export_cols = {
            "Region": "Khu vực",
            "stores": "Số Cửa Hàng",
            "skus": "Số SKU",
            "ton": "Tổng Tồn",
            "ban": "Tổng Bán",
            "rate": "Tỷ Lệ Bán (%)",
            "chuyen": "SL Đề Xuất Chuyển",
            "ton_sau": "Tồn Sau Điều Chuyển"
        }
        filename = "Bao_Cao_Khu_Vuc"
        
    elif active_tab == "store-report":
        agg = filtered.groupby(["Region", "Store_RP"], dropna=False).agg(
            Store_rank=("Store_rank", "first"),
            Trang_Thai=("Trang_Thai", "first"),
            skus=("MaHang", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        agg["rate"] = agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        agg = agg.sort_values("ton", ascending=False)
        
        export_cols = {
            "Region": "Khu vực",
            "Store_RP": "Cửa Hàng",
            "Store_rank": "Hạng Cửa Hàng",
            "Trang_Thai": "Trạng Thái Cửa Hàng",
            "skus": "Số SKU",
            "ton": "Tổng Tồn",
            "ban": "Tổng Bán",
            "rate": "Tỷ Lệ Bán (%)",
            "chuyen": "SL Đề Xuất Chuyển",
            "ton_sau": "Tồn Sau Điều Chuyển"
        }
        filename = "Bao_Cao_Cua_Hang"
        
    elif active_tab == "sku-report":
        agg = filtered.groupby("MaHang", dropna=False).agg(
            Report_item_name=("Report_item_name", "first"),
            Group=("Group", "first"),
            Operation=("Operation", "first"),
            Dist_plan=("Dist_plan", "first"),
            Color_group=("Color_group", "first"),
            Form=("Form", "first"),
            Style=("Style", "first"),
            stores=("Store_RP", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        agg["rate"] = agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        agg = agg.sort_values("ton", ascending=False)
        
        export_cols = {
            "MaHang": "Mã Hàng",
            "Report_item_name": "Tên Mặt Hàng",
            "Group": "Nhóm Hàng",
            "Operation": "Operation",
            "Dist_plan": "KHPP / Dis.Plan",
            "Color_group": "Màu Sắc",
            "Form": "Form Dáng",
            "Style": "Style",
            "stores": "Số CH Có Tồn",
            "ton": "Tổng Tồn",
            "ban": "Tổng Bán",
            "rate": "Tỷ Lệ Bán (%)",
            "chuyen": "SL Đề Xuất Chuyển",
            "ton_sau": "Tồn Sau Điều Chuyển"
        }
        filename = "Bao_Cao_Ma_Hang"
        
    elif active_tab == "group-report":
        agg = filtered.groupby("Group", dropna=False).agg(
            skus=("MaHang", "nunique"),
            stores=("Store_RP", "nunique"),
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            chuyen=("SL_Đề_Xuất", "sum"),
            ton_sau=("Ton_Sau_Dieu_Chuyen", "sum")
        ).reset_index()
        agg["rate"] = agg.apply(lambda r: round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1), axis=1)
        agg = agg.sort_values("ton", ascending=False)
        
        export_cols = {
            "Group": "Nhóm hàng",
            "skus": "Số SKU",
            "stores": "Số Cửa Hàng",
            "ton": "Tổng Tồn",
            "ban": "Tổng Bán",
            "rate": "Tỷ Lệ Bán (%)",
            "chuyen": "SL Đề Xuất Chuyển",
            "ton_sau": "Tồn Sau Điều Chuyển"
        }
        filename = "Bao_Cao_Nhom_Hang"
        
    else: # group-sku-report
        selected_grp = request.args.get("Group", "").strip()
        g_df = filtered if not selected_grp else filtered[filtered["Group"] == selected_grp]
        
        sku_agg = g_df.groupby("MaHang").agg(
            Report_item_name=("Report_item_name", "first"),
            ton_tot=("Ton_Size", "sum"),
            ban_tot=("Ban_Size", "sum")
        ).reset_index()
        sku_agg = sku_agg.sort_values("ton_tot", ascending=False)
        
        regions_list = ["Hà Nội", "TP. HCM", "Miền Tây", "Miền Đông", "Miền Trung - TN"]
        
        # Build regional columns in dataframe
        for reg in regions_list:
            r_df = g_df[g_df["Region"] == reg].groupby("MaHang").agg(
                ton=("Ton_Size", "sum"),
                ban=("Ban_Size", "sum")
            ).reset_index()
            
            ton_dict = dict(zip(r_df["MaHang"], r_df["ton"]))
            ban_dict = dict(zip(r_df["MaHang"], r_df["ban"]))
            
            sku_agg[f"{reg}_Tồn"] = sku_agg["MaHang"].map(ton_dict).fillna(0).astype(int)
            sku_agg[f"{reg}_Bán"] = sku_agg["MaHang"].map(ban_dict).fillna(0).astype(int)
            sku_agg[f"{reg}_TLB"] = sku_agg.apply(lambda r, reg=reg: round(r[f"{reg}_Bán"] / (r[f"{reg}_Tồn"] + r[f"{reg}_Bán"] + 0.0001) * 100, 1), axis=1)
            
        sku_agg["rate_tot"] = sku_agg.apply(lambda r: round(r["ban_tot"] / (r["ton_tot"] + r["ban_tot"] + 0.0001) * 100, 1), axis=1)
        
        export_cols = {
            "MaHang": "Mã Hàng",
            "Report_item_name": "Tên Mặt Hàng",
        }
        for reg in regions_list:
            export_cols[f"{reg}_Tồn"] = f"{reg} (Tồn)"
            export_cols[f"{reg}_Bán"] = f"{reg} (Bán)"
            export_cols[f"{reg}_TLB"] = f"{reg} (Tỷ Lệ Bán)"
            
        export_cols["ton_tot"] = "Tổng Tồn"
        export_cols["ban_tot"] = "Tổng Bán"
        export_cols["rate_tot"] = "Tỷ Lệ Bán (%)"
        
        agg = sku_agg
        filename = f"Bao_Cao_Chi_Tiet_Group_{selected_grp or 'All'}"
        
    ex_out = agg[list(export_cols.keys())].rename(columns=export_cols)
    
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        ex_out.to_excel(writer, sheet_name="Báo cáo", index=False)
        ws = writer.sheets["Báo cáo"]
        ws.freeze_panes(1, 0)
        ws.set_column('A:Z', 16)
        
    out.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return send_file(
        out,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"{filename}_{ts}.xlsx"
    )


# --- DATA PAGE ---
@app.route("/data")
def data_page():
    u = user()
    fv = get_fv()
    try:
        df = load_inventory()
    except Exception as e:
        return page("Error", f'<div class="flash e">Lỗi nạp database: {e}</div>', u)
        
    filtered = apply_f(df, fv)
    s = build_summary(filtered)
    cards = "".join(f'<div class="C"><div class="ci">{c.get("icon","")}</div><div class="l">{c["label"]}</div><div class="v">{fmt(c["value"])}</div></div>' for c in s["cards"])
    
    cols = ["Group", "Region", "Store_RP", "Store_rank", "MaHang", "Operation", "Size", 
            "Ton_Size", "Ban_Size", "SL_Đề_Xuất", "Ton_Sau_Dieu_Chuyen", "Cửa_Hàng_Đối_Tác", "Hành_Động", "Trang_Thai"]
            
    return page("Inventory Details", f"""
    {filt_form(df, fv)}
    <div class="G">{cards}</div>
    <div class="S">
        <h3>📦 Dữ liệu chi tiết tồn kho ({filtered['MaHang'].nunique():,} SKU khác nhau)</h3>
        {tbl(filtered.sort_values(['MaHang', 'Store_RP', 'Size']), cols, paginate=True, per_page=100)}
    </div>
    """, u)


# --- PRODUCT PAGE (PRODUCT FINDER & GALLERY) ---
@app.route("/product")
def product_page():
    u = user()
    fv = get_fv()
    try:
        df = load_inventory()
    except Exception as e:
        return page("Error", f'<div class="flash e">Lỗi nạp database: {e}</div>', u)
        
    filtered = apply_f(df, fv)
    mahang = (fv.get("MaHang", "") or fv.get("search", "")).strip().upper()
    
    # Custom filter panel
    search_html = f"""
    <div class="F">
        <h3>🔍 Product Finder</h3>
        <form method="get">
            <div class="fg">
                <div>
                    <label>Quick Search SKU</label>
                    <input name="search" value="{fv.get('search','')}" placeholder="Ví dụ: ASN002722" autofocus>
                </div>
            </div>
            <div style="margin-top:14px">
                <button class="btn">Search Product</button>
                <a class="btn btn-sec" href="/product">Reset</a>
            </div>
        </form>
    </div>
    """
    
    if not mahang:
        # Gallery View of products with Groups filter and Pagination
        active_group = request.args.get("group", "").strip()
        page_num = request.args.get("page", 1)
        try:
            page_num = int(page_num)
        except ValueError:
            page_num = 1
            
        in_stock = filtered[filtered["Ton_Size"] > 0]
        if in_stock.empty:
            return page("Products", search_html + '<div class="info">Không có mã hàng nào còn tồn kho.</div>', u)
            
        # Filter by Group if chosen
        if active_group:
            in_stock = in_stock[in_stock["Group"] == active_group]
            if in_stock.empty:
                # Render the group pills even when empty so they can switch back!
                unique_groups = ["Group A", "Group B", "Group D", "Group E"]
                group_tabs_html = '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; align-items:center;">'
                all_style = "background:rgba(255,255,255,0.02); border:1px solid var(--border); color:var(--t2);"
                group_tabs_html += f'<a href="?group=&search={fv.get("search","")}" class="btn" style="{all_style} padding:6px 14px; font-size:12.5px; border-radius:30px; text-decoration:none; display:inline-flex; align-items:center; gap:6px;">🏷️ Tất cả</a>'
                group_colors = {"Group A": "#34d399", "Group B": "#f59e0b", "Group D": "#ec4899", "Group E": "#6366f1"}
                for g in unique_groups:
                    is_active = active_group == g
                    color = group_colors.get(g, "#60a5fa")
                    if is_active:
                        style = f"background:rgba(255,255,255,0.08); border: 2px solid {color}; color:#fff; font-weight:700; box-shadow:0 0 12px {color}40;"
                    else:
                        style = f"background:rgba(255,255,255,0.02); border:1px solid var(--border); color:var(--t2);"
                    icon = "🔴" if g == "Group A" else "🟢" if g == "Group B" else "🟣" if g == "Group D" else "🔵"
                    group_tabs_html += f'<a href="?group={urllib.parse.quote(g)}&search={fv.get("search","")}" class="btn" style="{style} padding:6px 14px; font-size:12.5px; border-radius:30px; text-decoration:none; display:inline-flex; align-items:center; gap:6px;">{icon} {g}</a>'
                group_tabs_html += '</div>'
                return page("Products", search_html + f'<div class="S"><h3>📋 Thông tin sản phẩm tại HTCH</h3>{group_tabs_html}<div class="info">Không có sản phẩm nào thuộc {active_group} còn tồn kho.</div></div>', u)
                
        agg = in_stock.groupby("MaHang").agg(
            ton=("Ton_Size", "sum"),
            ban=("Ban_Size", "sum"),
            report_name=("Report_item_name", "first"),
            group_val=("Group", "first")
        ).reset_index().sort_values("ton", ascending=False)
        
        # Paginate results
        import math
        limit = 24
        total_items = len(agg)
        total_pages = math.ceil(total_items / limit)
        page_num = max(1, min(page_num, total_pages)) if total_pages > 0 else 1
        
        start_idx = (page_num - 1) * limit
        end_idx = start_idx + limit
        agg_page = agg.iloc[start_idx : end_idx]
        
        # Render Group Pills Tabs HTML
        unique_groups = ["Group A", "Group B", "Group D", "Group E"]
        group_tabs_html = '<div style="display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; align-items:center;">'
        is_all_active = not active_group
        all_style = (
            "background:linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%); color:#fff; box-shadow:0 0 10px rgba(59, 130, 246, 0.4); border:none;" 
            if is_all_active else 
            "background:rgba(255,255,255,0.02); border:1px solid var(--border); color:var(--t2);"
        )
        group_tabs_html += f'<a href="?group=&search={fv.get("search","")}" class="btn" style="{all_style} padding:6px 14px; font-size:12.5px; border-radius:30px; text-decoration:none; display:inline-flex; align-items:center; gap:6px;">🏷️ Tất cả</a>'
        
        group_colors = {
            "Group A": "#34d399",
            "Group B": "#f59e0b",
            "Group D": "#ec4899",
            "Group E": "#6366f1"
        }
        for g in unique_groups:
            is_active = active_group == g
            color = group_colors.get(g, "#60a5fa")
            if is_active:
                style = f"background:rgba(255,255,255,0.08); border: 2px solid {color}; color:#fff; font-weight:700; box-shadow:0 0 12px {color}40;"
            else:
                style = f"background:rgba(255,255,255,0.02); border:1px solid var(--border); color:var(--t2);"
            icon = "🔴" if g == "Group A" else "🟢" if g == "Group B" else "🟣" if g == "Group D" else "🔵"
            group_tabs_html += f'<a href="?group={urllib.parse.quote(g)}&search={fv.get("search","")}" class="btn" style="{style} padding:6px 14px; font-size:12.5px; border-radius:30px; text-decoration:none; display:inline-flex; align-items:center; gap:6px;">{icon} {g}</a>'
        group_tabs_html += '</div>'
        
        # Render Pagination HTML
        pagination_html = ""
        if total_pages > 1:
            pagination_html = '<div style="display:flex; justify-content:center; align-items:center; gap:8px; margin-top:35px; flex-wrap:wrap;">'
            
            def get_page_url(p):
                return f"?group={urllib.parse.quote(active_group)}&search={urllib.parse.quote(fv.get('search',''))}&page={p}"
                
            if page_num > 1:
                pagination_html += f'<a href="{get_page_url(page_num - 1)}" class="btn btn-sec" style="padding:6px 12px; font-size:12.5px; border-radius:6px; text-decoration:none;">« Trang trước</a>'
            else:
                pagination_html += f'<span class="btn btn-sec" style="padding:6px 12px; font-size:12.5px; border-radius:6px; opacity:0.4; cursor:not-allowed;">« Trang trước</span>'
                
            max_visible = 7
            start_page = max(1, page_num - 3)
            end_page = min(total_pages, start_page + max_visible - 1)
            if end_page - start_page < max_visible - 1:
                start_page = max(1, end_page - max_visible + 1)
                
            if start_page > 1:
                pagination_html += f'<a href="{get_page_url(1)}" class="btn btn-sec" style="padding:6px 10px; font-size:12.5px; border-radius:6px; text-decoration:none;">1</a>'
                if start_page > 2:
                    pagination_html += '<span style="color:var(--t2); padding:0 4px;">...</span>'
                    
            for p in range(start_page, end_page + 1):
                is_current = p == page_num
                if is_current:
                    style = "background:linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color:#fff; border:none; box-shadow:0 0 10px rgba(99,102,241,0.5);"
                    pagination_html += f'<span class="btn" style="{style} padding:6px 12px; font-size:12.5px; border-radius:6px; font-weight:700;">{p}</span>'
                else:
                    pagination_html += f'<a href="{get_page_url(p)}" class="btn btn-sec" style="padding:6px 12px; font-size:12.5px; border-radius:6px; text-decoration:none;">{p}</a>'
                    
            if end_page < total_pages:
                if end_page < total_pages - 1:
                    pagination_html += '<span style="color:var(--t2); padding:0 4px;">...</span>'
                pagination_html += f'<a href="{get_page_url(total_pages)}" class="btn btn-sec" style="padding:6px 10px; font-size:12.5px; border-radius:6px; text-decoration:none;">{total_pages}</a>'
                
            if page_num < total_pages:
                pagination_html += f'<a href="{get_page_url(page_num + 1)}" class="btn btn-sec" style="padding:6px 12px; font-size:12.5px; border-radius:6px; text-decoration:none;">Trang sau »</a>'
            else:
                pagination_html += f'<span class="btn btn-sec" style="padding:6px 12px; font-size:12.5px; border-radius:6px; opacity:0.4; cursor:not-allowed;">Trang sau »</span>'
                
            pagination_html += f'<div style="width:100%; text-align:center; font-size:11.5px; color:var(--t2); margin-top:8px;">Hiển thị {start_idx + 1} - {min(end_idx, total_items)} trên tổng số {total_items} sản phẩm (Trang {page_num}/{total_pages})</div>'
            pagination_html += '</div>'
            
        cards_html = ""
        for _, r in agg_page.iterrows():
            mh = r["MaHang"]
            rate = round(r["ban"] / (r["ton"] + r["ban"] + 0.0001) * 100, 1)
            q_mh = urllib.parse.quote(mh)
            cards_html += f"""
            <a href="?search={mh}" style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:12px;padding:16px;display:flex;flex-direction:column;gap:10px;color:var(--t);transition:var(--transition);position:relative;">
                <div style="width:100%;height:150px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.2);border-radius:8px;overflow:hidden;border:1px solid rgba(255,255,255,0.03);margin-bottom:6px;">
                    <img src="/image/{q_mh}" alt="{mh}" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                    <div style="display:none;font-size:36px;opacity:0.3;align-items:center;justify-content:center;width:100%;height:100%;">🏷️</div>
                </div>
                <div style="font-weight:bold;font-size:15px;color:var(--ac);text-align:center;">{mh}</div>
                <div style="font-size:11.5px;color:var(--t2);text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="{r['report_name']}">{r['report_name']}</div>
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:10px;border-top:1px solid rgba(255,255,255,0.05);padding-top:8px;">
                    <span style="color:#60a5fa">Tồn: <b>{fmt(r['ton'])}</b></span>
                    <span style="color:#34d399">Bán: <b>{fmt(r['ban'])}</b></span>
                    <span style="color:#fbbf24">TLB: <b>{rate}%</b></span>
                </div>
            </a>
            """
        gallery = f'<div class="S"><h3>📋 Thông tin sản phẩm tại HTCH</h3>{group_tabs_html}<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px;margin-top:16px;">{cards_html}</div>{pagination_html}</div>'
        return page("Products", search_html + gallery, u)
        
    prod_df = filtered[filtered["MaHang"].str.upper() == mahang]
    if prod_df.empty:
        prod_df = filtered[filtered["MaHang"].str.upper().str.contains(mahang, regex=False)]
        
    if prod_df.empty:
        return page("Product Info", search_html + f'<div class="flash e">Không tìm thấy mã hàng "{mahang}" trong hệ thống.</div>', u)
        
    p = prod_df.iloc[0]
    mh_actual = p["MaHang"]
    
    # SKUs totals
    ton = prod_df["Ton_Size"].sum()
    ban = prod_df["Ban_Size"].sum()
    chuyen = prod_df["SL_Đề_Xuất"].sum()
    stores = prod_df["Store_RP"].nunique()
    
    q_mh_actual = urllib.parse.quote(mh_actual)
    details = f"""
    <div style="display:grid;grid-template-columns:1fr 2fr;gap:20px;margin-top:20px">
        <div class="S" style="text-align:center;display:flex;flex-direction:column;justify-content:center;align-items:center;">
            <h3>Sản phẩm: {mh_actual}</h3>
            <div style="width:100%;height:320px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.15);border-radius:12px;overflow:hidden;border:1px solid var(--border);margin:20px 0;box-shadow:var(--shadow);">
                <img src="/image/{q_mh_actual}" alt="{mh_actual}" style="max-width:100%;max-height:100%;object-fit:contain;transition:all 0.3s ease;" onmouseover="this.style.transform='scale(1.05)';" onmouseout="this.style.transform='scale(1)';" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                <div style="display:none;font-size:100px;opacity:0.6;align-items:center;justify-content:center;width:100%;height:100%;">🏷️</div>
            </div>
            <p style="color:var(--t2)">Hình ảnh mặt hàng {mh_actual}</p>
        </div>
        <div>
            <div class="G" style="margin-top:0">
                <div class="C"><div class="l">Tổng Tồn</div><div class="v">{fmt(ton)}</div></div>
                <div class="C"><div class="l">Tổng Bán</div><div class="v">{fmt(ban)}</div></div>
                <div class="C"><div class="l">Chuyển đi</div><div class="v">{fmt(chuyen)}</div></div>
                <div class="C"><div class="l">Số Cửa hàng</div><div class="v">{fmt(stores)}</div></div>
            </div>
            <div class="S" style="margin-top:16px">
                <h3>Thông tin chung</h3>
                <table style="width:100%">
                    <tr><td style="color:var(--t2);width:30%">Tên mặt hàng</td><td><b>{p.get('Report_item_name','')}</b></td></tr>
                    <tr><td style="color:var(--t2)">Phân loại (Group)</td><td>{p.get('Group','')}</td></tr>
                    <tr><td style="color:var(--t2)">KHPP / Dis.Plan</td><td>{p.get('Dist_plan','')}</td></tr>
                    <tr><td style="color:var(--t2)">Màu sắc</td><td>{p.get('Color_group','')}</td></tr>
                    <tr><td style="color:var(--t2)">Form dáng</td><td>{p.get('Form','')}</td></tr>
                    <tr><td style="color:var(--t2)">Style</td><td>{p.get('Style','')}</td></tr>
                    <tr><td style="color:var(--t2)">Brand</td><td>{p.get('Brand','')}</td></tr>
                </table>
            </div>
        </div>
    </div>
    <div class="S" style="margin-top:20px">
        <h3>📍 Chi tiết phân bổ tại các shop</h3>
        {tbl(prod_df.sort_values(['Region', 'Store_RP', 'Size']), ["Region", "Store_RP", "Store_rank", "Size", "Ton_Size", "Ban_Size", "SL_Đề_Xuất", "Ton_Sau_Dieu_Chuyen", "Hành_Động", "Trang_Thai"])}
    </div>
    """
    return page(f"Product {mh_actual}", search_html + details, u)


# --- TRANSFER BOARD ---
@app.route("/transfer")
def transfer_page():
    u = user()
    fv = get_fv()
    try:
        df = load_inventory()
    except Exception as e:
        return page("Error", f'<div class="flash e">Lỗi nạp database: {e}</div>', u)
        
    filtered = apply_f(df, fv)
    has_tf = filtered[filtered["SL_Đề_Xuất"] > 0]
    s = build_summary(filtered)
    cards = "".join(f'<div class="C"><div class="ci">{c.get("icon","")}</div><div class="l">{c["label"]}</div><div class="v">{fmt(c["value"])}</div></div>' for c in s["cards"])
    
    cols = ["Group", "Region", "Store_RP", "MaHang", "Size", "Ton_Size", "SL_Đề_Xuất", "Ton_Sau_Dieu_Chuyen", "Cửa_Hàng_Đối_Tác", "Hành_Động"]
    return page("Transfer Board", f"""
    {filt_form(df, fv)}
    <div class="G">{cards}</div>
    <div class="S">
        <h3>🔀 Đề xuất lệnh điều chuyển chi tiết size ({has_tf['MaHang'].nunique():,} SKU cần điều chuyển)</h3>
        {tbl(has_tf.sort_values(['Group', 'MaHang', 'Store_RP', 'Size']), cols, paginate=True, per_page=100)}
    </div>
    """, u)


# --- REVIEW CENTER ---
@app.route("/review", methods=["GET", "POST"])
def review_page():
    u = user()
    if not can_review():
        flash("Không có quyền duyệt lệnh.", "err")
        return redirect("/dashboard")
        
    if request.method == "POST":
        ids = request.form.getlist("order_ids")
        action = request.form.get("action")
        note = request.form.get("note", "")
        if ids and action in ("approved", "rejected", "pending"):
            n = update_review(ids, action, u.get("display_name", u["username"]), note)
            flash(f"Đã duyệt trạng thái '{STATUS_LABELS.get(action,action)}' cho {n} lệnh.")
        else:
            flash("Chọn ít nhất một lệnh và một hành động duyệt.", "err")
        return redirect("/review")
        
    fv = {k: request.args.get(k, "") for k in ["review_status", "Report_item_name", "Ma hang", "Group", "search"]}
    try:
        df = merge_transfer_with_review()
    except Exception as e:
        return page("Error", f'<div class="flash e">Lỗi nạp lệnh điều chuyển: {e}</div>', u)
        
    # Filters in review page
    cols = ["review_status", "Report_item_name", "Ma hang", "Group"]
    opts = get_smart_opts(df, fv, cols)
    
    rows = ""
    for k, label in [("review_status", "Duyệt"), ("Report_item_name", "Report Item"), ("Group", "Group"), ("Ma hang", "SKU")]:
        os_html = ""
        for v in opts.get(k, []):
            lbl = STATUS_LABELS.get(v, v) if k == "review_status" else v
            os_html += f'<option value="{v}" {"selected" if fv.get(k)==v else ""}>{lbl}</option>'
        rows += f'<div><label>{label}</label><select name="{k}"><option value="">-- Tất cả --</option>{os_html}</select></div>'
    sv = fv.get("search", "")
    rows += f'<div><label>Search</label><input name="search" value="{sv}" placeholder="Shop, SKU..."></div>'
    
    filter_html = f'<div class="F"><h3>🔍 Review Filters</h3><form method="get"><div class="fg">{rows}</div><div style="margin-top:14px"><button class="btn">Apply Filter</button><a class="btn btn-sec" href="/review">Clear</a></div></form></div>'
    
    # Filter df
    r = df.copy()
    for k in ["review_status", "Report_item_name", "Ma hang", "Group"]:
        if fv.get(k):
            r = r[r[k].astype(str) == str(fv[k])]
    if fv.get("search"):
        s = fv["search"].upper()
        h = r[["Ma hang", "Operation", "CH Nguon", "CH Nhan", "Report_item_name", "Size"]].fillna("").astype(str).agg(" ".join, axis=1).str.upper()
        r = r[h.str.contains(s, regex=False)]
        
    # Status totals
    tot = len(df)
    app = len(df[df["review_status"] == "approved"])
    rej = len(df[df["review_status"] == "rejected"])
    pen = len(df[df["review_status"] == "pending"])
    
    stats = f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:18px;">
        <div class="C" style="--ac-gradient:linear-gradient(135deg,var(--ac),var(--ac));"><div class="l">Tổng số lệnh</div><div class="v">{tot:,}</div></div>
        <div class="C" style="--ac-gradient:linear-gradient(135deg,var(--ok),var(--ok));"><div class="l">Đã duyệt</div><div class="v">{app:,}</div></div>
        <div class="C" style="--ac-gradient:linear-gradient(135deg,var(--err),var(--err));"><div class="l">Rose Từ chối</div><div class="v">{rej:,}</div></div>
        <div class="C" style="--ac-gradient:linear-gradient(135deg,var(--w),var(--w));"><div class="l">Chờ duyệt</div><div class="v">{pen:,}</div></div>
    </div>
    """
    
    tbl_cols = ["Group", "Ma hang", "Size", "CH Nguon", "Khu vuc Nguon", "CH Nhan", "Khu vuc Nhan", "So luong chuyen", "Loai dieu chuyen", "review_status", "review_note", "reviewed_by", "reviewed_at"]
    
    body = f"""
    {stats}
    {filter_html}
    <div class="S">
        <h3>✅ Review Transfer Orders</h3>
        <form method="post">
            <div style="background:rgba(255,255,255,0.02);padding:16px;border-radius:8px;border:1px solid var(--border);margin-bottom:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                <span style="font-weight:700;font-size:13.5px;color:#fff;">Hành động duyệt hàng loạt:</span>
                <button name="action" value="approved" class="btn" style="background:var(--ok)">Duyệt Chọn</button>
                <button name="action" value="rejected" class="btn" style="background:var(--err)">Từ Chối Chọn</button>
                <button name="action" value="pending" class="btn btn-sec">Reset Chờ duyệt</button>
                <input name="note" placeholder="Nhập ghi chú duyệt (tùy chọn)..." style="flex:1;min-width:200px;background:#030712;color:#fff;border:1px solid var(--border);border-radius:6px;padding:9px 12px;font-size:13px;">
            </div>
            {tbl(r.sort_values(['review_status', 'Ma hang']), tbl_cols, limit=500, check=True)}
        </form>
    </div>
    """
    return page("Review Center", body, u)


# --- EXPORT REPORT ---
@app.route("/export", methods=["GET", "POST"])
def export_page():
    u = user()
    if not can_review():
        flash("Không có quyền xuất dữ liệu.", "err")
        return redirect("/dashboard")
        
    try:
        df = merge_transfer_with_review()
    except Exception as e:
        return page("Error", f'<div class="flash e">Lỗi nạp database xuất: {e}</div>', u)
        
    if request.method == "POST":
        mode = request.form.get("mode", "all")
        
        # Filter transfers based on review
        if mode == "approved":
            ex = df[df["review_status"] == "approved"]
        elif mode == "rejected":
            ex = df[df["review_status"] == "rejected"]
        else:
            ex = df
            
        if ex.empty:
            flash("Không có dữ liệu phù hợp để xuất.", "err")
            return redirect("/export")
            
        # Compile clean excel sheet
        out = io.BytesIO()
        
        # Rename back to beautiful Vietnamese columns for export
        export_map = {
            "Group": "Group",
            "Ma hang": "Mã Hàng",
            "Operation": "Operation",
            "Size": "Size",
            "CH Nguon": "Từ Cửa Hàng",
            "Khu vuc Nguon": "Từ Vùng",
            "CH Nhan": "Đến Cửa Hàng",
            "Khu vuc Nhan": "Đến Vùng",
            "So luong chuyen": "Số Lượng",
            "Loai dieu chuyen": "Cung KV",
            "review_status": "Trạng thái Duyệt",
            "reviewed_by": "Người Duyệt",
            "reviewed_at": "Thời gian Duyệt",
            "review_note": "Ghi chú"
        }
        
        ex_out = ex[list(export_map.keys())].rename(columns=export_map)
        ex_out["Trạng thái Duyệt"] = ex_out["Trạng thái Duyệt"].map(STATUS_LABELS)
        
        with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
            ex_out.to_excel(writer, sheet_name="Lenh_Dieu_Chuyen_Duyet", index=False)
            
            # Format sheet
            ws = writer.sheets["Lenh_Dieu_Chuyen_Duyet"]
            ws.freeze_panes(1, 0)
            ws.set_column('A:O', 16)
            
        out.seek(0)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        return send_file(
            out,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"Transfer_Orders_Reviewed_{mode}_{ts}.xlsx"
        )
        
    tot = len(df)
    app_c = len(df[df["review_status"] == "approved"])
    rej_c = len(df[df["review_status"] == "rejected"])
    
    body = f"""
    <div class="S" style="max-width:550px;margin:30px auto;">
        <h3>📥 Export Reviewed Transfer Orders</h3>
        <p style="color:var(--t2);margin-bottom:20px;">Tải xuống tệp Excel chứa các đề xuất lệnh điều phối sản phẩm đã được phê duyệt hoặc toàn bộ danh sách.</p>
        
        <form method="post">
            <div style="background:rgba(255,255,255,0.02);padding:20px;border-radius:10px;border:1px solid var(--border);margin-bottom:20px;display:flex;flex-direction:column;gap:12px;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <input type="radio" name="mode" value="approved" id="m_app" checked style="width:16px;height:16px;">
                    <label for="m_app" style="margin:0;cursor:pointer;">Chỉ xuất các lệnh <b>ĐÃ DUYỆT</b> ({app_c:,} lệnh)</label>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <input type="radio" name="mode" value="all" id="m_all" style="width:16px;height:16px;">
                    <label for="m_all" style="margin:0;cursor:pointer;">Xuất <b>TOÀN BỘ</b> trạng thái ({tot:,} lệnh)</label>
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    <input type="radio" name="mode" value="rejected" id="m_rej" style="width:16px;height:16px;">
                    <label for="m_rej" style="margin:0;cursor:pointer;">Chỉ xuất các lệnh bị <b>TỪ CHỐI</b> ({rej_c:,} lệnh)</label>
                </div>
            </div>
            
            <button class="btn" style="width:100%;padding:12px;font-size:14px;">📥 Download Excel Report</button>
        </form>
    </div>
    """
    return page("Export", body, u)


# --- FILE IMPORT ---
@app.route("/import_data", methods=["GET", "POST"])
def import_page():
    u = user()
    if not can_review():
        flash("Không có quyền tải lên.", "err")
        return redirect("/dashboard")
        
    if request.method == "POST":
        f = request.files.get("file")
        if f and f.filename:
            path = DATA_DIR / "Reallocation_Database.xlsx"
            os.makedirs(DATA_DIR, exist_ok=True)
            f.save(path)
            flash("Tải lên cơ sở dữ liệu thành công! Bộ nhớ tạm đã được làm mới.")
        else:
            flash("Vui lòng chọn một tệp Excel hợp lệ để tải lên.", "err")
        return redirect("/import_data")
        
    body = f"""
    <div class="S" style="max-width:550px;margin:30px auto;">
        <h3>📤 Upload Excel Database</h3>
        <p style="color:var(--t2);margin-bottom:20px;">Tải lên trực tiếp tệp <b>Reallocation_Database.xlsx</b> được kết xuất từ công cụ phân tích để xem nhanh và duyệt trên nền tảng web.</p>
        
        <form method="post" enctype="multipart/form-data">
            <div style="border: 2px dashed var(--border);border-radius:10px;padding:30px;text-align:center;background:rgba(255,255,255,0.01);margin-bottom:20px;display:flex;flex-direction:column;gap:10px;align-items:center;">
                <span style="font-size:40px;">📊</span>
                <label style="font-weight:700;color:#fff;">Chọn tệp Excel Reallocation_Database.xlsx</label>
                <input type="file" name="file" accept=".xlsx" style="background:transparent;border:none;color:var(--t2);font-size:13px;width:100%;max-width:300px;">
            </div>
            
            <button class="btn" style="width:100%;padding:12px;font-size:14px;">📤 Tải lên & Xem Database</button>
        </form>
    </div>
    """
    return page("Import", body, u)


# --- AUDIT & ADMIN ---
@app.route("/audit")
def audit_page():
    u = user()
    if not is_admin():
        flash("Quyền quản trị viên yêu cầu.", "err")
        return redirect("/dashboard")
        
    rows = recent_audit_rows()
    t_rows = ""
    for r in rows:
        t_rows += f"""<tr>
            <td>{fmt(r.get('at',''))}</td>
            <td>{fmt(r.get('by',''))}</td>
            <td>{fmt(r.get('order_id',''))}</td>
            <td><span class="badge {'badge-ok' if r.get('old')=='approved' else 'badge-w' if r.get('old')=='pending' else 'badge-err'}">{STATUS_LABELS.get(r.get('old',''),r.get('old',''))}</span></td>
            <td><span class="badge {'badge-ok' if r.get('new')=='approved' else 'badge-w' if r.get('new')=='pending' else 'badge-err'}">{STATUS_LABELS.get(r.get('new',''),r.get('new',''))}</span></td>
            <td>{fmt(r.get('note',''))}</td>
        </tr>"""
        
    body = f"""
    <div class="S">
        <h3>📜 Audit Trail Logs</h3>
        <p style="color:var(--t2);margin-bottom:20px;">Theo dõi lịch sử duyệt lệnh điều chuyển chi tiết, người thao tác và lý do từ chối/đồng ý.</p>
        
        <div class="TW">
            <table>
                <thead>
                    <tr><th>Thời gian</th><th>Thành viên</th><th>Mã Lệnh ID</th><th>Trạng thái Cũ</th><th>Trạng thái Mới</th><th>Ghi chú duyệt</th></tr>
                </thead>
                <tbody>{t_rows or '<tr><td colspan="6" style="text-align:center;">Chưa có lịch sử thao tác nào được lưu</td></tr>'}</tbody>
            </table>
        </div>
    </div>
    """
    return page("Audit Logs", body, u)

@app.route("/admin", methods=["GET", "POST"])
def admin_page():
    u = user()
    if not is_admin():
        flash("Quyền quản trị viên yêu cầu.", "err")
        return redirect("/dashboard")
        
    if request.method == "POST":
        un = request.form.get("username")
        act = request.form.get("act")
        users = load_users()
        idx = users[users["username"] == un].index
        if not idx.empty:
            if act == "approve_user":
                users.at[idx[0], "is_active"] = "1"
                users.at[idx[0], "approval_status"] = "approved"
                flash(f"Đã kích hoạt tài khoản '{un}'.")
            elif act == "deactivate":
                users.at[idx[0], "is_active"] = "0"
                flash(f"Đã vô hiệu hóa tài khoản '{un}'.")
            elif act == "role_reviewer":
                users.at[idx[0], "role"] = "reviewer"
                flash(f"Đã cập nhật vai trò '{un}' thành Reviewer.")
            elif act == "role_viewer":
                users.at[idx[0], "role"] = "viewer"
                flash(f"Đã cập nhật vai trò '{un}' thành Viewer.")
            elif act == "delete":
                users = users.drop(idx)
                flash(f"Đã xóa tài khoản '{un}'.")
            save_users(users)
        return redirect("/admin")
        
    users = load_users()
    t_rows = ""
    for _, r in users.iterrows():
        act_btn = ""
        un = r["username"]
        role_label = ROLE_LABELS.get(r['role'], r['role'])
        
        if un != "Thong.Nguyen":  # Protect super admin
            if r["is_active"] == "0":
                act_btn += f'<button name="act" value="approve_user" class="btn" style="padding:4px 10px;font-size:10px;background:var(--ok)">Kích Hoạt</button> '
            else:
                act_btn += f'<button name="act" value="deactivate" class="btn btn-sec" style="padding:4px 10px;font-size:10px;">Vô hiệu hóa</button> '
                
            if r["role"] == "viewer":
                act_btn += f'<button name="act" value="role_reviewer" class="btn" style="padding:4px 10px;font-size:10px;background:var(--ac)">Lên Reviewer</button> '
            elif r["role"] == "reviewer":
                act_btn += f'<button name="act" value="role_viewer" class="btn btn-sec" style="padding:4px 10px;font-size:10px;">Xuống Viewer</button> '
                
            act_btn += f'<button name="act" value="delete" class="btn" style="padding:4px 10px;font-size:10px;background:var(--err)" onclick="return confirm(\'Xóa thành viên này?\')">Xóa</button>'
            
        t_rows += f"""<tr>
            <td><b>{un}</b></td>
            <td>{r.get('display_name','')}</td>
            <td>{role_label}</td>
            <td><span class="badge {'badge-ok' if r.get('is_active')=='1' else 'badge-err'}">{'Active' if r.get('is_active')=='1' else 'Inactive'}</span></td>
            <td>{r.get('approval_status','')}</td>
            <td><form method="post" style="margin:0;"><input type="hidden" name="username" value="{un}">{act_btn}</form></td>
        </tr>"""
        
    body = f"""
    <div class="S">
        <h3>⚙️ Admin Panel</h3>
        <p style="color:var(--t2);margin-bottom:20px;">Duyệt tài khoản mới đăng ký, điều chỉnh quyền truy cập nội bộ (Viewer, Reviewer, Admin).</p>
        
        <div class="TW">
            <table>
                <thead>
                    <tr><th>Tài khoản</th><th>Tên hiển thị</th><th>Quyền hạn</th><th>Trạng thái</th><th>Xét duyệt</th><th>Thao tác</th></tr>
                </thead>
                <tbody>{t_rows}</tbody>
            </table>
        </div>
    </div>
    """
    return page("Admin Settings", body, u)


# --- USER GUIDE ---
@app.route("/guide")
def guide_page():
    u = user()
    body = """
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({startOnLoad:true, theme:'dark'});</script>
    
    <div class="S">
        <h3>📖 Hướng dẫn Vận hành & Logic Điều chuyển hàng hóa</h3>
        <p style="color:var(--t2); margin-bottom:20px; font-size:14px; line-height:1.6;">
            Chào mừng bạn đến với <b>Reallocation Pro</b>. Hệ thống này được thiết kế để tự động hóa quy trình phân tích bán tồn, dự báo đứt size và đề xuất điều chuyển hàng tối ưu giữa các cửa hàng trên toàn quốc. Nhằm giúp bạn nắm rõ cách vận hành của hệ thống, dưới đây là chi tiết về logic tính toán và quy trình xử lý hàng hóa.
        </p>

        <!-- SƠ ĐỒ 1: QUY TRÌNH VẬN HÀNH -->
        <style>
        #sodo1 svg {
            min-width: 1400px !important;
            min-height: 220px !important;
            height: auto !important;
        }
        #sodo1 {
            width: 100%;
            overflow-x: auto;
            display: block !important;
            text-align: center;
            padding: 8px 0;
        }
        #sodo1 .node rect, #sodo1 .node polygon {
            stroke-width: 2.5px !important;
        }
        #sodo1 .node .label { font-size: 14px !important; }
        </style>
        <div style="margin-top:24px; background:linear-gradient(135deg,rgba(30,27,75,0.35),rgba(12,74,110,0.2)); border:1px solid rgba(99,102,241,0.3); padding:22px 24px; border-radius:14px; box-shadow:0 4px 24px rgba(99,102,241,0.08);">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:16px; font-size:16px; text-align:center; letter-spacing:0.3px;">📊 Sơ đồ 1 — Quy trình Vận hành &amp; Duyệt lệnh điều chuyển</h4>
            <div class="mermaid" id="sodo1" style="display:block; padding:10px 0;">
                %%{init: {"theme": "dark", "themeVariables": {"fontSize": "15px", "nodeBorder": "2px"}}}%%
                graph LR
                    A["🚀 Planner\nChạy Optimizer"] -->|Chọn Vùng, Tháng, SKU| B["⚙️ Động cơ\nTính toán & Phân tích"]
                    B --> C["✅ Review Center\nDuyệt lệnh đề xuất"]
                    C -->|Reviewer/Admin| D{{"🤔 Xét duyệt\nlệnh?"}}
                    D -->|Chấp thuận ✓| E["👍 Approved\nLệnh được duyệt"]
                    D -->|Từ chối ✗| F["👎 Rejected\nLệnh bị bác bỏ"]
                    E & F --> G["📜 Audit Trail\nLưu lịch sử hệ thống"]
                    G --> H["📥 Export File\nXuất tệp lệnh Excel"]
                    H -->|Đóng gói & giao hàng| I["📦 Kho/Shop\nVận hành thực tế"]

                    style A fill:#1e1b4b,stroke:#6366f1,stroke-width:2.5px,color:#c7d2fe
                    style B fill:#0c4a6e,stroke:#0284c7,stroke-width:2.5px,color:#bae6fd
                    style C fill:#1e1b4b,stroke:#818cf8,stroke-width:2.5px,color:#c7d2fe
                    style D fill:#3f1a04,stroke:#f59e0b,stroke-width:2.5px,color:#fde68a
                    style E fill:#064e3b,stroke:#10b981,stroke-width:2.5px,color:#6ee7b7
                    style F fill:#450a0a,stroke:#f43f5e,stroke-width:2.5px,color:#fca5a5
                    style G fill:#1e293b,stroke:#3b82f6,stroke-width:2.5px,color:#93c5fd
                    style H fill:#2d1b69,stroke:#a855f7,stroke-width:2.5px,color:#d8b4fe
                    style I fill:#064e3b,stroke:#34d399,stroke-width:2.5px,color:#6ee7b7
            </div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:20px;">
            <div style="background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
                <h4 style="color:var(--ac); margin-top:0; margin-bottom:12px; font-size:15px; display:flex; align-items:center; gap:8px;">🎯 Wed này dùng làm gì?</h4>
                <p style="font-size:13px; color:var(--t2); line-height:1.6; margin:0;">
                    Hệ thống Reallocation Pro giải quyết bài toán <b>tồn kho cục bộ</b> (nơi thừa nơi thiếu size) bằng cách:<br>
                    • <b>Đẩy nhanh tốc độ quay vòng hàng hóa</b>: Chuyển hàng từ những nơi bán chậm về những nơi bán chạy.<br>
                    • <b>Tối ưu hóa cơ cấu size</b>: Tránh tình trạng đứt size tại các cửa hàng trọng điểm, gia tăng tối đa doanh số bán.<br>
                    • <b>Tự động hóa 100%</b>: Cắt giảm hoàn toàn quy trình tính toán thủ công và duyệt lệnh rườm rà.
                </p>
            </div>
            <div style="background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
                <h4 style="color:var(--ac); margin-top:0; margin-bottom:12px; font-size:15px; display:flex; align-items:center; gap:8px;">⚡ Quy trình vận hành 3 bước</h4>
                <p style="font-size:13px; color:var(--t2); line-height:1.6; margin:0;">
                    <b>Bước 1: Chạy lệnh điều chuyển (Optimizer)</b><br>
                    Chọn mặt hàng, số tháng bán gần đây và các khu vực tham gia điều chuyển ➔ Hệ thống tính toán đề xuất.<br>
                    <b>Bước 2: Duyệt lệnh (Review Center)</b><br>
                    Cấp quản lý (Reviewer/Admin) xem chi tiết, điều chỉnh số lượng hoặc phê duyệt/tối thiểu từ chối đề xuất.<br>
                    <b>Bước 3: Xuất lệnh & Vận hành (Export)</b><br>
                    Xuất file Excel chứa các lệnh đã duyệt ➔ Gửi cho kho và cửa hàng để đóng gói, chuyển đi.
                </p>
            </div>
        </div>

        <!-- SƠ ĐỒ 2A: PHÂN NHÓM SẢN PHẨM -->
        <div style="margin-top:24px; background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:14px; font-size:15px; text-align:center;">📊 Sơ đồ 2A: Cây quyết định Phân nhóm sản phẩm (Group A - E) (Trực quan hóa)</h4>
            <div class="mermaid" style="display:flex; justify-content:center; padding:10px 0;">
                graph TD
                    A["Mặt hàng nạp vào Optimizer 🚀"] --> B{{"Kiểm tra Điều kiện? ⚙️"}}
                    B -->|Tuổi hàng < 6 tháng| C["Group D: Hàng Mới 🆕 <br> ➔ Giữ nguyên hiện trạng"]
                    B -->|Tồn toàn quốc < 20 cái| D["Group E: Tồn quá thấp ⚠️ <br> ➔ Giữ nguyên hiện trạng"]
                    B -->|Sell-Through ST > 80%| E["Group A: Bán chạy 🔥 <br> ➔ Tối ưu gom về cửa hàng rank-I"]
                    B -->|30% <= ST <= 80%| F["Group B: Bán ổn định 📈 <br> ➔ Điều phối 2 bước cân bằng"]
                    B -->|ST < 30%| G["Group C: Bán chậm ❄️ <br> ➔ Giữ nguyên hiện trạng"]

                    style A fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff
                    style B fill:#3f1a04,stroke:#d97706,stroke-width:2px,color:#fff
                    style C fill:#083344,stroke:#06b6d4,stroke-width:2px,color:#fff
                    style D fill:#450a0a,stroke:#f43f5e,stroke-width:2px,color:#fff
                    style E fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                    style F fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff
                    style G fill:#1e293b,stroke:#475569,stroke-width:2px,color:#fff
            </div>
        </div>

        <div style="margin-top:24px; background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:14px; font-size:15px;">📦 Quy tắc xếp Nhóm sản phẩm (Group A - E)</h4>
            <p style="font-size:13px; color:var(--t2); line-height:1.6; margin-bottom:12px;">
                Mỗi mã hàng (SKU) sẽ được tự động xếp vào 1 trong 5 nhóm dựa trên tuổi hàng (Tháng XK), tỷ lệ bán toàn quốc (Sell-Through ST) và tồn kho:
            </p>
            <table style="width:100%; font-size:12.5px; border-collapse:collapse; text-align:left;">
                <thead>
                    <tr style="border-bottom:1px solid var(--border); color:#fff;">
                        <th style="padding:8px 0; width:15%">Nhóm hàng</th>
                        <th style="padding:8px 0; width:45%">Định nghĩa chi tiết</th>
                        <th style="padding:8px 0; width:20%">Điều kiện kỹ thuật</th>
                        <th style="padding:8px 0; width:20%">Hành động điều chuyển</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:10px 0;"><span class="badge badge-ok">Group A</span></td>
                        <td style="padding:10px 0; color:var(--t2)">Sản phẩm bán chạy toàn hệ thống có tỷ lệ bán trên 80%</td>
                        <td style="padding:10px 0;">ST > 80% & Tuổi hàng ≥ 6th</td>
                        <td style="padding:10px 0; color:#34d399"><b>Ưu tiên điều chuyển tối đa</b></td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:10px 0;"><span class="badge badge-ac" style="background:rgba(99, 102, 241, 0.2); color:#a5b4fc; border-color:rgba(99, 102, 241, 0.4)">Group B</span></td>
                        <td style="padding:10px 0; color:var(--t2)">Sản phẩm bán ổn định ở hệ thống, có tỷ lệ bán từ 30% đến 80%</td>
                        <td style="padding:10px 0;">30% ≤ ST ≤ 80% & Tuổi hàng ≥ 6th</td>
                        <td style="padding:10px 0; color:#818cf8"><b>Điều chuyển cân bằng</b></td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:10px 0;"><span class="badge badge-w">Group C</span></td>
                        <td style="padding:10px 0; color:var(--t2)">Sản phẩm bán chậm toàn quốc có tỷ lệ bán dưới 30%</td>
                        <td style="padding:10px 0;">ST < 30% & Tuổi hàng ≥ 6th</td>
                        <td style="padding:10px 0; color:var(--sub)">Giữ nguyên, không điều chuyển</td>
                    </tr>
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:10px 0;"><span class="badge badge-ac" style="background:rgba(6, 182, 212, 0.2); color:#67e8f9; border-color:rgba(6, 182, 212, 0.4)">Group D</span></td>
                        <td style="padding:10px 0; color:var(--t2)">Sản phẩm mới phân phối trong vòng 6 tháng gần nhất</td>
                        <td style="padding:10px 0;">Tuổi hàng < 6 tháng</td>
                        <td style="padding:10px 0; color:var(--sub)">Giữ nguyên, không điều chuyển</td>
                    </tr>
                    <tr>
                        <td style="padding:10px 0;"><span class="badge badge-err">Group E</span></td>
                        <td style="padding:10px 0; color:var(--t2)">Nhóm sản phẩm tồn kho toàn quốc dưới 20 cái (pcs)</td>
                        <td style="padding:10px 0;">Tồn toàn quốc < 20pcs</td>
                        <td style="padding:10px 0; color:var(--sub)">Giữ nguyên, không điều chuyển</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- SƠ ĐỒ 2B: LOGIC ĐIỀU PHỐI GROUP B -->
        <div style="margin-top:24px; background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:14px; font-size:15px; text-align:center;">🔄 Sơ đồ 2B: Logic Điều phối & Phân bổ Size cho Group B (Đa sắc màu & Icon)</h4>
            <div class="mermaid" style="display:flex; justify-content:center; padding:10px 0;">
                graph LR
                    subgraph NGUON_GUI ["Phía Nguồn đi 📤"]
                        S1["Shop Chậm bán ❄️"] -->|Chuyển 100% tồn size| P1["Pool Tồn khả dụng 📦"]
                        S2["Shop Chậm gần đây ⚠️"] -->|Chuyển phần tồn dư thừa| P1
                    end
                    
                    subgraph BO_PHAN_PHOI ["Ngân sách Phân bổ ⚖️"]
                        P1 --> D1{{"Phân bổ theo Budget? 🤔"}}
                        D1 -->|65% Budget| R1["Shop Bán rất chạy 🔥"]
                        D1 -->|35% Budget| R2["Shop Bán ổn định 📈"]
                    end
                    
                    subgraph CHIA_SIZE_TAI_DICH ["Phân bổ Size tại Đích 🎯"]
                        R1 --> A1["Tính lượng Cân nhận (ST 50%) 📊"]
                        R2 --> A1
                        A1 --> A2["Largest Remainder Method (LRM) 🔢 <br> chia theo tỷ lệ bán size của Đích"]
                    end

                    style S1 fill:#1e293b,stroke:#475569,stroke-width:2px,color:#fff
                    style S2 fill:#3f1a04,stroke:#d97706,stroke-width:2px,color:#fff
                    style P1 fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff
                    style D1 fill:#3f1a04,stroke:#d97706,stroke-width:2px,color:#fff
                    style R1 fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#fff
                    style R2 fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#fff
                    style A1 fill:#083344,stroke:#06b6d4,stroke-width:2px,color:#fff
                    style A2 fill:#1e1b4b,stroke:#a855f7,stroke-width:2px,color:#fff

                    style NGUON_GUI fill:#0f172a,stroke:#334155,stroke-width:1px,color:#fff
                    style BO_PHAN_PHOI fill:#0f172a,stroke:#334155,stroke-width:1px,color:#fff
                    style CHIA_SIZE_TAI_DICH fill:#0f172a,stroke:#334155,stroke-width:1px,color:#fff
            </div>
        </div>

        <div style="display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:20px;">
            <div style="background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
                <h4 style="color:var(--ac); margin-top:0; margin-bottom:12px; font-size:15px; display:flex; align-items:center; gap:8px;">📊 Tiêu chí xếp hạng Cửa hàng & Công thức Trạng thái Bán 2D</h4>
                <p style="font-size:13px; color:var(--t2); line-height:1.6; margin:0;">
                    Để phân phối chính xác cho Group B, hệ thống tự động đánh giá sức bán của từng cửa hàng dựa trên 2 chỉ số <b>All ST</b> và <b>Recent ST</b>:<br><br>
                    <b>1. Công thức tính toán chi tiết:</b><br>
                    • <b>All-time Sell-Through (All ST):</b><br>
                    <span style="display:block; background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:6px; font-family:monospace; margin:4px 0; color:#fff; border:1px solid rgba(255,255,255,0.04);">All ST = Tổng_Bán_All_Time / (Tổng_Bán_All_Time + Tồn_Kho_Hiện_Tại)</span>
                    <span style="font-size:11.5px; color:var(--sub); display:block; margin-bottom:10px;">➔ Đánh giá hiệu suất tiêu thụ lịch sử xuyên suốt của cửa hàng đối với mã sản phẩm.</span>
                    
                    • <b>Recent Sell-Through (Recent ST):</b><br>
                    <span style="display:block; background:rgba(0,0,0,0.25); padding:6px 10px; border-radius:6px; font-family:monospace; margin:4px 0; color:#fff; border:1px solid rgba(255,255,255,0.04);">Recent ST = Tổng_Bán_Gần_Đây / (Tổng_Bán_Gần_Đây + Tồn_Kho_Hiện_Tại)</span>
                    <span style="font-size:11.5px; color:var(--sub); display:block;">➔ Đánh giá tốc độ tiêu thụ thực tế gần đây (mặc định cấu hình 3 tháng gần nhất).</span>
                </p>
            </div>
            
            <div style="background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
                <h4 style="color:var(--ac); margin-top:0; margin-bottom:12px; font-size:15px;">🎯 Ma trận xếp hạng 2D & Hành động đề xuất</h4>
                <p style="font-size:13px; color:var(--t2); line-height:1.6; margin:0;">
                    Kết hợp 2 chỉ số trên, hệ thống phân loại cửa hàng thành 5 trạng thái 2D để đưa ra quyết định điều phối:<br><br>
                    • <b style="color:#10b981;">🟢 Bán rất chạy (Đích ưu tiên 1)</b>: All ST ≥ 75% & Recent ST ≥ 65%.<br>
                    <span style="font-size:11.5px; color:var(--sub); display:block; margin-left:14px; margin-bottom:6px;">➔ Ưu tiên nhận 65% ngân sách tồn khả dụng của Pool điều chuyển.</span>
                    
                    • <b style="color:#6366f1;">🔵 Bán ổn định (Đích ưu tiên 2)</b>: All ST ≥ 55% & Recent ST ≥ 40%.<br>
                    <span style="font-size:11.5px; color:var(--sub); display:block; margin-left:14px; margin-bottom:6px;">➔ Nhận 35% ngân sách tồn khả dụng của Pool điều chuyển.</span>
                    
                    • <b style="color:#f59e0b;">🟡 Chậm gần đây (Nguồn đi dư thừa)</b>: All ST ≥ 55% & Recent ST < 40%.<br>
                    <span style="font-size:11.5px; color:var(--sub); display:block; margin-left:14px; margin-bottom:6px;">➔ Chỉ chuyển đi phần tồn kho dư thừa vượt quá sức bán gần đây.</span>
                    
                    • <b style="color:#f43f5e;">🔴 Chậm bán (Nguồn đi 100%)</b>: All ST < 55% & Recent ST < 30%.<br>
                    <span style="font-size:11.5px; color:var(--sub); display:block; margin-left:14px; margin-bottom:6px;">➔ Chuyển đi sạch toàn bộ 100% lượng tồn size hiện có của cửa hàng.</span>
                    
                    • <b>⚪ Trung bình (Giữ nguyên)</b>: Các trường hợp còn lại (Giữ nguyên tồn hiện tại, không chuyển đi hay nhận thêm).
                </p>
            </div>
        </div>

        <!-- SƠ ĐỒ 3: MA TRẬN TRẠNG THÁI BÁN 2D -->
        <div style="margin-top:24px; background:linear-gradient(135deg,rgba(6,78,59,0.2),rgba(30,27,75,0.25)); border:1px solid rgba(16,185,129,0.25); padding:22px 24px; border-radius:14px; box-shadow:0 4px 24px rgba(16,185,129,0.06);">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:16px; font-size:16px; text-align:center;">🗺️ Sơ đồ 3 — Ma trận Xếp hạng Cửa hàng 2D (All ST × Recent ST)</h4>
            <div class="mermaid" style="display:block; padding:10px 0;">
                %%{init: {"theme": "dark", "themeVariables": {"fontSize": "14px"}}}%%
                graph TD
                    INPUT["🏪 Cửa hàng cần đánh giá\n(All ST + Recent ST)"] --> Q1{{"All ST ≥ 75%?"}}
                    Q1 -->|Có ✓| Q2{{"Recent ST ≥ 65%?"}}
                    Q1 -->|Không ✗| Q3{{"All ST ≥ 55%?"}}

                    Q2 -->|Có ✓| HOT["🟢 BÁN RẤT CHẠY\n🔥 Đích ưu tiên 1\n➔ Nhận 65% ngân sách Pool"]
                    Q2 -->|Không ✗| Q4{{"Recent ST ≥ 40%?"}}

                    Q3 -->|Có ✓| Q5{{"Recent ST ≥ 40%?"}}
                    Q3 -->|Không ✗| Q6{{"Recent ST < 30%?"}}

                    Q4 -->|Có ✓| STABLE["🔵 BÁN ỔN ĐỊNH\n📈 Đích ưu tiên 2\n➔ Nhận 35% ngân sách Pool"]
                    Q4 -->|Không ✗| SLOW_R["🟡 CHẬM GẦN ĐÂY\n⚠️ Nguồn đi (dư thừa)\n➔ Chuyển đi tồn dư = Tồn − Bán_recent"]

                    Q5 -->|Có ✓| STABLE
                    Q5 -->|Không ✗| SLOW_R

                    Q6 -->|Có ✓| DEAD["🔴 CHẬM BÁN\n❄️ Nguồn đi (100%)\n➔ Chuyển đi 100% tồn size"]
                    Q6 -->|Không ✗| NEUTRAL["⚪ TRUNG BÌNH\n➔ Giữ nguyên, không điều chuyển"]

                    style INPUT fill:#1e1b4b,stroke:#6366f1,stroke-width:2px,color:#c7d2fe
                    style Q1 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style Q2 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style Q3 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style Q4 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style Q5 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style Q6 fill:#3f1a04,stroke:#f59e0b,stroke-width:2px,color:#fde68a
                    style HOT fill:#064e3b,stroke:#10b981,stroke-width:2.5px,color:#6ee7b7
                    style STABLE fill:#1e1b4b,stroke:#6366f1,stroke-width:2.5px,color:#c7d2fe
                    style SLOW_R fill:#3f2204,stroke:#f59e0b,stroke-width:2.5px,color:#fde68a
                    style DEAD fill:#450a0a,stroke:#f43f5e,stroke-width:2.5px,color:#fca5a5
                    style NEUTRAL fill:#1e293b,stroke:#475569,stroke-width:2px,color:#94a3b8
            </div>
            <p style="font-size:12px; color:var(--sub); text-align:center; margin-top:8px; margin-bottom:0;">All ST = Tổng_Bán_All_Time / (Tổng_Bán_All_Time + Tồn_Hiện_Tại) &nbsp;|&nbsp; Recent ST = Bán_3_Tháng_Gần / (Bán_3_Tháng_Gần + Tồn_Hiện_Tại)</p>
        </div>

        <div style="background:rgba(255,255,255,0.015); border:1px solid var(--border); padding:20px; border-radius:12px; margin-top:20px;">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:12px; font-size:15px;">🔄 Logic Điều chuyển Chi tiết (Group A &amp; B)</h4>
            <p style="font-size:13px; color:var(--t2); line-height:1.6; margin:0;">
                <b>Quy tắc Điều chuyển cho Group A:</b><br>
                • Gom toàn bộ tồn kho tại các shop không phải rank-I (cửa hàng nhỏ/trung bình).<br>
                • Phân bổ về tất cả các cửa hàng rank-I (cửa hàng trọng điểm) nằm trong vùng bán chạy (Top 1 hoặc Top 1 + Top 2).<br><br>
                <b>Quy tắc Điều chuyển cho Group B:</b><br>
                • <b>Phía nguồn đi</b>: Shop "Chậm bán" chuyển 100% tồn size; Shop "Chậm gần đây" chỉ chuyển phần tồn dư thừa (Tồn size − Bán recent size).<br>
                • <b>Phía đích nhận</b>: Cân nhận = số cần để đạt ST 50%. Ngân sách ưu tiên 65% cho shop "Bán rất chạy" và 35% cho shop "Bán ổn định".<br>
                • <b>Chia size</b>: Chia theo tỷ lệ bán size của chính cửa hàng đích bằng phương pháp LRM (Largest Remainder Method).
            </p>
        </div>

        <!-- CẨM NANG THAO TÁC THEO VAI TRÒ -->
        <div style="margin-top:24px; background:rgba(255,255,255,0.01); border:1px solid var(--border); padding:20px; border-radius:12px;">
            <h4 style="color:var(--ac); margin-top:0; margin-bottom:14px; font-size:15px; text-align:center;">📋 Cẩm nang hướng dẫn thao tác theo Vai trò</h4>
            <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-top:10px;">
                <div style="background:rgba(0,0,0,0.1); padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.03);">
                    <h5 style="color:#60a5fa; margin-top:0; font-size:13px;">👨‍💻 Dành cho PLANNER (Phân phối)</h5>
                    <p style="font-size:11.5px; color:var(--t2); line-height:1.5; margin:0;">
                        1. Xem tỷ lệ bán và tồn kho tổng quan trên <b>Dasboarh</b> và <b>Reports Center</b>.<br>
                        2. Truy cập <b>Run Optimizer</b> (Chạy lệnh điều chuyển).<br>
                        3. Chọn mặt hàng, số tháng gần nhất (khuyến nghị 3 tháng) và khu vực tham gia điều chuyển.<br>
                        4. Nhấn <b>Chạy tối ưu hóa</b> và đợi hệ thống hoàn thành tính toán (khoảng 30 giây).
                    </p>
                </div>
                <div style="background:rgba(0,0,0,0.1); padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.03);">
                    <h5 style="color:#34d399; margin-top:0; font-size:13px;">🤵 Dành cho MANAGER (Quản lý duyệt)</h5>
                    <p style="font-size:11.5px; color:var(--t2); line-height:1.5; margin:0;">
                        1. Truy cập <b>Review Center</b> để xem danh sách các đề xuất điều chuyển chờ duyệt.<br>
                        2. Nhấp vào tên sản phẩm để xem hình ảnh thực tế và chi tiết phân bổ size giữa shop gửi & shop nhận.<br>
                        3. Click <b>Approve</b> (Duyệt) hoặc <b>Reject</b> (Bác bỏ), hoặc chỉnh sửa số lượng thực tế cần chuyển.<br>
                        4. Có thể chọn nhiều dòng và sử dụng nút <b>Duyệt hàng loạt</b> ở chân trang để tiết kiệm thời gian.
                    </p>
                </div>
                <div style="background:rgba(0,0,0,0.1); padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.03);">
                    <h5 style="color:#fbbf24; margin-top:0; font-size:13px;">📦 Dành cho WAREHOUSE / STORE (Kho & Shop)</h5>
                    <p style="font-size:11.5px; color:var(--t2); line-height:1.5; margin:0;">
                        1. Truy cập <b>Export File</b> để lọc và tải xuống tệp lệnh điều chuyển đã duyệt (trạng thái <i>approved</i>).<br>
                        2. Cửa hàng nguồn đóng gói hàng hóa theo đúng cột <b>Từ_Cửa_Hàng</b>, <b>Mã Hàng</b>, <b>Size</b> và <b>Số Lượng</b>.<br>
                        3. Dán nhãn địa chỉ shop nhận dựa vào cột <b>Đến_Cửa_Hàng</b> và bàn giao cho đơn vị vận chuyển.<br>
                        4. Cửa hàng đích kiểm đếm và xác nhận nhận hàng thành công.
                    </p>
                </div>
            </div>
        </div>
    </div>
    """
    return page("User Guide", body, u)


if __name__ == "__main__":
    DEV_MODE = False
    
    # Get server IPs for local network sharing
    ip_list = []
    try:
        hostname = socket.gethostname()
        ip_list = socket.gethostbyname_ex(hostname)[2]
    except Exception:
        pass
        
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        main_ip = s.getsockname()[0]
        if main_ip not in ip_list:
            ip_list.insert(0, main_ip)
    except Exception:
        pass
    finally:
        s.close()
        
    # Dynamically keep only the actual active IPv4 addresses resolved from network adapters
    ip_list = sorted(list(set([ip for ip in ip_list if ip and not ip.startswith("127.")])), key=lambda x: 0 if x.startswith("192.") or x.startswith("10.") else 1)
    if not ip_list:
        ip_list = ["127.0.0.1"]
        
    port = int(os.environ.get("PORT", "5050"))
    url = f"http://{ip_list[0]}:{port}"
    
    def safe_print(msg):
        try:
            print(msg)
        except Exception:
            try:
                print(msg.encode('ascii', 'ignore').decode('ascii'))
            except Exception:
                pass

    safe_print("\n" + "="*70)
    safe_print("  REALLOCATION PRO WEB APPLICATION LAUNCHED SUCCESSFULLY!")
    safe_print("  HE THONG DA SAN SANG CHIA SE TREN MANG NOI BO (LAN/WIFI)")
    safe_print("  TRUY CAP TRUC TIEP QUA CAC DIA CHI SAU:")
    for ip in ip_list:
        if not ip.startswith("127.") or len(ip_list) == 1:
            safe_print(f"    http://{ip}:{port}")
    safe_print("\n  (Hay chac chan cac thiet bi khac ket noi cung mang Wi-Fi hoac LAN)")
    safe_print(f"  CHE DO: {'DEVELOPMENT (Auto-reload)' if DEV_MODE else 'PRODUCTION (Multi-threaded)'}")
    safe_print("="*70 + "\n")
    
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        from threading import Timer
        Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
        
    try:
        app.run(host="0.0.0.0", port=port, debug=DEV_MODE, threaded=True)
    except Exception as e:
        print(f"Startup error: {e}")