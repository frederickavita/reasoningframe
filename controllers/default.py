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


# controllers/default.py

def dashboard():
    if not auth.user:
        redirect(URL('default', 'user', args='login'))
    
    # --- FIX CRITIQUE : On recharge l'user depuis la DB pour avoir les crédits à jour ---
    fresh_user = db.auth_user(auth.user.id)
    credits = fresh_user.credits if fresh_user else 0
    # ----------------------------------------------------------------------------------

    # Récupération des projets
    projects = db(db.generated_reports.user_id == auth.user.id).select(orderby=~db.generated_reports.created_on)
    
    # Stats (Fake logic pour l'instant ou calcul réel)
    total_generated = len(projects)
    hours_saved = total_generated * 5 # On dit qu'un projet sauve 5h

    # Gestion de l'état "Loading" si on vient d'ajouter un projet
    is_loading = request.vars.get('state') == 'loading'

    return dict(
        projects=projects, 
        credits=credits, # On passe la variable fraîche
        total_generated=total_generated,
        hours_saved=hours_saved,
        is_loading=is_loading,
        error_message=None
    )

def process_niche():
    if not auth.user:
        redirect(URL('default', 'user', args='login'))

    # --- FIX CRITIQUE : On vérifie le solde RÉEL en base, pas celui de la session ---
    fresh_user = db.auth_user(auth.user.id)
    current_credits = fresh_user.credits if fresh_user else 0

    if current_credits < 1:
        session.flash = "Crédits insuffisants. Veuillez recharger."
        redirect(URL('default', 'new_analysis'))
    # -------------------------------------------------------------------------------

    mode = request.vars.analysis_mode
    final_input = ""
    prompt_context = ""

    if mode == 'target':
        final_input = request.vars.niche
        prompt_context = f"Target: {final_input} | URL: {request.vars.specific_url_target}"
    elif mode == 'pain':
        final_input = request.vars.problem_context
        prompt_context = f"Pain: {final_input} | URL: {request.vars.specific_url_pain}"

    if not final_input:
        session.flash = "Champ requis manquant."
        redirect(URL('default', 'new_analysis'))

    # 1. Débit du crédit en BDD
    new_credits = current_credits - 1
    db(db.auth_user.id == auth.user.id).update(credits=new_credits)
    
    # 2. Mise à jour de la session (pour que l'interface reste synchro immédiatement)
    auth.user.credits = new_credits 

    # 3. Création du projet
    db.generated_reports.insert(
        user_id = auth.user.id,
        project_name = f"Mission: {final_input[:20]}...",
        niche = final_input,
        status = 'processing', # IMPORTANT pour le loader
        concept = "Agent is scanning the web...",
        prompt_preview = prompt_context
    )

    # 4. Retour au dashboard
    redirect(URL('default', 'dashboard'))


def new_analysis():
    # Affichage du formulaire
    if not auth.user:
        redirect(URL('default', 'login'))
    return dict()





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
        username   = data.get('email'),
        avatar_url = data.get('picture', '')
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



def logout():
    return dict(form=auth.logout())


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
