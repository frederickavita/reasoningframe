# -*- coding: utf-8 -*-

import json
import uuid

import importlib
import applications.reasoningframe.modules.domain.enums as domain_enums

importlib.reload(domain_enums)
RUN_STATUS_VALUES = set(domain_enums.RUN_STATUS_VALUES)


class RunServiceError(Exception):
    """Base exception for run service errors."""
    pass


class RunNotFoundError(RunServiceError):
    """Raised when a run cannot be found."""
    pass


class RunService(object):
    """
    Service responsible for creating and updating prospect_run records.

    This service does NOT perform prospect discovery or qualification.
    It only manages the lifecycle and state of a run.
    """

    def __init__(self, db, search_request_validator, criteria_validator, workflow_validator):
        self.db = db
        self.search_request_validator = search_request_validator
        self.criteria_validator = criteria_validator
        self.workflow_validator = workflow_validator

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _serialize_criteria(self, parsed_criteria):
        return json.dumps(parsed_criteria, ensure_ascii=False)

    def _deserialize_criteria(self, raw_json):
        if not raw_json:
            return []
        try:
            return json.loads(raw_json)
        except Exception:
            return []

    def _update_run_field(self, run_id, **fields):
        self.db(self.db.prospect_run.id == run_id).update(**fields)
        self.db.commit()
        return self.get_run_or_fail(run_id)

    # --------------------------------------------------
    # Create / Read
    # --------------------------------------------------

    def create_run(self, niche, city, offer, raw_criteria=None, requested_result_limit=None):
        """
        Validate input and create a new prospect_run row.
        """
        clean_input = self.search_request_validator.validate(
            niche=niche,
            city=city,
            offer=offer,
            requested_result_limit=requested_result_limit,
        )

        parsed_criteria = self.criteria_validator.validate(raw_criteria)

        ret = self.db.prospect_run.validate_and_insert(
            run_uuid=str(uuid.uuid4()),
            niche=clean_input["niche"],
            city=clean_input["city"],
            offer=clean_input["offer"],
            qualification_criteria_raw=self._serialize_criteria(parsed_criteria),
            search_query_built="",
            status="idle",
            payment_status="pending",
            is_unlocked=False,
            preview_count=3,
            requested_result_limit=clean_input["requested_result_limit"],
            discovered_count=0,
            processed_count=0,
            error_count=0,
            last_error_message="",
            exported_csv_path="",
        )

        if ret.get("errors"):
            raise RunServiceError("Failed to create run: %s" % ret.get("errors"))

        self.db.commit()
        return self.get_run_or_fail(ret.get("id"))

    def get_run(self, run_id):
        return self.db.prospect_run(run_)

    def get_run_or_fail(self, run_id):
        run = self.db.prospect_run(run_id)
        if not run:
            raise RunNotFoundError("Run not found: %s" % run_id)
        return run

    def get_run_parsed_criteria(self, run_row):
        self.workflow_validator.ensure_run_exists(run_row)
        return self._deserialize_criteria(run_row.qualification_criteria_raw)

    # --------------------------------------------------
    # Status management
    # --------------------------------------------------

    def update_status(self, run_id, new_status):
        run = self.get_run_or_fail(run_id)

        allowed_statuses = set([
            "idle",
            "validating_input",
            "searching",
            "inspecting",
            "extracting_contacts",
            "qualifying",
            "drafting",
            "rendering",
            "locked_preview",
            "unlocked",
            "exported",
            "failed",
        ])

        if new_status not in RUN_STATUS_VALUES:
            raise RunServiceError("Invalid run status: %s" % new_status)

        return self._update_run_field(run.id, status=new_status)

    def mark_locked_preview(self, run_id):
        return self.update_status(run_id, "locked_preview")

    def mark_unlocked(self, run_id):
        run = self.get_run_or_fail(run_id)
        self.workflow_validator.ensure_can_unlock(run)

        updated = self._update_run_field(
            run.id,
            is_unlocked=True,
            payment_status="paid",
            status="unlocked",
        )
        return updated

    def mark_exported(self, run_id, exported_csv_path):
        run = self.get_run_or_fail(run_id)
        self.workflow_validator.ensure_can_export(run)

        updated = self._update_run_field(
            run.id,
            exported_csv_path=exported_csv_path or "",
            status="exported",
        )
        return updated

    # --------------------------------------------------
    # Counters
    # --------------------------------------------------

    def increment_discovered_count(self, run_id, amount=1):
        run = self.get_run_or_fail(run_id)

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise RunServiceError("amount must be an integer")

        if amount < 0:
            raise RunServiceError("amount must be >= 0")

        return self._update_run_field(
            run.id,
            discovered_count=run.discovered_count + amount,
        )

    def increment_processed_count(self, run_id, amount=1):
        run = self.get_run_or_fail(run_id)

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise RunServiceError("amount must be an integer")

        if amount < 0:
            raise RunServiceError("amount must be >= 0")

        return self._update_run_field(
            run.id,
            processed_count=run.processed_count + amount,
        )

    def increment_error_count(self, run_id, amount=1, last_error_message=None):
        run = self.get_run_or_fail(run_id)

        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise RunServiceError("amount must be an integer")

        if amount < 0:
            raise RunServiceError("amount must be >= 0")

        update_fields = {
            "error_count": run.error_count + amount,
        }

        if last_error_message is not None:
            update_fields["last_error_message"] = str(last_error_message)

        return self._update_run_field(run.id, **update_fields)

    # --------------------------------------------------
    # Search query persistence
    # --------------------------------------------------

    def set_search_query_built(self, run_id, search_query_built):
        run = self.get_run_or_fail(run_id)

        if search_query_built is None:
            search_query_built = ""

        return self._update_run_field(
            run.id,
            search_query_built=str(search_query_built),
        )

    # --------------------------------------------------
    # Safety / consistency helpers
    # --------------------------------------------------

    def ensure_run_can_be_processed(self, run_id):
        run = self.get_run_or_fail(run_id)
        self.workflow_validator.ensure_can_process_run(run)
        return run

    def ensure_run_can_export(self, run_id):
        run = self.get_run_or_fail(run_id)
        self.workflow_validator.ensure_can_export(run)
        return run

    def ensure_run_can_unlock(self, run_id):
        run = self.get_run_or_fail(run_id)
        self.workflow_validator.ensure_can_unlock(run)
        return run