# -*- coding: utf-8 -*-

from gluon.validators import IS_IN_SET, IS_NOT_EMPTY

BILLING_PROVIDERS = [
    'paypal'
]

BILLING_OFFER_TYPES = [
    'lifetime'
]

BILLING_PAYMENT_STATUSES = [
    'created',      # commande créée chez nous
    'pending',      # en attente de validation/capture
    'approved',     # approuvée côté PayPal
    'completed',    # paiement finalisé
    'failed',       # échec
    'cancelled',    # annulé par l'utilisateur
    'refunded',     # remboursé
    'reversed'      # litige / reversal
]

BILLING_ACCESS_STATUSES = [
    'pending',
    'active',
    'revoked',
    'refunded'
]

SUPPORTED_CURRENCIES = [
    'EUR',
    'USD'
]

db.define_table(
    'billing_purchase',

    Field(
        'user_id',
        'reference auth_user',
        required=True,
        notnull=True
    ),

    Field(
        'provider',
        'string',
        length=32,
        default='paypal',
        requires=IS_IN_SET(BILLING_PROVIDERS)
    ),

    Field(
        'offer_type',
        'string',
        length=32,
        default='lifetime',
        requires=IS_IN_SET(BILLING_OFFER_TYPES)
    ),

    Field(
        'offer_code',
        'string',
        length=64,
        default='founder_lifetime',
        requires=IS_NOT_EMPTY()
    ),

    Field(
        'product_name',
        'string',
        length=200,
        default='AIFlow Academy Lifetime'
    ),

    Field(
        'currency',
        'string',
        length=8,
        default='EUR',
        requires=IS_IN_SET(SUPPORTED_CURRENCIES)
    ),

    # Montant affiché / attendu côté app
    Field(
        'amount',
        'decimal(10,2)',
        default='0.00'
    ),

    # Statut du paiement
    Field(
        'payment_status',
        'string',
        length=32,
        default='created',
        requires=IS_IN_SET(BILLING_PAYMENT_STATUSES)
    ),

    # Statut d'accès produit
    Field(
        'access_status',
        'string',
        length=32,
        default='pending',
        requires=IS_IN_SET(BILLING_ACCESS_STATUSES)
    ),

    # Identifiants PayPal
    Field('paypal_order_id', 'string', length=128, default=''),
    Field('paypal_capture_id', 'string', length=128, default=''),
    Field('paypal_payer_id', 'string', length=128, default=''),
    Field('paypal_payer_email', 'string', length=255, default=''),

    # Références internes
    Field('internal_reference', 'string', length=128, default=''),
    Field('notes', 'text', default=''),

    # Pour audit/debug : payload brut PayPal sérialisé en texte JSON
    Field('raw_payload', 'text', default=''),

    # Dates métier
    Field('purchased_on', 'datetime'),
    Field('activated_on', 'datetime'),
    Field('refunded_on', 'datetime'),

    # Flags utiles
    Field('is_lifetime', 'boolean', default=True),
    Field('is_active', 'boolean', default=False),

    # Dates techniques
    Field('created_on', 'datetime', default=request.now, writable=False, readable=False),
    Field('modified_on', 'datetime', default=request.now, update=request.now, writable=False, readable=False),

    format='%(product_name)s'
)

# ---------------------------------------------------------
# Labels
# ---------------------------------------------------------
db.billing_purchase.offer_type.label = T('Type d’offre')
db.billing_purchase.offer_code.label = T('Code offre')
db.billing_purchase.product_name.label = T('Produit')
db.billing_purchase.amount.label = T('Montant')
db.billing_purchase.currency.label = T('Devise')
db.billing_purchase.payment_status.label = T('Statut paiement')     
db.billing_purchase.access_status.label = T('Statut accès')
db.billing_purchase.paypal_order_id.label = T('PayPal Order ID')
db.billing_purchase.paypal_capture_id.label = T('PayPal Capture ID')
db.billing_purchase.paypal_payer_email.label = T('Email PayPal')
db.billing_purchase.raw_payload.label = T('Payload brut')



def create_pending_lifetime_purchase(user_id, amount, currency='EUR'):
    return db.billing_purchase.insert(
        user_id=user_id,
        provider='paypal',
        offer_type='lifetime',
        offer_code='founder_lifetime',
        product_name='AIFlow Academy Lifetime',
        amount=amount,
        currency=currency,
        payment_status='created',
        access_status='pending',
        is_lifetime=True,
        is_active=False
    )


def attach_paypal_order(purchase_id, paypal_order_id, raw_payload=''):
    db(db.billing_purchase.id == purchase_id).update(
        paypal_order_id=paypal_order_id,
        payment_status='pending',
        raw_payload=raw_payload,
        modified_on=request.now
    )


def activate_lifetime_purchase(purchase_id,
                               paypal_capture_id='',
                               paypal_payer_id='',
                               paypal_payer_email='',
                               raw_payload=''):
    purchase = db.billing_purchase[purchase_id]
    if not purchase:
        return False

    db(db.billing_purchase.id == purchase_id).update(
        paypal_capture_id=paypal_capture_id,
        paypal_payer_id=paypal_payer_id,
        paypal_payer_email=paypal_payer_email,
        payment_status='completed',
        access_status='active',
        is_active=True,
        purchased_on=request.now,
        activated_on=request.now,
        raw_payload=raw_payload or purchase.raw_payload,
        modified_on=request.now
    )

    return True


def user_has_active_lifetime_access(user_id):
    row = db(
        (db.billing_purchase.user_id == user_id) &
        (db.billing_purchase.offer_type == 'lifetime') &
        (db.billing_purchase.access_status == 'active') &
        (db.billing_purchase.is_active == True)
    ).select(
        db.billing_purchase.id,
        limitby=(0, 1)
    ).first()

    return bool(row)


def refund_purchase(purchase_id, notes=''):
    db(db.billing_purchase.id == purchase_id).update(
        payment_status='refunded',
        access_status='refunded',
        is_active=False,
        refunded_on=request.now,
        notes=notes,
        modified_on=request.now
    )