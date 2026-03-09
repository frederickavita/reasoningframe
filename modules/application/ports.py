# -*- coding: utf-8 -*-

class SearchProviderPort(object):
    """
    Contract for web search providers.
    Example implementations:
    - BraveSearchProvider
    - SerpApiSearchProvider
    """

    def search(self, query, limit=25):
        """
        Must return a list of dictionaries like:
        [
            {
                "company_name": "Cabinet Dentaire Paris Centre",
                "domain": "https://example.com",
                "title": "Cabinet Dentaire Paris Centre",
                "snippet": "Dental clinic in Paris...",
            }
        ]
        """
        raise NotImplementedError


class WebPageFetcherPort(object):
    """
    Contract for deterministic page fetching.
    Example implementations:
    - RequestsWebPageFetcher
    - PlaywrightWebPageFetcher
    """

    def fetch_page(self, url):
        """
        Must return a dictionary like:
        {
            "url": "https://example.com",
            "loaded": True,
            "http_status": 200,
            "extracted_text": "Visible text content...",
            "error_message": "",
        }
        """
        raise NotImplementedError

    def find_contact_page_url(self, homepage_url, homepage_text):
        """
        Must return:
        - a contact page URL string
        - or None if not found
        """
        raise NotImplementedError


class ContactExtractorPort(object):
    """
    Contract for extracting public contacts from fetched pages.
    Example implementations:
    - RegexContactExtractor
    """

    def extract_contacts(self, pages):
        """
        pages: list of dictionaries like:
        [
            {
                "url": "https://example.com",
                "page_type": "homepage",
                "extracted_text": "..."
            }
        ]

        Must return a list of dictionaries like:
        [
            {
                "contact_type": "email",
                "value": "hello@example.com",
                "source_url": "https://example.com/contact",
                "confidence": 0.9,
                "is_primary": True,
            }
        ]
        """
        raise NotImplementedError


class LLMEnrichmentPort(object):
    """
    Contract for LLM-based business understanding / qualification / outreach enrichment.
    Example implementations:
    - GeminiLLMClient
    """

    def enrich_prospect(self, site_text, business_context):
        """
        site_text: string
        business_context: dict like:
        {
            "niche": "dentists",
            "city": "Paris",
            "offer": "website redesign",
            "signals": [...]
        }

        Must return a dictionary like:
        {
            "business_summary": "...",
            "qualification_explanation": "...",
            "fit_confidence": "high",
            "llm_business_type": "clinic",
            "llm_offer_fit": "Strong fit for website redesign",
            "outreach_angle": "...",
            "email_subject": "...",
            "email_draft": "...",
            "llm_model_used": "gemini-2.5-flash-lite",
            "derived_signals": [
                {
                    "signal_type": "llm_fit",
                    "signal_value": "strong local service fit",
                    "polarity": "positive",
                    "source_kind": "llm",
                    "confidence": 0.91,
                    "reason": "..."
                }
            ]
        }
        """
        raise NotImplementedError