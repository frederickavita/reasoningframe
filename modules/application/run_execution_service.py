# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import re
from urllib.parse import urlparse

from gluon.storage import Storage


class RunExecutionServiceError(Exception):
    """Raised when the end-to-end run pipeline fails."""
    pass


class RunExecutionService(object):
    """
    Executes the full OutreachBrowser pipeline for one prospect_run:

    1. Validate run can be processed
    2. Build search query
    3. Search businesses
    4. Filter / deduplicate candidates
    5. Create prospect rows
    6. Fetch homepage + contact page
    7. Extract public contacts
    8. Extract visible people candidates
    9. Validate visible people with Gemini
    10. Evaluate simple rule signals
    11. Enrich with Gemini
    12. Persist artifacts / signals / qualification
    13. Finalize run as locked preview
    """

    EXCLUDED_HOST_PATTERNS = (
        "pagesjaunes",
        "yelp.",
        "tripadvisor.",
        "facebook.",
        "instagram.",
        "linkedin.",
        "x.com",
        "twitter.",
        "youtube.",
        "wikipedia.",
        "annuaire",
        "yellowpages",
        "justdial",
        "trustpilot",
        "mapquest",
        "foursquare",
    )

    CRITERION_SYNONYMS = {
        "booking": [
            "booking",
            "book",
            "appointment",
            "appointments",
            "book online",
            "online booking",
            "rendez-vous",
            "prise de rendez-vous",
            "prendre rendez-vous",
            "prendre un rendez-vous",
            "rdv",
            "doctolib",
        ],
        "quote": [
            "quote",
            "free quote",
            "get a quote",
            "devis",
            "demande de devis",
            "obtenir un devis",
            "devis gratuit",
        ],
        "form": [
            "form",
            "forms",
            "contact form",
            "lead form",
            "formulaire",
            "formulaires",
            "formulaire de contact",
            "formulaire de demande",
        ],
        "contact": [
            "contact",
            "contact us",
            "get in touch",
            "contactez-nous",
            "nous contacter",
        ],
        "appointment": [
            "appointment",
            "appointments",
            "rendez-vous",
            "prise de rendez-vous",
            "prendre rendez-vous",
            "rdv",
            "doctolib",
        ],
    }

    VISIBLE_PEOPLE_MIN_CONFIDENCE = 0.90

    def __init__(
        self,
        db,
        run_service,
        prospect_service,
        search_provider,
        web_page_fetcher,
        contact_extractor,
        llm_client,
        visible_people_candidate_extractor=None,
        visible_people_validator=None,
        default_phone_region="FR",
        session=None
    ):
        self.db = db
        self.session = session
        self.run_service = run_service
        self.prospect_service = prospect_service
        self.search_provider = search_provider
        self.web_page_fetcher = web_page_fetcher
        self.contact_extractor = contact_extractor
        self.llm_client = llm_client
        self.visible_people_candidate_extractor = visible_people_candidate_extractor
        self.visible_people_validator = visible_people_validator
        self.default_phone_region = default_phone_region

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def execute_run(self, run_id):
        run = self.run_service.get_run_or_fail(run_id)
        self.run_service.ensure_run_can_be_processed(run.id)

        try:
            parsed_criteria = self.run_service.get_run_parsed_criteria(run)

            self.run_service.update_status(run.id, "searching")
            self.db.commit()

            search_query = self._build_search_query(run)
            self.run_service.set_search_query_built(run.id, search_query)
            self.db.commit()

            raw_results = self.search_provider.search(
                search_query,
                limit=run.requested_result_limit,
            )

            candidates = self._prepare_candidates(raw_results)

            if not candidates:
                self.run_service.increment_error_count(
                    run.id,
                    amount=1,
                    last_error_message="No valid prospects discovered from search provider.",
                )
                self.run_service.mark_locked_preview(run.id)
                self.db.commit()
                return self.run_service.get_run_or_fail(run.id)

            created_prospects = self._create_candidate_prospects(run.id, run.city, candidates)
            self.run_service.increment_discovered_count(run.id, amount=len(created_prospects))
            self.db.commit()

            for prospect in created_prospects:
                self._process_one_prospect(run, prospect, parsed_criteria)
                self.run_service.increment_processed_count(run.id, amount=1)
                self.db.commit()

            self.run_service.mark_locked_preview(run.id)
            self.db.commit()

            return self.run_service.get_run_or_fail(run.id)

        except Exception as e:
            try:
                self.run_service.increment_error_count(
                    run.id,
                    amount=1,
                    last_error_message=str(e)[:1000],
                )
                self.run_service.update_status(run.id, "failed")
                self.db.commit()
            except Exception:
                pass

            raise RunExecutionServiceError(str(e))

    # --------------------------------------------------
    # Search phase
    # --------------------------------------------------

    def _build_search_query(self, run):
        parts = [
            self._clean_text(run.niche),
            self._clean_text(run.city),
        ]
        return " ".join([p for p in parts if p]).strip()

    def _prepare_candidates(self, raw_results):
        candidates = []
        seen_hosts = set()

        for item in raw_results or []:
            normalized = self._normalize_candidate(item)
            if not normalized:
                continue

            host = normalized.host
            if host in seen_hosts:
                continue

            seen_hosts.add(host)
            candidates.append(normalized)

        return candidates

    def _normalize_candidate(self, item):
        if not isinstance(item, dict):
            return None

        raw_url = self._clean_text(item.get("domain") or item.get("url") or "")
        if not raw_url:
            return None

        canonical_url = self._canonical_homepage_url(raw_url)
        if not canonical_url:
            return None

        parsed = urlparse(canonical_url)
        host = (parsed.netloc or "").lower().strip()
        if not host:
            return None

        host = host.replace("www.", "")

        if self._is_excluded_host(host):
            return None

        company_name = self._clean_text(item.get("company_name") or "")
        if not company_name:
            company_name = host

        return Storage(
            company_name=company_name[:255],
            domain=canonical_url,
            host=host,
            title=self._clean_text(item.get("title") or ""),
            snippet=self._clean_text(item.get("snippet") or ""),
        )

    def _canonical_homepage_url(self, raw_url):
        raw_url = self._clean_text(raw_url)
        if not raw_url:
            return ""

        if not re.match(r"^https?://", raw_url, flags=re.I):
            raw_url = "https://" + raw_url

        try:
            parsed = urlparse(raw_url)
        except Exception:
            return ""

        scheme = parsed.scheme or "https"
        host = (parsed.netloc or "").strip().lower()

        if not host:
            return ""

        host = host.replace("www.", "")
        return "%s://%s" % (scheme, host)

    def _is_excluded_host(self, host):
        host = (host or "").lower()
        for pattern in self.EXCLUDED_HOST_PATTERNS:
            if pattern in host:
                return True
        return False

    def _create_candidate_prospects(self, run_id, city, candidates):
        created = []

        for index, candidate in enumerate(candidates):
            prospect = self.prospect_service.create_prospect(
                run_id=run_id,
                company_name=candidate.company_name,
                domain=candidate.domain,
                city=city or "",
                render_order=index,
            )
            created.append(prospect)

        return created

    # --------------------------------------------------
    # Visible people / page scoping
    # --------------------------------------------------

    def _normalize_host(self, url):
        url = self._clean_text(url)
        if not url:
            return ""

        if not re.match(r"^https?://", url, flags=re.I):
            url = "https://" + url

        try:
            parsed = urlparse(url)
        except Exception:
            return ""

        host = (parsed.netloc or "").lower().strip()
        host = host.replace("www.", "")
        return host

    def _is_same_host(self, base_url, candidate_url):
        base_host = self._normalize_host(base_url)
        candidate_host = self._normalize_host(candidate_url)

        if not base_host or not candidate_host:
            return False

        return base_host == candidate_host

    def _select_business_pages(self, homepage_url, pages):
        """
        Only keep same-host pages for:
        - visible people extraction
        - site text sent to Gemini
        - rule text evaluation
        """
        selected = []

        for page in pages or []:
            page_url = self._clean_text(page.get("url") or "")
            loaded = bool(page.get("loaded"))

            if not loaded:
                continue

            if not page_url:
                continue

            if self._is_same_host(homepage_url, page_url):
                selected.append(page)

        return selected

    def _build_visible_people_business_context(self, run_row, prospect_row):
        llm_business_type = self._clean_text(getattr(prospect_row, "llm_business_type", "") or "")
        niche = self._clean_text(getattr(run_row, "niche", "") or "")
        city = self._clean_text(getattr(prospect_row, "city", "") or getattr(run_row, "city", "") or "")

        return {
            "business_type": llm_business_type or niche,
            "niche": niche,
            "city": city,
        }

    def _store_visible_people_debug(self, prospect_id, candidates, validations):
        if not self.session:
            return

        debug_store = getattr(self.session, "visible_people_debug_by_prospect", {}) or {}
        debug_store[str(prospect_id)] = {
            "candidates": candidates or [],
            "validations": validations or [],
        }
        self.session.visible_people_debug_by_prospect = debug_store

    def _extract_validate_and_persist_visible_people(self, run_row, prospect_row, pages):
        raw_candidates = []
        validation_results = []
        accepted_visible_people = []

        if not self.visible_people_candidate_extractor:
            self.prospect_service.replace_visible_people(
                prospect_id=prospect_row.id,
                visible_people=[],
            )
            self._store_visible_people_debug(
                prospect_id=prospect_row.id,
                candidates=[],
                validations=[],
            )
            return []

        raw_candidates = self.visible_people_candidate_extractor.extract_candidates(pages=pages) or []

        if not raw_candidates or not self.visible_people_validator:
            self.prospect_service.replace_visible_people(
                prospect_id=prospect_row.id,
                visible_people=[],
            )
            self._store_visible_people_debug(
                prospect_id=prospect_row.id,
                candidates=raw_candidates,
                validations=[],
            )
            return []

        business_context = self._build_visible_people_business_context(
            run_row=run_row,
            prospect_row=prospect_row,
        )

        for candidate in raw_candidates:
            try:
                result = self.visible_people_validator.validate_candidate(
                    candidate=candidate,
                    business_context=business_context,
                )
                validation_results.append({
                    "candidate": candidate,
                    "result": result,
                    "status": "ok",
                })

                if (
                    result.get("is_real_person") is True
                    and result.get("is_presented_as_working_for_business") is True
                    and float(result.get("confidence") or 0.0) >= self.VISIBLE_PEOPLE_MIN_CONFIDENCE
                ):
                    accepted_visible_people.append({
                        "full_name": self._clean_text(result.get("normalized_full_name", "")),
                        "role_text": self._clean_text(result.get("role_text", "")),
                        "source_url": self._clean_text(candidate.get("source_url", "")),
                        "evidence_text": self._clean_text(result.get("evidence_text", "")),
                        "confidence": float(result.get("confidence") or 0.0),
                    })

            except Exception as e:
                validation_results.append({
                    "candidate": candidate,
                    "result": {
                        "is_real_person": False,
                        "is_presented_as_working_for_business": False,
                        "normalized_full_name": "",
                        "role_text": "",
                        "evidence_text": "",
                        "confidence": 0.0,
                        "rejection_reason": self._clean_text(str(e))[:500],
                    },
                    "status": "error",
                })

        deduped = []
        seen = set()

        for item in accepted_visible_people:
            key = (
                (item.get("full_name") or "").strip().lower(),
                (item.get("role_text") or "").strip().lower(),
                (item.get("source_url") or "").strip().lower(),
            )
            if not key[0]:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        self.prospect_service.replace_visible_people(
            prospect_id=prospect_row.id,
            visible_people=deduped,
        )

        self._store_visible_people_debug(
            prospect_id=prospect_row.id,
            candidates=raw_candidates,
            validations=validation_results,
        )

        return deduped

    # --------------------------------------------------
    # Criteria helpers
    # --------------------------------------------------

    def _expand_criterion_needles(self, criterion_value):
        criterion_value = self._clean_text(criterion_value).lower()
        if not criterion_value:
            return []

        expanded = [criterion_value]

        if criterion_value in self.CRITERION_SYNONYMS:
            expanded.extend(self.CRITERION_SYNONYMS[criterion_value])

        seen = set()
        output = []
        for item in expanded:
            item = self._clean_text(item).lower()
            if not item:
                continue
            if item in seen:
                continue
            seen.add(item)
            output.append(item)

        return output

    def _find_first_matching_needle(self, haystack, needles):
        haystack = (haystack or "").lower()

        for needle in needles or []:
            if needle and needle in haystack:
                return needle

        return ""

    def _localized_signal_value(self, code, output_language):
        output_language = (output_language or "en").lower()

        fr_map = {
            "public_contact_found": "contact public visible",
            "contact_page_found": "page contact visible",
        }

        en_map = {
            "public_contact_found": "public contact visible",
            "contact_page_found": "contact page visible",
        }

        if output_language == "fr":
            return fr_map.get(code, code)

        return en_map.get(code, code)

    def _rule_reason(self, code, output_language="en", criterion_value="", matched_needle=""):
        output_language = (output_language or "en").lower()
        criterion_value = self._clean_text(criterion_value)
        matched_needle = self._clean_text(matched_needle)

        if output_language == "fr":
            mapping = {
                "criterion_match": (
                    "Le critère requis '%s' a été trouvé dans le texte public du site."
                    if not matched_needle or matched_needle == criterion_value
                    else "Le critère requis '%s' a été trouvé via le signal visible '%s' dans le texte public du site."
                ),
                "criterion_missing": "Le critère requis '%s' n’a pas été trouvé dans le texte public du site.",
                "forbidden_criterion_found": (
                    "Le critère interdit '%s' a été trouvé dans le texte public du site."
                    if not matched_needle or matched_needle == criterion_value
                    else "Le critère interdit '%s' a été trouvé via le signal visible '%s' dans le texte public du site."
                ),
                "forbidden_criterion_absent": "Le critère interdit '%s' n’a pas été trouvé dans le texte public du site.",
                "public_contact_found": "Un moyen de contact public a été extrait depuis les pages publiques.",
                "contact_page_found": "Une page contact publique a été trouvée pendant l’inspection.",
            }

            template = mapping.get(code, "Règle appliquée.")
            if "%s" in template:
                if matched_needle and matched_needle != criterion_value and template.count("%s") >= 2:
                    return template % (criterion_value, matched_needle)
                return template % criterion_value
            return template

        mapping = {
            "criterion_match": (
                "The required criterion '%s' was found in the public site text."
                if not matched_needle or matched_needle == criterion_value
                else "The required criterion '%s' was found via the visible signal '%s' in the public site text."
            ),
            "criterion_missing": "The required criterion '%s' was not found in the public site text.",
            "forbidden_criterion_found": (
                "The forbidden criterion '%s' was found in the public site text."
                if not matched_needle or matched_needle == criterion_value
                else "The forbidden criterion '%s' was found via the visible signal '%s' in the public site text."
            ),
            "forbidden_criterion_absent": "The forbidden criterion '%s' was not found in the public site text.",
            "public_contact_found": "A public contact method was extracted from public pages.",
            "contact_page_found": "A public contact page was found during inspection.",
        }

        template = mapping.get(code, "Rule applied.")
        if "%s" in template:
            if matched_needle and matched_needle != criterion_value and template.count("%s") >= 2:
                return template % (criterion_value, matched_needle)
            return template % criterion_value
        return template

    # --------------------------------------------------
    # Prospect processing
    # --------------------------------------------------

    def _process_one_prospect(self, run, prospect, parsed_criteria):
        try:
            self.run_service.update_status(run.id, "inspecting")
            self.db.commit()

            pages = self._fetch_public_pages(prospect.domain)

            if not any(page.get("loaded") for page in pages):
                self.db.prospect(prospect.id).update_record(inspection_failed=True)
                self.db.commit()

            # Persist all fetched pages for debug
            for page in pages:
                self.prospect_service.add_source_page(
                    prospect_id=prospect.id,
                    url=page.get("url") or "",
                    page_type=page.get("page_type") or "other",
                    loaded=bool(page.get("loaded")),
                    http_status=int(page.get("http_status") or 0),
                    extracted_text=page.get("extracted_text") or "",
                )

            self.run_service.update_status(run.id, "extracting_contacts")
            self.db.commit()

            extracted_contacts = self.contact_extractor.extract_contacts(
                pages=pages,
                default_region=self.default_phone_region,
            )

            best_contact = self._persist_contacts(prospect.id, extracted_contacts)
            self.prospect_service.set_best_contact(
                prospect_id=prospect.id,
                best_contact_value=best_contact.get("value", ""),
                has_public_contact=bool(best_contact.get("value")),
            )

            # Use only same-host business pages for text analysis and visible people
            analysis_pages = self._select_business_pages(prospect.domain, pages)

            self._extract_validate_and_persist_visible_people(
                run_row=run,
                prospect_row=prospect,
                pages=analysis_pages,
            )

            site_text = self._combine_page_text(analysis_pages)

            run_language = self._infer_output_language(run)

            rule_signals = self._evaluate_rule_signals(
                site_text=site_text,
                parsed_criteria=parsed_criteria,
                contacts=extracted_contacts,
                pages=analysis_pages,
                output_language=run_language,
            )
            self._persist_rule_signals(prospect.id, rule_signals)

            if not site_text:
                self._apply_no_content_fallback(prospect.id)
                self.prospect_service.set_processed(prospect.id, True)
                return

            self.run_service.update_status(run.id, "qualifying")
            self.db.commit()

            llm_context = {
                "niche": run.niche,
                "city": run.city,
                "offer": run.offer,
                "output_language": run_language,
                "signals": rule_signals,
            }

            llm_payload = self.llm_client.enrich_prospect(
                site_text=site_text,
                business_context=llm_context,
            )

            if not isinstance(llm_payload, dict):
                raise RunExecutionServiceError(
                    "GeminiLLMClient returned invalid payload type: %s" % type(llm_payload).__name__
                )

            self.run_service.update_status(run.id, "drafting")
            self.db.commit()

            self._persist_llm_payload(prospect.id, llm_payload)
            self._persist_llm_derived_signals(prospect.id, llm_payload.get("derived_signals", []))
            self._persist_llm_contact_enrichment(prospect.id, llm_payload)

            self.prospect_service.set_processed(prospect.id, True)

        except Exception as e:
            try:
                self.db.prospect(prospect.id).update_record(inspection_failed=True)
                self.run_service.increment_error_count(
                    run.id,
                    amount=1,
                    last_error_message=("Prospect %s failed: %s" % (prospect.domain, e))[:1000],
                )
                self.db.commit()
            except Exception:
                pass

    # --------------------------------------------------
    # Fetching
    # --------------------------------------------------

    def _fetch_public_pages(self, homepage_url):
        pages = []

        homepage = self.web_page_fetcher.fetch_page(homepage_url)
        homepage["page_type"] = "homepage"
        pages.append(homepage)

        if homepage.get("loaded"):
            contact_url = self.web_page_fetcher.find_contact_page_url(
                homepage.get("url") or homepage_url,
                homepage.get("extracted_text") or "",
            )
            contact_url = self._clean_text(contact_url)

            if contact_url and contact_url != (homepage.get("url") or homepage_url):
                contact_page = self.web_page_fetcher.fetch_page(contact_url)
                contact_page["page_type"] = "contact"
                pages.append(contact_page)

        return pages

    # --------------------------------------------------
    # Contacts
    # --------------------------------------------------

    def _persist_contacts(self, prospect_id, contacts):
        best = {
            "value": "",
            "confidence": 0.0,
            "contact_type": "none",
        }

        for contact in contacts or []:
            if not isinstance(contact, dict):
                continue

            row = self.prospect_service.add_contact(
                prospect_id=prospect_id,
                contact_type=contact.get("contact_type") or "none",
                value=contact.get("value") or "",
                source_url=contact.get("source_url") or "",
                confidence=float(contact.get("confidence") or 0.0),
                is_primary=bool(contact.get("is_primary")),
                contact_name="",
                contact_role="",
                address_text="",
                evidence_text="",
            )

            current_score = float(contact.get("confidence") or 0.0)
            if bool(contact.get("is_primary")) or current_score > float(best["confidence"]):
                if contact.get("contact_type") != "none":
                    best = {
                        "value": contact.get("value") or "",
                        "confidence": current_score,
                        "contact_type": contact.get("contact_type") or "none",
                        "row_id": row.id,
                    }

        return best

    def _persist_llm_contact_enrichment(self, prospect_id, llm_payload):
        has_any = bool(
            self._clean_text(llm_payload.get("contact_name", "")) or
            self._clean_text(llm_payload.get("contact_role", "")) or
            self._clean_text(llm_payload.get("address_text", ""))
        )

        if not has_any:
            return

        self.prospect_service.enrich_primary_contact(
            prospect_id=prospect_id,
            contact_name=llm_payload.get("contact_name", ""),
            contact_role=llm_payload.get("contact_role", ""),
            address_text=llm_payload.get("address_text", ""),
            evidence_text=llm_payload.get("contact_evidence_text", ""),
        )

    # --------------------------------------------------
    # Signals
    # --------------------------------------------------

    def _evaluate_rule_signals(self, site_text, parsed_criteria, contacts, pages, output_language="en"):
        text = (site_text or "").lower()
        signals = []
        output_language = (output_language or "en").lower()

        for criterion in parsed_criteria or []:
            if not isinstance(criterion, dict):
                continue

            kind = self._clean_text(criterion.get("kind") or "")
            value = self._clean_text(criterion.get("value") or "")
            if not kind or not value:
                continue

            needles = self._expand_criterion_needles(value)
            matched_needle = self._find_first_matching_needle(text, needles)
            is_match = bool(matched_needle)

            if kind == "must_mention":
                if is_match:
                    signals.append({
                        "signal_type": "criterion_match",
                        "signal_value": value,
                        "polarity": "positive",
                        "source_kind": "rule",
                        "confidence": 0.95,
                        "reason": self._rule_reason(
                            code="criterion_match",
                            output_language=output_language,
                            criterion_value=value,
                            matched_needle=matched_needle,
                        ),
                    })
                else:
                    signals.append({
                        "signal_type": "criterion_missing",
                        "signal_value": value,
                        "polarity": "negative",
                        "source_kind": "rule",
                        "confidence": 0.95,
                        "reason": self._rule_reason(
                            code="criterion_missing",
                            output_language=output_language,
                            criterion_value=value,
                            matched_needle="",
                        ),
                    })

            elif kind == "must_not_mention":
                if is_match:
                    signals.append({
                        "signal_type": "forbidden_criterion_found",
                        "signal_value": value,
                        "polarity": "negative",
                        "source_kind": "rule",
                        "confidence": 0.95,
                        "reason": self._rule_reason(
                            code="forbidden_criterion_found",
                            output_language=output_language,
                            criterion_value=value,
                            matched_needle=matched_needle,
                        ),
                    })
                else:
                    signals.append({
                        "signal_type": "forbidden_criterion_absent",
                        "signal_value": value,
                        "polarity": "positive",
                        "source_kind": "rule",
                        "confidence": 0.95,
                        "reason": self._rule_reason(
                            code="forbidden_criterion_absent",
                            output_language=output_language,
                            criterion_value=value,
                            matched_needle="",
                        ),
                    })

        visible_contact = False
        for contact in contacts or []:
            if not isinstance(contact, dict):
                continue
            if (contact.get("contact_type") or "none") != "none" and self._clean_text(contact.get("value") or ""):
                visible_contact = True
                break

        if visible_contact:
            signals.append({
                "signal_type": "public_contact_found",
                "signal_value": self._localized_signal_value("public_contact_found", output_language),
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.80,
                "reason": self._rule_reason(
                    code="public_contact_found",
                    output_language=output_language,
                ),
            })

        has_contact_page = any((page.get("page_type") or "") == "contact" for page in pages or [])
        if has_contact_page:
            signals.append({
                "signal_type": "contact_page_found",
                "signal_value": self._localized_signal_value("contact_page_found", output_language),
                "polarity": "positive",
                "source_kind": "rule",
                "confidence": 0.75,
                "reason": self._rule_reason(
                    code="contact_page_found",
                    output_language=output_language,
                ),
            })

        return signals

    def _persist_rule_signals(self, prospect_id, rule_signals):
        for signal in rule_signals or []:
            if not isinstance(signal, dict):
                continue

            self.prospect_service.add_signal(
                prospect_id=prospect_id,
                signal_type=signal.get("signal_type") or "rule_signal",
                signal_value=signal.get("signal_value") or "",
                polarity=signal.get("polarity") or "unknown",
                source_kind="rule",
                confidence=float(signal.get("confidence") or 0.5),
                reason=signal.get("reason") or "",
            )

    def _persist_llm_derived_signals(self, prospect_id, derived_signals):
        for signal in derived_signals or []:
            if not isinstance(signal, dict):
                continue

            self.prospect_service.add_signal(
                prospect_id=prospect_id,
                signal_type=signal.get("signal_type") or "llm_signal",
                signal_value=signal.get("signal_value") or "",
                polarity=signal.get("polarity") or "unknown",
                source_kind="llm",
                confidence=float(signal.get("confidence") or 0.5),
                reason=signal.get("reason") or "",
            )

    # --------------------------------------------------
    # LLM persistence
    # --------------------------------------------------

    def _persist_llm_payload(self, prospect_id, llm_payload):
        fit_confidence = self._clean_text(llm_payload.get("fit_confidence") or "low").lower()
        qualification_status = self._map_fit_confidence_to_qualification_status(fit_confidence)

        self.prospect_service.set_qualification(
            prospect_id=prospect_id,
            qualification_status=qualification_status,
            qualification_explanation=llm_payload.get("qualification_explanation", ""),
            fit_confidence=fit_confidence,
            llm_business_type=llm_payload.get("llm_business_type", ""),
            llm_offer_fit=llm_payload.get("llm_offer_fit", ""),
        )

        self.prospect_service.replace_artifact(
            prospect_id=prospect_id,
            business_summary=llm_payload.get("business_summary", ""),
            qualification_explanation=llm_payload.get("qualification_explanation", ""),
            fit_confidence=fit_confidence,
            outreach_angle=llm_payload.get("outreach_angle", ""),
            email_subject=llm_payload.get("email_subject", ""),
            email_draft=llm_payload.get("email_draft", ""),
            llm_model_used=llm_payload.get("llm_model_used", ""),
        )

        self.db.prospect(prospect_id).update_record(
            business_summary=llm_payload.get("business_summary", ""),
            outreach_angle=llm_payload.get("outreach_angle", ""),
            email_subject=llm_payload.get("email_subject", ""),
            email_draft=llm_payload.get("email_draft", ""),
        )

    def _apply_no_content_fallback(self, prospect_id):
        self.prospect_service.set_qualification(
            prospect_id=prospect_id,
            qualification_status="uncertain",
            qualification_explanation="No readable public website text could be extracted.",
            fit_confidence="low",
            llm_business_type="unknown",
            llm_offer_fit="Insufficient public content to assess fit reliably.",
        )

        self.prospect_service.replace_artifact(
            prospect_id=prospect_id,
            business_summary="No readable public website content was extracted.",
            qualification_explanation="No readable public website content was extracted.",
            fit_confidence="low",
            outreach_angle="Not enough visible public information to propose a strong outreach angle.",
            email_subject="quick question",
            email_draft="I had a quick look at your business, but public information was limited. If useful, I can send a very short note on where there may be relevance.",
            llm_model_used="fallback_no_content",
        )

        self.db.prospect(prospect_id).update_record(
            business_summary="No readable public website content was extracted.",
            outreach_angle="Not enough visible public information to propose a strong outreach angle.",
            email_subject="quick question",
            email_draft="I had a quick look at your business, but public information was limited. If useful, I can send a very short note on where there may be relevance.",
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _map_fit_confidence_to_qualification_status(self, fit_confidence):
        if fit_confidence == "high":
            return "qualified"
        if fit_confidence == "low":
            return "not_qualified"
        return "uncertain"

    def _combine_page_text(self, pages):
        chunks = []
        for page in pages or []:
            text = self._clean_text(page.get("extracted_text") or "")
            if text:
                chunks.append(text)
        return "\n\n".join(chunks).strip()

    def _infer_output_language(self, run):
        sample = " ".join([
            self._clean_text(run.niche or ""),
            self._clean_text(run.city or ""),
            self._clean_text(run.offer or ""),
        ]).lower()

        french_markers = (
            " refonte ", " optimisation ", " leads ", " qualification ",
            " rendez-vous ", " site web ", " agence ", " entreprise ",
            " sous-traitance ", " génération ", " local ", " design ",
        )

        sample_padded = " %s " % sample
        if re.search(r"[éèêàùçôîïâ]", sample):
            return "fr"

        for marker in french_markers:
            if marker in sample_padded:
                return "fr"

        return "en"

    def _clean_text(self, value):
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()