"""
services_routes.py — Pages web interactives AION-Services.

Routes :
  GET  /services              → liste des services (avec recherche)
  GET  /services/{name}       → formulaire interactif du service
  POST /services/{name}/run   → exécute et retourne le résultat (htmx)
"""
import logging
import os
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


def _svc_url() -> str:
    port = int(os.getenv("AION_SERVICES_PORT", "8001"))
    return f"http://localhost:{port}"


def _get_services() -> list[dict]:
    """Récupère la liste des services depuis AION-Services."""
    try:
        import requests as _req
        r = _req.get(f"{_svc_url()}/api/services", timeout=2.0)
        return r.json().get("services", []) if r.status_code == 200 else []
    except Exception:
        return []


def _get_service(name: str) -> dict | None:
    try:
        import requests as _req
        r = _req.get(f"{_svc_url()}/api/services/{name}", timeout=2.0)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def _sidebar_html(active: str, version: str, ai_ok: bool) -> str:
    """Retourne le HTML complet de la page shell avec sidebar."""
    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
:root[data-theme="dark"]{{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--green:#4caf50;--red:#f44336;--hdr:#151821;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}}
header{{background:var(--hdr);border-bottom:2px solid var(--accent);
  padding:0 20px;height:52px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
header h1{{color:var(--accent);font-size:1.2rem;font-weight:700;}}
.spacer{{flex:1;}}
.hbtn{{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}}
.layout{{display:flex;flex:1;overflow:hidden;}}
.sidebar{{width:220px;background:var(--sb);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;padding:10px 0;}}
.sb-sec{{padding:4px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-top:8px;}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;
  border-left:3px solid transparent;font-size:.88rem;text-decoration:none;color:var(--text);}}
.nav-item:hover{{background:rgba(30,144,255,.08);}}
.nav-item.active{{background:rgba(30,144,255,.12);border-left-color:var(--accent);
  color:var(--accent);font-weight:600;}}
.nav-icon{{width:20px;text-align:center;}}
.nav-label{{flex:1;}}
.main{{flex:1;overflow-y:auto;padding:24px;}}
input,textarea,select{{background:var(--card);border:1px solid var(--border);
  color:var(--text);border-radius:6px;padding:8px 12px;font-size:.9rem;width:100%;
  font-family:inherit;outline:none;}}
input:focus,textarea:focus,select:focus{{border-color:var(--accent);}}
button.btn-primary{{background:var(--accent);color:#fff;border:none;border-radius:6px;
  padding:10px 24px;cursor:pointer;font-size:.9rem;font-weight:600;}}
button.btn-primary:hover{{opacity:.85;}}
</style></head>
<body>
<header>
  <span style="font-size:1.4rem;">🤖</span>
  <h1>AION-Core <span style="font-size:.75rem;color:var(--dim);font-weight:400;">v{version}</span></h1>
  <span class="spacer"></span>
  <span style="background:{'rgba(76,175,80,.2)' if ai_ok else 'rgba(244,67,54,.2)'};
    color:{'#4caf50' if ai_ok else '#f44336'};padding:2px 8px;border-radius:10px;
    font-size:.75rem;font-weight:600;">{'● Groq' if ai_ok else '● Groq offline'}</span>
  <a href="/" class="hbtn">Dashboard</a>
  <a href="/store" class="hbtn">App Store</a>
</header>
<div class="layout">
  <nav class="sidebar">
    <div class="sb-sec">Navigation</div>
    <a href="/" class="nav-item"><span class="nav-icon">🏠</span><span class="nav-label">Dashboard</span></a>
    <a href="/chat" class="nav-item"><span class="nav-icon">🤖</span><span class="nav-label">IA Chat</span></a>
    <div class="sb-sec">Apps</div>
    <div id="sidebar-apps"
         hx-get="/api/nav/apps/sidebar"
         hx-trigger="load"
         hx-swap="innerHTML"></div>
    <div class="sb-sec">AION</div>
    <a href="/store" class="nav-item"><span class="nav-icon">🏪</span><span class="nav-label">App Store</span></a>
    <a href="/services" class="nav-item {'active' if active == '__services__' else ''}">
      <span class="nav-icon">⚡</span><span class="nav-label">Services</span></a>
    <a href="/memory" class="nav-item"><span class="nav-icon">🧠</span><span class="nav-label">Memory</span></a>
    <a href="/settings" class="nav-item"><span class="nav-icon">⚙️</span><span class="nav-label">Settings</span></a>
  </nav>
  <main class="main" id="main-content">
"""


def _page_end() -> str:
    return """
  </main>
</div>
</body></html>"""


# ── Formulaires par service ──────────────────────────────────────────────────
SERVICE_FORMS = {
    "system_power": {
        "title":       "Controle Alimentation Windows",
        "icon":        "🔌",
        "description": "Veille, arret, redemarrage.",
        "action":      "sleep",
        "fields": [
            {"id": "action_type", "label": "Action",
             "type": "select", "options": ["sleep", "shutdown", "reboot", "cancel", "status"],
             "required": True, "placeholder": ""},
            {"id": "delay_min", "label": "Delai minutes (0=immediat)",
             "type": "number", "placeholder": "0", "required": False,
             "value": "0", "min": "0", "step": "1"},
        ]
    },
    "capacity_calc": {
        "title":       "Calcul de Capacité Projet",
        "icon":        "📊",
        "description": "Calcule la charge de travail quotidienne par personne sur une tâche.",
        "action":      "calculate",
        "fields": [
            {"id": "task_name",     "label": "Nom de la tâche",        "type": "text",
             "placeholder": "Ex: Développement module X", "required": False},
            {"id": "duration_days", "label": "Durée (jours ouvrables)", "type": "number",
             "placeholder": "Ex: 20", "required": True, "min": 1},
            {"id": "people",        "label": "Nombre de personnes",     "type": "number",
             "placeholder": "Ex: 2", "required": True, "min": 1, "value": "1"},
            {"id": "split",         "label": "Répartition (%)",         "type": "text",
             "placeholder": "Ex: 50/50 ou 80/20 ou 60/20/20 (laisser vide = égale)",
             "required": False},
            {"id": "hours_per_day", "label": "Heures de travail / jour","type": "number",
             "placeholder": "8", "required": False, "value": "8", "step": "0.5"},
        ]
    },
}


def _build_form(svc_name: str, svc_info: dict) -> str:
    """Génère le formulaire HTML interactif pour un service."""
    form_def = SERVICE_FORMS.get(svc_name)
    actions  = svc_info.get("actions", ["calculate"])
    desc     = svc_info.get("description", "")

    if form_def:
        icon   = form_def["icon"]
        title  = form_def["title"]
        fdesc  = form_def["description"]
        action = form_def["action"]
        fields_html = ""
        for f in form_def["fields"]:
            fid   = f["id"]
            freq  = "required" if f.get("required") else ""
            rstar = '<span style="color:#f44336;">*</span>' if f.get("required") else ""
            lbl   = f'<label style="display:block;font-size:.82rem;color:#888;margin-bottom:6px;">{f.get("label",fid)} {rstar}</label>'
            if f.get("type") == "select":
                opts = "".join(f'<option value="{o}">{o}</option>' for o in f.get("options",[]))
                js   = f"document.getElementById('svc-form').setAttribute('data-action',this.value);"
                inp  = f'<select id="{fid}" name="{fid}" {freq} onchange="{js}">{opts}</select>'
            else:
                xval  = f'value="{f["value"]}"' if f.get("value") not in (None,"") else ""
                xmin  = f'min="{f["min"]}"'      if f.get("min")   not in (None,"") else ""
                xstep = f'step="{f["step"]}"'    if f.get("step")  not in (None,"") else ""
                xph   = f.get("placeholder","") or ""
                inp   = f'<input type="{f.get("type","text")}" id="{fid}" name="{fid}" placeholder="{xph}" {freq} {xval} {xmin} {xstep}>'
            fields_html += f'<div style="margin-bottom:16px;">{lbl}{inp}</div>'

        # ── Layout deux colonnes pour capacity_calc ──────────────────────────
        if svc_name == "capacity_calc":
            return f"""
        <style>
          .cap-layout{{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start;}}
          @media(max-width:900px){{.cap-layout{{grid-template-columns:1fr;}}}}
          .cap-result-box{{background:var(--card);border:1px solid var(--border);
            border-radius:10px;padding:24px;min-height:200px;}}
          .cap-result-placeholder{{display:flex;align-items:center;justify-content:center;
            height:100%;min-height:180px;color:var(--dim);font-size:.9rem;text-align:center;}}
          .res-table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:.88rem;}}
          .res-table th{{background:rgba(30,144,255,.12);color:#1e90ff;padding:8px 10px;
            text-align:left;border-bottom:1px solid var(--border);}}
          .res-table td{{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.05);}}
          .res-table tr:hover td{{background:rgba(255,255,255,.03);}}
          .alert-row{{background:rgba(244,67,54,.08);}}
          .alert-row td{{color:#f44336;}}
          .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.78rem;
            font-weight:600;}}
          .badge-ok{{background:rgba(76,175,80,.15);color:#4caf50;}}
          .badge-warn{{background:rgba(244,67,54,.15);color:#f44336;}}
          .stat-row{{display:flex;gap:12px;margin:14px 0;flex-wrap:wrap;}}
          .stat-card{{background:rgba(30,144,255,.08);border:1px solid rgba(30,144,255,.2);
            border-radius:8px;padding:10px 16px;flex:1;min-width:110px;text-align:center;}}
          .stat-val{{font-size:1.3rem;font-weight:700;color:#1e90ff;}}
          .stat-lbl{{font-size:.72rem;color:var(--dim);margin-top:2px;}}
          #svc-result{{animation:fadeIn .3s ease;}}
          @keyframes fadeIn{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
        </style>
        <div>
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
            <span style="font-size:2rem;">{icon}</span>
            <div>
              <h2 style="font-size:1.2rem;font-weight:700;">{title}</h2>
              <p style="color:#888;font-size:.85rem;margin-top:2px;">{fdesc}</p>
            </div>
          </div>
          <div class="cap-layout">
            <!-- Colonne gauche : formulaire -->
            <div style="background:var(--card);border:1px solid var(--border);
                 border-radius:10px;padding:24px;">
              <form id="svc-form" onsubmit="runCapacity(event)"
                    data-svc="{svc_name}" data-action="{action}">
                {fields_html}
                <button type="submit" class="btn-primary" style="margin-top:8px;width:100%;">
                  ▶ Calculer
                </button>
              </form>
            </div>
            <!-- Colonne droite : résultat -->
            <div class="cap-result-box">
              <div id="svc-result">
                <div class="cap-result-placeholder">
                  <div>
                    <div style="font-size:2rem;margin-bottom:10px;">📊</div>
                    <div>Le résultat apparaîtra ici<br>après le calcul</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <script>
        function runCapacity(e) {{
          e.preventDefault();
          var form = document.getElementById('svc-form');
          var data = {{}};
          new FormData(form).forEach(function(v, k) {{ if(v !== '') data[k] = v; }});
          ['duration_days','people','hours_per_day'].forEach(function(k) {{
            if(data[k] !== undefined) data[k] = parseFloat(data[k]);
          }});
          var res = document.getElementById('svc-result');
          res.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;' +
            'min-height:180px;color:#888;"><span style="margin-right:8px;">⏳</span>Calcul en cours...</div>';
          var svcName  = form.getAttribute('data-svc');
          var svcAction= form.getAttribute('data-action');
          fetch('/services/' + svcName + '/run', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{action: svcAction, params: data}})
          }})
          .then(function(r) {{ return r.json(); }})
          .then(function(d) {{
            if (!d.success) {{
              res.innerHTML = '<div style="color:#f44336;padding:16px;">' +
                '<strong>❌ Erreur</strong><br>' + (d.message || 'Erreur inconnue') + '</div>';
              return;
            }}
            // ── Données du résultat ──
            var taskName  = d.task_name      || 'Tâche';
            var durDays   = d.duration_days  || 0;
            var weeks     = d.weeks          || 0;
            var totalHrs  = d.total_hours    || 0;
            var people    = d.people         || 1;
            var splitPct  = d.split_pct      || [];
            var dailyHrs  = d.daily_hours    || [];
            var totalPers = d.total_hours_per_person || [];
            var hpd       = data.hours_per_day || 8;

            // ── Tableau personnes ──
            var tableRows = '';
            var hasAlert  = false;
            for (var i = 0; i < people; i++) {{
              var pct  = splitPct[i]  !== undefined ? splitPct[i]  : (100/people).toFixed(1);
              var dh   = dailyHrs[i]  !== undefined ? dailyHrs[i]  : 0;
              var th   = totalPers[i] !== undefined ? totalPers[i] : 0;
              var over = parseFloat(dh) > parseFloat(hpd);
              if (over) hasAlert = true;
              var rowCls = over ? ' class="alert-row"' : '';
              var badge  = over
                ? '<span class="badge badge-warn">⚠ Surcharge</span>'
                : '<span class="badge badge-ok">✓ OK</span>';
              tableRows += '<tr' + rowCls + '>' +
                '<td>Personne ' + (i+1) + '</td>' +
                '<td>' + parseFloat(pct).toFixed(1) + ' %</td>' +
                '<td>' + parseFloat(dh).toFixed(2) + ' h</td>' +
                '<td>' + parseFloat(th).toFixed(1) + ' h</td>' +
                '<td>' + badge + '</td>' +
                '</tr>';
            }}

            // ── Alertes globales ──
            var alertHtml = '';
            if (hasAlert) {{
              alertHtml = '<div style="background:rgba(244,67,54,.1);border:1px solid rgba(244,67,54,.3);' +
                'border-radius:8px;padding:12px 16px;margin-top:14px;font-size:.85rem;">' +
                '<strong style="color:#f44336;">⚠ Attention — Surcharge détectée</strong>' +
                '<p style="color:#ccc;margin-top:4px;">Une ou plusieurs personnes dépassent ' +
                parseFloat(hpd).toFixed(1) + ' h/jour. Envisagez d'allonger la durée ou d'ajouter des ressources.</p>' +
                '</div>';
            }}

            res.innerHTML =
              '<div style="border-left:3px solid #4caf50;padding-left:16px;margin-bottom:16px;">' +
              '<p style="color:#4caf50;font-weight:700;font-size:1rem;margin-bottom:4px;">✅ Résultat</p>' +
              '<p style="color:#ccc;font-size:.88rem;">' + taskName + '</p>' +
              '</div>' +

              '<div class="stat-row">' +
              '<div class="stat-card"><div class="stat-val">' + durDays + '</div>' +
                '<div class="stat-lbl">jours ouvrables</div></div>' +
              '<div class="stat-card"><div class="stat-val">' + parseFloat(weeks).toFixed(1) + '</div>' +
                '<div class="stat-lbl">semaines</div></div>' +
              '<div class="stat-card"><div class="stat-val">' + parseFloat(totalHrs).toFixed(1) + '</div>' +
                '<div class="stat-lbl">heures totales</div></div>' +
              '<div class="stat-card"><div class="stat-val">' + people + '</div>' +
                '<div class="stat-lbl">personne(s)</div></div>' +
              '</div>' +

              '<table class="res-table">' +
              '<thead><tr><th>Personne</th><th>%</th><th>H/jour</th><th>H/total</th><th>Statut</th></tr></thead>' +
              '<tbody>' + tableRows + '</tbody>' +
              '</table>' +
              alertHtml;
          }})
          .catch(function(err) {{
            res.innerHTML = '<div style="color:#f44336;padding:16px;">❌ Erreur réseau : ' + err + '</div>';
          }});
        }}
        </script>"""

        # ── Layout générique pour les autres services ──────────────────────
        return f"""
        <div style="max-width:680px;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
            <span style="font-size:2rem;">{icon}</span>
            <div>
              <h2 style="font-size:1.2rem;font-weight:700;">{title}</h2>
              <p style="color:#888;font-size:.85rem;margin-top:2px;">{fdesc}</p>
            </div>
          </div>
          <div style="background:var(--card);border:1px solid var(--border);
               border-radius:10px;padding:24px;margin-top:16px;">
            <form id="svc-form" onsubmit="runService(event)" data-svc="{svc_name}" data-action="{action}">
              {fields_html}
              <button type="submit" class="btn-primary" style="margin-top:8px;">
                ▶ Exécuter
              </button>
            </form>
          </div>
          <div id="svc-result" style="margin-top:20px;display:none;
               background:var(--card);border:1px solid var(--border);
               border-radius:10px;padding:20px;"></div>
        </div>
        <script>
        function runService(e) {{
          e.preventDefault();
          var form = document.getElementById('svc-form');
          var data = {{}};
          new FormData(form).forEach(function(v, k) {{ if(v !== '') data[k] = v; }});
          ['duration_days','people','hours_per_day'].forEach(function(k) {{
            if(data[k] !== undefined) data[k] = parseFloat(data[k]);
          }});
          var res = document.getElementById('svc-result');
          res.style.display = 'block';
          res.innerHTML = '<p style="color:#888;">⏳ Exécution en cours...</p>';
          var svcName  = form.getAttribute('data-svc');
          var svcAction= form.getAttribute('data-action');
          fetch('/services/' + svcName + '/run', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{action: svcAction, params: data}})
          }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
            if (d.success) {{
              var msg = (d.message||'').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                                       .replace(/\n/g, '<br>');
              res.innerHTML = '<div style="border-left:3px solid #4caf50;padding-left:16px;">' +
                '<p style="color:#4caf50;font-weight:600;margin-bottom:10px;">✅ Résultat</p>' +
                '<div style="line-height:1.8;font-size:.92rem;">' + msg + '</div></div>';
            }} else {{
              res.innerHTML = '<div style="color:#f44336;">❌ ' + (d.message||'Erreur') + '</div>';
            }}
          }}).catch(function(err) {{
            res.innerHTML = '<div style="color:#f44336;">❌ Erreur: ' + err + '</div>';
          }});
        }}
        </script>"""

    # Formulaire générique pour les services sans template
    acts_btns = " ".join(
        f'<button type="button" onclick="runGeneric(\'{a}\')" class="btn-primary" style="margin-right:8px;">{a}</button>'
        for a in actions
    )
    return f"""
        <div style="max-width:680px;">
          <h2 style="font-size:1.2rem;margin-bottom:8px;" id="gen-svc-title">⚡ Service</h2>
          <p style="color:#888;margin-bottom:20px;">{desc}</p>
          <div style="background:var(--card);border:1px solid var(--border);
               border-radius:10px;padding:24px;">
            <label style="font-size:.82rem;color:#888;display:block;margin-bottom:6px;">
              Paramètres JSON (optionnel)
            </label>
            <textarea id="gen-params" rows="4"
              placeholder='{{"key": "value"}}' style="font-family:monospace;"></textarea>
            <div style="margin-top:16px;">{acts_btns}</div>
          </div>
          <div id="svc-result" style="margin-top:20px;display:none;
               background:var(--card);border:1px solid var(--border);
               border-radius:10px;padding:20px;"></div>
        </div>
        <script>
        function runGeneric(action) {{
          var svcName = window.location.pathname.split('/').filter(Boolean)[1];
          var raw = document.getElementById('gen-params').value.trim();
          var params = {{}};
          if(raw) try {{ params = JSON.parse(raw); }} catch(e) {{
            alert('JSON invalide'); return;
          }}
          var res = document.getElementById('svc-result');
          res.style.display = 'block';
          res.innerHTML = '<p style="color:#888;">⏳ Exécution...</p>';
          fetch('/services/' + svcName + '/run', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{action: action, params: params}})
          }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
            var msg = (d.message||JSON.stringify(d,null,2)).replace(/\n/g,'<br>');
            res.innerHTML = '<div style="border-left:3px solid ' +
              (d.success?'#4caf50':'#f44336') + ';padding-left:16px;">' + msg + '</div>';
          }});
        }}
        </script>"""


def register_services_routes(app, aion_app):
    """Enregistre les routes web des services AION."""

    @app.get("/services", response_class=HTMLResponse)
    async def services_list(request: Request, q: str = ""):
        """Page liste des services avec recherche."""
        version  = aion_app.VERSION
        ai_ok    = aion_app.brain.is_available() if aion_app.brain else False
        services = _get_services()

        # Filtrer par recherche
        if q:
            ql = q.lower()
            services = [s for s in services
                        if ql in s["name"].lower() or ql in s.get("description","").lower()]

        svc_port = int(os.getenv("AION_SERVICES_PORT", "8001"))
        online   = len(services) > 0

        # Barre de recherche
        search_html = f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:24px;">
          <h1 style="font-size:1.3rem;font-weight:700;">⚡ Services AION</h1>
          <span style="font-size:.78rem;color:{'#4caf50' if online else '#f44336'};">
            {'● En ligne' if online else '● Hors ligne'} — port {svc_port}
          </span>
          <div style="flex:1;"></div>
          <form method="get" action="/services" style="display:flex;gap:8px;max-width:300px;">
            <input type="text" name="q" value="{q}"
                   placeholder="🔍 Rechercher un service..."
                   style="flex:1;" oninput="this.form.submit()">
          </form>
        </div>"""

        if not services:
            cards_html = """<div style="color:#888;text-align:center;padding:40px;">
              <p style="font-size:1.1rem;">Aucun service disponible.</p>
              <p style="font-size:.85rem;margin-top:8px;">
                AION-Services démarre au lancement d'AION-Core sur le port """ + str(svc_port) + """.</p>
              </div>"""
        else:
            cards = []
            for svc in services:
                sname = svc["name"]
                sdesc = svc.get("description", "")
                acts  = svc.get("actions", [])
                acts_html = " ".join(
                    f'<span style="background:rgba(30,144,255,.15);color:#1e90ff;'
                    f'padding:2px 8px;border-radius:4px;font-size:.75rem;">{a}</span>'
                    for a in acts
                )
                cards.append(f"""
                <a href="/services/{sname}" style="text-decoration:none;color:inherit;">
                  <div style="background:var(--card);border:1px solid var(--border);
                       border-radius:10px;padding:20px;margin-bottom:12px;
                       transition:border-color .2s;cursor:pointer;"
                       onmouseover="this.style.borderColor='#1e90ff'"
                       onmouseout="this.style.borderColor='var(--border)'">
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                      <span style="font-size:1.5rem;">⚡</span>
                      <div>
                        <div style="font-weight:600;font-size:.95rem;">{sname.replace("_"," ").title()}</div>
                        <div style="color:#888;font-size:.82rem;">{sdesc}</div>
                      </div>
                      <span style="margin-left:auto;color:#1e90ff;font-size:1.2rem;">›</span>
                    </div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;">{acts_html}</div>
                  </div>
                </a>""")
            cards_html = "".join(cards)

        html = (_sidebar_html("__services__", version, ai_ok)
                + search_html + cards_html + _page_end())
        return HTMLResponse(html)

    @app.get("/services/{svc_name}", response_class=HTMLResponse)
    async def service_detail(svc_name: str):
        """Page formulaire interactif d'un service."""
        version  = aion_app.VERSION
        ai_ok    = aion_app.brain.is_available() if aion_app.brain else False
        svc_info = _get_service(svc_name)

        if not svc_info:
            return HTMLResponse(
                _sidebar_html(svc_name, version, ai_ok) +
                f'<p style="color:#f44336;">Service "{svc_name}" introuvable.</p>' +
                '<a href="/services" style="color:#1e90ff;">← Retour aux services</a>' +
                _page_end()
            )

        breadcrumb = ('<a href="/services" style="color:#888;text-decoration:none;font-size:.82rem;">' +
                      '⚡ Services</a> <span style="color:#555;"> › </span>')
        content = (breadcrumb + _build_form(svc_name, svc_info))

        return HTMLResponse(_sidebar_html(svc_name, version, ai_ok) + content + _page_end())

    @app.post("/services/{svc_name}/run")
    async def service_run(svc_name: str, request: Request):
        """Exécute un service et retourne le résultat JSON."""
        import requests as _req
        body   = await request.json()
        action = body.get("action", "calculate")
        params = body.get("params", {})
        try:
            r = _req.post(
                f"{_svc_url()}/api/services/{svc_name}/{action}",
                json=params, timeout=15
            )
            return r.json()
        except Exception as e:
            # Fallback : appel local direct si AION-Services indisponible
            try:
                from aion_core.services.builtins.capacity_calc import CapacityCalcService
                svc = CapacityCalcService()
                result = svc.run(action=action, params=params)
                return result
            except Exception as e2:
                return {"success": False, "message": f"AION-Services indisponible: {e} | Fallback: {e2}"}
