"""
services_routes.py -- Services AION-Core (execution directe).
"""
import importlib.util
import logging
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)
BUILTINS_DIR = Path("aion_core/services/builtins")

SERVICE_FORMS = {
    "capacity_calc": {
        "title": "Calcul de Capacite Projet", "icon": "\U0001f4ca", "action": "calculate",
        "fields": [
            {"id":"task_name",     "label":"Nom de la tache",        "type":"text",   "ph":"Ex: Module X"},
            {"id":"duration_days", "label":"Duree (jours ouvrables)","type":"number", "ph":"20",  "req":True, "min":"1"},
            {"id":"people",        "label":"Nb personnes",           "type":"number", "ph":"2",   "req":True, "min":"1", "val":"1"},
            {"id":"split",         "label":"Repartition %",          "type":"text",   "ph":"50/50  80/20  60/20/20 (vide=egale)"},
            {"id":"hours_per_day", "label":"Heures / jour",          "type":"number", "ph":"8",   "val":"8", "step":"0.5"},
        ],
    },
    "git_status": {
        "title": "Statut Git des Repos", "icon": "\U0001f500", "action": "status",
        "fields": [
            {"id":"repos_root","label":"Repertoire racine","type":"text",
             "ph":"C:/AION_APPS/repos","val":"C:/AION_APPS/repos"},
        ],
    },
    "env_checker": {
        "title": "Verification .env", "icon": "\U0001f50d", "action": "check",
        "fields": [
            {"id":"repos_root","label":"Repertoire racine","type":"text",
             "ph":"C:/AION_APPS/repos","val":"C:/AION_APPS/repos"},
        ],
    },
    "ado_search": {
        "title": "Recherche Azure DevOps", "icon": "\U0001f535", "action": "search",
        "fields": [
            {"id":"query",   "label":"Recherche",        "type":"text",   "ph":"Ex: bug login",  "req":True},
            {"id":"project", "label":"Projet ADO",       "type":"text",   "ph":"PTG - TMM D2",   "val":"PTG - TMM D2"},
            {"id":"max",     "label":"Nb max resultats", "type":"number", "ph":"20",             "val":"20","min":"1","max":"100"},
        ],
    },
}


def _load_service(name):
    p = BUILTINS_DIR / (name + ".py")
    if not p.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("svc_" + name, str(p))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.Service()
    except Exception as e:
        logger.error("Load service %s: %s", name, e)
        return None


def _list_services():
    if not BUILTINS_DIR.exists():
        return []
    result = []
    for f in sorted(BUILTINS_DIR.glob("*.py")):
        if f.name.startswith("_"):
            continue
        svc = _load_service(f.stem)
        if svc:
            fd = SERVICE_FORMS.get(f.stem, {})
            result.append({
                "name": svc.name,
                "desc": svc.description,
                "icon": fd.get("icon", getattr(svc, "icon", "\u26a1")),
                "title": fd.get("title", svc.name.replace("_", " ").title()),
            })
    return result


def _field_html(f):
    fid   = f["id"]
    lbl   = f.get("label", fid)
    ftype = f.get("type", "text")
    ph    = f.get("ph", "")
    val   = f.get("val", "")
    req   = "required" if f.get("req") else ""
    star  = " *" if f.get("req") else ""
    extra = ""
    if "min"  in f: extra += ' min="'  + str(f["min"])  + '"'
    if "max"  in f: extra += ' max="'  + str(f["max"])  + '"'
    if "step" in f: extra += ' step="' + str(f["step"]) + '"'
    return (
        '<div style="margin-bottom:12px;">'
        '<label style="display:block;font-size:.78rem;color:var(--dim);margin-bottom:4px;">'
        + lbl + star +
        '</label><input type="' + ftype + '" id="' + fid + '" name="' + fid + '"'
        ' placeholder="' + ph + '" value="' + val + '" ' + req + extra +
        ' style="width:100%;background:#12141f;border:1px solid var(--border);'
        'color:var(--text);padding:8px 12px;border-radius:6px;font-size:.88rem;"'
        ' onkeydown="if(event.key===\'Enter\'&&event.ctrlKey)runService()"></div>'
    )


_CSS = """
:root[data-theme="dark"]{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--green:#4caf50;--red:#f44336;--hdr:#151821;}
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}
header{background:var(--hdr);border-bottom:2px solid var(--accent);padding:0 20px;
  height:52px;display:flex;align-items:center;gap:12px;flex-shrink:0;}
header h1{color:var(--accent);font-size:1.2rem;font-weight:700;}
.spacer{flex:1;}
.hbtn{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}
.hbtn:hover{background:var(--accent);color:#fff;}
.layout{display:flex;flex:1;overflow:hidden;}
.sidebar{width:220px;background:var(--sb);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;padding:10px 0;transition:width .2s;}
.sidebar.collapsed{width:52px;overflow:hidden;}
.sidebar.collapsed .nav-label,.sidebar.collapsed .sb-sec{display:none;}
.sidebar.collapsed .nav-item{justify-content:center;padding:10px 0;}
.collapse-btn{background:transparent;border:none;color:var(--dim);cursor:pointer;
  padding:8px 14px;font-size:.9rem;width:100%;display:flex;align-items:center;gap:8px;}
.sb-sec{padding:4px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-top:8px;}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 14px;border-left:3px solid transparent;
  font-size:.88rem;text-decoration:none;color:var(--text);}
.nav-item:hover{background:rgba(30,144,255,.08);}
.nav-item.active{background:rgba(30,144,255,.12);border-left-color:var(--accent);
  color:var(--accent);font-weight:600;}
.nav-icon{width:20px;text-align:center;} .nav-label{flex:1;}
.main{flex:1;overflow:hidden;padding:20px;}
::-webkit-scrollbar{width:5px;} ::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
"""

_JS_COMMON = """
document.addEventListener("htmx:afterSwap", function(e) {
  if (e.target.id === "sidebar-apps") {
    e.target.querySelectorAll(".nav-item").forEach(function(a) {
      if (a.getAttribute("href") === window.location.pathname) a.classList.add("active");
    });
  }
});
function toggleSb() {
  var sb = document.getElementById("sb");
  var c  = sb.classList.toggle("collapsed");
  localStorage.setItem("sidebarCollapsed", c ? "1" : "0");
  document.getElementById("sb-ic").textContent = c ? "\u276f" : "\u276e";
}
(function() {
  var t = localStorage.getItem("theme");
  if (t) document.documentElement.setAttribute("data-theme", t);
  if (localStorage.getItem("sidebarCollapsed") === "1") {
    var sb = document.getElementById("sb");
    if (sb) { sb.classList.add("collapsed"); document.getElementById("sb-ic").textContent = "\u276f"; }
  }
})();
"""


def _sidebar_html():
    return """
    <nav class="sidebar" id="sb">
      <button class="collapse-btn" onclick="toggleSb()">
        <span id="sb-ic">\u276e</span>
        <span class="nav-label" style="font-size:.78rem;">R\u00e9duire</span>
      </button>
      <div class="sb-sec">Navigation</div>
      <a href="/"     class="nav-item"><span class="nav-icon">\U0001f4ca</span><span class="nav-label">Dashboard</span></a>
      <a href="/chat" class="nav-item"><span class="nav-icon">\U0001f916</span><span class="nav-label">IA Chat</span></a>
      <div class="sb-sec">Apps</div>
      <div id="sidebar-apps" hx-get="/api/nav/apps/sidebar" hx-trigger="load" hx-swap="innerHTML">
        <div style="padding:8px 14px;color:var(--dim);font-size:.8rem;">\u2026</div>
      </div>
      <div class="sb-sec">AION</div>
      <a href="/store"    class="nav-item"><span class="nav-icon">\U0001f3ea</span><span class="nav-label">App Store</span></a>
      <a href="/docker"   class="nav-item"><span class="nav-icon">\U0001f433</span><span class="nav-label">Docker</span></a>
      <a href="/services" class="nav-item active"><span class="nav-icon">\u26a1</span><span class="nav-label">Services</span></a>
      <a href="/memory"   class="nav-item"><span class="nav-icon">\U0001f9e0</span><span class="nav-label">Memory</span></a>
      <a href="/settings" class="nav-item"><span class="nav-icon">\u2699\ufe0f</span><span class="nav-label">Settings</span></a>
    </nav>"""


def _page(version, ai_ok, content):
    gc = "#4caf50" if ai_ok else "#f44336"
    gl = "\u25cf Groq" if ai_ok else "\u25cf Groq offline"
    gba = "rgba(76,175,80,.2)" if ai_ok else "rgba(244,67,54,.2)"
    return (
        '<!DOCTYPE html><html lang="fr" data-theme="dark"><head>'
        '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Services \u2014 AION-Core</title>'
        '<script src="https://unpkg.com/htmx.org@1.9.12"></script>'
        '<style>' + _CSS + '</style></head><body>'
        '<header>'
        '<span style="font-size:1.3rem;">\U0001f916</span>'
        '<h1>AION-Core</h1>'
        '<span style="color:var(--dim);font-size:.75rem;">v' + version + '</span>'
        '<div class="spacer"></div>'
        '<span style="background:' + gba + ';color:' + gc + ';padding:2px 8px;'
        'border-radius:10px;font-size:.75rem;font-weight:600;">' + gl + '</span>'
        '<a href="/" class="hbtn">\u2190 Dashboard</a>'
        '</header>'
        '<div class="layout">'
        + _sidebar_html() +
        '<main class="main">' + content + '</main>'
        '</div>'
        '<script>' + _JS_COMMON + '</script>'
        '</body></html>'
    )


_RESULT_JS = r"""
function runService() {
  var data = {};
  document.getElementById("svc-form").querySelectorAll("input,select").forEach(function(el) {
    if (!el.name) return;
    data[el.name] = el.type === "checkbox" ? el.checked : el.value;
  });
  var zone = document.getElementById("result-zone");
  zone.innerHTML = '<div style="text-align:center;color:var(--dim);">\u23f3 Calcul...</div>';
  fetch("/services/" + SVC + "/run", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  }).then(function(r) { return r.json(); }).then(renderResult)
    .catch(function(e) { zone.innerHTML = '<p style="color:var(--red);">Erreur: ' + e + '</p>'; });
}
function renderResult(d) {
  var zone = document.getElementById("result-zone");
  if (!d.success) {
    zone.innerHTML = '<div style="color:var(--red);padding:12px;">\u274c ' + (d.message||"Erreur") + '</div>';
    return;
  }
  var html = '';
  if (d.rows && d.rows.length) {
    html += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:.82rem;">';
    if (d.headers) {
      html += '<thead><tr>';
      d.headers.forEach(function(h) {
        html += '<th style="padding:6px 8px;border-bottom:2px solid var(--border);color:var(--accent);text-align:left;">' + h + '</th>';
      });
      html += '</tr></thead>';
    }
    html += '<tbody>';
    d.rows.forEach(function(row, idx) {
      html += '<tr style="background:' + (idx%2===0?"transparent":"rgba(255,255,255,.02)") + '">';
      row.forEach(function(cell) {
        html += '<td style="padding:6px 8px;border-bottom:1px solid var(--border);">' + cell + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table></div>';
  } else if (d.cards && d.cards.length) {
    d.cards.forEach(function(c) {
      var color = c.status==="ok"?"var(--green)":(c.status==="warn"?"var(--orange)":"var(--red)");
      html += '<div style="border-left:3px solid '+color+';padding:8px 12px;margin-bottom:8px;border-radius:0 6px 6px 0;background:rgba(255,255,255,.02);">';
      html += '<div style="font-weight:600;font-size:.88rem;">' + c.title + '</div>';
      if (c.detail) html += '<div style="font-size:.78rem;color:var(--dim);margin-top:2px;">' + c.detail + '</div>';
      html += '</div>';
    });
  } else if (d.message) {
    html += '<pre style="font-size:.82rem;line-height:1.7;white-space:pre-wrap;color:var(--text);width:100%;">' + d.message + '</pre>';
  }
  zone.innerHTML = '<div style="width:100%;">' + (html || '<p style="color:var(--dim);">OK</p>') + '</div>';
}
"""


def register_services_routes(app, aion_app):

    @app.get("/services", response_class=HTMLResponse)
    async def services_list(request: Request):
        svcs  = _list_services()
        cards = ""
        for s in svcs:
            cards += (
                '<a href="/services/' + s["name"] + '" style="display:block;background:var(--card);'
                'border:1px solid var(--border);border-radius:10px;padding:16px;'
                'text-decoration:none;color:var(--text);">'
                '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">'
                '<span style="font-size:1.4rem;">' + s["icon"] + '</span>'
                '<span style="font-weight:600;">' + s["title"] + '</span></div>'
                '<div style="font-size:.82rem;color:var(--dim);">' + s["desc"] + '</div></a>'
            )
        if not cards:
            cards = ('<p style="color:var(--dim);">Aucun service disponible.<br>'
                     '<span style="font-size:.8rem;color:#555;">Ajouter des fichiers .py dans '
                     'aion_core/services/builtins/</span></p>')
        body = (
            '<h2 style="color:var(--accent);margin-bottom:16px;">\u26a1 Services AION</h2>'
            '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;">'
            + cards + '</div>'
        )
        return HTMLResponse(_page(aion_app.VERSION, aion_app.brain.is_available(), body))

    @app.get("/services/{name}", response_class=HTMLResponse)
    async def service_form_page(name: str, request: Request):
        svc = _load_service(name)
        if not svc:
            return HTMLResponse("<p style='color:var(--red);'>Service '" + name + "' introuvable.</p>", status_code=404)
        fd     = SERVICE_FORMS.get(name, {})
        title  = fd.get("title", name.replace("_"," ").title())
        icon   = fd.get("icon", "\u26a1")
        fields = "".join(_field_html(f) for f in fd.get("fields", []))
        body = (
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;height:calc(100vh - 112px);">'
            '<div style="overflow-y:auto;padding-right:8px;">'
            '<a href="/services" style="color:var(--dim);font-size:.8rem;text-decoration:none;display:block;margin-bottom:12px;">'
            '\u2190 Services</a>'
            '<h2 style="color:var(--accent);margin-bottom:16px;">' + icon + ' ' + title + '</h2>'
            '<form id="svc-form" onsubmit="event.preventDefault();runService();">'
            + fields +
            '<button type="submit" style="background:var(--accent);color:#fff;border:none;'
            'border-radius:6px;padding:10px 28px;cursor:pointer;font-size:.9rem;'
            'font-weight:600;width:100%;margin-top:4px;">\u25b6 Calculer</button>'
            '</form>'
            '<p style="font-size:.72rem;color:#555;margin-top:8px;text-align:center;">'
            'Ctrl+Entr\u00e9e pour soumettre</p>'
            '</div>'
            '<div id="result-zone" style="background:var(--card);border:1px solid var(--border);'
            'border-radius:10px;padding:16px;overflow-y:auto;display:flex;'
            'align-items:center;justify-content:center;">'
            '<p style="color:var(--dim);text-align:center;font-size:.85rem;">'
            '\u26a1 Le r\u00e9sultat s\'affichera ici.</p>'
            '</div></div>'
            '<script>var SVC="' + name + '";\n' + _RESULT_JS + '</script>'
        )
        return HTMLResponse(_page(aion_app.VERSION, aion_app.brain.is_available(), body))

    @app.post("/services/{name}/run")
    async def service_run(name: str, request: Request):
        svc = _load_service(name)
        if not svc:
            return JSONResponse({"success": False, "message": "Service '" + name + "' introuvable."}, status_code=404)
        try:
            body   = await request.json()
            action = SERVICE_FORMS.get(name, {}).get("action", "run")
            return JSONResponse(svc.execute(action, body))
        except Exception as e:
            logger.error("Service %s: %s", name, e)
            return JSONResponse({"success": False, "message": str(e)})
