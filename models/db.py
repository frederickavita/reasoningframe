# -*- coding: utf-8 -*-

# -------------------------------------------------------------------------
# AppConfig configuration made easy. Look inside private/appconfig.ini
# Auth is for authenticaiton and access control
# -------------------------------------------------------------------------
from gluon.contrib.appconfig import AppConfig
from gluon.tools import Auth
import os
import re
import time 
REQUIRED_WEB2PY_VERSION = "2.0.10"

# -------------------------------------------------------------------------
# This scaffolding model makes your app work on Google App Engine too
# File is released under public domain and you can use without limitations
# -------------------------------------------------------------------------

web2py_version_string = request.global_settings.web2py_version.split("-")[0]
web2py_version = list(map(int, web2py_version_string.split(".")[:3]))
if web2py_version < list(map(int, REQUIRED_WEB2PY_VERSION.split(".")[:3])):
    raise HTTP(500, f"Requires web2py version {REQUIRED_WEB2PY_VERSION} or newer, not {web2py_version_string}")

# -------------------------------------------------------------------------
# if SSL/HTTPS is properly configured and you want all HTTP requests to
# be redirected to HTTPS, uncomment the line below:
# -------------------------------------------------------------------------
# request.requires_https()

# -------------------------------------------------------------------------
# once in production, remove reload=True to gain full speed
# -------------------------------------------------------------------------
configuration = AppConfig(reload=True)

if "GAE_APPLICATION" not in os.environ:
    # ---------------------------------------------------------------------
    # if NOT running on Google App Engine use SQLite or other DB
    # ---------------------------------------------------------------------
    db = DAL(configuration.get("db.uri"),
             pool_size=configuration.get("db.pool_size"),
             migrate_enabled=configuration.get("db.migrate"),
             check_reserved=["common"])
else:
    # ---------------------------------------------------------------------
    # connect to Google Firestore
    # ---------------------------------------------------------------------
    db = DAL("firestore")
    # ---------------------------------------------------------------------
    # store sessions and tickets there
    # ---------------------------------------------------------------------
    session.connect(request, response, db=db)
    # ---------------------------------------------------------------------
    # or store session in Memcache, Redis, etc.
    # from gluon.contrib.memdb import MEMDB
    # from google.appengine.api.memcache import Client
    # session.connect(request, response, db = MEMDB(Client()))
    # ---------------------------------------------------------------------

# -------------------------------------------------------------------------
# by default give a view/generic.extension to all actions from localhost
# none otherwise. a pattern can be "controller/function.extension"
# -------------------------------------------------------------------------
response.generic_patterns = [] 
if request.is_local and not configuration.get("app.production"):
    response.generic_patterns.append("*")

# -------------------------------------------------------------------------
# choose a style for forms
# -------------------------------------------------------------------------
response.formstyle = "bootstrap4_inline"
response.form_label_separator = ""

# -------------------------------------------------------------------------
# (optional) optimize handling of static files
# -------------------------------------------------------------------------
# response.optimize_css = "concat,minify,inline"
# response.optimize_js = "concat,minify,inline"

# -------------------------------------------------------------------------
# (optional) static assets folder versioning
# -------------------------------------------------------------------------
# response.static_version = "0.0.0"

# -------------------------------------------------------------------------
# Here is sample code if you need for
# - email capabilities
# - authentication (registration, login, logout, ... )
# - authorization (role based authorization)
# - services (xml, csv, json, xmlrpc, jsonrpc, amf, rss)
# - old style crud actions
# (more options discussed in gluon/tools.py)
# -------------------------------------------------------------------------

# host names must be a list of allowed host names (glob syntax allowed)
auth = Auth(db, host_names=configuration.get("host.names"))

# -------------------------------------------------------------------------
# create all tables needed by auth, maybe add a list of extra fields
# -------------------------------------------------------------------------
auth.settings.extra_fields['auth_user'] = [
    # 1. LE NERF DE LA GUERRE : Les Crédits
    Field('credits', 'integer', default=1, 
          label='Solde Crédits',
          readable=True, writable=False), # L'utilisateur ne peut pas modifier son solde lui-même

    # 2. IDENTIFICATION MOLLIE (Remplacement de Stripe)
    # Permet de lier les transactions Mollie à cet utilisateur
    # Format habituel Mollie : 'cst_xxxxxxxx'
    Field('mollie_customer_id', 'string', length=255,
          writable=False, readable=False, label='Mollie Customer ID'),

    # 3. UI / UX : Avatar Google
    Field('avatar_url', 'string', length=512, 
          default='', label='Photo URL'),

    # 4. STATUT DU COMPTE
    Field('account_status', 'string', default='standard',
          requires=IS_IN_SET(['standard', 'founder', 'agency'])),
          
    # 5. CONTEXTE
    Field('company_name', 'string', label='Entreprise')
]
auth.define_tables(username=False, signature=False)

# -------------------------------------------------------------------------
# configure email
# -------------------------------------------------------------------------
mail = auth.settings.mailer
mail.settings.server = "logging" if request.is_local else configuration.get("smtp.server")
mail.settings.sender = configuration.get("smtp.sender")
mail.settings.login = configuration.get("smtp.login")
mail.settings.tls = configuration.get("smtp.tls") or False
mail.settings.ssl = configuration.get("smtp.ssl") or False

# -------------------------------------------------------------------------
# configure auth policy
# -------------------------------------------------------------------------
auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True

# -------------------------------------------------------------------------  
# read more at http://dev.w3.org/html5/markup/meta.name.html               
# -------------------------------------------------------------------------
response.meta.author = configuration.get("app.author")
response.meta.description = configuration.get("app.description")
response.meta.keywords = configuration.get("app.keywords")
response.meta.generator = configuration.get("app.generator")
response.show_toolbar = configuration.get("app.toolbar")

# -------------------------------------------------------------------------
# your http://google.com/analytics id                                      
# -------------------------------------------------------------------------
response.google_analytics_id = configuration.get("google.analytics_id")

# -------------------------------------------------------------------------
# maybe use the scheduler
# -------------------------------------------------------------------------
if configuration.get("scheduler.enabled"):
    from gluon.scheduler import Scheduler
    scheduler = Scheduler(db, heartbeat=configuration.get("scheduler.heartbeat"))

# -------------------------------------------------------------------------
# Define your tables below (or better in another model file) for example
#
# >>> db.define_table("mytable", Field("myfield", "string"))
#
# Fields can be "string","text","password","integer","double","boolean"
#       "date","time","datetime","blob","upload", "reference TABLENAME"
# There is an implicit "id integer autoincrement" field
# Consult manual for more options, validators, etc.
#
# More API examples for controllers:
#
# >>> db.mytable.insert(myfield="value")
# >>> rows = db(db.mytable.myfield == "value").select(db.mytable.ALL)
# >>> for row in rows: print row.id, row.myfield
# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# after defining tables, uncomment below to enable auditing
# -------------------------------------------------------------------------
# auth.enable_record_versioning(db)

import datetime

# --- 1. CONFIGURATION AGENCE (SINGLETON) ---
# C'est ici que David configure son "White Label" et ses clés API.
db.define_table('settings',
    Field('agency_name', 'string', default='AdGuard Agency', label='Nom de votre Agence'),
    Field('agency_logo', 'upload', label='Votre Logo (White Label)'),
    Field('alert_email', 'string', requires=IS_EMAIL(), label='Email pour les Alertes'),
    
    # Clés API Google Ads (Critiques pour le moteur)
    Field('developer_token', 'string', comment="Token développeur Google Ads"),
    Field('client_id', 'string', comment="OAuth2 Client ID"),
    Field('client_secret', 'password', comment="OAuth2 Client Secret (Masqué)"),
    Field('refresh_token', 'string', comment="Token de rafraîchissement longue durée"),
    
    # Méta-données
    format='%(agency_name)s'
)

# Sécurité : On force la création d'une ligne de config vide si elle n'existe pas
if db(db.settings).count() == 0:
    db.settings.insert(agency_name="Ma Super Agence", alert_email="admin@example.com")


# --- 2. CLIENTS & COMPTES SURVEILLÉS ---
# Le cœur du Dashboard. 
db.define_table('clients',
    Field('client_name', 'string', requires=IS_NOT_EMPTY(), label='Nom du Client (Interne)'),
    
    # Validation stricte du format ID Google (xxx-xxx-xxxx) pour éviter les erreurs de saisie
    Field('google_customer_id', 'string', 
          requires=IS_MATCH(r'^\d{3}-\d{3}-\d{4}$', error_message='Format requis: 123-456-7890'),
          label='ID Google Ads'),
          
    # Le budget plafond. Decimal pour la précision financière.
    Field('monthly_budget', 'decimal(10,2)', requires=IS_DECIMAL_IN_RANGE(0, 10000000), label='Budget Mensuel (€)'),
    
    # LE KILL SWITCH (ON par défaut pour la sécurité)
    Field('kill_switch_active', 'boolean', default=True, label="Activer l'Arrêt d'Urgence (Kill Switch)"),
    
    # --- Champs mis à jour AUTOMATIQUEMENT par le Script (Lecture seule pour l'humain) ---
    Field('current_spend', 'decimal(10,2)', default=0, writable=False, readable=False),
    Field('spend_percent', 'integer', default=0, writable=False, readable=False),
    
    # Statut visuel pour le Dashboard (Vert / Orange / Rouge / Gris)
    Field('status', 'string', default='OK', 
          requires=IS_IN_SET(['OK', 'WARNING', 'CRITICAL', 'ERROR']), 
          writable=False),
          
    Field('last_check', 'datetime', writable=False),
    
    format='%(client_name)s'
)


# --- 3. JOURNAL D'ACTIVITÉ (LOGS & AUDIT) ---
# La "Boîte Noire". Indispensable pour prouver au client pourquoi on a coupé.
db.define_table('logs',
    Field('event_time', 'datetime', default=request.now, label='Date/Heure'),
    
    # Lien vers le client (si le client est supprimé, on garde le log -> on_delete='SET NULL')
    Field('client_id', 'reference clients', on_delete='SET NULL'),
    
    # Type d'événement pour le filtrage
    Field('event_type', 'string', requires=IS_IN_SET(['INFO', 'WARNING', 'CRITICAL', 'ERROR'])),
    
    # Le message technique (Ex: "Budget: 5000 / Dépense: 5024.10")
    Field('message', 'text'),
    
    # Snapshot des données au moment du log (Preuve immuable)
    Field('snapshot_spend', 'decimal(10,2)'),
    Field('snapshot_budget', 'decimal(10,2)')
)

# Les logs sont en lecture seule (Personne ne doit pouvoir effacer ses traces)
db.logs.event_time.writable = False
db.logs.client_id.writable = False
db.logs.event_type.writable = False
db.logs.message.writable = False



def detach_logs_before_delete(s):
    try:
        print("detach_logs_before_delete")
        print("delete set:", s)         # ex: <Set ("clients"."id" > 0)>
        print("query:", s.query)        # utile

        ids_subquery = s._select(db.clients.id)  # nested select
        q = db.logs.client_id.belongs(ids_subquery)

        matched = db(q).count()
        updated = db(q).update(client_id=None)
        remaining = db(q).count()  # après update, devrait être 0

        print("logs matched:", matched)
        print("logs updated:", updated)
        print("logs remaining linked:", remaining)

        return False
    except Exception:
        import traceback
        traceback.print_exc()
        raise



# Attacher une seule fois
if detach_logs_before_delete not in db.clients._before_delete:
    db.clients._before_delete.append(detach_logs_before_delete)


# -------------------------------------------------------------------------
# FIN DU MODÈLE
# -