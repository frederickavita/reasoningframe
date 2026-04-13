# -*- coding: utf-8 -*-


FEEDBACK_TYPES = [
    'bug',
    'idea',
    'improvement',
    'content_issue',
    'ux_issue',
    'payment_issue',
    'other'
]

FEEDBACK_STATUSES = [
    'new',
    'reviewed',
    'planned',
    'in_progress',
    'answered',
    'closed'
]

FEEDBACK_PRIORITIES = [
    'low',
    'normal',
    'high'
]

db.define_table(
    'feedback',

    Field(
        'user_id',
        'reference auth_user',
        required=True,
        notnull=True
    ),

    Field(
        'feedback_type',
        'string',
        length=32,
        default='idea',
        requires=IS_IN_SET(FEEDBACK_TYPES)
    ),

    Field(
        'title',
        'string',
        length=200,
        requires=IS_NOT_EMPTY()
    ),

    Field(
        'message',
        'text',
        requires=IS_NOT_EMPTY()
    ),

    # Où le feedback a été émis
    Field('page_url', 'string', length=255, default=''),
    Field('page_key', 'string', length=100, default=''),

    # Niveau de traitement interne
    Field(
        'status',
        'string',
        length=32,
        default='new',
        requires=IS_IN_SET(FEEDBACK_STATUSES)
    ),

    Field(
        'priority',
        'string',
        length=16,
        default='normal',
        requires=IS_IN_SET(FEEDBACK_PRIORITIES)
    ),

    # Ce que l'utilisateur attend / veut améliorer
    Field('desired_outcome', 'text', default=''),

    # Notre réponse interne / support / produit
    Field('admin_response', 'text', default=''),

    Field('responded_by', 'reference auth_user'),
    Field('responded_on', 'datetime'),

    # Flags utiles
    Field('is_answered', 'boolean', default=False),
    Field('is_archived', 'boolean', default=False),

    # Dates techniques
    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Labels
# ---------------------------------------------------------
db.feedback.feedback_type.label = T('Type')
db.feedback.title.label = T('Titre')
db.feedback.message.label = T('Message')
db.feedback.desired_outcome.label = T('Amélioration souhaitée')
db.feedback.admin_response.label = T('Réponse')
db.feedback.status.label = T('Statut')
db.feedback.priority.label = T('Priorité')

# ---------------------------------------------------------
# Champs que l'utilisateur final ne doit pas modifier
# ---------------------------------------------------------
db.feedback.status.writable = False
db.feedback.priority.writable = False
db.feedback.admin_response.writable = False
db.feedback.responded_by.writable = False
db.feedback.responded_on.writable = False
db.feedback.is_answered.writable = False
db.feedback.is_archived.writable = False

# En général, ces champs n'ont pas besoin d'être lisibles côté utilisateur
db.feedback.admin_response.readable = False
db.feedback.responded_by.readable = False
db.feedback.responded_on.readable = False
db.feedback.is_archived.readable = False



def create_feedback_for_user(user_id, title, message, feedback_type='idea',
                             desired_outcome='', page_url='', page_key=''):
    return db.feedback.insert(
        user_id=user_id,
        title=title,
        message=message,
        feedback_type=feedback_type,
        desired_outcome=desired_outcome,
        page_url=page_url,
        page_key=page_key
    )


def answer_feedback(feedback_id, admin_user_id, response_text,
                    status='answered', priority='normal'):
    db(db.feedback.id == feedback_id).update(
        admin_response=response_text,
        responded_by=admin_user_id,
        responded_on=request.now,
        is_answered=True,
        status=status,
        priority=priority,
        modified_on=request.now
    )