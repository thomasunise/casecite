"""
Frontend Routes

Mounts static files and configures SPA catch-all routing
for the Vite-built frontend.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI) -> None:
    """Mount static files and SPA catch-all routes on the FastAPI application."""

    # Serve only the frontend's public/ static assets — NEVER the whole
    # frontend/ tree, which contains source, node_modules, and any stray .env.
    frontend_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend"
    )
    public_path = os.path.join(frontend_root, "public")
    if os.path.isdir(public_path):
        app.mount("/static", StaticFiles(directory=public_path), name="static")

    # Serve Vite-built frontend (mirrors nginx config in production)
    _dist_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist"
    )
    _dist_index = os.path.join(_dist_path, "index.html")

    if os.path.exists(_dist_path) and os.path.exists(_dist_index):
        # Serve built assets (JS, CSS, images)
        app.mount(
            "/assets",
            StaticFiles(directory=os.path.join(_dist_path, "assets")),
            name="frontend-assets",
        )

        # Serve logo and other root-level static files from dist
        @app.get("/logo.webp")
        async def serve_logo():
            logo = os.path.join(_dist_path, "logo.webp")
            if os.path.exists(logo):
                return FileResponse(logo, media_type="image/webp")
            raise HTTPException(status_code=404)

        # Resolve the dist root once so every request can be contained against it.
        _dist_root = os.path.realpath(_dist_path)

        # SPA catch-all: serve index.html for any non-API route
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Don't intercept API, health, docs, or other backend routes
            if full_path.startswith(
                ("api/", "health", "ready", "metrics", "docs", "redoc", "openapi")
            ):
                raise HTTPException(status_code=404)
            # Serve a real file only when it resolves to somewhere INSIDE dist/.
            # `full_path` is attacker-controlled and Starlette does not collapse
            # `..` segments, so a client bypassing browser normalization
            # (curl --path-as-is, or percent-encoded `%2e%2e%2f`) could otherwise
            # escape dist/ and read .env, the key stores, or the SQLite DBs.
            # realpath() also resolves symlinks, so a symlink pointing outside
            # dist/ is rejected too. Anything outside falls through to the SPA
            # index (harmless) rather than being served.
            if full_path:
                requested = os.path.realpath(os.path.join(_dist_root, full_path))
                if (
                    requested == _dist_root or requested.startswith(_dist_root + os.sep)
                ) and os.path.isfile(requested):
                    return FileResponse(requested)
            return FileResponse(_dist_index)
