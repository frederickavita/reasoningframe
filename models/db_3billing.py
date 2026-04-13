db.define_table(
    'billing_offer',
    Field('code', length=50, unique=True, notnull=True,
          requires=IS_NOT_EMPTY()),
    Field('name', length=150, notnull=True, requires=IS_NOT_EMPTY()),
    Field('description', 'text'),
    Field('provider', default='paypal',
          requires=IS_IN_SET(PAYMENT_PROVIDER, zero=None)),
    Field('currency', length=10, default='EUR', requires=IS_NOT_EMPTY()),
    Field('price_amount', 'double', default=79.0,
          requires=IS_FLOAT_IN_RANGE(0.0, 100000.0)),
    Field('is_lifetime', 'boolean', default=True),
    Field('is_active', 'boolean', default=True),
    auth.signature,
    format='%(name)s'
)

# 8) BILLING PAYMENT
db.define_table(
    'billing_payment',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('user_id', 'reference auth_user', notnull=True, ondelete='CASCADE'),
    Field('offer_id', 'reference billing_offer', notnull=True, ondelete='RESTRICT'),
    Field('provider', default='paypal',
          requires=IS_IN_SET(PAYMENT_PROVIDER, zero=None)),
    Field('provider_order_id', length=255, unique=True),
    Field('provider_capture_id', length=255),
    Field('provider_payer_id', length=255),
    Field('payer_email', length=255),
    Field('gross_amount', 'double', default=0.0),
    Field('fee_amount', 'double', default=0.0),
    Field('net_amount', 'double', default=0.0),
    Field('currency', length=10, default='EUR'),
    Field('status', default='created',
          requires=IS_IN_SET(PAYMENT_STATUS, zero=None)),
    Field('paid_on', 'datetime'),
    Field('refunded_on', 'datetime'),
    json_text_field('provider_payload_json', default='{}'),
    Field('notes', 'text'),
    auth.signature
)

# 9) USER ENTITLEMENT
db.define_table(
    'user_entitlement',
    Field('uuid', length=64, default=lambda: uuid4().hex, unique=True,
          writable=False, readable=False),
    Field('user_id', 'reference auth_user', notnull=True, ondelete='CASCADE'),
    Field('payment_id', 'reference billing_payment', ondelete='SET NULL'),
    Field('code', default='lifetime_access',
          requires=IS_IN_SET(ENTITLEMENT_CODE, zero=None)),
    Field('status', default='active',
          requires=IS_IN_SET(ENTITLEMENT_STATUS, zero=None)),
    Field('granted_on', 'datetime', default=request.now),
    Field('revoked_on', 'datetime'),
    Field('reason', 'text'),
    auth.signature
)
