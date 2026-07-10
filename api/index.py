"""Vercel Python entrypoint.

Vercel's Python runtime looks for an ASGI-compatible `app` object in files
under `api/`. All backend routes (defined on the real FastAPI app in
`app/main.py`) are served through this single function; `vercel.json`
rewrites `/api/*`, `/health`, and `/artifacts/*` here so FastAPI's own
router resolves the exact path.
"""

from app.main import app

__all__ = ["app"]
