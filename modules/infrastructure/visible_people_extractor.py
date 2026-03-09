# -*- coding: utf-8 -*-

import re

from bs4 import BeautifulSoup


class VisiblePeopleExtractorError(Exception):
    """Raised when visible people extraction fails unexpectedly."""
    pass


class VisiblePeopleExtractor(object):
    """
    Generic extractor for visible people mentioned on public pages.

    Goals:
    - extract human names explicitly visible on the page
    - optionally capture a nearby visible role/title
    - stay domain-agnostic (doctors, garages, museums, IT firms, etc.)
    - stay language-agnostic enough for common FR / EN / IT style pages
    - avoid turning long prose or business names into fake people
    """

    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}

    HONORIFIC_PATTERNS = [
        re.compile(
            r"\b(?:dr\.?|doctor|docteur|dott\.?|prof\.?|professor|professeur|mr\.?|mrs\.?|ms\.?|mme|mlle|m\.|maître|avv\.?|ing\.?|sir|lady)\s+([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-\s]{1,80})",
            re.IGNORECASE | re.UNICODE,
        ),
    ]

    # Bare-name pattern:
    # supports:
    # - Ralph BADAOUI
    # - Joseph NAMMOUR
    # - Maxime Lucas
    # - Maria del Carmen Rossi
    # - Jean de La Fontaine
    BARE_NAME_PATTERN = re.compile(
        r"\b("
        r"[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+"
        r"(?:\s+(?:de|del|della|di|du|des|da|van|von|bin|ibn|la|le))?"
        r"(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+){1,3}"
        r")\b",
        re.UNICODE,
    )

    BAD_NAME_FRAGMENTS = (
        "contact us",
        "contactez",
        "follow on",
        "instagram",
        "facebook",
        "linkedin",
        "google",
        "review",
        "reviews",
        "avis",
        "read more",
        "lire la suite",
        "your first name",
        "your last name",
        "first name",
        "last name",
        "prénom",
        "nom",
        "message",
        "envoyer",
        "send",
        "appointment",
        "booking",
        "rendez-vous",
        "phone number",
        "téléphone",
        "email",
        "adresse",
        "address",
        "opening hours",
        "horaires",
        "monday",
        "saturday",
        "copyright",
        "privacy",
        "terms",
        "cabinet dentaire",
        "dental clinic",
        "practice",
        "clinic",
        "museum",
        "garage",
        "agency",
        "studios",
        "hospital",
    )

    BAD_LINE_HINTS = (
        "google",
        "avis",
        "review",
        "reviews",
        "profile picture",
        "il y a",
        "year ago",
        "years ago",
        "lire la suite",
        "read more",
        "contact us",
        "contactez",
        "follow on",
        "instagram",
        "facebook",
        "linkedin",
        "your first name",
        "your last name",
        "prénom",
        "nom",
        "message",
        "envoyer",
        "send",
        "monday",
        "saturday",
        "09.30am",
        "copyright",
        "privacy",
        "terms",
    )

    BAD_BUSINESS_TOKENS = (
        "clinic",
        "cabinet",
        "agency",
        "museum",
        "garage",
        "hospital",
        "center",
        "centre",
        "studio",
        "studios",
        "company",
        "entreprise",
        "sarl",
        "sas",
        "inc",
        "llc",
        "ltd",
        "gmbh",
        "spa",
        "s.p.a",
        "srl",
    )

    LOWERCASE_PARTICLES = {
        "de", "del", "della", "di", "du", "des", "da", "van", "von", "bin", "ibn", "la", "le"
    }

    def extract_visible_people(self, pages):
        people = []
        seen = set()

        for page in pages or []:
            raw_html = page.get("raw_html") or ""
            page_url = page.get("url") or ""
            loaded = bool(page.get("loaded"))

            if not raw_html or not loaded:
                continue

            try:
                soup = BeautifulSoup(raw_html, "html.parser")
            except Exception:
                continue

            for tag_name in self.SKIP_TAGS:
                for tag in soup.find_all(tag_name):
                    tag.decompose()

            lines = self._build_candidate_lines(soup)
            if not lines:
                continue

            for idx, line in enumerate(lines):
                line_clean = self._normalize_space(line)
                if not line_clean:
                    continue

                if self._looks_like_bad_line(line_clean):
                    continue

                names = self._extract_names_from_line(line_clean, lines, idx)
                if not names:
                    continue

                context_window = self._build_context_window(lines, idx)

                for raw_name in names:
                    full_name = self._normalize_person_name(raw_name)
                    if not full_name:
                        continue

                    if self._looks_like_bad_name(full_name):
                        continue

                    role_text = self._extract_role_from_context(context_window, full_name)
                    evidence_text = self._build_evidence_text(context_window)

                    confidence = 0.88 if role_text else 0.72

                    dedupe_key = (
                        full_name.lower(),
                        role_text.lower(),
                        page_url.lower(),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    people.append({
                        "full_name": full_name,
                        "role_text": role_text,
                        "source_url": page_url,
                        "evidence_text": evidence_text,
                        "confidence": confidence,
                    })

        return self._dedupe_people(people)

    # --------------------------------------------------
    # Build lines
    # --------------------------------------------------

    def _build_candidate_lines(self, soup):
        lines = []

        # visible text
        for s in soup.stripped_strings:
            line = self._normalize_space(s)
            if not line:
                continue
            if len(line) > 180:
                continue
            lines.append(line)

        # useful attributes that often contain names
        for tag in soup.find_all(True):
            for attr_name in ("alt", "title", "aria-label"):
                attr_value = tag.get(attr_name)
                if not attr_value:
                    continue

                line = self._normalize_space(attr_value)
                if not line:
                    continue
                if len(line) > 180:
                    continue

                lines.append(line)

        return self._dedupe_lines(lines)

    def _dedupe_lines(self, lines):
        output = []
        seen = set()

        for line in lines or []:
            clean = self._normalize_space(line)
            if not clean:
                continue

            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(clean)

        return output

    # --------------------------------------------------
    # Name extraction
    # --------------------------------------------------

    def _extract_names_from_line(self, line, all_lines, idx):
        names = []

        # 1. explicit honorific names first
        for pattern in self.HONORIFIC_PATTERNS:
            for match in pattern.findall(line or ""):
                candidate = self._normalize_space(match)
                if candidate:
                    names.append(candidate)

        if names:
            return names

        # 2. bare names only if context supports "person-ness"
        if not self._has_person_like_context(all_lines, idx):
            return []

        for match in self.BARE_NAME_PATTERN.findall(line or ""):
            candidate = self._normalize_space(match)
            if candidate:
                names.append(candidate)

        return names

    def _has_person_like_context(self, lines, idx):
        window = self._build_context_window(lines, idx)

        for line in window:
            line_lower = line.lower()

            # role-ish nearby line: short descriptive line without contact noise
            if self._looks_like_role_line(line):
                return True

            # explicit visual hints of a person block
            if any(hint in line_lower for hint in (
                "team",
                "our team",
                "meet",
                "practitioner",
                "practitioners",
                "expert",
                "experts",
                "staff",
                "équipe",
                "notre équipe",
                "expertise",
                "photo",
                "portrait",
                "bio",
            )):
                return True

        return False

    def _normalize_person_name(self, raw_name):
        raw_name = self._normalize_space(raw_name)

        # trim common separators
        raw_name = re.split(r"[|,;:/()]", raw_name)[0].strip()

        # remove honorific if still present
        raw_name = re.sub(
            r"^(?:dr\.?|doctor|docteur|dott\.?|prof\.?|professor|professeur|mr\.?|mrs\.?|ms\.?|mme|mlle|m\.|maître|avv\.?|ing\.?|sir|lady)\s+",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()

        raw_name = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ'’\-\s]", "", raw_name)
        raw_name = self._normalize_space(raw_name)

        if not raw_name:
            return ""

        words = raw_name.split()

        if len(words) < 2:
            return ""
        if len(words) > 5:
            return ""

        lowered_full = raw_name.lower()

        if any(fragment in lowered_full for fragment in self.BAD_NAME_FRAGMENTS):
            return ""

        if any(token in lowered_full for token in self.BAD_BUSINESS_TOKENS):
            return ""

        # reject obviously prose-like names
        if len(lowered_full) > 60:
            return ""

        normalized_words = []
        for word in words:
            word_lower = word.lower()

            if word_lower in self.LOWERCASE_PARTICLES:
                normalized_words.append(word_lower)
            elif word.isupper() and len(word) > 1:
                normalized_words.append(word.title())
            else:
                normalized_words.append(word)

        final_name = " ".join(normalized_words).strip()
        return final_name[:255]

    def _looks_like_bad_name(self, value):
        lower = (value or "").lower()

        if any(fragment in lower for fragment in self.BAD_NAME_FRAGMENTS):
            return True

        # too many words that feel like a sentence
        if len(value.split()) > 5:
            return True

        return False

    # --------------------------------------------------
    # Context / role / evidence
    # --------------------------------------------------

    def _build_context_window(self, lines, idx):
        start = max(0, idx - 1)
        end = min(len(lines), idx + 3)
        return lines[start:end]

    def _extract_role_from_context(self, context_lines, full_name):
        for line in context_lines:
            line_clean = self._normalize_space(line)
            if not line_clean:
                continue

            if line_clean.lower() == full_name.lower():
                continue

            if self._looks_like_role_line(line_clean):
                return line_clean[:255]

        return ""

    def _looks_like_role_line(self, line):
        line_clean = self._normalize_space(line)
        line_lower = line_clean.lower()

        if not line_clean:
            return False

        if len(line_clean) > 120:
            return False

        if self._looks_like_bad_line(line_clean):
            return False

        if "@" in line_clean:
            return False

        if "http://" in line_lower or "https://" in line_lower:
            return False

        if re.search(r"\b\d{2}(?:[\s\.\-]?\d{2}){4}\b", line_clean):
            return False

        # a role line is typically short, descriptive, and not a paragraph
        word_count = len(line_clean.split())
        if word_count < 1 or word_count > 12:
            return False

        # avoid likely pure company / nav lines
        if any(token in line_lower for token in self.BAD_BUSINESS_TOKENS):
            return False

        return True

    def _build_evidence_text(self, context_lines):
        compact = []
        for line in context_lines:
            line_clean = self._normalize_space(line)
            if not line_clean:
                continue
            if len(line_clean) > 180:
                continue
            compact.append(line_clean)

        return " | ".join(compact)[:500]

    def _looks_like_bad_line(self, line):
        line_lower = (line or "").lower()

        if not line_lower:
            return True

        if any(hint in line_lower for hint in self.BAD_LINE_HINTS):
            return True

        return False

    # --------------------------------------------------
    # Final dedupe / utils
    # --------------------------------------------------

    def _dedupe_people(self, people):
        output = []
        seen = set()

        for person in people or []:
            full_name = (person.get("full_name") or "").strip()
            role_text = (person.get("role_text") or "").strip()

            if not full_name:
                continue

            key = (full_name.lower(), role_text.lower())
            if key in seen:
                continue
            seen.add(key)
            output.append(person)

        return output

    def _normalize_space(self, value):
        value = value or ""
        value = re.sub(r"\s+", " ", value).strip()
        return value