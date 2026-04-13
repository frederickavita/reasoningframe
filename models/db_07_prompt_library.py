# -*- coding: utf-8 -*-


PROMPT_OWNER_TYPES = [
    'system',   # prompt officiel du cours
    'user'      # prompt personnel de l'utilisateur
]

PROMPT_TYPES = [
    'summary',
    'email',
    'brainstorm',
    'structure',
    'analysis',
    'verification',
    'workflow',
    'general'
]

PROMPT_VISIBILITY = [
    'private',
    'course'
]

SUPPORTED_LANGUAGES = ['fr', 'en', 'es']

db.define_table(
    'prompt_library',

    Field(
        'user_id',
        'reference auth_user'
    ),

    Field(
        'owner_type',
        'string',
        length=16,
        default='user',
        requires=IS_IN_SET(PROMPT_OWNER_TYPES)
    ),

    Field(
        'visibility',
        'string',
        length=16,
        default='private',
        requires=IS_IN_SET(PROMPT_VISIBILITY)
    ),

    # Identifiant logique partagé entre variantes linguistiques
    Field('content_key', 'string', length=100, default=''),

    Field('slug', 'string', length=100, default=''),

    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field(
        'prompt_type',
        'string',
        length=32,
        default='general',
        requires=IS_IN_SET(PROMPT_TYPES)
    ),

    Field('title', 'string', length=200, required=True),
    Field('description', 'text', default=''),

    # Prompt principal
    Field('prompt_text', 'text', default=''),

    # Variante plus structurée / workflow si besoin
    Field('input_template', 'text', default=''),
    Field('expected_output', 'text', default=''),

    # Lien éventuel avec le contenu pédagogique
    Field('lesson_id', 'reference learning_lesson'),
    Field('mission_id', 'reference learning_mission'),

    # Métadonnées d’usage
    Field('tags_csv', 'string', length=255, default=''),
    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),

    # Usage réel
    Field('copy_count', 'integer', default=0),
    Field('last_copied_on', 'datetime'),

    # État
    Field('is_favorite', 'boolean', default=False),
    Field('is_active', 'boolean', default=True),

    # Dates techniques
    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# Labels
db.prompt_library.owner_type.label = T('Propriétaire')
db.prompt_library.visibility.label = T('Visibilité')
db.prompt_library.language.label = T('Langue')
db.prompt_library.prompt_type.label = T('Type')
db.prompt_library.prompt_text.label = T('Prompt')
db.prompt_library.input_template.label = T('Template d’entrée')     
db.prompt_library.expected_output.label = T('Sortie attendue')
db.prompt_library.tags_csv.label = T('Tags')
db.prompt_library.copy_count.label = T('Nombre de copies')



def create_system_prompt(title,
                         prompt_text,
                         language='fr',
                         prompt_type='general',
                         description='',
                         content_key='',
                         slug='',
                         input_template='',
                         expected_output='',
                         lesson_id=None,
                         mission_id=None,
                         tags_csv='',
                         sort_order=1):
    return db.prompt_library.insert(
        user_id=None,
        owner_type='system',
        visibility='course',
        content_key=content_key,
        slug=slug,
        language=language,
        prompt_type=prompt_type,
        title=title,
        description=description,
        prompt_text=prompt_text,
        input_template=input_template,
        expected_output=expected_output,
        lesson_id=lesson_id,
        mission_id=mission_id,
        tags_csv=tags_csv,
        sort_order=sort_order,
        is_active=True
    )


def create_user_prompt(user_id,
                       title,
                       prompt_text,
                       language='fr',
                       prompt_type='general',
                       description='',
                       input_template='',
                       expected_output='',
                       tags_csv=''):
    return db.prompt_library.insert(
        user_id=user_id,
        owner_type='user',
        visibility='private',
        language=language,
        prompt_type=prompt_type,
        title=title,
        description=description,
        prompt_text=prompt_text,
        input_template=input_template,
        expected_output=expected_output,
        tags_csv=tags_csv,
        is_active=True
    )


def get_course_prompts(language='fr', prompt_type=None):
    query = (
        (db.prompt_library.owner_type == 'system') &
        (db.prompt_library.visibility == 'course') &
        (db.prompt_library.language == language) &
        (db.prompt_library.is_active == True)
    )

    if prompt_type:
        query &= (db.prompt_library.prompt_type == prompt_type)

    return db(query).select(orderby=db.prompt_library.sort_order)


def get_user_prompts(user_id, language=None, favorites_only=False):
    query = (
        (db.prompt_library.owner_type == 'user') &
        (db.prompt_library.user_id == user_id) &
        (db.prompt_library.is_active == True)
    )

    if language:
        query &= (db.prompt_library.language == language)

    if favorites_only:
        query &= (db.prompt_library.is_favorite == True)

    return db(query).select(orderby=~db.prompt_library.modified_on)



def mark_prompt_copied(prompt_id):
    row = db.prompt_library[prompt_id]
    if not row:
        return False

    db(db.prompt_library.id == prompt_id).update(
        copy_count=(row.copy_count or 0) + 1,
        last_copied_on=request.now,
        modified_on=request.now
    )
    return True


def toggle_prompt_favorite(prompt_id, value=True):
    row = db.prompt_library[prompt_id]
    if not row:
        return False

    db(db.prompt_library.id == prompt_id).update(
        is_favorite=value,
        modified_on=request.now
    )
    return True