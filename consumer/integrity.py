
import hashlib
import re


MIN_BODY_WORDS = 40

SUSPICIOUS_PHRASES = [
    "access denied",
    "please log in",
    "enable javascript",
    "403 forbidden",
    "verify you are human",
    "checking your browser",
]


def normalize_text(text):
    """Make text consistent before comparing it."""
    return " ".join(text.lower().split())


def generate_fingerprint(body):
    """Generate a SHA-256 fingerprint of article content."""
    normalized = normalize_text(body)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def validate_content(title, body):
    """Evaluate the quality of scraped article content."""
    reasons = []

    title = title.strip()
    body = body.strip()

    word_count = len(body.split())

    if not title:
        reasons.append("Missing article title")

    if not body:
        reasons.append("Missing article body")

    if word_count < MIN_BODY_WORDS:
        reasons.append("Article body is unusually short")

    combined_text = normalize_text(title + " " + body)

    for phrase in SUSPICIOUS_PHRASES:
        if phrase in combined_text:
            reasons.append(
                f"Suspicious content detected: {phrase}"
            )

    # Detect repeated consecutive words.
    if re.search(r"\b(\w+)(?:\s+\1){4,}\b", body, re.I):
        reasons.append("Excessive repeated words")

    quality_status = "accepted" if not reasons else "flagged"

    return {
        "quality_status": quality_status,
        "quality_reasons": reasons,
        "word_count": word_count,
        "content_fingerprint": generate_fingerprint(body)
        if body else None
    }
