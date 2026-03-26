# -*- coding: utf-8 -*-
# models/30_learning_platform.py
#
# Architecture de la plateforme d'Active Learning - CogniAI EdTech
# Conçue pour gérer 6 modules (du simple terminal aux workflows multimodaux en Y)

import uuid
import typing_extensions as typing

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



# models/db.py (à ajouter à la fin du fichier)
# Dans models/db.py
db.define_table('generated_course',
    Field('user_id', 'reference auth_user'),
    Field('title', 'string'),
    Field('language', 'string'),
    Field('topic', 'string'),
    Field('prompt_used', 'text'),       # NOUVEAU : Pour le debug et l'historique
    Field('content_json', 'text'),
    Field('created_on', 'datetime', default=request.now)
)




# --- Définition du schéma strict pour Gemini ---
# --- Définition du schéma strict pour Gemini ---
class ExampleSchema(typing.TypedDict):
    type: str
    title: str
    code: str
    result: str
    explanation: str

class QuickChallengeSchema(typing.TypedDict):
    instruction: str

class ModuleSchema(typing.TypedDict):
    module_title: str
    goal: str
    definition: str
    syntax: str
    examples: list[ExampleSchema]
    quick_challenge: QuickChallengeSchema

class CourseSchema(typing.TypedDict):
    course_title: str
    topic_overview: str
    modules: list[ModuleSchema]