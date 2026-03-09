from gluon.validators import IS_NOT_EMPTY, IS_LENGTH, IS_IN_SET
import importlib
import applications.reasoningframe.modules.domain.enums as domain_enums

importlib.reload(domain_enums)

RUN_STATUS_VALUES = domain_enums.RUN_STATUS_VALUES
PAYMENT_STATUS_VALUES = domain_enums.PAYMENT_STATUS_VALUES


db.define_table(
    "prospect_run",
    Field("run_uuid", "string", unique=True, notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("niche", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("city", "string", notnull=True, requires=[IS_NOT_EMPTY(), IS_LENGTH(255)]),
    Field("offer", "text", notnull=True, requires=IS_NOT_EMPTY()),
    Field("qualification_criteria_raw", "text", default=""),
    Field("search_query_built", "text", default=""),
    Field("status", "string", default="idle", notnull=True, requires=IS_IN_SET(RUN_STATUS_VALUES)),
    Field("payment_status", "string", default="pending", notnull=True, requires=IS_IN_SET(PAYMENT_STATUS_VALUES)),
    Field("is_unlocked", "boolean", default=False),
    Field("preview_count", "integer", default=3),
    Field("requested_result_limit", "integer", default=25),
    Field("discovered_count", "integer", default=0),
    Field("processed_count", "integer", default=0),
    Field("error_count", "integer", default=0),
    Field("last_error_message", "text", default=""),
    Field("exported_csv_path", "string", default="", requires=IS_LENGTH(1024)),
    Field("created_on", "datetime", default=request.now, writable=False, readable=True),
    Field("modified_on", "datetime", default=request.now, update=request.now, writable=False, readable=True),
    migrate=True,
)



db.prospect_run.preview_count.requires = IS_INT_IN_RANGE(0, 9999999, error_message="preview_count must be >= 0")
db.prospect_run.requested_result_limit.requires = IS_INT_IN_RANGE(1, 9999999, error_message="requested_result_limit must be > 0")
db.prospect_run.discovered_count.requires = IS_INT_IN_RANGE(0, 9999999, error_message="discovered_count must be >= 0")
db.prospect_run.processed_count.requires = IS_INT_IN_RANGE(0, 9999999, error_message="processed_count must be >= 0")
db.prospect_run.error_count.requires = IS_INT_IN_RANGE(0, 9999999, error_message="error_count must be >= 0")