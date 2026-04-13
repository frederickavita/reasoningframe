
def _flash_login_error(message):
    session.flash = message
    redirect(URL('default', 'login'))


def _get_auth_user_by_email(email_value):
    if not email_value:
        return None
    return db(db.auth_user.email == email_value.lower().strip()).select().first()


def _get_auth_user_by_google_sub(google_sub):
    if not google_sub:
        return None
    registration_id = 'google:%s' % google_sub
    return db(db.auth_user.registration_id == registration_id).select().first()


def _make_auth_user_payload(email_value, given_name='', family_name='',
                            avatar_url='', ui_language='fr',
                            learning_language='fr'):
    return dict(
        first_name=(given_name or '').strip() or 'Utilisateur',
        last_name=(family_name or '').strip() or 'Google',
        email=(email_value or '').strip().lower(),
        username=None,
        registration_id='',
        auth_provider='google',
        avatar_url=(avatar_url or '').strip(),
        onboarding_completed=False,
        onboarding_step=0,
        learning_goal='productivity',
        primary_track='solopreneur',
        ui_language=ui_language,
        learning_language=learning_language,
        timezone='Europe/Paris',
        last_seen_at=request.now,
    )


def _update_auth_user_profile(user_id, given_name='', family_name='',
                              avatar_url='', google_sub=''):
    updates = dict(
        auth_provider='google',
        avatar_url=(avatar_url or '').strip(),
        last_seen_at=request.now,
    )

    if google_sub:
        updates['registration_id'] = 'google:%s' % google_sub

    if given_name:
        updates['first_name'] = given_name.strip()

    if family_name:
        updates['last_name'] = family_name.strip()

    db(db.auth_user.id == user_id).update(**updates)


def _bootstrap_user_after_login(user_id):
    # Crée la ligne de progression résumé si elle n'existe pas
    row = db(db.user_progress.user_id == user_id).select().first()
    if not row:
        db.user_progress.insert(
            user_id=user_id,
            total_xp=0,
            level=1,
            current_streak=0,
            longest_streak=0,
            current_world_slug='world-1-discover',
            current_lesson_slug='ce-que-claude-sait-bien-faire',
            current_track='solopreneur',
            completed_lessons_count=0,
            completed_missions_count=0,
            unlocked_skills_count=0,
            first_lesson_started=False,
            first_mission_completed=False
        )


def _get_google_config():
    """
    Adapte cette fonction à ta vraie source de config.
    Pour le moment on lit dans private/appconfig.ini via myconf.
    """
    try:
        client_id = configuration.get('google.client_id')
        client_secret = configuration.get('google.client_secret')
    except:
        client_id = None
        client_secret = None

    return client_id, client_secret