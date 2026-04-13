# 1) PROJECT
db.define_table(
    'project',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('owner_id', 'reference auth_user', notnull=True,
          default=(auth.user_id if auth.user else None)),
    Field('name', length=150, notnull=True, requires=IS_NOT_EMPTY()),
    Field('slug', length=150, unique=True, requires=IS_SLUG()),
    Field('description', 'text'),
    Field('status', default='draft',
          requires=IS_IN_SET(('draft', 'active', 'archived'), zero=None)),
    Field('base_url', length=255),
    Field('default_browser', default='chromium',
          requires=IS_IN_SET(BROWSERS, zero=None)),
    Field('headed', 'boolean', default=False),
    Field('retries', 'integer', default=0,
          requires=IS_INT_IN_RANGE(0, 6)),
    Field('timeout_ms', 'integer', default=30000,
          requires=IS_INT_IN_RANGE(1000, 300001)),
    Field('trace_mode', default='retain-on-failure',
          requires=IS_IN_SET(TRACE_MODE, zero=None)),
    Field('last_opened_on', 'datetime'),
    auth.isgnature,
    format='%(name)s'
)



# 2) PROJECT PAGE
db.define_table(
    'project_page',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('project_id', 'reference project', notnull=True, ondelete='CASCADE'),
    Field('name', length=100, notnull=True, requires=IS_NOT_EMPTY()),
    Field('route', length=255),
    Field('status', default='partial',
          requires=IS_IN_SET(PAGE_STATUS, zero=None)),
    Field('notes', 'text'),
    Field('sort_order', 'integer', default=0),
    auth.isgnature,
    format='%(name)s'
)

# 3) PROJECT ELEMENT
db.define_table(
    'project_element',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('project_id', 'reference project', notnull=True, ondelete='CASCADE'),
    Field('page_id', 'reference project_page', notnull=True, ondelete='CASCADE'),
    Field('name', length=100, notnull=True, requires=IS_NOT_EMPTY()),
    Field('locator_type', default='role',
          requires=IS_IN_SET(LOCATOR_TYPES, zero=None)),
    Field('locator_value', 'text', requires=IS_NOT_EMPTY()),
    Field('quality_label', default='recommended',
          requires=IS_IN_SET(LOCATOR_QUALITY, zero=None)),
    Field('quality_score', 'integer', default=100,
          requires=IS_INT_IN_RANGE(0, 101)),
    Field('status', default='ready',
          requires=IS_IN_SET(('ready', 'warning', 'error', 'archived'), zero=None)),
    Field('is_critical', 'boolean', default=False),
    Field('notes', 'text'),
    Field('sort_order', 'integer', default=0),
    auth.signature,
    format='%(name)s'
)

# 4) SCENARIO
db.define_table(
    'scenario',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('project_id', 'reference project', notnull=True, ondelete='CASCADE'),
    Field('name', length=150, notnull=True, requires=IS_NOT_EMPTY()),
    Field('source_text', 'text', default=''),
    Field('status', default='draft',
          requires=IS_IN_SET(SCENARIO_STATUS, zero=None)),
    json_text_field('ast_json', default='{}'),
    json_text_field('steps_json', default='[]'),
    json_text_field('validation_json', default='{}'),
    Field('generated_code', 'text'),
    json_text_field('source_map_json', default='[]'),
    Field('parser_version', length=30, default='v1'),
    Field('compiler_version', length=30, default='v1'),
    Field('last_compiled_on', 'datetime'),
    Field('sort_order', 'integer', default=0),
    auth.signature,
    format='%(name)s'
)

# 5) SCENARIO RUN
db.define_table(
    'scenario_run',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('project_id', 'reference project', notnull=True, ondelete='CASCADE'),
    Field('scenario_id', 'reference scenario', notnull=True, ondelete='CASCADE'),
    Field('status', default='idle',
          requires=IS_IN_SET(RUN_STATUS, zero=None)),
    Field('started_on', 'datetime'),
    Field('finished_on', 'datetime'),
    Field('duration_ms', 'integer'),
    Field('failed_step_index', 'integer'),
    Field('failed_step_source', 'text'),
    Field('error_type', length=80),
    Field('error_message', 'text'),
    json_text_field('runtime_snapshot_json', default='{}'),
    json_text_field('result_summary_json', default='{}'),
    Field('stdout_text', 'text'),
    Field('stderr_text', 'text'),
    auth.signature
)

# 6) RUN ARTIFACT
db.define_table(
    'run_artifact',
    Field('uuid', length=64, default=lambda: web2py_uuid(), unique=True,
          writable=False, readable=False),
    Field('run_id', 'reference scenario_run', notnull=True, ondelete='CASCADE'),
    Field('artifact_type',
          requires=IS_IN_SET(ARTIFACT_TYPE, zero=None)),
    Field('file_path', 'text'),
    Field('file_name', length=255),
    Field('mime_type', length=100),
    Field('size_bytes', 'integer', default=0),
    Field('notes', 'text'),
    auth.signature
)