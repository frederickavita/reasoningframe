# -*- coding: utf-8 -*-

import json
import re

from google import genai


class GeminiVisiblePeopleValidatorError(Exception):
    """Raised when Gemini visible-people validation fails."""
    pass


class GeminiVisiblePeopleValidator(object):
    """
    Validate a candidate visible person using Gemini with strict structured output.

    Input contract:
    {
        "candidate_name": "...",
        "candidate_role_hint": "...",
        "source_url": "...",
        "context_before": "...",
        "context_line": "...",
        "context_after": "...",
        "page_title": "...",
    }

    Output contract:
    {
        "is_real_person": true|false,
        "is_presented_as_working_for_business": true|false,
        "normalized_full_name": "...",
        "role_text": "...",
        "evidence_text": "...",
        "confidence": 0.0-1.0,
        "rejection_reason": "...",
        "llm_model_used": "gemini-2.5-flash-lite"
    }
    """

    DEFAULT_MODEL = "models/gemini-2.5-flash-lite"
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_CONTEXT_CHARS = 2500

    def __init__(self, api_key, model_name=None, temperature=None, max_context_chars=None):
        if not api_key:
            raise GeminiVisiblePeopleValidatorError("Gemini API key is missing.")

        self.api_key = api_key
        self.model_name = model_name or self.DEFAULT_MODEL
        self.temperature = self.DEFAULT_TEMPERATURE if temperature is None else temperature
        self.max_context_chars = max_context_chars or self.DEFAULT_MAX_CONTEXT_CHARS
        self.client = genai.Client(api_key=self.api_key)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def validate_candidate(self, candidate, business_context=None):
        if not isinstance(candidate, dict):
            raise GeminiVisiblePeopleValidatorError("candidate must be a dictionary.")

        business_context = business_context or {}

        prompt = self._build_user_prompt(candidate, business_context)
        schema = self._build_response_schema()
        system_instruction = self._build_system_instruction()

        parsed = None
        raw_text = ""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={
                    "temperature": self.temperature,
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "response_json_schema": schema,
                },
            )

            parsed = getattr(response, "parsed", None)
            if parsed is None:
                raw_text = self._extract_response_text(response)
                parsed = self._parse_json_response(raw_text)

        except Exception as e:
            try:
                fallback_response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt + "\n\nReturn only one valid JSON object matching the schema.",
                    config={
                        "temperature": self.temperature,
                        "system_instruction": system_instruction,
                        "response_mime_type": "application/json",
                        "response_json_schema": schema,
                    },
                )

                parsed = getattr(fallback_response, "parsed", None)
                if parsed is None:
                    raw_text = self._extract_response_text(fallback_response)
                    parsed = self._parse_json_response(raw_text)

            except Exception as fallback_e:
                raise GeminiVisiblePeopleValidatorError(
                    "Gemini visible people validation failed. "
                    "Structured output error: %s ; fallback error: %s" % (e, fallback_e)
                )

        normalized = self._normalize_output(parsed, candidate=candidate)
        normalized["llm_model_used"] = self._normalize_model_name(self.model_name)
        return normalized

    # --------------------------------------------------
    # Prompt building
    # --------------------------------------------------

    def _build_system_instruction(self):
        return """
<role>
You are a strict validator for visible people mentioned on a public business website.
</role>

<goal>
Decide whether a candidate refers to:
1. a real human person
2. explicitly presented as working for, representing, or practicing within the business shown on the page
</goal>

<core_rules>
- Use only the provided candidate and local page context.
- Do not invent facts.
- Do not infer employment from weak clues alone.
- A person must be explicitly or very strongly presented as part of the business to be accepted.
- If the candidate is a place, street, university, award, certification, hospital, menu item, service, city, heading, or organization, reject it.
- If uncertain, reject it.
</core_rules>

<acceptance_rules>
Accept only if the text explicitly supports that:
- this is a real person, and
- this person is presented as part of the business/team/staff/practice/company/site

Examples of acceptable explicit business links:
- team member
- practitioner
- dentist
- founder
- manager
- expert
- staff member
- surgeon
- doctor
</acceptance_rules>

<rejection_rules>
Reject if the candidate appears to be:
- a location
- an address fragment
- a street
- a city
- a transport stop
- a hospital
- a university
- an award
- a certification
- a service
- a menu item
- a page heading
- a legal mention
- a copyright block
- a generic phrase
- a real person mentioned without explicit evidence of working for the business
</rejection_rules>

<normalization_rules>
- normalized_full_name should be short and human-readable.
- Keep titles only if they are clearly part of the visible presentation, e.g. "Dr Ralph Badaoui".
- role_text should be short and based only on visible evidence.
- evidence_text must be a short excerpt from the provided context.
- confidence must be between 0.0 and 1.0.
</normalization_rules>

<decision_policy>
- If is_real_person is false, then is_presented_as_working_for_business must also be false.
- If the person is real but not explicitly tied to the business, reject.
- If accepted, rejection_reason must be "".
- If rejected, normalized_full_name and role_text may be empty.
</decision_policy>

<examples>
<example>
<input>
candidate_name: Dr. Ralph BADAOUI
candidate_role_hint:
context_line: Dr. Ralph BADAOUI | Dental surgeon & Cosmetic dentist
</input>
<output_summary>
Decision: accept
Reason: explicit person with explicit practitioner role on the page
Normalized name: Dr Ralph Badaoui
Role: Dental surgeon & Cosmetic dentist
Evidence: Dr. Ralph BADAOUI | Dental surgeon & Cosmetic dentist
</output_summary>
</example>

<example>
<input>
candidate_name: Université Paris Descartes
candidate_role_hint: 2020
context_line: Diplôme de formation approfondie en sciences odontologiques - Université Paris Descartes
</input>
<output_summary>
Decision: reject
Reason: organization or institution, not a person
Evidence: Diplôme de formation approfondie en sciences odontologiques - Université Paris Descartes
</output_summary>
</example>

<example>
<input>
candidate_name: Victor Hugo
candidate_role_hint: Aix en Provence
context_line: Aix en Provence | 22 avenue Victor Hugo, 13100 AIX EN PROVENCE
</input>
<output_summary>
Decision: reject
Reason: address or location fragment, not a person
Evidence: Aix en Provence | 22 avenue Victor Hugo, 13100 AIX EN PROVENCE
</output_summary>
</example>

<example>
<input>
candidate_name: Jean Dupont
candidate_role_hint:
context_line: Merci à Jean Dupont pour son intervention lors de notre conférence annuelle.
</input>
<output_summary>
Decision: reject
Reason: real person mentioned, but not explicitly presented as working for the business
Evidence: Merci à Jean Dupont pour son intervention lors de notre conférence annuelle.
</output_summary>
</example>
</examples>
""".strip()

    def _build_user_prompt(self, candidate, business_context):
        candidate_name = self._normalize_text(candidate.get("candidate_name", ""))[:300]
        candidate_role_hint = self._normalize_text(candidate.get("candidate_role_hint", ""))[:300]
        source_url = self._normalize_text(candidate.get("source_url", ""))[:500]
        page_title = self._normalize_text(candidate.get("page_title", ""))[:500]

        local_context = self._build_local_context(
            candidate.get("context_before", ""),
            candidate.get("context_line", ""),
            candidate.get("context_after", ""),
        )

        business_type = self._normalize_text(business_context.get("business_type", ""))[:200]
        niche = self._normalize_text(business_context.get("niche", ""))[:200]
        city = self._normalize_text(business_context.get("city", ""))[:200]

        return """
<input>
<business_context>
business_type: %(business_type)s
niche: %(niche)s
city: %(city)s
</business_context>

<candidate>
candidate_name: %(candidate_name)s
candidate_role_hint: %(candidate_role_hint)s
source_url: %(source_url)s
page_title: %(page_title)s
</candidate>

<local_context>
context_before: %(context_before)s
context_line: %(context_line)s
context_after: %(context_after)s
</local_context>

<task>
Validate whether this candidate is:
1. a real person
2. explicitly presented as working for or representing the business on this page

Return only the JSON object matching the schema.
</task>
</input>
""" % {
            "business_type": business_type,
            "niche": niche,
            "city": city,
            "candidate_name": candidate_name,
            "candidate_role_hint": candidate_role_hint,
            "source_url": source_url,
            "page_title": page_title,
            "context_before": local_context["context_before"],
            "context_line": local_context["context_line"],
            "context_after": local_context["context_after"],
        }

    def _build_local_context(self, context_before, context_line, context_after):
        parts = [
            ("context_before", self._normalize_text(context_before)),
            ("context_line", self._normalize_text(context_line)),
            ("context_after", self._normalize_text(context_after)),
        ]

        remaining = self.max_context_chars
        out = {
            "context_before": "",
            "context_line": "",
            "context_after": "",
        }

        for key, value in parts:
            if remaining <= 0:
                out[key] = ""
                continue

            clipped = value[:remaining]
            out[key] = clipped
            remaining -= len(clipped)

        return out

    def _build_response_schema(self):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_real_person": {
                    "type": "boolean",
                    "description": "True only if the candidate clearly refers to a human person."
                },
                "is_presented_as_working_for_business": {
                    "type": "boolean",
                    "description": "True only if the context explicitly or very strongly shows the person is part of the business/team/practice."
                },
                "normalized_full_name": {
                    "type": "string",
                    "description": "Short normalized person name. Empty string if rejected."
                },
                "role_text": {
                    "type": "string",
                    "description": "Visible role or title explicitly supported by the local context. Empty string if not visible or rejected."
                },
                "evidence_text": {
                    "type": "string",
                    "description": "Short excerpt from the provided context supporting the decision."
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence score between 0.0 and 1.0."
                },
                "rejection_reason": {
                    "type": "string",
                    "description": "Short reason when the candidate is rejected, else empty string."
                },
            },
            "required": [
                "is_real_person",
                "is_presented_as_working_for_business",
                "normalized_full_name",
                "role_text",
                "evidence_text",
                "confidence",
                "rejection_reason",
            ],
        }

    # --------------------------------------------------
    # Response parsing
    # --------------------------------------------------

    def _extract_response_text(self, response):
        text = getattr(response, "text", None)
        if text:
            return text.strip()

        try:
            candidates = []
            for cand in getattr(response, "candidates", []) or []:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", []) or []
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if part_text:
                        candidates.append(part_text)
            if candidates:
                return "\n".join(candidates).strip()
        except Exception:
            pass

        raise GeminiVisiblePeopleValidatorError("Gemini returned no text content.")

    def _parse_json_response(self, raw_text):
        raw_text = (raw_text or "").strip()

        if not raw_text:
            raise GeminiVisiblePeopleValidatorError("Gemini returned empty text.")

        raw_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"^```\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        try:
            return json.loads(raw_text)
        except ValueError:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = raw_text[start:end + 1]
                try:
                    return json.loads(candidate)
                except ValueError:
                    pass

        raise GeminiVisiblePeopleValidatorError(
            "Gemini returned invalid JSON: %s" % raw_text[:1000]
        )

    # --------------------------------------------------
    # Normalization
    # --------------------------------------------------

    def _normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _normalize_model_name(self, value):
        value = self._normalize_text(value)
        if value.startswith("models/"):
            return value[len("models/"):]
        return value

    def _normalize_confidence(self, value, default_value=0.5):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return default_value

        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value

    def _has_name_overlap(self, a, b):
        a_tokens = set(re.findall(r"[A-Za-zÀ-ÿ]+", self._normalize_text(a).lower()))
        b_tokens = set(re.findall(r"[A-Za-zÀ-ÿ]+", self._normalize_text(b).lower()))
        return bool(a_tokens & b_tokens)

    def _normalize_output(self, parsed, candidate=None):
        if not isinstance(parsed, dict):
            raise GeminiVisiblePeopleValidatorError("Parsed response must be a dictionary.")

        candidate = candidate or {}
        candidate_name = self._normalize_text(candidate.get("candidate_name", ""))

        is_real_person = bool(parsed.get("is_real_person", False))
        is_presented = bool(parsed.get("is_presented_as_working_for_business", False))

        normalized_full_name = self._normalize_text(parsed.get("normalized_full_name", ""))
        role_text = self._normalize_text(parsed.get("role_text", ""))
        evidence_text = self._normalize_text(parsed.get("evidence_text", ""))
        rejection_reason = self._normalize_text(parsed.get("rejection_reason", ""))
        confidence = self._normalize_confidence(parsed.get("confidence", 0.5), default_value=0.5)

        if not is_real_person:
            is_presented = False

        if is_presented:
            if not evidence_text or not normalized_full_name:
                is_presented = False
                normalized_full_name = ""
                role_text = ""
                if not rejection_reason:
                    rejection_reason = "Accepted output lacks sufficient explicit evidence."
            elif candidate_name and not self._has_name_overlap(candidate_name, normalized_full_name):
                is_presented = False
                normalized_full_name = ""
                role_text = ""
                rejection_reason = "Normalized name does not sufficiently match the candidate."

        if not is_presented:
            normalized_full_name = ""
            role_text = ""
            if not rejection_reason:
                rejection_reason = "Candidate not explicitly validated as a visible person working for the business."

        if len(evidence_text) > 500:
            evidence_text = evidence_text[:500].strip()

        return {
            "is_real_person": is_real_person,
            "is_presented_as_working_for_business": is_presented,
            "normalized_full_name": normalized_full_name,
            "role_text": role_text,
            "evidence_text": evidence_text,
            "confidence": confidence,
            "rejection_reason": rejection_reason,
        }