# DomainPulse ⚡

A fast, clean, professional **native desktop application** for domain availability scraping and generation. Built in Python using `CustomTkinter` and direct socket queries to authoritative TLD Registry WHOIS servers (Verisign, Identity Digital, PIR, Google Registry, CentralNic) with RDAP fallback.

---

## 🎯 Accurate Registry Availability (No False Positives)

Standard DNS-only checkers rely on `NXDOMAIN` to claim a domain is available. This produces false positives because tens of thousands of registered domains sit parked without nameservers or with inactive DNS.

**DomainPulse solves this by querying the actual registry databases:**
- **.com / .net / .cc / .tv**: Authoritative Verisign Registry WHOIS (`whois.verisign-grs.com`) using exact match syntax (`=domain`).
- **.io / .ai / .sh / .ac**: Identity Digital Registry WHOIS (`whois.nic.io`, `whois.nic.ai`).
- **.org / .ngo**: Public Interest Registry (`whois.pir.org`).
- **.app / .dev / .page**: Google Registry (`whois.nic.google`).
- **.co**: CoInternet / Registry.co (`whois.registry.co`).
- **.xyz / .tech / .online / .store / .club**: Respective registry WHOIS servers with dynamic IANA root discovery (`whois.iana.org`) for arbitrary new gTLDs and ccTLDs.
- **ICANN RDAP Fallback**: Automated HTTPS RDAP verification for strict TLD compliance.

A domain is **ONLY** marked `AVAILABLE` if the authoritative registry responds with confirmed unregistered signatures (e.g. `No match for domain`, `Domain not found`, `The queried object does not exist`).

---

## 🖥️ Professional Desktop UI

No web server required, no bloated browser tabs, no animated gradients or "ai slop" styling. A clean, native Windows desktop application:

- **Clean Two-Panel Layout**:
  - **Left Sidebar**: Search mode parameters, TLD presets, and engine settings.
  - **Right Main Panel**: Metric counters, real-time progress bar, search/filter controls, and a high-performance spreadsheet data grid (`ttk.Treeview`).
- **Data Table Columns**:
  - `Domain` (bold/monospace)
  - `Status` (Clean green `AVAILABLE`, muted gray `TAKEN`)
  - `Length` (Character count)
  - `Registry Server` (e.g. `whois.verisign-grs.com`, `whois.nic.io`)
  - `WHOIS Response` (Signature returned by the registry)
  - `Latency` (ms)
- **Instant Filtering & Sorting**:
  - Radio buttons: `All`, `Available Only`, `Taken Only`.
  - Real-time search filter box to narrow down results instantly.
  - Click any column header to sort (A-Z, length, response time).
- **Interactive Actions**:
  - **Right-Click Context Menu**: Copy domain, copy all available, open direct register links (Porkbun, Namecheap, GoDaddy), or view the raw full WHOIS text response in a detail popup.
  - **Double-Click**: Instantly opens registrar checkout search.
  - **Bulk Export**: Native Windows file save dialogs for **CSV** and **TXT**.

---

## 🔍 4 Search & Generation Modes

1. **Batch List / Custom**:
   - Paste arbitrary domains or words (one per line). Names without extensions automatically combine with selected TLDs.
2. **Letter Length Generator**:
   - Select exact character length (2, 3, 4, 5, 6+ letters).
   - Styles:
     - **Pronounceable (CVCV / VCVC)**: High-yield brandable names (e.g. `velo`, `koba`, `zira`, `telo`).
     - **Letters (a-z)**.
     - **Alphanumeric (a-z, 0-9)**.
     - **Digits Only (0-9)**.
     - **Custom Wildcard Pattern**: e.g., `?ai`, `xx?`, `?app?` (`?` = letter, `#` = digit).
   - Configurable generation limit (25, 50, 100, 200, 500).
3. **Keyword Combinator**:
   - Enter base keyword (e.g., `cloud`, `pay`, `flow`).
   - Modes: `Prefix & Suffix`, `Prefixes Only`, `Suffixes Only`, `Niche Pack`, or `Custom Words`.
   - Built-in Niche Packs: **Tech & SaaS**, **AI & ML**, **Crypto & Web3**, **Creative & Agency**, **Finance & Fintech**.
4. **Curated Brandables**:
   - Tests short, ultra-premium root words across your chosen TLDs.

---

## ⚙️ Verification Engine Settings

- **Hybrid Mode (Recommended)**:
  - Stage 1: Checks if domain has active DNS/IP records. If active, it is registered (taken).
  - Stage 2: For any domain with NO active DNS, queries the **Authoritative Registry WHOIS**. Only marked `AVAILABLE` if the registry responds "No match / Domain not found".
  - *Saves bandwidth while guaranteeing 0% false positives.*
- **Strict Registry WHOIS Mode**:
  - Queries authoritative registry WHOIS port 43 or RDAP directly for every single candidate domain.
- **Worker Concurrency Slider**: 3 to 25 parallel threads.
- **Request Delay Slider**: 0ms to 500ms to respect registry connection rate limits.

---

## 🚀 How to Run

### 1. Launch with Windows Batch File
Double-click `run.bat` in the project root.

### 2. Launch via Python
```bash
python main.py
```

### 3. Command-Line Interface (CLI Mode)
You can also run headless scans directly in the console:

```bash
# Search 3-letter pronounceable domains on .io and .ai
python main.py --cli --length 3 --style pronounceable --tld io,ai --limit 20

# Search keyword 'flow' + suffixes on .ai
python main.py --cli --keyword flow --mode suffix --tld ai --limit 15

# Strict registry WHOIS for specific domains (only output available)
python main.py --cli --domains google.com,apple.com,nonexistentxyz998811.com --strict-whois --available-only
```

---

## 🧪 Automated Test Suite

Run the full suite of 16 unit and integration tests:

```bash
python -m unittest discover tests
```
*Tests cover generator algorithms, TLD root server discovery, Verisign/Identity Digital/PIR signature parsing, and desktop GUI initialization.*
