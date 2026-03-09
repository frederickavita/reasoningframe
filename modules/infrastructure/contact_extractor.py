# -*- coding: utf-8 -*-

import re

import phonenumbers
from bs4 import BeautifulSoup
from phonenumbers import NumberParseException, PhoneNumberFormat

from applications.reasoningframe.modules.application.ports import ContactExtractorPort


class ContactExtractorError(Exception):
    """Raised when contact extraction fails unexpectedly."""
    pass


class RegexContactExtractor(ContactExtractorPort):
    EMAIL_REGEX = re.compile(
        r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b",
        re.IGNORECASE
    )

    PHONE_CANDIDATE_REGEX = re.compile(
        r"(?:(?:\+|00)\d{1,3}[\s\.\-/]?)?"
        r"(?:\(?\d{1,4}\)?[\s\.\-/]?)?"
        r"(?:\d[\s\.\-/]?){6,16}\d"
    )

    GENERIC_EMAIL_PREFIXES = (
        "info@",
        "contact@",
        "hello@",
        "bonjour@",
        "support@",
        "admin@",
        "office@",
        "cabinet@",
        "resa@",
        "booking@",
    )

    DEFAULT_REGION_BY_COUNTRY_HINT = {
        "FR": "FR",
        "US": "US",
        "DE": "DE",
        "GB": "GB",
        "UK": "GB",
        "ES": "ES",
        "IT": "IT",
        "BE": "BE",
        "CH": "CH",
        "CA": "CA",
        "NL": "NL",
        "AU": "AU",
    }

    def extract_contacts(self, pages, default_region=None):
        if not pages:
            return [self._none_contact()]

        contacts = []

        html_link_contacts = self._extract_contacts_from_html_links(
            pages,
            default_region=default_region,
        )
        contacts.extend(html_link_contacts)

        email_contacts = self._extract_emails(pages)
        contacts.extend(email_contacts)

        phone_contacts = self._extract_phones(
            pages,
            default_region=default_region,
        )
        contacts.extend(phone_contacts)

        contacts = self._dedupe_contacts(contacts)

        if not contacts:
            fallback_contact = self._extract_contact_page_fallback(pages)
            if fallback_contact:
                contacts.append(fallback_contact)

        if not contacts:
            contacts.append(self._none_contact())

        contacts = self._mark_primary_contact(contacts)
        return contacts

    # --------------------------------------------------
    # HTML links (tel:, mailto:)
    # --------------------------------------------------

    def _extract_contacts_from_html_links(self, pages, default_region=None):
        found = []
        seen = set()

        for page in pages:
            raw_html = page.get("raw_html") or ""
            page_url = page.get("url") or ""
            page_type = (page.get("page_type") or "").lower()

            if not raw_html:
                continue

            try:
                soup = BeautifulSoup(raw_html, "html.parser")
            except Exception:
                continue

            for a_tag in soup.find_all("a", href=True):
                href = (a_tag.get("href") or "").strip()

                if href.lower().startswith("mailto:"):
                    email = href[7:].strip()
                    email = self._clean_email(email)
                    if not email:
                        continue

                    key = ("email", email.lower())
                    if key in seen:
                        continue
                    seen.add(key)

                    found.append({
                        "contact_type": "email",
                        "value": email,
                        "source_url": page_url,
                        "confidence": 0.95 if page_type == "contact" else 0.88,
                        "is_primary": False,
                    })

                elif href.lower().startswith("tel:"):
                    raw_phone = href[4:].strip()
                    raw_phone = raw_phone.replace("%20", " ").replace("%2B", "+")
                    normalized_phone, confidence = self._normalize_phone(
                        raw_phone,
                        default_region=default_region,
                        page_type=page_type,
                    )
                    if not normalized_phone:
                        continue

                    key = ("phone", normalized_phone)
                    if key in seen:
                        continue
                    seen.add(key)

                    found.append({
                        "contact_type": "phone",
                        "value": normalized_phone,
                        "source_url": page_url,
                        "confidence": max(confidence, 0.92 if page_type == "contact" else 0.85),
                        "is_primary": False,
                    })

        return found

    # --------------------------------------------------
    # Emails
    # --------------------------------------------------

    def _extract_emails(self, pages):
        found = []
        seen = set()

        for page in pages:
            page_text = (page.get("extracted_text") or "")
            page_url = page.get("url") or ""

            matches = self.EMAIL_REGEX.findall(page_text)

            for email in matches:
                cleaned = self._clean_email(email)
                if not cleaned:
                    continue

                key = cleaned.lower()
                if key in seen:
                    continue

                seen.add(key)

                found.append({
                    "contact_type": "email",
                    "value": cleaned,
                    "source_url": page_url,
                    "confidence": self._score_email_confidence(cleaned, page),
                    "is_primary": False,
                })

        return found

    def _clean_email(self, email):
        if not email:
            return ""
        return email.strip().strip(".,;:()[]{}<>")

    def _score_email_confidence(self, email, page):
        email_lower = email.lower()
        page_type = (page.get("page_type") or "").lower()

        score = 0.75

        if page_type == "contact":
            score += 0.15

        for prefix in self.GENERIC_EMAIL_PREFIXES:
            if email_lower.startswith(prefix):
                score += 0.05
                break

        return min(score, 1.0)

    # --------------------------------------------------
    # Phones
    # --------------------------------------------------

    def _extract_phones(self, pages, default_region=None):
        found = []
        seen = set()

        for page in pages:
            page_text = (page.get("extracted_text") or "")
            raw_html = (page.get("raw_html") or "")
            page_url = page.get("url") or ""
            page_type = (page.get("page_type") or "").lower()

            candidates = []

            # 1. From extracted visible text
            candidates.extend(self.PHONE_CANDIDATE_REGEX.findall(page_text))

            # 2. From raw HTML visible lines
            if raw_html:
                try:
                    soup = BeautifulSoup(raw_html, "html.parser")
                    raw_text = soup.get_text("\n", strip=True) or ""
                    for line in raw_text.split("\n"):
                        line = re.sub(r"\s+", " ", line).strip()
                        if not line:
                            continue
                        line_matches = self.PHONE_CANDIDATE_REGEX.findall(line)
                        candidates.extend(line_matches)
                except Exception:
                    pass

            for raw_candidate in candidates:
                candidate = self._clean_phone_candidate(raw_candidate)
                if not candidate:
                    continue

                normalized_phone, confidence = self._normalize_phone(
                    candidate,
                    default_region=default_region,
                    page_type=page_type,
                )

                if not normalized_phone:
                    continue

                if normalized_phone in seen:
                    continue

                seen.add(normalized_phone)

                found.append({
                    "contact_type": "phone",
                    "value": normalized_phone,
                    "source_url": page_url,
                    "confidence": confidence,
                    "is_primary": False,
                })

        return found

    def _clean_phone_candidate(self, raw_phone):
        if not raw_phone:
            return ""

        phone = raw_phone.strip()
        phone = re.sub(r"\s+", " ", phone)

        if "@" in phone:
            return ""

        digits_only = re.sub(r"\D", "", phone)
        if len(digits_only) < 7:
            return ""

        return phone

    def _normalize_phone(self, candidate, default_region=None, page_type=""):
        region = self._normalize_region(default_region)

        parse_attempts = []

        if candidate.startswith("+") or candidate.startswith("00"):
            parse_attempts.append((candidate, None))
        else:
            if region:
                parse_attempts.append((candidate, region))
            else:
                parse_attempts.append((candidate, None))

        for raw_value, parse_region in parse_attempts:
            try:
                parsed = phonenumbers.parse(raw_value, parse_region)
            except NumberParseException:
                continue

            if not phonenumbers.is_possible_number(parsed):
                continue

            if not phonenumbers.is_valid_number(parsed):
                continue

            normalized = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)

            confidence = 0.72
            if page_type == "contact":
                confidence = 0.85
            elif page_type == "homepage":
                confidence = 0.78

            return normalized, confidence

        return None, 0.0

    def _normalize_region(self, region):
        if not region:
            return None

        region = str(region).strip().upper()
        return self.DEFAULT_REGION_BY_COUNTRY_HINT.get(region, region)

    # --------------------------------------------------
    # Fallback contact page
    # --------------------------------------------------

    def _extract_contact_page_fallback(self, pages):
        for page in pages:
            page_type = (page.get("page_type") or "").lower()
            page_url = page.get("url") or ""

            if page_type == "contact" and page_url:
                return {
                    "contact_type": "contact_page",
                    "value": page_url,
                    "source_url": page_url,
                    "confidence": 0.5,
                    "is_primary": False,
                }

        return None

    # --------------------------------------------------
    # Dedupe / ranking
    # --------------------------------------------------

    def _dedupe_contacts(self, contacts):
        deduped = []
        seen = set()

        for contact in contacts or []:
            contact_type = (contact.get("contact_type") or "none").strip().lower()
            value = (contact.get("value") or "").strip()

            key = (contact_type, value.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(contact)

        return deduped

    def _mark_primary_contact(self, contacts):
        if not contacts:
            return contacts

        def rank(contact):
            contact_type = contact.get("contact_type") or "none"
            confidence = float(contact.get("confidence") or 0.0)

            type_rank = {
                "email": 4,
                "phone": 3,
                "contact_page": 2,
                "none": 1,
            }.get(contact_type, 0)

            return (type_rank, confidence)

        best_index = 0
        best_value = rank(contacts[0])

        for i in range(1, len(contacts)):
            current = rank(contacts[i])
            if current > best_value:
                best_value = current
                best_index = i

        output = []
        for i, contact in enumerate(contacts):
            item = dict(contact)
            item["is_primary"] = (i == best_index)
            output.append(item)

        return output

    def _none_contact(self):
        return {
            "contact_type": "none",
            "value": "",
            "source_url": "",
            "confidence": 0.0,
            "is_primary": False,
        }