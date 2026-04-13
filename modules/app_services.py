# -*- coding: utf-8 -*-

import json
import re
from gluon import current
from gluon.utils import web2py_uuid


# =============================================================================
# EXCEPTIONS
# =============================================================================

class AppServiceError(Exception):
    pass


class NotFoundError(AppServiceError):
    pass


class PermissionDeniedError(AppServiceError):
    pass


class ValidationError(AppServiceError):
    def __init__(self, message, field_errors=None):
        super(ValidationError, self).__init__(message)
        self.field_errors = field_errors or {}


class BillingAccessError(AppServiceError):
    pass


# =============================================================================
# INTERNAL ACCESSORS
# =============================================================================

def _db():
    return current.db


def _auth():
    return current.auth


def _request():
    return current.request


def _now():
    return _request().now


# =============================================================================
# JSON HELPERS
# =============================================================================

def _json_dumps(value):
    return json.dumps(value or {}, ensure_ascii=False)


def _json_dumps_list(value):
    return json.dumps(value or [], ensure_ascii=False)


def _json_loads(value, default=None):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


# =============================================================================
# GENERIC HELPERS
# =============================================================================

def _clean(value):
    return str(value).strip() if value is not None else ''


def _slugify(value):
    value = _clean(value).lower()
    value = re.sub(r'[^a-z0-9]+', '-', value)
    value = re.sub(r'-{2,}', '-', value).strip('-')
    return value or ('project-' + web2py_uuid()[:8])


def _identifierify(value):
    """
    Pour noms techniques simples type page/element.
    """
    value = _clean(value).lower()
    value = re.sub(r'[^a-z0-9_]+', '_', value)
    value = re.sub(r'_{2,}', '_', value).strip('_')
    return value


def _require_user_id(user_id):
    if not user_id:
        raise PermissionDeniedError('Authentication required.')


def _get_row(table, row_id, message='Record not found.'):
    db = _db()
    row = table[row_id]
    if not row:
        raise NotFoundError(message)
    return row


def _is_active_row(row):
    return bool(row) and ('is_active' not in row or row.is_active is True)


# =============================================================================
# LOCATOR QUALITY
# =============================================================================

def locator_quality_for(locator_type):
    """
    Politique simple V1 alignée avec notre produit.
    """
    locator_type = _clean(locator_type).lower()

    if locator_type == 'role':
        return dict(score=100, label='recommended')
    if locator_type == 'label':
        return dict(score=95, label='recommended')
    if locator_type == 'testid':
        return dict(score=85, label='good')
    if locator_type == 'text':
        return dict(score=70, label='acceptable')
    if locator_type == 'css':
        return dict(score=40, label='fragile')

    return dict(score=0, label='fragile')


# =============================================================================
# ACCESS CONTROL
# =============================================================================

def require_user_can_access_project(user_id, project_id):
    """
    Vérifie que le projet appartient à l'utilisateur et qu'il est actif.
    """
    db = _db()
    _require_user_id(user_id)

    project = db(
        (db.project.id == project_id) &
        (db.project.owner_id == user_id) &
        (db.project.is_active == True)
    ).select().first()

    if not project:
        raise PermissionDeniedError('You do not have access to this project.')

    return project


def require_user_has_lifetime_access(user_id):
    db = _db()
    _require_user_id(user_id)

    row = db(
        (db.user_entitlement.user_id == user_id) &
        (db.user_entitlement.code == 'lifetime_access') &
        (db.user_entitlement.status == 'active') &
        (db.user_entitlement.is_active == True)
    ).select(db.user_entitlement.id).first()

    if not row:
        raise BillingAccessError('Active lifetime access is required.')

    return True


# =============================================================================
# PROJECT SERVICES
# =============================================================================

def list_projects_for_user(user_id):
    db = _db()
    _require_user_id(user_id)

    return db(
        (db.project.owner_id == user_id) &
        (db.project.is_active == True)
    ).select(orderby=~db.project.modified_on)


def get_project_for_user(user_id, project_id):
    return require_user_can_access_project(user_id, project_id)


def _ensure_unique_project_slug(slug, exclude_project_id=None):
    db = _db()
    q = (db.project.slug == slug) & (db.project.is_active == True)
    if exclude_project_id:
        q &= (db.project.id != exclude_project_id)

    if db(q).count():
        base = slug
        i = 2
        while db((db.project.slug == '%s-%s' % (base, i)) & (db.project.is_active == True)).count():
            i += 1
        slug = '%s-%s' % (base, i)

    return slug


def create_project_for_user(
    user_id,
    name='My first project',
    description='',
    base_url='',
    default_browser='chromium',
    headed=False,
    retries=0,
    timeout_ms=30000,
    trace_mode='retain-on-failure'
):
    db = _db()
    _require_user_id(user_id)

    name = _clean(name)
    if not name:
        raise ValidationError('Project name is required.', {'name': 'required'})

    slug = _ensure_unique_project_slug(_slugify(name))

    project_id = db.project.insert(
        owner_id=user_id,
        name=name,
        slug=slug,
        description=_clean(description),
        status='draft',
        base_url=_clean(base_url) or None,
        default_browser=default_browser,
        headed=bool(headed),
        retries=int(retries or 0),
        timeout_ms=int(timeout_ms or 30000),
        trace_mode=trace_mode,
        last_opened_on=_now()
    )

    return db.project[project_id]


def create_default_project_if_missing(user_id):
    db = _db()
    _require_user_id(user_id)

    existing = db(
        (db.project.owner_id == user_id) &
        (db.project.is_active == True)
    ).select(db.project.id, limitby=(0, 1)).first()

    if existing:
        return db.project[existing.id]

    project = create_project_for_user(
        user_id=user_id,
        name='My first project',
        description='Starter project',
        default_browser='chromium',
        headed=False,
        retries=0,
        timeout_ms=30000,
        trace_mode='retain-on-failure'
    )

    # Ajout d'un petit scénario d'exemple
    db.scenario.insert(
        project_id=project.id,
        name='Starter scenario',
        source_text='TEST "Starter scenario"\nFIN',
        status='draft',
        ast_json='{}',
        steps_json='[]',
        validation_json='{}',
        generated_code=''
    )

    return project


def update_project_settings(
    user_id,
    project_id,
    name=None,
    description=None,
    base_url=None,
    default_browser=None,
    headed=None,
    retries=None,
    timeout_ms=None,
    trace_mode=None,
    status=None
):
    db = _db()
    project = require_user_can_access_project(user_id, project_id)

    updates = {}

    if name is not None:
        clean_name = _clean(name)
        if not clean_name:
            raise ValidationError('Project name is required.', {'name': 'required'})
        updates['name'] = clean_name
        updates['slug'] = _ensure_unique_project_slug(_slugify(clean_name), exclude_project_id=project.id)

    if description is not None:
        updates['description'] = _clean(description)

    if base_url is not None:
        updates['base_url'] = _clean(base_url) or None

    if default_browser is not None:
        updates['default_browser'] = default_browser

    if headed is not None:
        updates['headed'] = bool(headed)

    if retries is not None:
        retries = int(retries)
        if retries < 0 or retries > 5:
            raise ValidationError('Retries must be between 0 and 5.', {'retries': 'invalid'})
        updates['retries'] = retries

    if timeout_ms is not None:
        timeout_ms = int(timeout_ms)
        if timeout_ms < 1000 or timeout_ms > 300000:
            raise ValidationError('Timeout must be between 1000 and 300000 ms.', {'timeout_ms': 'invalid'})
        updates['timeout_ms'] = timeout_ms

    if trace_mode is not None:
        updates['trace_mode'] = trace_mode

    if status is not None:
        updates['status'] = status

    if updates:
        db(db.project.id == project.id).update(**updates)

    return db.project[project.id]


def touch_project_last_opened(user_id, project_id):
    db = _db()
    project = require_user_can_access_project(user_id, project_id)
    db(db.project.id == project.id).update(last_opened_on=_now())
    return db.project[project.id]


def archive_project(user_id, project_id):
    db = _db()
    project = require_user_can_access_project(user_id, project_id)

    db(db.project.id == project.id).update(
        status='archived',
        is_active=False
    )
    return True


# =============================================================================
# PAGE SERVICES
# =============================================================================

def _ensure_unique_page_name(project_id, name, exclude_page_id=None):
    db = _db()
    q = (
        (db.project_page.project_id == project_id) &
        (db.project_page.name == name) &
        (db.project_page.is_active == True)
    )
    if exclude_page_id:
        q &= (db.project_page.id != exclude_page_id)

    if db(q).count():
        raise ValidationError('Page name must be unique in the project.', {'name': 'duplicate'})


def list_pages(user_id, project_id):
    db = _db()
    require_user_can_access_project(user_id, project_id)

    return db(
        (db.project_page.project_id == project_id) &
        (db.project_page.is_active == True)
    ).select(orderby=[db.project_page.sort_order, db.project_page.id])


def create_page(user_id, project_id, name, route=None, notes=None, sort_order=0):
    db = _db()
    require_user_can_access_project(user_id, project_id)

    clean_name = _identifierify(name)
    if not clean_name:
        raise ValidationError('Page name is required.', {'name': 'required'})

    _ensure_unique_page_name(project_id, clean_name)

    page_id = db.project_page.insert(
        project_id=project_id,
        name=clean_name,
        route=_clean(route) or None,
        status='partial',
        notes=_clean(notes),
        sort_order=int(sort_order or 0)
    )

    return db.project_page[page_id]


def update_page(user_id, page_id, name=None, route=None, notes=None, status=None, sort_order=None):
    db = _db()
    page = _get_row(db.project_page, page_id, 'Page not found.')
    require_user_can_access_project(user_id, page.project_id)

    if not _is_active_row(page):
        raise NotFoundError('Page not found.')

    updates = {}

    if name is not None:
        clean_name = _identifierify(name)
        if not clean_name:
            raise ValidationError('Page name is required.', {'name': 'required'})
        _ensure_unique_page_name(page.project_id, clean_name, exclude_page_id=page.id)
        updates['name'] = clean_name

    if route is not None:
        updates['route'] = _clean(route) or None

    if notes is not None:
        updates['notes'] = _clean(notes)

    if status is not None:
        updates['status'] = status

    if sort_order is not None:
        updates['sort_order'] = int(sort_order)

    if updates:
        db(db.project_page.id == page.id).update(**updates)

    return db.project_page[page.id]


def archive_page(user_id, page_id):
    db = _db()
    page = _get_row(db.project_page, page_id, 'Page not found.')
    require_user_can_access_project(user_id, page.project_id)

    db(db.project_page.id == page.id).update(
        status='archived',
        is_active=False
    )

    # On archive aussi les éléments de cette page
    db(db.project_element.page_id == page.id).update(
        status='archived',
        is_active=False
    )
    return True


# =============================================================================
# ELEMENT SERVICES
# =============================================================================

def _ensure_unique_element_name(page_id, name, exclude_element_id=None):
    db = _db()
    q = (
        (db.project_element.page_id == page_id) &
        (db.project_element.name == name) &
        (db.project_element.is_active == True)
    )
    if exclude_element_id:
        q &= (db.project_element.id != exclude_element_id)

    if db(q).count():
        raise ValidationError('Element name must be unique in the page.', {'name': 'duplicate'})


def list_elements(user_id, page_id):
    db = _db()
    page = _get_row(db.project_page, page_id, 'Page not found.')
    require_user_can_access_project(user_id, page.project_id)

    return db(
        (db.project_element.page_id == page_id) &
        (db.project_element.is_active == True)
    ).select(orderby=[db.project_element.sort_order, db.project_element.id])


def create_element(
    user_id,
    page_id,
    name,
    locator_type,
    locator_value,
    notes=None,
    is_critical=False,
    sort_order=0
):
    db = _db()
    page = _get_row(db.project_page, page_id, 'Page not found.')
    require_user_can_access_project(user_id, page.project_id)

    clean_name = _identifierify(name)
    if not clean_name:
        raise ValidationError('Element name is required.', {'name': 'required'})

    locator_type = _clean(locator_type).lower()
    locator_value = _clean(locator_value)
    if not locator_value:
        raise ValidationError('Locator value is required.', {'locator_value': 'required'})

    _ensure_unique_element_name(page.id, clean_name)

    quality = locator_quality_for(locator_type)

    element_id = db.project_element.insert(
        project_id=page.project_id,
        page_id=page.id,
        name=clean_name,
        locator_type=locator_type,
        locator_value=locator_value,
        quality_label=quality['label'],
        quality_score=quality['score'],
        status='ready' if quality['score'] >= 70 else 'warning',
        is_critical=bool(is_critical),
        notes=_clean(notes),
        sort_order=int(sort_order or 0)
    )

    _refresh_page_status_from_elements(page.id)

    return db.project_element[element_id]


def update_element(
    user_id,
    element_id,
    name=None,
    locator_type=None,
    locator_value=None,
    notes=None,
    is_critical=None,
    status=None,
    sort_order=None
):
    db = _db()
    element = _get_row(db.project_element, element_id, 'Element not found.')
    require_user_can_access_project(user_id, element.project_id)

    if not _is_active_row(element):
        raise NotFoundError('Element not found.')

    updates = {}

    if name is not None:
        clean_name = _identifierify(name)
        if not clean_name:
            raise ValidationError('Element name is required.', {'name': 'required'})
        _ensure_unique_element_name(element.page_id, clean_name, exclude_element_id=element.id)
        updates['name'] = clean_name

    next_locator_type = locator_type if locator_type is not None else element.locator_type
    next_locator_value = locator_value if locator_value is not None else element.locator_value

    if locator_type is not None:
        updates['locator_type'] = _clean(locator_type).lower()

    if locator_value is not None:
        clean_locator_value = _clean(locator_value)
        if not clean_locator_value:
            raise ValidationError('Locator value is required.', {'locator_value': 'required'})
        updates['locator_value'] = clean_locator_value

    if locator_type is not None or locator_value is not None:
        quality = locator_quality_for(_clean(next_locator_type).lower())
        updates['quality_label'] = quality['label']
        updates['quality_score'] = quality['score']

        if status is None:
            updates['status'] = 'ready' if quality['score'] >= 70 else 'warning'

    if notes is not None:
        updates['notes'] = _clean(notes)

    if is_critical is not None:
        updates['is_critical'] = bool(is_critical)

    if status is not None:
        updates['status'] = status

    if sort_order is not None:
        updates['sort_order'] = int(sort_order)

    if updates:
        db(db.project_element.id == element.id).update(**updates)

    _refresh_page_status_from_elements(element.page_id)

    return db.project_element[element.id]


def archive_element(user_id, element_id):
    db = _db()
    element = _get_row(db.project_element, element_id, 'Element not found.')
    require_user_can_access_project(user_id, element.project_id)

    db(db.project_element.id == element.id).update(
        status='archived',
        is_active=False
    )

    _refresh_page_status_from_elements(element.page_id)
    return True


def _refresh_page_status_from_elements(page_id):
    """
    Politique simple :
    - 0 élément actif => partial
    - au moins un élément error => error
    - au moins un warning => partial
    - sinon ready
    """
    db = _db()
    page = db.project_page[page_id]
    if not page or not page.is_active:
        return

    rows = db(
        (db.project_element.page_id == page_id) &
        (db.project_element.is_active == True)
    ).select(db.project_element.status)

    if not rows:
        status = 'partial'
    else:
        statuses = set(r.status for r in rows)
        if 'error' in statuses:
            status = 'error'
        elif 'warning' in statuses:
            status = 'partial'
        else:
            status = 'ready'

    db(db.project_page.id == page_id).update(status=status)


# =============================================================================
# SCENARIO SERVICES
# =============================================================================

def list_scenarios(user_id, project_id):
    db = _db()
    require_user_can_access_project(user_id, project_id)

    return db(
        (db.scenario.project_id == project_id) &
        (db.scenario.is_active == True)
    ).select(orderby=[db.scenario.sort_order, db.scenario.id])


def create_scenario(user_id, project_id, name, source_text='TEST "New scenario"\nFIN', sort_order=0):
    db = _db()
    require_user_can_access_project(user_id, project_id)

    name = _clean(name)
    if not name:
        raise ValidationError('Scenario name is required.', {'name': 'required'})

    scenario_id = db.scenario.insert(
        project_id=project_id,
        name=name,
        source_text=source_text or '',
        status='draft',
        ast_json='{}',
        steps_json='[]',
        validation_json='{}',
        generated_code='',
        source_map_json='[]',
        sort_order=int(sort_order or 0)
    )
    return db.scenario[scenario_id]


def save_scenario(user_id, scenario_id, name=None, source_text=None, status=None, sort_order=None):
    db = _db()
    scenario = _get_row(db.scenario, scenario_id, 'Scenario not found.')
    require_user_can_access_project(user_id, scenario.project_id)

    if not _is_active_row(scenario):
        raise NotFoundError('Scenario not found.')

    updates = {}

    if name is not None:
        clean_name = _clean(name)
        if not clean_name:
            raise ValidationError('Scenario name is required.', {'name': 'required'})
        updates['name'] = clean_name

    if source_text is not None:
        updates['source_text'] = source_text

    if status is not None:
        updates['status'] = status

    if sort_order is not None:
        updates['sort_order'] = int(sort_order)

    if updates:
        db(db.scenario.id == scenario.id).update(**updates)

    return db.scenario[scenario.id]


def archive_scenario(user_id, scenario_id):
    db = _db()
    scenario = _get_row(db.scenario, scenario_id, 'Scenario not found.')
    require_user_can_access_project(user_id, scenario.project_id)

    db(db.scenario.id == scenario.id).update(
        status='archived',
        is_active=False
    )
    return True


def set_scenario_compilation(
    user_id,
    scenario_id,
    ast=None,
    steps=None,
    validation=None,
    generated_code='',
    source_map=None,
    status=None,
    parser_version='v1',
    compiler_version='v1'
):
    """
    Stocke les résultats du parser / validator / compiler.
    """
    db = _db()
    scenario = _get_row(db.scenario, scenario_id, 'Scenario not found.')
    require_user_can_access_project(user_id, scenario.project_id)

    updates = dict(
        ast_json=_json_dumps(ast or {}),
        steps_json=_json_dumps_list(steps or []),
        validation_json=_json_dumps(validation or {}),
        generated_code=generated_code or '',
        source_map_json=_json_dumps_list(source_map or []),
        parser_version=parser_version,
        compiler_version=compiler_version,
        last_compiled_on=_now()
    )

    if status is not None:
        updates['status'] = status

    db(db.scenario.id == scenario.id).update(**updates)
    return db.scenario[scenario.id]


def get_scenario_payload(user_id, scenario_id):
    db = _db()
    scenario = _get_row(db.scenario, scenario_id, 'Scenario not found.')
    require_user_can_access_project(user_id, scenario.project_id)

    return dict(
        scenario=scenario,
        ast=_json_loads(scenario.ast_json, default={}),
        steps=_json_loads(scenario.steps_json, default=[]),
        validation=_json_loads(scenario.validation_json, default={}),
        source_map=_json_loads(scenario.source_map_json, default=[])
    )


# =============================================================================
# RUN SERVICES
# =============================================================================

def record_run_start(user_id, scenario_id, runtime_snapshot=None):
    db = _db()
    scenario = _get_row(db.scenario, scenario_id, 'Scenario not found.')
    require_user_can_access_project(user_id, scenario.project_id)

    run_id = db.scenario_run.insert(
        project_id=scenario.project_id,
        scenario_id=scenario.id,
        status='precheck',
        started_on=_now(),
        runtime_snapshot_json=_json_dumps(runtime_snapshot or {})
    )

    db(db.scenario.id == scenario.id).update(status='running')
    return db.scenario_run[run_id]


def update_run_status(user_id, run_id, status, error_type=None, error_message=None):
    db = _db()
    run = _get_row(db.scenario_run, run_id, 'Run not found.')
    require_user_can_access_project(user_id, run.project_id)

    db(db.scenario_run.id == run.id).update(
        status=status,
        error_type=error_type,
        error_message=error_message
    )

    return db.scenario_run[run.id]


def record_run_finish(
    user_id,
    run_id,
    status,
    duration_ms=None,
    failed_step_index=None,
    failed_step_source=None,
    error_type=None,
    error_message=None,
    result_summary=None,
    stdout_text=None,
    stderr_text=None
):
    db = _db()
    run = _get_row(db.scenario_run, run_id, 'Run not found.')
    require_user_can_access_project(user_id, run.project_id)

    updates = dict(
        status=status,
        finished_on=_now(),
        duration_ms=(int(duration_ms) if duration_ms is not None else None),
        failed_step_index=failed_step_index,
        failed_step_source=failed_step_source,
        error_type=error_type,
        error_message=error_message,
        result_summary_json=_json_dumps(result_summary or {}),
        stdout_text=stdout_text,
        stderr_text=stderr_text
    )

    db(db.scenario_run.id == run.id).update(**updates)

    # Refléter l'état sur le scénario
    scenario_status = 'ready'
    if status == 'passed':
        scenario_status = 'passed'
    elif status == 'failed':
        scenario_status = 'failed'
    elif status == 'cancelled':
        scenario_status = 'cancelled'

    db(db.scenario.id == run.scenario_id).update(status=scenario_status)

    return db.scenario_run[run.id]


def attach_run_artifact(
    user_id,
    run_id,
    artifact_type,
    file_path,
    file_name=None,
    mime_type=None,
    size_bytes=0,
    notes=None
):
    db = _db()
    run = _get_row(db.scenario_run, run_id, 'Run not found.')
    require_user_can_access_project(user_id, run.project_id)

    artifact_id = db.run_artifact.insert(
        run_id=run.id,
        artifact_type=artifact_type,
        file_path=file_path,
        file_name=file_name,
        mime_type=mime_type,
        size_bytes=int(size_bytes or 0),
        notes=_clean(notes)
    )
    return db.run_artifact[artifact_id]


def list_run_artifacts(user_id, run_id):
    db = _db()
    run = _get_row(db.scenario_run, run_id, 'Run not found.')
    require_user_can_access_project(user_id, run.project_id)

    return db(
        (db.run_artifact.run_id == run.id) &
        (db.run_artifact.is_active == True)
    ).select(orderby=db.run_artifact.id)


def get_run_payload(user_id, run_id):
    db = _db()
    run = _get_row(db.scenario_run, run_id, 'Run not found.')
    require_user_can_access_project(user_id, run.project_id)

    artifacts = list_run_artifacts(user_id, run.id)

    return dict(
        run=run,
        runtime_snapshot=_json_loads(run.runtime_snapshot_json, default={}),
        result_summary=_json_loads(run.result_summary_json, default={}),
        artifacts=artifacts
    )


# =============================================================================
# FEEDBACK SERVICES
# =============================================================================

def submit_feedback(
    user_id=None,
    project_id=None,
    category='suggestion',
    subject='',
    message='',
    contact_email='',
    priority='normal',
    meta=None
):
    db = _db()

    subject = _clean(subject)
    message = _clean(message)
    contact_email = _clean(contact_email).lower()

    if not subject:
        raise ValidationError('Subject is required.', {'subject': 'required'})
    if not message:
        raise ValidationError('Message is required.', {'message': 'required'})

    if project_id and user_id:
        require_user_can_access_project(user_id, project_id)

    feedback_id = db.feedback.insert(
        user_id=user_id,
        project_id=project_id,
        category=category,
        status='new',
        subject=subject,
        message=message,
        contact_email=contact_email or None,
        priority=priority,
        meta_json=_json_dumps(meta or {})
    )

    return db.feedback[feedback_id]


def reply_to_feedback(admin_user_id, feedback_id, admin_reply, new_status='answered'):
    """
    Simple service admin. Le contrôle admin réel se fait dans le contrôleur.
    """
    db = _db()
    feedback = _get_row(db.feedback, feedback_id, 'Feedback not found.')

    db(db.feedback.id == feedback.id).update(
        admin_reply=_clean(admin_reply),
        status=new_status,
        replied_on=_now()
    )
    return db.feedback[feedback.id]