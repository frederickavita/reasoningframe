# -*- coding: utf-8 -*-

import re


class ApplicationValidationError(Exception):
    """Raised when application-level validation fails."""
    pass


class SearchInputValidationError(ApplicationValidationError):
    """Raised when the prospect search input is invalid."""
    pass


class CriteriaValidationError(ApplicationValidationError):
    """Raised when qualification criteria are invalid."""
    pass


class WorkflowValidationError(ApplicationValidationError):
    """Raised when a workflow action is not allowed."""
    pass


class SearchRequestValidator(object):
    """
    Validate and normalize user input before creating a prospect_run.
    This is application-level validation, separate from DAL field validation.
    """

    MIN_TEXT_LENGTH = 2
    MAX_NICHE_LENGTH = 255
    MAX_CITY_LENGTH = 255
    MAX_OFFER_LENGTH = 5000
    DEFAULT_RESULT_LIMIT = 25
    MIN_RESULT_LIMIT = 1
    MAX_RESULT_LIMIT = 100

    def normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def validate_required_text(self, value, field_name, min_length=2, max_length=255):
        normalized = self.normalize_text(value)

        if not normalized:
            raise SearchInputValidationError("%s is required." % field_name)

        if len(normalized) < min_length:
            raise SearchInputValidationError("%s must be at least %s characters." % (field_name, min_length))

        if len(normalized) > max_length:
            raise SearchInputValidationError("%s must be at most %s characters." % (field_name, max_length))

        return normalized

    def validate_requested_result_limit(self, value):
        if value in (None, "", False):
            return self.DEFAULT_RESULT_LIMIT

        try:
            value = int(value)
        except (TypeError, ValueError):
            raise SearchInputValidationError("requested_result_limit must be an integer.")

        if value < self.MIN_RESULT_LIMIT:
            raise SearchInputValidationError(
                "requested_result_limit must be >= %s." % self.MIN_RESULT_LIMIT
            )

        if value > self.MAX_RESULT_LIMIT:
            raise SearchInputValidationError(
                "requested_result_limit must be <= %s." % self.MAX_RESULT_LIMIT
            )

        return value

    def validate(self, niche, city, offer, requested_result_limit=None):
        cleaned_niche = self.validate_required_text(
            niche,
            field_name="niche",
            min_length=self.MIN_TEXT_LENGTH,
            max_length=self.MAX_NICHE_LENGTH,
        )

        cleaned_city = self.validate_required_text(
            city,
            field_name="city",
            min_length=self.MIN_TEXT_LENGTH,
            max_length=self.MAX_CITY_LENGTH,
        )

        cleaned_offer = self.validate_required_text(
            offer,
            field_name="offer",
            min_length=self.MIN_TEXT_LENGTH,
            max_length=self.MAX_OFFER_LENGTH,
        )

        cleaned_limit = self.validate_requested_result_limit(requested_result_limit)

        return {
            "niche": cleaned_niche,
            "city": cleaned_city,
            "offer": cleaned_offer,
            "requested_result_limit": cleaned_limit,
        }


class QualificationCriteriaValidator(object):
    """
    Parse and validate qualification criteria.

    Accepted raw formats:
    - must_mention:shopify
    - must_not_mention:klaviyo

    Can accept:
    - multiline text
    - comma-separated text
    - a Python list of strings
    """

    ALLOWED_KINDS = ("must_mention", "must_not_mention")
    MAX_CRITERIA_COUNT = 20
    MAX_VALUE_LENGTH = 255

    def normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def split_raw_criteria(self, raw_criteria):
        if raw_criteria is None:
            return []

        if isinstance(raw_criteria, (list, tuple)):
            parts = [self.normalize_text(x) for x in raw_criteria]
            return [p for p in parts if p]

        raw_criteria = str(raw_criteria).replace("\r", "\n")
        raw_criteria = raw_criteria.replace(",", "\n")
        parts = [self.normalize_text(x) for x in raw_criteria.split("\n")]
        return [p for p in parts if p]

    def parse_criterion(self, item):
        if ":" not in item:
            raise CriteriaValidationError(
                "Invalid criterion format '%s'. Expected kind:value." % item
            )

        kind, value = item.split(":", 1)
        kind = self.normalize_text(kind)
        value = self.normalize_text(value)

        if kind not in self.ALLOWED_KINDS:
            raise CriteriaValidationError(
                "Invalid criterion kind '%s'. Allowed kinds: %s."
                % (kind, ", ".join(self.ALLOWED_KINDS))
            )

        if not value:
            raise CriteriaValidationError(
                "Criterion '%s' must have a non-empty value." % item
            )

        if len(value) > self.MAX_VALUE_LENGTH:
            raise CriteriaValidationError(
                "Criterion value '%s' is too long (max %s chars)." % (value, self.MAX_VALUE_LENGTH)
            )

        return {
            "kind": kind,
            "value": value,
        }

    def validate(self, raw_criteria):
        items = self.split_raw_criteria(raw_criteria)

        if len(items) > self.MAX_CRITERIA_COUNT:
            raise CriteriaValidationError(
                "Too many criteria. Maximum allowed is %s." % self.MAX_CRITERIA_COUNT
            )

        parsed = []
        seen = set()

        for item in items:
            criterion = self.parse_criterion(item)
            dedup_key = (criterion["kind"], criterion["value"].lower())

            if dedup_key in seen:
                continue

            seen.add(dedup_key)
            parsed.append(criterion)

        return parsed


class RunWorkflowValidator(object):
    """
    Validate business workflow actions on prospect runs.
    Expects DAL Row objects or any object exposing the same attributes.
    """

    def ensure_run_exists(self, run_row):
        if not run_row:
            raise WorkflowValidationError("Run not found.")

    def ensure_can_unlock(self, run_row):
        self.ensure_run_exists(run_row)

        if run_row.is_unlocked:
            raise WorkflowValidationError("Run is already unlocked.")

        if run_row.discovered_count == 0 and run_row.processed_count == 0:
            raise WorkflowValidationError("Cannot unlock an empty run.")

    def ensure_can_export(self, run_row):
        self.ensure_run_exists(run_row)

        if not run_row.is_unlocked:
            raise WorkflowValidationError("Run must be unlocked before export.")

        if run_row.processed_count <= 0:
            raise WorkflowValidationError("Cannot export a run with no processed prospects.")

    def ensure_can_render_preview(self, run_row):
        self.ensure_run_exists(run_row)

        if run_row.preview_count < 0:
            raise WorkflowValidationError("Invalid preview_count.")

    def ensure_can_process_run(self, run_row):
        self.ensure_run_exists(run_row)

        if not run_row.niche:
            raise WorkflowValidationError("Run has no niche.")
        if not run_row.city:
            raise WorkflowValidationError("Run has no city.")
        if not run_row.offer:
            raise WorkflowValidationError("Run has no offer.")

        if run_row.requested_result_limit <= 0:
            raise WorkflowValidationError("Run has invalid requested_result_limit.")


class ProspectOutputValidator(object):
    MAX_SUMMARY_LENGTH = 2000
    MAX_ANGLE_LENGTH = 2000
    MAX_EMAIL_SUBJECT_LENGTH = 255
    MAX_EMAIL_DRAFT_LENGTH = 10000
    MAX_QUALIFICATION_EXPLANATION_LENGTH = 3000

    FALLBACK_SUMMARY = "Business summary unavailable."
    FALLBACK_ANGLE = "Potential outreach opportunity identified from public business information."
    FALLBACK_EMAIL_SUBJECT = "Quick idea"
    FALLBACK_EMAIL_DRAFT = (
        "Hi, I had a quick idea that may help improve your business visibility or conversion."
    )
    FALLBACK_QUALIFICATION_EXPLANATION = (
        "Qualification explanation unavailable."
    )

    ALLOWED_CONFIDENCE_LEVELS = ("low", "medium", "high")

    def normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def truncate(self, value, max_length):
        if len(value) <= max_length:
            return value
        return value[:max_length].strip()

    def validate_summary(self, summary):
        summary = self.normalize_text(summary)
        if not summary:
            summary = self.FALLBACK_SUMMARY
        return self.truncate(summary, self.MAX_SUMMARY_LENGTH)

    def validate_angle(self, angle):
        angle = self.normalize_text(angle)
        if not angle:
            angle = self.FALLBACK_ANGLE
        return self.truncate(angle, self.MAX_ANGLE_LENGTH)

    def validate_email_subject(self, subject):
        subject = self.normalize_text(subject)
        if not subject:
            subject = self.FALLBACK_EMAIL_SUBJECT
        return self.truncate(subject, self.MAX_EMAIL_SUBJECT_LENGTH)

    def validate_email_draft(self, draft):
        draft = self.normalize_text(draft)
        if not draft:
            draft = self.FALLBACK_EMAIL_DRAFT
        return self.truncate(draft, self.MAX_EMAIL_DRAFT_LENGTH)

    def validate_qualification_explanation(self, text):
        text = self.normalize_text(text)
        if not text:
            text = self.FALLBACK_QUALIFICATION_EXPLANATION
        return self.truncate(text, self.MAX_QUALIFICATION_EXPLANATION_LENGTH)

    def validate_fit_confidence(self, value):
        value = self.normalize_text(value).lower()
        if value not in self.ALLOWED_CONFIDENCE_LEVELS:
            return "medium"
        return value

    def validate_all(self, summary, angle, subject, draft, qualification_explanation="", fit_confidence="medium"):
        return {
            "business_summary": self.validate_summary(summary),
            "outreach_angle": self.validate_angle(angle),
            "email_subject": self.validate_email_subject(subject),
            "email_draft": self.validate_email_draft(draft),
            "qualification_explanation": self.validate_qualification_explanation(qualification_explanation),
            "fit_confidence": self.validate_fit_confidence(fit_confidence),
        }