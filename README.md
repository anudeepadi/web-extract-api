# SCRAPE — Neural Extraction Engine

A stunning web scraper with a cyberpunk-editorial UI, powered by Crawl4AI. Extract clean, preprocessed content from any website with live streaming output.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![Crawl4AI](https://img.shields.io/badge/Crawl4AI-0.7.7-cyan)

## Features

### Advanced Scraping
- **JavaScript Rendering** — Wait for dynamic content to load
- **Stealth Mode** — Bypass bot detection on protected sites
- **Page Scrolling** — Handle infinite scroll and lazy-loaded content
- **BM25 Filtering** — Intelligent content extraction using BM25 algorithm

### Content Preprocessing
- Remove links while preserving text
- Strip images and media
- Remove navigation, headers, and footers
- Extract main content only
- Clean whitespace and formatting

### Beautiful UI
- Neo-brutalist meets luxury terminal aesthetic
- Real-time SSE streaming output
- Terminal-style logging with color-coded messages
- Smooth progress animations
- Copy/Download extracted content

## Installation

```bash
# Clone the repository
git clone https://github.com/anudeepadi/automatic-winner.git
cd automatic-winner

# Install dependencies
pip install crawl4ai fastapi uvicorn

# Setup Crawl4AI browsers
crawl4ai-setup
```

## Usage

### Web UI

```bash
python scraper_api.py
```

Open http://localhost:8080 in your browser.

### CLI Scraper

```bash
python smoking_cessation_scraper.py
```

Scrapes smoking cessation resources from CDC, Mayo Clinic, American Lung Association, and more.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scrape` | Scrape a URL with SSE streaming |
| GET | `/api/health` | Health check |

### Request Body

```json
{
  "url": "https://example.com",
  "wait_for_js": true,
  "wait_time": 2.0,
  "scroll_page": false,
  "stealth_mode": false,
  "remove_links": false,
  "remove_images": false,
  "remove_nav_footer": true,
  "only_main_content": true,
  "use_bm25_filter": false
}
```

### Response (SSE Stream)

```
event: status
data: {"message": "Fetching URL...", "progress": 30}

event: result
data: {"doc_id": "abc123", "title": "Page Title", "content": "...", "word_count": 1500}
```

## Output Format

Each scraped document is saved as JSON:

```json
{
  "doc_id": "unique_hash",
  "source_url": "https://...",
  "source_name": "Source Name",
  "title": "Page Title",
  "content": "Cleaned text content...",
  "content_markdown": "Full markdown...",
  "scraped_at": "2024-12-04T...",
  "word_count": 1234
}
```

## Project Structure

```
├── scraper_api.py              # FastAPI backend with SSE
├── smoking_cessation_scraper.py # CLI scraper for health resources
├── static/
│   └── index.html              # Stunning web UI
└── scraped_data/               # Output directory
    ├── manifest.json
    └── *.json                  # Individual documents
```

## Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **Scraping**: Crawl4AI, Playwright
- **Frontend**: Vanilla JS, CSS3 animations
- **Fonts**: Syne, Instrument Serif, Space Mono

## License

MIT
