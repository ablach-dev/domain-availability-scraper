"""
Authoritative Registry & WHOIS Domain Availability Scraper.
Main entry point. Launches the native desktop GUI by default, or runs CLI mode.
"""

import argparse
import sys
import time
from typing import List
from concurrent.futures import ThreadPoolExecutor

from scraper.whois_checker import (
    check_domain_registry,
    check_domain_hybrid,
    get_tld_from_domain,
)
from scraper.generator import (
    generate_letter_domains,
    generate_keyword_domains,
    generate_brandable_domains,
    parse_custom_domains,
)


def run_cli_scan(args):
    """Run command-line domain availability scan using authoritative Registry WHOIS."""
    domains: List[str] = []
    tlds = [t if t.startswith(".") else f".{t}" for t in args.tld.split(",")]

    if args.domains:
        domains = parse_custom_domains(args.domains, tlds)
    elif args.keyword:
        domains = generate_keyword_domains(
            keywords=args.keyword.split(","),
            mode=args.mode,
            tlds=tlds,
            max_count=args.limit
        )
    elif args.length:
        domains = generate_letter_domains(
            length=args.length,
            mode=args.style,
            pattern=args.pattern or "",
            max_count=args.limit,
            tlds=tlds
        )
    elif args.brandable:
        domains = generate_brandable_domains(tlds=tlds, max_count=args.limit)

    if not domains:
        print("[!] No domains generated. Check your arguments.")
        return

    mode_name = "Strict Registry WHOIS" if args.strict_whois else "Smart Hybrid (DNS Filter + Registry WHOIS)"
    print("=" * 72)
    print("  DOMAIN AVAILABILITY SCRAPER - Authoritative Registry & WHOIS")
    print(f"  Target: {len(domains)} candidate domains")
    print(f"  Engine: {mode_name}")
    print(f"  Concurrency: {args.concurrency} workers | Delay: {args.delay}ms")
    print("=" * 72)

    total = len(domains)
    checked = 0
    available_found = []
    start_time = time.time()
    delay_sec = args.delay / 1000.0

    def check_one(domain: str):
        if delay_sec > 0:
            time.sleep(delay_sec)
        if args.strict_whois:
            return check_domain_registry(domain)
        else:
            return check_domain_hybrid(domain)

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(check_one, d): d for d in domains}

        for f in futures:
            res = f.result()
            checked += 1
            domain = res.get("domain", "")
            status = res.get("status", "error")
            server = res.get("server", "")
            reason = res.get("reason", "")
            elapsed = res.get("elapsed_ms", 0)

            if status == "available":
                available_found.append(domain)
                print(f" \033[92m[AVAILABLE]\033[0m {domain:<28} | {server:<22} | {reason} ({elapsed}ms)")
            elif not args.available_only:
                print(f" \033[90m[TAKEN]    \033[0m {domain:<28} | {server:<22} | {reason} ({elapsed}ms)")

            if checked % 10 == 0 or checked == total:
                cur_elapsed = max(0.001, time.time() - start_time)
                speed = checked / cur_elapsed
                sys.stdout.write(
                    f"\rProgress: {checked}/{total} ({int((checked/total)*100)}%) | "
                    f"Available: {len(available_found)} | Speed: {speed:.1f}/s   "
                )
                sys.stdout.flush()

    print("\n" + "=" * 72)
    print(f"[*] Scan Complete! Found {len(available_found)} verified available domains.")
    if available_found:
        print("\nVerified Available Domains:")
        for d in available_found:
            print(f"  - {d}")


def main():
    parser = argparse.ArgumentParser(description="Domain Availability Scraper - Authoritative Registry & WHOIS")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode instead of Desktop GUI")
    parser.add_argument("--web", action="store_true", help="Run local web server instead of Desktop GUI")
    parser.add_argument("--port", type=int, default=8765, help="Port for optional web server (default: 8765)")

    # CLI scan options
    parser.add_argument("--domains", type=str, help="Comma-separated domains or names to check")
    parser.add_argument("--keyword", type=str, help="Keyword to generate combinations for")
    parser.add_argument("--length", type=int, help="Exact letter length to generate (e.g. 3, 4)")
    parser.add_argument("--style", type=str, default="pronounceable", choices=["pronounceable", "letters", "alphanumeric", "digits", "pattern"], help="Generation style for letter length")
    parser.add_argument("--pattern", type=str, help="Pattern for wildcard letter generation, e.g. '?ai'")
    parser.add_argument("--mode", type=str, default="both", choices=["prefix", "suffix", "both"], help="Affix mode for keywords")
    parser.add_argument("--brandable", action="store_true", help="Scan curated startup brandables")
    parser.add_argument("--tld", type=str, default="com,io,ai", help="Comma-separated TLDs (default: com,io,ai)")
    parser.add_argument("--limit", type=int, default=50, help="Maximum combinations to generate")
    parser.add_argument("--concurrency", type=int, default=12, help="Concurrent workers (default: 12)")
    parser.add_argument("--delay", type=int, default=50, help="Delay in ms between requests (default: 50)")
    parser.add_argument("--strict-whois", action="store_true", help="Directly query registry WHOIS for all domains (bypass DNS filter)")
    parser.add_argument("--available-only", action="store_true", help="Only output available domains in CLI")

    parser.add_argument("--tk", action="store_true", help="Run fallback Tkinter desktop app instead of Fluent UI")

    args = parser.parse_args()

    if args.web:
        from aiohttp import web
        from web.app import create_app
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{args.port}")
        app = create_app()
        web.run_app(app, host="127.0.0.1", port=args.port, print=None)
    elif args.cli or args.domains or args.keyword or args.length or args.brandable:
        run_cli_scan(args)
    elif args.tk:
        from desktop_app import launch_desktop_app
        launch_desktop_app()
    else:
        # Default: Windows 11 Fluent Design Desktop Application
        try:
            from fluent_app import launch_fluent_app
            launch_fluent_app()
        except ImportError:
            from desktop_app import launch_desktop_app
            launch_desktop_app()


if __name__ == "__main__":
    main()
