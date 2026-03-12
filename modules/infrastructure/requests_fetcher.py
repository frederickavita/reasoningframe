# -*- coding: utf-8 -*-

import re
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from applications.reasoningframe.modules.application.ports import WebPageFetcherPort


class RequestsWebPageFetcherError(Exception):
    """Raised when page fetching fails in an unexpected way."""
    pass


class RequestsWebPageFetcher(WebPageFetcherPort):
    """
    Deterministic page fetcher based on requests + BeautifulSoup.

    Output format:
    {
        "url": "https://example.com",
        "loaded": True,
        "http_status": 200,
        "raw_html": "<html>...</html>",
        "extracted_text": "Visible text content...",
        "error_message": "",
    }
    """

    DEFAULT_TIMEOUT = 20

    CONTACT_KEYWORDS = (
        "contact",
        "contact-us",
        "contactez",
        "contactez-nous",
        "get-in-touch",
        "book",
        "booking",
        "appointment",
        "rendez-vous",
        "rdv",
        "doctolib",
    )

    SKIP_TAGS = {
        "script", "style", "noscript", "svg", "canvas",
        "iframe", "header", "footer", "nav", "aside"
    }

    META_CHARSET_RE = re.compile(
        br'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_\-]+)',
        re.I
    )

    META_HTTP_EQUIV_RE = re.compile(
        br'<meta[^>]+content=["\'][^"\']*charset=([a-zA-Z0-9_\-]+)',
        re.I
    )

    def __init__(self, requests_session=None, timeout=None, user_agent=None):
        self.requests_session = requests_session or requests.Session()
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def fetch_page(self, url):
        if not url or not str(url).strip():
            return {
                "url": url or "",
                "loaded": False,
                "http_status": 0,
                "raw_html": "",
                "extracted_text": "",
                "error_message": "URL is required.",
            }

        url = str(url).strip()
        headers = {"User-Agent": self.user_agent}

        try:
            response = self.requests_session.get(
                url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.RequestException as e:
            return {
                "url": url,
                "loaded": False,
                "http_status": 0,
                "raw_html": "",
                "extracted_text": "",
                "error_message": "Request failed: %s" % e,
            }

        if response.status_code != 200:
            return {
                "url": response.url or url,
                "loaded": False,
                "http_status": response.status_code,
                "raw_html": "",
                "extracted_text": "",
                "error_message": "HTTP status %s" % response.status_code,
            }

        content_type = response.headers.get("Content-Type", "") or ""
        if "text/html" not in content_type.lower():
            return {
                "url": response.url or url,
                "loaded": False,
                "http_status": response.status_code,
                "raw_html": "",
                "extracted_text": "",
                "error_message": "Unsupported content type: %s" % content_type,
            }

        raw_html = self._decode_response_html(response)
        extracted_text = self._extract_visible_text(raw_html)

        return {
            "url": response.url or url,
            "loaded": True,
            "http_status": response.status_code,
            "raw_html": raw_html,
            "extracted_text": extracted_text,
            "error_message": "",
        }

    def find_contact_page_url(self, homepage_url, homepage_text=None):
        """
        Try to find a likely contact page URL from the homepage HTML.
        """
        if not homepage_url or not str(homepage_url).strip():
            return None

        headers = {"User-Agent": self.user_agent}

        try:
            response = self.requests_session.get(
                homepage_url,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            return None

        content_type = response.headers.get("Content-Type", "") or ""
        if "text/html" not in content_type.lower():
            return None

        raw_html = self._decode_response_html(response)
        soup = BeautifulSoup(raw_html, "html.parser")

        best_candidate = None
        best_score = -1

        for a_tag in soup.find_all("a", href=True):
            href = (a_tag.get("href") or "").strip()
            anchor_text = self._normalize_space(a_tag.get_text(" ", strip=True)).lower()

            if not href:
                continue

            full_url = urljoin(response.url, href)
            score = self._score_contact_candidate(full_url, anchor_text)

            if score > best_score:
                best_score = score
                best_candidate = full_url

        if best_score <= 0:
            return None

        return best_candidate

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _decode_response_html(self, response):
        """
        Decode HTML from raw bytes with a robust strategy.

        Important:
        - prefer real byte decoding over response.text
        - try meta charset early
        - prefer utf-8 before legacy encodings
        - choose the least mojibake-looking decoding
        """
        content = response.content or b""
        if not content:
            return ""

        encodings_to_try = []

        meta_charset = self._extract_meta_charset(content[:4096])
        if meta_charset:
            encodings_to_try.append(meta_charset)

        # Prefer utf-8 early because many bad pages lie about encoding.
        encodings_to_try.append("utf-8")

        if response.encoding:
            encodings_to_try.append(response.encoding)

        apparent = getattr(response, "apparent_encoding", None)
        if apparent:
            encodings_to_try.append(apparent)

        encodings_to_try.extend(["cp1252", "latin-1"])

        tried = set()
        best_text = None
        best_score = None

        for enc in encodings_to_try:
            if not enc:
                continue

            enc = str(enc).strip()
            if not enc:
                continue

            enc_key = enc.lower()
            if enc_key in tried:
                continue
            tried.add(enc_key)

            try:
                decoded = content.decode(enc, errors="strict")
            except Exception:
                continue

            score = self._mojibake_score(decoded)

            if best_text is None or score < best_score:
                best_text = decoded
                best_score = score

            if score == 0:
                break

        if best_text is None:
            best_text = content.decode("utf-8", errors="replace")

        return self._normalize_unicode_text(best_text)

    def _extract_meta_charset(self, sample_bytes):
        if not sample_bytes:
            return ""

        match = self.META_CHARSET_RE.search(sample_bytes)
        if match:
            try:
                return match.group(1).decode("ascii", errors="ignore").strip()
            except Exception:
                pass

        match = self.META_HTTP_EQUIV_RE.search(sample_bytes)
        if match:
            try:
                return match.group(1).decode("ascii", errors="ignore").strip()
            except Exception:
                pass

        return ""

    def _mojibake_score(self, text):
        if not text:
            return 999999

        bad_patterns = (
            "Ã", "Â", "â€", "â€™", "â€œ", "â€", "â€“", "â€”",
            "Å", "œ", "�", "Ã©", "Ã¨", "Ãª", "Ã ", "Ã§",
            "Â ", "Â°", "Â©", "ðŸ", "â"
        )

        score = 0
        for pattern in bad_patterns:
            score += text.count(pattern)

        replacement_count = text.count("\ufffd")
        score += replacement_count * 3

        return score

    def _extract_visible_text(self, html):
        soup = BeautifulSoup(html, "html.parser")

        for tag_name in self.SKIP_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        body = soup.body if soup.body else soup
        text = body.get_text(separator=" ", strip=True)
        text = self._normalize_unicode_text(text)
        text = self._normalize_space(text)

        return text[:25000]

    def _normalize_unicode_text(self, value):
        value = value or ""
        value = unicodedata.normalize("NFKC", value)
        return value

    def _normalize_space(self, value):
        value = value or ""
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _score_contact_candidate(self, full_url, anchor_text):
        """
        Score links that look like contact / booking pages.
        """
        url_lower = full_url.lower()
        text_lower = (anchor_text or "").lower()

        score = 0

        for keyword in self.CONTACT_KEYWORDS:
            if keyword in url_lower:
                score += 2
            if keyword in text_lower:
                score += 3

        bad_keywords = (
            "facebook",
            "instagram",
            "linkedin",
            "twitter",
            "x.com",
            "youtube",
            "mailto:",
            "tel:",
            "#",
            "javascript:",
        )

        for bad in bad_keywords:
            if bad in url_lower:
                score -= 5

        try:
            parsed = urlparse(full_url)
            if not parsed.scheme.startswith("http"):
                score -= 10
        except Exception:
            score -= 10

        return score