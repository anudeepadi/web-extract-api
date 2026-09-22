"""Exercise the real SSE route against a local HTML fixture; no API keys used."""
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from scraper_api import app

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

engine = sys.argv[1] if len(sys.argv) > 1 else "crawl4ai"
if engine not in {"crawl4ai", "scrapy"}:
    raise SystemExit("Use crawl4ai or scrapy; this example never calls Firecrawl.")
server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "examples")))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    url = f"http://127.0.0.1:{server.server_port}/article.html"
    with TestClient(app) as client:
        response = client.post("/api/scrape", json={
            "url": url, "scraper": engine, "wait_for_js": False,
            "wait_time": 0, "only_main_content": False,
            "remove_links": True, "remove_images": True,
        })
    response.raise_for_status()
    result = None
    for event in response.text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in event.splitlines() if ": " in line)
        if fields.get("event") == "error":
            raise RuntimeError(fields["data"])
        if fields.get("event") == "result":
            result = json.loads(fields["data"])
    assert result is not None, response.text
    assert result["title"] == "Planning a small documentation release", result
    assert "synthetic article" in result["content"], result
    assert result["word_count"] == len(result["content"].split()), result
    assert result["scraper_used"] == engine, result
    print(json.dumps(result, indent=2))
finally:
    server.shutdown()
    server.server_close()
    thread.join()
