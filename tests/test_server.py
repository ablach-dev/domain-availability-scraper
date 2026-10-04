"""
Integration tests for DomainPulse web server and WebSocket streaming.
"""

import unittest
import asyncio
import aiohttp
from web.app import create_app
from aiohttp.test_utils import TestServer, TestClient


class TestWebServer(unittest.TestCase):

    def test_web_app_endpoints(self):
        async def run_tests():
            app = create_app()
            client = TestClient(TestServer(app))
            await client.start_server()
            try:
                # 1. Index
                r = await client.get("/")
                self.assertEqual(r.status, 200)
                text = await r.text()
                self.assertIn("DomainPulse", text)

                # 2. Presets
                r = await client.get("/api/presets")
                self.assertEqual(r.status, 200)
                data = await r.json()
                self.assertIn("tld_presets", data)

                # 3. Generate
                r = await client.post(
                    "/api/generate",
                    json={
                        "mode": "letters",
                        "tlds": [".io"],
                        "letter_length": 3,
                        "letter_mode": "pronounceable",
                        "letter_count": 5
                    }
                )
                self.assertEqual(r.status, 200)
                gen_data = await r.json()
                self.assertEqual(gen_data["count"], 5)

                # 4. Quick check
                r = await client.get("/api/quick-check?domain=google.com")
                self.assertEqual(r.status, 200)
                qc = await r.json()
                self.assertEqual(qc["status"], "taken")

                # 5. WebSocket scan
                ws = await client.ws_connect("/ws/scan")
                await ws.send_json({
                    "action": "start",
                    "domains": ["google.com", "nonexistentdomain999xyz.com"],
                    "concurrency": 5
                })

                results = []
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        d = msg.json()
                        if d.get("type") == "result":
                            results.append(d["data"])
                        elif d.get("type") == "finished":
                            break

                await ws.close()
                self.assertEqual(len(results), 2)
                statuses = {res["domain"]: res["status"] for res in results}
                self.assertEqual(statuses["google.com"], "taken")
                self.assertEqual(statuses["nonexistentdomain999xyz.com"], "available")

            finally:
                await client.close()

        asyncio.run(run_tests())


if __name__ == "__main__":
    unittest.main()
