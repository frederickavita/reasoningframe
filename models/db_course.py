# -*- coding: utf-8 -*-
# models/30_learning_platform.py
#
# Architecture de la plateforme d'Active Learning - CogniAI EdTech
# Conçue pour gérer 6 modules (du simple terminal aux workflows multimodaux en Y)

import uuid

# -----------------------------------------------------------------------------
# CONSTANTES ET ÉNUMÉRATIONS
# -----------------------------------------------------------------------------

db.define_table('course',
    Field('user_id', 'reference auth_user', default=auth.user_id),
    Field('title', 'string', requires=IS_NOT_EMPTY()),
    Field('subject', 'text'), # Ce que l'utilisateur a tapé
    Field('language', 'string'), # Python, CSS, etc.
    Field('content', 'json'), # Le cours complet généré par l'IA
    Field('created_on', 'datetime', default=request.now),
    auth.signature
)


db.define_table('user_transaction',
    Field('user_id', 'reference auth_user'),
    Field('paypal_id'),
    Field('amount', 'double'),
    Field('status', 'string'),
    Field('created_on', 'datetime', default=request.now),
    auth.signature
)




# -*- coding: utf-8 -*-
from gluon.validators import IS_NOT_EMPTY

db.define_table(
    'credit_topup',
    Field('user_id', 'reference auth_user', requires=IS_NOT_EMPTY()),
    Field('topup_ref', requires=IS_NOT_EMPTY()),
    Field('provider', default='paypal'),
    Field('status', default='pending'),  # pending / completed / failed
    Field('amount', 'decimal(10,2)', default=39.00),
    Field('currency', length=3, default='USD'),
    Field('credits', 'integer', default=100),
    Field('paypal_capture_id', unique=True),
    Field('paypal_event_id', unique=True),
    Field('raw_payload', 'text'),
    Field('created_on', 'datetime', default=request.now),
    Field('updated_on', 'datetime', update=request.now),
)




# Définition de la référence utilisateur (Compatible avec Auth Web2py)
USER_REF = 'reference auth_user' if 'auth_user' in db.tables else 'integer'

TRACK_STATUSES = ('draft', 'published', 'archived')
MODULE_STATUSES = ('draft', 'published', 'archived')
MODULE_TYPES = ('concept', 'project', 'lab')

# La structure visuelle du module (ex: Split-Screen pour M1, Canvas en Y pour M6)
UI_LAYOUTS = ('split_screen', 'split_screen_multimodal', 'fullscreen_canvas')

LEFT_PANEL_KINDS = ('tutor', 'video', 'text_only')
RIGHT_PANEL_KINDS = ('terminal', 'workbench', 'workflow_canvas', 'multimodal_canvas')

QUESTION_KINDS = ('suggested', 'definition', 'qcm', 'hint', 'squelette')

PROGRESS_STATUSES = ('not_started', 'in_progress', 'blocked', 'completed')
SESSION_STATUSES = ('active', 'paused', 'completed', 'abandoned')

# Les actions traçables pour l'analytique (Event-Sourcing)
EVENT_TYPES = (
    'page_view',
    'suggestion_opened',
    'help_requested',
    'help_proactive_shown',
    'drag_sort_started',
    'drag_sort_submitted',
    'drag_sort_corrected',
    'node_added',
    'node_removed',
    'node_connected',
    'node_disconnected',
    'run_started',
    'run_paused',
    'run_failed',
    'run_succeeded',
    'qcm_opened',
    'qcm_answered',
    'hint_opened',
    'prompt_opened',
    'prompt_updated',
    'human_validation_approved', # Spécifique Module 4
    'cost_simulated',            # Spécifique Module 4
    'module_completed',
)

ACTOR_TYPES = ('user', 'system', 'tutor', 'backend')

RUN_KINDS = ('simulation', 'live_api', 'hybrid')
RUN_STATUSES = ('pending', 'running', 'paused', 'failed', 'succeeded', 'partial')

ARTIFACT_TYPES = (
    'text_draft',
    'email_preview',
    'image',
    'document_assembled', # Spécifique Module 6 (Texte + Image)
    'json_data',          # Spécifique Module 5
    'table_cell',
)
ARTIFACT_ROLES = ('before', 'after', 'final', 'source', 'preview')
MODEL_TIERS = ('small', 'standard', 'powerful')

# -----------------------------------------------------------------------------
# HELPERS DAL (Data Abstraction Layer)
# -----------------------------------------------------------------------------

def json_field(name, default=None, label=None, comment=None):
    """
    Crée un champ JSON natif optimisé pour Web2py.
    Utilise une lambda pour éviter le partage de référence mémoire du dictionnaire vide.
    """
    if default is None:
        default = lambda: {}
    return Field(
        name,
        'json',
        default=default,
        label=label,
        comment=comment or 'Objet Python auto-sérialisé en JSON'
    )

def common_fields():
    """Ajoute les champs de traçabilité standard à chaque table."""
    return [
        Field('is_active', 'boolean', default=True),
        Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
        Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),
    ]

def define_lp_table(name, *fields):
    """Encapsule la création de table avec les options standards."""
    db.define_table(
        name,
        *(list(fields) + common_fields()),
        migrate=True,
        redefine=False,
    )

# Validateur de Slug : format strict + unicité (gérée par appelant avec IS_NOT_IN_DB)
slug_requires = [
    IS_NOT_EMPTY(),
    IS_MATCH(
        r'^[a-z0-9][a-z0-9\-]*$',
        error_message='Utilisez seulement des minuscules, des chiffres et des tirets'
    ),
]

# -----------------------------------------------------------------------------
# 1. CATALOGUE DE FORMATION (Tracks & Modules)
# -----------------------------------------------------------------------------

define_lp_table(
    'lp_track',
    Field('slug', length=80, unique=True, requires=slug_requires + [IS_NOT_IN_DB(db, 'lp_track.slug')]),
    Field('title', length=160, requires=IS_NOT_EMPTY()),
    Field('description', 'text'),
    Field('audience', length=80, default='debutant'),
    Field('status', length=20, default='draft', requires=IS_IN_SET(TRACK_STATUSES)),
    json_field('settings_json'),      # Ex: { theme: 'dark' }
    json_field('design_system_json'), # Ex: { primary_color: '#F26E47' }
)
db.lp_track._format = '%(title)s'

define_lp_table(
    'lp_module',
    Field('track_id', 'reference lp_track', requires=IS_IN_DB(db, 'lp_track.id', '%(title)s')),
    Field('slug', length=80, unique=True, requires=slug_requires + [IS_NOT_IN_DB(db, 'lp_module.slug')]),
    Field('module_number', 'integer', default=1, requires=IS_INT_IN_RANGE(1, 1000)),
    Field('title', length=160, requires=IS_NOT_EMPTY()),
    Field('module_type', length=20, default='concept', requires=IS_IN_SET(MODULE_TYPES)),
    Field('pedagogical_goal', 'text'),
    Field('concept_goal', 'text'),
    Field('summary', 'text'),
    
    # Configuration de l'Interface Visuelle (Pour Brython)
    Field('ui_layout', length=30, default='split_screen', requires=IS_IN_SET(UI_LAYOUTS)),
    Field('left_panel_kind', length=30, default='tutor', requires=IS_IN_SET(LEFT_PANEL_KINDS)),
    Field('right_panel_kind', length=40, default='workflow_canvas', requires=IS_IN_SET(RIGHT_PANEL_KINDS)),
    
    Field('status', length=20, default='draft', requires=IS_IN_SET(MODULE_STATUSES)),
    Field('estimated_minutes', 'integer', default=10, requires=IS_INT_IN_RANGE(1, 1000)),
    Field('version_no', 'integer', default=1, requires=IS_INT_IN_RANGE(1, 100000)),
    
    # Configuration profonde du Module (Consommée par Brython)
    json_field('starter_graph_json'), # Les nœuds dispos au lancement (Ex: ['gmail', 'gpt4'])
    json_field('content_json'),       # La mission, le sous-titre
    json_field('copy_json'),          # Les textes du Tuteur Gemini
    json_field('settings_json'),      # Paramètres avancés (Ex: timer d'aide proactive à 120s)
)
db.lp_module._format = '%(module_number)s - %(title)s'

# -----------------------------------------------------------------------------
# 2. MÉCANIQUES PÉDAGOGIQUES (Suggestions, QCM, Squelettes, Hints)
# -----------------------------------------------------------------------------

define_lp_table(
    'lp_question',
    Field('module_id', 'reference lp_module', requires=IS_IN_DB(db, 'lp_module.id', '%(title)s')),
    Field('phase_key', length=60, default='phase_1'), # Ex: 'intro', 'error_handling', 'success'
    Field('question_kind', length=20, default='suggested', requires=IS_IN_SET(QUESTION_KINDS)),
    Field('prompt_text', 'text', requires=IS_NOT_EMPTY()),
    Field('choice_a', 'text'),
    Field('choice_b', 'text'),
    Field('correct_choice', length=5, requires=IS_IN_SET(['', 'A', 'B', 'NONE'], zero=None), default=''),
    Field('answer_text', 'text'),
    Field('display_order', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 100000)),
    json_field('metadata_json'), # Pour stocker l'ordre des cartes d'un squelette par exemple
)

# -----------------------------------------------------------------------------
# 3. ÉTAT UTILISATEUR & SESSIONS LIVE
# -----------------------------------------------------------------------------

define_lp_table(
    'lp_module_progress',
    Field('user_id', USER_REF),
    Field('track_id', 'reference lp_track'),
    Field('module_id', 'reference lp_module'),
    Field('status', length=20, default='not_started', requires=IS_IN_SET(PROGRESS_STATUSES)),
    Field('percent_complete', 'double', default=0.0, requires=IS_FLOAT_IN_RANGE(0, 101)),
    Field('current_phase', length=60, default='phase_1'),
    Field('attempts_count', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 1000000)),
    Field('first_opened_on', 'datetime'),
    Field('last_opened_on', 'datetime'),
    Field('completed_on', 'datetime'),
    Field('best_score', 'double', default=0.0),
    json_field('state_json'),
    json_field('analytics_json'),
)
db.lp_module_progress._format = '%(status)s'

define_lp_table(
    'lp_module_session',
    Field('user_id', USER_REF),
    Field('module_id', 'reference lp_module'),
    Field('progress_id', 'reference lp_module_progress'),
    Field('session_token', length=64, unique=True, default=lambda: uuid.uuid4().hex),
    Field('status', length=20, default='active', requires=IS_IN_SET(SESSION_STATUSES)),
    Field('current_phase', length=60, default='phase_1'),
    Field('current_step_key', length=100),
    
    # L'état complet de l'UI sauvegardé en temps réel
    json_field('workflow_graph_json'), # Le Canvas de l'utilisateur
    json_field('ui_state_json'),       # Quels tiroirs sont ouverts ?
    json_field('input_state_json'),    # Les textes tapés (Prompt, Plainte client M5)
    json_field('helper_state_json'),   # Le QCM est-il réussi ? Hint révélé ?
    
    Field('started_on', 'datetime', default=request.now),
    Field('last_seen_on', 'datetime', default=request.now),
    Field('completed_on', 'datetime'),
    Field('closed_reason', length=100),
)
db.lp_module_session._format = '%(session_token)s'

# -----------------------------------------------------------------------------
# 4. ANALYTIQUE & EXÉCUTION (Event-Driven)
# -----------------------------------------------------------------------------

define_lp_table(
    'lp_session_event',
    Field('session_id', 'reference lp_module_session'),
    Field('module_id', 'reference lp_module'),
    Field('phase_key', length=60, default='phase_1'),
    Field('event_type', length=40, default='page_view', requires=IS_IN_SET(EVENT_TYPES)),
    Field('actor_type', length=20, default='user', requires=IS_IN_SET(ACTOR_TYPES)),
    Field('label', length=160),
    Field('sequence_no', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 100000000)),
    json_field('payload_json'), # Ex: { 'choice_selected': 'A', 'time_to_click': 14.5 }
    Field('happened_on', 'datetime', default=request.now),
)

define_lp_table(
    'lp_run',
    Field('session_id', 'reference lp_module_session'),
    Field('module_id', 'reference lp_module'),
    Field('phase_key', length=60, default='phase_1'),
    Field('run_kind', length=20, default='simulation', requires=IS_IN_SET(RUN_KINDS)),
    Field('status', length=20, default='pending', requires=IS_IN_SET(RUN_STATUSES)),
    
    # La traçabilité de l'exécution du workflow
    json_field('input_json'),            # La plainte du client (M5)
    json_field('graph_snapshot_json'),   # À quoi ressemblait le workflow à cet instant T
    json_field('source_payload_json'),   
    json_field('request_payload_json'),  
    json_field('response_payload_json'), # Le résultat généré par l'Agent
    
    Field('error_code', length=80),
    Field('error_message', 'text'),
    Field('cost_estimate', 'double', default=0.0),
    Field('latency_ms', 'integer', default=0),
    Field('started_on', 'datetime', default=request.now),
    Field('finished_on', 'datetime'),
)
db.lp_run._format = '%(status)s'

# -----------------------------------------------------------------------------
# 5. ARTEFACTS & SIMULATION (Sorties multimodales et coûts)
# -----------------------------------------------------------------------------

define_lp_table(
    'lp_artifact',
    Field('module_id', 'reference lp_module'),
    Field('session_id', 'reference lp_module_session'),
    Field('run_id', 'reference lp_run'),
    Field('artifact_type', length=30, requires=IS_IN_SET(ARTIFACT_TYPES)),
    Field('artifact_role', length=20, default='final', requires=IS_IN_SET(ARTIFACT_ROLES)),
    Field('title', length=160),
    Field('mime_type', length=120),
    Field('content_text', 'text'),        # L'email généré
    json_field('content_json'),           # La donnée JSON brute de l'API météo (M5)
    Field('file_upload', 'upload'),       # Les images générées (M6)
    Field('external_url', length=255),
    Field('sort_order', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 100000)),
)
db.lp_artifact._format = '%(artifact_type)s'

define_lp_table(
    'lp_cost_simulation', # Spécifique au Module 4
    Field('session_id', 'reference lp_module_session'),
    Field('module_id', 'reference lp_module'),
    Field('emails_per_month', 'integer', default=1000, requires=IS_INT_IN_RANGE(0, 100000000)),
    Field('model_tier', length=20, default='standard', requires=IS_IN_SET(MODEL_TIERS)),
    Field('estimated_monthly_cost', 'double', default=0.0),
    json_field('assumptions_json'),
    Field('computed_on', 'datetime', default=request.now),
)
db.lp_cost_simulation._format = '%(estimated_monthly_cost)s'

# -----------------------------------------------------------------------------
# PERSONNALISATION DE L'ADMIN WEB2PY (Labels UI)
# -----------------------------------------------------------------------------

db.lp_module.track_id.label = 'Parcours'
db.lp_module.module_number.label = 'Numéro'
db.lp_module.module_type.label = 'Type de module'
db.lp_module.pedagogical_goal.label = 'Objectif pédagogique'
db.lp_module.ui_layout.label = 'Layout UI'
db.lp_module.left_panel_kind.label = 'Panneau gauche'
db.lp_module.right_panel_kind.label = 'Panneau droit'

db.lp_question.question_kind.label = 'Type de question'
db.lp_question.prompt_text.label = 'Question / Prompt'
db.lp_question.answer_text.label = 'Réponse'

db.lp_module_progress.percent_complete.label = '% progression'
db.lp_run.graph_snapshot_json.label = 'Snapshot graphe (JSON)'
db.lp_artifact.content_text.label = 'Contenu texte'
db.lp_artifact.content_json.label = 'Contenu structuré (JSON)'