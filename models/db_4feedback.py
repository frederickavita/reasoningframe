# 10) FEEDBACK
db.define_table(
    'feedback',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('user_id', 'reference auth_user', ondelete='SET NULL'),
    Field('project_id', 'reference project', ondelete='SET NULL'),
    Field('category', default='suggestion',
          requires=IS_IN_SET(FEEDBACK_CATEGORY, zero=None)),
    Field('status', default='new',
          requires=IS_IN_SET(FEEDBACK_STATUS, zero=None)),
    Field('subject', length=200, requires=IS_NOT_EMPTY()),
    Field('message', 'text', requires=IS_NOT_EMPTY()),
    Field('contact_email', length=255),
    Field('priority', default='normal',
          requires=IS_IN_SET(('low', 'normal', 'high', 'urgent'), zero=None)),
    Field('admin_reply', 'text'),
    Field('replied_on', 'datetime'),
    Field('resolved_on', 'datetime'),
    json_text_field('meta_json', default='{}'),
    auth.signature,
    format='%(subject)s'
)



# BASIC REPRESENTATION
# -----------------------------------------------------------------------------
db.project_page._format = '%(name)s'
db.project_element._format = '%(name)s'
db.scenario._format = '%(name)s'
db.feedback._format = '%(subject)s'
db.billing_offer._format = '%(name)s'

# -----------------------------------------------------------------------------
# OPTIONAL VISIBILITY TWEAKS
# -----------------------------------------------------------------------------
for t in (db.project, db.project_page, db.project_element, db.scenario,
          db.scenario_run, db.run_artifact, db.billing_payment,
          db.user_entitlement, db.feedback):
    if 'uuid' in t.fields:
        t.uuid.readable = t.uuid.writable = False