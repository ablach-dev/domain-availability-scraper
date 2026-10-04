"""
Unit tests for Authoritative Registry WHOIS and RDAP Checker.
"""

import unittest
from scraper.whois_checker import (
    check_domain_registry,
    check_domain_hybrid,
    discover_registry_server,
    get_tld_from_domain,
    TLD_REGISTRY_SERVERS,
)


class TestWhoisChecker(unittest.TestCase):

    def test_tld_extraction(self):
        self.assertEqual(get_tld_from_domain("google.com"), "com")
        self.assertEqual(get_tld_from_domain("github.io"), "io")
        self.assertEqual(get_tld_from_domain("sub.domain.co.uk"), "uk")

    def test_registry_server_discovery(self):
        self.assertEqual(discover_registry_server("com"), "whois.verisign-grs.com")
        self.assertEqual(discover_registry_server("io"), "whois.nic.io")
        self.assertEqual(discover_registry_server("org"), "whois.pir.org")

    def test_known_taken_domain_verisign(self):
        # google.com must report TAKEN from Verisign registry WHOIS
        res = check_domain_registry("google.com")
        self.assertEqual(res["status"], "taken")
        self.assertIn("whois.verisign-grs.com", res["server"])

    def test_known_available_domain_verisign(self):
        # High-entropy random domain must report AVAILABLE from Verisign
        res = check_domain_registry("z987supernonexistentxyz123456789.com")
        self.assertEqual(res["status"], "available")
        self.assertIn("no match for", res["reason"].lower())

    def test_known_taken_domain_io(self):
        # apple.io must report TAKEN from Identity Digital .io registry
        res = check_domain_registry("apple.io")
        self.assertEqual(res["status"], "taken")
        self.assertEqual(res["server"], "whois.nic.io")

    def test_known_available_domain_io(self):
        # High-entropy .io domain must report AVAILABLE from .io registry
        res = check_domain_registry("z987supernonexistentxyz123456789.io")
        self.assertEqual(res["status"], "available")
        self.assertIn("domain not found", res["reason"].lower())

    def test_hybrid_check(self):
        res_taken = check_domain_hybrid("microsoft.com")
        self.assertEqual(res_taken["status"], "taken")

        res_avail = check_domain_hybrid("z987supernonexistentxyz123456789.com")
        self.assertEqual(res_avail["status"], "available")


if __name__ == "__main__":
    unittest.main()
