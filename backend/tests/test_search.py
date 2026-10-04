"""
Unit & Integration Tests for Web Search Service (NARAD V2.1 Web Intelligence).
Verifies:
- Live search query execution
- Result format (title, url, source, snippet)
- Max results limit enforcement
- Clean URL redirect decoding
- Safe handling of empty/whitespace queries
"""

import unittest
import asyncio
from app.services.search import web_search_service, WebSearchService


class TestWebSearchService(unittest.TestCase):
    def test_01_empty_query_handling(self):
        res = asyncio.run(web_search_service.search(""))
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["results"], [])
        self.assertIn("cannot be empty", res["message"])

        res_ws = asyncio.run(web_search_service.search("   "))
        self.assertEqual(res_ws["status"], "error")

    def test_02_clean_url_decoding(self):
        svc = WebSearchService()
        # Direct URL
        self.assertEqual(svc._clean_url("https://example.com/page"), "https://example.com/page")
        # DDG redirect wrapper
        wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fconsole.groq.com%2Fdocs&rut=123"
        cleaned = svc._clean_url(wrapped)
        self.assertEqual(cleaned, "https://console.groq.com/docs")

    def test_03_live_search_execution(self):
        # Query for stable technical documentation
        res = asyncio.run(
            web_search_service.search("Groq documentation", max_results=3)
        )
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["count"], 1)
        self.assertLessEqual(res["count"], 3)

        first = res["results"][0]
        self.assertIn("title", first)
        self.assertIn("url", first)
        self.assertIn("source", first)
        self.assertIn("snippet", first)
        self.assertTrue(first["url"].startswith("http"))
        self.assertTrue(len(first["title"]) > 0)
        self.assertTrue(len(first["source"]) > 0)


if __name__ == "__main__":
    unittest.main()
