from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from urllib.parse import urlparse
from database import init_db, create_link, get_link, increment_clicks, generate_slug
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

def _parse_combination(slug: str) -> str:
    # slug format is always prefix_combination_suffix; extract the middle part
    parts = slug.split('_')
    return parts[1] if len(parts) >= 3 else slug

@app.get("/{combination}")
@limiter.limit("10/minute")
def splash(combination: str , request: Request) -> _TemplateResponse | HTMLResponse:
    original_url = get_link(_parse_combination(combination))
    if not original_url:
        return HTMLResponse("Link not found", 404) # basically saying the combination/shortened url is not in our db so we dont know the redirected domain
    domain = urlparse(original_url).netloc
    slug = generate_slug(_parse_combination(combination)) # regenerates random prefix/suffix each visit by design
    return templates.TemplateResponse("splash.html", {
        "request": request,
        "original_url": original_url,
        "domain": domain,
        "slug"  : slug
    })

@app.post("/shorten")
@limiter.limit("10/minute")
def shorten(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http","https"):
        raise HTTPException(status_code = 400, detail="Invalid URL")
    combination = create_link(url)
    return {"short_url": f"/{generate_slug(combination)}"}

@app.get("/{combination}/go")
@limiter.limit("10/minute")
def redirect(combination: str) -> RedirectResponse | HTMLResponse:
    raw = _parse_combination(combination)
    original_url = get_link(raw)
    if not original_url:
        return HTMLResponse("Link not found", 404)
    increment_clicks(raw) # increment the count that tracks the number of times a link has been accessed
    return RedirectResponse(original_url, status_code=302)

@app.exception_handler(RateLimitExceeded) # this is the custom error response when rate limit is hit - controls what users see.
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests made. Please try again later :)"}
    )