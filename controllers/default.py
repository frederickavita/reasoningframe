# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------
# This is a sample controller
# this file is released under public domain and you can use without limitations
# -------------------------------------------------------------------------

# ---- example index page ----
GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPE         = 'openid email profile'


def index():
    # Récupérer le code du parrain dans l'URL (ex: ?ref=abc1234)
    return dict()


def success():
    lead = db.lead(request.vars.id) or redirect(URL('index'))
    total_waitlist = db(db.lead).count()
    # Calcul de la position (très basique pour le MVP)
    position = total_waitlist - lead.points 
    share_url = URL('index', vars={'ref': lead.referral_code}, scheme=True, host=True)
    return dict(lead=lead, position=position, share_url=share_url)



def maintenance_clean_temp():
    """
    Supprime les fichiers vieux de 15 min (900s) en lisant le Timestamp dans le nom.
    Format attendu : guest_{TIMESTAMP}_{UUID}_{NOM_ORIGINAL}
    """
    import os
    import time
    
    temp_folder = os.path.join(request.folder, 'uploads', 'temp')
    TTL = 900 
    now = int(time.time())
    
    if not os.path.exists(temp_folder):
        return

    try:
        for filename in os.listdir(temp_folder):
            # On ne traite que nos fichiers "guest"
            if not filename.startswith("guest_"):
                continue

            file_path = os.path.join(temp_folder, filename)
            
            try:
                # Structure : guest_1738165000_uuid-long_monfichier.csv
                # On récupère le 2ème élément (index 1) qui est le timestamp
                parts = filename.split('_')
                if len(parts) < 3: continue # Sécurité format
                
                file_ts = int(parts[1])
                
                # Si (Maintenant - DateCréation) > 15 min
                if (now - file_ts) > TTL:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
            except (ValueError, IndexError):
                # Si le nom est mal formé, on ignore (ou on supprime par sécurité)
                pass
                
    except Exception:
        pass




def api_verify_guest_upload():
    import os
    import shutil
    import uuid
    import time
    import re
    from importlib import reload

    """
    Endpoint de validation V1.3 (Fusionné).
    Gère l'upload sécurisé ET le parsing immédiat pour la preview.
    """
    
    # 0. Nettoyage préventif
    maintenance_clean_temp()
    
    response.headers['Content-Type'] = 'application/json'
    print("\n" + "="*50)
    print("DEBUG: Début api_verify_guest_upload")

    # --- 1. Vérification Présence ---
    if not request.vars.file:
        print("DEBUG: ERREUR - Pas de fichier reçu")
        response.status = 400
        return response.json({'status': 'error', 'message': "Aucun fichier reçu."})
        
    f_stream = request.vars.file.file
    
    # SECURITE : On force le basename
    original_filename = os.path.basename(request.vars.file.filename)
    filename_lower = original_filename.lower()
    print(f"DEBUG: Fichier reçu: {original_filename}")
    
    # --- 2. Vérification Taille ---
    f_stream.seek(0, 2)
    size = f_stream.tell()
    f_stream.seek(0)
    
    if size == 0:
        response.status = 400
        return response.json({'status': 'error', 'message': "Fichier vide."})
    
    if size > 50 * 1024 * 1024:
        response.status = 400
        return response.json({'status': 'error', 'message': "Fichier trop volumineux (> 50 Mo)."})

    # --- 3. Vérification Format ---
    header = f_stream.read(4) 
    f_stream.seek(0) 
    
    # A. Rejet .xls
    if filename_lower.endswith('.xls'):
        response.status = 415
        return response.json({'status': 'error', 'message': "Format .xls obsolète. Utilisez .xlsx ou .csv."})

    # B. Détection Excel
    is_xlsx = header.startswith(b'PK\x03\x04') and filename_lower.endswith('.xlsx')
    is_csv = False
    
    # C. Détection CSV
    if filename_lower.endswith('.csv') or filename_lower.endswith('.tsv') or filename_lower.endswith('.txt'):
        try:
            sample = f_stream.read(4096)
            if len(sample) == 0: is_csv = False
            elif b'\0' in sample: is_csv = False
            else:
                try:
                    sample.decode('utf-8')
                    is_csv = True
                except UnicodeDecodeError:
                    try:
                        sample.decode('latin-1')
                        non_printable = sum(1 for c in sample if c < 32 and c not in (9, 10, 13))
                        if (non_printable / len(sample)) > 0.3: is_csv = False
                        else: is_csv = True
                    except: is_csv = False
        except: is_csv = False
        finally: f_stream.seek(0)

    if not (is_xlsx or is_csv):
        response.status = 415 
        return response.json({'status': 'error', 'message': "Format non reconnu. Utilisez .xlsx ou .csv."})
    
    # --- 4. SAUVEGARDE TEMP ---
    unique_id = str(uuid.uuid4())
    current_ts = int(time.time())
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', original_filename)
    temp_filename = f"guest_{current_ts}_{unique_id}_{safe_name}"
    
    temp_dir = os.path.join(request.folder, 'uploads', 'temp')
    if not os.path.exists(temp_dir): os.makedirs(temp_dir)
        
    temp_path = os.path.join(temp_dir, temp_filename)
        
    try:
        with open(temp_path, 'wb') as dest:
            shutil.copyfileobj(f_stream, dest)
    except Exception:
        response.status = 500
        return response.json({'status': 'error', 'message': "Erreur interne (Stockage)."})

    # --- 5. PARSING (L'étape qui manquait !) ---
    try:
        # Import robuste avec reload
        try:
            import applications.reasoningframe.modules.data_utils as data_utils
            reload(data_utils)
        except ImportError:
            import data_utils
            reload(data_utils)

        # Appel du module
        data = data_utils.read_file_to_virtual_table(temp_path, preview_limit=10)
        
        if data['status'] == 'error':
             return response.json(data)
             
        # --- 6. MISE EN SESSION ---
        session.pending_import = {
            'path': temp_path,
            'original_name': original_filename,
            'type': 'csv' if is_csv else 'xlsx',
            'id': unique_id
        }
        
        # --- 7. REPONSE JSON COMPLETE ---
        # On renvoie TOUT ce dont le frontend a besoin
        return response.json({
            'status': "success", 
            'message': "Fichier validé.",
            'file_id': unique_id,
            'original_name': original_filename,
            'type': 'csv' if is_csv else 'xlsx',
            'file': {
                'name': original_filename,
                'detected_rows': data.get('total_rows', 0),
                'detected_header_row': data.get('file', {}).get('detected_header_row', 1)
            },
            'columns': data.get('columns', []),
            'sample_rows': [r.get('raw', []) for r in data.get('rows', [])]
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return response.json({'status': 'error', 'message': f"Erreur Analyse: {str(e)}"})

# -------------------------------------------------------------------------
# 1. TEST CONNEXION (PING)
# -------------------------------------------------------------------------
def api_test_gemini():
    response.headers['Content-Type'] = 'application/json'
    
    # ✅ FIX INDISPENSABLE : Import de reload
    from importlib import reload 

    # 1. Rate Limit
    if not _rate_limit('last_ai_test_ts', 1.0):
        return response.json({'status': 'error', 'code': 'RATE_LIMIT', 'message': "Doucement !"})

    api_key = request.vars.api_key
    model_choice = request.vars.model or "lite" 

    # 2. Validation
    if not isinstance(api_key, str):
        return response.json({'status': 'error', 'code': 'INVALID_KEY', 'message': "Format invalide."})
    api_key = api_key.strip()
    if not api_key:
        return response.json({'status': 'error', 'code': 'INVALID_KEY', 'message': "Clé API vide."})

    # 3. Import & Reload (Spécifique reasoningframe)
    try:
        import applications.reasoningframe.modules.ai_engine as ai_engine
        reload(ai_engine)
    except ImportError:
        try:
            # Fallback classique
            import ai_engine
            reload(ai_engine)
        except Exception as e:
             return response.json({'status': 'error', 'message': f"Erreur Import Fallback: {str(e)}"})
    except Exception as e:
        return response.json({'status': 'error', 'message': f"Erreur Import Serveur: {str(e)}"})

    # 4. Appel
    try:
        ok, msg, model_id, code = ai_engine.test_connection(api_key, model_choice)
        return response.json({
            'status': 'success' if ok else 'error',
            'code': code,
            'message': msg,
            'model_id': model_id
        })
    except Exception as e:
        return response.json({'status': 'error', 'message': f"Crash Test: {str(e)}"})

# -------------------------------------------------------------------------
# 2. SCAN DES COLONNES (LE CERVEAU)
# -------------------------------------------------------------------------
def api_ai_scan_columns():
    response.headers['Content-Type'] = 'application/json'
    
    # ✅ FIX INDISPENSABLE : Import de reload
    from importlib import reload

    # 1. Rate Limit
    if not _rate_limit('last_ai_scan_ts', 2.0):
        return response.json({'status': 'error', 'code': 'RATE_LIMIT', 'message': "Analyse en cours..."})

    api_key = request.vars.api_key
    model_choice = request.vars.model or "lite"

    # 2. Validation
    if not api_key: 
        return response.json({'status': 'error', 'code': 'INVALID_KEY', 'message': "Clé requise."})
    
    pending = session.get('pending_import')
    if not pending: 
        return response.json({'status': 'error', 'code': 'SESSION_EXPIRED', 'message': "Session expirée (Aucun fichier)."})
    
    file_path = pending.get('path')
    
    # 3. Sécurité Path
    temp_root = os.path.abspath(os.path.join(request.folder, 'uploads', 'temp'))
    abs_path = os.path.abspath(file_path) if file_path else ""
    if not file_path or not abs_path.startswith(temp_root):
        return response.json({'status': 'error', 'code': 'FORBIDDEN', 'message': "Fichier introuvable ou interdit."})

    # 4. Imports & Reloads
    try:
        import applications.reasoningframe.modules.data_utils as data_utils
        import applications.reasoningframe.modules.ai_engine as ai_engine
        reload(data_utils)
        reload(ai_engine)
    except ImportError:
        try:
            import data_utils
            import ai_engine
            reload(data_utils)
            reload(ai_engine)
        except Exception as e:
             return response.json({'status': 'error', 'message': f"Erreur Import Fallback: {str(e)}"})
    except Exception as e:
        return response.json({'status': 'error', 'message': f"Erreur Import Module: {str(e)}"})

    # 5. Lecture Fichier
    try:
        vt = data_utils.read_file_to_virtual_table(file_path, preview_limit=10)
        print(vt)
        if vt.get('status') != 'success':
            print(vt)
            return response.json({'status': 'error', 'code': 'PARSE_ERROR', 'message': vt.get('message')})
    except Exception as e:
        print(str(e))
        return response.json({'status': 'error', 'message': f"Crash Parser: {str(e)}"})

    # 6. Appel IA
    print("DEBUG: Appel AI Engine")
    try:
        ai_result = ai_engine.analyze_csv_sample(
            api_key=api_key.strip(),
            model_short_name=model_choice,
            columns=vt.get('columns', []),
            sample_rows=[r.get('raw', []) for r in vt.get('rows', [])]
        )

        if ai_result['status'] == 'success':
            data = ai_result['data']
            model_real_id = ai_engine.MODELS.get(model_choice, "unknown")
            
            return response.json({
                'status': 'success',
                'mapping': data.get('mapping', {}),
                'confidence': data.get('confidence', 0),
                'model_id': model_real_id
            })
        else:
            return response.json({
                'status': 'error',
                'code': ai_result.get('code', 'AI_ERROR'),
                'message': ai_result.get('message', 'Erreur IA')
            })
            
    except Exception as e:
        return response.json({'status': 'error', 'message': f"Crash AI Engine: {str(e)}"})

def app():
    maintenance_clean_temp()
    if not auth.user:
        redirect(URL('default', 'login'))
    import json
    import os
    pending_file = None
    pending = session.get('pending_import')

    if pending:
        file_path = pending.get('path')
        file_name = pending.get('original_name')

        if file_path and os.path.exists(file_path):
            pending_file = {
                'status': 'restored',
                'name': file_name,
                'type': pending.get('type'),
                'path': file_path
            }
        else:
            pending_file = {
                'status': 'expired',
                'name': file_name
            }

        session.pending_import = None

    return dict(pending_file_json=json.dumps(pending_file) if pending_file else 'null')

def api_get_mapping_data():
    """
    Lit le fichier temporaire stocké en session et renvoie la structure (VirtualTable).
    Version Dev : Force le reload du module data_utils à chaque appel.
    """
    import os
    import importlib # Nécessaire pour le reload
    
    # 1. IMPORT & RELOAD (Pour le développement)
    # On importe d'abord le module complet pour pouvoir le recharger
    try:
        import applications.reasoningframe.modules.data_utils as data_utils_module
        
        # FORCE LE RELOAD : Oblige Python à relire le fichier data_utils.py
        importlib.reload(data_utils_module)
        
        # On récupère la fonction depuis le module rechargé
        read_file_to_virtual_table = data_utils_module.read_file_to_virtual_table
        
    except ImportError as e:
        print(f"API ERROR: {str(e)}")
        # Fallback ou erreur explicite
        response.status = 500
        return response.json({'status': 'error', 'message': f"Module introuvable : {str(e)}"})

    response.headers['Content-Type'] = 'application/json'

    # 2. AUTHENTIFICATION API
    if not auth.user:
        response.status = 401
        return response.json({'status': 'error', 'message': 'Session expirée. Veuillez vous reconnecter.'})

    # 3. VÉRIFICATION SESSION
    pending = session.get('pending_import')
    
    if not pending or not isinstance(pending, dict):
        response.status = 400
        return response.json({'status': 'error', 'message': 'Session upload expirée. Veuillez réuploader le fichier.'})

    file_path = pending.get('path')
    
    # 4. SÉCURITÉ PATH
    if not file_path or not isinstance(file_path, str):
        response.status = 400
        return response.json({'status': 'error', 'message': 'Chemin de fichier invalide.'})
        
    temp_root = os.path.abspath(os.path.join(request.folder, 'uploads', 'temp'))
    abs_path = os.path.abspath(file_path)
    
    if not abs_path.startswith(temp_root):
        session.pending_import = None 
        response.status = 403
        return response.json({'status': 'error', 'message': 'Accès fichier interdit.'})

    try:
        # 5. LECTURE INTELLIGENTE
        result = read_file_to_virtual_table(file_path, preview_limit=10)

        if result.get('status') == 'error':
            response.status = 400
            return response.json(result)

        # 6. ENRICHISSEMENT META-DATA
        result.setdefault('file', {})
        result['file']['original_name'] = pending.get('original_name', 'Inconnu')
        result['file']['file_id'] = pending.get('id')

        return response.json(result)

    except Exception as e:
        response.status = 500
        print(f"API ERROR: {str(e)}")
        # On utilise type(e).__name__ pour ne pas fuiter d'infos sensibles
        return response.json({'status': 'error', 'message': f"Erreur serveur interne ({type(e).__name__})"})




# controllers/default.py

def dashboard():
    if not auth.user:
        redirect(URL('default', 'user', args='login'))
    
    # 1. State Management for UI Testing
    # Options: 'ideal' (default, fetches DB), 'empty', 'partial', 'loading', 'error'
    current_state = request.vars.state or 'ideal'
    
    # User info
    user_credits = auth.user.credits if hasattr(auth.user, 'credits') else 0 # Assuming you added a credits field to auth_user
    
    # 2. Logic based on State
    projects = []
    is_loading = False
    error_message = None
    
    if current_state == 'ideal':
        # FETCH REAL DATA FROM DB
        rows = db(db.generated_reports.user_id == auth.user.id).select(orderby=~db.generated_reports.created_on)
        
        # Convert rows to list of dicts for the view (normalizing keys)
        for row in rows:
            projects.append({
                'id': row.id,
                'created_on': row.created_on.strftime("%d %b %H:%M"),
                'niche': row.niche,
                'project_name': row.project_name,
                'concept': row.concept,
                'status': row.status,
                'prompt_preview': row.prompt_preview
            })
            
    elif current_state == 'partial':
        # Fetch just one (or fake one if DB empty)
        if db(db.generated_reports.user_id == auth.user.id).count() > 0:
             row = db(db.generated_reports.user_id == auth.user.id).select(limitby=(0,1)).first()
             projects = [{
                'id': row.id,
                'created_on': row.created_on.strftime("%d %b %H:%M"),
                'niche': row.niche,
                'project_name': row.project_name,
                'concept': row.concept,
                'status': row.status,
                'prompt_preview': row.prompt_preview
            }]
        else:
            # Fallback fake data if DB is empty so "partial" state still works for visuals
            projects = [{
                'id': 999, 
                'created_on': 'Today', 
                'niche': 'Demo Niche', 
                'project_name': 'DemoProject', 
                'concept': 'This is a demo project for the partial state.', 
                'status': 'complete', 
                'prompt_preview': 'Demo prompt...'
            }]

    elif current_state == 'empty':
        projects = [] # Force empty list
        
    elif current_state == 'loading':
        is_loading = True
        
    elif current_state == 'error':
        error_message = "Unable to retrieve projects. The database server is not responding."

    # Metrics
    total_generated = len(projects)
    hours_saved = total_generated * 2

    return dict(
        projects=projects,
        credits=user_credits,
        total_generated=total_generated,
        hours_saved=hours_saved,
        current_state=current_state,
        is_loading=is_loading,
        error_message=error_message
    )


def login():
    next_url = request.vars._next or session.get('oauth_next') or URL('default', 'dashboard')
    google_url = URL('default', 'google_begin', vars={'_next': next_url}) 
    return dict(google_url=google_url)


def google_redirect_uri():
    # => AJOUTE EXACTEMENT cette URL dans la console Google (Authorized redirect URIs)
    return URL('default', 'google_callback', scheme=True, host=True)


def google_begin():
    from urllib.parse import urlencode
    import uuid
    GOOGLE_CLIENT_ID = configuration.get('google.client_id')
    GOOGLE_CLIENT_SECRET = configuration.get('google.client_secret')
    """
    Démarre l’autorisation Google et envoie l’utilisateur chez Google.
    Tu peux appeler ce endpoint depuis ton bouton 'Continuer avec Google'.
    """
    state = str(uuid.uuid4())
    session.oauth_state = state

    # Où rediriger après login ? (optionnel)
    _next = request.vars.get('_next')
    if _next:
        session.oauth_next = _next

    params = dict(
        client_id=GOOGLE_CLIENT_ID,
        response_type='code',
        scope=GOOGLE_SCOPE,
        redirect_uri=google_redirect_uri(),
        include_granted_scopes='true',
        access_type='online',         # ou 'offline' si tu veux un refresh_token
        state=state,
        prompt='consent'              # optionnel
    )
    redirect(GOOGLE_AUTH_URL + '?' + urlencode(params))


def google_callback():
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
    import json
    import logging
    GOOGLE_CLIENT_ID = configuration.get('google.client_id')
    GOOGLE_CLIENT_SECRET = configuration.get('google.client_secret')
    """
    Redirect URI autorisée (Google renvoie ici ?code&state ou ?error).
    Échange le code, récupère /userinfo, connecte/crée l’utilisateur,
    puis redirige vers _next (ou dashboard par défaut).
    """
    logger = logging.getLogger("web2py.app.yourfirstship")
    # 1) Erreur utilisateur (annule)
    if request.vars.get('error'):
        session.flash = 'Google sign-in cancelled.'
        return redirect(URL('default', 'login'))

    # 2) Anti-CSRF state
    if not session.get('oauth_state') or request.vars.get('state') != session.oauth_state:
        session.flash = 'Invalid state token.'
        return redirect(URL('default', 'login'))

    # 3) Code présent ?
    code = request.vars.get('code')
    if not code:
        session.flash = 'Authorization code missing.'
        return redirect(URL('default','login'))

    # 4) Échange code -> token
    data = dict(
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        code=code,
        grant_type='authorization_code',
        redirect_uri=google_redirect_uri(),   # DOIT être identique à celle utilisée à l’aller
    )
    body = urlencode(data).encode('utf-8')
    try:
        resp = urlopen(Request(GOOGLE_TOKEN_URL,
                               data=body,
                               headers={'Content-Type':'application/x-www-form-urlencoded'}),
                       timeout=10)
        token_payload = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.error('Token exchange failed: %s', e)
        session.flash = 'Token exchange failed.'
        return redirect(URL('default', 'login'))

    access_token = token_payload.get('access_token')
    if not access_token:
        session.flash = 'Access token missing.'
        return redirect(URL('default','login'))

    session.token = access_token  # si tu veux le réutiliser ailleurs

    # 5) /userinfo
    try:
        uresp = urlopen(Request(GOOGLE_USERINFO_URL,
                                headers={'Authorization': 'Bearer %s' % access_token}),
                        timeout=10)
        data = json.loads(uresp.read().decode('utf-8'))
    except Exception as e:
        logger.error('Userinfo failed: %s', e)
        session.flash = 'Unable to read Google profile.'
        return redirect(URL('default','login'))

    profile = dict(
        first_name = data.get('given_name', ''),
        last_name  = data.get('family_name', ''),
        email      = data.get('email') or '',
        
        # --- AJOUT CRUCIAL ---
        google_id  = data.get('sub'), # C'est l'identifiant unique de l'utilisateur chez Google
        # ---------------------
        
        # Optionnel : On définit le username comme l'email pour éviter des erreurs
        username   = data.get('email')
    )

    # 7) Création/connexion utilisateur web2py
    user = auth.get_or_create_user(profile)   # crée si inexistant
    if not user:
        session.flash = 'Unable to create or log in user.'
        return redirect(URL('default', 'login'))
    
    auth.login_user(user)
    # 8) Redirection finale
    _next = session.pop('oauth_next', None) or request.vars.get('_next') or URL('default','dashboard')
    redirect(_next)



def archive_import_file(temp_path, original_name, status, rows, log_data, model_used):
    """
    Déplace le fichier de TEMP vers PROTECTED et enregistre l'entrée en BDD.

    - Si le fichier n'existe plus: on log, on insère l'historique (sans stored_filename).
    - Si le move échoue: status passe en WARNING (import possiblement OK), stored_filename=None.
    - stored_filename n'est renseigné que si le fichier est effectivement archivé.

    Retour:
        import_id (id de t_import_history)
    """
    import os
    import shutil

    # Normaliser le log
    log_data = dict(log_data) if isinstance(log_data, dict) else {}

    # Normaliser status
    allowed_status = {"PENDING", "SUCCESS", "FAILED", "WARNING"}
    if status not in allowed_status:
        status = "FAILED"

    # Normaliser rows
    try:
        rows_int = int(rows)
        if rows_int < 0:
            rows_int = 0
    except Exception:
        rows_int = 0

    # Normaliser model_used
    if not isinstance(model_used, str) or not model_used.strip():
        model_used = "gemini-2.0-flash"
    model_used = model_used.strip()[:100]

    # Dossier cible (supposé non exposé publiquement selon ton infra)
    protected_folder = os.path.join(request.folder, "uploads", "protected")
    if not os.path.exists(protected_folder):
        os.makedirs(protected_folder)

    archived = False
    stored_filename = None
    file_size = 0

    # Valider temp_path
    if not isinstance(temp_path, str) or not temp_path.strip():
        log_data["error"] = "temp_path invalide"
        status = "FAILED"
    else:
        temp_path = temp_path.strip()
        filename_on_disk = os.path.basename(temp_path)
        final_path = os.path.join(protected_folder, filename_on_disk)

        # Déplacement
        if os.path.exists(temp_path):
            try:
                file_size = os.path.getsize(temp_path)

                # shutil.move est atomique uniquement si rename sur même filesystem,
                # sinon c'est copy+delete. On gère les erreurs proprement.
                shutil.move(temp_path, final_path)

                archived = True
                stored_filename = filename_on_disk

            except Exception as e:
                log_data["error_move"] = f"{type(e).__name__}: {str(e)[:200]}"
                # import peut avoir réussi mais archive fail => WARNING
                if status == "SUCCESS":
                    status = "WARNING"
                stored_filename = None
                file_size = 0
        else:
            log_data["error"] = "Fichier source introuvable (expiré ou déjà traité)"
            # Ici: import peut avoir réussi, mais archive impossible => WARNING
            if status == "SUCCESS":
                status = "WARNING"
            stored_filename = None
            file_size = 0

    # Insert DB
    import_id = db.t_import_history.insert(
        original_filename=str(original_name)[:255] if original_name is not None else "unknown",
        stored_filename=stored_filename,
        file_size=file_size,
        status=status,
        row_count=rows_int,
        ai_model=model_used,
        process_log=log_data
    )

    return import_id


@auth.requires_login()
def api_commit_import():
    import json
    response.headers["Content-Type"] = "application/json"

    # 1) Vérification session (safe)
    pending = session.get("pending_import")
    if not pending or not isinstance(pending, dict):
        response.status = 400
        return response.json({
            "status": "error",
            "message": "Session expirée ou aucun fichier en attente."
        })

    # Validation minimale des champs attendus
    temp_path = pending.get("path")
    original_name = pending.get("original_name") or pending.get("original_filename") or pending.get("name")

    if not temp_path or not isinstance(temp_path, str):
        response.status = 400
        session.pending_import = None
        return response.json({
            "status": "error",
            "message": "Ticket session invalide (path manquant)."
        })

    if not original_name or not isinstance(original_name, str):
        original_name = "unknown"

    # 2) Lecture JSON frontend (optionnel)
    try:
        req_json = request.json or {}
    except Exception:
        req_json = {}

    model_used = req_json.get("model", "gemini-2.0-flash")
    if not isinstance(model_used, str) or len(model_used) > 100:
        model_used = "gemini-2.0-flash"

    # Optionnel: rows envoyé par le frontend
    rows_front = req_json.get("rows")
    try:
        rows_front = int(rows_front) if rows_front is not None else None
        if rows_front is not None and rows_front < 0:
            rows_front = 0
    except Exception:
        rows_front = None

    # ---------------------------------------------------------
    # ZONE DE TRAITEMENT MÉTIER (SIMULATION)
    # ---------------------------------------------------------
    # Ici: tu insères réellement les données mappées dans tes tables finales.
    # Pour l'instant: simulation.
    rows_inserted = rows_front if rows_front is not None else 1240
    processing_log = {
        "msg": "Import réalisé avec succès",
        "steps": ["mapping", "cleaning", "insertion"],
        "duration_ms": 2400
    }
    # ---------------------------------------------------------

    # 3) Archivage + historique
    try:
        history_id = archive_import_file(
            temp_path=temp_path,
            original_name=original_name,
            status="SUCCESS",
            rows=rows_inserted,
            log_data=processing_log,
            model_used=model_used
        )
    except Exception as e:
        # On ne veut pas casser l'import à cause de l'historique
        # Mais on évite aussi le double commit => on consomme la session.
        session.pending_import = None
        return response.json({
            "status": "warning",
            "message": f"Import OK mais erreur historique: {type(e).__name__}",
            "rows": rows_inserted
        })

    # 4) Nettoyage session (anti doublon)
    session.pending_import = None

    # 5) Réponse
    return response.json({
        "status": "success",
        "history_id": history_id,
        "rows": rows_inserted
    })


def logout():
    return dict(form=auth.logout())

def api_upload():
    return dict() 


def api_mapping_suggestion():
    return dict()

def api_save_data():
    return dict()


# ---- API (example) -----
@auth.requires_login()
def api_get_user_email():
    if not request.env.request_method == 'GET': raise HTTP(403)
    return response.json({'status':'success', 'email':auth.user.email})

# ---- Smart Grid (example) -----
@auth.requires_membership('admin') # can only be accessed by members of admin groupd
def grid():
    response.view = 'generic.html' # use a generic view
    tablename = request.args(0)
    if not tablename in db.tables: raise HTTP(403)
    grid = SQLFORM.smartgrid(db[tablename], args=[tablename], deletable=False, editable=False)
    return dict(grid=grid)

# ---- Embedded wiki (example) ----
def wiki():
    auth.wikimenu() # add the wiki to the menu
    return auth.wiki() 

# ---- Action for login/register/etc (required for auth) -----
def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    http://..../[app]/default/user/bulk_register
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    also notice there is http://..../[app]/appadmin/manage/auth to allow administrator to manage users
    """
    return dict(form=auth())

# ---- action to server uploaded static content (required) ---
@cache.action()
def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request, db)
