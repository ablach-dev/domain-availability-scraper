# Domain Availability Scraper

An authoritative domain availability scraper and desktop application built with Python, PyQt6, and Windows 11 Fluent Design. The application performs direct socket queries to authoritative TLD Registry WHOIS servers (Verisign, Identity Digital, PIR, Google Registry, CentralNic) with ICANN RDAP fallback to prevent false positives from parked or inactive domains.

---

## Technical Overview

### Registry Authoritative Verification vs DNS Resolution
Standard domain checking tools rely on DNS `NXDOMAIN` status to determine availability. This methodology is fundamentally flawed: tens of thousands of registered domains sit parked without active nameservers or have DNS records disabled. A domain that returns `NXDOMAIN` on public resolvers may still be actively registered and owned at the registry level.

This tool queries official registry databases on TCP Port 43:
- `.com` / `.net` / `.cc` / `.tv`: Verisign Registry WHOIS (`whois.verisign-grs.com`) using exact match prefix syntax (`=domain`).
- `.io` / `.ai` / `.sh`: Identity Digital Registry WHOIS (`whois.nic.io`, `whois.nic.ai`).
- `.org`: Public Interest Registry (`whois.pir.org`).
- `.co`: CoInternet / Registry.co (`whois.registry.co`).
- `.app` / `.dev`: Google Registry (`whois.nic.google`).
- Other gTLDs and ccTLDs: Dynamic IANA root discovery (`whois.iana.org`) with automated HTTPS RDAP fallback.

A domain is classified as `AVAILABLE` only when the authoritative registry returns confirmed unregistered signatures (e.g., `No match for domain`, `Domain not found`, `The queried object does not exist`).

---

## Desktop Architecture

The desktop interface is built using PyQt6 and Windows 11 Fluent Design components:

- **Splitter Layout**: Resizable control panel and live data grid allowing flexible side-by-side workflow.
- **Search Modes**:
  - `Batch List`: Raw multiline domain or keyword input with automatic TLD expansion.
  - `Letter Length`: Exact character length selector (2 to 12 letters) supporting pronounceable CVCV/VCVC patterns, alphanumeric sets, digits, and wildcard pattern matching (`?` for letter, `#` for digit).
  - `Keyword Affixes`: Keyword prefix, suffix, both, and industry niche packs (Tech & SaaS, AI & ML, Crypto, Creative, Finance).
  - `Brandables`: Curated high-demand short brandable roots.
- **Interactive Extension Selector**:
  - Preset filters: Popular, Tech, Startup, Short, All, and Clear.
  - Pill-style checkable buttons for active extensions.
  - Custom TLD input with inline Add button to dynamically register arbitrary extensions into the active search pool.
- **Engine Configuration**:
  - Verification mode selector: Hybrid (DNS pre-filter + Registry WHOIS verification) or Strict Registry WHOIS (direct Port 43 for all candidates).
  - Worker thread slider (3 to 25 threads).
  - Request delay slider (0 to 500 ms) to prevent registry rate limiting and IP blocking.
- **Data Table**:
  - High-DPI table view with columns for Domain, Status, Length, Registry Server, WHOIS Signature, and Latency.
  - Sortable column headers.
  - Real-time text search filter and status radio filters (All, Available Only, Taken Only).
  - Right-click context menu: Copy domain, copy all available, open in registrar search (Porkbun, Namecheap, GoDaddy), or inspect raw WHOIS text responses.
  - Native file save dialogs for CSV and TXT exports.

---

## Performance Analysis: Python vs Go

A common question for high-throughput network scrapers is whether rewriting the engine in Go provides a performance benefit.

### 1. Network I/O vs CPU Overhead
Domain checking is almost entirely I/O-bound. The process consists of sending small TCP packets (50–100 bytes) to remote WHOIS servers on port 43 and waiting for the response. 
- Local CPU compute (string matching and regex parsing) accounts for less than 1% of total cycle time.
- Network latency (round-trip time to Verisign or Identity Digital servers) accounts for over 99% of query duration (typically 40–150 ms per query).

### 2. Registry Rate Limits
Authoritative registry servers strictly enforce IP-based rate limiting:
- Verisign (`whois.verisign-grs.com`) and Identity Digital (`whois.nic.io`) throttle or ban IP addresses that exceed continuous connection thresholds (generally 20–50 queries per second from a single IP).
- Even if a compiled Go binary can spawn 10,000 goroutines per second, sending that volume to registry servers from a single workstation will result in immediate connection resets (`ECONNRESET`) and temporary IP bans.

### 3. Engine Optimizations Applied in Python
Instead of a language rewrite, the following optimizations maximize throughput within registry safety limits:
- **Two-Stage Hybrid Pipeline**: Rapid DNS pre-filtering skips known active domains in milliseconds, reserving registry socket bandwidth for actual available candidates.
- **Thread Pool Concurrency**: Concurrent thread pools dispatch multiple queries in parallel up to the registry's maximum safe rate.
- **Local In-Memory Cache**: Repeated lookups within a session resolve with zero network latency.

For single-machine desktop software, Python with PyQt6 delivers optimal performance while maintaining a native Windows 11 user interface.

---

## Requirements and Installation

### Prerequisites
- Python 3.10 or higher
- Windows 10/11 (for Fluent Design effects)

### Installation
Clone the repository and install dependencies:

```bash
git clone https://github.com/ablach-dev/domain-availability-scraper.git
cd domain-availability-scraper
pip install -r requirements.txt
```

Dependencies include:
- `PyQt6` (Qt 6 bindings)
- `PyQt6-Fluent-Widgets` (Windows 11 Fluent Design components)
- `customtkinter` (Alternative GUI fallback)
- `aiohttp` (Asynchronous HTTP / DoH client)
- `pillow` (Image rendering)

---

## Usage

### Native Desktop Application
Launch the desktop application:

```bash
python main.py
```
Or double-click `run.bat` on Windows.

### Command-Line Interface (CLI Mode)
To run headless scans directly in the console:

```bash
# Search 3-letter pronounceable .io and .ai domains
python main.py --cli --length 3 --style pronounceable --tld io,ai --limit 20

# Search keyword combinations on .ai with strict registry check
python main.py --cli --keyword flow --mode suffix --tld ai --limit 15 --strict-whois

# Check specific domain list and print available domains only
python main.py --cli --domains google.com,apple.com,nonexistentxyz998811.com --strict-whois --available-only
```

### CLI Parameters
| Flag | Description | Default |
|---|---|---|
| `--cli` | Run in command-line mode | `False` |
| `--domains` | Comma-separated list of domains or words | `None` |
| `--keyword` | Base keyword for affix combinations | `None` |
| `--length` | Exact character length | `None` |
| `--style` | Letter style (`pronounceable`, `letters`, `alphanumeric`, `digits`, `pattern`) | `pronounceable` |
| `--pattern` | Wildcard pattern (`?`=letter, `#`=digit, `*`=any) | `None` |
| `--mode` | Keyword affix mode (`prefix`, `suffix`, `both`) | `both` |
| `--brandable` | Check curated startup roots | `False` |
| `--tld` | Comma-separated target TLDs | `com,io,ai` |
| `--limit` | Maximum combinations to generate | `50` |
| `--concurrency` | Worker thread count | `12` |
| `--delay` | Delay between socket requests in ms | `50` |
| `--strict-whois` | Direct Port 43 query for all domains | `False` |
| `--available-only` | Filter console output to available domains | `False` |

---

## Test Suite

Run the automated test suite covering socket parsing, root discovery, and UI initialization:

```bash
python -m unittest discover tests
```
