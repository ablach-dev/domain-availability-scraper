"""
Unit tests for Domain Availability Scraper.
Tests generator modes, TLD formatting, and async DoH checker.
"""

import unittest
import asyncio
from scraper.generator import (
    generate_letter_domains,
    generate_keyword_domains,
    generate_brandable_domains,
    parse_custom_domains,
    clean_domain_input,
)
from scraper.checker import DomainChecker, DomainCheckResult
from scraper.tlds import format_tld, get_registrar_links


class TestDomainScraper(unittest.TestCase):

    def test_clean_domain_input(self):
        self.assertEqual(clean_domain_input("https://www.example.com/"), "example.com")
        self.assertEqual(clean_domain_input("http://mysite.io"), "mysite.io")
        self.assertEqual(clean_domain_input("  HELLO.AI  "), "hello.ai")

    def test_format_tld(self):
        self.assertEqual(format_tld("com"), ".com")
        self.assertEqual(format_tld(".io"), ".io")
        self.assertEqual(format_tld(" AI "), ".ai")

    def test_parse_custom_domains(self):
        text = "foo.com, bar, https://example.net"
        tlds = [".com", ".io"]
        res = parse_custom_domains(text, tlds)
        self.assertIn("foo.com", res)
        self.assertIn("bar.com", res)
        self.assertIn("bar.io", res)
        self.assertIn("example.net", res)

    def test_letter_generation_modes(self):
        # Pronounceable 4-letter
        d1 = generate_letter_domains(4, mode="pronounceable", max_count=10, tlds=[".com"])
        self.assertEqual(len(d1), 10)
        for d in d1:
            self.assertTrue(d.endswith(".com"))
            base = d.split(".")[0]
            self.assertEqual(len(base), 4)

        # Pure alphabet 3-letter
        d2 = generate_letter_domains(3, mode="letters", max_count=5, tlds=[".ai"])
        self.assertEqual(len(d2), 5)
        for d in d2:
            self.assertTrue(d.endswith(".ai"))
            self.assertEqual(len(d.split(".")[0]), 3)

        # Pattern ?ai
        d3 = generate_letter_domains(3, mode="pattern", pattern="?ai", max_count=5, tlds=[".io"])
        self.assertEqual(len(d3), 5)
        for d in d3:
            self.assertTrue(d.endswith("ai.io"))

    def test_keyword_generation(self):
        res = generate_keyword_domains(["cloud"], mode="suffix", max_count=5, tlds=[".com"])
        self.assertTrue(any("cloud" in d for d in res))
        self.assertTrue(any(d.endswith(".com") for d in res))

        # Niche pack
        res_niche = generate_keyword_domains(["agent"], mode="niche", niche_pack="ai_ml", max_count=5, tlds=[".ai"])
        self.assertGreater(len(res_niche), 0)

    def test_brandable_generation(self):
        res = generate_brandable_domains(tlds=[".io"], max_count=8)
        self.assertEqual(len(res), 8)
        self.assertTrue(all(d.endswith(".io") for d in res))

    def test_registrar_links(self):
        links = get_registrar_links("testdomain.com")
        self.assertIn("porkbun", links)
        self.assertIn("namecheap", links)
        self.assertIn("godaddy", links)
        self.assertIn("testdomain.com", links["porkbun"])

    def test_checker_live_lookup(self):
        async def run_check():
            checker = DomainChecker(concurrency=5, deep_check=False)
            try:
                # Google is taken
                r_taken = await checker.check_single_domain("google.com")
                self.assertEqual(r_taken.status, "taken")

                # Highly improbable random string is available
                r_avail = await checker.check_single_domain("z789nonexistentdomainqwe999xyz.com")
                self.assertEqual(r_avail.status, "available")
            finally:
                await checker.close()

        asyncio.run(run_check())


if __name__ == "__main__":
    unittest.main()
