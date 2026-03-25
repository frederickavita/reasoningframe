from browser import document, window, html, ajax
import json

APP = document["learning-app"]

URLS = {
    "create_session": APP.attrs["data-create-session-url"],
    "create_run": APP.attrs["data-create-run-url"],
    "update_run": APP.attrs["data-update-run-url"],
    "create_artifact": APP.attrs["data-create-artifact-url"],
    "upload_artifact": APP.attrs["data-upload-artifact-url"],
    "list_artifacts": APP.attrs["data-list-artifacts-url"],
}

STATE = {
    "module_id": int(APP.attrs["data-module-id"]),
    "session_id": None,
    "run_id": None,
    "artifact_id": None,
}

# ------------------------------------------------------------
# UI helpers (Inchangés)
# ------------------------------------------------------------
def log(msg, kind="info"):
    line = html.DIV(msg)
    if kind == "ok":
        line.class_name = "lp-ok"
    elif kind == "err":
        line.class_name = "lp-err"
    document["log"] <= line
    document["log"].scrollTop = document["log"].scrollHeight

def sync_state():
    document["state-module-id"].text = str(STATE["module_id"] or "-")
    document["state-session-id"].text = str(STATE["session_id"] or "-")
    document["state-run-id"].text = str(STATE["run_id"] or "-")
    document["state-artifact-id"].text = str(STATE["artifact_id"] or "-")

def clear_artifacts():
    document["artifact-list"].clear()

def render_artifacts(items):
    clear_artifacts()
    if not items:
        document["artifact-list"] <= html.LI("Aucun artifact pour cette session.")
        return

    for item in items:
        label = f"#{item.get('id')} — {item.get('artifact_type')} / {item.get('artifact_role')}"
        extra = []
        if item.get("title"): extra.append(item["title"])
        if item.get("file_upload"): extra.append(f"file={item['file_upload']}")
        if item.get("external_url"): extra.append(f"url={item['external_url']}")
        if extra: label += " — " + " | ".join(extra)
        document["artifact-list"] <= html.LI(label)

# ------------------------------------------------------------
# AJAX helpers (Modernisés pour Brython)
# ------------------------------------------------------------

def handle_response(req, on_success, on_error):
    """Fonction commune pour traiter les réponses Web2py"""
    if req.status in (200, 201):
        try:
            data = json.loads(req.text)
            if on_success: on_success(data, req.status)
        except Exception:
            if on_error: on_error({"success": False, "errors": "JSON invalide"}, req.status)
    else:
        try:
            data = json.loads(req.text)
            if on_error: on_error(data, req.status)
        except Exception:
            if on_error: on_error({"success": False, "errors": f"HTTP {req.status}"}, req.status)

def post_json(url, payload, on_success=None, on_error=None):
    # En Brython, ajax.post avec headers 'application/json' gère le dict Python auto
    ajax.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        oncomplete=lambda req: handle_response(req, on_success, on_error)
    )

def get_json(url, params=None, on_success=None, on_error=None):
    qs = ""
    if params:
        pairs = [f"{k}={window.encodeURIComponent(str(v))}" for k, v in params.items()]
        qs = "?" + "&".join(pairs)
    
    ajax.get(
        url + qs,
        oncomplete=lambda req: handle_response(req, on_success, on_error)
    )

def upload_file(url, artifact_id, file_obj, on_success=None, on_error=None):
    # Pour l'upload multipart en Brython, on utilise l'objet req.send natif
    req = ajax.ajax()
    form = window.FormData.new()
    form.append("artifact_id", str(artifact_id))
    form.append("file_upload", file_obj)
    
    req.bind("complete", lambda evt: handle_response(evt.target, on_success, on_error))
    req.open("POST", url, True)
    req.send(form)

# ------------------------------------------------------------
# Endpoint actions (Inchangées)
# ------------------------------------------------------------

def create_session(ev=None):
    payload = {
        "module_id": STATE["module_id"],
        "status": "active",
        "current_phase": "phase_1",
        "current_step_key": "intro",
        "workflow_graph_json": {"nodes": [], "edges": []},
        "ui_state_json": {"right_panel": "workflow_canvas"}
    }
    log("POST create_module_session ...")
    
    def ok(data, status):
        STATE["session_id"] = data["id"]
        sync_state()
        log(f"Session créée: id={STATE['session_id']}", "ok")
        
    post_json(URLS["create_session"], payload, ok, lambda d, s: log(f"Erreur HTTP {s}: {d}", "err"))

def create_run(ev=None):
    if not STATE["session_id"]:
        return log("Crée d'abord une session.", "err")

    payload = {
        "session_id": STATE["session_id"],
        "phase_key": "phase_1",
        "run_kind": "simulation",
        "status": "running",
        "input_json": {"message": "Run depuis Brython"},
        "graph_snapshot_json": {"nodes": ["webhook", "agent", "gmail"]}
    }
    log("POST create_run ...")
    
    def ok(data, status):
        STATE["run_id"] = data["id"]
        sync_state()
        log(f"Run créé: id={STATE['run_id']}", "ok")
        
    post_json(URLS["create_run"], payload, ok, lambda d, s: log(f"Erreur HTTP {s}: {d}", "err"))

def mark_run_success(ev=None):
    if not STATE["run_id"]:
        return log("Crée d'abord un run.", "err")

    payload = {
        "id": STATE["run_id"],
        "status": "succeeded",
        "response_payload_json": {"draft": "Bonjour, je suis sincèrement désolé..."}
    }
    log("POST update_run_status ...")
    post_json(URLS["update_run"], payload, lambda d, s: log(f"Run mis à jour: {d['data']['status']}", "ok"), lambda d, s: log(f"Erreur {s}: {d}", "err"))

def create_artifact(ev=None):
    if not STATE["session_id"]:
        return log("Crée d'abord une session.", "err")

    payload = {
        "session_id": STATE["session_id"],
        "run_id": STATE["run_id"],
        "artifact_type": "image",
        "title": "Artifact créé depuis Brython",
        "mime_type": "image/png"
    }
    log("POST create_artifact ...")
    
    def ok(data, status):
        STATE["artifact_id"] = data["id"]
        sync_state()
        log(f"Artifact créé: id={STATE['artifact_id']}", "ok")

    post_json(URLS["create_artifact"], payload, ok, lambda d, s: log(f"Erreur {s}: {d}", "err"))

def upload_artifact_action(ev=None):
    if not STATE["artifact_id"]:
        return log("Crée d'abord un artifact.", "err")

    files = document["artifact-file"].files
    if files.length == 0:
        return log("Choisis d'abord un fichier.", "err")

    file_obj = files[0]
    log(f"POST upload_artifact_file ... ({file_obj.name})")
    
    upload_file(URLS["upload_artifact"], STATE["artifact_id"], file_obj, 
                lambda d, s: [log("Upload terminé", "ok"), list_artifacts()], 
                lambda d, s: log(f"Erreur {s}: {d}", "err"))

def list_artifacts(ev=None):
    if not STATE["session_id"]:
        return log("Crée d'abord une session.", "err")

    log("GET list_artifacts_by_session ...")
    
    def ok(data, status):
        items = data["data"].get("items", [])
        render_artifacts(items)
        log(f"Artifacts récupérés: {len(items)}", "ok")

    get_json(URLS["list_artifacts"], {"session_id": STATE["session_id"]}, ok, lambda d, s: log(f"Erreur {s}: {d}", "err"))

# ------------------------------------------------------------
# Bindings
# ------------------------------------------------------------
document["btn-create-session"].bind("click", create_session)
document["btn-create-run"].bind("click", create_run)
document["btn-mark-success"].bind("click", mark_run_success)
document["btn-create-artifact"].bind("click", create_artifact)
document["btn-upload-artifact"].bind("click", upload_artifact_action)
document["btn-refresh-artifacts"].bind("click", list_artifacts)

sync_state()
log("Brython prêt. Clique sur 'Create Session' pour démarrer.", "ok")