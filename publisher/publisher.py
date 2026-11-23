
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import redis


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("publisher")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE_NAME = "articles:pending"

ARTICLES_FILE = Path(
    os.getenv("ARTICLES_FILE", "/app/articles.json")
)

REQUIRED_FIELDS = {
    "id", "url", "source", "category", "priority"
}

VALID_PRIORITIES = {"high", "medium", "low"}


def load_articles():
    with ARTICLES_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    articles = data.get("articles")

    if not isinstance(articles, list):
        raise ValueError("'articles' must be a list")

    return articles


def validate_article(article):
    if not isinstance(article, dict):
        return False

    if not REQUIRED_FIELDS.issubset(article):
        return False

    for field in REQUIRED_FIELDS:
        if not isinstance(article[field], str):
            return False
        if not article[field].strip():
            return False

    parsed_url = urlparse(article["url"])

    if parsed_url.scheme not in {"http", "https"}:
        return False

    if not parsed_url.hostname:
        return False

    if article["priority"] not in VALID_PRIORITIES:
        return False

    return True


def connect_to_redis():
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=5
    )

    for attempt in range(1, 11):
        try:
            client.ping()
            logger.info("Connected to Redis")
            return client
        except redis.RedisError as error:
            logger.warning(
                "Redis connection attempt %s failed: %s",
                attempt,
                error
            )
            time.sleep(2)

    raise ConnectionError("Could not connect to Redis")


def publish_articles():
    articles = load_articles()
    client = connect_to_redis()

    published = 0
    skipped = 0
    seen_ids = set()

    for article in articles:
        if not validate_article(article):
            logger.warning("Skipping invalid article: %s", article)
            skipped += 1
            continue

        article_id = article["id"]

        if article_id in seen_ids:
            logger.warning("Duplicate ID in dataset: %s", article_id)
            skipped += 1
            continue

        seen_ids.add(article_id)

        payload = {
            field: article[field]
            for field in REQUIRED_FIELDS
        }

        client.lpush(QUEUE_NAME, json.dumps(payload))

        published += 1
        logger.info("Published article: %s", article_id)

    logger.info(
        "Finished: %s published, %s skipped",
        published,
        skipped
    )


if __name__ == "__main__":
    try:
        publish_articles()
    except (OSError, ValueError, redis.RedisError, ConnectionError):
        logger.exception("Publisher failed")
        raise
