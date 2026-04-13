from gluon import current
from gluon.tools import Auth

def seed_learning():
    if not auth.user:
        redirect(URL('default', 'user', args='login'))

    # À adapter selon ta logique admin
    # Ici on autorise juste l'utilisateur connecté pour aller vite en MVP
    from applications.reasoningframe.modules.seed_learning import seed_all
    result = seed_all(db)

    response.flash = result['message']
    redirect(URL('default', 'index'))