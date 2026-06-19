# ScaryURL

A URL shortener that generates phishing-style links for security awareness and education. Shortened URLs look like `lottery_abc123_now` or `secure-login_xyz789_urgent` — deliberately suspicious so recipients learn to pause before clicking.

Every link goes through a warning splash page showing the real destination before redirecting.

## How it works

1. Submit a URL to `POST /shorten` — get back a scary-looking short link
2. Anyone who visits the link sees a warning page with the real destination domain
3. They choose to proceed or go back

## Setup

**1. Clone and create a virtual environment**
```
pip install -r requirements.txt
```

**2. Create a `.env` file**
```
DATABASE_URL=postgresql://user:password@host:port/dbname
```

**3. Run**
```
uvicorn main:app --reload
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/shorten?url=<url>` | Shorten a URL, returns `{"short_url": "/slug"}` |
| `GET` | `/{slug}` | Splash warning page |
| `GET` | `/{slug}/go` | Redirect to the real URL |

## Implementation notes

**Connection pooling** — uses `psycopg2.ThreadedConnectionPool` to reuse database connections across requests rather than opening a new one each time. Connections are always returned to the pool via `try/finally`, so nothing leaks even on errors.

**Rate limiting** — `slowapi` limits requests per IP to prevent abuse of the `/shorten` endpoint.

**URL validation** — submitted URLs are validated for a valid scheme (`http`/`https`) and host before being stored, rejecting malformed or non-URL input.

**XSS protection** — all user-supplied data is rendered through Jinja2 templates with autoescaping enabled, so injected HTML/JS in URLs is rendered as plain text.

**SQL injection safe** — all queries use psycopg2 parameterized statements; no raw string interpolation.

## Stack

- [FastAPI](https://fastapi.tiangolo.com/) — API framework
- [psycopg2](https://www.psycopg.org/) — PostgreSQL with connection pooling
- [Jinja2](https://jinja.palletsprojects.com/) — HTML templating
- [slowapi](https://github.com/laurentS/slowapi) — Rate limiting
