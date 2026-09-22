#!/usr/bin/env python3
"""
Web Scraper API with SSE (Server-Sent Events) for live output
Supports multiple scraping engines: Crawl4AI, Scrapy, and Firecrawl
"""

import asyncio
import json
import re
import hashlib
import os
from datetime import datetime, timezone
from typing import Optional, Literal
from dataclasses import dataclass, asdict
from enum import Enum

# Environment variables for API keys
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl

# Crawl4AI imports
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter, BM25ContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

# Scrapy imports
import scrapy
from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from scrapy.signalmanager import dispatcher
from scrapy import signals
from twisted.internet import reactor, defer
from twisted.internet.asyncioreactor import AsyncioSelectorReactor
import threading

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

# Firecrawl import (optional - requires API key)
try:
    from firecrawl import Firecrawl
    FIRECRAWL_AVAILABLE = True
except ImportError:
    FIRECRAWL_AVAILABLE = False


class ScraperType(str, Enum):
    CRAWL4AI = "crawl4ai"
    SCRAPY = "scrapy"
    FIRECRAWL = "firecrawl"


app = FastAPI(title="Web Extract API", version="1.1.0")

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
    # Scraper selection
    scraper: ScraperType = ScraperType.CRAWL4AI
    api_key: Optional[str] = None  # Required for Firecrawl
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


# ==================== SCRAPY SCRAPER ====================

class ScrapyContentSpider(scrapy.Spider):
    """Simple Scrapy spider for content extraction."""
    name = 'content_spider'
    
    def __init__(self, url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url] if url else []
        self.scraped_data = {}
    
    def parse(self, response):
        # Extract title
        title = response.css('title::text').get() or ''
        
        # Extract main content - try multiple selectors
        content_selectors = [
            'article',
            'main',
            '[role="main"]',
            '.content',
            '.post-content',
            '.entry-content',
            '#content',
            'body'
        ]
        
        text_content = ""
        for selector in content_selectors:
            elements = response.css(selector)
            if elements:
                # Get all text from the element
                texts = elements.css('*::text').getall()
                text_content = ' '.join(t.strip() for t in texts if t.strip())
                if len(text_content) > 100:  # Found substantial content
                    break
        
        self.scraped_data = {
            'url': response.url,
            'title': title.strip(),
            'content': text_content,
            'html': response.text[:5000]  # First 5KB of HTML
        }
        
        return self.scraped_data


async def scrape_with_scrapy(url: str) -> dict:
    """Run Scrapy spider and return results."""
    import tempfile
    import subprocess
    import sys
    
    # Create a simple script to run scrapy
    spider_script = f'''
import scrapy
from scrapy.crawler import CrawlerProcess
import json

class ContentSpider(scrapy.Spider):
    name = 'content'
    start_urls = ['{url}']
    
    def parse(self, response):
        title = response.css('title::text').get() or ''
        
        # Try multiple content selectors
        for selector in ['article', 'main', '[role="main"]', '.content', '#content', 'body']:
            elements = response.css(selector)
            if elements:
                texts = elements.css('*::text').getall()
                content = ' '.join(t.strip() for t in texts if t.strip())
                if len(content) > 100:
                    break
        else:
            content = ' '.join(response.css('body *::text').getall())
        
        result = {{
            'url': response.url,
            'title': title.strip(),
            'content': content
        }}
        print("SCRAPY_RESULT:" + json.dumps(result))

process = CrawlerProcess({{
    'LOG_LEVEL': 'ERROR',
    'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}})
process.crawl(ContentSpider)
process.start()
'''
    
    # Run in subprocess to avoid reactor issues
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(spider_script)
        f.flush()
        
        try:
            result = subprocess.run(
                [sys.executable, f.name],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # Parse result from stdout
            for line in result.stdout.split('\n'):
                if line.startswith('SCRAPY_RESULT:'):
                    data = json.loads(line[14:])
                    return data
            
            # If no result found, return error
            return {
                'url': url,
                'title': '',
                'content': result.stderr or 'No content extracted',
                'error': True
            }
        except subprocess.TimeoutExpired:
            return {
                'url': url,
                'title': '',
                'content': 'Scraping timed out',
                'error': True
            }
        finally:
            import os
            os.unlink(f.name)


# ==================== FIRECRAWL SCRAPER ====================

async def scrape_with_firecrawl(url: str, api_key: str, formats: list = None) -> dict:
    """Scrape using Firecrawl API."""
    if not FIRECRAWL_AVAILABLE:
        raise ValueError("Firecrawl is not installed. Run: pip install firecrawl-py")
    
    if not api_key:
        raise ValueError("Firecrawl API key is required")
    
    # Initialize Firecrawl client (new SDK uses 'Firecrawl' not 'FirecrawlApp')
    client = Firecrawl(api_key=api_key)
    
    # Default formats
    if formats is None:
        formats = ["markdown", "html"]
    
    try:
        # Scrape the URL (new SDK uses 'scrape' not 'scrape_url')
        result = client.scrape(url, formats=formats)
        
        # Handle both dict and object responses
        if hasattr(result, 'markdown'):
            markdown = result.markdown or ''
            html = getattr(result, 'html', '') or ''
            metadata = getattr(result, 'metadata', {}) or {}
            title = metadata.get('title', '') if isinstance(metadata, dict) else getattr(metadata, 'title', '')
        else:
            markdown = result.get('markdown', '')
            html = result.get('html', '')
            metadata = result.get('metadata', {})
            title = metadata.get('title', '')
        
        return {
            'url': url,
            'title': title,
            'content': markdown,
            'html': html,
            'metadata': metadata,
        }
    except Exception as e:
        return {
            'url': url,
            'title': '',
            'content': str(e),
            'error': True
        }


async def stream_scrape(request: ScrapeRequest):
    """Generator for SSE streaming of scrape progress."""

    def send_event(event_type: str, data: dict):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    url = str(request.url)
    scraper_name = request.scraper.value.upper()

    yield send_event("status", {"message": f"Initializing {scraper_name}...", "progress": 5})

    try:
        scraped_data = None

        # ==================== FIRECRAWL ====================
        if request.scraper == ScraperType.FIRECRAWL:
            if not FIRECRAWL_AVAILABLE:
                yield send_event("error", {"message": "Firecrawl not installed. Run: pip install firecrawl-py"})
                return
            
            # Use API key from request, or fall back to environment variable
            api_key = request.api_key or FIRECRAWL_API_KEY
            if not api_key:
                yield send_event("error", {"message": "Firecrawl API key is required. Set FIRECRAWL_API_KEY env var or provide in request."})
                return

            yield send_event("status", {"message": "Connecting to Firecrawl API...", "progress": 20})
            yield send_event("status", {"message": f"Scraping: {url}", "progress": 40})
            
            scraped_data = await scrape_with_firecrawl(url, api_key)
            
            if scraped_data.get('error'):
                yield send_event("error", {"message": f"Firecrawl error: {scraped_data['content']}"})
                return
            
            yield send_event("status", {"message": "Content received from Firecrawl", "progress": 70})

        # ==================== SCRAPY ====================
        elif request.scraper == ScraperType.SCRAPY:
            yield send_event("status", {"message": "Launching Scrapy spider...", "progress": 20})
            yield send_event("status", {"message": f"Crawling: {url}", "progress": 40})
            
            scraped_data = await scrape_with_scrapy(url)
            
            if scraped_data.get('error'):
                yield send_event("error", {"message": f"Scrapy error: {scraped_data['content']}"})
                return
            
            yield send_event("status", {"message": "Spider completed extraction", "progress": 70})

        # ==================== CRAWL4AI (default) ====================
        else:
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

                # Extract title
                title = ""
                if result.metadata and result.metadata.get('title'):
                    title = result.metadata['title']

                scraped_data = {
                    'url': url,
                    'title': title,
                    'content': markdown_content
                }

        yield send_event("status", {"message": "Preprocessing content...", "progress": 75})

        # Apply preprocessing
        preprocessor = TextPreprocessor()
        processed = scraped_data.get('content', '')

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
        doc_id = hashlib.md5(url.encode()).hexdigest()[:12]
        word_count = len(processed.split())

        output = {
            "doc_id": doc_id,
            "url": url,
            "title": scraped_data.get('title', ''),
            "content": processed,
            "word_count": word_count,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scraper_used": request.scraper.value,
            "settings_used": {
                "scraper": request.scraper.value,
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
    import os
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Scraper API on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
