# ScaryURL

A URL shortener that generates phishing-style links for security awareness and education. Shortened URLs look like `lottery_abc123_now` or `secure-login_xyz789_urgent` — deliberately suspicious so recipients learn to pause before clicking.

Every link goes through a warning splash page showing the real destination before redirecting.

## How it works

1. Visit the landing page and paste a URL
2. Get back a scary-looking short link (e.g. `/redeem_aB3xZ9_urgent`)
3. Anyone who visits the link sees a warning page with the real destination domain
4. They choose to proceed or go back

Links expire after 90 days.

## Setup

### Local development

**1. Start Postgres and Redis**
```bash
docker compose up postgres redis -d
```

**2. Create a virtual environment and install dependencies**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Create a `.env` file**
```
DATABASE_URL=postgresql://scaryurl:scaryurl@localhost:5432/scaryurl
REDIS_URL=redis://localhost:6379
```

**4. Run the app**
```bash
uvicorn main:app --reload
```

Visit `http://localhost:8000` to use the landing page.

### Full Docker (app + databases)

```bash
docker compose up --build
```

This starts the app, Postgres, and Redis together. The app is available at `http://localhost:8000`.

## Running tests

```bash
pytest test_app.py -v
```

Requires Postgres and Redis to be running (see setup above).

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Landing page with URL input form |
| `POST` | `/shorten?url=<url>` | Shorten a URL, returns `{"short_url": "/slug"}` |
| `GET` | `/{slug}` | Splash warning page |
| `GET` | `/{slug}/go` | Redirect to the real URL |
| `GET` | `/health` | Health check (Postgres + Redis status) |

## Architecture

```
User submits URL
       |
       v
  POST /shorten
       |
       v
  Generate 6-char combination (62^6 = ~56.8B possibilities)
       |
       v
  Store in Postgres + Redis (write-through cache)
       |
       v
  Return scary slug (prefix_combination_suffix)


User visits scary link
       |
       v
  GET /{slug} -> parse combination from slug
       |
       v
  Check Redis cache (7-day TTL, refreshes on each read)
       |
  hit? --> refresh TTL --> return URL
       |
  miss? --> query Postgres --> check expiration --> populate Redis --> return URL
       |
       v
  Show splash warning page
       |
       v
  GET /{slug}/go -> redirect to original URL
```

## Implementation notes

**Redis caching** — write-through on link creation (creator likely tests their link immediately) + cache-aside on reads. 7-day TTL with refresh-on-read — the TTL resets every time a link is accessed, so popular links stay cached indefinitely while inactive ones get evicted after 7 days of no activity.

**Link expiration** — links expire after 90 days (`expires_at` column). Expired links return HTTP 410 Gone.

**Connection pooling** — uses `psycopg2.ThreadedConnectionPool` to reuse database connections across requests. Connections are always returned to the pool via `try/finally`.

**Rate limiting** — `slowapi` limits requests per IP (10/minute) to prevent abuse.

**URL validation** — submitted URLs must have `http` or `https` scheme.

**XSS protection** — all user-supplied data is rendered through Jinja2 templates with autoescaping enabled.

**SQL injection safe** — all queries use psycopg2 parameterized statements.

**Health check** — `GET /health` pings both Postgres and Redis, returns 503 if either is down.

## Stack

- [FastAPI](https://fastapi.tiangolo.com/) — API framework
- [PostgreSQL](https://www.postgresql.org/) — persistent storage with connection pooling (psycopg2)
- [Redis](https://redis.io/) — caching layer (7-day TTL)
- [Jinja2](https://jinja.palletsprojects.com/) — HTML templating
- [slowapi](https://github.com/laurentS/slowapi) — rate limiting
- [Docker](https://www.docker.com/) — containerized deployment
- [pytest](https://docs.pytest.org/) — test suite
