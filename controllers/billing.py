# -*- coding: utf-8 -*-

import json
from applications.reasoningframe.modules.paypal_service import (
    PayPalServiceError,
    create_lifetime_order,
    capture_order,
    grant_lifetime_entitlement_from_payment,
    verify_webhook_signature,
    process_webhook_event,
)

@auth.requires_login()
def pricing():
    offer = db(db.billing_offer.code == 'LIFETIME').select().first()
    return dict(offer=offer)


@auth.requires_login()
def buy_lifetime():
    try:
        result = create_lifetime_order(auth.user_id, offer_code='LIFETIME')
    except PayPalServiceError as e:
        session.flash = T(str(e))
        redirect(URL('billing', 'pricing'))

    redirect(result['approve_url'])


@auth.requires_login()
def paypal_return():
    """
    Retour utilisateur après approbation PayPal.
    PayPal renvoie généralement token=<ORDER_ID>.
    """
    order_id = request.vars.get('token')
    payer_id = request.vars.get('PayerID')

    if not order_id:
        session.flash = T("Retour PayPal invalide.")
        redirect(URL('billing', 'pricing'))

    payment = db(db.billing_payment.provider_order_id == order_id).select().first()
    if not payment:
        session.flash = T("Paiement introuvable.")
        redirect(URL('billing', 'pricing'))

    # On peut stocker payer_id si présent
    if payer_id:
        db(db.billing_payment.id == payment.id).update(provider_payer_id=payer_id)

    try:
        payload = capture_order(order_id)
    except PayPalServiceError as e:
        session.flash = T("Le paiement n'a pas pu être finalisé.")
        redirect(URL('billing', 'pricing'))

    payment = db.billing_payment[payment.id]

    if payment.status == 'captured':
        try:
            grant_lifetime_entitlement_from_payment(payment.id)
        except PayPalServiceError:
            pass

        session.flash = T("Paiement confirmé. Votre accès lifetime est actif.")
        redirect(URL('default', 'dashboard'))

    session.flash = T("Le paiement n'a pas été capturé.")
    redirect(URL('billing', 'pricing'))


@request.restful()
def paypal_webhook():
    """
    Endpoint webhook PayPal.
    IMPORTANT:
    - exposer en HTTPS
    - enregistrer l'URL dans le dashboard PayPal
    - configurer le webhook_id dans appconfig.ini
    """
    def POST(*args, **vars):
        raw_body = request.body.read()
        if not raw_body:
            response.status = 400
            return dict(ok=False, error='empty_body')

        headers = {k.upper(): v for k, v in request.env.items()}

        # web2py met les headers HTTP_* dans request.env avec get() pour éviter les crashs
        normalized_headers = {
            'PAYPAL-TRANSMISSION-ID': request.env.get('HTTP_PAYPAL_TRANSMISSION_ID'),
            'PAYPAL-TRANSMISSION-TIME': request.env.get('HTTP_PAYPAL_TRANSMISSION_TIME'),
            'PAYPAL-TRANSMISSION-SIG': request.env.get('HTTP_PAYPAL_TRANSMISSION_SIG'),
            'PAYPAL-CERT-URL': request.env.get('HTTP_PAYPAL_CERT_URL'),
            'PAYPAL-AUTH-ALGO': request.env.get('HTTP_PAYPAL_AUTH_ALGO'),
        }

        # Sécurité : vérifier qu'aucun header vital ne manque
        if not all(normalized_headers.values()):
            response.status = 400
            return dict(ok=False, error='missing_headers')
        


        try:
            verified = verify_webhook_signature(normalized_headers, raw_body)
        except PayPalServiceError:
            response.status = 400
            return dict(ok=False, error='verification_failed')

        if not verified:
            response.status = 400
            return dict(ok=False, error='invalid_signature')

        try:
            event_payload = json.loads(raw_body.decode('utf-8'))
        except Exception:
            response.status = 400
            return dict(ok=False, error='invalid_json')

        result = process_webhook_event(event_payload)

        # Toujours 200/2xx si bien traité pour éviter les retries inutiles
        return dict(ok=True, result=result)

    return locals()