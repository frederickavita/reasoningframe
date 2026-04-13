# -*- coding: utf-8 -*-

# Suppression de "from gluon import current" et "db = current.db"

SUPPORTED_LANGUAGES = ['fr', 'en', 'es']

# =========================================================
# Generic Helpers
# =========================================================

def _first_or_none(db, query):
    return db(query).select(limitby=(0, 1)).first()


def _upsert(db, table, query, values):
    row = _first_or_none(db, query)
    if row:
        row.update_record(**values)
        return row.id
    return table.insert(**values)


def _get_track_id(db, content_key, language):
    row = _first_or_none(db,
        (db.learning_track.content_key == content_key) &
        (db.learning_track.language == language)
    )
    return row.id if row else None


def _get_world_id(db, content_key, language):
    row = _first_or_none(db,
        (db.learning_world.content_key == content_key) &
        (db.learning_world.language == language)
    )
    return row.id if row else None


def _get_skill_id(db, content_key, language):
    row = _first_or_none(db,
        (db.learning_skill.content_key == content_key) &
        (db.learning_skill.language == language)
    )
    return row.id if row else None


def _get_lesson_id(db, content_key, language):
    row = _first_or_none(db,
        (db.learning_lesson.content_key == content_key) &
        (db.learning_lesson.language == language)
    )
    return row.id if row else None


def _get_mission_id(db, content_key, language):
    row = _first_or_none(db,
        (db.learning_mission.content_key == content_key) &
        (db.learning_mission.language == language)
    )
    return row.id if row else None


# =========================================================
# Catalog Upserts
# =========================================================

def upsert_track(db, content_key, slug, language, track_type, title,
                 subtitle='', description='', sort_order=1, is_active=True):
    return _upsert(
        db,
        db.learning_track,
        (db.learning_track.content_key == content_key) &
        (db.learning_track.language == language),
        dict(
            content_key=content_key,
            slug=slug,
            language=language,
            track_type=track_type,
            title=title,
            subtitle=subtitle,
            description=description,
            sort_order=sort_order,
            is_active=is_active,
        )
    )


def upsert_world(db, track_content_key, content_key, slug, language, title,
                 subtitle='', description='', sort_order=1,
                 estimated_lessons_count=0, is_active=True):
    track_id = _get_track_id(db, track_content_key, language)
    if not track_id:
        raise RuntimeError("Track not found: %s / %s" % (track_content_key, language))

    return _upsert(
        db,
        db.learning_world,
        (db.learning_world.content_key == content_key) &
        (db.learning_world.language == language),
        dict(
            track_id=track_id,
            content_key=content_key,
            slug=slug,
            language=language,
            title=title,
            subtitle=subtitle,
            description=description,
            sort_order=sort_order,
            estimated_lessons_count=estimated_lessons_count,
            is_active=is_active,
        )
    )


def upsert_skill(db, content_key, slug, language, category, title,
                 description='', sort_order=1, is_active=True):
    return _upsert(
        db,
        db.learning_skill,
        (db.learning_skill.content_key == content_key) &
        (db.learning_skill.language == language),
        dict(
            content_key=content_key,
            slug=slug,
            language=language,
            category=category,
            title=title,
            description=description,
            sort_order=sort_order,
            is_active=is_active,
        )
    )


def upsert_lesson(db, world_content_key, content_key, slug, language, lesson_type,
                  title, short_title='', hook_text='', objective='',
                  mini_concept='', takeaway='', estimated_minutes=4,
                  xp_reward=10, sort_order=1, is_published=True, is_active=True):
    world_id = _get_world_id(db, world_content_key, language)
    if not world_id:
        raise RuntimeError("World not found: %s / %s" % (world_content_key, language))

    return _upsert(
        db,
        db.learning_lesson,
        (db.learning_lesson.content_key == content_key) &
        (db.learning_lesson.language == language),
        dict(
            world_id=world_id,
            content_key=content_key,
            slug=slug,
            language=language,
            lesson_type=lesson_type,
            title=title,
            short_title=short_title,
            hook_text=hook_text,
            objective=objective,
            mini_concept=mini_concept,
            takeaway=takeaway,
            estimated_minutes=estimated_minutes,
            xp_reward=xp_reward,
            sort_order=sort_order,
            is_published=is_published,
            is_active=is_active,
        )
    )


def upsert_lesson_skill(db, lesson_content_key, skill_content_key, language, weight=1):
    lesson_id = _get_lesson_id(db, lesson_content_key, language)
    skill_id = _get_skill_id(db, skill_content_key, language)

    if not lesson_id:
        raise RuntimeError("Lesson not found: %s / %s" % (lesson_content_key, language))
    if not skill_id:
        raise RuntimeError("Skill not found: %s / %s" % (skill_content_key, language))

    return _upsert(
        db,
        db.learning_lesson_skill,
        (db.learning_lesson_skill.lesson_id == lesson_id) &
        (db.learning_lesson_skill.skill_id == skill_id),
        dict(
            lesson_id=lesson_id,
            skill_id=skill_id,
            weight=weight,
        )
    )


def upsert_mission(db, track_content_key, content_key, slug, language, title,
                   brief='', success_criteria='', estimated_minutes=10,
                   xp_reward=50, sort_order=1, is_published=True, is_active=True):
    track_id = _get_track_id(db, track_content_key, language)
    if not track_id:
        raise RuntimeError("Track not found: %s / %s" % (track_content_key, language))

    return _upsert(
        db,
        db.learning_mission,
        (db.learning_mission.content_key == content_key) &
        (db.learning_mission.language == language),
        dict(
            track_id=track_id,
            content_key=content_key,
            slug=slug,
            language=language,
            title=title,
            brief=brief,
            success_criteria=success_criteria,
            estimated_minutes=estimated_minutes,
            xp_reward=xp_reward,
            sort_order=sort_order,
            is_published=is_published,
            is_active=is_active,
        )
    )


def upsert_prompt(db, owner_type, visibility, language, prompt_type, title,
                  prompt_text, description='', content_key='', slug='',
                  input_template='', expected_output='',
                  lesson_content_key=None, mission_content_key=None,
                  tags_csv='', sort_order=1, user_id=None, is_active=True):
    lesson_id = _get_lesson_id(db, lesson_content_key, language) if lesson_content_key else None
    mission_id = _get_mission_id(db, mission_content_key, language) if mission_content_key else None

    if owner_type == 'system':
        query = (
            (db.prompt_library.owner_type == 'system') &
            (db.prompt_library.content_key == content_key) &
            (db.prompt_library.language == language)
        )
    else:
        # for seed, we only manage system prompts here
        raise RuntimeError("This seed only handles system prompts.")

    return _upsert(
        db,
        db.prompt_library,
        query,
        dict(
            user_id=user_id,
            owner_type=owner_type,
            visibility=visibility,
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
            is_active=is_active,
        )
    )


# =========================================================
# MVP Data
# =========================================================
# ... The content translations (TRACK_TRANSLATIONS, WORLD_TRANSLATIONS, etc.) remain unchanged.
# (To save space, assume the large dictionaries you provided are right here)

TRACK_TRANSLATIONS = {
    'fr': {
        'core': {
            'title': 'Parcours fondamental Claude',
            'subtitle': 'Apprends Claude par micro-leçons interactives',
            'description': 'Parcours principal pour comprendre Claude, bien prompter, itérer et travailler avec fiabilité.'
        },
        'solopreneur': {
            'title': 'Track Solopreneur',
            'subtitle': 'Claude pour la productivité indépendante',
            'description': 'Applique Claude à tes emails, résumés, idées et mini-workflows.'
        }
    },
    'en': {
        'core': {
            'title': 'Claude Fundamentals Track',
            'subtitle': 'Learn Claude through interactive micro-lessons',
            'description': 'Core path to understand Claude, prompt well, iterate, and use it reliably.'
        },
        'solopreneur': {
            'title': 'Solopreneur Track',
            'subtitle': 'Claude for independent productivity',
            'description': 'Use Claude for emails, summaries, ideas, and mini-workflows.'
        }
    },
    'es': {
        'core': {
            'title': 'Ruta fundamental de Claude',
            'subtitle': 'Aprende Claude con microlecciones interactivas',
            'description': 'Ruta principal para entender Claude, escribir buenos prompts, iterar y usarlo con fiabilidad.'
        },
        'solopreneur': {
            'title': 'Track Solopreneur',
            'subtitle': 'Claude para productividad independiente',
            'description': 'Usa Claude para correos, resúmenes, ideas y mini-workflows.'
        }
    }
}

WORLD_TRANSLATIONS = {
    'fr': [
        ('world_1_discover', 'world-1-discover', 'Découvrir Claude', 'Comprendre ses forces et ses limites'),
        ('world_2_prompting', 'world-2-prompting', 'Bien parler à Claude', 'Contexte, objectif, format, contraintes'),
        ('world_3_iteration', 'world-3-iteration', 'Itérer intelligemment', 'Améliorer au lieu de recommencer'),
        ('world_4_use_cases', 'world-4-use-cases', 'Cas universels', 'Résumé, email, brainstorming, structure'),
        ('world_5_reliability', 'world-5-reliability', 'Fiabilité et usage réel', 'Vérification, limites, workflow personnel'),
    ],
    'en': [
        ('world_1_discover', 'world-1-discover', 'Discover Claude', 'Understand strengths and limitations'),
        ('world_2_prompting', 'world-2-prompting', 'Talk to Claude well', 'Context, goal, format, constraints'),
        ('world_3_iteration', 'world-3-iteration', 'Iterate smartly', 'Improve instead of restarting'),
        ('world_4_use_cases', 'world-4-use-cases', 'Universal use cases', 'Summary, email, brainstorming, structure'),
        ('world_5_reliability', 'world-5-reliability', 'Reliability and real use', 'Verification, limits, personal workflow'),
    ],
    'es': [
        ('world_1_discover', 'world-1-discover', 'Descubrir Claude', 'Entender fortalezas y límites'),
        ('world_2_prompting', 'world-2-prompting', 'Hablar bien con Claude', 'Contexto, objetivo, formato, restricciones'),
        ('world_3_iteration', 'world-3-iteration', 'Iterar inteligentemente', 'Mejorar en lugar de reiniciar'),
        ('world_4_use_cases', 'world-4-use-cases', 'Casos universales', 'Resumen, email, ideas, estructura'),
        ('world_5_reliability', 'world-5-reliability', 'Fiabilidad y uso real', 'Verificación, límites y workflow personal'),
    ]
}


SKILL_TRANSLATIONS = {
    'fr': [
        ('skill_use_claude_well', 'use-claude-well', 'fundamentals', 'Identifier les bons usages de Claude'),
        ('skill_understand_limits', 'understand-limits', 'fundamentals', 'Comprendre les limites de Claude'),
        ('skill_collaboration_mindset', 'collaboration-mindset', 'fundamentals', 'Utiliser Claude comme collaborateur'),
        ('skill_first_clear_request', 'first-clear-request', 'fundamentals', 'Formuler une première demande claire'),
        ('skill_add_context', 'add-context', 'prompting', 'Ajouter le bon contexte'),
        ('skill_define_goal', 'define-goal', 'prompting', 'Formuler un objectif net'),
        ('skill_choose_format', 'choose-format', 'prompting', 'Choisir le bon format de sortie'),
        ('skill_use_constraints', 'use-constraints', 'prompting', 'Poser des contraintes utiles'),
        ('skill_iterate', 'iterate', 'iteration', 'Traiter la première réponse comme un brouillon'),
        ('skill_targeted_revision', 'targeted-revision', 'iteration', 'Réviser avec une consigne ciblée'),
        ('skill_use_examples', 'use-examples', 'iteration', 'Guider Claude avec un exemple'),
        ('skill_adapt_output', 'adapt-output', 'iteration', 'Adapter ton, longueur et détail'),
        ('skill_summarize', 'summarize', 'use_cases', 'Résumer sans perdre l’essentiel'),
        ('skill_write_email', 'write-email', 'use_cases', 'Rédiger un email utile'),
        ('skill_brainstorm', 'brainstorm', 'use_cases', 'Brainstormer sans banalités'),
        ('skill_structure_notes', 'structure-notes', 'use_cases', 'Structurer des notes brouillon'),
        ('skill_detect_hallucination', 'detect-hallucination', 'reliability', 'Repérer une hallucination probable'),
        ('skill_verify_by_risk', 'verify-by-risk', 'reliability', 'Vérifier selon le niveau de risque'),
        ('skill_ask_for_sources', 'ask-for-sources', 'reliability', 'Demander sources, raisonnement et limites'),
        ('skill_build_workflow', 'build-workflow', 'workflow', 'Construire un mini-workflow personnel'),
    ],
    'en': [
        ('skill_use_claude_well', 'use-claude-well', 'fundamentals', 'Identify strong Claude use cases'),
        ('skill_understand_limits', 'understand-limits', 'fundamentals', 'Understand Claude limitations'),
        ('skill_collaboration_mindset', 'collaboration-mindset', 'fundamentals', 'Use Claude as a collaborator'),
        ('skill_first_clear_request', 'first-clear-request', 'fundamentals', 'Write a clear first request'),
        ('skill_add_context', 'add-context', 'prompting', 'Add the right context'),
        ('skill_define_goal', 'define-goal', 'prompting', 'Define a clear goal'),
        ('skill_choose_format', 'choose-format', 'prompting', 'Choose the right output format'),
        ('skill_use_constraints', 'use-constraints', 'prompting', 'Add useful constraints'),
        ('skill_iterate', 'iterate', 'iteration', 'Treat the first answer as a draft'),
        ('skill_targeted_revision', 'targeted-revision', 'iteration', 'Revise with a targeted instruction'),
        ('skill_use_examples', 'use-examples', 'iteration', 'Guide Claude with an example'),
        ('skill_adapt_output', 'adapt-output', 'iteration', 'Adapt tone, length and detail'),
        ('skill_summarize', 'summarize', 'use_cases', 'Summarize without losing the core meaning'),
        ('skill_write_email', 'write-email', 'use_cases', 'Write a useful email'),
        ('skill_brainstorm', 'brainstorm', 'use_cases', 'Brainstorm without generic ideas'),
        ('skill_structure_notes', 'structure-notes', 'use_cases', 'Turn messy notes into structure'),
        ('skill_detect_hallucination', 'detect-hallucination', 'reliability', 'Spot a likely hallucination'),
        ('skill_verify_by_risk', 'verify-by-risk', 'reliability', 'Verify according to risk'),
        ('skill_ask_for_sources', 'ask-for-sources', 'reliability', 'Ask for sources, reasoning and limits'),
        ('skill_build_workflow', 'build-workflow', 'workflow', 'Build a small personal workflow'),
    ],
    'es': [
        ('skill_use_claude_well', 'use-claude-well', 'fundamentals', 'Identificar buenos usos de Claude'),
        ('skill_understand_limits', 'understand-limits', 'fundamentals', 'Comprender los límites de Claude'),
        ('skill_collaboration_mindset', 'collaboration-mindset', 'fundamentals', 'Usar Claude como colaborador'),
        ('skill_first_clear_request', 'first-clear-request', 'fundamentals', 'Formular una primera petición clara'),
        ('skill_add_context', 'add-context', 'prompting', 'Añadir el contexto adecuado'),
        ('skill_define_goal', 'define-goal', 'prompting', 'Definir un objetivo claro'),
        ('skill_choose_format', 'choose-format', 'prompting', 'Elegir el formato de salida correcto'),
        ('skill_use_constraints', 'use-constraints', 'prompting', 'Añadir restricciones útiles'),
        ('skill_iterate', 'iterate', 'iteration', 'Tratar la primera respuesta como borrador'),
        ('skill_targeted_revision', 'targeted-revision', 'iteration', 'Revisar con una instrucción precisa'),
        ('skill_use_examples', 'use-examples', 'iteration', 'Guiar Claude con un ejemplo'),
        ('skill_adapt_output', 'adapt-output', 'iteration', 'Adaptar tono, longitud y detalle'),
        ('skill_summarize', 'summarize', 'use_cases', 'Resumir sin perder lo esencial'),
        ('skill_write_email', 'write-email', 'use_cases', 'Redactar un email útil'),
        ('skill_brainstorm', 'brainstorm', 'use_cases', 'Generar ideas sin banalidades'),
        ('skill_structure_notes', 'structure-notes', 'use_cases', 'Estructurar notas desordenadas'),
        ('skill_detect_hallucination', 'detect-hallucination', 'reliability', 'Detectar una alucinación probable'),
        ('skill_verify_by_risk', 'verify-by-risk', 'reliability', 'Verificar según el nivel de riesgo'),
        ('skill_ask_for_sources', 'ask-for-sources', 'reliability', 'Pedir fuentes, razonamiento y límites'),
        ('skill_build_workflow', 'build-workflow', 'workflow', 'Construir un mini-workflow personal'),
    ]
}


LESSONS_DATA = {
    'fr': [
        # world_1_discover
        ('world_1_discover', 'lesson_01_use_cases', 'ce-que-claude-sait-bien-faire', 'concept',
         'Ce que Claude sait bien faire', 'Bons usages',
         'Reconnaître les tâches où Claude aide vraiment.',
         'Comprendre les forces principales de Claude.',
         'Claude est surtout utile pour expliquer, structurer, reformuler, résumer et brainstormer.',
         'Claude améliore le travail intellectuel ; il ne remplace pas la validation critique.',
         1, 12, ['skill_use_claude_well']),
        ('world_1_discover', 'lesson_02_limits', 'ce-que-claude-ne-garantit-pas', 'concept',
         'Ce que Claude ne garantit pas', 'Limites',
         'Comprendre qu’une réponse fluide n’est pas toujours fiable.',
         'Identifier les cas où il faut vérifier fortement.',
         'Une réponse IA peut sembler crédible tout en étant fausse ou incomplète.',
         'La fluidité d’une réponse ne suffit jamais à juger sa fiabilité.',
         2, 12, ['skill_understand_limits']),
        ('world_1_discover', 'lesson_03_collaboration', 'penser-claude-comme-collaborateur', 'concept',
         'Penser Claude comme collaborateur', 'Collaborateur',
         'Utiliser Claude comme partenaire de réflexion.',
         'Adopter un mindset actif et critique.',
         'La valeur maximale vient quand l’utilisateur guide, juge, corrige et itère.',
         'Claude est plus utile comme partenaire de travail que comme machine à réponses finales.',
         3, 12, ['skill_collaboration_mindset']),
        ('world_1_discover', 'lesson_04_first_request', 'faire-sa-premiere-demande-utile', 'exercise',
         'Faire sa première demande utile', 'Première demande',
         'Transformer une intention floue en demande exploitable.',
         'Passer d’une demande vague à une demande actionnable.',
         'Une bonne demande contient contexte, objectif, audience/usage et résultat attendu.',
         'Une bonne demande réduit immédiatement les allers-retours.',
         4, 14, ['skill_first_clear_request']),

        # world_2_prompting
        ('world_2_prompting', 'lesson_05_context', 'ajouter-le-bon-contexte', 'exercise',
         'Ajouter le bon contexte', 'Contexte',
         'Comprendre pourquoi le contexte améliore la réponse.',
         'Fournir le minimum de contexte utile.',
         'Le contexte donne à Claude le cadre : qui parle, pour quoi faire, dans quelle situation.',
         'Sans contexte, Claude remplit les vides avec du générique.',
         1, 14, ['skill_add_context']),
        ('world_2_prompting', 'lesson_06_goal', 'formuler-un-objectif-net', 'exercise',
         'Formuler un objectif net', 'Objectif',
         'Demander un résultat précis plutôt qu’une aide vague.',
         'Exprimer un objectif observable et actionnable.',
         'Un bon objectif décrit le livrable attendu, pas juste le sujet.',
         'Claude répond mieux quand tu demandes un résultat visible.',
         2, 14, ['skill_define_goal']),
        ('world_2_prompting', 'lesson_07_format', 'demander-le-bon-format-de-sortie', 'exercise',
         'Demander le bon format de sortie', 'Format',
         'Associer un besoin au bon format de réponse.',
         'Choisir une structure directement exploitable.',
         'Un bon format réduit le retraitement et accélère l’usage réel.',
         'Le format est un raccourci vers une réponse utile.',
         3, 14, ['skill_choose_format']),
        ('world_2_prompting', 'lesson_08_constraints', 'poser-des-contraintes-utiles', 'exercise',
         'Poser des contraintes utiles', 'Contraintes',
         'Cadrer la sortie sans créer de contradictions.',
         'Ajouter longueur, ton, audience, périmètre.',
         'Les contraintes servent à guider ; trop peu = flou, trop = bruit.',
         'Les contraintes utiles améliorent la précision ; les contradictions créent du bruit.',
         4, 14, ['skill_use_constraints']),

        # world_3_iteration
        ('world_3_iteration', 'lesson_09_draft', 'la-premiere-reponse-est-un-brouillon', 'concept',
         'La première réponse est un brouillon', 'Brouillon',
         'Utiliser la première sortie comme point de départ.',
         'Adopter une posture d’amélioration progressive.',
         'La vraie qualité vient souvent de 1 à 3 itérations ciblées.',
         'La première réponse sert à diagnostiquer ce qu’il faut améliorer.',
         1, 14, ['skill_iterate']),
        ('world_3_iteration', 'lesson_10_revision', 'ameliorer-une-reponse-avec-une-consigne-ciblee', 'exercise',
         'Améliorer une réponse avec une consigne ciblée', 'Révision ciblée',
         'Apprendre à demander une amélioration précise.',
         'Formuler une demande de révision utile.',
         'Une bonne itération nomme le problème : trop long, trop vague, mauvais ton, mauvais format.',
         'Plus tu pointes le défaut, plus Claude peut corriger efficacement.',
         2, 14, ['skill_targeted_revision']),
        ('world_3_iteration', 'lesson_11_examples', 'utiliser-un-exemple-pour-guider-claude', 'exercise',
         'Utiliser un exemple pour guider Claude', 'Exemples',
         'Montrer qu’un bon exemple réduit l’ambiguïté.',
         'Savoir quand et comment fournir un exemple.',
         'Un exemple donne un modèle implicite de style, structure ou détail.',
         'Un exemple pertinent vaut souvent plus qu’une longue explication abstraite.',
         3, 14, ['skill_use_examples']),
        ('world_3_iteration', 'lesson_12_adapt_output', 'changer-ton-longueur-et-niveau-de-detail', 'exercise',
         'Changer ton, longueur et niveau de détail', 'Adapter la sortie',
         'Adapter une réponse à son contexte réel.',
         'Modifier un output sans repartir de zéro.',
         'Une même idée peut être transformée pour devenir plus courte, plus simple ou plus pro.',
         'L’utilité d’une réponse dépend souvent plus de son adaptation que de son contenu brut.',
         4, 14, ['skill_adapt_output']),

        # world_4_use_cases
        ('world_4_use_cases', 'lesson_13_summary', 'resumer-un-texte-sans-perdre-lessentiel', 'exercise',
         'Résumer un texte sans perdre l’essentiel', 'Résumé',
         'Produire une synthèse fidèle et exploitable.',
         'Obtenir un résumé sans déformation majeure.',
         'Un bon résumé conserve l’idée centrale, les points clés et la hiérarchie de l’information.',
         'Résumer, ce n’est pas raccourcir au hasard ; c’est préserver le sens essentiel.',
         1, 16, ['skill_summarize']),
        ('world_4_use_cases', 'lesson_14_email', 'rediger-un-email-utile', 'exercise',
         'Rédiger un email utile', 'Email',
         'Produire un email réutilisable rapidement.',
         'Structurer un prompt email efficace.',
         'Pour un bon email, il faut préciser qui écrit, à qui, pourquoi, le ton et l’action attendue.',
         'Un bon email est une sortie orientée action, pas juste un texte correct.',
         2, 16, ['skill_write_email']),
        ('world_4_use_cases', 'lesson_15_brainstorm', 'brainstormer-sans-obtenir-des-banalites', 'exercise',
         'Brainstormer sans obtenir des banalités', 'Brainstorm',
         'Générer des idées plus utiles que des réponses génériques.',
         'Cadrer une demande de brainstorming.',
         'Un brainstorming faible vient souvent d’un brief trop large.',
         'Claude brainstorme mieux quand tu définis un terrain de jeu clair.',
         3, 16, ['skill_brainstorm']),
        ('world_4_use_cases', 'lesson_16_structure', 'transformer-des-notes-brouillon-en-plan-clair', 'exercise',
         'Transformer des notes brouillon en plan clair', 'Structurer',
         'Passer d’un contenu brut à une structure exploitable.',
         'Convertir des notes en plan, checklist ou synthèse.',
         'Claude est très utile pour transformer des notes, idées ou brouillons en structure actionnable.',
         'La vraie valeur n’est pas juste de résumer, mais de rendre l’information exploitable.',
         4, 16, ['skill_structure_notes']),

        # world_5_reliability
        ('world_5_reliability', 'lesson_17_hallucination', 'reperer-une-hallucination-probable', 'exercise',
         'Repérer une hallucination probable', 'Hallucination',
         'Développer un réflexe de doute intelligent.',
         'Identifier les signaux d’une réponse possiblement fausse.',
         'Les signaux fréquents : précision excessive sans source, chiffres sortis de nulle part, certitude trop forte.',
         'Une hallucination convaincante se repère souvent par son excès d’assurance.',
         1, 18, ['skill_detect_hallucination']),
        ('world_5_reliability', 'lesson_18_verify', 'savoir-quand-verifier-absolument', 'exercise',
         'Savoir quand vérifier absolument', 'Vérification',
         'Hiérarchiser les usages selon le risque.',
         'Distinguer faible, moyen et fort besoin de vérification.',
         'Tous les usages n’ont pas le même coût d’erreur.',
         'Le bon réflexe n’est pas de tout vérifier pareil, mais de vérifier selon le risque.',
         2, 18, ['skill_verify_by_risk']),
        ('world_5_reliability', 'lesson_19_sources', 'demander-sources-raisonnement-et-limites', 'exercise',
         'Demander sources, raisonnement et limites', 'Transparence',
         'Obtenir une réponse plus transparente et plus vérifiable.',
         'Enrichir un prompt pour mieux cibler ce qu’il faut contrôler.',
         'On peut demander à Claude de distinguer faits, hypothèses, limites et points à vérifier.',
         'Une bonne réponse utile n’est pas seulement correcte ; elle est aussi lisible sur ses limites.',
         3, 18, ['skill_ask_for_sources']),
        ('world_5_reliability', 'lesson_20_workflow', 'construire-un-mini-workflow-personnel', 'mission_prep',
         'Construire un mini-workflow personnel', 'Workflow',
         'Passer d’un usage ponctuel à un usage répétable.',
         'Assembler une procédure simple réutilisable avec Claude.',
         'Un workflow contient un input clair, un prompt, un output attendu, un point de vérification et une fréquence.',
         'Le vrai niveau supérieur est de créer une méthode que tu peux répéter.',
         4, 20, ['skill_build_workflow']),
    ],
    'en': [
        ('world_1_discover', 'lesson_01_use_cases', 'what-claude-does-well', 'concept',
         'What Claude does well', 'Good use cases',
         'Recognize the tasks where Claude truly helps.',
         'Understand Claude’s main strengths.',
         'Claude is especially useful for explaining, structuring, rewriting, summarizing and brainstorming.',
         'Claude improves knowledge work; it does not replace critical validation.',
         1, 12, ['skill_use_claude_well']),
        ('world_1_discover', 'lesson_02_limits', 'what-claude-does-not-guarantee', 'concept',
         'What Claude does not guarantee', 'Limits',
         'Understand that a fluent answer is not always reliable.',
         'Identify cases that require strong verification.',
         'An AI answer can sound credible while still being false or incomplete.',
         'Fluency alone is never enough to judge reliability.',
         2, 12, ['skill_understand_limits']),
        ('world_1_discover', 'lesson_03_collaboration', 'think-of-claude-as-a-collaborator', 'concept',
         'Think of Claude as a collaborator', 'Collaborator',
         'Use Claude as a thinking partner.',
         'Adopt an active and critical mindset.',
         'Maximum value comes when the user guides, judges, corrects and iterates.',
         'Claude is more useful as a work partner than as a final-answer machine.',
         3, 12, ['skill_collaboration_mindset']),
        ('world_1_discover', 'lesson_04_first_request', 'make-your-first-useful-request', 'exercise',
         'Make your first useful request', 'First request',
         'Turn a vague intent into a usable request.',
         'Move from vague to actionable.',
         'A good request includes context, goal, audience/use case and expected output.',
         'A good request reduces back-and-forth immediately.',
         4, 14, ['skill_first_clear_request']),

        ('world_2_prompting', 'lesson_05_context', 'add-the-right-context', 'exercise',
         'Add the right context', 'Context',
         'Understand why context improves the answer.',
         'Provide the minimum useful context.',
         'Context gives Claude the frame: who is speaking, for what, in which situation.',
         'Without context, Claude fills the gaps with generic assumptions.',
         1, 14, ['skill_add_context']),
        ('world_2_prompting', 'lesson_06_goal', 'define-a-clear-goal', 'exercise',
         'Define a clear goal', 'Goal',
         'Ask for a precise result rather than vague help.',
         'Express an observable and actionable goal.',
         'A good goal describes the expected deliverable, not just the topic.',
         'Claude responds better when you ask for a visible result.',
         2, 14, ['skill_define_goal']),
        ('world_2_prompting', 'lesson_07_format', 'ask-for-the-right-output-format', 'exercise',
         'Ask for the right output format', 'Format',
         'Match a need with the best output format.',
         'Choose a structure that is directly usable.',
         'A good format reduces rework and accelerates real usage.',
         'Format is a shortcut to a useful answer.',
         3, 14, ['skill_choose_format']),
        ('world_2_prompting', 'lesson_08_constraints', 'add-useful-constraints', 'exercise',
         'Add useful constraints', 'Constraints',
         'Frame the output without creating contradictions.',
         'Add length, tone, audience and scope.',
         'Constraints guide the model; too few = blurry, too many = noisy.',
         'Useful constraints improve precision; contradictions create noise.',
         4, 14, ['skill_use_constraints']),

        ('world_3_iteration', 'lesson_09_draft', 'the-first-answer-is-a-draft', 'concept',
         'The first answer is a draft', 'Draft',
         'Use the first output as a starting point.',
         'Adopt a mindset of progressive improvement.',
         'Real quality often comes from 1 to 3 targeted iterations.',
         'The first answer helps diagnose what should improve.',
         1, 14, ['skill_iterate']),
        ('world_3_iteration', 'lesson_10_revision', 'improve-with-a-targeted-revision', 'exercise',
         'Improve with a targeted revision', 'Targeted revision',
         'Learn to ask for precise improvements.',
         'Write a useful revision request.',
         'A good iteration names the problem: too long, too vague, wrong tone, wrong format.',
         'The more precisely you point out the defect, the better Claude can fix it.',
         2, 14, ['skill_targeted_revision']),
        ('world_3_iteration', 'lesson_11_examples', 'use-an-example-to-guide-claude', 'exercise',
         'Use an example to guide Claude', 'Examples',
         'Show that a good example reduces ambiguity.',
         'Know when and how to provide an example.',
         'An example gives Claude an implicit model of style, structure or detail.',
         'A relevant example is often worth more than a long abstract explanation.',
         3, 14, ['skill_use_examples']),
        ('world_3_iteration', 'lesson_12_adapt_output', 'change-tone-length-and-detail', 'exercise',
         'Change tone, length and detail', 'Adapt output',
         'Adapt an answer to a real context of use.',
         'Modify an output without starting from scratch.',
         'The same idea can be transformed to become shorter, simpler or more professional.',
         'Usefulness often depends more on adaptation than on raw content.',
         4, 14, ['skill_adapt_output']),

        ('world_4_use_cases', 'lesson_13_summary', 'summarize-without-losing-the-core', 'exercise',
         'Summarize without losing the core', 'Summary',
         'Produce a faithful and usable summary.',
         'Get a summary without major distortion.',
         'A good summary preserves the central idea, key points and information hierarchy.',
         'Summarizing is not random shortening; it is preserving the essential meaning.',
         1, 16, ['skill_summarize']),
        ('world_4_use_cases', 'lesson_14_email', 'write-a-useful-email', 'exercise',
         'Write a useful email', 'Email',
         'Produce a reusable email quickly.',
         'Structure an effective email prompt.',
         'A good email prompt clarifies who writes, to whom, why, the tone and the expected action.',
         'A good email is action-oriented, not just correct text.',
         2, 16, ['skill_write_email']),
        ('world_4_use_cases', 'lesson_15_brainstorm', 'brainstorm-without-generic-ideas', 'exercise',
         'Brainstorm without generic ideas', 'Brainstorm',
         'Generate ideas that are more useful than generic outputs.',
         'Frame a brainstorming request.',
         'Weak brainstorming often comes from a brief that is too broad.',
         'Claude brainstorms better when you define a clear playground.',
         3, 16, ['skill_brainstorm']),
        ('world_4_use_cases', 'lesson_16_structure', 'turn-messy-notes-into-a-clear-plan', 'exercise',
         'Turn messy notes into a clear plan', 'Structure',
         'Turn raw content into a usable structure.',
         'Convert notes into a plan, checklist or summary.',
         'Claude is very useful for transforming notes, ideas or drafts into actionable structure.',
         'The real value is not only to summarize, but to make information actionable.',
         4, 16, ['skill_structure_notes']),

        ('world_5_reliability', 'lesson_17_hallucination', 'spot-a-likely-hallucination', 'exercise',
         'Spot a likely hallucination', 'Hallucination',
         'Develop a smart doubt reflex.',
         'Identify the signals of a possibly false answer.',
         'Frequent signals include over-precision without sources, numbers from nowhere, and too much certainty.',
         'A convincing hallucination often reveals itself through overconfidence.',
         1, 18, ['skill_detect_hallucination']),
        ('world_5_reliability', 'lesson_18_verify', 'know-when-to-verify', 'exercise',
         'Know when to verify', 'Verification',
         'Prioritize usage according to risk.',
         'Distinguish low, medium and high verification needs.',
         'Not all use cases have the same cost of error.',
         'The right reflex is not to verify everything equally, but to verify according to risk.',
         2, 18, ['skill_verify_by_risk']),
        ('world_5_reliability', 'lesson_19_sources', 'ask-for-sources-reasoning-and-limits', 'exercise',
         'Ask for sources, reasoning and limits', 'Transparency',
         'Get a more transparent and more verifiable answer.',
         'Enrich a prompt to better target what should be checked.',
         'You can ask Claude to distinguish facts, assumptions, limits and points to verify.',
         'A useful answer is not only correct; it is also clear about its limits.',
         3, 18, ['skill_ask_for_sources']),
        ('world_5_reliability', 'lesson_20_workflow', 'build-a-small-personal-workflow', 'mission_prep',
         'Build a small personal workflow', 'Workflow',
         'Move from one-off use to repeatable use.',
         'Assemble a simple reusable procedure with Claude.',
         'A workflow includes a clear input, a prompt, an expected output, a verification point and a frequency.',
         'The next level is not writing one good prompt once, but creating a method you can repeat.',
         4, 20, ['skill_build_workflow']),
    ],
    'es': [
        ('world_1_discover', 'lesson_01_use_cases', 'lo-que-claude-hace-bien', 'concept',
         'Lo que Claude hace bien', 'Buenos usos',
         'Reconocer las tareas donde Claude realmente ayuda.',
         'Comprender las principales fortalezas de Claude.',
         'Claude es especialmente útil para explicar, estructurar, reformular, resumir y generar ideas.',
         'Claude mejora el trabajo intelectual; no sustituye la validación crítica.',
         1, 12, ['skill_use_claude_well']),
        ('world_1_discover', 'lesson_02_limits', 'lo-que-claude-no-garantiza', 'concept',
         'Lo que Claude no garantiza', 'Límites',
         'Entender que una respuesta fluida no siempre es fiable.',
         'Identificar los casos que requieren verificación fuerte.',
         'Una respuesta de IA puede sonar creíble y aun así ser falsa o incompleta.',
         'La fluidez por sí sola nunca basta para juzgar la fiabilidad.',
         2, 12, ['skill_understand_limits']),
        ('world_1_discover', 'lesson_03_collaboration', 'pensar-en-claude-como-colaborador', 'concept',
         'Pensar en Claude como colaborador', 'Colaborador',
         'Usar Claude como compañero de reflexión.',
         'Adoptar una mentalidad activa y crítica.',
         'El máximo valor aparece cuando el usuario guía, juzga, corrige e itera.',
         'Claude es más útil como compañero de trabajo que como máquina de respuestas finales.',
         3, 12, ['skill_collaboration_mindset']),
        ('world_1_discover', 'lesson_04_first_request', 'hacer-una-primera-peticion-util', 'exercise',
         'Hacer una primera petición útil', 'Primera petición',
         'Transformar una intención vaga en una petición utilizable.',
         'Pasar de una petición vaga a una accionable.',
         'Una buena petición incluye contexto, objetivo, audiencia/uso y resultado esperado.',
         'Una buena petición reduce inmediatamente los ida y vuelta.',
         4, 14, ['skill_first_clear_request']),

        ('world_2_prompting', 'lesson_05_context', 'anadir-el-contexto-correcto', 'exercise',
         'Añadir el contexto correcto', 'Contexto',
         'Comprender por qué el contexto mejora la respuesta.',
         'Aportar el mínimo contexto útil.',
         'El contexto da a Claude el marco: quién habla, para qué y en qué situación.',
         'Sin contexto, Claude rellena los huecos con suposiciones genéricas.',
         1, 14, ['skill_add_context']),
        ('world_2_prompting', 'lesson_06_goal', 'formular-un-objetivo-claro', 'exercise',
         'Formular un objetivo claro', 'Objetivo',
         'Pedir un resultado preciso en lugar de ayuda vaga.',
         'Expresar un objetivo observable y accionable.',
         'Un buen objetivo describe el entregable esperado, no solo el tema.',
         'Claude responde mejor cuando pides un resultado visible.',
         2, 14, ['skill_define_goal']),
        ('world_2_prompting', 'lesson_07_format', 'pedir-el-formato-de-salida-correcto', 'exercise',
         'Pedir el formato de salida correcto', 'Formato',
         'Relacionar una necesidad con el mejor formato de salida.',
         'Elegir una estructura directamente utilizable.',
         'Un buen formato reduce retrabajo y acelera el uso real.',
         'El formato es un atajo hacia una respuesta útil.',
         3, 14, ['skill_choose_format']),
        ('world_2_prompting', 'lesson_08_constraints', 'anadir-restricciones-utiles', 'exercise',
         'Añadir restricciones útiles', 'Restricciones',
         'Guiar la salida sin crear contradicciones.',
         'Añadir longitud, tono, audiencia y alcance.',
         'Las restricciones guían al modelo; pocas = borroso, demasiadas = ruido.',
         'Las restricciones útiles mejoran la precisión; las contradicciones crean ruido.',
         4, 14, ['skill_use_constraints']),

        ('world_3_iteration', 'lesson_09_draft', 'la-primera-respuesta-es-un-borrador', 'concept',
         'La primera respuesta es un borrador', 'Borrador',
         'Usar la primera salida como punto de partida.',
         'Adoptar una mentalidad de mejora progresiva.',
         'La calidad real suele venir de 1 a 3 iteraciones dirigidas.',
         'La primera respuesta ayuda a diagnosticar qué debe mejorar.',
         1, 14, ['skill_iterate']),
        ('world_3_iteration', 'lesson_10_revision', 'mejorar-con-una-revision-dirigida', 'exercise',
         'Mejorar con una revisión dirigida', 'Revisión dirigida',
         'Aprender a pedir mejoras precisas.',
         'Redactar una solicitud de revisión útil.',
         'Una buena iteración nombra el problema: demasiado largo, demasiado vago, tono erróneo, formato incorrecto.',
         'Cuanto más precisamente señales el defecto, mejor podrá Claude corregirlo.',
         2, 14, ['skill_targeted_revision']),
        ('world_3_iteration', 'lesson_11_examples', 'usar-un-ejemplo-para-guiar-a-claude', 'exercise',
         'Usar un ejemplo para guiar a Claude', 'Ejemplos',
         'Mostrar que un buen ejemplo reduce la ambigüedad.',
         'Saber cuándo y cómo proporcionar un ejemplo.',
         'Un ejemplo da a Claude un modelo implícito de estilo, estructura o detalle.',
         'Un ejemplo relevante suele valer más que una explicación abstracta larga.',
         3, 14, ['skill_use_examples']),
        ('world_3_iteration', 'lesson_12_adapt_output', 'cambiar-tono-longitud-y-detalle', 'exercise',
         'Cambiar tono, longitud y detalle', 'Adaptar salida',
         'Adaptar una respuesta a un contexto real de uso.',
         'Modificar una salida sin empezar desde cero.',
         'La misma idea puede transformarse para ser más corta, más simple o más profesional.',
         'La utilidad suele depender más de la adaptación que del contenido bruto.',
         4, 14, ['skill_adapt_output']),

        ('world_4_use_cases', 'lesson_13_summary', 'resumir-sin-perder-lo-esencial', 'exercise',
         'Resumir sin perder lo esencial', 'Resumen',
         'Producir un resumen fiel y utilizable.',
         'Obtener un resumen sin distorsión importante.',
         'Un buen resumen conserva la idea central, los puntos clave y la jerarquía de la información.',
         'Resumir no es acortar al azar; es preservar el significado esencial.',
         1, 16, ['skill_summarize']),
        ('world_4_use_cases', 'lesson_14_email', 'redactar-un-email-util', 'exercise',
         'Redactar un email útil', 'Email',
         'Producir un email reutilizable rápidamente.',
         'Estructurar un prompt de email eficaz.',
         'Un buen prompt de email aclara quién escribe, a quién, por qué, el tono y la acción esperada.',
         'Un buen email está orientado a la acción, no solo a estar bien escrito.',
         2, 16, ['skill_write_email']),
        ('world_4_use_cases', 'lesson_15_brainstorm', 'generar-ideas-sin-banalidades', 'exercise',
         'Generar ideas sin banalidades', 'Brainstorm',
         'Generar ideas más útiles que respuestas genéricas.',
         'Enmarcar una solicitud de brainstorming.',
         'Un brainstorming débil suele venir de un brief demasiado amplio.',
         'Claude genera mejores ideas cuando defines un terreno de juego claro.',
         3, 16, ['skill_brainstorm']),
        ('world_4_use_cases', 'lesson_16_structure', 'convertir-notas-desordenadas-en-un-plan-claro', 'exercise',
         'Convertir notas desordenadas en un plan claro', 'Estructura',
         'Pasar de contenido bruto a estructura utilizable.',
         'Convertir notas en plan, checklist o síntesis.',
         'Claude es muy útil para transformar notas, ideas o borradores en estructura accionable.',
         'El verdadero valor no es solo resumir, sino volver la información accionable.',
         4, 16, ['skill_structure_notes']),

        ('world_5_reliability', 'lesson_17_hallucination', 'detectar-una-alucinacion-probable', 'exercise',
         'Detectar una alucinación probable', 'Alucinación',
         'Desarrollar una duda inteligente.',
         'Identificar señales de una respuesta posiblemente falsa.',
         'Señales frecuentes: precisión excesiva sin fuente, cifras inventadas, demasiada certeza.',
         'Una alucinación convincente suele delatarse por exceso de seguridad.',
         1, 18, ['skill_detect_hallucination']),
        ('world_5_reliability', 'lesson_18_verify', 'saber-cuando-verificar', 'exercise',
         'Saber cuándo verificar', 'Verificación',
         'Priorizar el uso según el riesgo.',
         'Distinguir necesidades de verificación baja, media y alta.',
         'No todos los usos tienen el mismo coste de error.',
         'El reflejo correcto no es verificar todo igual, sino verificar según el riesgo.',
         2, 18, ['skill_verify_by_risk']),
        ('world_5_reliability', 'lesson_19_sources', 'pedir-fuentes-razonamiento-y-limites', 'exercise',
         'Pedir fuentes, razonamiento y límites', 'Transparencia',
         'Obtener una respuesta más transparente y verificable.',
         'Enriquecer un prompt para enfocar mejor lo que debe comprobarse.',
         'Puedes pedir a Claude que distinga hechos, hipótesis, límites y puntos a verificar.',
         'Una respuesta útil no solo es correcta; también deja claras sus limitaciones.',
         3, 18, ['skill_ask_for_sources']),
        ('world_5_reliability', 'lesson_20_workflow', 'construir-un-mini-workflow-personal', 'mission_prep',
         'Construir un mini-workflow personal', 'Workflow',
         'Pasar de un uso puntual a uno repetible.',
         'Montar un procedimiento simple y reutilizable con Claude.',
         'Un workflow incluye una entrada clara, un prompt, una salida esperada, un punto de verificación y una frecuencia.',
         'El siguiente nivel no es escribir un buen prompt una vez, sino crear un método repetible.',
         4, 20, ['skill_build_workflow']),
    ]
}


MISSION_TRANSLATIONS = {
    'fr': [
        ('mission_01_long_doc', 'resumer-un-document-long', 'Résumer un document long',
         'Produis une synthèse claire et exploitable d’un contenu long.',
         'Fidélité, structure, concision'),
        ('mission_02_email', 'preparer-un-email-client-ou-manager', 'Préparer un email client ou manager',
         'Rédige un email prêt à envoyer avec bon ton et objectif clair.',
         'Contexte, clarté, ton, action attendue'),
        ('mission_03_workflow', 'construire-un-workflow-personnel', 'Construire un workflow personnel',
         'Transforme un besoin répétitif en procédure réutilisable avec Claude.',
         'Clarté des étapes, réutilisabilité, point de vérification'),
    ],
    'en': [
        ('mission_01_long_doc', 'summarize-a-long-document', 'Summarize a long document',
         'Produce a clear and usable synthesis of a long piece of content.',
         'Fidelity, structure, concision'),
        ('mission_02_email', 'prepare-a-client-or-manager-email', 'Prepare a client or manager email',
         'Write an email ready to send with the right tone and a clear objective.',
         'Context, clarity, tone, expected action'),
        ('mission_03_workflow', 'build-a-personal-workflow', 'Build a personal workflow',
         'Turn a recurring need into a reusable procedure with Claude.',
         'Clear steps, reusability, verification point'),
    ],
    'es': [
        ('mission_01_long_doc', 'resumir-un-documento-largo', 'Resumir un documento largo',
         'Produce una síntesis clara y utilizable de un contenido largo.',
         'Fidelidad, estructura, concisión'),
        ('mission_02_email', 'preparar-un-email-para-cliente-o-manager', 'Preparar un email para cliente o manager',
         'Redacta un email listo para enviar con buen tono y objetivo claro.',
         'Contexto, claridad, tono, acción esperada'),
        ('mission_03_workflow', 'construir-un-workflow-personal', 'Construir un workflow personal',
         'Convierte una necesidad repetitiva en un procedimiento reutilizable con Claude.',
         'Claridad de pasos, reutilización, punto de verificación'),
    ]
}


PROMPT_TRANSLATIONS = {
    'fr': [
        ('prompt_summary_core', 'prompt-resume-core', 'summary',
         'Prompt résumé — synthèse exploitable',
         "Résume ce contenu en 5 points maximum. Préserve l’idée centrale, les nuances importantes et les éléments à retenir pour quelqu’un qui devra agir ensuite.",
         'summary,lesson',
         'lesson_13_summary'),
        ('prompt_email_core', 'prompt-email-core', 'email',
         'Prompt email — contexte + ton + action',
         "Rédige un email.\nContexte : ...\nDestinataire : ...\nObjectif : ...\nTon : ...\nAction attendue : ...\nLongueur souhaitée : ...",
         'email,lesson',
         'lesson_14_email'),
        ('prompt_verify_core', 'prompt-verification-core', 'verification',
         'Prompt vérification — faits, hypothèses, limites',
         "Réponds à ma demande en séparant :\n1. faits établis,\n2. hypothèses ou interprétations,\n3. points à vérifier,\n4. limites de ta réponse.",
         'verification,reliability',
         'lesson_19_sources'),
        ('prompt_workflow_core', 'prompt-workflow-core', 'workflow',
         'Prompt workflow — besoin récurrent',
         "Mon besoin récurrent : ...\nInput de départ : ...\nPrompt / instruction : ...\nOutput attendu : ...\nPoint de vérification : ...\nFréquence d’usage : ...",
         'workflow,mission',
         None),
    ],
    'en': [
        ('prompt_summary_core', 'summary-core-prompt', 'summary',
         'Summary prompt — actionable synthesis',
         "Summarize this content in no more than 5 bullet points. Preserve the core idea, important nuances, and the elements someone would need in order to take action next.",
         'summary,lesson',
         'lesson_13_summary'),
        ('prompt_email_core', 'email-core-prompt', 'email',
         'Email prompt — context + tone + action',
         "Write an email.\nContext: ...\nRecipient: ...\nGoal: ...\nTone: ...\nExpected action: ...\nDesired length: ...",
         'email,lesson',
         'lesson_14_email'),
        ('prompt_verify_core', 'verification-core-prompt', 'verification',
         'Verification prompt — facts, assumptions, limits',
         "Answer my request by separating:\n1. established facts,\n2. assumptions or interpretations,\n3. points to verify,\n4. limits of your answer.",
         'verification,reliability',
         'lesson_19_sources'),
        ('prompt_workflow_core', 'workflow-core-prompt', 'workflow',
         'Workflow prompt — recurring need',
         "My recurring need: ...\nStarting input: ...\nPrompt / instruction: ...\nExpected output: ...\nVerification point: ...\nFrequency of use: ...",
         'workflow,mission',
         None),
    ],
    'es': [
        ('prompt_summary_core', 'prompt-resumen-core', 'summary',
         'Prompt resumen — síntesis utilizable',
         "Resume este contenido en un máximo de 5 puntos. Conserva la idea central, los matices importantes y los elementos que alguien necesitaría para actuar después.",
         'summary,lesson',
         'lesson_13_summary'),
        ('prompt_email_core', 'prompt-email-core', 'email',
         'Prompt email — contexto + tono + acción',
         "Redacta un email.\nContexto: ...\nDestinatario: ...\nObjetivo: ...\nTono: ...\nAcción esperada: ...\nLongitud deseada: ...",
         'email,lesson',
         'lesson_14_email'),
        ('prompt_verify_core', 'prompt-verificacion-core', 'verification',
         'Prompt verificación — hechos, hipótesis, límites',
         "Responde a mi solicitud separando:\n1. hechos establecidos,\n2. hipótesis o interpretaciones,\n3. puntos a verificar,\n4. límites de tu respuesta.",
         'verification,reliability',
         'lesson_19_sources'),
        ('prompt_workflow_core', 'prompt-workflow-core', 'workflow',
         'Prompt workflow — necesidad recurrente',
         "Mi necesidad recurrente: ...\nInput inicial: ...\nPrompt / instrucción: ...\nSalida esperada: ...\nPunto de verificación: ...\nFrecuencia de uso: ...",
         'workflow,mission',
         None),
    ]
}


# =========================================================
# Seed principal
# =========================================================

def seed_tracks(db):
    for language in SUPPORTED_LANGUAGES:
        core = TRACK_TRANSLATIONS[language]['core']
        solo = TRACK_TRANSLATIONS[language]['solopreneur']

        upsert_track(
            db,
            content_key='track_core',
            slug='core',
            language=language,
            track_type='core',
            title=core['title'],
            subtitle=core['subtitle'],
            description=core['description'],
            sort_order=1
        )

        upsert_track(
            db,
            content_key='track_solopreneur',
            slug='solopreneur',
            language=language,
            track_type='role_based',
            title=solo['title'],
            subtitle=solo['subtitle'],
            description=solo['description'],
            sort_order=2
        )


def seed_worlds(db):
    for language in SUPPORTED_LANGUAGES:
        for idx, (content_key, slug, title, subtitle) in enumerate(WORLD_TRANSLATIONS[language], start=1):
            upsert_world(
                db,
                track_content_key='track_core',
                content_key=content_key,
                slug=slug,
                language=language,
                title=title,
                subtitle=subtitle,
                description='',
                sort_order=idx,
                estimated_lessons_count=4
            )


def seed_skills(db):
    for language in SUPPORTED_LANGUAGES:
        for idx, (content_key, slug, category, title) in enumerate(SKILL_TRANSLATIONS[language], start=1):
            upsert_skill(
                db,
                content_key=content_key,
                slug=slug,
                language=language,
                category=category,
                title=title,
                description='',
                sort_order=idx
            )


def seed_lessons(db):
    for language in SUPPORTED_LANGUAGES:
        for item in LESSONS_DATA[language]:
            (
                world_content_key,
                lesson_content_key,
                slug,
                lesson_type,
                title,
                short_title,
                objective,
                hook_text,
                mini_concept,
                takeaway,
                sort_order,
                xp_reward,
                skill_keys
            ) = item

            upsert_lesson(
                db,
                world_content_key=world_content_key,
                content_key=lesson_content_key,
                slug=slug,
                language=language,
                lesson_type=lesson_type,
                title=title,
                short_title=short_title,
                hook_text=hook_text,
                objective=objective,
                mini_concept=mini_concept,
                takeaway=takeaway,
                estimated_minutes=4,
                xp_reward=xp_reward,
                sort_order=sort_order,
                is_published=True,
                is_active=True
            )

            for skill_content_key in skill_keys:
                upsert_lesson_skill(
                    db,
                    lesson_content_key=lesson_content_key,
                    skill_content_key=skill_content_key,
                    language=language,
                    weight=1
                )


def seed_missions(db):
    for language in SUPPORTED_LANGUAGES:
        for idx, (content_key, slug, title, brief, criteria) in enumerate(MISSION_TRANSLATIONS[language], start=1):
            upsert_mission(
                db,
                track_content_key='track_solopreneur',
                content_key=content_key,
                slug=slug,
                language=language,
                title=title,
                brief=brief,
                success_criteria=criteria,
                estimated_minutes=10,
                xp_reward=60,
                sort_order=idx,
                is_published=True,
                is_active=True
            )


def seed_prompts(db):
    for language in SUPPORTED_LANGUAGES:
        for idx, (content_key, slug, prompt_type, title, prompt_text, tags_csv, lesson_content_key) in enumerate(PROMPT_TRANSLATIONS[language], start=1):
            upsert_prompt(
                db,
                owner_type='system',
                visibility='course',
                language=language,
                prompt_type=prompt_type,
                title=title,
                prompt_text=prompt_text,
                description='',
                content_key=content_key,
                slug=slug,
                input_template='',
                expected_output='',
                lesson_content_key=lesson_content_key,
                mission_content_key=None,
                tags_csv=tags_csv,
                sort_order=idx,
                user_id=None,
                is_active=True
            )


def seed_all(db):
    seed_tracks(db)
    seed_worlds(db)
    seed_skills(db)
    seed_lessons(db)
    seed_missions(db)
    seed_prompts(db)
    db.commit()
    return {
        'ok': True,
        'languages': SUPPORTED_LANGUAGES,
        'message': 'Learning seed completed successfully.'
    }