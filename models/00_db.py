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

# 1ion']
VALIDATION_ISSUE_SEVERITIES = ['low', 'medium', 'high']
CONTENT_UPDATE_TRIGGERS = ['feature_change', 'ui_change', 'quality_fix', 'outdated_example', 'manual_review']
auth.settings.logout_next = URL('default', 'index')

# 2. Message flash personnalisé (traduit en français)
auth.messages.logged_out = T('Vous êtes déconnecté. À bientôt !')





def _slug_field(table_name):
    return Field(
        'slug',
        length=255,
        unique=True,
        requires=[IS_NOT_EMPTY(), IS_NOT_IN_DB(db, '%s.slug' % table_name)],
    )


def _status_field(name, values, default):
    return Field(name, default=default, requires=IS_IN_SET(values, zero=None))

# -------------------------------------------------------------------------
# auth_user extra fields (MUST be before auth.define_tables)
# -------------------------------------------------------------------------
# Pas de username local





auth.settings.extra_fields['auth_user'] = [

    Field(
    'ui_language',
    'string',
    length=8,
    default='fr',
    requires=IS_IN_SET(['fr', 'en', 'es'])
),
Field(
    'learning_language',
    'string',
    length=8,
    default='fr',
    requires=IS_IN_SET(['fr', 'en', 'es'])
),
    Field(
        'auth_provider',
        default='google',
        writable=False,
        readable=False
    ),
    Field(
        'avatar_url',
        'string',
        length=512,
        default='',
        writable=False,
        readable=False
    ),
    Field(
        'onboarding_completed',
        'boolean',
        default=False
    ),
    Field(
        'onboarding_step',
        'integer',
        default=0
    ),
    Field(
        'learning_goal',
        'string',
        length=64,
        default='',
        requires=IS_IN_SET(
            [
                'productivity',
                'writing',
                'research',
                'marketing',
                'solopreneur',
                'education'
            ],
            zero=''
        )
    ),
    Field(
        'primary_track',
        'string',
        length=64,
        default='',
        requires=IS_IN_SET(
            [
                'solopreneur',
                'consultant',
                'marketing',
                'student',
                'teacher',
                'office_productivity'
            ],
            zero=''
        )
    ),
    Field(
        'timezone',
        'string',
        length=64,
        default='Europe/Paris'
    ),
    Field(
        'last_seen_at',
        'datetime',
        writable=False,
        readable=False
    )
]
auth.define_tables(username=False, signature=False)



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
# 1. Profil utilisateur
db.define_table(
    'user_profile',
    Field('user_id', 'reference auth_user', required=True, unique=True, ondelete='CASCADE'),
    Field('role_label', 'string', length=100),
    Field('experience_level', 'string', length=50),
    Field('preferred_language', 'string', length=10, default='fr',
          requires=IS_IN_SET(['fr', 'en', 'es', 'de', 'it'])),
    Field('goals_summary', 'text'),
    auth.signature
)



db.define_table(
'user_feedback',
Field('user_id', 'reference auth_user', required=True),
Field('category', 'string', default='suggestion', required=True,
        requires=IS_IN_SET(['suggestion', 'improvement', 'critique', 'bug'])),
Field('subject', 'string', length=200),
Field('message', 'text', required=True),
Field('status', 'string', default='new', required=True,
        requires=IS_IN_SET(['new', 'reviewed', 'archived'])),
Field('created_at', 'datetime', default=request.now),
migrate=True,
)
