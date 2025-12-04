#!/usr/bin/env python3
"""
Smoking Cessation Resources Scraper
Uses Crawl4AI to extract clean text content from health resource pages
for RAG dataset expansion.

Output format: Individual JSON documents with source attribution for citations.
"""

import asyncio
import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator


@dataclass
class ScrapedDocument:
    """Document structure for RAG pipeline ingestion."""
    doc_id: str
    source_url: str
    source_name: str
    source_category: str
    title: str
    content: str
    content_markdown: str
    scraped_at: str
    word_count: int
    metadata: dict


# Target URLs for smoking cessation resources
SMOKING_CESSATION_SOURCES = [
    # CDC Resources (updated Dec 2024 - new site structure)
    {
        "url": "https://www.cdc.gov/tobacco/health-effects/index.html",
        "name": "CDC",
        "category": "government_guidelines"
    },
    {
        "url": "https://www.cdc.gov/tobacco/secondhand-smoke/index.html",
        "name": "CDC",
        "category": "government_guidelines"
    },
    {
        "url": "https://www.cdc.gov/tobacco/features/back-to-school.html",
        "name": "CDC",
        "category": "government_guidelines"
    },

    # Mayo Clinic Resources
    {
        "url": "https://www.mayoclinic.org/healthy-lifestyle/quit-smoking/basics/quit-smoking-basics/hlv-20049487",
        "name": "Mayo Clinic",
        "category": "medical_institution"
    },
    {
        "url": "https://www.mayoclinic.org/healthy-lifestyle/quit-smoking/in-depth/nicotine-craving/art-20045454",
        "name": "Mayo Clinic",
        "category": "medical_institution"
    },
    {
        "url": "https://www.mayoclinic.org/healthy-lifestyle/quit-smoking/in-depth/quit-smoking-products/art-20045599",
        "name": "Mayo Clinic",
        "category": "medical_institution"
    },
    {
        "url": "https://www.mayoclinic.org/diseases-conditions/nicotine-dependence/symptoms-causes/syc-20351584",
        "name": "Mayo Clinic",
        "category": "medical_institution"
    },

    # American Lung Association
    {
        "url": "https://www.lung.org/quit-smoking",
        "name": "American Lung Association",
        "category": "nonprofit_health"
    },
    {
        "url": "https://www.lung.org/quit-smoking/i-want-to-quit",
        "name": "American Lung Association",
        "category": "nonprofit_health"
    },
    {
        "url": "https://www.lung.org/quit-smoking/i-want-to-quit/reasons-to-quit-smoking",
        "name": "American Lung Association",
        "category": "nonprofit_health"
    },
    {
        "url": "https://www.lung.org/quit-smoking/smoking-facts",
        "name": "American Lung Association",
        "category": "nonprofit_health"
    },
    {
        "url": "https://www.lung.org/quit-smoking/helping-teens-quit",
        "name": "American Lung Association",
        "category": "nonprofit_health"
    },

    # AHRQ Clinical Guidelines
    {
        "url": "https://www.ahrq.gov/prevention/guidelines/tobacco/index.html",
        "name": "AHRQ",
        "category": "clinical_guidelines"
    },

    # Smokefree.gov (NCI/NIH)
    {
        "url": "https://smokefree.gov/",
        "name": "Smokefree.gov",
        "category": "government_guidelines"
    },
    {
        "url": "https://smokefree.gov/quit-smoking/why-you-should-quit",
        "name": "Smokefree.gov",
        "category": "government_guidelines"
    },
    {
        "url": "https://smokefree.gov/quit-smoking/getting-started",
        "name": "Smokefree.gov",
        "category": "government_guidelines"
    },
    {
        "url": "https://smokefree.gov/challenges-when-quitting/cravings-triggers",
        "name": "Smokefree.gov",
        "category": "government_guidelines"
    },

    # National Cancer Institute
    {
        "url": "https://www.cancer.gov/about-cancer/causes-prevention/risk/tobacco/quit-smoking-hp-pdq",
        "name": "National Cancer Institute",
        "category": "government_guidelines"
    },
]


class SmokingCessationScraper:
    """Scraper for smoking cessation health resources."""

    def __init__(self, output_dir: str = "scraped_data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Rate limiting: delay between requests (seconds)
        # Conservative for government/medical sites
        self.rate_limit_delay = 3.0

        # Configure content filtering for clean extraction
        self.content_filter = PruningContentFilter(
            threshold=0.4,
            threshold_type="dynamic"
        )

        self.markdown_generator = DefaultMarkdownGenerator(
            content_filter=self.content_filter
        )

    def _generate_doc_id(self, url: str) -> str:
        """Generate a unique document ID from URL."""
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _clean_text(self, text: str) -> str:
        """Clean extracted text content."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)

        # Remove common navigation/footer patterns
        patterns_to_remove = [
            r'Skip to main content',
            r'Cookie Settings',
            r'Privacy Policy',
            r'Terms of Use',
            r'©\s*\d{4}.*?(?:All rights reserved|$)',
            r'Follow us on.*?(?:\n|$)',
            r'Share this page.*?(?:\n|$)',
        ]

        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    def _extract_title(self, result) -> str:
        """Extract page title from crawl result."""
        if result.metadata and result.metadata.get('title'):
            return result.metadata['title']

        # Try to extract from markdown h1
        markdown_text = ""
        if result.markdown:
            if hasattr(result.markdown, 'raw_markdown'):
                markdown_text = result.markdown.raw_markdown or ""
            elif isinstance(result.markdown, str):
                markdown_text = result.markdown

        if markdown_text:
            match = re.search(r'^#\s+(.+)$', markdown_text, re.MULTILINE)
            if match:
                return match.group(1).strip()

        return "Untitled Document"

    async def scrape_url(
        self,
        crawler: AsyncWebCrawler,
        source: dict,
        max_retries: int = 2
    ) -> Optional[ScrapedDocument]:
        """Scrape a single URL and return structured document."""
        url = source["url"]

        for attempt in range(max_retries + 1):
            try:
                config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    markdown_generator=self.markdown_generator,
                    # Use domcontentloaded for faster loading on slow sites
                    wait_until="domcontentloaded",
                    # Extended timeout for government/medical sites
                    page_timeout=60000,
                    # Add delay after page load to let JS render
                    delay_before_return_html=2.0,
                )

                result = await crawler.arun(url=url, config=config)

                if not result.success:
                    if attempt < max_retries:
                        print(f"  ⚠ Attempt {attempt + 1} failed, retrying...")
                        await asyncio.sleep(2)
                        continue
                    print(f"  ✗ Failed: {url}")
                    print(f"    Error: {result.error_message}")
                    return None

                # Extract markdown - handle MarkdownGenerationResult object
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

                # Extract and clean content
                clean_content = self._clean_text(markdown_content)

                if not clean_content or len(clean_content) < 100:
                    print(f"  ⚠ Skipped (insufficient content): {url}")
                    return None

                # Build document
                doc = ScrapedDocument(
                    doc_id=self._generate_doc_id(url),
                    source_url=url,
                    source_name=source["name"],
                    source_category=source["category"],
                    title=self._extract_title(result),
                    content=clean_content,
                    content_markdown=markdown_content,
                    scraped_at=datetime.utcnow().isoformat() + "Z",
                    word_count=len(clean_content.split()),
                    metadata={
                        "links_count": len(result.links.get("internal", [])) + len(result.links.get("external", [])) if result.links else 0,
                        "has_images": bool(result.media and result.media.get("images")),
                    }
                )

                print(f"  ✓ Scraped: {doc.title[:60]}... ({doc.word_count} words)")
                return doc

            except Exception as e:
                if attempt < max_retries:
                    print(f"  ⚠ Attempt {attempt + 1} error: {str(e)[:50]}... retrying...")
                    await asyncio.sleep(3)
                    continue
                print(f"  ✗ Error scraping {url}: {str(e)}")
                return None

        return None

    def save_document(self, doc: ScrapedDocument) -> Path:
        """Save document as JSON file."""
        filename = f"{doc.doc_id}_{doc.source_name.lower().replace(' ', '_')}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(asdict(doc), f, indent=2, ensure_ascii=False)

        return filepath

    async def run(self, sources: list = None):
        """Run the scraper on all sources."""
        sources = sources or SMOKING_CESSATION_SOURCES

        print("=" * 60)
        print("Smoking Cessation Resources Scraper")
        print("=" * 60)
        print(f"Target sources: {len(sources)} URLs")
        print(f"Output directory: {self.output_dir.absolute()}")
        print(f"Rate limit delay: {self.rate_limit_delay}s between requests")
        print("=" * 60)

        documents = []

        async with AsyncWebCrawler(verbose=False) as crawler:
            for i, source in enumerate(sources):
                print(f"\n[{i+1}/{len(sources)}] {source['name']}")
                print(f"    URL: {source['url']}")

                doc = await self.scrape_url(crawler, source)

                if doc:
                    filepath = self.save_document(doc)
                    documents.append(doc)
                    print(f"    Saved: {filepath.name}")

                # Rate limiting - be polite to servers
                if i < len(sources) - 1:
                    print(f"    Waiting {self.rate_limit_delay}s (rate limiting)...")
                    await asyncio.sleep(self.rate_limit_delay)

        # Save manifest file
        self._save_manifest(documents)

        print("\n" + "=" * 60)
        print("Scraping Complete!")
        print("=" * 60)
        print(f"Successfully scraped: {len(documents)}/{len(sources)} documents")
        print(f"Total words collected: {sum(d.word_count for d in documents):,}")
        print(f"Output directory: {self.output_dir.absolute()}")
        print("=" * 60)

        return documents

    def _save_manifest(self, documents: list):
        """Save a manifest of all scraped documents."""
        manifest = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "total_documents": len(documents),
            "total_words": sum(d.word_count for d in documents),
            "sources_by_category": {},
            "documents": []
        }

        for doc in documents:
            cat = doc.source_category
            if cat not in manifest["sources_by_category"]:
                manifest["sources_by_category"][cat] = 0
            manifest["sources_by_category"][cat] += 1

            manifest["documents"].append({
                "doc_id": doc.doc_id,
                "source_name": doc.source_name,
                "title": doc.title,
                "word_count": doc.word_count,
                "url": doc.source_url
            })

        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"\nManifest saved: {manifest_path}")


async def main():
    """Main entry point."""
    scraper = SmokingCessationScraper(output_dir="scraped_data")
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
