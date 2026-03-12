# -*- coding: utf-8 -*-

import re
import unicodedata

from bs4 import BeautifulSoup


class VisiblePeopleCandidateExtractor(object):
    """
    Conservative, multi-domain, multi-language visible people candidate extractor.

    Goal:
    - extract only candidate people blocks
    - do NOT validate final truth
    - do NOT persist
    - let GeminiVisiblePeopleValidator do the final decision

    Preferred strategy:
    1. use raw_html when available
    2. extract from small local HTML/text blocks
    3. fallback to segmented extracted_text only if needed

    Output item:
    {
        "candidate_name": "...",
        "candidate_role_hint": "...",
        "source_url": "...",
        "page_title": "...",
        "context_before": "...",
        "context_line": "...",
        "context_after": "...",
    }
    """

    MAX_CANDIDATES = 25
    MAX_BLOCK_LENGTH = 700
    MAX_LINE_LENGTH = 260

    PERSON_PREFIXES = (
        "dr", "dr.", "docteur", "doctor", "dott.", "dottore",
        "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "mme", "m.", "mlle",
        "prof", "prof.", "pr",
    )

    ROLE_KEYWORDS = (
        # EN
        "founder", "co-founder", "cofounder", "owner", "manager", "director",
        "head", "lead", "specialist", "consultant", "advisor", "partner",
        "engineer", "developer", "designer", "technician", "mechanic",
        "sales", "account manager", "curator", "conservator", "guide",
        "archivist", "receptionist", "assistant", "coordinator", "operator",
        "practitioner", "staff", "member", "expert", "surgeon",
        "dentist", "doctor", "dr", "professor", "prof", "lawyer", "attorney",
        "notary", "architect", "veterinarian", "therapist", "clinician",

        # FR
        "fondateur", "fondatrice", "cofondateur", "cofondatrice", "gérant",
        "gérante", "responsable", "directeur", "directrice", "chef",
        "consultant", "consultante", "conseiller", "conseillère", "associé",
        "associée", "ingénieur", "développeur", "développeuse", "designer",
        "technicien", "technicienne", "commercial", "commerciale", "curateur",
        "conservateur", "conservatrice", "guide", "archiviste", "assistante",
        "assistant", "coordinateur", "coordinatrice", "opérateur", "opératrice",
        "membre", "expert", "experte", "chirurgien", "chirurgienne",
        "dentiste", "docteur", "dr", "professeur", "avocat", "avocate",
        "notaire", "architecte", "vétérinaire", "thérapeute", "clinicien",
        "clinicienne", "secrétariat", "praticien", "praticienne",

        # IT
        "fondatore", "fondatrice", "responsabile", "direttore", "direttrice",
        "capo", "consulente", "partner", "ingegnere", "sviluppatore",
        "designer", "tecnico", "commerciale", "curatore", "conservatore",
        "guida", "archivista", "assistente", "coordinatore", "operatore",
        "membro", "esperto", "chirurgo", "dentista", "dottore",
        "dr", "professore", "avvocato", "notaio", "architetto", "veterinario",
    )

    TEAM_CONTEXT_KEYWORDS = (
        "our team", "meet the team", "meet our team", "team of experts",
        "our experts", "our practitioners", "our staff", "discover the team",
        "notre équipe", "notre equipe", "rencontrez l'équipe",
        "rencontrez notre équipe", "nos experts", "nos praticiens",
        "découvrir l'équipe", "decouvrir l'equipe", "l'équipe du cabinet",
        "il nostro team", "incontra il team", "i nostri esperti",
    )

    UI_NOISE_KEYWORDS = (
        "menu", "blog", "search", "rechercher", "home", "accueil",
        "contact us", "follow us", "instagram", "facebook", "linkedin",
        "privacy", "cookies", "faq", "about us", "about", "book", "booking",
        "prendre rendez-vous", "rendez-vous", "appointment", "appointments",
        "find out more", "learn more", "en savoir plus", "gérer le consentement",
        "gerer le consentement",
    )

    LEGAL_NOISE_KEYWORDS = (
        "copyright", "mentions légales", "mentions legales", "terms",
        "legal", "legal notice", "all rights reserved",
    )

    LOCATION_NOISE_KEYWORDS = (
        "avenue", "boulevard", "street", "road", "rue", "place",
        "gare", "station", "métro", "metro", "line", "ligne",
    )

    INSTITUTION_NOISE_KEYWORDS = (
        "hospital", "hôpital", "hopital", "university", "université",
        "universite", "ordre national", "national order", "museum",
        "musée", "musee",
    )

    EDUCATION_NOISE_KEYWORDS = (
        "certification", "certificate", "diplôme", "diplome", "degree",
        "award", "thèse", "these", "lauréat", "laureat", "formation",
    )

    GENERIC_HEADING_NOISE_KEYWORDS = (
        "services", "soins", "care", "staff", "experts", "practitioners",
        "selection", "choisir", "sélectionnez", "selectionnez",
    )

    ADDRESS_TERMS = (
        "avenue", "street", "road", "boulevard", "rue", "place",
        "postcode", "code postal", "zip", "ville", "city", "cedex",
        "gare", "station", "metro", "métro",
    )

    SKIP_CONTAINER_HINTS = (
        "nav", "menu", "footer", "header", "breadcrumb", "sidebar",
        "cookie", "newsletter", "legal", "copyright", "social",
    )

    MULTISPACE_RE = re.compile(r"\s+")
    EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
    PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{6,}\d)")
    URL_RE = re.compile(r"https?://|www\.", re.I)
    YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

    NAME_TOKEN = r"[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-\.\u0152\u0153]+"
    NAME_PATTERN = re.compile(
        r"\b(" + NAME_TOKEN + r"(?:\s+" + NAME_TOKEN + r"){1,3})\b"
    )

    def extract_candidates(self, pages):
        pages = pages or []
        if isinstance(pages, dict):
            pages = [pages]

        candidates = []
        seen = set()

        for page in pages:
            page_candidates = self.extract_candidates_from_page(page)

            for item in page_candidates:
                key = self._candidate_key(item)
                if not key[0]:
                    continue
                if key in seen:
                    continue

                seen.add(key)
                candidates.append(item)

                if len(candidates) >= self.MAX_CANDIDATES:
                    return candidates

        return candidates

    def extract_candidates_from_page(self, page):
        raw_html = (
            page.get("raw_html")
            or page.get("html")
            or page.get("body_html")
            or page.get("content_html")
            or ""
        )
        extracted_text = self._normalize_text(
            page.get("extracted_text")
            or page.get("site_text")
            or page.get("text")
            or ""
        )
        source_url = (
            page.get("source_url")
            or page.get("final_url")
            or page.get("url")
            or page.get("page_url")
            or ""
        )
        page_title = self._normalize_text(page.get("page_title") or page.get("title") or "")

        if raw_html:
            html_candidates = self._extract_from_html(
                raw_html=raw_html,
                source_url=source_url,
                page_title=page_title,
            )
            if html_candidates:
                return html_candidates

        if extracted_text:
            return self._extract_from_text(
                text=extracted_text,
                source_url=source_url,
                page_title=page_title,
            )

        return []

    # --------------------------------------------------
    # HTML-first extraction
    # --------------------------------------------------

    def _extract_from_html(self, raw_html, source_url="", page_title=""):
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except Exception:
            return []

        self._remove_noise_nodes(soup)

        if not page_title:
            title_tag = soup.find("title")
            if title_tag:
                page_title = self._normalize_text(title_tag.get_text(" ", strip=True))

        body = soup.find("main") or soup.find("body") or soup
        blocks = self._collect_local_blocks(body)

        results = []
        seen = set()

        for lines in blocks:
            block_candidates = self._extract_candidates_from_lines(
                lines=lines,
                source_url=source_url,
                page_title=page_title,
            )

            for item in block_candidates:
                key = self._candidate_key(item)
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)

                if len(results) >= self.MAX_CANDIDATES:
                    return results

        return results

    def _remove_noise_nodes(self, soup):
        for tag_name in (
            "script", "style", "noscript", "svg", "iframe",
            "form", "input", "button", "select", "option", "textarea",
        ):
            for tag in soup.find_all(tag_name):
                tag.decompose()

        for node in soup.find_all(True):
            class_names = " ".join(node.get("class", []) or []).lower()
            node_id = (node.get("id") or "").lower()
            signature = "%s %s %s" % (node.name.lower(), class_names, node_id)

            if any(hint in signature for hint in self.SKIP_CONTAINER_HINTS):
                node.decompose()

    def _collect_local_blocks(self, body):
        tags = ("article", "section", "div", "li", "p", "td")
        blocks = []

        for node in body.find_all(tags):
            text = self._normalize_text(node.get_text("\n", strip=True))
            if not text:
                continue

            if len(text) < 15 or len(text) > self.MAX_BLOCK_LENGTH:
                continue

            lines = self._normalize_lines(text.split("\n"))
            if not lines:
                continue

            if self._looks_like_noise_block(lines):
                continue

            blocks.append(lines)

        return blocks

    # --------------------------------------------------
    # Flattened-text fallback
    # --------------------------------------------------

    def _extract_from_text(self, text, source_url="", page_title=""):
        segments = self._segment_text(text)
        results = []
        seen = set()

        for idx, segment in enumerate(segments):
            if not self._segment_has_people_anchor(segment):
                continue

            extracted = self._extract_from_segment(
                segment=segment,
                prev_segment=segments[idx - 1] if idx > 0 else "",
                next_segment=segments[idx + 1] if idx + 1 < len(segments) else "",
                source_url=source_url,
                page_title=page_title,
            )

            for item in extracted:
                key = self._candidate_key(item)
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)

                if len(results) >= self.MAX_CANDIDATES:
                    return results

        return results

    def _segment_text(self, text):
        if not text:
            return []

        text = text.replace(" | ", "\n")
        text = text.replace(" • ", "\n")
        text = text.replace(" · ", "\n")
        text = text.replace(" — ", "\n")
        text = re.sub(r"\s*\|\s*", "\n", text)
        text = re.sub(r"\s{2,}", " ", text)

        raw_parts = re.split(r"(?:\n+|(?<=[\.\!\?])\s+(?=[A-ZÀ-ÖØ-Ý]))", text)

        segments = []
        for part in raw_parts:
            part = self._normalize_text(part)
            if not part:
                continue
            if len(part) < 8:
                continue
            if len(part) > self.MAX_BLOCK_LENGTH:
                continue
            segments.append(part)

        return segments

    # --------------------------------------------------
    # Candidate extraction
    # --------------------------------------------------

    def _extract_candidates_from_lines(self, lines, source_url="", page_title=""):
        output = []
        seen = set()

        for idx, line in enumerate(lines):
            if len(line) < 4 or len(line) > self.MAX_LINE_LENGTH:
                continue

            prev_line = lines[idx - 1] if idx > 0 else ""
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            next_next_line = lines[idx + 2] if idx + 2 < len(lines) else ""

            window_text = " | ".join([prev_line, line, next_line, next_next_line])

            if not self._segment_has_people_anchor(window_text):
                continue

            names = self.NAME_PATTERN.findall(line) or []
            prefixed_names = self._extract_prefixed_names(line)
            for name in prefixed_names:
                if name not in names:
                    names.append(name)

            if not names and self._has_strong_person_identity(line):
                names = self.NAME_PATTERN.findall(line) or []

            role_hint = self._extract_role_hint_from_window(lines, idx)

            for name in names:
                cleaned = self._clean_candidate_name(name)
                if not cleaned:
                    continue
                if self._looks_like_noise_name(cleaned):
                    continue
                if not self._name_has_human_shape(cleaned):
                    continue

                if not self._passes_filters(
                    candidate_name=cleaned,
                    context_before=prev_line,
                    context_line=line,
                    context_after=" | ".join([next_line, next_next_line]).strip(" |"),
                    role_hint=role_hint,
                    page_title=page_title,
                ):
                    continue

                item = {
                    "candidate_name": cleaned,
                    "candidate_role_hint": role_hint,
                    "source_url": source_url,
                    "page_title": page_title,
                    "context_before": prev_line[:300],
                    "context_line": line[:500],
                    "context_after": " | ".join([x for x in [next_line, next_next_line] if x])[:300],
                }

                item_key = self._candidate_key(item)
                if item_key in seen:
                    continue

                seen.add(item_key)
                output.append(item)

        return output

    def _extract_from_segment(self, segment, prev_segment, next_segment, source_url, page_title=""):
        output = []

        if self._is_noise_segment(segment):
            return output

        names = self.NAME_PATTERN.findall(segment) or []
        prefixed_names = self._extract_prefixed_names(segment)

        for name in prefixed_names:
            if name not in names:
                names.append(name)

        if not names:
            return output

        role_hint = self._extract_role_hint(segment)

        for name in names:
            cleaned = self._clean_candidate_name(name)
            if not cleaned:
                continue
            if self._looks_like_noise_name(cleaned):
                continue
            if not self._name_has_human_shape(cleaned):
                continue

            if not self._passes_filters(
                candidate_name=cleaned,
                context_before=prev_segment,
                context_line=segment,
                context_after=next_segment,
                role_hint=role_hint,
                page_title=page_title,
            ):
                continue

            output.append({
                "candidate_name": cleaned,
                "candidate_role_hint": role_hint,
                "source_url": source_url,
                "page_title": page_title,
                "context_before": prev_segment[:300],
                "context_line": segment[:500],
                "context_after": next_segment[:300],
            })

        return output

    def _extract_prefixed_names(self, segment):
        found = []

        for prefix in self.PERSON_PREFIXES:
            pattern = re.compile(
                r"\b%s\s+([A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-\.\u0152\u0153]+"
                r"(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'’\-\.\u0152\u0153]+){0,2})\b" % re.escape(prefix),
                re.IGNORECASE
            )
            matches = pattern.findall(segment) or []

            for match in matches:
                full = ("%s %s" % (prefix, match)).strip()
                found.append(self._normalize_spacing(full))

        return found

    def _extract_role_hint_from_window(self, lines, idx):
        window_lines = []

        for offset in (-1, 0, 1, 2):
            line_idx = idx + offset
            if line_idx < 0 or line_idx >= len(lines):
                continue
            window_lines.append(self._normalize_text(lines[line_idx]))

        # First, look for explicit role lines around the name line.
        for nearby in window_lines:
            role_hint = self._extract_role_hint(nearby)
            if role_hint:
                return role_hint

        # Then, combine adjacent short non-name lines after the name.
        combined = []
        for offset in (1, 2):
            line_idx = idx + offset
            if line_idx < 0 or line_idx >= len(lines):
                continue
            candidate = self._normalize_text(lines[line_idx])
            if not candidate:
                continue
            if self.NAME_PATTERN.search(candidate):
                continue
            if len(candidate) > 80:
                continue
            if self._looks_like_role_text(candidate) or not self._is_noise_segment(candidate):
                combined.append(candidate)

        if combined:
            combined_text = " | ".join(combined[:2])
            if len(combined_text) <= 160:
                return combined_text

        return ""

    def _extract_role_hint(self, segment):
        segment = self._normalize_text(segment)
        if not segment:
            return ""

        segment_lower = segment.lower()

        matched_roles = []
        for keyword in self.ROLE_KEYWORDS:
            if keyword in segment_lower:
                matched_roles.append(keyword)

        if matched_roles:
            matched_roles.sort(key=lambda x: len(x), reverse=True)
            return matched_roles[0][:120]

        parts = [p.strip() for p in re.split(r"[\|\-–—:/]", segment) if p.strip()]
        if len(parts) >= 2:
            candidate = parts[1]
            if 2 <= len(candidate) <= 120 and not self._is_noise_segment(candidate):
                if self._looks_like_role_text(candidate):
                    return candidate

        return ""

    # --------------------------------------------------
    # Heuristics
    # --------------------------------------------------

    def _segment_has_people_anchor(self, segment):
        s = (segment or "").lower()

        for keyword in self.ROLE_KEYWORDS:
            if keyword in s:
                return True

        for keyword in self.TEAM_CONTEXT_KEYWORDS:
            if keyword in s:
                return True

        for prefix in self.PERSON_PREFIXES:
            if re.search(r"\b%s\b" % re.escape(prefix), s):
                return True

        if self.NAME_PATTERN.search(segment):
            if len(segment) <= 220 and self._looks_like_name_context(segment):
                return True

        return False

    def _passes_filters(self, candidate_name, context_before, context_line, context_after, role_hint, page_title):
        joined = " | ".join([
            page_title or "",
            context_before or "",
            context_line or "",
            context_after or "",
            role_hint or "",
        ]).lower()

        if self._is_probable_address_context(context_line):
            if not role_hint and not self._has_strong_person_identity(candidate_name):
                return False

        if self._contains_strong_negative_context(joined):
            if not role_hint and not self._has_strong_person_identity(candidate_name):
                return False

        positive_signals = 0

        if self._has_strong_person_identity(candidate_name):
            positive_signals += 1

        if role_hint:
            positive_signals += 1

        if self._has_team_context(joined):
            positive_signals += 1

        if self._looks_like_name_context(" | ".join([context_line or "", context_after or ""])):
            positive_signals += 1

        return positive_signals > 0

    def _is_noise_segment(self, segment):
        s = (segment or "").strip()
        sl = s.lower()

        if not s:
            return True

        if len(s) > self.MAX_BLOCK_LENGTH:
            return True

        digits = len(re.findall(r"\d", s))
        if digits >= 8:
            return True

        if "http" in sl or "www." in sl:
            return True

        if s.count("|") >= 6:
            return True

        if self._contains_strong_negative_context(sl):
            if self._has_strong_person_identity(s):
                return False
            return True

        return False

    def _contains_strong_negative_context(self, lower_text):
        negative_hits = 0

        for bucket in (
            self.UI_NOISE_KEYWORDS,
            self.LEGAL_NOISE_KEYWORDS,
            self.LOCATION_NOISE_KEYWORDS,
            self.INSTITUTION_NOISE_KEYWORDS,
            self.EDUCATION_NOISE_KEYWORDS,
            self.GENERIC_HEADING_NOISE_KEYWORDS,
        ):
            for keyword in bucket:
                if keyword in lower_text:
                    negative_hits += 1
                    break

        return negative_hits >= 2

    def _has_strong_person_identity(self, text):
        tl = (text or "").lower()
        has_prefix = any(re.search(r"\b%s\b" % re.escape(prefix), tl) for prefix in self.PERSON_PREFIXES)
        has_name = bool(self.NAME_PATTERN.search(text or ""))
        return has_prefix and has_name

    def _has_team_context(self, lower_text):
        for keyword in self.TEAM_CONTEXT_KEYWORDS:
            if keyword in lower_text:
                return True
        return False

    def _looks_like_role_text(self, text):
        text = self._normalize_text(text)
        if not text:
            return False

        if len(text) > 120:
            return False

        if self.EMAIL_RE.search(text) or self.URL_RE.search(text):
            return False

        lower_text = text.lower()
        for keyword in self.ROLE_KEYWORDS:
            if keyword in lower_text:
                return True

        return False

    def _looks_like_name_context(self, line):
        line = self._normalize_text(line)
        if not line:
            return False

        if self.NAME_PATTERN.search(line) and (
            " | " in line or
            " - " in line or
            " – " in line or
            ", " in line or
            ":" in line
        ):
            return True

        if self.NAME_PATTERN.search(line) and self._has_team_context(line.lower()):
            return True

        if self.NAME_PATTERN.search(line):
            for keyword in self.ROLE_KEYWORDS:
                if keyword in line.lower():
                    return True

        return False

    def _looks_like_noise_name(self, name):
        nl = (name or "").strip().lower()

        if not nl:
            return True

        if re.search(r"\d", name):
            return True

        if len(name) > 80:
            return True

        for bucket in (
            self.UI_NOISE_KEYWORDS,
            self.LEGAL_NOISE_KEYWORDS,
            self.LOCATION_NOISE_KEYWORDS,
            self.INSTITUTION_NOISE_KEYWORDS,
            self.EDUCATION_NOISE_KEYWORDS,
        ):
            for noise in bucket:
                if noise in nl:
                    return True

        if name.isupper() and len(name.split()) <= 4:
            return True

        return False

    def _name_has_human_shape(self, name):
        tokens = [t for t in re.split(r"\s+", name.strip()) if t]
        if len(tokens) < 2 or len(tokens) > 4:
            return False

        short_tokens = sum(1 for t in tokens if len(t) <= 1)
        if short_tokens >= 2:
            return False

        if self.YEAR_RE.search(name):
            return False

        if self.EMAIL_RE.search(name) or self.URL_RE.search(name):
            return False

        return True

    def _is_probable_address_context(self, text):
        text = self._normalize_text(text).lower()
        if not text:
            return False

        for term in self.ADDRESS_TERMS:
            if term in text:
                return True

        if re.search(r"\b\d{4,6}\b", text):
            return True

        return False

    def _looks_like_noise_block(self, lines):
        if not lines:
            return True

        if len(lines) >= 8:
            short_count = len([x for x in lines if len(x) <= 24])
            if short_count >= 5:
                return True

        return False

    # --------------------------------------------------
    # Cleaning / helpers
    # --------------------------------------------------

    def _clean_candidate_name(self, value):
        value = self._normalize_spacing(value)
        value = value.strip(" |,-–—:/")

        parts = []
        for token in value.split():
            token_low = token.lower()
            if token_low in self.PERSON_PREFIXES:
                parts.append(token)
            elif token.isupper() and len(token) > 2:
                parts.append(token.title())
            else:
                parts.append(token.strip())

        value = " ".join(parts)
        value = value[:120].strip()
        return value

    def _normalize_lines(self, lines):
        out = []
        previous = None

        for line in lines:
            line = self._normalize_text(line)
            if not line:
                continue
            if len(line) > self.MAX_LINE_LENGTH:
                continue
            if line == previous:
                continue

            out.append(line)
            previous = line

        return out

    def _normalize_text(self, value):
        if value is None:
            return ""
        value = str(value)
        value = unicodedata.normalize("NFKC", value)
        value = value.replace("\xa0", " ")
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _normalize_spacing(self, value):
        value = value or ""
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _candidate_key(self, item):
        return (
            (item.get("candidate_name") or "").strip().lower(),
            (item.get("candidate_role_hint") or "").strip().lower(),
            (item.get("source_url") or "").strip().lower(),
            (item.get("context_line") or "").strip().lower(),
        )