"""
High-performance asynchronous domain availability checker.
Uses multi-provider DNS-over-HTTPS (Cloudflare + Google DoH) for blazing speed,
with optional RDAP authoritative verification.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, Awaitable
import aiohttp

CLOUDFLARE_DOH = "https://cloudflare-dns.com/dns-query"
GOOGLE_DOH = "https://dns.google/resolve"
RDAP_BASE = "https://rdap.org/domain"

USER_AGENT = "DomainPulse/2.0 (High-Speed Availability Scanner)"


class DomainCheckResult:
    def __init__(
        self,
        domain: str,
        status: str,  # 'available', 'taken', 'error'
        response_time_ms: float = 0.0,
        method: str = "DNS-DoH",
        details: str = "",
        dns_status: Optional[int] = None
    ):
        self.domain = domain
        self.status = status
        self.response_time_ms = round(response_time_ms, 1)
        self.method = method
        self.details = details
        self.dns_status = dns_status
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.domain,
            "status": self.status,
            "response_time_ms": self.response_time_ms,
            "method": self.method,
            "details": self.details,
            "dns_status": self.dns_status,
            "timestamp": self.timestamp
        }


class DomainChecker:
    def __init__(
        self,
        concurrency: int = 25,
        deep_check: bool = False,
        delay_ms: int = 0
    ):
        self.concurrency = max(1, min(concurrency, 60))
        self.deep_check = deep_check
        self.delay_ms = delay_ms
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._is_paused = asyncio.Event()
        self._is_paused.set()  # Not paused initially
        self._is_cancelled = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=100
            )
            timeout = aiohttp.ClientTimeout(total=4.0, connect=2.0)
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "application/dns-json, application/json, */*"
            }
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=headers
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def pause(self):
        self._is_paused.clear()

    def resume(self):
        self._is_paused.set()

    def stop(self):
        self._is_cancelled = True
        self._is_paused.set()  # Unblock in case it's paused

    async def check_single_domain(self, domain: str) -> DomainCheckResult:
        """
        Check a single domain's availability using DoH + optional RDAP.
        """
        domain = domain.strip().lower()
        if not domain or "." not in domain:
            return DomainCheckResult(domain, "error", details="Invalid domain format")

        session = await self._get_session()
        t0 = time.time()

        # Step 1: Cloudflare DoH query for NS records
        dns_status = None
        method = "Cloudflare-DoH"
        cf_headers = {"Accept": "application/dns-json"}
        try:
            params = {"name": domain, "type": "NS"}
            async with session.get(CLOUDFLARE_DOH, params=params, headers=cf_headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    dns_status = data.get("Status")
                elif resp.status == 429:
                    dns_status = None
        except Exception:
            dns_status = None

        # Fallback to Google DoH if Cloudflare had an issue
        if dns_status is None:
            try:
                method = "Google-DoH"
                params = {"name": domain, "type": "NS"}
                goog_headers = {"Accept": "application/json"}
                async with session.get(GOOGLE_DOH, params=params, headers=goog_headers) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        dns_status = data.get("Status")
            except Exception as e:
                elapsed = (time.time() - t0) * 1000
                return DomainCheckResult(domain, "error", elapsed, "DNS-Error", str(e))

        elapsed = (time.time() - t0) * 1000

        # DNS Status Interpretation:
        # Status 0 = NOERROR (Registered domain)
        # Status 3 = NXDOMAIN (Domain does not exist -> very likely available)
        # Status 2 = SERVFAIL (Could mean DNS failure or unassigned)
        if dns_status == 0:
            return DomainCheckResult(
                domain,
                status="taken",
                response_time_ms=elapsed,
                method=method,
                details="Active DNS records (NOERROR)",
                dns_status=0
            )

        if dns_status == 3:
            # Domain has no DNS records.
            # If deep check is requested, verify via RDAP
            if self.deep_check:
                try:
                    rdap_url = f"{RDAP_BASE}/{domain}"
                    t_rdap = time.time()
                    async with session.get(
                        rdap_url,
                        timeout=aiohttp.ClientTimeout(total=3.0),
                        allow_redirects=True
                    ) as rdap_resp:
                        rdap_elapsed = (time.time() - t0) * 1000
                        if rdap_resp.status == 404:
                            return DomainCheckResult(
                                domain,
                                status="available",
                                response_time_ms=rdap_elapsed,
                                method="RDAP-Verified",
                                details="Unregistered (RDAP 404)",
                                dns_status=3
                            )
                        elif rdap_resp.status in (200, 302, 301):
                            return DomainCheckResult(
                                domain,
                                status="taken",
                                response_time_ms=rdap_elapsed,
                                method="RDAP-Verified",
                                details="Registered (RDAP Record Found)",
                                dns_status=3
                            )
                except Exception:
                    pass  # Fall back to DoH result

            return DomainCheckResult(
                domain,
                status="available",
                response_time_ms=elapsed,
                method=method,
                details="No DNS records (NXDOMAIN)",
                dns_status=3
            )

        # Other DNS Status (e.g. SERVFAIL or REFUSED)
        return DomainCheckResult(
            domain,
            status="available" if dns_status == 3 else "taken",
            response_time_ms=elapsed,
            method=method,
            details=f"DNS Status {dns_status}",
            dns_status=dns_status
        )

    async def scan_queue(
        self,
        domains: list,
        on_result: Optional[Callable[[DomainCheckResult], Awaitable[None]]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        """
        Run high-concurrency scan across domains list.
        Emits real-time result events and progress metrics.
        """
        total = len(domains)
        checked = 0
        available_count = 0
        taken_count = 0
        error_count = 0
        start_time = time.time()

        async def worker(domain: str):
            nonlocal checked, available_count, taken_count, error_count

            if self._is_cancelled:
                return

            await self._is_paused.wait()

            async with self._semaphore:
                if self._is_cancelled:
                    return

                if self.delay_ms > 0:
                    await asyncio.sleep(self.delay_ms / 1000.0)

                res = await self.check_single_domain(domain)
                checked += 1

                if res.status == "available":
                    available_count += 1
                elif res.status == "taken":
                    taken_count += 1
                else:
                    error_count += 1

                if on_result:
                    await on_result(res)

                if on_progress:
                    elapsed = max(0.001, time.time() - start_time)
                    speed = checked / elapsed
                    remaining = total - checked
                    eta = remaining / speed if speed > 0 else 0

                    await on_progress({
                        "total": total,
                        "checked": checked,
                        "available": available_count,
                        "taken": taken_count,
                        "errors": error_count,
                        "speed": round(speed, 1),
                        "elapsed": round(elapsed, 1),
                        "eta": round(eta, 1),
                        "percent": round((checked / total) * 100, 1) if total > 0 else 100.0,
                        "is_complete": checked >= total
                    })

        tasks = [asyncio.create_task(worker(d)) for d in domains]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self.close()
