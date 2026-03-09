from gluon.validators import IS_NOT_EMPTY, IS_LENGTH, IS_IN_SET, IS_IN_DB
import importlib
import applications.reasoningframe.modules.domain.enums as domain_enums

importlib.reload(domain_enums)

QUALIFICATION_STATUS_VALUES = domain_enums.QUALIFICATION_STATUS_VALUES
CONFIDENCE_LEVEL_VALUES = domain_enums.CONFIDENCE_LEVEL_VALUES


db.define_table(
    "prospect",
    Field("run_id", "reference prospect_run", notnull=True, requires=IS_NOT_EMPTY()),
    Field("company_name", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("domain", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(512)]),
    Field("city", "string", default="", requires=IS_LENGTH(255)),

    Field("qualification_status", "string", default="uncertain", notnull=True,
          requires=IS_IN_SET(QUALIFICATION_STATUS_VALUES)),

    Field("fit_confidence", "string", default="medium",
          requires=IS_IN_SET(CONFIDENCE_LEVEL_VALUES)),

    Field("qualification_explanation", "text", default=""),
    Field("llm_business_type", "string", default="", requires=IS_LENGTH(255)),
    Field("llm_offer_fit", "text", default=""),

    Field("is_processed", "boolean", default=False),
    Field("inspection_failed", "boolean", default=False),
    Field("has_public_contact", "boolean", default=False),
    Field("best_contact_value", "string", default="", requires=IS_LENGTH(512)),

    Field("business_summary", "text", default=""),
    Field("outreach_angle", "text", default=""),
    Field("email_subject", "string", default="", requires=IS_LENGTH(255)),
    Field("email_draft", "text", default=""),

    Field("render_order", "integer", default=0),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    Field("modified_on", "datetime", default=request.now, update=request.now, writable=False, readable=True),
    migrate=True,
)



db.prospect.run_id.requires = IS_IN_DB(db, "prospect_run.id", "%(id)s")
db.prospect.render_order.requires = IS_INT_IN_RANGE(0, 9999999, error_message="render_order must be >= 0")




db.define_table(
    "prospect_visible_person",
    Field("prospect_id", "reference prospect", notnull=True, requires=IS_NOT_EMPTY()),
    Field("full_name", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("role_text", "string", default="", requires=IS_LENGTH(255)),
    Field("source_url", "string", default="", requires=IS_LENGTH(1000)),
    Field("evidence_text", "text", default=""),
    Field("confidence", "double", default=0.5),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    migrate=True,
)

db.prospect_visible_person.prospect_id.requires = IS_IN_DB(db, "prospect.id", "%(id)s")
db.prospect_visible_person.confidence.requires = IS_FLOAT_IN_RANGE(
    0.0, 1.0, error_message="confidence must be between 0 and 1"
)