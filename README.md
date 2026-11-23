
# Article Processing Pipeline

A Docker-based publisher–consumer pipeline built with Python, Redis, and MongoDB.

The system publishes article metadata from a JSON dataset, processes article URLs through a Redis queue, scrapes article content, validates content integrity, and stores the results in MongoDB.

## Technologies

- Python 3.12
- Redis 7
- MongoDB 7
- Docker and Docker Compose
- Requests and BeautifulSoup
- PyMongo
- Python unittest

## Architecture

articles.json
    |
    v
Python Publisher
    |
    v
Redis Queue
    |
    v
Python Consumer
    |
    v
Web Scraper
    |
    v
Smart Article Integrity Engine
    |
    v
MongoDB

## Prerequisites

- Docker Engine with Docker Compose plugin, or Docker Desktop
- Internet connectivity to fetch article URLs
- Git (for cloning the repository)

Python, Redis, and MongoDB do not need separate host installations.

## Quick Start

Clone the repository:

```bash
git clone <YOUR_REPOSITORY_URL>
cd technical-exam
```

Start Redis and MongoDB:

```bash
docker compose up -d redis db
```

Build and start the Consumer:

```bash
docker compose up -d --build consumer
```

Publish article tasks:

```bash
docker compose run --build --rm publisher
```

Alternatively, start all configured services with:

```bash
docker compose up --build
```

The publisher runs once and exits. The consumer continues listening for tasks.

## Database

Database: article_pipeline
Collection: articles

Each document stores:

- Article ID
- Source URL
- Source and category
- Priority
- Scraped title and body
- Processing status
- Error information
- Processing duration
- Integrity validation results

A unique index on the article ID prevents duplicate database records.

MongoDB upserts update existing records instead of inserting another document with the same ID.

## Error Handling

The Consumer handles scraping failures such as:

- HTTP errors
- Connection failures
- Request timeouts
- Missing article content

Failed articles are stored with a failed status and an error description.

Redis uses separate pending and processing lists. The Consumer acknowledges tasks after database storage and attempts to recover unfinished tasks during startup.

## Additional Feature: Smart Article Integrity Engine

The Smart Article Integrity Engine checks article content after scraping.

### Content Quality Validation

Detects:

- Missing titles
- Empty article bodies
- Unusually short content
- Suspicious access-restriction messages
- Excessively repeated consecutive words

Articles are marked as accepted or flagged. Flagged content is retained for inspection.

### Content Fingerprinting

The engine normalizes article body text and generates a SHA-256 fingerprint.

### Duplicate Content Detection

The Consumer checks MongoDB for another article with the same fingerprint.

If matching content is found under another article ID, the article is flagged and a duplicate reference is stored.

This detects identical normalized article text, not paraphrased content.

## Testing

Run the automated tests:

```bash
docker compose build consumer

docker run --rm \
  -v "$PWD:/project:ro" \
  -w /project \
  -e PYTHONDONTWRITEBYTECODE=1 \
  technical-exam-consumer \
  python -m unittest discover -s tests -v
```

Five automated tests have passed:

1. Valid article validation
2. Short article detection
3. Suspicious content detection
4. Consistent content fingerprints
5. Mock-based duplicate detection

## Initial Pipeline Results

The initial end-to-end run processed 10 article tasks.

- 6 articles scraped successfully
- 4 articles failed with HTTP 403 responses
- 10 unique article records stored in MongoDB
- Pending and processing Redis queues emptied

The failures demonstrate that scraping errors are handled without stopping the entire pipeline.

## LLM Integration

LLM integration is an optional extension and is not currently implemented.

A future extension could use the Gemini API to summarize accepted articles or extract technical keywords.

## Design Choices

### Why MongoDB?

MongoDB stores flexible JSON-like documents, making it suitable for article metadata, scraped text, error information, and integrity results.

### Why Redis Lists?

Redis Lists provide a simple task queue without requiring a more complex message-broker setup.

### Why Docker Compose?

Docker Compose allows the required services to run together using a reproducible configuration.

### Limitations

- Some websites block automated scraping.
- Different article websites use different HTML structures.
- Content quality checks use configurable heuristics.
- Duplicate detection compares exact normalized content fingerprints.
- Task recovery is designed for a single Consumer worker and is not a fully distributed acknowledgment system.
- No graphical user interface is included because the application is a backend processing pipeline.
```
