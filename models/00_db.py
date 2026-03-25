# -*- coding: utf-8 -*-

# -------------------------------------------------------------------------
# AppConfig configuration made easy. Look inside private/appconfig.ini
# Auth is for authenticaiton and access control
# -------------------------------------------------------------------------
import urllib.request
import sys

import json
import hashlib

# On crée une classe vide qui ne fait rien
class MockURLopener:
    pass

# On force l'injection dans le module urllib pour tromper Web2py
if not hasattr(urllib.request, 'URLopener'):
    urllib.request.URLopener = MockURLopener
if not hasattr(urllib.request, 'FancyURLopener'):
    urllib.request.FancyURLopener = MockURLopener

from gluon.contrib.appconfig import AppConfig
from gluon.tools import Auth
import os
import re
import time 
import datetime
# pytz est standard pour les timezones, très recommandé de l'installer via pip
import pytz
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


ACCOUNT_STATUS_SET = ['active', 'suspended', 'deleted']
PRIMARY_PROFILE_SET = ['entrepreneur', 'manager', 'ops', 'support', 'sales', 'curious']
PRIMARY_GOAL_SET = ['understand_basics', 'build_agent', 'evaluate_roi', 'avoid_risks']
LOCALE_SET = ['fr', 'en']

# -------------------------------------------------------------------------
# 1. EXTENSION DE AUTH_USER (Identité, État, Préférences)
# -------------------------------------------------------------------------
auth.settings.extra_fields['auth_user'] = [
    # Identité / Auth externe
    Field('google_id', 'string', length=255, unique=True, readable=False, writable=False),
    Field('auth_provider', 'string', default='google', requires=IS_IN_SET(['google', 'local']), readable=False, writable=False),
    Field('avatar_url', 'string', length=512, default='', readable=False, writable=False),
    Field('display_name', 'string', length=255, default='', readable=False, writable=False),
    Field('xp_points', 'integer', default=0, readable=False, writable=False),
    Field('streak_days', 'integer', default=0, readable=False, writable=False),
    Field('subscription_tier', 'string', default='Free', 
          requires=IS_IN_SET(['Free', 'Premium'])),

    # Statut du compte
    Field('account_status', 'string', default='active', requires=IS_IN_SET(ACCOUNT_STATUS_SET), readable=False, writable=False),
    Field('suspension_reason', 'text', readable=False, writable=False),

    # Lien Billing (Technique)
    Field('stripe_customer_id', 'string', length=255, readable=False, writable=False),
    Field('credits', 'integer', default=5),

    # Onboarding & Préférences
    Field('onboarding_completed', 'boolean', default=False, readable=False, writable=False),
    Field('primary_profile', 'string', requires=IS_EMPTY_OR(IS_IN_SET(PRIMARY_PROFILE_SET)), readable=False, writable=False),
    Field('primary_goal', 'string', requires=IS_EMPTY_OR(IS_IN_SET(PRIMARY_GOAL_SET)), readable=False, writable=False),
    Field('timezone', 'string', requires=IS_EMPTY_OR(IS_IN_SET(pytz.common_timezones)), readable=False, writable=False),
    Field('locale', 'string', default='fr', requires=IS_IN_SET(LOCALE_SET), readable=False, writable=False),
    Field('company_name', 'string', length=255, default='', readable=False, writable=False),

    # Métadonnées manuelles (web2py gère déjà created_on/modified_on si signature=True, 
    # mais on les explicite ici comme demandé pour l'activité)
    Field('last_login_at', 'datetime', readable=False, writable=False),
    Field('last_active_at', 'datetime', readable=False, writable=False),
    Field('created_on', 'datetime', default=request.now, readable=False, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, readable=False, writable=False),
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
auth.settings.login_next = URL('default', 'dashboard')
auth.settings.register_next = URL('default', 'dashboard')
auth.settings.logout_next = URL('default', 'login')

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

# -*- coding: utf-8 -*-


# -------------------------------------------------------------------------
# 2. CORE BUSINESS & PRICING (La vérité business)
# -------------------------------------------------------------------------
