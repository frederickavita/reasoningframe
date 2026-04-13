# -*- coding: utf-8 -*-

import base64
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from gluon import current
from gluon.utils import web2py_uuid


class PayPalServiceError(Exception):
    pass


def _db():
    return current.db


def _auth():
    return current.auth


def _request():
    return current.request


def _myconf():
    return current.myconf


def _get_paypal_config():
    """
    Exemple appconfig.ini :

    [paypal]
    client_id = xxx
    client_secret = xxx
    environment = sandbox
    webhook_id = WH-XXXX
    brand_name = My App
    currency = EUR
    return_controller = billing
    return_function = paypal_return
    cancel_controller = billing
    cancel_function = pricing
    """
    myconf = _myconf()
    env = (myconf.take('paypal.environment') or 'sandbox').strip().lower()

    cfg = dict(
        client_id=myconf.take('paypal.client_id'),
        client_secret=myconf.take('paypal.client_secret'),
        environment=env,
        webhook_id=myconf.take('paypal.webhook_id'),
        brand_name=(myconf.take('paypal.brand_name') or 'My App'),
        currency=(myconf.take('paypal.currency') or 'EUR').upper(),
        return_controller=(myconf.take('paypal.return_controller') or 'billing'),
        return_function=(myconf.take('paypal.return_function') or 'paypal_return'),
        cancel_controller=(myconf.take('paypal.cancel_controller') or 'billing'),
        cancel_function=(myconf.take('paypal.cancel_function') or 'pricing'),
    )

    if env == 'live':
        cfg['base_url'] = 'https://api-m.paypal.com'
    else:
        cfg['base_url'] = 'https://api-m.sandbox.paypal.com'

    if not cfg['client_id'] or not cfg['client_secret']:
        raise PayPalServiceError('PayPal configuration is incomplete.')

    return cfg


def _paypal_request(method, path, payload=None, access_token=None, extra_headers=None):
    cfg = _get_paypal_config()
    url = cfg['base_url'] + path

    data = None
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    if access_token:
        headers['Authorization'] = 'Bearer %s' % access_token

    if extra_headers:
        headers.update(extra_headers)

    if payload is not None:
        data = json.dumps(payload).encode('utf-8')

    req = Request(url, data=data, method=method.upper())
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except Exception as e:
        raise PayPalServiceError('PayPal API request failed: %s' % e)


def get_access_token():
    cfg = _get_paypal_config()
    token_url = cfg['base_url'] + '/v1/oauth2/token'

    credentials = ('%s:%s' % (cfg['client_id'], cfg['client_secret'])).encode('utf-8')
    auth_header = base64.b64encode(credentials).decode('utf-8')

    req = Request(
        token_url,
        data=urlencode({'grant_type': 'client_credentials'}).encode('utf-8'),
        method='POST'
    )
    req.add_header('Authorization', 'Basic %s' % auth_header)
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Accept', 'application/json')

    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise PayPalServiceError('Failed to get PayPal access token: %s' % e)

    token = payload.get('access_token')
    if not token:
        raise PayPalServiceError('No PayPal access token returned.')
    return token


def _absolute_return_url():
    cfg = _get_paypal_config()
    req = _request()
    return current.URL(
        cfg['return_controller'],
        cfg['return_function'],
        scheme=True,
        host=True
    )


def _absolute_cancel_url():
    cfg = _get_paypal_config()
    return current.URL(
        cfg['cancel_controller'],
        cfg['cancel_function'],
        scheme=True,
        host=True
    )


def _find_approve_link(order_payload):
    for link in order_payload.get('links', []):
        if link.get('rel') == 'approve':
            return link.get('href')
    return None


def create_lifetime_order(user_id, offer_code='LIFETIME'):
    """
    Crée une commande PayPal + un billing_payment local en statut 'created'.
    Retourne approve_url et order_id.
    """
    db = _db()
    cfg = _get_paypal_config()
    token = get_access_token()

    user = db.auth_user[user_id]
    if not user:
        raise PayPalServiceError('User not found.')

    offer = db(db.billing_offer.code == offer_code).select().first()
    if not offer or not offer.is_active:
        raise PayPalServiceError('Active billing offer not found.')

    reference_id = 'offer-%s-user-%s' % (offer.id, user.id)

    payload = {
        'intent': 'CAPTURE',
        'purchase_units': [
            {
                'reference_id': reference_id,
                'description': offer.name,
                'amount': {
                    'currency_code': offer.currency or cfg['currency'],
                    'value': ('%.2f' % float(offer.price_amount)),
                },
                'custom_id': str(user.id),
                'invoice_id': 'inv-%s' % web2py_uuid()[:20],
            }
        ],
        'payment_source': {
            'paypal': {
                'experience_context': {
                    'brand_name': cfg['brand_name'],
                    'shipping_preference': 'NO_SHIPPING',
                    'user_action': 'PAY_NOW',
                    'return_url': _absolute_return_url(),
                    'cancel_url': _absolute_cancel_url(),
                }
            }
        }
    }

    order_payload = _paypal_request(
        'POST',
        '/v2/checkout/orders',
        payload=payload,
        access_token=token,
        extra_headers={
            'PayPal-Request-Id': 'create-%s' % web2py_uuid()
        }
    )

    order_id = order_payload.get('id')
    approve_url = _find_approve_link(order_payload)

    if not order_id or not approve_url:
        raise PayPalServiceError('PayPal order creation returned incomplete data.')

    payment_id = db.billing_payment.insert(
        user_id=user.id,
        offer_id=offer.id,
        provider='paypal',
        provider_order_id=order_id,
        payer_email=user.email,
        gross_amount=offer.price_amount,
        fee_amount=0.0,
        net_amount=0.0,
        currency=offer.currency or cfg['currency'],
        status='created',
        provider_payload_json=json.dumps(order_payload),
        notes='Order created, awaiting buyer approval.'
    )

    return dict(
        payment_id=payment_id,
        order_id=order_id,
        approve_url=approve_url
    )


def capture_order(order_id):
    """
    Capture côté serveur après retour PayPal.
    """
    db = _db()
    token = get_access_token()

    capture_payload = _paypal_request(
        'POST',
        '/v2/checkout/orders/%s/capture' % order_id,
        payload={},
        access_token=token,
        extra_headers={
            'PayPal-Request-Id': 'capture-%s' % web2py_uuid()
        }
    )

    payment = db(db.billing_payment.provider_order_id == order_id).select().first()
    if not payment:
        raise PayPalServiceError('Local payment record not found for order_id=%s' % order_id)

    status = (capture_payload.get('status') or '').upper()

    # Extraire la première capture si présente
    capture_id = None
    gross_amount = None
    fee_amount = None
    net_amount = None
    paid_on = None
    payer_email = payment.payer_email

    payer = capture_payload.get('payer') or {}
    if payer.get('email_address'):
        payer_email = payer.get('email_address')

    purchase_units = capture_payload.get('purchase_units') or []
    if purchase_units:
        payments = purchase_units[0].get('payments') or {}
        captures = payments.get('captures') or []
        if captures:
            first_capture = captures[0]
            capture_id = first_capture.get('id')
            paid_on = first_capture.get('create_time')

            amount = first_capture.get('amount') or {}
            gross_amount = amount.get('value')

            breakdown = first_capture.get('seller_receivable_breakdown') or {}
            paypal_fee = breakdown.get('paypal_fee') or {}
            net_amount_obj = breakdown.get('net_amount') or {}

            fee_amount = paypal_fee.get('value')
            net_amount = net_amount_obj.get('value')

    if status == 'COMPLETED':
        db(db.billing_payment.id == payment.id).update(
            provider_capture_id=capture_id,
            payer_email=payer_email,
            gross_amount=float(gross_amount or payment.gross_amount or 0.0),
            fee_amount=float(fee_amount or 0.0),
            net_amount=float(net_amount or 0.0),
            status='captured',
            paid_on=_request().now,
            provider_payload_json=json.dumps(capture_payload),
            notes='Order captured successfully.'
        )
    else:
        db(db.billing_payment.id == payment.id).update(
            status='failed',
            provider_payload_json=json.dumps(capture_payload),
            notes='Capture returned non-completed status: %s' % status
        )

    return capture_payload


def grant_lifetime_entitlement_from_payment(payment_id):
    db = _db()
    payment = db.billing_payment[payment_id]
    if not payment:
        raise PayPalServiceError('Payment not found.')

    if payment.status != 'captured':
        raise PayPalServiceError('Payment is not captured.')

    existing = db(
        (db.user_entitlement.user_id == payment.user_id) &
        (db.user_entitlement.code == 'lifetime_access') &
        (db.user_entitlement.status == 'active')
    ).select().first()

    if existing:
        return existing.id

    entitlement_id = db.user_entitlement.insert(
        user_id=payment.user_id,
        payment_id=payment.id,
        code='lifetime_access',
        status='active',
        granted_on=_request().now,
        reason='Granted after successful PayPal capture.'
    )
    return entitlement_id


def revoke_entitlement_from_payment(payment_id, reason='Revoked after refund or manual action.'):
    db = _db()
    payment = db.billing_payment[payment_id]
    if not payment:
        raise PayPalServiceError('Payment not found.')

    rows = db(
        (db.user_entitlement.payment_id == payment.id) &
        (db.user_entitlement.status == 'active')
    ).select()

    for row in rows:
        db(db.user_entitlement.id == row.id).update(
            status='revoked',
            revoked_on=_request().now,
            reason=reason
        )


def verify_webhook_signature(headers, raw_body):
    """
    Vérification cryptographique via PayPal.
    headers doit contenir :
      PAYPAL-TRANSMISSION-ID
      PAYPAL-TRANSMISSION-TIME
      PAYPAL-TRANSMISSION-SIG
      PAYPAL-CERT-URL
      PAYPAL-AUTH-ALGO
    """
    cfg = _get_paypal_config()
    token = get_access_token()

    payload = {
        'auth_algo': headers.get('PAYPAL-AUTH-ALGO'),
        'cert_url': headers.get('PAYPAL-CERT-URL'),
        'transmission_id': headers.get('PAYPAL-TRANSMISSION-ID'),
        'transmission_sig': headers.get('PAYPAL-TRANSMISSION-SIG'),
        'transmission_time': headers.get('PAYPAL-TRANSMISSION-TIME'),
        'webhook_id': cfg['webhook_id'],
        'webhook_event': json.loads(raw_body.decode('utf-8'))
    }

    result = _paypal_request(
        'POST',
        '/v1/notifications/verify-webhook-signature',
        payload=payload,
        access_token=token
    )

    return result.get('verification_status') == 'SUCCESS'


def process_webhook_event(event_payload):
    """
    Gère les événements utiles pour notre offre lifetime.
    """
    db = _db()

    event_type = event_payload.get('event_type')
    resource = event_payload.get('resource') or {}

    if event_type == 'PAYMENT.CAPTURE.COMPLETED':
        capture_id = resource.get('id')
        if not capture_id:
            return dict(ok=False, action='ignored', reason='missing_capture_id')

        payment = db(db.billing_payment.provider_capture_id == capture_id).select().first()

        # Fallback possible via lien "up" vers order_id
        if not payment:
            for link in resource.get('links', []):
                if link.get('rel') == 'up':
                    up_href = link.get('href', '')
                    order_id = up_href.rstrip('/').split('/')[-1] if up_href else None
                    if order_id:
                        payment = db(db.billing_payment.provider_order_id == order_id).select().first()
                        break

        if not payment:
            return dict(ok=False, action='ignored', reason='payment_not_found')

        if payment.status != 'captured':
            db(db.billing_payment.id == payment.id).update(
                status='captured',
                paid_on=_request().now,
                provider_payload_json=json.dumps(event_payload),
                notes='Marked captured from webhook.'
            )

        entitlement_id = grant_lifetime_entitlement_from_payment(payment.id)
        return dict(ok=True, action='granted', entitlement_id=entitlement_id)

    if event_type == 'PAYMENT.CAPTURE.DENIED':
        capture_id = resource.get('id')
        payment = None
        if capture_id:
            payment = db(db.billing_payment.provider_capture_id == capture_id).select().first()

        if payment:
            db(db.billing_payment.id == payment.id).update(
                status='failed',
                provider_payload_json=json.dumps(event_payload),
                notes='Capture denied webhook received.'
            )
        return dict(ok=True, action='marked_failed')

    if event_type == 'PAYMENT.CAPTURE.REFUNDED':
        capture_id = resource.get('id')
        payment = None
        if capture_id:
            payment = db(db.billing_payment.provider_capture_id == capture_id).select().first()

        if payment:
            db(db.billing_payment.id == payment.id).update(
                status='refunded',
                refunded_on=_request().now,
                provider_payload_json=json.dumps(event_payload),
                notes='Refund webhook received.'
            )
            revoke_entitlement_from_payment(payment.id, reason='Entitlement revoked after refund.')
        return dict(ok=True, action='revoked_after_refund')

    return dict(ok=True, action='ignored', reason='event_not_used')