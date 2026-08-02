"""
Vivy AI — Internet Intelligence Layer: DuckDuckGo Provider Adapter
Universal DuckDuckGo Search provider supporting python libraries (ddgs/duckduckgo_search),
direct HTML scraping, and Lite fallback with deduplication, rate limiting, and ranking.
"""

import time
import re
import urllib.parse
import html as html_lib
from typing import List, Dict, Any, Optional
import requests

from internet.search_provider import SearchProvider, SearchResult

class DuckDuckGoProvider(SearchProvider):
    """Universal DuckDuckGo search engine adapter."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        default_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.112 Safari/537.36"
        self.user_agent = self.config.get("user_agent", default_ua)
        self.timeout = float(self.config.get("timeout_seconds", 5.0))
        self.safesearch = self.config.get("safesearch", "moderate")
        self._last_search_time = 0.0
        self._min_interval = float(self.config.get("min_interval_seconds", 0.0))  # Dynamically configured interval (no hardcoded bottleneck)

    def name(self) -> str:
        return "duckduckgo"

    def is_available(self) -> bool:
        return True

    def _rate_limit(self):
        if self._min_interval <= 0.0:
            return
        elapsed = time.time() - self._last_search_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_search_time = time.time()

    def search(self, query: str, max_results: int = 5, **kwargs) -> List[SearchResult]:
        if not query or len(query.strip()) < 2:
            return []

        clean_query = query.strip()
        self._rate_limit()

        # Tier 0: Check Smart Request Router and enforce required ordered sequence: Step 1 Network Verification -> Step 2 Tor/Scapy Gateway -> Step 3 DDG Retrieval
        try:
            from internet.network.request_router import get_request_router
            router = get_request_router()
            route_resp = router.route_request(clean_query, user_privacy_mode=False, max_results=max_results)
            seq_info = route_resp.get("pipeline_sequence", "Step 1 Network Verification -> Step 2 Tor/Scapy Gateway -> Step 3 DDG Retrieval")
            print(f"[DuckDuckGoProvider] Enforcing ordered network gateway pipeline: {seq_info}")
            if route_resp.get("is_tor") or ".onion" in clean_query.lower() or route_resp.get("status") == "success_virtual_sandbox_fallback":
                if route_resp.get("results") and isinstance(route_resp["results"], list):
                    tor_res = [SearchResult(title=r.get("title", ""), snippet=r.get("summary", ""), url=r.get("url", ""), source=str(route_resp.get("route_used", "duckduckgo_tor_onion")).lower().replace(" ", "_"), confidence=0.98) for r in route_resp["results"]]
                    print(f"[DuckDuckGoProvider] Retrieved {len(tor_res)} results via secure gateway route ({route_resp.get('route_used')}) for '{clean_query}'")
                    return tor_res
        except Exception as err:
            print(f"[DuckDuckGoProvider] Ordered network gateway evaluation note: {err}")

        # Tier 1: Try python package ddgs / duckduckgo_search
        results = self._search_via_ddgs(clean_query, max_results)
        if results:
            return results

        # Tier 2: Try html.duckduckgo.com scraping
        results = self._search_via_html(clean_query, max_results)
        if results:
            return results

        # Tier 3: Try lite.duckduckgo.com fallback
        results = self._search_via_lite(clean_query, max_results)
        if results:
            return results

        return []

    def _search_via_ddgs(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS

                raw_results = []
                with DDGS() as ddgs:
                    for r in ddgs.text(query, max_results=max_results):
                        raw_results.append(r)

                results = []
                for r in raw_results:
                    title = r.get("title", "").strip()
                    snippet = r.get("body", "").strip()
                    url = r.get("href", "").strip()
                    if snippet:
                        results.append(SearchResult(
                            title=title,
                            snippet=snippet,
                            url=url,
                            source="duckduckgo_ddgs",
                            confidence=0.95
                        ))
                if results:
                    print(f"[DuckDuckGoProvider] Retrieved {len(results)} results via DDGS library for '{query}'")
                    return self._deduplicate_and_rank(results, max_results)
        except Exception as e:
            print(f"[DuckDuckGoProvider] DDGS library search attempt failed for '{query}': {e}")
        return []

    def _search_via_html(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            base_url = cfg.get("apis.duckduckgo_html", "https://html.duckduckgo.com/html/?q=")
            
            headers = {
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            }
            url = f"{base_url}{urllib.parse.quote(query)}"
            r = requests.get(url, headers=headers, timeout=self.timeout)
            if r.status_code == 200:
                html_text = r.text
                results = []

                # Extract result blocks (title, url, snippet)
                pattern = re.compile(
                    r'<a class="result__snippet"[^>]*href="(?P<url>[^"]*)"[^>]*>(?P<snippet>.*?)</a>',
                    re.DOTALL
                )
                matches = pattern.finditer(html_text)

                for m in matches:
                    snippet_raw = m.group("snippet")
                    raw_url = m.group("url")
                    clean_s = re.sub(r'<[^>]*>', '', snippet_raw).strip()
                    clean_s = html_lib.unescape(clean_s)
                    if clean_s and len(clean_s) > 10:
                        results.append(SearchResult(
                            title="",
                            snippet=clean_s,
                            url=raw_url,
                            source="duckduckgo_html",
                            confidence=0.85
                        ))

                if not results:
                    snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL)
                    if not snippets:
                        snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', html_text, re.DOTALL)
                    for s in snippets:
                        clean_s = re.sub(r'<[^>]*>', '', s).strip()
                        clean_s = html_lib.unescape(clean_s)
                        if clean_s and len(clean_s) > 10:
                            results.append(SearchResult(
                                title="",
                                snippet=clean_s,
                                source="duckduckgo_html",
                                confidence=0.80
                            ))

                if results:
                    print(f"[DuckDuckGoProvider] Retrieved {len(results)} results via HTML for '{query}'")
                    return self._deduplicate_and_rank(results, max_results)
        except Exception as e:
            print(f"[DuckDuckGoProvider] HTML search attempt failed for '{query}': {e}")
        return []

    def _search_via_lite(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            lite_url = cfg.get("apis.duckduckgo_lite", "https://lite.duckduckgo.com/lite/")
            
            headers = {
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            }
            r_lite = requests.post(lite_url, data={"q": query}, headers=headers, timeout=self.timeout)
            if r_lite.status_code == 200:
                html_lite = r_lite.text
                snippets = re.findall(r'<td class="result-snippet"[^>]*>(.*?)</td>', html_lite, re.DOTALL)
                results = []
                for s in snippets:
                    clean_s = re.sub(r'<[^>]*>', '', s).strip()
                    clean_s = html_lib.unescape(clean_s)
                    if clean_s and len(clean_s) > 10:
                        results.append(SearchResult(
                            title="",
                            snippet=clean_s,
                            source="duckduckgo_lite",
                            confidence=0.75
                        ))
                if results:
                    print(f"[DuckDuckGoProvider] Retrieved {len(results)} results via Lite for '{query}'")
                    return self._deduplicate_and_rank(results, max_results)
        except Exception as e:
            print(f"[DuckDuckGoProvider] Lite search attempt failed for '{query}': {e}")
        return []

    def _deduplicate_and_rank(self, results: List[SearchResult], max_results: int) -> List[SearchResult]:
        seen = set()
        deduped = []
        for r in results:
            normalized = re.sub(r'\W+', '', r.snippet.lower())
            if normalized not in seen:
                seen.add(normalized)
                deduped.append(r)
        return deduped[:max_results]
