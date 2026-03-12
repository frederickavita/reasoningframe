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

# -------------------------------------------------------------------------
# create all tables needed by auth, maybe add a list of extra fields
# -------------------------------------------------------------------------
# --- EXTENSION DE LA TABLE AUTH_USER (Mise à jour Trial) ---
# --- EXTENSION DE LA TABLE AUTH_USER ---
import datetime

auth.settings.extra_fields['auth_user'] = [
    
   # -------------------------------------------------------------------------
    # 1. IDENTIFICATION EXTERNE (SSO & Agnostique Provider)
    # -------------------------------------------------------------------------
    Field('google_id', 'string', length=255, label='Google ID'), 
    
    # Pivot PayPal -> Stripe anticipé !
    Field('billing_provider', 'string', 
          requires=IS_IN_SET(['paypal', 'stripe', 'none']), default='none'),
    Field('billing_customer_id', 'string', length=255, writable=False, readable=False),
    
    # -------------------------------------------------------------------------
    # 2. BUSINESS MODEL & DROITS
    # -------------------------------------------------------------------------
    Field('account_status', 'string', default='active', 
          requires=IS_IN_SET(['active', 'suspended', 'banned']), 
          label='Statut du compte'),
    
    # Le champ compagnon pour le support client
    Field('suspension_reason', 'string', label='Raison de la suspension (ex: chargeback paypal)'),
          
    # Règle stricte : Compte le nombre de user_workflow où desired_state == 'ON'
    Field('max_active_workflows', 'integer', default=10, label='Quota de workflows actifs'),

    # -------------------------------------------------------------------------
    # 3. CONFIGURATION MOTEUR & ONBOARDING
    # -------------------------------------------------------------------------
    # Marqueur produit très utile pour la PWA
    Field('onboarding_completed', 'boolean', default=False),
    
    # Pas de valeur par défaut ! Oblige l'UI à demander ou détecter le fuseau.
    Field('timezone', 'string', 
          requires=IS_IN_SET(pytz.common_timezones), 
          label='Fuseau Horaire (IANA)'),
          
    Field('locale', 'string', default='fr', 
          requires=IS_IN_SET(['fr', 'en', 'es']), 
          label='Langue UI'),

    # -------------------------------------------------------------------------
    # 4. UI / UX & AUDIT
    # -------------------------------------------------------------------------
    Field('company_name', 'string', label='Nom Entreprise/Agence'),
    Field('avatar_url', 'string', length=512, default='', label='Avatar URL (Temporaire)'),
    
    # web2py Auth ne crée pas created_on/updated_on par défaut sur auth_user,
    # c'est donc une excellente pratique de les rajouter.
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False),
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
# applications/n8n_life/models/01_schema.py


# =========================================================================
# 1. CATALOGUE COMMERCIAL (Les "Recettes")
# =========================================================================

"""
TABLE : workflow_template
-------------------------
* UTILITÉ : C'est le catalogue de la boutique. Cette table stocke la version "Master" 
  (le modèle original) d'un workflow généré par l'IA ou créé par un expert.
* POURQUOI SA CRÉATION : Pour séparer le "Produit vendu" de "l'Instance utilisée". 
  Si on ne faisait pas ça, une modification du template original casserait les workflows 
  de tous les clients l'ayant déjà acheté. Cela permet aussi le versioning et la gestion des prix.
"""
db.define_table('workflow_template',
    Field('name', 'string', requires=IS_NOT_EMPTY()),
    Field('description', 'text'),
    Field('version', 'integer', default=1, label="Version du template"),
    Field('provider_price_id', 'string', label="ID Prix (ex: Stripe Price ID)"), 
    Field('price_cents', 'integer', default=0),
    Field('workflow_json', 'json', label="Graphe DAG Canonique"),
    Field('required_credentials', 'list:string', label="Cache métier des secrets requis"), 
    Field('is_published', 'boolean', default=False),
    
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False),
    format='%(name)s (v%(version)s)'
)

# =========================================================================
# 2. ESPACE UTILISATEUR (Instances et Secrets)
# =========================================================================

"""
TABLE : user_workflow
---------------------
* UTILITÉ : C'est l'instance vivante et personnelle du workflow pour un client donné. 
  C'est le clone d'un template (ou une création de zéro) qui lui appartient.
* POURQUOI SA CRÉATION : Chaque utilisateur doit pouvoir activer/désactiver son flux, 
  le modifier, et surtout y injecter ses propres données sans impacter les autres. 
  C'est ici qu'on gère l'état d'exécution réel (runtime_status) versus l'intention (desired_state).
"""
db.define_table('user_workflow',
    Field('user_id', 'reference auth_user'),
    Field('template_id', 'reference workflow_template'), # Peut être None si création manuelle (Optionnel V2)
    Field('template_version_at_clone', 'integer'),
    Field('name', 'string', requires=IS_NOT_EMPTY()),
    
    Field('desired_state', 'string', requires=IS_IN_SET(['ON', 'OFF']), default='OFF', label="Intention Utilisateur"),
    Field('runtime_status', 'string', requires=IS_IN_SET(['waiting_credentials', 'ready', 'active', 'error', 'archived']), default='waiting_credentials'),
    
    Field('workflow_json', 'json'),
    Field('is_legitimately_acquired', 'boolean', default=False),
    
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False),
    Field('deleted_on', 'datetime', readable=False), 
    format='%(name)s'
)

"""
TABLE : user_credential
-----------------------
* UTILITÉ : C'est le coffre-fort (Vault) de l'utilisateur. Il stocke les mots de passe, 
  clés API et tokens OAuth de manière chiffrée.
* POURQUOI SA CRÉATION : Règle de sécurité absolue. On ne stocke JAMAIS de secrets en clair 
  dans le `workflow_json`. Les secrets sont isolés ici pour être déchiffrés "Just-in-Time" 
  pendant le run, puis détruits de la mémoire.
"""
db.define_table('user_credential',
    Field('user_id', 'reference auth_user'),
    Field('service_name', 'string', requires=IS_NOT_EMPTY()), # ex: 'slack_api'
    Field('encrypted_data', 'text'),
    
    Field('crypto_algo', 'string', default='AES-256-CBC-HMAC'),
    Field('crypto_version', 'integer', default=1),
    Field('is_valid', 'boolean', default=False),
    Field('last_checked_on', 'datetime'),
    
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False)
)
# Règle architecturale : L'unicité composite (user_id, service_name) sera garantie
# au niveau de la couche Service (CredentialService) lors de l'insertion/mise à jour.

# =========================================================================
# 3. ROUTAGE EXTERNE (Ingestion des Triggers)
# =========================================================================

"""
TABLE : webhook_endpoint
------------------------
* UTILITÉ : C'est le standardiste. Il mappe une URL publique (ex: /api/webhook/123-abc) 
  vers un Workflow et un Nœud précis.
* POURQUOI SA CRÉATION : Optimisation des performances et de la sécurité (O(1) lookup). 
  Quand un événement HTTP arrive, au lieu d'ouvrir et de parser des milliers de JSON en base 
  pour trouver qui écoute, on interroge cette petite table ultra-rapide. Elle gère aussi la 
  stratégie de signature (HMAC) avant même de réveiller le moteur.
"""
db.define_table('webhook_endpoint',
    Field('user_workflow_id', 'reference user_workflow'),
    Field('trigger_node_id', 'string'),
    
    # AJOUT DU VALIDATEUR IS_NOT_IN_DB COMBINÉ AVEC IS_NOT_EMPTY
    Field('path', 'string', requires=[IS_NOT_EMPTY(), IS_NOT_IN_DB(db, 'webhook_endpoint.path')], unique=True),
    
    Field('http_method', 'string', requires=IS_IN_SET(['GET', 'POST', 'PUT', 'ANY']), default='POST'),
    Field('signature_strategy', 'string', requires=IS_IN_SET(['none', 'stripe_hmac', 'github_hmac', 'custom_hmac']), default='none'), 
    Field('is_active', 'boolean', default=False), 
    
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False)
)

# =========================================================================
# 4. SUPERVISION ET TRAÇABILITÉ (Strict Déterminisme)
# =========================================================================

"""
TABLE : workflow_run
--------------------
* UTILITÉ : C'est le journal de bord (Log) de haut niveau. Il trace chaque exécution 
  globale d'un workflow (du début à la fin).
* POURQUOI SA CRÉATION : Indispensable pour l'audit, le support client et l'idempotence. 
  Si un webhook Stripe est reçu deux fois (même `source_event_id`), on regarde ici pour ne 
  pas facturer le client deux fois. Permet aussi d'afficher un historique propre à l'utilisateur.
"""
db.define_table('workflow_run',
    Field('user_workflow_id', 'reference user_workflow'),
    Field('trigger_type', 'string'), 
    Field('started_by', 'string'),
    Field('source_event_id', 'string', label="Idempotency Key"), 
    
    Field('status', 'string', requires=IS_IN_SET(['running', 'success', 'failed']), default='running'),
    Field('error_code', 'string'),
    Field('trigger_payload_snapshot', 'json'),
    
    Field('started_at', 'datetime', default=request.now),
    Field('finished_at', 'datetime'),
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False)
)

"""
TABLE : workflow_run_step
-------------------------
* UTILITÉ : C'est la boîte noire de l'avion. Elle logge l'état exact (inputs, outputs, erreurs) 
  pour CHAQUE NŒUD traversé pendant un run.
* POURQUOI SA CRÉATION : Débogage "Fail Fast". Si un workflow de 10 étapes plante à l'étape 4, 
  le système s'arrête net. Cette table permet de savoir exactement ce qui est entré et sorti de 
  l'étape 3, et l'erreur exacte levée à l'étape 4, sans avoir à deviner ce qui s'est passé en mémoire.
"""
db.define_table('workflow_run_step',
    Field('run_id', 'reference workflow_run'),
    Field('execution_order', 'integer', label="Séquence stricte du run"), # Pas de default, forcé par le moteur
    Field('node_id', 'string', requires=IS_NOT_EMPTY()), 
    Field('node_type', 'string', label="ex: slack.send_message"), 
    
    Field('status', 'string', requires=IS_IN_SET(['running', 'success', 'failed', 'skipped'])),
    Field('error_code', 'string'),
    Field('error_message', 'text'),
    
    Field('input_count', 'integer', default=0),
    Field('output_count', 'integer', default=0),
    Field('context_snapshot', 'json', label="Inputs/Outputs Sanitizés Uniquement"),
    
    Field('started_at', 'datetime', default=request.now),
    Field('finished_at', 'datetime'),
    Field('execution_time_ms', 'integer')
)

# =========================================================================
# 5. E-COMMERCE ET PROVISIONING (La Boutique)
# =========================================================================

"""
TABLE : payment_order
---------------------
* UTILITÉ : C'est le reçu d'achat. Il lie un utilisateur, un paiement externe (ex: Stripe) 
  et un Template de Workflow.
* POURQUOI SA CRÉATION : C'est le pilier de votre business model (B2C - Achat de recettes). 
  Il sert de preuve ("Acquisition légitime") pour déclencher le "ProvisioningService", 
  qui va cloner le Template vers un `user_workflow` et donner l'accès au client en toute sécurité.
"""
db.define_table('payment_order',
    Field('user_id', 'reference auth_user'),
    Field('template_id', 'reference workflow_template'),
    Field('provisioned_workflow_id', 'reference user_workflow'),
    
    Field('provider', 'string', default='stripe'),
    
    # AJOUT DU VALIDATEUR IS_NOT_IN_DB
    Field('provider_session_id', 'string', requires=IS_NOT_IN_DB(db, 'payment_order.provider_session_id'), unique=True), 
    
    Field('amount_cents', 'integer'),
    Field('currency', 'string', default='EUR'),
    
    Field('status', 'string', requires=IS_IN_SET(['pending', 'paid', 'failed']), default='pending'),
    Field('paid_at', 'datetime'),
    
    Field('created_on', 'datetime', default=request.now, writable=False),
    Field('updated_on', 'datetime', default=request.now, update=request.now, writable=False)
)