from browser import document, window, timer, ajax, html, alert
from browser.local_storage import storage
import json

# =============================================================================
# 1. ETAT GLOBAL & CONFIGURATION
# =============================================================================

AI_STATE = {
    'connected': False,
    'key': None,
    'model_id': 'gemini-2.5-flash-lite'
}

CURRENT_FILE_DATA = None

# =============================================================================
# 2. INITIALISATION & BINDINGS UI
# =============================================================================

def bind_events():
    """Attache les événements globaux"""
    
    # Drag & Drop + Click Upload
    if 'drop-zone' in document:
        zone = document['drop-zone']
        inp = document['file-upload']
        
        zone.bind('dragover', on_dragover)
        zone.bind('dragleave', on_dragleave)
        zone.bind('drop', on_drop)
        
        inp.bind('click', lambda ev: ev.stopPropagation())
        
        def safe_zone_click(ev):
            if ev.target.id != 'file-upload':
                inp.click()
                
        zone.bind('click', safe_zone_click)
        inp.bind('change', on_input_change)

    # API Panel
    if 'btn-api-config' in document:
        document['btn-api-config'].bind('click', open_api_modal)
    if 'btn-close-modal' in document:
        document['btn-close-modal'].bind('click', close_api_modal)
    if 'btn-save-api' in document:
        document['btn-save-api'].bind('click', trigger_ai_connection_test)
    
    # AI Model Switch
    for rad in document.select('input[name="ai_model"]'):
        rad.bind('change', lambda ev: reset_ai_status())

    # Profile Menu
    if 'btn-profile-menu' in document:
        document['btn-profile-menu'].bind('click', toggle_profile_menu)
    if 'btn-logout' in document:
        document['btn-logout'].bind('click', do_logout)

    # Navigation
    if 'btn-restart' in document: document['btn-restart'].bind('click', on_restart)
    if 'btn-back-mapping' in document:
        document['btn-back-mapping'].bind('click', on_back_click)
        
    # Analyze Button
    if 'btn-analyze' in document:
        document['btn-analyze'].bind('click', trigger_ai_analysis)

# =============================================================================
# 3. GESTION DU PROFIL UI
# =============================================================================

def toggle_profile_menu(ev):
    ev.stopPropagation()
    menu = document['profile-dropdown']
    arrow = document['profile-arrow']
    if menu.classList.contains('hidden'):
        menu.classList.remove('hidden')
        arrow.classList.add('rotate-180')
        document.bind('click', close_profile_menu)
    else:
        menu.classList.add('hidden')
        arrow.classList.remove('rotate-180')
        document.unbind('click', close_profile_menu)

def close_profile_menu(ev):
    menu = document['profile-dropdown']
    btn = document['btn-profile-menu']
    arrow = document['profile-arrow']
    if not menu.contains(ev.target) and not btn.contains(ev.target):
        menu.classList.add('hidden')
        arrow.classList.remove('rotate-180')
        document.unbind('click', close_profile_menu)

def do_logout(ev=None):
    if ev: ev.preventDefault()
    if window.confirm("Se déconnecter ?"):
        target = ev.target.dataset.get('url', window.location.href)
        window.location.href = target

# =============================================================================
# 4. GESTION BOUTON BACK (RESET TOTAL & ROBUSTE)
# =============================================================================

def on_back_click(ev):
    """
    Réinitialise l'interface pour revenir à l'étape 1 (Upload).
    """
    global CURRENT_FILE_DATA
    print("DEBUG: Back button clicked. Resetting...")

    # 1. Nettoyage Mémoire
    CURRENT_FILE_DATA = None
    
    # 2. Reset de l'input fichier
    if 'file-upload' in document:
        document['file-upload'].value = ''

    # 3. Reset de la Dropzone (État visuel)
    if 'drop-content-loading' in document:
        document['drop-content-loading'].classList.add('hidden')
    if 'drop-content-default' in document:
        document['drop-content-default'].classList.remove('hidden')
    if 'drop-message-error' in document:
        document['drop-message-error'].classList.add('hidden')

    # 4. Reset du Score AI
    if 'ai-score' in document:
        score_span = document['ai-score']
        score_span.text = "Waiting..."
        for c in ['text-green-400', 'text-orange-400', 'text-red-400', 'text-yellow-400', 'animate-pulse']:
            score_span.classList.remove(c)

    # 5. Nettoyage des conteneurs
    if 'mapping-source-container' in document:
        document['mapping-source-container'].innerHTML = ''
    if 'mapping-target-container' in document:
        document['mapping-target-container'].innerHTML = '<div class="text-gray-500 text-xs text-center italic mt-10">Waiting for AI analysis...</div>'
    if 'preview-container' in document:
        document['preview-container'].innerHTML = '<p class="text-gray-600 text-xs italic">Loading preview...</p>'

    # 6. BASCULE DES VUES
    if 'view-mapping' in document:
        document['view-mapping'].classList.add('hidden')
    if 'view-dashboard' in document:
        document['view-dashboard'].classList.remove('hidden')

# =============================================================================
# 5. GESTION MODALE API & CONNEXION IA
# =============================================================================

def open_api_modal(ev):
    if AI_STATE['key']:
        document['api-key-input'].value = AI_STATE['key']
    document['modal-api'].classList.remove('hidden')

def close_api_modal(ev):
    document['modal-api'].classList.add('hidden')

def reset_ai_status():
    AI_STATE['connected'] = False
    inp = document['api-key-input']
    inp.classList.remove('border-green-500', 'border-red-500', 'animate-shake')
    document['api-error-msg'].classList.add('hidden')
    
    btn = document['btn-save-api']
    btn.classList.remove('bg-green-600', 'bg-red-600')
    btn.classList.add('bg-neonBlue')
    document['btn-save-text'].text = "Vérifier & Connecter"
    
    update_api_dot(False)

def update_api_dot(is_connected):
    dot = document['api-status-dot']
    if not dot: return
    if is_connected:
        dot.classList.remove('bg-red-500', 'shadow-red-500')
        dot.classList.add('bg-green-500', 'shadow-[0_0_5px_rgba(34,197,94,0.5)]')
    else:
        dot.classList.remove('bg-green-500')
        dot.classList.add('bg-red-500')

def trigger_ai_connection_test(ev):
    key_input = document['api-key-input']
    api_key = key_input.value.strip()
    
    model_choice = "lite"
    for rad in document.select('input[name="ai_model"]'):
        if rad.checked: model_choice = rad.value

    if not api_key:
        show_api_error("Veuillez saisir une clé API.")
        return

    btn = document['btn-save-api']
    btn_text = document['btn-save-text']
    btn_text.text = "Connexion..."
    btn.disabled = True
    document['btn-spinner'].classList.remove('hidden')

    def on_complete(req):
        document['btn-spinner'].classList.add('hidden')
        btn.disabled = False
        
        if req.status != 200:
            btn_text.text = "Erreur Réseau"
            show_api_error(f"HTTP {req.status}")
            return

        try:
            data = json.loads(req.text)
        except:
            show_api_error("Réponse serveur invalide")
            return

        if data.get('status') == 'success':
            AI_STATE['connected'] = True
            AI_STATE['key'] = api_key
            AI_STATE['model_id'] = data.get('model_id')
            storage['gemini_key'] = api_key 
            
            btn.classList.remove('bg-neonBlue', 'bg-red-600')
            btn.classList.add('bg-green-600')
            btn_text.text = "Connecté !"
            key_input.classList.add('border-green-500')
            document['api-error-msg'].classList.add('hidden')
            update_api_dot(True)
            
            timer.set_timeout(lambda: close_api_modal(None), 1000)
            
            if not document['view-mapping'].classList.contains('hidden'):
                trigger_ai_analysis()
        else:
            AI_STATE['connected'] = False
            btn.classList.remove('bg-neonBlue')
            btn.classList.add('bg-red-600')
            btn_text.text = "Réessayer"
            show_api_error(data.get('message', 'Erreur inconnue'))

    req = ajax.ajax()
    req.bind('complete', on_complete)
    req.open('POST', window.api_urls['test_ai'], True)
    req.set_header('content-type', 'application/x-www-form-urlencoded')
    
    encoded_key = window.encodeURIComponent(api_key)
    req.send(f"api_key={encoded_key}&model={model_choice}")

def show_api_error(msg):
    err = document['api-error-msg']
    err.text = f"⚠️ {msg}"
    err.classList.remove('hidden')
    
    inp = document['api-key-input']
    inp.classList.remove('border-green-500')
    inp.classList.add('border-red-500', 'animate-shake')
    timer.set_timeout(lambda: inp.classList.remove('animate-shake'), 500)

# =============================================================================
# 6. GESTION UPLOAD & PARSING (STEP 1)
# =============================================================================

def on_dragover(ev):
    ev.preventDefault()
    document['drop-zone'].classList.add('border-neonBlue', 'bg-gray-800')

def on_dragleave(ev):
    ev.preventDefault()
    document['drop-zone'].classList.remove('border-neonBlue', 'bg-gray-800')

def on_drop(ev):
    ev.preventDefault()
    document['drop-zone'].classList.remove('border-neonBlue', 'bg-gray-800')
    if ev.dataTransfer.files.length > 0:
        handle_file(ev.dataTransfer.files[0])

def on_input_change(ev):
    if ev.target.files.length > 0:
        handle_file(ev.target.files[0])

def handle_file(file):
    MAX_MB = 50
    if file.size > MAX_MB * 1024 * 1024:
        alert(f"Fichier trop gros (> {MAX_MB}Mo)")
        return
    
    document['drop-content-default'].classList.add('hidden')
    document['drop-content-loading'].classList.remove('hidden')
    
    upload_file_to_server(file)

def upload_file_to_server(file):
    form_data = window.FormData.new()
    form_data.append('file', file, file.name)
    
    def on_complete(req):
        if req.status == 200:
            try:
                data = json.loads(req.text)
                if data['status'] == 'success':
                    document['drop-content-loading'].classList.add('hidden')
                    document['drop-content-default'].classList.remove('hidden')
                    
                    show_view('view-mapping')
                    render_preview_table(data)
                    render_mapping_ui(data)
                    
                    if AI_STATE['connected']:
                        trigger_ai_analysis()
                else:
                    reset_upload_ui()
                    alert(data.get('message'))
            except:
                reset_upload_ui()
                alert("Erreur lecture réponse JSON")
        else:
            reset_upload_ui()
            alert(f"Erreur Upload {req.status}")

    req = ajax.ajax()
    req.bind('complete', on_complete)
    req.open('POST', window.api_urls['verify'], True)
    req.send(form_data)

def reset_upload_ui():
    document['drop-content-loading'].classList.add('hidden')
    document['drop-content-default'].classList.remove('hidden')
    document['file-upload'].value = ''

# =============================================================================
# 7. MAPPING & PREVIEW (STEP 2)
# =============================================================================

def render_preview_table(data):
    container = document['preview-container']
    container.clear()
    
    columns = data.get('columns', [])
    rows = data.get('sample_rows', []) or data.get('rows', [])
    
    if not rows:
        container <= html.P("Aucune donnée.", Class="text-gray-500 text-xs")
        return

    def make_chars_visible(val):
        if val is None: return ""
        s = str(val)
        return (s.replace("\n", "⏎").replace("\t", "⇥").replace("\u00A0", "⍽"))

    table = html.TABLE(Class="w-full text-left border-collapse text-xs font-mono whitespace-nowrap")
    thead = html.THEAD(Class="bg-gray-800 text-gray-400")
    tr_head = html.TR()
    
    display_cols = columns[:8]
    for col in display_cols:
        raw = make_chars_visible(col.get('raw', ''))
        tr_head <= html.TH(raw, Class="p-2 border-b border-gray-700 font-normal")
        
    if len(columns) > 8: tr_head <= html.TH("...", Class="p-2 border-b border-gray-700")
    thead <= tr_head
    table <= thead
    
    tbody = html.TBODY(Class="text-gray-300")
    for row_item in rows[:5]:
        tr = html.TR(Class="hover:bg-gray-800/50 transition")
        raw_vals = row_item.get('raw', []) if isinstance(row_item, dict) else row_item
        
        for i in range(len(display_cols)):
            val = raw_vals[i] if i < len(raw_vals) else ""
            val_vis = make_chars_visible(val)
            if len(val_vis) > 30: val_vis = val_vis[:30] + "..."
            tr <= html.TD(val_vis, Class="p-2 border-b border-gray-800/50")
            
        if len(columns) > 8: tr <= html.TD("...", Class="p-2 border-b border-gray-800/50")
        tbody <= tr
    table <= tbody
    
    wrapper = html.DIV(Class="overflow-x-auto border border-gray-700 rounded")
    wrapper <= table
    container <= wrapper
    container <= html.DIV(html.SPAN("Symboles : ⏎ Retour ligne | ⇥ Tab | ⍽ Espace Insécable", Class="text-[10px] text-gray-600"), Class="mt-1 text-right")

def render_mapping_ui(data):
    src_cont = document['mapping-source-container']
    tgt_cont = document['mapping-target-container']
    src_cont.clear()
    tgt_cont.clear()

    columns = data.get('columns', [])
    crm_options = {
        "first_name": "First Name", "last_name": "Last Name", "email": "Email Address",
        "phone": "Phone Number", "company": "Company Name", "job_title": "Job Title",
        "linkedin": "LinkedIn Profile", "website": "Website", "country": "Country",
        "city": "City", "ignore": "Ignore"
    }
    
    seen = {}
    for idx, col in enumerate(columns):
        col_id = col.get('id', idx)
        raw = col.get('raw', '')
        seen[raw] = seen.get(raw, 0) + 1
        
        disp = f"{raw} ({seen[raw]})" if seen[raw] > 1 else raw
        if not raw.strip(): disp = f"Col {col_id} (Vide)"

        div = html.DIV(disp, Class="h-10 flex items-center px-3 bg-gray-700 rounded text-white border border-gray-600 truncate font-mono text-sm mb-4 transition-all duration-300")
        div.attrs['data-col-id'] = str(col_id)
        div.title = raw
        src_cont <= div

        sel = html.SELECT(Class="h-10 w-full bg-gray-900 border border-gray-600 rounded px-3 text-white text-sm focus:border-neonBlue focus:ring-1 focus:ring-neonBlue focus:outline-none mb-4 transition-all duration-300")
        sel.id = f"select-target-{col_id}"
        sel <= html.OPTION("Select Field...", value="", selected=True)
        for k, v in crm_options.items(): sel <= html.OPTION(v, value=k)
        tgt_cont <= sel

# =============================================================================
# 8. LOGIQUE IA (SCAN & HIGHLIGHT - CORRIGÉE)
# =============================================================================

def trigger_ai_analysis(ev=None):
    if not AI_STATE['connected']: return

    score_span = document['ai-score']
    for c in ['text-green-400', 'text-orange-400', 'text-red-400', 'text-yellow-400', 'text-gray-400', 'animate-pulse']:
        score_span.classList.remove(c)
    
    score_span.text = "Thinking..."
    score_span.classList.add('animate-pulse', 'text-yellow-400')

    model_choice = "lite"
    for rad in document.select('input[name="ai_model"]'):
        if rad.checked: model_choice = rad.value
    
    def on_complete(req):
        score_span.classList.remove('animate-pulse', 'text-yellow-400')
        
        if req.status != 200:
            score_span.text = "Error"
            score_span.classList.add('text-red-400')
            return

        try:
            res = json.loads(req.text)
        except:
            score_span.text = "JSON Error"
            return
            
        if res['status'] == 'success':
            # ✅ PATCH DE COMPATIBILITÉ (FLAT vs WRAPPED)
            payload = res.get('data')
            if not isinstance(payload, dict):
                payload = res

            conf = payload.get('confidence', 0)
            drift = payload.get('drift_warning', False)
            
            # 1. Score UI
            if drift:
                score_span.text = f"⚠️ {conf}% (Drift?)"
                score_span.classList.add('text-red-500', 'font-bold')
                alert("Attention : L'IA détecte que ce fichier ne ressemble pas à des données CRM classiques.")
            else:
                score_span.text = f"{conf}%"
                if conf > 80: score_span.classList.add('text-green-400')
                elif conf > 50: score_span.classList.add('text-orange-400')
                else: score_span.classList.add('text-red-400')

            # 2. Mapping
            mappings = payload.get('mapping', {}) or {}
            rich_info = payload.get('rich_mapping', {}) or {}

            for col_id_str, target in mappings.items():
                sel_id = f"select-target-{col_id_str}"
                
                if sel_id in document:
                    sel = document[sel_id]
                    # On cherche la valeur dans les options
                    vals = [o.value for o in sel.options]
                    if target in vals:
                        sel.value = target
                        sel.classList.remove('border-gray-600')
                        sel.classList.add('border-neonBlue', 'shadow-[0_0_8px_rgba(0,243,255,0.3)]')

                        # Raison
                        reason_id = f"reason-{col_id_str}"
                        if reason_id in document:
                            r_div = document[reason_id]
                        else:
                            r_div = html.DIV(id=reason_id, Class="text-[10px] mt-1 italic transition-all")
                            sel.parent <= r_div
                        
                        details = rich_info.get(col_id_str, {})
                        r_text = details.get('reason', '')
                        r_conf = details.get('confidence', 0)
                        
                        if target == "ignore":
                            r_div.text = f"🚫 Ignoré : {r_text}"
                            r_div.class_name = "text-[10px] mt-1 text-gray-500 italic"
                            sel.classList.remove('border-neonBlue', 'shadow-[0_0_8px_rgba(0,243,255,0.3)]')
                            sel.classList.add('border-gray-600', 'opacity-50')
                        else:
                            prefix = "🤖" if r_conf > 80 else "🤔"
                            r_div.text = f"{prefix} {r_text}"
                            if "Off-Nominal" in r_text:
                                r_div.class_name = "text-[10px] mt-1 text-orange-400 font-bold"
                            else:
                                r_div.class_name = "text-[10px] mt-1 text-neonBlue/80"

                # Highlight Gauche
                src = document.select_one(f'div[data-col-id="{col_id_str}"]')
                if src:
                    if target != "ignore":
                        src.classList.remove('border-gray-600')
                        src.classList.add('border-l-4', 'border-neonBlue', 'bg-gray-800/60')
                    else:
                        src.classList.remove('border-l-4', 'border-neonBlue', 'bg-gray-800/60')
                        src.classList.add('border-gray-600')

        else:
            score_span.text = "Retry"
            score_span.classList.add('text-red-400')
            print(f"Error AI: {res.get('message')}")

    req = ajax.ajax()
    req.bind('complete', on_complete)
    req.open('POST', window.api_urls['scan_ai'], True)
    req.set_header('content-type', 'application/x-www-form-urlencoded')
    
    enc_key = window.encodeURIComponent(AI_STATE['key'])
    req.send(f"api_key={enc_key}&model={model_choice}")

# =============================================================================
# 9. HELPERS NAVIGATION
# =============================================================================

def show_view(view_id):
    for vid in ['view-dashboard', 'view-mapping', 'view-review', 'view-success']:
        if vid in document: document[vid].classList.add('hidden')
    document[view_id].classList.remove('hidden')
    window.scrollTo(0, 0)

def on_restart(ev):
    show_view('view-dashboard')
    document['file-upload'].value = ''

# Init
bind_events()
if 'gemini_key' in storage:
    AI_STATE['key'] = storage['gemini_key']