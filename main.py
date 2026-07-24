from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import urlparse
from database import init_db, create_link, get_link, increment_clicks, generate_slug, redis_client, get_db, return_db
from starlette.templating import _TemplateResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi import HTTPException

limiter = Limiter(key_func=get_remote_address)

app = FastAPI()

app.state.limiter = limiter # added rate limiter just in case people spam it 

templates = Jinja2Templates(directory="templates")

init_db() # initialise the db

@app.get("/health")
def health():
    status = {"postgres": "down", "redis": "down"}
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        return_db(db)
        status["postgres"] = "up"
    except Exception:
        pass
    try:
        redis_client.ping()
        status["redis"] = "up"
    except Exception:
        pass
    all_healthy = all(v == "up" for v in status.values())
    if not all_healthy:
        raise HTTPException(status_code=503, detail=status)
    return status

@app.get("/", response_model=None)
@limiter.limit("10/minute")
def landing(request: Request):
    return templates.TemplateResponse(request, "index.html", {})

def _parse_combination(slug: str) -> str:
    # slug format is always prefix_combination_suffix; extract the middle part
    parts = slug.split('_')
    return parts[1] if len(parts) >= 3 else slug

@app.get("/{combination}", response_model=None)
@limiter.limit("10/minute")
def splash(combination: str , request: Request) -> _TemplateResponse | HTMLResponse:
    original_url = get_link(_parse_combination(combination))
    if not original_url:
        return HTMLResponse("Link not found", 404)
    if original_url == "EXPIRED":
        return HTMLResponse("This link has expired", 410)
    domain = urlparse(original_url).netloc
    return templates.TemplateResponse(request, "splash.html", {
        "original_url": original_url,
        "domain": domain,
        "slug"  : combination
    })

@app.post("/shorten")
@limiter.limit("10/minute")
def shorten(url: str, request: Request) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http","https"):
        raise HTTPException(status_code = 400, detail="Invalid URL")
    combination = create_link(url)
    return {"short_url": f"/{generate_slug(combination)}"}

@app.get("/{combination}/go", response_model=None)
@limiter.limit("10/minute")
def redirect(combination: str, request: Request) -> RedirectResponse | HTMLResponse:
    raw = _parse_combination(combination)
    original_url = get_link(raw)
    if not original_url:
        return HTMLResponse("Link not found", 404)
    if original_url == "EXPIRED":
        return HTMLResponse("This link has expired", 410)
    increment_clicks(raw) # increment the count that tracks the number of times a link has been accessed
    return RedirectResponse(original_url, status_code=302)

@app.exception_handler(RateLimitExceeded) # this is the custom error response when rate limit is hit - controls what users see.
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests made. Please try again later :)"}
    )