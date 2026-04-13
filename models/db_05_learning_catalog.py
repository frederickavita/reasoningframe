# -*- coding: utf-8 -*-



SUPPORTED_LANGUAGES = ['fr', 'en', 'es']

TRACK_TYPES = [
    'core',
    'role_based'
]

LESSON_TYPES = [
    'concept',
    'quiz',
    'exercise',
    'scenario',
    'mission_prep'
]

SKILL_CATEGORIES = [
    'fundamentals',
    'prompting',
    'iteration',
    'use_cases',
    'reliability',
    'workflow'
]

# ---------------------------------------------------------
# Tracks
# Exemple :
# - core
# - solopreneur
# - consultant
# - marketing
# ---------------------------------------------------------
db.define_table(
    'learning_track',

    Field('content_key', 'string', length=100, required=True, notnull=True),
    Field('slug', 'string', length=100, required=True, notnull=True),
    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field(
        'track_type',
        'string',
        length=32,
        default='core',
        requires=IS_IN_SET(TRACK_TYPES)
    ),

    Field('title', 'string', length=200, requires=IS_NOT_EMPTY()),
    Field('subtitle', 'string', length=255, default=''),
    Field('description', 'text', default=''),

    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),
    Field('is_active', 'boolean', default=True),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Worlds / modules
# Exemple :
# - world_1_discover_claude
# - world_2_prompting
# ---------------------------------------------------------
db.define_table(
    'learning_world',

    Field('track_id', 'reference learning_track', required=True, notnull=True),

    Field('content_key', 'string', length=100, required=True, notnull=True),
    Field('slug', 'string', length=100, required=True, notnull=True),
    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field('title', 'string', length=200, requires=IS_NOT_EMPTY()),
    Field('subtitle', 'string', length=255, default=''),
    Field('description', 'text', default=''),

    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),
    Field('estimated_lessons_count', 'integer', default=0),

    Field('is_active', 'boolean', default=True),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Skills / micro-compétences
# Exemple :
# - add_context
# - define_goal
# - choose_format
# ---------------------------------------------------------
db.define_table(
    'learning_skill',

    Field('content_key', 'string', length=100, required=True, notnull=True),
    Field('slug', 'string', length=100, required=True, notnull=True),
    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field(
        'category',
        'string',
        length=32,
        default='fundamentals',
        requires=IS_IN_SET(SKILL_CATEGORIES)
    ),

    Field('title', 'string', length=200, requires=IS_NOT_EMPTY()),
    Field('description', 'text', default=''),

    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),
    Field('is_active', 'boolean', default=True),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Lessons
# Une leçon appartient à un world
# ---------------------------------------------------------
db.define_table(
    'learning_lesson',

    Field('world_id', 'reference learning_world', required=True, notnull=True),

    Field('content_key', 'string', length=100, required=True, notnull=True),
    Field('slug', 'string', length=100, required=True, notnull=True),
    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field(
        'lesson_type',
        'string',
        length=32,
        default='concept',
        requires=IS_IN_SET(LESSON_TYPES)
    ),

    Field('title', 'string', length=200, requires=IS_NOT_EMPTY()),
    Field('short_title', 'string', length=120, default=''),
    Field('hook_text', 'text', default=''),
    Field('objective', 'text', default=''),
    Field('mini_concept', 'text', default=''),
    Field('takeaway', 'text', default=''),

    Field('estimated_minutes', 'integer', default=4, requires=IS_INT_IN_RANGE(1, 61)),
    Field('xp_reward', 'integer', default=10, requires=IS_INT_IN_RANGE(0, 1000)),
    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),

    Field('is_published', 'boolean', default=True),
    Field('is_active', 'boolean',  default=True),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Mapping many-to-many : lesson <-> skill
# Une leçon peut entraîner plusieurs skills
# Une skill peut apparaître dans plusieurs leçons
# ---------------------------------------------------------
db.define_table(
    'learning_lesson_skill',

    Field('lesson_id', 'reference learning_lesson', required=True, notnull=True),
    Field('skill_id', 'reference learning_skill', required=True, notnull=True),

    Field('weight', 'integer', default=1, requires=IS_INT_IN_RANGE(1, 11)),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),

    format='%(id)s'
)

# ---------------------------------------------------------
# Missions
# ---------------------------------------------------------
db.define_table(
    'learning_mission',

    Field('track_id', 'reference learning_track', required=True, notnull=True),

    Field('content_key', 'string', length=100, required=True, notnull=True),
    Field('slug', 'string', length=100, required=True, notnull=True),
    Field(
        'language',
        'string',
        length=8,
        default='fr',
        requires=IS_IN_SET(SUPPORTED_LANGUAGES)
    ),

    Field('title', 'string', length=200, requires=IS_NOT_EMPTY()),
    Field('brief', 'text', default=''),
    Field('success_criteria', 'text', default=''),
    Field('estimated_minutes', 'integer', default=10, requires=IS_INT_IN_RANGE(1, 181)),
    Field('xp_reward', 'integer', default=50, requires=IS_INT_IN_RANGE(0, 5000)),

    Field('sort_order', 'integer', default=1, requires=IS_INT_IN_RANGE(0, 10000)),
    Field('is_published', 'boolean', default=True),
    Field('is_active', 'boolean', default=True),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(title)s'
)

# ---------------------------------------------------------
# Labels lisibles
# ---------------------------------------------------------
db.learning_track.language.label = T('Langue')
db.learning_world.language.label = T('Langue')
db.learning_skill.language.label = T('Langue')
db.learning_lesson.language.label = T('Langue')
db.learning_mission.language.label = T('Langue')

db.learning_lesson.hook_text.label = T('Hook')
db.learning_lesson.mini_concept.label = T('Mini-concept')
db.learning_lesson.takeaway.label = T('Takeaway')
db.learning_mission.brief.label = T('Brief')
db.learning_mission.success_criteria.label = T('Critères de réussite')



def get_track_by_slug(slug, language='fr'):
    return db(
        (db.learning_track.slug == slug) &
        (db.learning_track.language == language) &
        (db.learning_track.is_active == True)
    ).select().first()


def get_worlds_for_track(track_id, language='fr'):
    return db(
        (db.learning_world.track_id == track_id) &
        (db.learning_world.language == language) &
        (db.learning_world.is_active == True)
    ).select(orderby=db.learning_world.sort_order)


def get_lessons_for_world(world_id, language='fr'):
    return db(
        (db.learning_lesson.world_id == world_id) &
        (db.learning_lesson.language == language) &
        (db.learning_lesson.is_active == True) &
        (db.learning_lesson.is_published == True)
    ).select(orderby=db.learning_lesson.sort_order)

