# -*- coding: utf-8 -*-
# models/01_ai_pickup_models.py


import os
import uuid
from datetime import datetime
from decimal import Decimal
import urllib.request
import pytz
import json
import base64
import logging

# Compatibilité Python 2/3 pour urllib
try:
    from urllib.request import Request, urlopen
    from urllib.parse import urlencode
except ImportError:
    from urllib2 import Request, urlopen
    from urllib import urlencode



from gluon.storage import Storage
from gluon.contrib.appconfig import AppConfig


# -------------------------------------------------------------------------
# Compat URLopener hack (kept from your template)
# -------------------------------------------------------------------------
class MockURLopener:
    pass


if not hasattr(urllib.request, 'URLopener'):
    urllib.request.URLopener = MockURLopener
if not hasattr(urllib.request, 'FancyURLopener'):
    urllib.request.FancyURLopener = MockURLopener

from gluon.tools import Auth
# -------------------------------------------------------------------------
# Configuration / DB / Auth bootstrap
# -------------------------------------------------------------------------
configuration = AppConfig(reload=True)

if 'db' not in globals():
    if 'GAE_APPLICATION' not in os.environ:
        db = DAL(
            configuration.get('db.uri'),
            pool_size=configuration.get('db.pool_size'),
            migrate_enabled=configuration.get('db.migrate'),
            check_reserved=['common'],
        )
    else:
        db = DAL('firestore')
        session.connect(request, response, db=db)

response.generic_patterns = []
if request.is_local and not configuration.get('app.production'):
    response.generic_patterns.append('*')

response.formstyle = 'bootstrap4_inline'
response.form_label_separator = ''


auth = Auth(db, host_names=configuration.get('host.names'))
auth.settings.login_url = URL('default', 'login')
auth.settings.on_failed_authorization = URL('default', 'login')



# =============================================================================
# CONSTANTES ET ÉNUMÉRATIONS (Stabilité du vocabulaire)
# =============================================================================



# Google-first V1 : on coupe les flows locaux inutiles
auth.settings.actions_disabled = [
    'register',
    'change_password',
    'request_reset_password',
    'retrieve_password',
    'reset_password',
    'retrieve_username',
]
# --- CONFIGURATION DE LA DÉCONNEXION (US 17) ---
# Dans un modèle (par exemple models/db.py)
auth.settings.on_failed_authorization = URL('default', 'not_authorized')

# --- CONFIGURATION DE LA DÉCONNEXION (US 17) ---

auth.settings.logout_next = URL('default', 'index')

# 2. Message flash personnalisé (traduit en français)
auth.messages.logged_out = T('Vous êtes déconnecté. À bientôt !')


ACCOUNT_STATUS = ('pending', 'active', 'blocked', 'refunded', 'revoked')
LOCATOR_TYPES = ('role', 'label', 'text', 'testid', 'css')
LOCATOR_QUALITY = ('recommended', 'good', 'acceptable', 'fragile')
PAGE_STATUS = ('empty', 'partial', 'ready', 'error', 'archived')
SCENARIO_STATUS = (
    'empty', 'draft', 'blocked', 'incomplete', 'ready',
    'running', 'passed', 'failed', 'cancelled', 'archived'
)
RUN_STATUS = ('idle', 'precheck', 'compiling', 'executing', 'passed', 'failed', 'cancelled', 'blocked')
TRACE_MODE = ('off', 'on', 'retain-on-failure', 'on-first-retry')
BROWSERS = ('chromium', 'firefox', 'webkit')
PAYMENT_PROVIDER = ('paypal',)
PAYMENT_STATUS = ('created', 'approved', 'captured', 'failed', 'refunded', 'revoked')
ENTITLEMENT_CODE = ('lifetime_access',)
ENTITLEMENT_STATUS = ('active', 'revoked', 'refunded')
FEEDBACK_CATEGORY = ('suggestion', 'question', 'complaint', 'bug', 'billing', 'feature_request', 'other')
FEEDBACK_STATUS = ('new', 'in_review', 'answered', 'closed')
ARTIFACT_TYPE = ('trace', 'screenshot', 'video', 'stdout', 'stderr', 'report', 'other')




# -------------------------------------------------------------------------
# auth_user extra fields (MUST be before auth.define_tables)
# -------------------------------------------------------------------------
# Pas de username local



auth.settings.extra_fields['auth_user'] = [
    Field('uuid', length=64, default=lambda: uuid.uuid4().hex, unique=True,
          writable=False, readable=False),
    Field('account_status', default='active',
          requires=IS_IN_SET(ACCOUNT_STATUS, zero=None)),
    Field('auth_provider', default='google',
          writable=False, readable=False),
    Field('google_sub', length=255, unique=True, writable=False, readable=False),
    Field('google_picture_url', 'string', length=512, writable=False, readable=False),
    Field('email_verified', 'boolean', default=False, writable=False, readable=False),
    Field('last_login_at', 'datetime', writable=False, readable=False),
]



auth.define_tables(username=False, signature=False)
# Champs qu'on ne veut pas exposer
db.auth_user.password.readable = False
db.auth_user.password.writable = False
db.auth_user.registration_key.readable = False
db.auth_user.registration_key.writable = False
db.auth_user.reset_password_key.readable = False
db.auth_user.reset_password_key.writable = False
db.auth_user.registration_id.readable = False
db.auth_user.registration_id.writable = False

db.auth_user.first_name.requires = IS_NOT_EMPTY()
db.auth_user.last_name.requires = IS_NOT_EMPTY()
db.auth_user.email.requires = [IS_EMAIL(), IS_NOT_IN_DB(db, 'auth_user.email')]


def auth_signature_fields():
    """
    Version légère de auth.signature pour garder la main sur les refs / defaults.
    """
    return [
        Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
        Field('created_by', 'reference auth_user',
              default=(auth.user_id if auth.user else None),
              writable=False, readable=False),
        Field('modified_on', 'datetime', default=request.now, update=request.now,
              writable=False, readable=False),
        Field('modified_by', 'reference auth_user',
              default=(auth.user_id if auth.user else None),
              update=(auth.user_id if auth.user else None),
              writable=False, readable=False),
    ]


def json_text_field(name, default='{}'):
    return Field(name, 'text', default=default)



# 2. Modèle GoogleIdentity (Table liée)
db.define_table(
    'google_identity',
    Field('user_id', 'reference auth_user', ondelete='CASCADE'),
    Field('provider', 'string', length=50, default='google'),
    Field('google_sub', 'string', length=255, unique=True, notnull=True),
    Field('email_verified', 'boolean', default=False),
    Field('linked_at', 'datetime', default=request.now, writable=False),
    auth.signature
)
# Empêche la création automatique de groupes "user_xxx"
auth.settings.create_user_groups = None

# Messages utiles si jamais certaines routes auth natives sont atteintes
auth.messages.access_denied = T('Access denied')
auth.messages.logged_in = T('Signed in successfully')
auth.messages.logged_out = T('Signed out successfully')
auth.messages.invalid_login = T('Unable to sign you in')



# -------------------------------------------------------------------------
# Mail / auth policy
# -------------------------------------------------------------------------
mail = auth.settings.mailer
mail.settings.server = 'logging' if request.is_local else configuration.get('smtp.server')
mail.settings.sender = configuration.get('smtp.sender')
mail.settings.login = configuration.get('smtp.login')
mail.settings.tls = configuration.get('smtp.tls') or False
mail.settings.ssl = configuration.get('smtp.ssl') or False

auth.settings.registration_requires_verification = False
auth.settings.registration_requires_approval = False
auth.settings.reset_password_requires_verification = True
auth.settings.login_next = URL('default', 'dashboard')
auth.settings.register_next = URL('default', 'dashboard')
auth.settings.logout_next = URL('default', 'login')

response.meta.author = configuration.get('app.author')
response.meta.description = configuration.get('app.description')
response.meta.keywords = configuration.get('app.keywords')
response.meta.generator = configuration.get('app.generator')
response.show_toolbar = configuration.get('app.toolbar')
response.google_analytics_id = configuration.get('google.analytics_id')

if configuration.get('scheduler.enabled'):
    from gluon.scheduler import Scheduler
    scheduler = Scheduler(db, heartbeat=configuration.get('scheduler.heartbeat'))


# -------------------------------------------------------------------------
# AI Pickup Score tables
# -------------------------------------------------------------------------
