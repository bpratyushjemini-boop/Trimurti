"""
Web Search Service Subsystem for NARAD V2.1 Web Intelligence.
Provides fast, asynchronous live web search with multi-tier engine fallback (DuckDuckGo HTML & Lite),
clean URL extraction, domain source resolution, and snippet generation without requiring paid API keys.
"""

import re
import html
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, parse_qs, unquote
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class WebSearchService:
    """
    Asynchronous web search provider.
    Tries DuckDuckGo HTML first; if unavailable, falls back to DuckDuckGo Lite.
    Returns normalized results containing title, url, source, and snippet.
    """

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def _clean_url(self, raw_url: str) -> str:
        """Decode DuckDuckGo redirect wrapper URL into destination URL."""
        if not raw_url:
            return ""
        if "uddg=" in raw_url:
            try:
                parsed = urlparse(raw_url)
                qs = parse_qs(parsed.query)
                if "uddg" in qs:
                    return unquote(qs["uddg"][0])
            except Exception:
                pass
        if raw_url.startswith("//"):
            return "https:" + raw_url
        return raw_url

    async def _search_ddg_html(self, client: httpx.AsyncClient, query: str, max_results: int) -> List[Dict[str, str]]:
        """Search via DuckDuckGo HTML endpoint."""
        url = "https://html.duckduckgo.com/html/"
        resp = await client.post(url, data={"q": query})
        if resp.status_code != 200:
            logger.warning(f"[WebSearch] DDG HTML returned status {resp.status_code}")
            return []

        text = resp.text
        titles = re.findall(r'<a[^>]*class=\"result__a\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>', text)
        snippets = re.findall(r'<a[^>]*class=\"result__snippet\"[^>]*>(.*?)</a>', text)

        results: List[Dict[str, str]] = []
        count = min(len(titles), len(snippets))
        for i in range(count):
            raw_url, raw_title = titles[i]
            raw_snippet = snippets[i]

            clean_url = self._clean_url(raw_url)
            if not clean_url.startswith("http"):
                continue

            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
            source = urlparse(clean_url).netloc.lower()

            if title:
                results.append({
                    "title": title,
                    "url": clean_url,
                    "source": source,
                    "snippet": snippet
                })
            if len(results) >= max_results:
                break

        return results

    async def _search_ddg_lite(self, client: httpx.AsyncClient, query: str, max_results: int) -> List[Dict[str, str]]:
        """Fallback search via DuckDuckGo Lite endpoint."""
        url = "https://lite.duckduckgo.com/lite/"
        resp = await client.post(url, data={"q": query})
        if resp.status_code != 200:
            logger.warning(f"[WebSearch] DDG Lite returned status {resp.status_code}")
            return []

        text = resp.text
        links = re.findall(r'<a[^>]*class=\"result-link\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>', text)
        snippets = re.findall(r'<td[^>]*class=\"result-snippet\"[^>]*>(.*?)</td>', text, re.DOTALL)

        results: List[Dict[str, str]] = []
        for i in range(len(links)):
            raw_url, raw_title = links[i]
            raw_snippet = snippets[i] if i < len(snippets) else ""

            clean_url = self._clean_url(raw_url)
            if not clean_url.startswith("http"):
                continue

            title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
            source = urlparse(clean_url).netloc.lower()

            if title:
                results.append({
                    "title": title,
                    "url": clean_url,
                    "source": source,
                    "snippet": snippet
                })
            if len(results) >= max_results:
                break

        return results

    async def _search_yahoo(self, client: httpx.AsyncClient, query: str, max_results: int) -> List[Dict[str, str]]:
        """Resilient fallback search via Yahoo Web Search endpoint."""
        url = "https://search.yahoo.com/search"
        resp = await client.get(url, params={"p": query})
        if resp.status_code != 200:
            logger.warning(f"[WebSearch] Yahoo returned status {resp.status_code}")
            return []

        text = resp.text
        items = re.findall(r"<div class=\"(?:dd )?algo[^\"]*\">.*?</div>\s*</li>", text, re.DOTALL)
        if not items:
            items = re.findall(r"<div class=\"compTitle[^\"]*\">.*?</div>\s*<div class=\"compText[^\"]*\">.*?</div>", text, re.DOTALL)

        results: List[Dict[str, str]] = []
        for item in items:
            m_link = re.search(r"<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", item, re.DOTALL)
            m_snip = re.search(r"<div class=\"compText[^\"]*\"[^>]*>(.*?)</div>", item, re.DOTALL)
            if not m_snip:
                m_snip = re.search(r"<p[^>]*class=\"[^\"]*lh-[^\"]*\"[^>]*>(.*?)</p>", item, re.DOTALL)

            if not m_link:
                continue

            raw_url, raw_title = m_link.groups()
            clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            if "›" in clean_title:
                clean_title = clean_title.split("›")[-1].strip()
            if "/" in clean_title and " " in clean_title:
                parts = clean_title.split()
                if "." in parts[0] and len(parts) > 1:
                    clean_title = " ".join(parts[1:])

            clean_url = raw_url
            if "/RU=" in raw_url:
                m_ru = re.search(r"/RU=([^/]+)/", raw_url)
                if m_ru:
                    clean_url = unquote(m_ru.group(1))

            if not clean_url.startswith("http"):
                continue

            snippet = ""
            if m_snip:
                snippet = html.unescape(re.sub(r"<[^>]+>", "", m_snip.group(1))).strip()

            source = urlparse(clean_url).netloc.lower()
            if clean_title:
                results.append({
                    "title": clean_title,
                    "url": clean_url,
                    "source": source,
                    "snippet": snippet
                })
            if len(results) >= max_results:
                break

        return results

    async def _search_wikipedia(self, client: httpx.AsyncClient, query: str, max_results: int) -> List[Dict[str, str]]:
        """Encyclopedia fallback search via Wikipedia OpenSearch API."""
        url = "https://en.wikipedia.org/w/api.php"
        headers = {"User-Agent": "NaradAssistant/2.1 (contact@trimurti.local)"}
        resp = await client.get(
            url,
            params={
                "action": "opensearch",
                "search": query,
                "limit": str(max_results),
                "namespace": "0",
                "format": "json"
            },
            headers=headers
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list) and len(data) >= 4:
            titles = data[1]
            snippets = data[2]
            urls = data[3]
            results: List[Dict[str, str]] = []
            for i in range(min(len(titles), len(urls))):
                results.append({
                    "title": titles[i],
                    "url": urls[i],
                    "source": "en.wikipedia.org",
                    "snippet": snippets[i] or f"Wikipedia article regarding {titles[i]}."
                })
            return results
        return []

    async def search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Execute live web search for the specified query.
        Multi-tier fallback: DuckDuckGo HTML -> DuckDuckGo Lite -> Yahoo Search -> Wikipedia.
        Returns a structured dictionary containing status, count, and results.
        """
        clean_query = str(query or "").strip()
        if not clean_query:
            return {
                "status": "error",
                "message": "Search query cannot be empty.",
                "query": "",
                "count": 0,
                "results": []
            }

        limit = max(1, min(int(max_results or 5), 10))
        logger.info(f"[WebSearch] Executing live search for query: '{clean_query}' (limit={limit})")

        async with httpx.AsyncClient(headers=DEFAULT_HEADERS, timeout=self.timeout, follow_redirects=True) as client:
            # Tier 1: DuckDuckGo HTML
            try:
                html_results = await self._search_ddg_html(client, clean_query, limit)
                if html_results:
                    logger.info(f"[WebSearch] DDG HTML returned {len(html_results)} results for '{clean_query}'")
                    return {
                        "status": "success",
                        "engine": "duckduckgo",
                        "query": clean_query,
                        "count": len(html_results),
                        "results": html_results
                    }
            except Exception as e:
                logger.warning(f"[WebSearch] DDG HTML search failed for '{clean_query}': {e}")

            # Tier 2: DuckDuckGo Lite
            try:
                lite_results = await self._search_ddg_lite(client, clean_query, limit)
                if lite_results:
                    logger.info(f"[WebSearch] DDG Lite returned {len(lite_results)} results for '{clean_query}'")
                    return {
                        "status": "success",
                        "engine": "duckduckgo_lite",
                        "query": clean_query,
                        "count": len(lite_results),
                        "results": lite_results
                    }
            except Exception as e:
                logger.warning(f"[WebSearch] DDG Lite search failed for '{clean_query}': {e}")

            # Tier 3: Yahoo Search
            try:
                yahoo_results = await self._search_yahoo(client, clean_query, limit)
                if yahoo_results:
                    logger.info(f"[WebSearch] Yahoo returned {len(yahoo_results)} results for '{clean_query}'")
                    return {
                        "status": "success",
                        "engine": "yahoo",
                        "query": clean_query,
                        "count": len(yahoo_results),
                        "results": yahoo_results
                    }
            except Exception as e:
                logger.warning(f"[WebSearch] Yahoo search failed for '{clean_query}': {e}")

            # Tier 4: Wikipedia OpenSearch
            try:
                wiki_results = await self._search_wikipedia(client, clean_query, limit)
                if wiki_results:
                    logger.info(f"[WebSearch] Wikipedia returned {len(wiki_results)} results for '{clean_query}'")
                    return {
                        "status": "success",
                        "engine": "wikipedia",
                        "query": clean_query,
                        "count": len(wiki_results),
                        "results": wiki_results
                    }
            except Exception as e:
                logger.warning(f"[WebSearch] Wikipedia search failed for '{clean_query}': {e}")

        logger.error(f"[WebSearch] All search providers failed or returned 0 results for '{clean_query}'")
        return {
            "status": "error",
            "message": f"Web search could not retrieve live results for '{clean_query}'. Please verify internet connectivity or search query.",
            "query": clean_query,
            "count": 0,
            "results": []
        }


# Global singleton WebSearchService instance
web_search_service = WebSearchService()
