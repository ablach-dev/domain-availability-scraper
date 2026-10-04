"""
TLD definitions, presets, and registrar purchase links.
"""

# Common TLD presets
TLD_PRESETS = {
    "popular": [".com", ".io", ".ai", ".co", ".net", ".org"],
    "tech": [".ai", ".io", ".dev", ".app", ".tech", ".sh", ".cloud"],
    "startup": [".com", ".io", ".ai", ".co", ".app", ".xyz"],
    "budget": [".xyz", ".top", ".club", ".site", ".online", ".me"],
    "classic": [".com", ".net", ".org", ".info", ".biz"],
    "short": [".co", ".io", ".ai", ".me", ".so", ".to", ".cc", ".is"],
}

ALL_COMMON_TLDS = [
    ".com", ".io", ".ai", ".co", ".net", ".org", ".app", ".dev",
    ".xyz", ".tech", ".me", ".so", ".to", ".cc", ".is", ".cloud",
    ".sh", ".design", ".agency", ".store", ".online", ".site",
    ".pro", ".space", ".fun", ".live", ".press", ".news", ".gg"
]

def format_tld(tld: str) -> str:
    """Ensure TLD starts with a dot and is lowercase."""
    tld = tld.strip().lower()
    if not tld.startswith("."):
        tld = "." + tld
    return tld

def get_registrar_links(domain: str) -> dict:
    """Generate direct search/buy URLs for major registrars in preferred order."""
    return {
        "godaddy": f"https://www.godaddy.com/domainsearch/find?checkAvail=1&domainToCheck={domain}",
        "cloudflare": f"https://www.cloudflare.com/products/registrar/",
        "dynadot": f"https://www.dynadot.com/domain/search?domain={domain}",
        "namecheap": f"https://www.namecheap.com/domains/registration/results/?domain={domain}",
        "porkbun": f"https://porkbun.com/checkout/search?q={domain}",
    }
