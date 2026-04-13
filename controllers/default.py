

GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPE         = 'openid email profile'
 


# -*- coding: utf-8 -*-
# controllers/default.py (bloc login / logout / Google OAuth)

import uuid
import json
import logging # <-- AJOUTEZ CECI

# Initialisation d'un logger standard pour ce contrôleur
logger = logging.getLogger("app.reasoningframe")

try:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
except ImportError:
    from urllib import urlencode
    from urllib2 import Request, urlopen


def dashboard():
    if not auth.user:
        redirect(URL('default', 'login', vars={'_next': URL('default', 'dashboard')}))

    response.title = T('Dashboard')
    response.subtitle = T('Welcome to your learning space')

    user = auth.user
    # Par défaut on passe sur l'anglais
    learning_language = user.learning_language or 'en'

    progress = db(db.user_progress.user_id == user.id).select().first()
    if not progress:
        progress_id = db.user_progress.insert(
            user_id=user.id,
            total_xp=0,
            level=1,
            current_streak=0,
            longest_streak=0,
            current_world_slug='world-1-discover',
            current_lesson_slug='what-claude-does-well', # Remplacé par le slug anglais du seed
            current_track='solopreneur',
            completed_lessons_count=0,
            completed_missions_count=0,
            unlocked_skills_count=0,
            first_lesson_started=False,
            first_mission_completed=False
        )
        progress = db.user_progress[progress_id]

    current_world = db(
        (db.learning_world.slug == progress.current_world_slug) &
        (db.learning_world.language == learning_language) &
        (db.learning_world.is_active == True)
    ).select().first()

    current_lesson = db(
        (db.learning_lesson.slug == progress.current_lesson_slug) &
        (db.learning_lesson.language == learning_language) &
        (db.learning_lesson.is_active == True) &
        (db.learning_lesson.is_published == True)
    ).select().first()

    # Fallback de sécurité (déjà géré de manière excellente)
    if not current_lesson:
        current_lesson = db(
            (db.learning_lesson.language == learning_language) &
            (db.learning_lesson.is_active == True) &
            (db.learning_lesson.is_published == True)
        ).select(orderby=db.learning_lesson.sort_order, limitby=(0, 1)).first()

    # Progression du monde courant
    world_progress_percent = 0
    completed_in_world = 0
    total_lessons_in_world = 0

    if current_world:
        world_lessons = db(
            (db.learning_lesson.world_id == current_world.id) &
            (db.learning_lesson.language == learning_language) &
            (db.learning_lesson.is_active == True) &
            (db.learning_lesson.is_published == True)
        ).select(db.learning_lesson.id, orderby=db.learning_lesson.sort_order)

        lesson_ids = [row.id for row in world_lessons]
        total_lessons_in_world = len(lesson_ids)

        if lesson_ids:
            completed_in_world = db(
                (db.lesson_progress.user_id == user.id) &
                (db.lesson_progress.lesson_id.belongs(lesson_ids)) &
                (db.lesson_progress.status.belongs(['completed', 'mastered']))
            ).count()

        if total_lessons_in_world:
            world_progress_percent = int((completed_in_world * 100.0) / total_lessons_in_world)

    # Mission à afficher
    current_mission = db(
        (db.learning_mission.language == learning_language) &
        (db.learning_mission.is_active == True) &
        (db.learning_mission.is_published == True)
    ).select(orderby=db.learning_mission.sort_order, limitby=(0, 1)).first()

    mission_progress = None
    if current_mission:
        mission_progress = db(
            (db.mission_progress.user_id == user.id) &
            (db.mission_progress.mission_id == current_mission.id)
        ).select().first()

    # Prompts rapides
    quick_prompts = db(
        (db.prompt_library.owner_type == 'system') &
        (db.prompt_library.visibility == 'course') &
        (db.prompt_library.language == learning_language) &
        (db.prompt_library.is_active == True)
    ).select(orderby=db.prompt_library.sort_order, limitby=(0, 3))

    return dict(
        progress=progress,
        current_world=current_world,
        current_lesson=current_lesson,
        current_mission=current_mission,
        mission_progress=mission_progress,
        quick_prompts=quick_prompts,
        world_progress_percent=world_progress_percent,
        completed_in_world=completed_in_world,
        total_lessons_in_world=total_lessons_in_world,
    )



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


def logout():
    """Déconnexion standard."""
    return auth.logout(next=URL('default', 'login'))


def google_redirect_uri():
    """URL absolue exigée par Google."""
    return URL('default', 'google_callback', scheme=True, host=True)


def google_begin():
    """Démarre le flux Google OAuth2/OpenID Connect."""
    google_client_id, _ = _get_google_config()

    if not google_client_id:
        _flash_login_error(T("Configuration OAuth Google incomplète."))

    state = str(uuid.uuid4())
    session.oauth_state = state

    if request.vars.get('_next'):
        session.oauth_next = request.vars.get('_next')

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

    data = dict(
        client_id=google_client_id,
        client_secret=google_client_secret,
        code=code,
        grant_type='authorization_code',
        redirect_uri=google_redirect_uri(),
    )

    try:
        req = Request(
            'https://oauth2.googleapis.com/token',
            data=urlencode(data).encode('utf-8')
        )
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        token_payload = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
        access_token = token_payload.get('access_token')
    except Exception as e:
        _flash_login_error(T("Échec de la connexion aux serveurs Google."))

    if not access_token:
        _flash_login_error(T("Aucun jeton d'accès Google reçu."))

    try:
        req = Request('https://www.googleapis.com/oauth2/v3/userinfo')
        req.add_header('Authorization', 'Bearer %s' % access_token)
        google_data = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
    except Exception as e:
        _flash_login_error(T("Impossible de lire le profil Google."))

    clean = lambda x: str(x).strip() if x else ''

    google_sub = clean(google_data.get('sub'))
    email_value = clean(google_data.get('email')).lower()
    email_verified = bool(google_data.get('email_verified', False))
    given_name = clean(google_data.get('given_name'))
    family_name = clean(google_data.get('family_name'))
    avatar_url = clean(google_data.get('picture'))
    locale = clean(google_data.get('locale'))

    if not google_sub or not email_value:
        _flash_login_error(T("Les informations Google reçues sont incomplètes."))

    if not email_verified:
        _flash_login_error(T("Votre adresse email Google doit être vérifiée."))

    # Normalisation langue
    ui_language = 'fr'
    learning_language = 'fr'
    if locale.startswith('en'):
        ui_language = 'en'
        learning_language = 'en'
    elif locale.startswith('es'):
        ui_language = 'es'
        learning_language = 'es'

    created = False

    # 1. recherche par registration_id = google:<sub>
    user = _get_auth_user_by_google_sub(google_sub)

    # 2. fallback par email
    if not user:
        user = _get_auth_user_by_email(email_value)

    # 3. création si absent
    if not user:
        user_id = db.auth_user.insert(**_make_auth_user_payload(
            email_value=email_value,
            given_name=given_name,
            family_name=family_name,
            avatar_url=avatar_url,
            ui_language=ui_language,
            learning_language=learning_language
        ))

        db(db.auth_user.id == user_id).update(
            registration_id='google:%s' % google_sub
        )

        user = db.auth_user[user_id]
        created = True
    else:
        _update_auth_user_profile(
            user_id=user.id,
            given_name=given_name,
            family_name=family_name,
            avatar_url=avatar_url,
            google_sub=google_sub
        )

    _bootstrap_user_after_login(user.id)

    auth.login_user(user)

    session.flash = T("Bienvenue dans l'application !") if created else T("Content de vous revoir.")
    redirect(session.pop('oauth_next', None) or URL('default', 'dashboard'))


# def login():
#     """Page de login Google. Redirige vers dashboard si déjà connecté."""
#     if auth.user:
#         redirect(URL('default', 'dashboard'))

#     next_url = request.vars._next or session.get('oauth_next') or URL('default', 'dashboard')
#     google_url = URL('default', 'google_begin', vars={'_next': next_url})

#     error_text = response.flash or session.flash or ''
#     initial_state = 'state-ideal'
#     if error_text:
#         initial_state = 'state-error'

#     return dict(
#         google_url=google_url,
#         initial_state=initial_state,
#         error_text=error_text,
#     )


# def logout():
#     """Déconnexion standard."""
#     if auth.user:
#         _log_account_event_safe(auth.user.id, 'logout')
#     return auth.logout(next=URL('default', 'login'))


# def google_redirect_uri():
#     """URL absolue exigée pour le callback OAuth."""
#     return URL('default', 'google_callback', scheme=True, host=True)


# def google_begin():
#     """Démarre le flux Google OAuth2/OpenID Connect."""
#     google_client_id = _get_config('google.client_id')

#     if not google_client_id:
#         _flash_login_error("Configuration OAuth Google incomplète.")

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
#     google_client_id = _get_config('google.client_id')
#     google_client_secret = _get_config('google.client_secret')

#     if not google_client_id or not google_client_secret:
#         _flash_login_error("Configuration OAuth Google incomplète.")

#     oauth_state = session.pop('oauth_state', None)
#     if not oauth_state or request.vars.get('state') != oauth_state:
#         _flash_login_error("Jeton de sécurité invalide.")

#     code = request.vars.get('code')
#     if not code:
#         _flash_login_error("Code d'autorisation manquant.")

#     data = dict(
#         client_id=google_client_id,
#         client_secret=google_client_secret,
#         code=code,
#         grant_type='authorization_code',
#         redirect_uri=google_redirect_uri(),
#     )

#     try:
#         req = Request('https://oauth2.googleapis.com/token', data=urlencode(data).encode('utf-8'))
#         req.add_header('Content-Type', 'application/x-www-form-urlencoded')
#         token_payload = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
#         access_token = token_payload.get('access_token')
#     except Exception as e:
#         logger.error('Échec échange token Google : %s', e)
#         _flash_login_error("Échec de la connexion aux serveurs Google.")

#     if not access_token:
#         _flash_login_error("Aucun jeton d'accès Google reçu.")

#     try:
#         req = Request('https://www.googleapis.com/oauth2/v3/userinfo')
#         req.add_header('Authorization', 'Bearer %s' % access_token)
#         google_data = json.loads(urlopen(req, timeout=15).read().decode('utf-8'))
#     except Exception as e:
#         logger.error('Échec lecture profil Google : %s', e)
#         _flash_login_error("Impossible de lire le profil Google.")

#     clean = lambda x: str(x).strip() if x else ''
#     google_sub = clean(google_data.get('sub'))
#     email_value = clean(google_data.get('email')).lower()
#     email_verified = bool(google_data.get('email_verified', False))
#     given_name = clean(google_data.get('given_name'))
#     family_name = clean(google_data.get('family_name'))
#     avatar_url = clean(google_data.get('picture'))
#     full_name = clean(google_data.get('name')) or ('%s %s' % (given_name, family_name)).strip()

#     if not google_sub or not email_value:
#         _flash_login_error("Les informations Google reçues sont incomplètes.")

#     if not email_verified:
#         _flash_login_error("Votre adresse email Google doit être vérifiée.")

#     identity_table = _google_identity_table()
#     if not identity_table:
#         _flash_login_error("La table de liaison Google n'existe pas encore dans la base.")

#     google_sub_field = _identity_field(identity_table, 'google_sub')
#     identity_user_id_field = _identity_field(identity_table, 'user_id')
#     identity_status_field = _identity_field(identity_table, 'status')

#     created = False
#     identity_record = db(identity_table[google_sub_field] == google_sub).select().first()

#     if identity_record:
#         user = db.auth_user(identity_record[identity_user_id_field])
#         if not user or _get_auth_user_status(user) != 'active':
#             _flash_login_error("Accès refusé ou compte inactif.")
#     else:
#         user = _get_auth_user_by_email(email_value)

#         if user and _get_auth_user_status(user) != 'active':
#             _flash_login_error("Accès refusé. Ce compte n'est pas actif.")

#         if not user:
#             user_id = db.auth_user.insert(**_make_auth_user_payload(
#                 email_value=email_value,
#                 given_name=given_name,
#                 family_name=family_name,
#                 full_name=full_name,
#                 avatar_url=avatar_url,
#             ))
#             user = db.auth_user[user_id]
#             created = True

#         identity_values = {
#             'user_id': user.id,
#             'provider': 'google',
#             'google_sub': google_sub,
#             'google_email': email_value,
#             'email_verified': email_verified,
#             'linked_at': request.now,
#             'last_login_at': request.now,
#             'status': 'linked',
#         }
#         _table_insert_safe(identity_table, identity_values)

#     _update_auth_user_profile(user, full_name, avatar_url)

#     if identity_record:
#         identity_updates = {
#             'google_email': email_value,
#             'email_verified': email_verified,
#             'last_login_at': request.now,
#         }
#         if identity_status_field:
#             identity_updates['status'] = 'linked'
#         _table_update_record_safe(identity_table, identity_record, identity_updates)

#     if 'user_profile' in db.tables:
#         profile = db(db.user_profile.user_id == user.id).select().first()
#         if not profile:
#             _table_insert_safe(db.user_profile, {
#                 'user_id': user.id,
#                 'preferred_language': 'fr',
#             })

#     _bootstrap_user_after_login(user.id)

#     auth.login_user(user)
#     _log_account_event_safe(user.id, 'login_google', {'email': email_value, 'created': created})

#     session.flash = "Bienvenue dans l'application !" if created else "Content de vous revoir."
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
