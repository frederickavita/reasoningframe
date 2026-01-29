from browser import document, window, timer, html, alert
from browser.local_storage import storage

# --- 1. ETAT INITIAL & CONFIG ---
history_data = [
    {"date": "2026-01-28", "file": "clients_v2.csv", "status": "SUCCESS", "rows": 1240},
    {"date": "2026-01-25", "file": "cv_2024.pdf", "status": "FAILED", "rows": 0}
]

# Valeurs par défaut (écrasées par le localStorage si présent)
has_api_key = False 
current_model = "gemini-2.0-flash"

# --- 2. GESTION DES MODALES ---

# --- A. MODALE API (COMPLEXE 5 ETATS) ---
def open_api_modal(ev):
    document['modal-api'].classList.remove('hidden')

def close_api_modal(ev):
    document['modal-api'].classList.add('hidden')

def select_model(model_type):
    global current_model
    card_flash = document['model-card-flash']
    card_pro = document['model-card-pro']
    icon_flash = document['icon-check-flash']
    icon_pro = document['icon-check-pro']
    input_val = document['selected-model-value']

    if model_type == 'flash':
        current_model = "gemini-2.0-flash"
        card_flash.classList.remove('border-gray-700', 'bg-gray-800')
        card_flash.classList.add('border-neonBlue', 'bg-blue-900/20')
        icon_flash.classList.remove('hidden')
        
        card_pro.classList.remove('border-neonBlue', 'bg-blue-900/20')
        card_pro.classList.add('border-gray-700', 'bg-gray-800')
        icon_pro.classList.add('hidden')
    else:
        current_model = "gemini-1.5-pro"
        card_pro.classList.remove('border-gray-700', 'bg-gray-800')
        card_pro.classList.add('border-neonBlue', 'bg-blue-900/20')
        icon_pro.classList.remove('hidden')
        
        card_flash.classList.remove('border-neonBlue', 'bg-blue-900/20')
        card_flash.classList.add('border-gray-700', 'bg-gray-800')
        icon_flash.classList.add('hidden')

    input_val.value = current_model

def set_modal_state(state):
    """Machine à état visuelle pour le bouton API"""
    btn = document['btn-save-api']
    btn_text = document['btn-save-text']
    spinner = document['btn-spinner']
    inp = document['api-key-input']
    err = document['api-error-msg']
    badge = document['status-badge']
    status_txt = document['status-text']
    success_icon = document['icon-success-input']
    
    inp.classList.remove('border-red-500', 'border-green-500')
    err.classList.add('hidden')
    spinner.classList.add('hidden')
    success_icon.classList.add('hidden')
    
    if state == "EMPTY":
        btn_text.text = "Sauvegarder"
        btn.classList.remove('bg-neonBlue', 'text-black', 'shadow-lg')
        btn.classList.add('bg-gray-700', 'text-gray-300')
        btn.disabled = False
        inp.disabled = False
        
    elif state == "PARTIAL":
        btn.classList.remove('bg-gray-700', 'text-gray-300')
        btn.classList.add('bg-neonBlue', 'text-black', 'shadow-lg')
        btn_text.text = "Sauvegarder"
        btn.disabled = False
        
    elif state == "LOADING":
        btn_text.text = "Vérification..."
        btn.disabled = True
        btn.classList.remove('bg-neonBlue', 'text-black')
        btn.classList.add('bg-gray-600', 'text-gray-300')
        inp.disabled = True
        spinner.classList.remove('hidden')
        
    elif state == "ERROR":
        btn_text.text = "Réessayer"
        btn.disabled = False
        btn.classList.remove('bg-gray-600')
        btn.classList.add('bg-red-600', 'text-white')
        inp.disabled = False
        inp.classList.add('border-red-500', 'animate-shake')
        err.classList.remove('hidden')
        inp.focus()
        timer.set_timeout(lambda: inp.classList.remove('animate-shake'), 500)

    elif state == "IDEAL":
        btn_text.text = "Mettre à jour"
        btn.disabled = False
        btn.classList.remove('bg-gray-600', 'bg-red-600')
        btn.classList.add('bg-green-600', 'text-white')
        inp.disabled = False
        inp.classList.add('border-green-500')
        success_icon.classList.remove('hidden')
        badge.classList.remove('bg-blue-900/30', 'text-blue-400', 'border-blue-500/30')
        badge.classList.add('bg-green-900/30', 'text-green-400', 'border-green-500/30')
        status_txt.text = "Connecté & Prêt"

def on_input_typing(ev):
    val = ev.target.value
    if len(val) > 0 and not has_api_key:
        set_modal_state("PARTIAL")
    elif len(val) == 0:
        set_modal_state("EMPTY")

def save_api_key(ev):
    global has_api_key, current_model
    key = document['api-key-input'].value
    
    set_modal_state("LOADING")
    
    def process_verification():
        if len(key) > 10 and (key.startswith('AIza') or key.startswith('sk-')):
            has_api_key = True
            
            # Stockage Dictionnaire
            storage['gemini_key'] = key
            storage['gemini_model'] = current_model
            
            set_modal_state("IDEAL")
            update_api_status()
            
            show_alert(f"Configuration Sauvegardée !\nModèle: {current_model}")
            timer.set_timeout(lambda: document['custom-alert'].classList.add('hidden'), 2000)
            timer.set_timeout(lambda: document['modal-api'].classList.add('hidden'), 1000)
        else:
            set_modal_state("ERROR")
    
    timer.set_timeout(process_verification, 800)

# --- B. MODALE SETTINGS (SIMPLE) ---

def open_settings_modal(ev):
    # Charge valeurs
    if 'settings_date_fmt' in storage:
        document['date-format-select'].value = storage['settings_date_fmt']
    if 'settings_prompt' in storage:
        document['system-prompt-input'].value = storage['settings_prompt']
    if 'settings_strictness' in storage:
        val = storage['settings_strictness']
        document['strictness-slider'].value = val
        update_slider_label(int(val))
        
    document['modal-settings'].classList.remove('hidden')

def close_settings_modal(ev):
    document['modal-settings'].classList.add('hidden')

def save_settings_logic(ev):
    storage['settings_date_fmt'] = document['date-format-select'].value
    storage['settings_prompt'] = document['system-prompt-input'].value
    storage['settings_strictness'] = document['strictness-slider'].value
    
    btn = document['btn-save-settings']
    original_text = btn.text
    btn.text = "Sauvegardé !"
    
    def reset():
        close_settings_modal(None)
        btn.text = original_text
    timer.set_timeout(reset, 800)

def switch_tab(tab_name):
    btn_gen = document['tab-btn-general']
    btn_brain = document['tab-btn-brain']
    
    btn_gen.classList.remove('border-neonBlue', 'text-neonBlue')
    btn_gen.classList.add('border-transparent', 'text-gray-400')
    btn_brain.classList.remove('border-neonBlue', 'text-neonBlue')
    btn_brain.classList.add('border-transparent', 'text-gray-400')

    document['tab-content-general'].classList.add('hidden')
    document['tab-content-brain'].classList.add('hidden')

    if tab_name == 'general':
        document['tab-content-general'].classList.remove('hidden')
        btn_gen.classList.add('border-neonBlue', 'text-neonBlue')
        btn_gen.classList.remove('border-transparent', 'text-gray-400')
    else:
        document['tab-content-brain'].classList.remove('hidden')
        btn_brain.classList.add('border-neonBlue', 'text-neonBlue') 
        btn_brain.classList.remove('border-transparent', 'text-gray-400')

def update_slider_label(val):
    labels = ["Strict", "Équilibré", "Créatif"]
    if 0 <= val < len(labels):
        document['strictness-label'].text = labels[val]

def on_slider_change(ev):
    update_slider_label(int(ev.target.value))


# --- 3. UI DASHBOARD & UPLOAD ---

def render_history():
    rows_container = document['history-rows']
    rows_container.clear()
    
    if not history_data:
        document['history-table'].classList.add('hidden')
        document['history-empty'].classList.remove('hidden')
    else:
        document['history-table'].classList.remove('hidden')
        document['history-empty'].classList.add('hidden')
        for item in history_data:
            badge_class = "bg-green-900/50 text-green-400 border-green-800" if item['status'] == "SUCCESS" else "bg-red-900/50 text-red-400 border-red-800"
            row = html.TR(Class="hover:bg-gray-700/50 transition")
            row <= html.TD(item['date'], Class="px-6 py-4")
            row <= html.TD(item['file'], Class="px-6 py-4 text-white font-mono")
            row <= html.TD(html.SPAN(f"[ {item['status']} ]", Class=f"border px-2 py-1 rounded text-xs font-bold {badge_class}"), Class="px-6 py-4")
            row <= html.TD(str(item['rows']), Class="px-6 py-4 text-right")
            row <= html.TD(html.A("[Log]", Href="#", Class="text-gray-500 hover:text-white"), Class="px-6 py-4 text-right")
            rows_container <= row

def update_api_status():
    dot = document['api-status-dot']
    btn = document['btn-api-config']
    if has_api_key:
        dot.classList.remove('bg-red-500')
        dot.classList.add('bg-green-500', 'shadow-[0_0_8px_rgba(34,197,94,0.8)]')
        btn.classList.remove('border-gray-600', 'text-gray-400', 'hover:text-white')
        btn.classList.add('border-green-500/50', 'text-green-400', 'bg-green-900/10')
    else:
        dot.classList.remove('bg-green-500', 'shadow-[0_0_8px_rgba(34,197,94,0.8)]')
        dot.classList.add('bg-red-500')
        btn.classList.remove('border-green-500/50', 'text-green-400', 'bg-green-900/10')
        btn.classList.add('border-gray-600', 'text-gray-400', 'hover:text-white')

def show_error(msg):
    err_box = document['drop-message-error']
    drop_zone = document['drop-zone']
    err_box.text = f"⚠️ {msg}"
    err_box.classList.remove('hidden')
    drop_zone.classList.add('border-red-500', 'animate-shake')
    drop_zone.classList.remove('border-gray-600', 'hover:border-neonBlue')
    def reset_error():
        err_box.classList.add('hidden')
        drop_zone.classList.remove('border-red-500', 'animate-shake')
        drop_zone.classList.add('border-gray-600', 'hover:border-neonBlue')
    timer.set_timeout(reset_error, 3000)

def show_alert(message):
    document['alert-message'].text = message
    document['custom-alert'].classList.remove('hidden')

def close_alert(ev):
    document['custom-alert'].classList.add('hidden')

def handle_file(file):
    global has_api_key
    if not has_api_key:
        document['modal-api'].classList.remove('hidden')
        return
    filename = file.name.lower()
    is_valid = filename.endswith('.csv') or filename.endswith('.xlsx') or filename.endswith('.xls')
    if not is_valid:
        show_alert(f"Le fichier '{file.name}' n'est pas supporté.\nMerci d'utiliser uniquement .csv ou .xlsx")
        return
    document['drop-content-default'].classList.add('hidden')
    document['drop-content-loading'].classList.remove('hidden')
    def go_next():
        document['drop-content-default'].classList.remove('hidden')
        document['drop-content-loading'].classList.add('hidden')
        window.show_view('view-mapping') 
    timer.set_timeout(go_next, 1500)

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

# --- 4. NAVIGATION VIEW ---
def show_view(view_id):
    for vid in ['view-dashboard', 'view-mapping', 'view-review', 'view-success']:
        document[vid].classList.add('hidden')
    document[view_id].classList.remove('hidden')
    window.scrollTo(0, 0)
    window.show_view = show_view

def on_analyze(ev):
    btn = document['btn-analyze']
    btn.text = "Processing..."
    def go_review():
        show_view('view-review')
        btn.text = "[ ANALYZE DATA > ]"
    timer.set_timeout(go_review, 500)

def on_commit(ev):
    btn = document['btn-commit']
    btn.text = "Saving..."
    def go_success():
        show_view('view-success')
        btn.text = "[ COMMIT IMPORT ]"
    timer.set_timeout(go_success, 1500)

def on_restart(ev):
    show_view('view-dashboard')
    document['file-upload'].value = ''


# --- 5. CHARGEMENT & BINDINGS ---

def check_local_storage():
    global has_api_key, current_model
    if 'gemini_key' in storage:
        stored_key = storage['gemini_key']
        document['api-key-input'].value = stored_key
        has_api_key = True
        update_api_status()
        set_modal_state("IDEAL")
        if 'gemini_model' in storage:
            current_model = storage['gemini_model']
            # Note: Select model visuel à faire si besoin

# Exposer fonctions globales
window.select_model = select_model
window.switch_tab = switch_tab
window.show_view = show_view

# BINDINGS API
document['api-key-input'].bind('input', on_input_typing)
document['btn-save-api'].bind('click', save_api_key)
document['btn-api-config'].bind('click', open_api_modal)
document['btn-close-modal'].bind('click', close_api_modal)

# BINDINGS SETTINGS
document['btn-open-settings'].bind('click', open_settings_modal)
document['btn-close-settings'].bind('click', close_settings_modal)
document['btn-save-settings'].bind('click', save_settings_logic)
document['strictness-slider'].bind('input', on_slider_change)

# BINDINGS UPLOAD & ALERT
document['drop-zone'].bind('dragover', on_dragover)
document['drop-zone'].bind('dragleave', on_dragleave)
document['drop-zone'].bind('drop', on_drop)
document['file-upload'].bind('change', on_input_change)
document['btn-close-alert'].bind('click', close_alert)

# BINDINGS NAV
document['btn-back-mapping'].bind('click', lambda ev: show_view('view-dashboard'))
document['btn-analyze'].bind('click', on_analyze)
document['btn-back-review'].bind('click', lambda ev: show_view('view-mapping'))
document['btn-commit'].bind('click', on_commit)
document['btn-restart'].bind('click', on_restart)

# RUN
render_history()
update_api_status()
check_local_storage()