
import json
import logging
import os
import time
from datetime import datetime, timezone

import redis
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from integrity import validate_content
from ai_enrichment import enrich_article


# Configure application logging.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("consumer")


# Service configuration.
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://db:27017/")

PENDING_QUEUE = "articles:pending"
PROCESSING_QUEUE = "articles:processing"


def connect_services():
    """Connect to Redis and MongoDB."""

    for attempt in range(1, 11):
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=6379,
                decode_responses=True,
                socket_connect_timeout=5
            )

            redis_client.ping()

            mongo_client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000
            )

            mongo_client.admin.command("ping")

            collection = mongo_client["article_pipeline"]["articles"]

            # Ensure article IDs are unique.
            collection.create_index("id", unique=True)

            logger.info("Connected to Redis and MongoDB")

            return redis_client, collection

        except (redis.RedisError, PyMongoError) as error:
            logger.warning(
                "Connection attempt %s failed: %s",
                attempt,
                error
            )

            time.sleep(2)

    raise ConnectionError("Could not connect to services")


def scrape_article(url):
    """Download a webpage and extract its title and body."""

    response = requests.get(
        url,
        timeout=15,
        headers={
            "User-Agent": "ArticlePipelineExam/1.0"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove elements that usually contain irrelevant content.
    for element in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form"
    ]):
        element.decompose()

    # Extract the page title.
    title = (
        soup.title.get_text(" ", strip=True)
        if soup.title else ""
    )

    # Prefer the article's main heading.
    heading = soup.find("h1")

    if heading:
        title = heading.get_text(" ", strip=True)

    # Find the most relevant content container.
    article_area = (
        soup.find("article")
        or soup.find("main")
        or soup.body
    )

    if article_area is None:
        raise ValueError("No article content found")

    # Extract paragraph text.
    paragraphs = article_area.find_all("p")

    body = "\n".join(
        paragraph.get_text(" ", strip=True)
        for paragraph in paragraphs
        if paragraph.get_text(" ", strip=True)
    )

    if not title or not body:
        raise ValueError("Missing article title or body")

    return title, body


def process_article(task, collection):
    """Scrape, validate, enrich, and store an article."""

    article_id = task["id"]

    logger.info("Processing article: %s", article_id)

    started = time.monotonic()

    # Preserve the original metadata.
    result = {
        "id": article_id,
        "url": task["url"],
        "source": task["source"],
        "category": task["category"],
        "priority": task["priority"],
        "processed_at": datetime.now(timezone.utc)
    }

    try:
        # Step 1: Scrape the article.
        title, body = scrape_article(task["url"])

        # Step 2: Validate article content.
        integrity = validate_content(title, body)

        # Step 3: Check for duplicate article content.
        fingerprint = integrity["content_fingerprint"]

        duplicate = None

        if fingerprint:
            duplicate = collection.find_one(
                {
                    "id": {"$ne": article_id},
                    "status": "success",
                    "integrity.content_fingerprint": fingerprint
                },
                {"id": 1}
            )

        # Record the duplicate reference, if one exists.
        integrity["duplicate_of"] = (
            duplicate["id"] if duplicate else None
        )

        if duplicate:
            integrity["quality_status"] = "flagged"

            integrity["quality_reasons"].append(
                f"Duplicate content of article {duplicate['id']}"
            )

            logger.warning(
                "Article %s duplicates article %s",
                article_id,
                duplicate["id"]
            )

        # Step 4: Prepare the successful result.
        result.update({
            "title": title,
            "body": body,
            "status": "success",
            "error": None,
            "integrity": integrity,
            "ai": None
        })

        logger.info(
            "Scraped article %s | Quality: %s",
            article_id,
            integrity["quality_status"]
        )

        # Step 5: Generate AI insights for accepted articles.
        if (
            integrity["quality_status"] == "accepted"
            and not integrity["duplicate_of"]
        ):
            try:
                # Check whether this article already has AI results.
                previous = collection.find_one(
                    {"id": article_id},
                    {"integrity": 1, "ai": 1}
                )

                previous_ai = (
                    previous.get("ai") if previous else None
                )

                previous_integrity = (
                    previous.get("integrity") or {}
                    if previous else {}
                )

                previous_fingerprint = (
                    previous_integrity.get("content_fingerprint")
                )

                provider = os.getenv("AI_PROVIDER", "mock")

                model = (
                    os.getenv("AI_MODEL", "openai/gpt-oss-20b")
                    if provider == "groq"
                    else "mock"
                )

                # Reuse existing AI results if content is unchanged.
                if (
                    previous_fingerprint == fingerprint
                    and isinstance(previous_ai, dict)
                    and previous_ai.get("provider") == provider
                    and previous_ai.get("model") == model
                    and previous_ai.get("status") in ("success", "mock")
                ):
                    result["ai"] = previous_ai

                    logger.info(
                        "Reused AI results for article %s",
                        article_id
                    )

                else:
                    result["ai"] = enrich_article(title, body)

                    logger.info(
                        "AI enrichment completed for article %s",
                        article_id
                    )

            except Exception as error:
                # AI errors must not discard scraped articles.
                result["ai"] = {
                    "status": "failed",
                    "error": str(error)
                }

                logger.warning(
                    "AI enrichment failed for %s: %s",
                    article_id,
                    error
                )

    except (requests.RequestException, ValueError) as error:
        # Check whether this article was saved successfully before.
        previous = collection.find_one(
            {"id": article_id},
            {"status": 1}
        )

        if previous and previous.get("status") == "success":
            # Keep existing content, integrity, and AI results.
            logger.warning(
                "Could not re-scrape article %s: %s. "
                "Preserving previously successful record.",
                article_id,
                error
            )

            return

        # First-time failures are still recorded in MongoDB.
        result.update({
            "title": None,
            "body": None,
            "status": "failed",
            "error": str(error),
            "integrity": None,
            "ai": None
        })

        logger.warning(
            "Failed to scrape %s: %s",
            article_id,
            error
        )

    # Step 6: Measure processing duration.
    result["processing_seconds"] = round(
        time.monotonic() - started,
        3
    )

    # Step 7: Save without creating duplicate article IDs.
    collection.update_one(
        {"id": article_id},
        {"$set": result},
        upsert=True
    )

    logger.info(
        "Saved article %s with status %s",
        article_id,
        result["status"]
    )


def recover_pending_tasks(client):
    """Return unfinished tasks to the pending queue."""

    recovered = 0

    while True:
        task = client.rpoplpush(
            PROCESSING_QUEUE,
            PENDING_QUEUE
        )

        if task is None:
            break

        recovered += 1

    if recovered:
        logger.warning(
            "Recovered %s unfinished tasks",
            recovered
        )


def run_consumer():
    """Continuously process tasks from Redis."""

    client, collection = connect_services()

    # Recover tasks interrupted during previous processing.
    recover_pending_tasks(client)

    logger.info("Consumer is waiting for article tasks...")

    while True:
        # Move a task into the processing queue.
        task_json = client.brpoplpush(
            PENDING_QUEUE,
            PROCESSING_QUEUE,
            timeout=5
        )

        if task_json is None:
            continue

        try:
            task = json.loads(task_json)

            # Scrape, validate, and store the article.
            process_article(task, collection)

            # Acknowledge the completed task.
            client.lrem(
                PROCESSING_QUEUE,
                1,
                task_json
            )

        except (PyMongoError, redis.RedisError):
            logger.exception(
                "Database or queue operation failed"
            )

            raise

        except (ValueError, TypeError, KeyError):
            logger.exception("Invalid queued task")

            # Remove malformed tasks after logging.
            client.lrem(
                PROCESSING_QUEUE,
                1,
                task_json
            )


if __name__ == "__main__":
    run_consumer()
