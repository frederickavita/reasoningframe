class LLMEnrichmentServiceError(Exception):
    pass


class LLMEnrichmentService(object):
    def __init__(self, llm_client, output_validator):
        self.llm_client = llm_client
        self.output_validator = output_validator

    def enrich(self, site_text, niche, city, offer, simple_signals=None):
        simple_signals = simple_signals or []

        raw = self.llm_client.enrich_prospect(
            site_text=site_text,
            business_context={
                "niche": niche,
                "city": city,
                "offer": offer,
                "signals": simple_signals,
            }
        )

        validated = self.output_validator.validate_all(
            summary=raw.get("business_summary", ""),
            angle=raw.get("outreach_angle", ""),
            subject=raw.get("email_subject", ""),
            draft=raw.get("email_draft", ""),
            qualification_explanation=raw.get("qualification_explanation", ""),
            fit_confidence=raw.get("fit_confidence", "medium"),
        )

        validated["llm_business_type"] = raw.get("llm_business_type", "")
        validated["llm_offer_fit"] = raw.get("llm_offer_fit", "")
        validated["llm_model_used"] = raw.get("llm_model_used", "")

        return validated