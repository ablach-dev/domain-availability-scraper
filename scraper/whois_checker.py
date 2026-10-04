"""
Authoritative Registry WHOIS & RDAP Domain Availability Checker.
Queries official TLD registry servers on port 43 (e.g., Verisign for .com/.net,
Identity Digital for .io, .ai, PIR for .org) with dynamic IANA discovery
and HTTPS RDAP fallback.
"""

import socket
import ssl
import time
import re
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, Tuple, Callable

# Authoritative TLD Registry WHOIS Servers (Port 43)
TLD_REGISTRY_SERVERS: Dict[str, str] = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "io": "whois.nic.io",
    "ai": "whois.nic.ai",
    "co": "whois.registry.co",
    "xyz": "whois.nic.xyz",
    "app": "whois.nic.google",
    "dev": "whois.nic.google",
    "page": "whois.nic.google",
    "me": "whois.nic.me",
    "sh": "whois.nic.sh",
    "cc": "ccwhois.verisign-grs.com",
    "tv": "tvwhois.verisign-grs.com",
    "info": "whois.afilias.net",
    "biz": "whois.nic.biz",
    "tech": "whois.nic.tech",
    "online": "whois.nic.online",
    "site": "whois.nic.site",
    "store": "whois.nic.store",
    "club": "whois.nic.club",
    "design": "whois.nic.design",
    "agency": "whois.nic.agency",
    "cloud": "whois.nic.cloud",
    "pro": "whois.nic.pro",
    "space": "whois.nic.space",
    "live": "whois.nic.live",
    "gg": "whois.gg",
    "so": "whois.nic.so",
    "to": "whois.tonic.to",
    "us": "whois.nic.us",
    "ca": "whois.cira.ca",
    "uk": "whois.nic.uk",
    "de": "whois.denic.de",
    "fr": "whois.nic.fr",
    "nl": "whois.domain-registry.nl",
    "eu": "whois.eu",
    "in": "whois.registry.in",
    "is": "whois.isnic.is",
}

# Signatures returned by registry WHOIS servers when a domain is NOT registered
AVAILABLE_SIGNATURES = [
    "no match for",
    "domain not found",
    "the queried object does not exist",
    "no entries found",
    "no data found",
    "is available for registration",
    "is available for purchase",
    "status: free",
    "status: available",
    "domain: none",
    "object does not exist",
    "nothing found",
    "query_status: 220 available",
]

# Signatures returned when a domain IS registered at the registry
TAKEN_SIGNATURES = [
    "registry domain id:",
    "domain name:",
    "creation date:",
    "created on:",
    "registrar whois server:",
    "registrant:",
    "domain status:",
    "registrar:",
]

# In-memory cache for discovered WHOIS servers
_DISCOVERED_SERVERS: Dict[str, str] = {}


def get_tld_from_domain(domain: str) -> str:
    """Extract root TLD from a domain name."""
    parts = domain.lower().strip().split(".")
    if len(parts) >= 2:
        return parts[-1]
    return "com"


def discover_registry_server(tld: str) -> Optional[str]:
    """Query IANA on port 43 to find authoritative WHOIS server for unknown TLDs."""
    tld = tld.lower().strip().lstrip(".")
    if tld in TLD_REGISTRY_SERVERS:
        return TLD_REGISTRY_SERVERS[tld]
    if tld in _DISCOVERED_SERVERS:
        return _DISCOVERED_SERVERS[tld]

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(4.0)
        s.connect(("whois.iana.org", 43))
        s.send(f"{tld}\r\n".encode("utf-8"))
        resp = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            resp += chunk
        s.close()
        text = resp.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            line_s = line.strip()
            if line_s.lower().startswith("whois:"):
                server = line_s.split(":", 1)[1].strip()
                if server:
                    _DISCOVERED_SERVERS[tld] = server
                    return server
    except Exception:
        pass

    # Generic fallback
    fallback = f"whois.nic.{tld}"
    _DISCOVERED_SERVERS[tld] = fallback
    return fallback


def query_whois_socket(domain: str, server: str, timeout: float = 4.5) -> str:
    """Send query to authoritative registry WHOIS server on port 43."""
    domain = domain.strip().lower()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect((server, 43))

    # Format query appropriately for specific registries
    if "verisign" in server:
        # Verisign uses =domain to prevent partial prefix matches
        query = f"={domain}\r\n"
    elif "denic.de" in server:
        query = f"-T dn,ace {domain}\r\n"
    else:
        query = f"{domain}\r\n"

    s.send(query.encode("utf-8"))
    response = b""
    while True:
        try:
            data = s.recv(4096)
            if not data:
                break
            response += data
            # Guard against massive WHOIS text responses
            if len(response) > 65536:
                break
        except socket.timeout:
            break

    s.close()
    return response.decode("utf-8", errors="ignore")


def query_rdap_fallback(domain: str, timeout: float = 4.0) -> Tuple[Optional[bool], str, str]:
    """Query official ICANN RDAP as fallback if WHOIS port 43 is blocked or times out."""
    url = f"https://rdap.org/domain/{domain}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DomainPulse-RegistryChecker/2.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.getcode()
            if status_code in (200, 301, 302):
                return False, "Registered (RDAP 200)", "RDAP Record Found"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True, "Available (RDAP 404 Not Found)", "RDAP: Unregistered Domain"
        elif e.code == 403:
            return None, "RDAP Rate Limited", "RDAP 403"
    except Exception as e:
        return None, f"RDAP Error: {e}", str(e)

    return None, "RDAP Unknown", ""


def check_domain_registry(domain: str, timeout: float = 4.5) -> Dict[str, Any]:
    """
    Check domain availability against the authoritative registry WHOIS.
    Returns:
      {
        'domain': domain,
        'status': 'available' | 'taken' | 'error',
        'server': registry_server,
        'reason': short explanation,
        'raw_snippet': first 200 chars of WHOIS response,
        'elapsed_ms': float
      }
    """
    t0 = time.time()
    domain = domain.strip().lower()
    tld = get_tld_from_domain(domain)
    server = discover_registry_server(tld) or f"whois.nic.{tld}"

    try:
        whois_text = query_whois_socket(domain, server, timeout=timeout)
        elapsed = (time.time() - t0) * 1000
        text_lower = whois_text.lower()

        # Step 1: Check for taken signatures first to avoid false positives from disclaimers
        for sig in TAKEN_SIGNATURES:
            if sig in text_lower:
                return {
                    "domain": domain,
                    "status": "taken",
                    "server": server,
                    "reason": f"Registry: {sig}",
                    "raw_snippet": whois_text[:250].strip().replace("\r", " "),
                    "elapsed_ms": round(elapsed, 1)
                }

        # Step 2: Check for authoritative available signatures
        for sig in AVAILABLE_SIGNATURES:
            if sig in text_lower:
                return {
                    "domain": domain,
                    "status": "available",
                    "server": server,
                    "reason": f"Registry: {sig}",
                    "raw_snippet": whois_text[:250].strip().replace("\r", " "),
                    "elapsed_ms": round(elapsed, 1)
                }

        # If inconclusive, check RDAP
        rdap_avail, rdap_reason, rdap_snip = query_rdap_fallback(domain)
        if rdap_avail is True:
            return {
                "domain": domain,
                "status": "available",
                "server": "ICANN-RDAP",
                "reason": rdap_reason,
                "raw_snippet": rdap_snip,
                "elapsed_ms": round((time.time() - t0) * 1000, 1)
            }
        elif rdap_avail is False:
            return {
                "domain": domain,
                "status": "taken",
                "server": "ICANN-RDAP",
                "reason": rdap_reason,
                "raw_snippet": rdap_snip,
                "elapsed_ms": round((time.time() - t0) * 1000, 1)
            }

        # Fallback to Taken if registry returned text but no clear available pattern
        if len(whois_text.strip()) > 50:
            return {
                "domain": domain,
                "status": "taken",
                "server": server,
                "reason": "Registry record present",
                "raw_snippet": whois_text[:250].strip().replace("\r", " "),
                "elapsed_ms": round(elapsed, 1)
            }

    except Exception as e:
        # If port 43 socket failed, try RDAP before erroring
        rdap_avail, rdap_reason, rdap_snip = query_rdap_fallback(domain)
        elapsed = (time.time() - t0) * 1000
        if rdap_avail is True:
            return {
                "domain": domain,
                "status": "available",
                "server": "ICANN-RDAP",
                "reason": rdap_reason,
                "raw_snippet": rdap_snip,
                "elapsed_ms": round(elapsed, 1)
            }
        elif rdap_avail is False:
            return {
                "domain": domain,
                "status": "taken",
                "server": "ICANN-RDAP",
                "reason": rdap_reason,
                "raw_snippet": rdap_snip,
                "elapsed_ms": round(elapsed, 1)
            }

        return {
            "domain": domain,
            "status": "error",
            "server": server,
            "reason": f"Connection error: {e}",
            "raw_snippet": str(e),
            "elapsed_ms": round(elapsed, 1)
        }

    return {
        "domain": domain,
        "status": "error",
        "server": server,
        "reason": "Inconclusive registry response",
        "raw_snippet": "",
        "elapsed_ms": round((time.time() - t0) * 1000, 1)
    }


def quick_dns_has_records(domain: str) -> bool:
    """
    Fast pre-filter check: returns True if domain has active A or NS records.
    If True -> definitely registered (taken).
    If False -> might be unregistered OR parked without DNS -> must check registry WHOIS!
    """
    try:
        # socket.getaddrinfo returns IP if domain has an active A/AAAA record
        socket.getaddrinfo(domain, 80, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror:
        return False
    except Exception:
        return False


def check_domain_hybrid(domain: str, timeout: float = 4.5) -> Dict[str, Any]:
    """
    Smart 2-Stage Verification:
    Stage 1: If domain resolves with active IP/DNS, it is unequivocally registered (taken).
    Stage 2: If domain does NOT resolve (inactive DNS, parked, or unregistered),
             query Authoritative Registry WHOIS to confirm whether it is actually available
             or just sitting parked without nameservers!
    A domain is NEVER marked available without Authoritative Registry confirmation.
    """
    t0 = time.time()
    domain = domain.strip().lower()

    # Stage 1: Active DNS resolution check
    if quick_dns_has_records(domain):
        elapsed = (time.time() - t0) * 1000
        return {
            "domain": domain,
            "status": "taken",
            "server": "Active-DNS",
            "reason": "Active DNS/IP records found",
            "raw_snippet": "Domain resolves to active IP address",
            "elapsed_ms": round(elapsed, 1)
        }

    # Stage 2: Authoritative Registry WHOIS lookup for candidates
    # This catches parked domains with inactive DNS and confirms real availability!
    return check_domain_registry(domain, timeout=timeout)
