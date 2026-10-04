"""
High-performance aiohttp web application for DomainPulse.
Provides REST endpoints, static file serving, and native WebSocket streaming.
"""

import asyncio
import json
import os
from typing import List, Optional, Dict, Any
from aiohttp import web, WSMsgType

from scraper.checker import DomainChecker, DomainCheckResult
from scraper.generator import (
    generate_letter_domains,
    generate_keyword_domains,
    generate_brandable_domains,
    parse_custom_domains,
    NICHE_PACKS,
    COMMON_PREFIXES,
    COMMON_SUFFIXES
)
from scraper.tlds import TLD_PRESETS, ALL_COMMON_TLDS, get_registrar_links

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


async def serve_index(request: web.Request) -> web.Response:
    """Serve the main index.html page."""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()
    return web.Response(text=content, content_type="text/html")


async def get_presets(request: web.Request) -> web.Response:
    """Return TLD presets and niche packs."""
    data = {
        "tld_presets": TLD_PRESETS,
        "all_tlds": ALL_COMMON_TLDS,
        "niche_packs": list(NICHE_PACKS.keys()),
        "sample_prefixes": COMMON_PREFIXES[:12],
        "sample_suffixes": COMMON_SUFFIXES[:12],
    }
    return web.json_response(data)


async def generate_domains_api(request: web.Request) -> web.Response:
    """Generate domain candidates without running a scan."""
    try:
        req = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    mode = req.get("mode", "custom")
    tlds = req.get("tlds", [".com"])
    if not tlds:
        tlds = [".com"]

    domains: List[str] = []

    if mode == "custom":
        domains = parse_custom_domains(req.get("custom_text", ""), tlds)

    elif mode == "letters":
        domains = generate_letter_domains(
            length=int(req.get("letter_length", 3)),
            mode=req.get("letter_mode", "letters"),
            pattern=req.get("letter_pattern", ""),
            strategy=req.get("letter_strategy", "random"),
            max_count=int(req.get("letter_count", 100)),
            tlds=tlds
        )

    elif mode == "keyword":
        raw_kws = req.get("keywords", [])
        if isinstance(raw_kws, str):
            raw_kws = [raw_kws]
        domains = generate_keyword_domains(
            keywords=raw_kws,
            mode=req.get("keyword_mode", "both"),
            custom_affixes=req.get("custom_affixes", []),
            niche_pack=req.get("niche_pack", ""),
            tlds=tlds,
            max_count=int(req.get("keyword_count", 200))
        )

    elif mode == "brandable":
        domains = generate_brandable_domains(
            tlds=tlds,
            max_count=int(req.get("brandable_count", 50))
        )

    return web.json_response({
        "count": len(domains),
        "domains": domains
    })


async def quick_check_domain(request: web.Request) -> web.Response:
    """Check a single domain on-demand."""
    domain = request.query.get("domain", "").strip()
    deep = request.query.get("deep", "false").lower() in ("true", "1")

    if not domain:
        return web.json_response({"error": "domain query param required"}, status=400)

    checker = DomainChecker(concurrency=1, deep_check=deep)
    res = await checker.check_single_domain(domain)
    await checker.close()

    result_dict = res.to_dict()
    result_dict["registrar_links"] = get_registrar_links(res.domain)
    return web.json_response(result_dict)


async def websocket_scan(request: web.Request) -> web.WebSocketResponse:
    """WebSocket endpoint for real-time bidirectional scan streaming."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    checker: Optional[DomainChecker] = None
    scan_task: Optional[asyncio.Task] = None

    async def on_result_callback(r: DomainCheckResult):
        data = r.to_dict()
        data["registrar_links"] = get_registrar_links(r.domain)
        try:
            await ws.send_json({
                "type": "result",
                "data": data
            })
        except Exception:
            pass

    async def on_progress_callback(p: Dict[str, Any]):
        try:
            await ws.send_json({
                "type": "progress",
                "data": p
            })
        except Exception:
            pass

    async def run_scan_coro(domains, concurrency, deep_check, delay_ms):
        nonlocal checker
        checker = DomainChecker(
            concurrency=concurrency,
            deep_check=deep_check,
            delay_ms=delay_ms
        )
        try:
            await checker.scan_queue(
                domains,
                on_result=on_result_callback,
                on_progress=on_progress_callback
            )
            await ws.send_json({"type": "finished"})
        except asyncio.CancelledError:
            await ws.send_json({"type": "stopped"})
        except Exception as e:
            await ws.send_json({"type": "error", "message": str(e)})

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    continue

                action = payload.get("action")

                if action == "start":
                    if scan_task and not scan_task.done():
                        if checker:
                            checker.stop()
                        scan_task.cancel()

                    domains = payload.get("domains", [])
                    concurrency = int(payload.get("concurrency", 25))
                    deep_check = bool(payload.get("deep_check", False))
                    delay_ms = int(payload.get("delay_ms", 0))

                    if not domains:
                        await ws.send_json({"type": "error", "message": "No domains to scan."})
                        continue

                    scan_task = asyncio.create_task(
                        run_scan_coro(domains, concurrency, deep_check, delay_ms)
                    )

                elif action == "pause":
                    if checker:
                        checker.pause()
                    await ws.send_json({"type": "status", "status": "paused"})

                elif action == "resume":
                    if checker:
                        checker.resume()
                    await ws.send_json({"type": "status", "status": "running"})

                elif action == "stop":
                    if checker:
                        checker.stop()
                    if scan_task and not scan_task.done():
                        scan_task.cancel()
                    await ws.send_json({"type": "status", "status": "stopped"})

            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break

    finally:
        if checker:
            checker.stop()
        if scan_task and not scan_task.done():
            scan_task.cancel()

    return ws


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application()
    app.router.add_get("/", serve_index)
    app.router.add_get("/api/presets", get_presets)
    app.router.add_post("/api/generate", generate_domains_api)
    app.router.add_get("/api/quick-check", quick_check_domain)
    app.router.add_get("/ws/scan", websocket_scan)
    app.router.add_static("/static", STATIC_DIR, name="static")
    return app
