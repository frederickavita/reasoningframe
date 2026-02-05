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

# models/db.py

db.define_table('generated_reports',
    Field('user_id', 'reference auth_user', default=auth.user_id),
    Field('project_name', 'string', requires=IS_NOT_EMPTY()),
    Field('niche', 'string', requires=IS_NOT_EMPTY()),
    Field('concept', 'text'),
    Field('status', 'string', default='complete', requires=IS_IN_SET(['complete', 'draft', 'archived'])),
    Field('prompt_preview', 'text'), # The prompt to copy
    Field('json_data', 'json'), # Stores the full generated data
    Field('created_on', 'datetime', default=request.now),
)


"""
full_projects = [
        {'id': 101, 'created_on': datetime.datetime.now().strftime("%d %b %H:%M"), 'niche': 'Hôtes Airbnb', 'project_name': 'GuestBookAI', 'concept': 'Générateur auto de livrets d\'accueil PDF.', 'status': 'complete', 'prompt_preview': 'Agis comme un expert React...'},
        {'id': 102, 'created_on': 'Hier', 'niche': 'Gym Owners', 'project_name': 'FitStaffule', 'concept': 'Planification coachs.', 'status': 'complete', 'prompt_preview': 'Senior PM prompt...'},
        {'id': 103, 'created_on': '02 Fév', 'niche': 'Copywriters', 'project_name': 'WriteFlow', 'concept': 'Portail validation.', 'status': 'complete', 'prompt_preview': 'Copywriting platform...'},
        {'id': 104, 'created_on': '28 Jan', 'niche': 'Dentistes', 'project_name': 'SmileRecov', 'concept': 'Suivi SMS post-op.', 'status': 'archived', 'prompt_preview': 'SMS notification sys...'}
    ]

"""