# -*- coding: utf-8 -*-

import requests

from applications.reasoningframe.modules.application.ports import SearchProviderPort


class BraveSearchProviderError(Exception):
    """Raised when Brave Search provider fails."""
    pass


class BraveSearchProvider(SearchProviderPort):
    """
    Brave Search API provider.

    Expected output format:
    [
        {
            "company_name": "...",
            "domain": "https://example.com",
            "title": "...",
            "snippet": "...",
        }
    ]
    """

    SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    DEFAULT_TIMEOUT = 20

    def __init__(self, api_key, requests_session=None, timeout=None):
        self.api_key = api_key
        self.requests_session = requests_session or requests.Session()
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def _build_headers(self):
        if not self.api_key:
            raise BraveSearchProviderError("Brave API key is missing.")

        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

    def _normalize_result(self, item):
        url = item.get("url", "") or ""
        title = item.get("title", "") or ""
        snippet = item.get("description", "") or ""

        company_name = self._infer_company_name(title, url)

        return {
            "company_name": company_name,
            "domain": url,
            "title": title,
            "snippet": snippet,
        }

    def _infer_company_name(self, title, url):
        title = (title or "").strip()
        url = (url or "").strip()

        if title:
            return title[:255]

        if url:
            try:
                clean = url.replace("https://", "").replace("http://", "").strip("/")
                return clean.split("/")[0][:255]
            except Exception:
                return url[:255]

        return "Unknown company"

    def search(self, query, limit=25):
        if not query or not str(query).strip():
            raise BraveSearchProviderError("Search query is required.")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise BraveSearchProviderError("limit must be an integer.")

        if limit <= 0:
            raise BraveSearchProviderError("limit must be > 0.")

        params = {
            "q": str(query).strip(),
            "count": limit,
        }

        try:
            response = self.requests_session.get(
                self.SEARCH_ENDPOINT,
                headers=self._build_headers(),
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise BraveSearchProviderError("Brave request failed: %s" % e)

        if response.status_code != 200:
            raise BraveSearchProviderError(
                "Brave API returned status %s: %s" % (response.status_code, response.text[:500])
            )

        try:
            payload = response.json()
        except ValueError as e:
            raise BraveSearchProviderError("Invalid JSON from Brave API: %s" % e)

        web_data = payload.get("web", {}) or {}
        raw_results = web_data.get("results", []) or []

        normalized = []
        seen_urls = set()

        for item in raw_results:
            normalized_item = self._normalize_result(item)
            url = normalized_item["domain"]

            if not url:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)
            normalized.append(normalized_item)

        return normalized