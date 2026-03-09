class OutreachService(object):
    def build_final_outreach(self, enriched_payload):
        return {
            "email_subject": enriched_payload.get("email_subject", ""),
            "email_draft": enriched_payload.get("email_draft", ""),
        }