# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------
# This is a sample controller
# this file is released under public domain and you can use without limitations
# -------------------------------------------------------------------------

# ---- example index page ----
import json, time, uuid, random, hashlib, io
import requests 



GOOGLE_AUTH_URL      = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL     = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL  = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_SCOPE         = 'openid email profile'


# -------------------------------------------------------------------------
# ROUTE 1 : Récupérer les données de la leçon et l'état de l'utilisateur
# -------------------------------------------------------------------------
# --- CONFIGURATION GLOBALE ---


def index():
    """
    Landing page
    """
    return dict()


def logout():
    return auth.logout(next=URL('default', 'index'))



def dashboard():
    if not auth.user:
        redirect(URL('default', 'login'))
    return dict()


def profile():
    if not auth.user:
        redirect(URL('default', 'login'))
        
    # 1. Compter les cours
    course_count = db(db.course.user_id == auth.user_id).count()
    
    # 2. Récupérer les crédits
    user_row = db(db.auth_user.id == auth.user_id).select(db.auth_user.credits).first()
    credits_restants = user_row.credits if user_row else 0 
    
    # 3. NOUVEAU : Récupérer l'historique des paiements (du plus récent au plus ancien)
    transactions = db(db.user_transaction.user_id == auth.user_id).select(
        orderby=~db.user_transaction.created_on
    )
    
    return dict(
        user_courses_count=course_count,
        user_credits=credits_restants,
        transactions=transactions # On passe l'historique à la vue
    )



@auth.requires_login()
def download_invoice():
    """Génère et télécharge la facture en format texte"""
    trans_id = request.vars.id
    if not trans_id:
        redirect(URL('default', 'profile'))
        
    # --- ZERO TRUST ---
    # On vérifie que la transaction existe ET qu'elle appartient bien à l'utilisateur connecté
    trans = db((db.user_transaction.id == trans_id) & (db.user_transaction.user_id == auth.user_id)).select().first()
    
    if not trans:
        session.flash = "Facture introuvable ou accès refusé."
        redirect(URL('default', 'profile'))
        
    # Formatage des dates et numéro de facture
    date_str = trans.created_on.strftime('%d %B %Y')
    # On crée un numéro de facture unique (ex: INV-2026-0001)
    invoice_num = f"INV-{trans.created_on.strftime('%Y')}-{trans.id:04d}"
    
    # Tentative d'extraction de l'adresse si elle est stockée en JSON depuis PayPal
    address_line = ""
    country = ""
    try:
        addr_data = json.loads(trans.payer_address)
        address_line = addr_data.get('address_line_1', '')
        country = addr_data.get('country_code', '')
    except:
        address_line = "Adresse non fournie via PayPal"

    # Le modèle de facture 2k services
    invoice_text = f"""================== INVOICE ==================
Tax date:       {date_str}
Invoice number: {invoice_num}

This message is for your records. Thank you for your purchase!

Invoice from:
2k services
8 RUE CHARLES GIDE
77130 VARENNES SUR SEINE
France
SIRET: 47831009700025
SIREN: 478310097
N° de compte auto-entrepreneur: 117000001558790893 (Profession Libérale Non Réglementée)

Invoice to:
{trans.payer_name or auth.user.first_name + ' ' + auth.user.last_name}
{trans.payer_email or auth.user.email}
{address_line}
{country}

Invoice for: reasoningframe AI Credits (Pack)
Order ID: {trans.order_id}

Total price: US${trans.amount:.2f}

(TVA non applicable, art. 293 B du CGI)

Thanks for using our site!

The 2k services team
--
reasoningframe: Develop your AI skills
A product from 2k services
"""

    # --- LA MAGIE DU TÉLÉCHARGEMENT ---
    # Ces deux lignes disent au navigateur : "Ceci n'est pas une page web, c'est un fichier texte à télécharger"
    response.headers['Content-Type'] = 'text/plain'
    response.headers['Content-Disposition'] = f'attachment; filename="Invoice_{invoice_num}.txt"'
    
    return invoice_text



def get_courses():
    """Endpoint API sécurisé pour Brython"""
    
    # 1. Vérification d'authentification (Gatekeeper)
    if not auth.user:
        # On renvoie un code 401 pour que Brython déclenche l'état Error ou Redirect
        return response.json({"error": "Unauthorized"}, status=401)
    
    # 2. Isolation des données
    # On force le filtre sur l'ID de la session serveur (auth.user_id)
    # Impossible pour un utilisateur A de voir les cours de l'utilisateur B
    courses = db(db.course.user_id == auth.user_id).select(
        db.course.id,
        db.course.title,
        db.course.language,
        db.course.created_on,
        orderby=~db.course.created_on
    )
    
    # 3. Formatage pour le Dashboard (Data Transformation)
    formatted = []
    for c in courses:
        # Sécurité supplémentaire : double vérification (optionnel mais recommandé)
        if c.user_id == auth.user_id:
            formatted.append({
                "id": c.id,
                "title": c.title,
                "date": c.created_on.strftime("%b %d, %Y") if c.created_on else "N/A",
                "language": c.language
            })
        
    return response.json(formatted)





def get_credits():
    """Récupère les crédits de l'utilisateur"""
    return response.json({"credits": 5})



def login():
    # 1. État Partiel (Utilisateur déjà connecté) -> Redirection directe
    if auth.user:
        # Si on veut forcer l'état partiel visuel (comme dans ton cahier des charges) :
        # return dict(initial_state='state-partiel')
        
        # Mais comme tu l'as sagement suggéré : Redirection directe (meilleure UX)
        redirect(URL('default', 'dashboard'))  # ou 'new' selon ta structure
    next_url = request.vars._next or session.get('oauth_next') or URL('default', 'dashboard')
    google_url = URL('default', 'google_begin', vars={'_next': next_url}) 
    return dict(google_url=google_url,initial_state='state-ideal', error_text='' )


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
  # 1. Helper simple pour nettoyer les chaînes (remplace _safe_strip)
    clean = lambda x: str(x).strip() if x else ""

    # 2. Extraction et nettoyage des données Google
    # 'data' est le dictionnaire JSON renvoyé par l'API UserInfo de Google
    google_sub = clean(data.get('sub'))
    email_value = clean(data.get('email')).lower()
    given_name = clean(data.get('given_name'))
    family_name = clean(data.get('family_name'))
    avatar_url = clean(data.get('picture'))

    # 3. Gestion de la locale (on s'assure qu'elle matche ton LOCALE_SET : fr, en, es)
    raw_locale = clean(data.get('locale')).lower()[:2]
    locale_value = raw_locale if raw_locale in ('fr', 'en', 'es') else 'en'

    # 4. Construction du nom d'affichage
    display_name = clean(data.get('name')) or f"{given_name} {family_name}".strip()

    # 5. Préparation du profil pour Web2py
    profile = dict(
        first_name=given_name,
        last_name=family_name,
        email=email_value,
        google_id=google_sub,
        auth_provider='google',
        avatar_url=avatar_url,
        display_name=display_name,
        locale=locale_value,
        last_login_at=request.now
    )

    # 6. Création ou récupération de l'utilisateur
    # Note : Web2py utilise l'email comme clé unique par défaut
    user = auth.get_or_create_user(profile)

    if not user:
        session.flash = T('Unable to create or log in user.')
        return redirect(URL(c='default', f='login'))

    # 7. Synchronisation des données (Update)
    # On met à jour les infos à chaque connexion pour garder l'avatar et le nom frais
    db(db.auth_user.id == user.id).update(
        google_id=google_sub,
        auth_provider='google',
        first_name=given_name,
        last_name=family_name,
        avatar_url=avatar_url,
        display_name=display_name,
        last_login_at=request.now,
        last_active_at=request.now,
        updated_on=request.now
    )

    # 8. Connexion de la session
    auth.login_user(user)

    # Redirection vers la page de saisie principale
    redirect(URL(c='default', f='dashboard'))  # ou 'new' selon ta structure
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
