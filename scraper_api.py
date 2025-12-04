#!/usr/bin/env python3
"""
Web Scraper API with SSE (Server-Sent Events) for live output
Supports advanced Crawl4AI features for hard-to-scrape sites
"""

import asyncio
import json
import re
import hashlib
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter, BM25ContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

app = FastAPI(title="Web Scraper API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    url: HttpUrl
    # JavaScript/Dynamic content options
    wait_for_js: bool = True
    wait_time: float = 2.0
    scroll_page: bool = False
    # Anti-detection options
    stealth_mode: bool = False
    custom_user_agent: Optional[str] = None
    # Content preprocessing
    remove_links: bool = False
    remove_images: bool = False
    remove_nav_footer: bool = True
    only_main_content: bool = True
    # Advanced extraction
    css_selector: Optional[str] = None
    excluded_tags: Optional[list[str]] = None
    use_bm25_filter: bool = False


class TextPreprocessor:
    """Clean and preprocess scraped content."""

    @staticmethod
    def remove_links(text: str) -> str:
        # Remove markdown links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove raw URLs
        text = re.sub(r'https?://\S+', '', text)
        return text

    @staticmethod
    def remove_images(text: str) -> str:
        # Remove markdown images
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
        return text

    @staticmethod
    def remove_nav_footer(text: str) -> str:
        patterns = [
            r'(?i)skip to (?:main )?content',
            r'(?i)cookie (?:policy|settings|notice)',
            r'(?i)privacy policy',
            r'(?i)terms (?:of use|and conditions|of service)',
            r'(?i)©\s*\d{4}.*?(?:all rights reserved)?',
            r'(?i)follow us on.*?(?:\n|$)',
            r'(?i)share (?:this page|on).*?(?:\n|$)',
            r'(?i)subscribe to (?:our )?newsletter',
            r'(?i)sign up for (?:our )?email',
            r'(?i)back to top',
            r'(?i)accessibility',
            r'(?i)site ?map',
        ]
        for pattern in patterns:
            text = re.sub(pattern, '', text)
        return text

    @staticmethod
    def clean_whitespace(text: str) -> str:
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    @staticmethod
    def extract_main_content(text: str) -> str:
        """Try to extract main content by removing menu/sidebar patterns."""
        lines = text.split('\n')
        content_lines = []
        in_menu = False

        for line in lines:
            stripped = line.strip()
            # Skip short lines that look like menu items
            if len(stripped) < 50 and stripped.startswith('* ['):
                in_menu = True
                continue
            if in_menu and stripped == '':
                in_menu = False
                continue
            if not in_menu:
                content_lines.append(line)

        return '\n'.join(content_lines)


async def stream_scrape(request: ScrapeRequest):
    """Generator for SSE streaming of scrape progress."""

    def send_event(event_type: str, data: dict):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    url = str(request.url)

    yield send_event("status", {"message": "Initializing scraper...", "progress": 5})

    try:
        # Configure browser
        browser_config = BrowserConfig(
            headless=True,
            java_script_enabled=request.wait_for_js,
            enable_stealth=request.stealth_mode,
            viewport_width=1920,
            viewport_height=1080,
        )

        if request.custom_user_agent:
            browser_config.user_agent = request.custom_user_agent

        yield send_event("status", {"message": "Browser configured", "progress": 15})

        # Configure content filter
        if request.use_bm25_filter:
            content_filter = BM25ContentFilter(
                user_query="main content article body",
                bm25_threshold=1.0
            )
            yield send_event("status", {"message": "Using BM25 content filter", "progress": 20})
        elif request.only_main_content:
            content_filter = PruningContentFilter(
                threshold=0.4,
                threshold_type="dynamic"
            )
            yield send_event("status", {"message": "Using pruning filter", "progress": 20})
        else:
            content_filter = None

        markdown_generator = DefaultMarkdownGenerator(
            content_filter=content_filter
        ) if content_filter else DefaultMarkdownGenerator()

        # Build excluded tags
        excluded = list(request.excluded_tags) if request.excluded_tags else []
        if request.remove_images:
            excluded.extend(['img', 'svg', 'picture', 'figure'])
        if request.remove_nav_footer:
            excluded.extend(['nav', 'footer', 'aside', 'header'])

        # Configure crawler
        crawler_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            markdown_generator=markdown_generator,
            wait_until="networkidle" if request.wait_for_js else "domcontentloaded",
            page_timeout=60000,
            delay_before_return_html=request.wait_time,
            css_selector=request.css_selector,
            excluded_tags=excluded if excluded else None,
            scan_full_page=request.scroll_page,
        )

        yield send_event("status", {"message": f"Fetching: {url}", "progress": 30})

        async with AsyncWebCrawler(config=browser_config, verbose=False) as crawler:
            yield send_event("status", {"message": "Browser launched, navigating...", "progress": 40})

            result = await crawler.arun(url=url, config=crawler_config)

            yield send_event("status", {"message": "Page loaded, extracting content...", "progress": 60})

            if not result.success:
                yield send_event("error", {"message": f"Scrape failed: {result.error_message}"})
                return

            # Extract markdown
            markdown_content = ""
            if result.markdown:
                if hasattr(result.markdown, 'raw_markdown'):
                    markdown_content = result.markdown.raw_markdown or ""
                elif hasattr(result.markdown, 'fit_markdown'):
                    markdown_content = result.markdown.fit_markdown or ""
                elif isinstance(result.markdown, str):
                    markdown_content = result.markdown
                else:
                    markdown_content = str(result.markdown)

            yield send_event("status", {"message": "Preprocessing content...", "progress": 75})

            # Apply preprocessing
            preprocessor = TextPreprocessor()
            processed = markdown_content

            if request.remove_links:
                processed = preprocessor.remove_links(processed)
                yield send_event("status", {"message": "Removed links", "progress": 80})

            if request.remove_images:
                processed = preprocessor.remove_images(processed)
                yield send_event("status", {"message": "Removed images", "progress": 82})

            if request.remove_nav_footer:
                processed = preprocessor.remove_nav_footer(processed)
                yield send_event("status", {"message": "Removed nav/footer", "progress": 85})

            if request.only_main_content:
                processed = preprocessor.extract_main_content(processed)
                yield send_event("status", {"message": "Extracted main content", "progress": 88})

            processed = preprocessor.clean_whitespace(processed)

            yield send_event("status", {"message": "Finalizing...", "progress": 95})

            # Build result
            title = ""
            if result.metadata and result.metadata.get('title'):
                title = result.metadata['title']

            doc_id = hashlib.md5(url.encode()).hexdigest()[:12]
            word_count = len(processed.split())

            output = {
                "doc_id": doc_id,
                "url": url,
                "title": title,
                "content": processed,
                "word_count": word_count,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "settings_used": {
                    "stealth_mode": request.stealth_mode,
                    "wait_for_js": request.wait_for_js,
                    "remove_links": request.remove_links,
                    "remove_images": request.remove_images,
                    "only_main_content": request.only_main_content,
                }
            }

            yield send_event("status", {"message": "Complete!", "progress": 100})
            yield send_event("result", output)

    except Exception as e:
        yield send_event("error", {"message": str(e)})


@app.post("/api/scrape")
async def scrape_url(request: ScrapeRequest):
    """Scrape a URL with SSE streaming for live output."""
    return StreamingResponse(
        stream_scrape(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# Serve static files (frontend)
try:
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
except:
    pass  # Static folder might not exist yet


if __name__ == "__main__":
    import uvicorn
    print("Starting Scraper API on http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
