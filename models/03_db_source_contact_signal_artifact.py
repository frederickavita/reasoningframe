from gluon.validators import IS_NOT_EMPTY, IS_LENGTH, IS_IN_SET, IS_IN_DB
import importlib
import applications.reasoningframe.modules.domain.enums as domain_enums

importlib.reload(domain_enums)
SOURCE_PAGE_TYPE_VALUES = domain_enums.SOURCE_PAGE_TYPE_VALUES
CONTACT_TYPE_VALUES = domain_enums.CONTACT_TYPE_VALUES
SIGNAL_POLARITY_VALUES = domain_enums.SIGNAL_POLARITY_VALUES
SIGNAL_SOURCE_KIND_VALUES = domain_enums.SIGNAL_SOURCE_KIND_VALUES
CONFIDENCE_LEVEL_VALUES = domain_enums.CONFIDENCE_LEVEL_VALUES

db.define_table(
    "prospect_source_page",
    Field("prospect_id", "reference prospect", notnull=True, requires=IS_NOT_EMPTY()),
    Field("url", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(1000)]),
    Field("page_type", "string", notnull=True, default="other", requires=IS_IN_SET(SOURCE_PAGE_TYPE_VALUES)),
    Field("loaded", "boolean", default=False),
    Field("http_status", "integer", default=0),
    Field("extracted_text", "text", default=""),
    Field("error_message", "text", default=""),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    migrate=True,
)

db.define_table(
    "prospect_contact",
    Field("prospect_id", "reference prospect", notnull=True, requires=IS_NOT_EMPTY()),
    Field("contact_type", "string", notnull=True, default="none", requires=IS_IN_SET(CONTACT_TYPE_VALUES)),
    Field("value", "string", default="", requires=IS_LENGTH(512)),
    Field("contact_name", "string", default="", requires=IS_LENGTH(255)),
    Field("contact_role", "string", default="", requires=IS_LENGTH(255)),
    Field("address_text", "text", default=""),
    Field("evidence_text", "text", default=""),
    Field("source_url", "string", default="", requires=IS_LENGTH(1000)),
    Field("confidence", "double", default=0.0),
    Field("is_primary", "boolean", default=False),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    migrate=True,
)

db.define_table(
    "prospect_signal",
    Field("prospect_id", "reference prospect", notnull=True, requires=IS_NOT_EMPTY()),
    Field("signal_type", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("signal_value", "string", default="", requires=IS_LENGTH(512)),
    Field("polarity", "string", notnull=True, requires=IS_IN_SET(SIGNAL_POLARITY_VALUES)),
    Field("source_kind", "string", default="rule", notnull=True, requires=IS_IN_SET(SIGNAL_SOURCE_KIND_VALUES)),
    Field("confidence", "double", default=0.5),
    Field("reason", "text", default=""),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    migrate=True,
)

db.define_table(
    "prospect_artifact",
    Field("prospect_id", "reference prospect", unique=True, notnull=True, requires=IS_NOT_EMPTY()),
    Field("business_summary", "text", default=""),
    Field("qualification_explanation", "text", default=""),
    Field("fit_confidence", "string", default="medium", requires=IS_IN_SET(CONFIDENCE_LEVEL_VALUES)),
    Field("outreach_angle", "text", default=""),
    Field("email_subject", "string", default="", requires=IS_LENGTH(255)),
    Field("email_draft", "text", default=""),
    Field("llm_model_used", "string", default="", requires=IS_LENGTH(255)),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    Field("modified_on", "datetime", default=request.now, update=request.now, writable=False, readable=True),
    migrate=True,
)

db.prospect_source_page.prospect_id.requires = IS_IN_DB(db, "prospect.id", "%(id)s")
db.prospect_contact.prospect_id.requires = IS_IN_DB(db, "prospect.id", "%(id)s")
db.prospect_signal.prospect_id.requires = IS_IN_DB(db, "prospect.id", "%(id)s")
db.prospect_artifact.prospect_id.requires = IS_IN_DB(db, "prospect.id", "%(id)s")


db.prospect_contact.confidence.requires = IS_FLOAT_IN_RANGE(
    0.0, 1.0, error_message="confidence must be between 0 and 1"
)

db.prospect_signal.confidence.requires = IS_FLOAT_IN_RANGE(
    0.0, 1.0, error_message="confidence must be between 0 and 1"
)


