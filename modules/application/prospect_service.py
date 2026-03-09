class ProspectServiceError(Exception):
    pass

class ProspectService(object):
    def __init__(self, db):
        self.db = db

    def create_prospect(self, run_id, company_name, domain, city="", render_order=0):
        ret = self.db.prospect.validate_and_insert(
            run_id=run_id,
            company_name=company_name,
            domain=domain,
            city=city,
            qualification_status="uncertain",
            fit_confidence="medium",
            render_order=render_order,
        )
        if ret.get("errors"):
            raise ProspectServiceError("Failed to create prospect: %s" % ret.get("errors"))
        self.db.commit()
        return self.db.prospect(ret.get("id"))

    def add_source_page(self, prospect_id, url, page_type, loaded=False, http_status=0, extracted_text="", error_message=""):
        ret = self.db.prospect_source_page.validate_and_insert(
            prospect_id=prospect_id,
            url=url,
            page_type=page_type,
            loaded=loaded,
            http_status=http_status,
            extracted_text=extracted_text,
            error_message=error_message,
        )
        if ret.get("errors"):
            raise ProspectServiceError("Failed to add source page: %s" % ret.get("errors"))
        self.db.commit()
        return self.db.prospect_source_page(ret.get("id"))

    def add_contact(self, prospect_id, contact_type, value, source_url="", confidence=0.5, is_primary=False, contact_name="", contact_role="", address_text="", evidence_text=""):
        ret = self.db.prospect_contact.validate_and_insert(
            prospect_id=prospect_id,
            contact_type=contact_type,
            value=value,
            contact_name=contact_name,
            contact_role=contact_role,
            address_text=address_text,
            evidence_text=evidence_text,
            source_url=source_url,
            confidence=confidence,
            is_primary=is_primary,
        )
        if ret.get("errors"):
            raise ProspectServiceError("Failed to add contact: %s" % ret.get("errors"))
        self.db.commit()
        return self.db.prospect_contact(ret.get("id"))

    def add_signal(self, prospect_id, signal_type, signal_value="", polarity="unknown", source_kind="rule", confidence=0.5, reason=""):
        ret = self.db.prospect_signal.validate_and_insert(
            prospect_id=prospect_id,
            signal_type=signal_type,
            signal_value=signal_value,
            polarity=polarity,
            source_kind=source_kind,
            confidence=confidence,
            reason=reason,
        )
        if ret.get("errors"):
            raise ProspectServiceError("Failed to add signal: %s" % ret.get("errors"))
        self.db.commit()
        return self.db.prospect_signal(ret.get("id"))

    def replace_artifact(
        self,
        prospect_id,
        business_summary="",
        qualification_explanation="",
        fit_confidence="medium",
        outreach_angle="",
        email_subject="",
        email_draft="",
        llm_model_used=""
    ):
        existing = self.db(self.db.prospect_artifact.prospect_id == prospect_id).select().first()

        payload = dict(
            prospect_id=prospect_id,
            business_summary=business_summary,
            qualification_explanation=qualification_explanation,
            fit_confidence=fit_confidence,
            outreach_angle=outreach_angle,
            email_subject=email_subject,
            email_draft=email_draft,
            llm_model_used=llm_model_used,
        )

        if existing:
            self.db(self.db.prospect_artifact.id == existing.id).update(**payload)
        else:
            ret = self.db.prospect_artifact.validate_and_insert(**payload)
            if ret.get("errors"):
                raise ProspectServiceError("Failed to upsert artifact: %s" % ret.get("errors"))

        self.db(self.db.prospect.id == prospect_id).update(
            business_summary=business_summary,
            qualification_explanation=qualification_explanation,
            fit_confidence=fit_confidence,
            outreach_angle=outreach_angle,
            email_subject=email_subject,
            email_draft=email_draft,
        )

        self.db.commit()
        return self.db(self.db.prospect_artifact.prospect_id == prospect_id).select().first()

    def set_processed(self, prospect_id, is_processed=True):
        self.db(self.db.prospect.id == prospect_id).update(is_processed=is_processed)
        self.db.commit()
        return self.db.prospect(prospect_id)

    def set_inspection_failed(self, prospect_id, inspection_failed=True):
        self.db(self.db.prospect.id == prospect_id).update(inspection_failed=inspection_failed)
        self.db.commit()
        return self.db.prospect(prospect_id)

    def set_best_contact(self, prospect_id, best_contact_value, has_public_contact=True):
        self.db(self.db.prospect.id == prospect_id).update(
            best_contact_value=best_contact_value or "",
            has_public_contact=has_public_contact,
        )
        self.db.commit()
        return self.db.prospect(prospect_id)

    def set_qualification(self, prospect_id, qualification_status, qualification_explanation="", fit_confidence="medium", llm_business_type="", llm_offer_fit=""):
        self.db(self.db.prospect.id == prospect_id).update(
            qualification_status=qualification_status,
            qualification_explanation=qualification_explanation,
            fit_confidence=fit_confidence,
            llm_business_type=llm_business_type,
            llm_offer_fit=llm_offer_fit,
        )
        self.db.commit()
        return self.db.prospect(prospect_id)

    def enrich_primary_contact(self, prospect_id, contact_name="", contact_role="", address_text="", evidence_text=""):
        prospect = self.db.prospect(prospect_id)
        if not prospect:
            raise ProspectServiceError("Prospect not found: %s" % prospect_id)

        primary = self.db(
            (self.db.prospect_contact.prospect_id == prospect_id) &
            (self.db.prospect_contact.is_primary == True)
        ).select().first()

        if not primary:
            fallback = self.db(
                self.db.prospect_contact.prospect_id == prospect_id
            ).select(orderby=self.db.prospect_contact.id).first()

            if fallback:
                fallback.update_record(is_primary=True)
                primary = fallback

        if not primary:
            ret = self.db.prospect_contact.validate_and_insert(
                prospect_id=prospect_id,
                contact_type="none",
                value="",
                source_url="",
                confidence=0.0,
                is_primary=True,
                contact_name="",
                contact_role="",
                address_text="",
                evidence_text="",
            )
            if ret.get("errors"):
                raise ProspectServiceError(ret.get("errors"))
            primary = self.db.prospect_contact(ret.get("id"))

        primary.update_record(
            contact_name=contact_name or "",
            contact_role=contact_role or "",
            address_text=address_text or "",
            evidence_text=evidence_text or "",
        )
        self.db.commit()
        return primary
    
    def replace_visible_people(self, prospect_id, visible_people):
        prospect = self.db.prospect(prospect_id)
        if not prospect:
            raise ProspectServiceError("Prospect not found: %s" % prospect_id)

        self.db(self.db.prospect_visible_person.prospect_id == prospect_id).delete()

        inserted = []
        seen = set()

        for person in visible_people or []:
            if not isinstance(person, dict):
                continue

            full_name = (person.get("full_name") or "").strip()
            role_text = (person.get("role_text") or "").strip()
            source_url = (person.get("source_url") or "").strip()
            evidence_text = (person.get("evidence_text") or "").strip()

            try:
                confidence = float(person.get("confidence") or 0.5)
            except (TypeError, ValueError):
                confidence = 0.5

            if confidence < 0.0:
                confidence = 0.0
            if confidence > 1.0:
                confidence = 1.0

            if not full_name:
                continue

            dedupe_key = (full_name.lower(), role_text.lower(), source_url.lower())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            ret = self.db.prospect_visible_person.validate_and_insert(
                prospect_id=prospect_id,
                full_name=full_name,
                role_text=role_text,
                source_url=source_url,
                evidence_text=evidence_text,
                confidence=confidence
            )

            if ret.get("errors"):
                raise ProspectServiceError(ret.get("errors"))

            inserted.append(self.db.prospect_visible_person(ret.get("id")))

        self.db.commit()
        return inserted
    
    def replace_visible_people(self, prospect_id, visible_people):
        if "prospect_visible_person" not in self.db.tables:
            raise ProspectServiceError("Table prospect_visible_person is not defined.")

        prospect = self.db.prospect(prospect_id)
        if not prospect:
            raise ProspectServiceError("Prospect not found: %s" % prospect_id)

        self.db(self.db.prospect_visible_person.prospect_id == prospect.id).delete()

        inserted_rows = []

        for item in visible_people or []:
            ret = self.db.prospect_visible_person.validate_and_insert(
                prospect_id=prospect.id,
                full_name=(item.get("full_name") or "").strip(),
                role_text=(item.get("role_text") or "").strip(),
                source_url=(item.get("source_url") or "").strip(),
                evidence_text=(item.get("evidence_text") or "").strip(),
                confidence=float(item.get("confidence") or 0.0),
            )

            if ret.get("errors"):
                raise ProspectServiceError(
                    "Failed to insert visible person: %s" % ret.get("errors")
                )

            inserted_rows.append(self.db.prospect_visible_person(ret.get("id")))

        self.db.commit()
        return inserted_rows