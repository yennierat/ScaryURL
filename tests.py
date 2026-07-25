# Steps to run tests:
# 1. Make sure Postgres and Redis are running (docker compose up postgres redis -d)
# 2. Activate venv: source venv/bin/activate
# 3. Install deps: pip install -r requirements.txt
# 4. Run tests: pytest test_app.py -v

from datetime import datetime, timedelta
import pytest
from main import app, _parse_combination
from database import (
    generate_combination, generate_slug, PREFIXES, SUFFIXES,
    record_rate_limit_violation, block_ip, is_ip_blocked,
    redis_client, VIOLATION_THRESHOLD
)


# --- Unit tests for generate_combination ---

def test_generate_combination_length():
    combo = generate_combination()
    assert len(combo) == 6

def test_generate_combination_alphanumeric():
    combo = generate_combination()
    assert combo.isalnum()

def test_generate_combination_unique():
    combos = {generate_combination() for _ in range(100)}
    assert len(combos) == 100


# --- Unit tests for generate_slug ---

def test_generate_slug_format():
    slug = generate_slug("abc123")
    parts = slug.split("_")
    assert len(parts) == 3
    assert parts[0] in PREFIXES
    assert parts[1] == "abc123"
    assert parts[2] in SUFFIXES


# --- Unit tests for _parse_combination ---

def test_parse_combination_with_full_slug():
    assert _parse_combination("lottery_abc123_urgent") == "abc123"

def test_parse_combination_with_raw_combination():
    assert _parse_combination("abc123") == "abc123"

def test_parse_combination_with_two_parts():
    assert _parse_combination("prefix_suffix") == "prefix_suffix"


# --- Integration tests for API endpoints ---

@pytest.fixture
def client():
    from starlette.testclient import TestClient
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["postgres"] == "up"
    assert data["redis"] == "up"


def test_landing_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "ScaryURL" in response.text


def test_shorten_valid_url(client):
    response = client.post("/shorten?url=https://example.com")
    assert response.status_code == 200
    data = response.json()
    assert "short_url" in data
    assert data["short_url"].startswith("/")


def test_shorten_invalid_url(client):
    response = client.post("/shorten?url=ftp://example.com")
    assert response.status_code == 400


def test_shorten_and_splash(client):
    response = client.post("/shorten?url=https://example.com")
    short_url = response.json()["short_url"]

    response = client.get(short_url)
    assert response.status_code == 200
    assert "example.com" in response.text


def test_shorten_and_redirect(client):
    response = client.post("/shorten?url=https://example.com")
    short_url = response.json()["short_url"]

    response = client.get(f"{short_url}/go", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com"


def test_not_found(client):
    response = client.get("/nonexistent")
    assert response.status_code == 404


def test_expired_link(client):
    response = client.post("/shorten?url=https://expired.com")
    short_url = response.json()["short_url"]
    combination = _parse_combination(short_url.lstrip("/"))

    from database import get_db, return_db
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE urls SET expires_at = %s WHERE combination = %s",
            (datetime.now() - timedelta(days=1), combination)
        )
    db.commit()
    return_db(db)

    from database import redis_client
    redis_client.delete(f"url:{combination}")

    response = client.get(short_url)
    assert response.status_code == 410
    assert "expired" in response.text.lower()


# --- Unit test for cache behavior ---

def test_cache_populated_on_create(client):
    response = client.post("/shorten?url=https://cached.com")
    short_url = response.json()["short_url"]
    combination = _parse_combination(short_url.lstrip("/"))

    from database import redis_client
    cached = redis_client.get(f"url:{combination}")
    assert cached == "https://cached.com"


def test_cache_populated_on_read(client):
    response = client.post("/shorten?url=https://readcache.com")
    short_url = response.json()["short_url"]
    combination = _parse_combination(short_url.lstrip("/"))

    from database import redis_client
    redis_client.delete(f"url:{combination}")

    response = client.get(short_url)
    assert response.status_code == 200

    cached = redis_client.get(f"url:{combination}")
    assert cached == "https://readcache.com"


# --- IP abuse detection and blocking tests ---

@pytest.fixture(autouse=True)
def cleanup_redis_keys():
    for key in redis_client.scan_iter("ratelimit:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("LIMITS:*"):
        redis_client.delete(key)
    yield
    for key in redis_client.scan_iter("ratelimit:*"):
        redis_client.delete(key)
    for key in redis_client.scan_iter("LIMITS:*"):
        redis_client.delete(key)


def test_record_violation_increments_counter():
    ip = "10.0.0.1"
    record_rate_limit_violation(ip)
    count = redis_client.get(f"ratelimit:violations:{ip}")
    assert count == "1"


def test_record_violation_returns_false_below_threshold():
    ip = "10.0.0.2"
    for _ in range(VIOLATION_THRESHOLD - 1):
        result = record_rate_limit_violation(ip)
        assert result is False


def test_record_violation_returns_true_at_threshold():
    ip = "10.0.0.3"
    for i in range(VIOLATION_THRESHOLD):
        result = record_rate_limit_violation(ip)
    assert result is True


def test_block_ip_sets_key():
    ip = "10.0.0.4"
    block_ip(ip)
    assert is_ip_blocked(ip) is True


def test_is_ip_blocked_returns_false_for_unblocked():
    assert is_ip_blocked("10.0.0.99") is False


def test_block_ip_cleans_violation_counter():
    ip = "10.0.0.5"
    record_rate_limit_violation(ip)
    assert redis_client.exists(f"ratelimit:violations:{ip}") == 1
    block_ip(ip)
    assert redis_client.exists(f"ratelimit:violations:{ip}") == 0


def test_blocked_ip_gets_403(client):
    block_ip("testclient")
    response = client.get("/")
    assert response.status_code == 403
    assert "blocked" in response.json()["detail"].lower()


def test_blocked_ip_can_still_hit_health(client):
    block_ip("testclient")
    response = client.get("/health")
    assert response.status_code == 200


def test_unblocked_ip_passes_middleware(client):
    response = client.get("/")
    assert response.status_code == 200
