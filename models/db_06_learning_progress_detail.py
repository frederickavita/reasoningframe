# -*- coding: utf-8 -*-



LESSON_PROGRESS_STATUSES = [
    'not_started',
    'in_progress',
    'completed',
    'mastered'
]

ATTEMPT_RESULT_STATUSES = [
    'success',
    'failure',
    'partial'
]

SKILL_PROGRESS_STATUSES = [
    'locked',
    'learning',
    'unlocked',
    'mastered'
]

MISSION_PROGRESS_STATUSES = [
    'not_started',
    'in_progress',
    'submitted',
    'completed',
    'needs_revision'
]

# ---------------------------------------------------------
# Progression détaillée par leçon
# Une ligne = un utilisateur + une leçon
# ---------------------------------------------------------
db.define_table(
    'lesson_progress',

    Field('user_id', 'reference auth_user', required=True, notnull=True),
    Field('lesson_id', 'reference learning_lesson', required=True, notnull=True),

    Field(
        'status',
        'string',
        length=32,
        default='not_started',
        requires=IS_IN_SET(LESSON_PROGRESS_STATUSES)
    ),

    Field('attempts_count', 'integer', default=0),
    Field('best_score', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 101)),
    Field('last_score', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 101)),

    Field('xp_earned', 'integer', default=0),
    Field('time_spent_seconds', 'integer', default=0),

    Field('started_on', 'datetime'),
    Field('completed_on', 'datetime'),
    Field('last_attempt_on', 'datetime'),
    Field('last_viewed_on', 'datetime'),

    Field('is_unlocked', 'boolean', default=False),
    Field('is_current', 'boolean', default=False),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(id)s'
)

# ---------------------------------------------------------
# Tentatives détaillées sur une leçon
# Une ligne = une tentative
# raw_payload peut contenir les réponses, ordre choisi, etc. en JSON texte
# ---------------------------------------------------------
db.define_table(
    'lesson_attempt',

    Field('user_id', 'reference auth_user', required=True, notnull=True),
    Field('lesson_id', 'reference learning_lesson', required=True, notnull=True),
    Field('lesson_progress_id', 'reference lesson_progress'),

    Field('attempt_number', 'integer', default=1),
    Field(
        'result_status',
        'string',
        length=32,
        default='success',
        requires=IS_IN_SET(ATTEMPT_RESULT_STATUSES)
    ),

    Field('score', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 101)),
    Field('xp_earned', 'integer', default=0),
    Field('duration_seconds', 'integer', default=0),

    Field('raw_payload', 'text', default=''),
    Field('feedback_snapshot', 'text', default=''),

    Field('attempted_on', 'datetime', default=request.now),

    format='%(id)s'
)

# ---------------------------------------------------------
# Progression par skill / micro-compétence
# Une ligne = un utilisateur + une skill
# ---------------------------------------------------------
db.define_table(
    'skill_progress',

    Field('user_id', 'reference auth_user', required=True, notnull=True),
    Field('skill_id', 'reference learning_skill', required=True, notnull=True),

    Field(
        'status',
        'string',
        length=32,
        default='locked',
        requires=IS_IN_SET(SKILL_PROGRESS_STATUSES)
    ),

    Field('mastery_percent', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 101)),
    Field('evidence_count', 'integer', default=0),
    Field('successful_uses_count', 'integer', default=0),

    Field('unlocked_on', 'datetime'),
    Field('mastered_on', 'datetime'),
    Field('last_practiced_on', 'datetime'),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(id)s'
)

# ---------------------------------------------------------
# Progression par mission
# Une ligne = un utilisateur + une mission
# ---------------------------------------------------------
db.define_table(
    'mission_progress',

    Field('user_id', 'reference auth_user', required=True, notnull=True),
    Field('mission_id', 'reference learning_mission', required=True, notnull=True),

    Field(
        'status',
        'string',
        length=32,
        default='not_started',
        requires=IS_IN_SET(MISSION_PROGRESS_STATUSES)
    ),

    Field('score', 'integer', default=0, requires=IS_INT_IN_RANGE(0, 101)),
    Field('xp_earned', 'integer', default=0),

    Field('submission_text', 'text', default=''),
    Field('submission_payload', 'text', default=''),
    Field('review_notes', 'text', default=''),

    Field('started_on', 'datetime'),
    Field('submitted_on', 'datetime'),
    Field('completed_on', 'datetime'),
    Field('last_updated_on', 'datetime', default=request.now),

    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(id)s'
)

# ---------------------------------------------------------
# Labels lisibles
# ---------------------------------------------------------
db.lesson_progress.status.label = T('Statut')
db.lesson_progress.best_score.label = T('Meilleur score')
db.lesson_progress.last_score.label = T('Dernier score')
db.lesson_progress.xp_earned.label = T('XP gagnés')

db.lesson_attempt.result_status.label = T('Résultat')
db.lesson_attempt.raw_payload.label = T('Payload brut')
db.lesson_attempt.feedback_snapshot.label = T('Feedback généré')

db.skill_progress.status.label = T('Statut')
db.skill_progress.mastery_percent.label = T('Maîtrise (%)')

db.mission_progress.status.label = T('Statut')
db.mission_progress.submission_text.label = T('Soumission')
db.mission_progress.review_notes.label = T('Notes de revue')



def get_or_create_lesson_progress(user_id, lesson_id):
    row = db(
        (db.lesson_progress.user_id == user_id) &
        (db.lesson_progress.lesson_id == lesson_id)
    ).select().first()

    if row:
        return row

    progress_id = db.lesson_progress.insert(
        user_id=user_id,
        lesson_id=lesson_id,
        is_unlocked=True,
        is_current=False
    )
    return db.lesson_progress[progress_id]


def start_lesson_for_user(user_id, lesson_id):
    row = get_or_create_lesson_progress(user_id, lesson_id)

    updates = {
        'status': 'in_progress',
        'last_viewed_on': request.now,
        'modified_on': request.now
    }

    if not row.started_on:
        updates['started_on'] = request.now

    db(db.lesson_progress.id == row.id).update(**updates)
    return db.lesson_progress[row.id]



def record_lesson_attempt(user_id, lesson_id, score,
                          result_status='success',
                          xp_earned=0,
                          duration_seconds=0,
                          raw_payload='',
                          feedback_snapshot=''):
    progress = get_or_create_lesson_progress(user_id, lesson_id)

    attempt_number = (progress.attempts_count or 0) + 1

    db.lesson_attempt.insert(
        user_id=user_id,
        lesson_id=lesson_id,
        lesson_progress_id=progress.id,
        attempt_number=attempt_number,
        result_status=result_status,
        score=score,
        xp_earned=xp_earned,
        duration_seconds=duration_seconds,
        raw_payload=raw_payload,
        feedback_snapshot=feedback_snapshot,
        attempted_on=request.now
    )

    new_best = max(progress.best_score or 0, score)

    new_status = 'in_progress'
    completed_on = progress.completed_on
    if score >= 80:
        new_status = 'completed'
        if score >= 95:
            new_status = 'mastered'
        if not completed_on:
            completed_on = request.now

    db(db.lesson_progress.id == progress.id).update(
        status=new_status,
        attempts_count=attempt_number,
        best_score=new_best,
        last_score=score,
        xp_earned=(progress.xp_earned or 0) + xp_earned,
        time_spent_seconds=(progress.time_spent_seconds or 0) + duration_seconds,
        last_attempt_on=request.now,
        last_viewed_on=request.now,
        completed_on=completed_on,
        modified_on=request.now
    )

    return db.lesson_progress[progress.id]



def get_or_create_skill_progress(user_id, skill_id):
    row = db(
        (db.skill_progress.user_id == user_id) &
        (db.skill_progress.skill_id == skill_id)
    ).select().first()

    if row:
        return row

    progress_id = db.skill_progress.insert(
        user_id=user_id,
        skill_id=skill_id,
        status='locked',
        mastery_percent=0
    )
    return db.skill_progress[progress_id]



def update_skill_progress_after_lesson(user_id, skill_id, lesson_score):
    row = get_or_create_skill_progress(user_id, skill_id)

    new_mastery = row.mastery_percent or 0

    if lesson_score >= 60:
        new_mastery = min(100, new_mastery + 20)

    new_status = 'learning'
    unlocked_on = row.unlocked_on
    mastered_on = row.mastered_on

    if new_mastery > 0 and not unlocked_on:
        unlocked_on = request.now
        new_status = 'unlocked'

    if new_mastery >= 100:
        new_status = 'mastered'
        if not mastered_on:
            mastered_on = request.now
    elif new_mastery >= 60:
        new_status = 'unlocked'

    db(db.skill_progress.id == row.id).update(
        status=new_status,
        mastery_percent=new_mastery,
        evidence_count=(row.evidence_count or 0) + 1,
        successful_uses_count=(row.successful_uses_count or 0) + (1 if lesson_score >= 80 else 0),
        unlocked_on=unlocked_on,
        mastered_on=mastered_on,
        last_practiced_on=request.now,
        modified_on=request.now
    )

    return db.skill_progress[row.id]



def start_mission_for_user(user_id, mission_id):
    row = db(
        (db.mission_progress.user_id == user_id) &
        (db.mission_progress.mission_id == mission_id)
    ).select().first()

    if row:
        db(db.mission_progress.id == row.id).update(
            status='in_progress',
            started_on=row.started_on or request.now,
            last_updated_on=request.now,
            modified_on=request.now
        )
        return db.mission_progress[row.id]

    progress_id = db.mission_progress.insert(
        user_id=user_id,
        mission_id=mission_id,
        status='in_progress',
        started_on=request.now,
        last_updated_on=request.now
    )
    return db.mission_progress[progress_id]


def submit_mission_for_user(user_id, mission_id, submission_text='', submission_payload=''):
    row = db(
        (db.mission_progress.user_id == user_id) &
        (db.mission_progress.mission_id == mission_id)
    ).select().first()

    if not row:
        row = start_mission_for_user(user_id, mission_id)

    db(db.mission_progress.id == row.id).update(
        status='submitted',
        submission_text=submission_text,
        submission_payload=submission_payload,
        submitted_on=request.now,
        last_updated_on=request.now,
        modified_on=request.now
    )

    return db.mission_progress[row.id]