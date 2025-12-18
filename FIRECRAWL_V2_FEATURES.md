# Firecrawl v2 API Integration

This document describes the enhanced Firecrawl v2 API integration features added to the Neural Extraction Engine.

## Overview

The scraper now supports advanced Firecrawl v2 API features including:
- Multiple output format options (markdown, HTML, links, screenshots)
- AI-powered LLM extraction with natural language prompts
- Page interaction capabilities with Actions
- Enhanced metadata extraction

## New Features

### 1. Multiple Output Formats

Select from multiple output formats when scraping with Firecrawl:

- **Markdown**: Clean, LLM-ready markdown content (default)
- **HTML**: Raw HTML content
- **Links**: Extract all links from the page with titles
- **Screenshot**: Capture page screenshot

**API Usage:**
```python
{
  "url": "https://example.com",
  "scraper": "firecrawl",
  "firecrawl_formats": ["markdown", "html", "links", "screenshot"]
}
```

### 2. LLM Extraction

Extract structured data using natural language prompts. The AI will automatically structure the output based on your prompt.

**Examples:**

Extract company information:
```python
{
  "url": "https://company.com",
  "scraper": "firecrawl",
  "firecrawl_extract_prompt": "Extract the company name, mission statement, and contact email"
}
```

Extract product details:
```python
{
  "url": "https://shop.com/product",
  "scraper": "firecrawl",
  "firecrawl_extract_prompt": "Extract product name, price, description, and availability"
}
```

**Response includes:**
```json
{
  "extracted_data": {
    "company_name": "Acme Corp",
    "mission_statement": "Building the future...",
    "contact_email": "contact@acme.com"
  }
}
```

### 3. Page Actions (Advanced)

Interact with pages before scraping using Actions. Useful for:
- Clicking buttons
- Filling forms
- Scrolling
- Waiting for dynamic content
- Taking screenshots at specific points

**API Usage:**
```python
{
  "url": "https://example.com",
  "scraper": "firecrawl",
  "firecrawl_actions": [
    {"type": "wait", "milliseconds": 2000},
    {"type": "click", "selector": "button.load-more"},
    {"type": "wait", "milliseconds": 3000},
    {"type": "screenshot"}
  ]
}
```

**Available Action Types:**
- `wait`: Pause execution (requires `milliseconds`)
- `click`: Click an element (requires `selector`)
- `write`: Type text (requires `text`)
- `press`: Press a key (requires `key`)
- `screenshot`: Capture screenshot
- `scroll`: Scroll the page

### 4. Enhanced Metadata

Firecrawl v2 provides comprehensive metadata including:
- Page title and description
- Language detection
- Status code
- Keywords and robots directives
- Open Graph tags (ogTitle, ogDescription, ogImage)
- Source URL

## Web UI Integration

### Firecrawl Options Panel

When Firecrawl is selected as the scraper, additional options appear:

1. **Output Formats**: Checkboxes to select desired formats
2. **LLM Extraction**: Textarea for natural language extraction prompts

### Result Display

Enhanced result display shows:
- Extracted structured data (if LLM extraction was used)
- Links found on the page (up to 20 shown)
- Screenshot indicators
- Comprehensive metadata

## API Request Examples

### Basic Scraping with Multiple Formats
```bash
curl -X POST http://localhost:8080/api/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://firecrawl.dev",
    "scraper": "firecrawl",
    "api_key": "fc-YOUR_API_KEY",
    "firecrawl_formats": ["markdown", "html", "links"]
  }'
```

### LLM Extraction Example
```bash
curl -X POST http://localhost:8080/api/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://company.com/about",
    "scraper": "firecrawl",
    "api_key": "fc-YOUR_API_KEY",
    "firecrawl_formats": ["markdown"],
    "firecrawl_extract_prompt": "Extract the company name, founded year, and number of employees"
  }'
```

### With Actions (Search Example)
```bash
curl -X POST http://localhost:8080/api/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://google.com",
    "scraper": "firecrawl",
    "api_key": "fc-YOUR_API_KEY",
    "firecrawl_actions": [
      {"type": "click", "selector": "input[name=q]"},
      {"type": "write", "text": "firecrawl"},
      {"type": "press", "key": "ENTER"},
      {"type": "wait", "milliseconds": 3000}
    ]
  }'
```

## Response Format

### Standard Response
```json
{
  "doc_id": "abc123",
  "url": "https://example.com",
  "title": "Example Page",
  "content": "Markdown content here...",
  "word_count": 1500,
  "scraped_at": "2024-01-15T10:30:00Z",
  "scraper_used": "firecrawl"
}
```

### Enhanced Response (with Firecrawl v2 features)
```json
{
  "doc_id": "abc123",
  "url": "https://example.com",
  "title": "Example Page",
  "content": "Markdown content here...",
  "html": "<html>...</html>",
  "links": [
    {"url": "https://example.com/page1", "title": "Page 1"},
    {"url": "https://example.com/page2", "title": "Page 2"}
  ],
  "screenshot": "base64_encoded_image_data...",
  "extracted_data": {
    "company_name": "Example Corp",
    "founded": 2020,
    "employees": 50
  },
  "metadata": {
    "title": "Example Page",
    "description": "Page description",
    "language": "en",
    "statusCode": 200,
    "ogTitle": "Example Page",
    "ogDescription": "Description",
    "ogImage": "https://example.com/image.jpg"
  },
  "word_count": 1500,
  "scraped_at": "2024-01-15T10:30:00Z",
  "scraper_used": "firecrawl"
}
```

## Code Changes

### Backend Changes (scraper_api.py)

1. **Updated ScrapeRequest Model** (lines 96-100):
   - Added `firecrawl_formats` for format selection
   - Added `firecrawl_actions` for page interactions
   - Added `firecrawl_extract_schema` for schema-based extraction
   - Added `firecrawl_extract_prompt` for prompt-based extraction

2. **Enhanced scrape_with_firecrawl Function** (lines 300-442):
   - Support for multiple output formats
   - Actions integration
   - LLM extraction with schema or prompt
   - Comprehensive response parsing for all data types
   - Better error handling

3. **Updated stream_scrape Function** (lines 460-507):
   - Pass Firecrawl v2 options to scraper
   - Enhanced progress messages
   - Better error reporting

4. **Enhanced Output Building** (lines 661-672):
   - Include links, screenshots, extracted data, and metadata in response
   - Conditional inclusion based on availability

### Frontend Changes (static/index.html)

1. **New UI Controls** (lines 944-983):
   - Format selection checkboxes
   - LLM extraction prompt textarea
   - Integrated into Firecrawl API key section

2. **Updated JavaScript** (lines 1304-1322):
   - Collect and send Firecrawl v2 options
   - Build format array from checkboxes
   - Include extraction prompt if provided

3. **Enhanced Result Display** (lines 1380-1439):
   - Show extracted data prominently
   - Display links found
   - Log screenshot capture
   - Formatted output with sections

## Best Practices

### When to Use Each Feature

**Multiple Formats:**
- Use `markdown` for LLM training and RAG systems
- Use `html` when you need to preserve exact structure
- Use `links` for building sitemaps or discovering content
- Use `screenshot` for visual documentation

**LLM Extraction:**
- Perfect for structured data extraction from unstructured pages
- Use clear, specific prompts describing what to extract
- Works best with well-structured websites

**Actions:**
- Essential for single-page applications (SPAs)
- Useful for sites with lazy-loaded content
- Required for sites with consent banners or popups
- Great for automating repetitive navigation tasks

### Tips

1. **Start Simple**: Begin with just `markdown` format, add others as needed
2. **Be Specific**: LLM extraction works best with clear, detailed prompts
3. **Test Actions**: Complex action sequences may need adjustment per site
4. **Monitor Credits**: Advanced features use more Firecrawl API credits
5. **Combine Features**: Use formats + extraction for comprehensive results

## Troubleshooting

### Common Issues

**Issue**: "Firecrawl API key is required"
- **Solution**: Set `FIRECRAWL_API_KEY` env var or provide via `api_key` parameter

**Issue**: No extracted data despite using prompt
- **Solution**: Make prompt more specific, ensure page has relevant content

**Issue**: Actions timing out
- **Solution**: Increase wait times between actions, simplify action sequence

**Issue**: Screenshot not captured
- **Solution**: Ensure `screenshot` is in formats list or use screenshot action

## Resources

- [Firecrawl Documentation](https://docs.firecrawl.dev)
- [Firecrawl API Reference](https://docs.firecrawl.dev/api-reference)
- [Get Firecrawl API Key](https://firecrawl.dev)
- [Firecrawl GitHub](https://github.com/mendableai/firecrawl)

## Version History

- **v1.1**: Added Firecrawl v2 API support
  - Multiple format options
  - LLM extraction with prompts
  - Actions support (API-level)
  - Enhanced metadata extraction
  - Improved UI controls
