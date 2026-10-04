"""
Domain name generator supporting:
- Direct custom / batch lists
- Exact letter length combinations (alphabetical, random, pronounceable CVCV, custom patterns)
- Keyword prefix/suffix generators and industry niche packs
- Brandable dictionary words
"""

import itertools
import random
import re
from typing import List, Set, Generator

# Pronounceable phonetic elements
VOWELS = "aeiou"
CONSONANTS = "bcdfghjklmnprstvwxyz"  # excluded q for better pronounceability

# Curated startup affixes
COMMON_PREFIXES = [
    "get", "try", "use", "my", "the", "go", "open", "hey", "join",
    "pro", "smart", "super", "ultra", "meta", "omni", "cyber", "zen",
    "vibe", "next", "prime", "neo", "pure", "true", "ever", "fast",
    "deep", "all", "star", "nova", "hyper", "one", "top", "free",
    "auto", "real", "apex", "peak", "pulse", "flow", "core"
]

COMMON_SUFFIXES = [
    "hq", "app", "hub", "lab", "io", "box", "ly", "ify", "flow",
    "stack", "sync", "deck", "craft", "link", "base", "kit", "spot",
    "cloud", "forge", "zone", "wave", "nest", "pulse", "grid", "core",
    "port", "cast", "wire", "vault", "run", "bit", "pad", "works",
    "ai", "bot", "go", "up", "now", "space", "point", "loop"
]

NICHE_PACKS = {
    "tech_saas": [
        "stack", "cloud", "flow", "sync", "hq", "box", "lab", "base",
        "engine", "scale", "mesh", "forge", "api", "dev", "ops", "pipeline",
        "platform", "vault", "code", "infra"
    ],
    "ai_ml": [
        "ai", "mind", "neural", "bot", "cortex", "agent", "prompt", "tensor",
        "cogni", "synth", "deep", "brain", "intel", "model", "copilot", "gpt",
        "logic", "vision"
    ],
    "crypto_web3": [
        "chain", "dao", "crypto", "token", "block", "swap", "mint", "node",
        "dex", "vault", "coin", "ledger", "meta", "stake", "gas", "yield"
    ],
    "creative_studio": [
        "studio", "craft", "design", "vibe", "creative", "pixel", "canvas",
        "brand", "art", "press", "media", "lab", "agency", "folio", "ink"
    ],
    "finance_fintech": [
        "pay", "cash", "capital", "fin", "vault", "ledger", "fund", "coin",
        "wallet", "bill", "wealth", "yield", "rate", "credit", "vest"
    ]
}

# Curated short brandable root words
SHORT_BRANDABLE_ROOTS = [
    # 3-letter
    "zen", "lux", "neo", "vox", "orb", "pix", "hex", "sky", "arc", "jet",
    "dot", "hub", "fit", "zap", "ray", "vib", "opt", "syn", "nex", "lum",
    # 4-letter pronounceables
    "velo", "koba", "zira", "luma", "nova", "apex", "echo", "flux", "aura",
    "wave", "axon", "lyra", "byte", "nook", "vibe", "zest", "pinn", "fuse",
    "mira", "telo", "orbi", "cyro", "solu", "pave", "soma", "kuro", "tala",
    # 5-letter
    "zenith", "hyper", "pulse", "sonic", "prism", "nexus", "orbit", "spark",
    "swift", "glyph", "voxel", "cortex", "syntx", "astral", "lumos", "verve"
]


def clean_domain_input(raw: str) -> str:
    """Normalize input domain, removing protocol, www, trailing slashes."""
    s = raw.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.rstrip("/")
    return s


def parse_custom_domains(text: str, default_tlds: List[str]) -> List[str]:
    """
    Parse multiline or comma-separated user inputs.
    If a domain already has an extension, keep it.
    If not, combine it with the selected default TLDs.
    """
    raw_lines = re.split(r"[\n,\s]+", text)
    cleaned = []
    seen = set()

    for item in raw_lines:
        clean = clean_domain_input(item)
        if not clean or len(clean) < 2:
            continue

        if "." in clean:
            # Already has extension
            if clean not in seen:
                seen.add(clean)
                cleaned.append(clean)
        else:
            # Append selected TLDs
            for tld in default_tlds:
                tld_clean = tld.strip().lower()
                if not tld_clean.startswith("."):
                    tld_clean = "." + tld_clean
                domain = f"{clean}{tld_clean}"
                if domain not in seen:
                    seen.add(domain)
                    cleaned.append(domain)

    return cleaned


def generate_letter_domains(
    length: int,
    mode: str = "letters",
    pattern: str = "",
    strategy: str = "random",
    max_count: int = 200,
    tlds: List[str] = None
) -> List[str]:
    """
    Generate domains of exact letter length.
    Modes:
      - 'letters': pure a-z
      - 'alphanumeric': a-z, 0-9
      - 'digits': 0-9
      - 'pronounceable': CVCV or VCVC alternating pronounceable patterns
      - 'pattern': e.g. '?ai', 'xx?', '?app?' where ?=letter, #=digit, *=any
    """
    if tlds is None or len(tlds) == 0:
        tlds = [".com"]

    names: List[str] = []
    seen: Set[str] = set()

    # 1. Custom Pattern mode
    if mode == "pattern" and pattern:
        pat = pattern.strip().lower()
        char_sets = []
        for ch in pat:
            if ch == "?":
                char_sets.append("abcdefghijklmnopqrstuvwxyz")
            elif ch == "#":
                char_sets.append("0123456789")
            elif ch == "*":
                char_sets.append("abcdefghijklmnopqrstuvwxyz0123456789")
            else:
                char_sets.append(ch)

        total_possible = 1
        for s in char_sets:
            total_possible *= len(s)

        if strategy == "random" and total_possible > max_count * 2:
            while len(names) < max_count and len(seen) < max_count:
                name = "".join(random.choice(s) for s in char_sets)
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        else:
            for combo in itertools.product(*char_sets):
                name = "".join(combo)
                names.append(name)
                if len(names) >= max_count:
                    break

    # 2. Pronounceable mode (e.g. CVCV, CVCVC, VCVC)
    elif mode == "pronounceable":
        # Form pronounceable pattern based on length
        # For length 3: CVC or VCV
        # For length 4: CVCV or VCVC
        # For length 5: CVCVC or CVCCV
        cv_patterns = []
        if length == 2:
            cv_patterns = ["CV", "VC"]
        elif length == 3:
            cv_patterns = ["CVC", "VCV"]
        elif length == 4:
            cv_patterns = ["CVCV", "VCVC"]
        elif length == 5:
            cv_patterns = ["CVCVC", "CVCVO", "VCVCV"]
        elif length == 6:
            cv_patterns = ["CVCVCV", "CVCVCC"]
        else:
            # Alternating CV pattern
            cv_patterns = ["".join("C" if i % 2 == 0 else "V" for i in range(length))]

        attempts = 0
        target = max_count
        while len(names) < target and attempts < target * 20:
            attempts += 1
            pat = random.choice(cv_patterns)
            candidate = []
            for ch in pat:
                if ch == "C":
                    candidate.append(random.choice(CONSONANTS))
                else:
                    candidate.append(random.choice(VOWELS))
            name = "".join(candidate)
            if name not in seen:
                seen.add(name)
                names.append(name)

    # 3. Standard character set generation (letters, alphanumeric, digits)
    else:
        if mode == "digits":
            chars = "0123456789"
        elif mode == "alphanumeric":
            chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        else:
            chars = "abcdefghijklmnopqrstuvwxyz"

        total_combinations = len(chars) ** length

        if strategy == "random" and total_combinations > max_count:
            # Efficient random sampling without building full product
            attempts = 0
            while len(names) < max_count and attempts < max_count * 15:
                attempts += 1
                name = "".join(random.choice(chars) for _ in range(length))
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        else:
            # Sequential product
            for combo in itertools.product(chars, repeat=length):
                name = "".join(combo)
                names.append(name)
                if len(names) >= max_count:
                    break

    # Multiply across selected TLDs
    final_domains = []
    for name in names:
        for tld in tlds:
            tld_clean = tld.strip().lower()
            if not tld_clean.startswith("."):
                tld_clean = "." + tld_clean
            final_domains.append(f"{name}{tld_clean}")

    return final_domains


def generate_keyword_domains(
    keywords: List[str],
    mode: str = "both",
    custom_affixes: List[str] = None,
    niche_pack: str = "",
    tlds: List[str] = None,
    max_count: int = 300
) -> List[str]:
    """
    Generate domain combinations around keywords.
    Modes:
      - 'prefix': prefix + keyword
      - 'suffix': keyword + suffix
      - 'both': both prefix and suffix combinations
      - 'niche': combine with selected niche word pack
      - 'custom': combine with user provided custom affixes
    """
    if tlds is None or len(tlds) == 0:
        tlds = [".com"]

    affixes_pre: List[str] = []
    affixes_suf: List[str] = []

    if mode == "custom" and custom_affixes:
        affixes_pre = [a.strip().lower() for a in custom_affixes if a.strip()]
        affixes_suf = affixes_pre
    elif mode == "niche" and niche_pack in NICHE_PACKS:
        affixes_pre = NICHE_PACKS[niche_pack]
        affixes_suf = NICHE_PACKS[niche_pack]
    elif mode == "prefix":
        affixes_pre = COMMON_PREFIXES
    elif mode == "suffix":
        affixes_suf = COMMON_SUFFIXES
    else:  # 'both'
        affixes_pre = COMMON_PREFIXES
        affixes_suf = COMMON_SUFFIXES

    names: List[str] = []
    seen: Set[str] = set()

    for kw_raw in keywords:
        kw = clean_domain_input(kw_raw)
        if not kw:
            continue

        # Also add raw keyword by itself
        if kw not in seen:
            seen.add(kw)
            names.append(kw)

        # Prefixes: prefix + keyword
        for pre in affixes_pre:
            name = f"{pre}{kw}"
            if name not in seen:
                seen.add(name)
                names.append(name)
            if len(names) >= max_count:
                break

        # Suffixes: keyword + suffix
        for suf in affixes_suf:
            name = f"{kw}{suf}"
            if name not in seen:
                seen.add(name)
                names.append(name)
            if len(names) >= max_count:
                break

        if len(names) >= max_count:
            break

    # Cross with TLDs
    final_domains = []
    for name in names:
        for tld in tlds:
            tld_clean = tld.strip().lower()
            if not tld_clean.startswith("."):
                tld_clean = "." + tld_clean
            final_domains.append(f"{name}{tld_clean}")

    return final_domains


def generate_brandable_domains(
    tlds: List[str] = None,
    max_count: int = 100
) -> List[str]:
    """Generate high-yield brandable names from curated root words."""
    if tlds is None or len(tlds) == 0:
        tlds = [".com"]

    sample_roots = SHORT_BRANDABLE_ROOTS[:max_count]
    final_domains = []
    for root in sample_roots:
        for tld in tlds:
            tld_clean = tld.strip().lower()
            if not tld_clean.startswith("."):
                tld_clean = "." + tld_clean
            final_domains.append(f"{root}{tld_clean}")

    return final_domains
