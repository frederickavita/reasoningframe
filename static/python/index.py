from browser import document, window, ajax, timer
import json

# --- UI CONFIGURATION ---
BTN_ID = "btn-magic-test" 
original_btn_text = "Test the magic now"

# --- CUSTOM ALERT MANAGEMENT (ENGLISH) ---

def show_custom_alert(title, message, level="error"):
    """
    Displays Tailwind modal instead of native alert.
    level: 'error' (Red) or 'info' (Blue)
    """
    modal = document['landing-alert']
    box = document['alert-box']
    icon_container = document['alert-icon-container']
    btn = document['btn-close-landing-alert']
    
    # 1. Update Text
    document['alert-title'].text = title
    document['alert-message'].text = message
    
    # 2. Handle Style (Red vs Blue)
    if level == "error":
        # ERROR Style
        box.classList.remove('border-neonBlue', 'shadow-[0_0_50px_rgba(0,243,255,0.5)]')
        box.classList.add('border-red-500', 'shadow-[0_0_50px_rgba(239,68,68,0.5)]')
        
        icon_container.classList.remove('bg-blue-900/50', 'border-neonBlue')
        icon_container.classList.add('bg-red-900/50', 'border-red-500')
        
        document['icon-error'].classList.remove('hidden')
        document['icon-info'].classList.add('hidden')
        
        btn.classList.remove('bg-neonBlue', 'hover:bg-white', 'text-black')
        btn.classList.add('bg-red-600', 'hover:bg-red-700', 'text-white')
        btn.text = "I understand"
        
    else:
        # INFO / SUCCESS Style
        box.classList.remove('border-red-500', 'shadow-[0_0_50px_rgba(239,68,68,0.5)]')
        box.classList.add('border-neonBlue', 'shadow-[0_0_50px_rgba(0,243,255,0.5)]')
        
        icon_container.classList.remove('bg-red-900/50', 'border-red-500')
        icon_container.classList.add('bg-blue-900/50', 'border-neonBlue')
        
        document['icon-error'].classList.add('hidden')
        document['icon-info'].classList.remove('hidden')
        
        btn.classList.remove('bg-red-600', 'hover:bg-red-700', 'text-white')
        btn.classList.add('bg-neonBlue', 'hover:bg-white', 'text-black')
        btn.text = "Continue"

    # 3. Show
    modal.classList.remove('hidden')

def close_custom_alert(ev):
    document['landing-alert'].classList.add('hidden')

# --- UPLOAD LOGIC ---

def reset_ui():
    """Restores the button to its initial state"""
    if BTN_ID in document:
        btn = document[BTN_ID]
        btn.text = original_btn_text
        btn.classList.remove('cursor-wait', 'opacity-50')
        btn.disabled = False
        document["file-input"].value = ""


def on_upload_complete(req):
    reset_ui()

    if req.status == 200:
        try:
            resp = json.loads(req.text)
            window.location.href = resp.get('next_step', '/default/login')
        except:
            show_custom_alert("Technical Issue", "The server returned an unexpected response.", "error")
            
    elif req.status == 400:
        # AJOUT : Gestion spécifique pour Fichier Vide / Erreur Client
        try:
            err_resp = json.loads(req.text)
            msg = err_resp.get('error', 'Bad Request')
        except:
            msg = "The file content is invalid."
        
        # On affiche le message précis envoyé par le serveur ("The file is empty...")
        show_custom_alert("File Rejected", msg, "error")

    elif req.status == 415:
        # Erreur Signature (Magic Bytes)
        try:
            err_resp = json.loads(req.text)
            msg = err_resp.get('error', 'Invalid format.')
        except:
            msg = "This file appears corrupt."
        show_custom_alert("Format Rejected", msg, "error")
        
    elif req.status == 413:
         show_custom_alert("File Too Large", "The file exceeds the maximum size.", "error")
         
    else:
        show_custom_alert("Server Error", f"Code {req.status}. Please try again.", "error")


def on_file_select(ev):
    if not ev.target.files or ev.target.files.length == 0:
        return

    file = ev.target.files[0]
    
    # Client Validation (Size)
    if file.size > 10 * 1024 * 1024:
        show_custom_alert("File Too Large", "The limit is 10 MB for this demo.", "error")
        document["file-input"].value = ""
        return

    # UI Loading
    if BTN_ID in document:
        btn = document[BTN_ID]
        global original_btn_text
        if btn.text != "⏳ Analyzing...": 
            original_btn_text = btn.text 
        btn.text = "⏳ Analyzing..."
        btn.classList.add('cursor-wait', 'opacity-50')
        btn.disabled = True
    
    # Send
    form_data = window.FormData.new()
    form_data.append("file", file)
    
    req = ajax.ajax()
    req.bind('complete', on_upload_complete)
    # Dynamic URL via Web2py
    target_url = window.target_url
    req.open('POST', target_url)
    req.send(form_data)

# --- BINDINGS ---
if "file-input" in document:
    document["file-input"].bind("change", on_file_select)

# Bind alert close button
if "btn-close-landing-alert" in document:
    document["btn-close-landing-alert"].bind("click", close_custom_alert)
