# -*- coding: utf-8 -*-


db.define_table(
    'user_progress',

    Field(
        'user_id',
        'reference auth_user',
        required=True,
        unique=True,
        notnull=True
    ),

    # Vue globale
    Field('total_xp', 'integer', default=0),
    Field('level', 'integer', default=1),

    # Streaks
    Field('current_streak', 'integer', default=0),
    Field('longest_streak', 'integer', default=0),
    Field('last_activity_on', 'date'),

    # Position actuelle dans le parcours
    Field('current_world_slug', 'string', length=64, default='world-1'),
    Field('current_lesson_slug', 'string', length=64, default='lesson-1'),

    # Track principal choisi
    Field(
        'current_track',
        'string',
        length=64,
        default='solopreneur',
        requires=IS_IN_SET([
            'solopreneur',
            'consultant',
            'marketing',
            'student',
            'teacher',
            'office_productivity'
        ])
    ),

    # Compteurs utiles dashboard
    Field('completed_lessons_count', 'integer', default=0),
    Field('completed_missions_count', 'integer', default=0),
    Field('unlocked_skills_count', 'integer', default=0),

    # État d’usage
    Field('first_lesson_started', 'boolean', default=False),
    Field('first_mission_completed', 'boolean', default=False),

    # Dates techniques
    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(current_track)s'
)


def get_or_create_user_progress(user_id):
    row = db(db.user_progress.user_id == user_id).select().first()
    if row:
        return row

    progress_id = db.user_progress.insert(user_id=user_id)
    return db.user_progress[progress_id]