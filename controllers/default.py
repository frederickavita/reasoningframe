

GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPE         = 'openid email profile'
 


# -*- coding: utf-8 -*-
# controllers/default.py (bloc login / logout / Google OAuth)

import uuid
import json
import logging # <-- AJOUTEZ CECI
from applications.reasoningframe.modules.app_services import create_page, ValidationError, PermissionDeniedError
# Initialisation d'un logger standard pour ce contrôleur
logger = logging.getLogger("app.reasoningframe")

try:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import urlencode
    from urllib2 import Request, urlopen





def login():
    """Page de login Google."""
    if auth.user:
        redirect(URL('default', 'dashboard'))

    next_url = request.vars._next or session.get('oauth_next') or URL('default', 'dashboard')
    google_url = URL('default', 'google_begin', vars={'_next': next_url})

    error_text = response.flash or session.flash or ''
    initial_state = 'state-ideal'
    if error_text:
        initial_state = 'state-error'

    response.title = T('Sign In')
    response.subtitle = T('Sign in with Google to resume your journey')

    return dict(
        google_url=google_url,
        initial_state=initial_state,
        error_text=error_text,
    )


@auth.requires_login()
def api_create_page():
    try:
        page = create_page(
            user_id=auth.user_id,
            project_id=request.vars.project_id,
            name=request.vars.name,
            route=request.vars.route
        )
        return response.json(dict(ok=True, page_id=page.id, name=page.name))
    except ValidationError as e:
        return response.json(dict(ok=False, error=str(e), field_errors=e.field_errors))
    except PermissionDeniedError as e:
        response.status = 403
        return response.json(dict(ok=False, error=str(e)))



def logout():
    """Déconnexion standard."""
    return auth.logout(next=URL('default', 'login'))


def google_redirect_uri():
    """URL absolue exigée par Google."""
    return URL('default', 'google_callback', scheme=True, host=True)


def google_begin():
    """Démarre le flux Google OAuth2 / OpenID Connect."""
    google_client_id, _ = _get_google_config()

    if not google_client_id:
        _flash_login_error(T("Configuration OAuth Google incomplète."))

    state = str(uuid.uuid4())
    session.oauth_state = state

    nxt = request.vars.get('_next')
    if nxt:
        session.oauth_next = nxt

    params = dict(
        client_id=google_client_id,
        response_type='code',
        scope='openid email profile',
        redirect_uri=google_redirect_uri(),
        include_granted_scopes='true',
        access_type='online',
        state=state,
        prompt='select_account'
    )

    redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))


def google_callback():
    """Gère le retour Google, l'upsert utilisateur et la connexion."""
    google_client_id, google_client_secret = _get_google_config()

    if not google_client_id or not google_client_secret:
        _flash_login_error(T("Configuration OAuth Google incomplète."))

    oauth_state = session.pop('oauth_state', None)
    if not oauth_state or request.vars.get('state') != oauth_state:
        _flash_login_error(T("Jeton de sécurité invalide."))

    code = request.vars.get('code')
    if not code:
        _flash_login_error(T("Code d'autorisation manquant."))

    # -------------------------------------------------------------------------
    # 1) Exchange code -> access token
    # -------------------------------------------------------------------------
    token_data = dict(
        client_id=google_client_id,
        client_secret=google_client_secret,
        code=code,
        grant_type='authorization_code',
        redirect_uri=google_redirect_uri(),
    )

    try:
        req = Request(
            'https://oauth2.googleapis.com/token',
            data=urlencode(token_data).encode('utf-8')
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        token_payload = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
        access_token = token_payload.get('access_token')
    except Exception:
        _flash_login_error(T("Échec de la connexion aux serveurs Google."))

    if not access_token:
        _flash_login_error(T("Aucun jeton d'accès Google reçu."))

    # -------------------------------------------------------------------------
    # 2) Read Google profile
    # -------------------------------------------------------------------------
    try:
        req = Request('https://www.googleapis.com/oauth2/v3/userinfo')
        req.add_header('Authorization', 'Bearer %s' % access_token)
        google_data = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
    except Exception:
        _flash_login_error(T("Impossible de lire le profil Google."))

    clean = lambda x: str(x).strip() if x else ''

    google_sub = clean(google_data.get('sub'))
    email_value = clean(google_data.get('email')).lower()
    email_verified = bool(google_data.get('email_verified', False))
    given_name = clean(google_data.get('given_name'))
    family_name = clean(google_data.get('family_name'))
    avatar_url = clean(google_data.get('picture'))

    if not google_sub or not email_value:
        _flash_login_error(T("Les informations Google reçues sont incomplètes."))

    if not email_verified:
        _flash_login_error(T("Votre adresse email Google doit être vérifiée."))

    created = False

    # -------------------------------------------------------------------------
    # 3) Lookup priority:
    #    a) by google_sub
    #    b) fallback by email
    # -------------------------------------------------------------------------
    user = _get_auth_user_by_google_sub(google_sub)

    if not user:
        user = _get_auth_user_by_email(email_value)

    # -------------------------------------------------------------------------
    # 4) Create or update
    # -------------------------------------------------------------------------
    if not user:
        user_id = db.auth_user.insert(**_make_auth_user_payload(
            email_value=email_value,
            given_name=given_name,
            family_name=family_name,
            avatar_url=avatar_url,
            google_sub=google_sub,
            email_verified=email_verified
        ))
        user = db.auth_user[user_id]
        created = True
    else:
        _assert_user_can_login(user)

        _update_auth_user_profile(
            user_id=user.id,
            given_name=given_name,
            family_name=family_name,
            avatar_url=avatar_url,
            google_sub=google_sub,
            email_verified=email_verified
        )

        user = db.auth_user[user.id]

    # Re-check after create/update
    _assert_user_can_login(user)

    # -------------------------------------------------------------------------
    # 5) Post-login bootstrap
    # -------------------------------------------------------------------------
    _bootstrap_user_after_login(user.id)

    # -------------------------------------------------------------------------
    # 6) Login user
    # -------------------------------------------------------------------------
    auth.login_user(user)

    if created:
        session.flash = T("Bienvenue dans l'application !")
    else:
        session.flash = T("Content de vous revoir.")

    # -------------------------------------------------------------------------
    # 7) Redirect
    # -------------------------------------------------------------------------
    # Option A: toujours dashboard
    target = _safe_next_url(URL('default', 'dashboard'))

    # Option B: si tu veux gate l'app par entitlement lifetime :
    # if not user_has_active_lifetime_access(user.id):
    #     target = _safe_next_url(URL('billing', 'pricing'))
    # else:
    #     target = _safe_next_url(URL('default', 'dashboard'))

    redirect(target)





# def google_redirect_uri():
#     """URL absolue exigée par Google."""
#     return URL('default', 'google_callback', scheme=True, host=True)


# def google_begin():
#     """Démarre le flux Google OAuth2/OpenID Connect."""
#     google_client_id, _ = _get_google_config()

#     if not google_client_id:
#         _flash_login_error(T("Configuration OAuth Google incomplète."))

#     state = str(uuid.uuid4())
#     session.oauth_state = state

#     if request.vars.get('_next'):
#         session.oauth_next = request.vars.get('_next')

#     params = dict(
#         client_id=google_client_id,
#         response_type='code',
#         scope='openid email profile',
#         redirect_uri=google_redirect_uri(),
#         include_granted_scopes='true',
#         access_type='online',
#         state=state,
#         prompt='select_account'
#     )

#     redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))


# def google_callback():
#     """Gère le retour Google, l'upsert utilisateur et la connexion."""
#     google_client_id, google_client_secret = _get_google_config()

#     if not google_client_id or not google_client_secret:
#         _flash_login_error(T("Configuration OAuth Google incomplète."))

#     oauth_state = session.pop('oauth_state', None)
#     if not oauth_state or request.vars.get('state') != oauth_state:
#         _flash_login_error(T("Jeton de sécurité invalide."))

#     code = request.vars.get('code')
#     if not code:
#         _flash_login_error(T("Code d'autorisation manquant."))

#     data = dict(
#         client_id=google_client_id,
#         client_secret=google_client_secret,
#         code=code,
#         grant_type='authorization_code',
#         redirect_uri=google_redirect_uri(),
#     )

#     try:
#         req = Request(
#             'https://oauth2.googleapis.com/token',
#             data=urlencode(data).encode('utf-8')
#         )
#         req.add_header('Content-Type', 'application/x-www-form-urlencoded')
#         token_payload = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
#         access_token = token_payload.get('access_token')
#     except Exception as e:
#         _flash_login_error(T("Échec de la connexion aux serveurs Google."))

#     if not access_token:
#         _flash_login_error(T("Aucun jeton d'accès Google reçu."))

#     try:
#         req = Request('https://www.googleapis.com/oauth2/v3/userinfo')
#         req.add_header('Authorization', 'Bearer %s' % access_token)
#         google_data = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
#     except Exception as e:
#         _flash_login_error(T("Impossible de lire le profil Google."))

#     clean = lambda x: str(x).strip() if x else ''

#     google_sub = clean(google_data.get('sub'))
#     email_value = clean(google_data.get('email')).lower()
#     email_verified = bool(google_data.get('email_verified', False))
#     given_name = clean(google_data.get('given_name'))
#     family_name = clean(google_data.get('family_name'))
#     avatar_url = clean(google_data.get('picture'))
#     locale = clean(google_data.get('locale'))

#     if not google_sub or not email_value:
#         _flash_login_error(T("Les informations Google reçues sont incomplètes."))

#     if not email_verified:
#         _flash_login_error(T("Votre adresse email Google doit être vérifiée."))

#     # Normalisation langue
#     ui_language = 'fr'
#     learning_language = 'fr'
#     if locale.startswith('en'):
#         ui_language = 'en'
#         learning_language = 'en'
#     elif locale.startswith('es'):
#         ui_language = 'es'
#         learning_language = 'es'

#     created = False

#     # 1. recherche par registration_id = google:<sub>
#     user = _get_auth_user_by_google_sub(google_sub)

#     # 2. fallback par email
#     if not user:
#         user = _get_auth_user_by_email(email_value)

#     # 3. création si absent
#     if not user:
#         user_id = db.auth_user.insert(**_make_auth_user_payload(
#             email_value=email_value,
#             given_name=given_name,
#             family_name=family_name,
#             avatar_url=avatar_url,
#             ui_language=ui_language,
#             learning_language=learning_language
#         ))

#         db(db.auth_user.id == user_id).update(
#             registration_id='google:%s' % google_sub
#         )

#         user = db.auth_user[user_id]
#         created = True
#     else:
#         _update_auth_user_profile(
#             user_id=user.id,
#             given_name=given_name,
#             family_name=family_name,
#             avatar_url=avatar_url,
#             google_sub=google_sub
#         )

#     _bootstrap_user_after_login(user.id)

#     auth.login_user(user)

#     session.flash = T("Bienvenue dans l'application !") if created else T("Content de vous revoir.")
#     redirect(session.pop('oauth_next', None) or URL('default', 'dashboard'))

def index():
    if auth.user:
        redirect(URL('default', 'dashboard'))
    """
    Landing page
    """
    return dict()

def not_authorized():
    """
    Action pour afficher la page 'Accès restreint'.
    """
    # 1. Définition du titre de la page (facultatif mais recommandé)
    response.title = T("Accès restreint")
    
    # 2. Retourne un dictionnaire. Les clés deviennent des variables dans la vue.
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
