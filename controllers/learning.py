## -*- coding: utf-8 -*-
import json


def _build_lesson_navigation(track, lesson, language):
    ordered = _get_ordered_track_lessons(track.id, language) if track else []
    ordered_lessons = [l for w, l in ordered]
    lesson_ids = [l.id for l in ordered_lessons]

    prev_lesson = None
    next_lesson = None

    if lesson.id in lesson_ids:
        idx = lesson_ids.index(lesson.id)
        if idx > 0:
            prev_lesson = ordered_lessons[idx - 1]
        if idx < len(lesson_ids) - 1:
            next_lesson = ordered_lessons[idx + 1]

    return prev_lesson, next_lesson


def _lesson_completion_context(user_id, lesson, language):
    world = db.learning_world[lesson.world_id]
    track = db.learning_track[world.track_id] if world else None
    lesson_progress = db(
        (db.lesson_progress.user_id == user_id) &
        (db.lesson_progress.lesson_id == lesson.id)
    ).select().first()

    prev_lesson, next_lesson = _build_lesson_navigation(track, lesson, language)
    summary = _sync_user_progress_summary(user_id, language)

    # Progression du monde
    world_lessons = db(
        (db.learning_lesson.world_id == world.id) &
        (db.learning_lesson.language == language) &
        (db.learning_lesson.is_active == True) &
        (db.learning_lesson.is_published == True)
    ).select(db.learning_lesson.id, orderby=db.learning_lesson.sort_order)

    lesson_ids = [row.id for row in world_lessons]
    total_lessons = len(lesson_ids)
    completed_in_world = 0

    if lesson_ids:
        completed_in_world = db(
            (db.lesson_progress.user_id == user_id) &
            (db.lesson_progress.lesson_id.belongs(lesson_ids)) &
            (db.lesson_progress.status.belongs(['completed', 'mastered']))
        ).count()

    world_progress_percent = int((completed_in_world * 100.0) / total_lessons) if total_lessons else 0

    # Skills de la leçon
    skill_links = db(db.learning_lesson_skill.lesson_id == lesson.id).select()
    skill_ids = [row.skill_id for row in skill_links]
    unlocked_skills = []

    if skill_ids:
        unlocked_skills = db(
            (db.learning_skill.id.belongs(skill_ids)) &
            (db.learning_skill.language == language) &
            (db.learning_skill.is_active == True)
        ).select(orderby=db.learning_skill.sort_order)

    return dict(
        lesson=lesson,
        world=world,
        track=track,
        lesson_progress=lesson_progress,
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
        progress=summary,
        completed_in_world=completed_in_world,
        total_lessons=total_lessons,
        world_progress_percent=world_progress_percent,
        unlocked_skills=unlocked_skills,
    )


def complete_lesson_htmx():
    user = _require_login()
    language = _user_language(user)

    if request.env.request_method != 'POST':
        raise HTTP(405)

    lesson_slug = request.args(0) or request.post_vars.lesson_slug
    lesson = _get_lesson_by_slug(lesson_slug, language)
    if not lesson:
        raise HTTP(404)

    score = request.post_vars.score or 100
    _record_lesson_completion(user.id, lesson, score=score)

    context = _lesson_completion_context(user.id, lesson, language)

    # Toast HTMX
    response.headers['HX-Trigger'] = json.dumps({
        "app:toast": {
            "message": "Leçon terminée.",
            "kind": "success"
        }
    })

    return response.render('learning/_lesson_completion.html', context)

def _current_page_url():
    return URL(request.controller, request.function, args=request.args, vars=request.get_vars)


def _require_login():
    if not auth.user:
        redirect(URL('default', 'login', vars={'_next': _current_page_url()}))
    return auth.user


def _user_language(user):
    lang = getattr(user, 'learning_language', None) or getattr(user, 'ui_language', None) or 'en'
    return lang if lang in ('en', 'fr', 'es') else 'en'


def _ensure_user_progress(user_id):
    row = db(db.user_progress.user_id == user_id).select().first()
    if row:
        return row

    progress_id = db.user_progress.insert(
        user_id=user_id,
        total_xp=0,
        level=1,
        current_streak=0,
        longest_streak=0,
        current_world_slug='world-1-discover',
        current_lesson_slug='what-claude-does-well', # English slug from seed
        current_track='core',
        completed_lessons_count=0,
        completed_missions_count=0,
        unlocked_skills_count=0,
        first_lesson_started=False,
        first_mission_completed=False
    )
    return db.user_progress[progress_id]


def _get_track_by_slug(track_slug, language):
    return db(
        (db.learning_track.slug == track_slug) &
        (db.learning_track.language == language) &
        (db.learning_track.is_active == True)
    ).select().first()


def _get_lesson_by_slug(lesson_slug, language):
    return db(
        (db.learning_lesson.slug == lesson_slug) &
        (db.learning_lesson.language == language) &
        (db.learning_lesson.is_active == True) &
        (db.learning_lesson.is_published == True)
    ).select().first()


def _get_mission_by_slug(mission_slug, language):
    return db(
        (db.learning_mission.slug == mission_slug) &
        (db.learning_mission.language == language) &
        (db.learning_mission.is_active == True) &
        (db.learning_mission.is_published == True)
    ).select().first()


def _get_ordered_track_lessons(track_id, language):
    worlds = db(
        (db.learning_world.track_id == track_id) &
        (db.learning_world.language == language) &
        (db.learning_world.is_active == True)
    ).select(orderby=db.learning_world.sort_order)

    lessons = []
    for world in worlds:
        world_lessons = db(
            (db.learning_lesson.world_id == world.id) &
            (db.learning_lesson.language == language) &
            (db.learning_lesson.is_active == True) &
            (db.learning_lesson.is_published == True)
        ).select(orderby=db.learning_lesson.sort_order)

        for lesson in world_lessons:
            lessons.append((world, lesson))

    return lessons


def _get_or_create_lesson_progress(user_id, lesson_id):
    row = db(
        (db.lesson_progress.user_id == user_id) &
        (db.lesson_progress.lesson_id == lesson_id)
    ).select().first()

    if row:
        return row

    progress_id = db.lesson_progress.insert(
        user_id=user_id,
        lesson_id=lesson_id,
        status='not_started',
        attempts_count=0,
        best_score=0,
        last_score=0,
        xp_earned=0,
        time_spent_seconds=0,
        is_unlocked=True,
        is_current=False
    )
    return db.lesson_progress[progress_id]


def _mark_lesson_started(user_id, lesson):
    row = _get_or_create_lesson_progress(user_id, lesson.id)

    updates = dict(
        status='in_progress' if row.status == 'not_started' else row.status,
        last_viewed_on=request.now,
        last_attempt_on=row.last_attempt_on,
        modified_on=request.now
    )

    if not row.started_on:
        updates['started_on'] = request.now

    db(db.lesson_progress.id == row.id).update(**updates)

    return db.lesson_progress[row.id]


def _record_lesson_completion(user_id, lesson, score=100):
    score = max(0, min(100, int(score or 0)))
    xp_reward = lesson.xp_reward or 0

    row = _get_or_create_lesson_progress(user_id, lesson.id)
    attempt_number = (row.attempts_count or 0) + 1

    result_status = 'success' if score >= 80 else 'partial'

    db.lesson_attempt.insert(
        user_id=user_id,
        lesson_id=lesson.id,
        lesson_progress_id=row.id,
        attempt_number=attempt_number,
        result_status=result_status,
        score=score,
        xp_earned=xp_reward if score >= 80 else 0,
        duration_seconds=0,
        raw_payload='',
        feedback_snapshot='',
        attempted_on=request.now
    )

    new_status = 'in_progress'
    completed_on = row.completed_on
    xp_earned = row.xp_earned or 0

    if score >= 80:
        new_status = 'completed'
        if score >= 95:
            new_status = 'mastered'
        if not completed_on:
            completed_on = request.now
        xp_earned += xp_reward

    db(db.lesson_progress.id == row.id).update(
        status=new_status,
        attempts_count=attempt_number,
        best_score=max(row.best_score or 0, score),
        last_score=score,
        xp_earned=xp_earned,
        last_attempt_on=request.now,
        last_viewed_on=request.now,
        completed_on=completed_on,
        modified_on=request.now
    )

    mappings = db(
        db.learning_lesson_skill.lesson_id == lesson.id
    ).select()

    for mapping in mappings:
        skill_row = db(
            (db.skill_progress.user_id == user_id) &
            (db.skill_progress.skill_id == mapping.skill_id)
        ).select().first()

        if not skill_row:
            skill_id = db.skill_progress.insert(
                user_id=user_id,
                skill_id=mapping.skill_id,
                status='locked',
                mastery_percent=0,
                evidence_count=0,
                successful_uses_count=0
            )
            skill_row = db.skill_progress[skill_id]

        mastery = skill_row.mastery_percent or 0
        if score >= 60:
            mastery = min(100, mastery + 20)

        status = 'learning'
        unlocked_on = skill_row.unlocked_on
        mastered_on = skill_row.mastered_on

        if mastery > 0 and not unlocked_on:
            unlocked_on = request.now
            status = 'unlocked'

        if mastery >= 100:
            status = 'mastered'
            if not mastered_on:
                mastered_on = request.now
        elif mastery >= 60:
            status = 'unlocked'

        db(db.skill_progress.id == skill_row.id).update(
            status=status,
            mastery_percent=mastery,
            evidence_count=(skill_row.evidence_count or 0) + 1,
            successful_uses_count=(skill_row.successful_uses_count or 0) + (1 if score >= 80 else 0),
            unlocked_on=unlocked_on,
            mastered_on=mastered_on,
            last_practiced_on=request.now,
            modified_on=request.now
        )


def _sync_user_progress_summary(user_id, language):
    progress = _ensure_user_progress(user_id)

    total_xp = 0
    completed_lessons_count = db(
        (db.lesson_progress.user_id == user_id) &
        (db.lesson_progress.status.belongs(['completed', 'mastered']))
    ).count()

    completed_missions_count = db(
        (db.mission_progress.user_id == user_id) &
        (db.mission_progress.status == 'completed')
    ).count()

    unlocked_skills_count = db(
        (db.skill_progress.user_id == user_id) &
        (db.skill_progress.status.belongs(['unlocked', 'mastered']))
    ).count()

    lesson_xp_rows = db(db.lesson_progress.user_id == user_id).select(db.lesson_progress.xp_earned)
    mission_xp_rows = db(db.mission_progress.user_id == user_id).select(db.mission_progress.xp_earned)

    total_xp = sum([(r.xp_earned or 0) for r in lesson_xp_rows]) + sum([(r.xp_earned or 0) for r in mission_xp_rows])

    track = _get_track_by_slug('core', language)
    current_world_slug = progress.current_world_slug
    current_lesson_slug = progress.current_lesson_slug
    current_track = 'core'

    if track:
        ordered = _get_ordered_track_lessons(track.id, language)
        ordered_lessons = [lesson for world, lesson in ordered]

        next_lesson = None
        for world, lesson in ordered:
            lp = db(
                (db.lesson_progress.user_id == user_id) &
                (db.lesson_progress.lesson_id == lesson.id)
            ).select().first()

            if not lp or lp.status not in ('completed', 'mastered'):
                next_lesson = (world, lesson)
                break

        if next_lesson:
            current_world_slug = next_lesson[0].slug
            current_lesson_slug = next_lesson[1].slug
        elif ordered:
            current_world_slug = ordered[-1][0].slug
            current_lesson_slug = ordered[-1][1].slug

    db(db.user_progress.id == progress.id).update(
        total_xp=total_xp,
        completed_lessons_count=completed_lessons_count,
        completed_missions_count=completed_missions_count,
        unlocked_skills_count=unlocked_skills_count,
        current_world_slug=current_world_slug,
        current_lesson_slug=current_lesson_slug,
        current_track=current_track,
        first_lesson_started=(completed_lessons_count > 0 or progress.first_lesson_started),
        first_mission_completed=(completed_missions_count > 0 or progress.first_mission_completed),
        modified_on=request.now
    )

    return db.user_progress[progress.id]


def index():
    redirect(URL('learning', 'track', args=['core']))


def track():
    user = _require_login()
    language = _user_language(user)
    progress = _ensure_user_progress(user.id)

    track_slug = request.args(0) or 'core'
    track = _get_track_by_slug(track_slug, language)
    if not track:
        raise HTTP(404)

    worlds = db(
        (db.learning_world.track_id == track.id) &
        (db.learning_world.language == language) &
        (db.learning_world.is_active == True)
    ).select(orderby=db.learning_world.sort_order)

    world_ids = [w.id for w in worlds]
    lessons_by_world = {}

    if world_ids:
        lessons = db(
            (db.learning_lesson.world_id.belongs(world_ids)) &
            (db.learning_lesson.language == language) &
            (db.learning_lesson.is_active == True) &
            (db.learning_lesson.is_published == True)
        ).select(orderby=[db.learning_lesson.world_id, db.learning_lesson.sort_order])

        for lesson in lessons:
            lessons_by_world.setdefault(lesson.world_id, []).append(lesson)

    progress_rows = db(
        db.lesson_progress.user_id == user.id
    ).select()

    progress_by_lesson_id = {row.lesson_id: row for row in progress_rows}

    current_slug = progress.current_lesson_slug
    world_cards = []

    for world in worlds:
        lesson_items = []
        total_lessons = len(lessons_by_world.get(world.id, []))
        completed_count = 0

        for lesson in lessons_by_world.get(world.id, []):
            lp = progress_by_lesson_id.get(lesson.id)
            status = 'locked'

            if lp and lp.status in ('completed', 'mastered'):
                status = 'done'
                completed_count += 1
            elif lesson.slug == current_slug:
                status = 'current'
            elif not lp and total_lessons and completed_count == 0 and lesson.sort_order == 1 and world.sort_order == 1:
                status = 'current'

            lesson_items.append(dict(
                lesson=lesson,
                progress=lp,
                ui_state=status
            ))

        world_percent = int((completed_count * 100.0) / total_lessons) if total_lessons else 0

        world_cards.append(dict(
            world=world,
            lessons=lesson_items,
            completed_count=completed_count,
            total_lessons=total_lessons,
            progress_percent=world_percent
        ))

    response.title = track.title
    response.subtitle = track.subtitle or T('Path')

    return dict(
        track=track,
        world_cards=world_cards,
        progress=progress,
        language=language
    )


def lesson():
    user = _require_login()
    language = _user_language(user)

    lesson_slug = request.args(0)
    if not lesson_slug:
        raise HTTP(404)

    lesson = _get_lesson_by_slug(lesson_slug, language)
    if not lesson:
        raise HTTP(404)

    lesson_progress = _mark_lesson_started(user.id, lesson)

    world = db.learning_world[lesson.world_id]
    track = db.learning_track[world.track_id] if world else None

    ordered = _get_ordered_track_lessons(track.id, language) if track else []
    ordered_lessons = [l for w, l in ordered]
    lesson_ids = [l.id for l in ordered_lessons]

    prev_lesson = None
    next_lesson = None
    if lesson.id in lesson_ids:
        idx = lesson_ids.index(lesson.id)
        if idx > 0:
            prev_lesson = ordered_lessons[idx - 1]
        if idx < len(lesson_ids) - 1:
            next_lesson = ordered_lessons[idx + 1]

    skill_links = db(
        db.learning_lesson_skill.lesson_id == lesson.id
    ).select()

    skill_ids = [row.skill_id for row in skill_links]
    skills = []
    if skill_ids:
        skills = db(
            (db.learning_skill.id.belongs(skill_ids)) &
            (db.learning_skill.language == language) &
            (db.learning_skill.is_active == True)
        ).select(orderby=db.learning_skill.sort_order)

    prompts = db(
        (db.prompt_library.owner_type == 'system') &
        (db.prompt_library.visibility == 'course') &
        (db.prompt_library.language == language) &
        (db.prompt_library.lesson_id == lesson.id) &
        (db.prompt_library.is_active == True)
    ).select(orderby=db.prompt_library.sort_order)

    response.title = lesson.title
    response.subtitle = world.title if world else T('Lesson')

    return dict(
        lesson=lesson,
        lesson_progress=lesson_progress,
        world=world,
        track=track,
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
        skills=skills,
        prompts=prompts
    )


def complete_lesson():
    user = _require_login()
    language = _user_language(user)

    if request.env.request_method != 'POST':
        redirect(URL('learning', 'track', args=['core']))

    lesson_slug = request.args(0) or request.post_vars.lesson_slug
    lesson = _get_lesson_by_slug(lesson_slug, language)
    if not lesson:
        session.flash = T("Lesson not found.")
        redirect(URL('learning', 'track', args=['core']))

    score = request.post_vars.score or 100
    _record_lesson_completion(user.id, lesson, score=score)
    _sync_user_progress_summary(user.id, language)

    session.flash = T("Lesson completed.")
    redirect(URL('learning', 'lesson', args=[lesson.slug]))


def mission():
    user = _require_login()
    language = _user_language(user)

    mission_slug = request.args(0)
    if not mission_slug:
        raise HTTP(404)

    mission = _get_mission_by_slug(mission_slug, language)
    if not mission:
        raise HTTP(404)

    row = db(
        (db.mission_progress.user_id == user.id) &
        (db.mission_progress.mission_id == mission.id)
    ).select().first()

    if not row:
        progress_id = db.mission_progress.insert(
            user_id=user.id,
            mission_id=mission.id,
            status='not_started',
            score=0,
            xp_earned=0
        )
        row = db.mission_progress[progress_id]

    if request.env.request_method == 'POST':
        submission_text = (request.post_vars.submission_text or '').strip()

        if submission_text:
            status = 'submitted'
            completed_on = row.completed_on
            xp_earned = row.xp_earned or 0

            db(db.mission_progress.id == row.id).update(
                status=status,
                submission_text=submission_text,
                submitted_on=request.now,
                last_updated_on=request.now,
                modified_on=request.now
            )

            session.flash = T("Mission submitted.")
            redirect(URL('learning', 'mission', args=[mission.slug]))
        else:
            response.flash = T("Please add an answer before submitting.")

    related_prompts = db(
        (db.prompt_library.owner_type == 'system') &
        (db.prompt_library.visibility == 'course') &
        (db.prompt_library.language == language) &
        (db.prompt_library.is_active == True) &
        (
            (db.prompt_library.mission_id == mission.id) |
            (db.prompt_library.prompt_type == 'workflow')
        )
    ).select(orderby=db.prompt_library.sort_order)

    response.title = mission.title
    response.subtitle = T('Mission')

    return dict(
        mission=mission,
        mission_progress=row,
        related_prompts=related_prompts
    )


def library():
    user = _require_login()
    language = _user_language(user)

    course_prompts = db(
        (db.prompt_library.owner_type == 'system') &
        (db.prompt_library.visibility == 'course') &
        (db.prompt_library.language == language) &
        (db.prompt_library.is_active == True)
    ).select(orderby=db.prompt_library.sort_order)

    user_prompts = db(
        (db.prompt_library.owner_type == 'user') &
        (db.prompt_library.user_id == user.id) &
        (db.prompt_library.is_active == True)
    ).select(orderby=~db.prompt_library.modified_on)

    response.title = T('Library')
    response.subtitle = T('Course prompts and personal prompts')

    return dict(
        course_prompts=course_prompts,
        user_prompts=user_prompts,
        language=language
    )



LESSON_INTERACTIONS = {
    'ce-que-claude-sait-bien-faire': {
        'key': 'strong_use_case',
        'prompt': "Laquelle de ces tâches est la plus adaptée à Claude ?",
        'helper': "Choisis le cas où Claude aide surtout à structurer, reformuler ou synthétiser.",
        'options': [
            {'value': 'medical', 'label': "Donner un diagnostic médical définitif"},
            {'value': 'summary', 'label': "Structurer et résumer des notes brouillon"},
            {'value': 'legal', 'label': "Valider seul une clause contractuelle finale"},
            {'value': 'compliance', 'label': "Garantir une conformité réglementaire sans revue humaine"},
        ],
        'correct_answer': 'summary',
        'success_title': "Bien vu",
        'success_explanation': "Claude est très utile pour transformer de l’information brute en sortie plus claire et plus exploitable.",
        'error_title': "Pas tout à fait",
        'error_explanation': "Le meilleur cas d’usage ici est la structuration et le résumé de notes brouillon. Claude est fort pour organiser et reformuler, pas pour garantir seul un diagnostic ou une conformité.",
        'takeaway': "Claude est fort pour expliquer, structurer, reformuler et synthétiser."
    },
    'ce-que-claude-ne-garantit-pas': {
        'key': 'verification_risk',
        'prompt': "Laquelle de ces demandes exige la vérification la plus forte ?",
        'helper': "Choisis la tâche où une erreur aurait les conséquences les plus élevées.",
        'options': [
            {'value': 'email', 'label': "Rédiger un email de relance"},
            {'value': 'summary', 'label': "Résumer un article général"},
            {'value': 'legal', 'label': "Fournir une clause juridique prête à signer"},
            {'value': 'ideas', 'label': "Proposer des idées de contenu"},
        ],
        'correct_answer': 'legal',
        'success_title': "Exact",
        'success_explanation': "Une clause juridique est un cas à fort risque. Une réponse fluide ou convaincante ne suffit pas : elle doit être vérifiée par une source ou un expert adapté.",
        'error_title': "Pas tout à fait",
        'error_explanation': "La clause juridique est l’usage le plus risqué ici. C’est précisément le type de réponse où la vérification forte est indispensable.",
        'takeaway': "Plus le coût d’erreur est élevé, plus la vérification doit être forte."
    },
    'ajouter-le-bon-contexte': {
        'key': 'context_block',
        'prompt': "Quel élément de contexte est le plus utile pour améliorer ce prompt : 'Rédige un email de suivi' ?",
        'helper': "Choisis l’information qui aide Claude à produire un email pertinent plutôt qu’un message générique.",
        'options': [
            {'value': 'weather', 'label': "La météo de la semaine"},
            {'value': 'recipient', 'label': "Le destinataire, le contexte commercial et l’objectif du suivi"},
            {'value': 'mood', 'label': "L’humeur approximative de l’auteur"},
            {'value': 'font', 'label': "La police utilisée dans le site web"},
        ],
        'correct_answer': 'recipient',
        'success_title': "Oui",
        'success_explanation': "Le destinataire, le contexte et l’objectif donnent à Claude le cadre nécessaire pour sortir du générique.",
        'error_title': "Essaie encore",
        'error_explanation': "Le bon contexte n’est pas décoratif. Il doit aider Claude à comprendre qui écrit, à qui, pourquoi et pour obtenir quel résultat.",
        'takeaway': "Sans contexte, Claude remplit les vides avec des hypothèses génériques."
    },
    'demander-le-bon-format-de-sortie': {
        'key': 'output_format',
        'prompt': "Quel format est le plus adapté pour comparer 3 options ?",
        'helper': "Choisis la structure la plus facile à lire et à exploiter rapidement.",
        'options': [
            {'value': 'story', 'label': "Une histoire courte"},
            {'value': 'table', 'label': "Un tableau"},
            {'value': 'sentence', 'label': "Une phrase simple"},
            {'value': 'image', 'label': "Une image"},
        ],
        'correct_answer': 'table',
        'success_title': "Excellent",
        'success_explanation': "Le tableau est le meilleur format pour aligner plusieurs options sur les mêmes critères et comparer rapidement.",
        'error_title': "Pas tout à fait",
        'error_explanation': "Quand tu dois comparer plusieurs options, le tableau est le format le plus directement exploitable.",
        'takeaway': "Le bon format économise du temps de retraitement."
    }
}


def _get_interaction_for_lesson(lesson_slug, language=None):
    # Pour le MVP, les interactions sont définies par slug
    return LESSON_INTERACTIONS.get(lesson_slug)


def validate_lesson_answer_htmx():
    user = _require_login()
    language = _user_language(user)

    if request.env.request_method != 'POST':
        raise HTTP(405)

    lesson_slug = request.args(0)
    if not lesson_slug:
        raise HTTP(404)

    lesson = _get_lesson_by_slug(lesson_slug, language)
    if not lesson:
        raise HTTP(404)

    interaction = _get_interaction_for_lesson(lesson.slug, language)
    if not interaction:
        raise HTTP(404)

    user_answer = (request.post_vars.answer or '').strip()
    is_correct = user_answer == interaction.get('correct_answer')

    response.headers['HX-Trigger'] = json.dumps({
        "app:toast": {
            "message": "Bonne réponse." if is_correct else "Essaie encore.",
            "kind": "success" if is_correct else "warning"
        }
    })

    return response.render('learning/_lesson_feedback.html', dict(
        lesson=lesson,
        interaction=interaction,
        is_correct=is_correct,
        user_answer=user_answer
    ))