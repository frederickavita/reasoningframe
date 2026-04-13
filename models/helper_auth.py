def _get_google_config():
    """
    Lit la config Google OAuth depuis AppConfig.
    Adapte cette fonction si tu stockes ailleurs.
    """
    try:
        client_id = configuration.take('google.client_id')
        client_secret = configuration.take('google.client_secret')
    except Exception:
        client_id = None
        client_secret = None
    return client_id, client_secret


def _flash_login_error(message):
    session.flash = message
    redirect(URL('default', 'login'))


def _safe_next_url(default_url):
    """
    Empêche les redirections externes arbitraires.
    On accepte seulement :
    - une URL locale relative
    - sinon on revient sur default_url
    """
    nxt = session.pop('oauth_next', None)
    if nxt and isinstance(nxt, str) and nxt.startswith('/'):
        return nxt
    return default_url


def _get_auth_user_by_google_sub(google_sub):
    return db(db.auth_user.google_sub == google_sub).select().first()


def _get_auth_user_by_email(email_value):
    return db(db.auth_user.email == email_value).select().first()


def _build_dummy_password_hash():
    """
    Même si on est en Google-only, on préfère stocker un hash aléatoire
    plutôt qu'une chaîne vide ou en clair.
    """
    raw = str(uuid.uuid4())
    hashed, error = db.auth_user.password.validate(raw)
    if error:
        # Fallback ultra-défensif ; en pratique validate() devrait marcher.
        return 'oauth_only_' + raw
    return hashed


def _make_auth_user_payload(email_value, given_name, family_name, avatar_url, google_sub, email_verified):
    first_name = (given_name or '').strip() or 'Google'
    last_name = (family_name or '').strip() or 'User'

    return dict(
        first_name=first_name,
        last_name=last_name,
        email=email_value,
        password=_build_dummy_password_hash(),
        account_status='active',
        auth_provider='google',
        google_sub=google_sub,
        google_picture_url=avatar_url or None,
        email_verified=bool(email_verified),
        last_login_at=request.now,
    )


def _update_auth_user_profile(user_id, given_name, family_name, avatar_url, google_sub, email_verified):
    updates = dict(
        auth_provider='google',
        google_sub=google_sub,
        google_picture_url=avatar_url or None,
        email_verified=bool(email_verified),
        last_login_at=request.now,
    )

    if given_name:
        updates['first_name'] = given_name.strip()

    if family_name:
        updates['last_name'] = family_name.strip()

    db(db.auth_user.id == user_id).update(**updates)


def _assert_user_can_login(user):
    if not user:
        _flash_login_error(T("Utilisateur introuvable."))

    if user.account_status in ('blocked', 'revoked'):
        _flash_login_error(T("Votre compte est désactivé. Contactez le support."))

    if user.account_status == 'refunded':
        _flash_login_error(T("Votre accès a été révoqué suite à un remboursement."))


def _bootstrap_user_after_login(user_id):
    """
    Garde cette fonction légère.
    Le login ne doit pas embarquer trop de logique métier.
    """
    db(db.auth_user.id == user_id).update(last_login_at=request.now)

    # Optionnel : créer un projet par défaut à la première connexion
    has_project = db(db.project.owner_id == user_id).count() > 0
    if not has_project:
        slug = 'starter-%s' % web2py_uuid()[:8]
        db.project.insert(
            owner_id=user_id,
            name='My first project',
            slug=slug,
            status='draft',
            default_browser='chromium',
            headed=False,
            retries=0,
            timeout_ms=30000,
            trace_mode='retain-on-failure',
            last_opened_on=request.now,
        )


def user_has_active_lifetime_access(user_id):
    """
    À utiliser pour le gating produit si besoin.
    On ne bloque pas forcément le login avec ça.
    """
    row = db(
        (db.user_entitlement.user_id == user_id) &
        (db.user_entitlement.code == 'lifetime_access') &
        (db.user_entitlement.status == 'active')
    ).select(db.user_entitlement.id).first()

    return bool(row)
