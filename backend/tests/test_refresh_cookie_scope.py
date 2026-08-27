"""
Tests for refresh-token cookie scoping.

Guards the fix for the inert-logout bug: the refresh cookie was scoped to
path=/api/v1/auth/refresh, so the browser never sent it to /api/v1/auth/logout
and the logout handler's refresh-revocation code was dead. The cookie must be
scoped to /api/v1/auth so both /refresh and /logout receive it.
"""

import os

os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["ENCRYPTION_SALT"] = "test-salt-16chars!"
os.environ["DEBUG"] = "true"

from http.cookies import SimpleCookie

from app.routers.auth import _clear_auth_cookies, _set_auth_cookies
from fastapi import Request, Response


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/login",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def _cookies_from(response: Response) -> list[SimpleCookie]:
    out = []
    for key, value in response.raw_headers:
        if key == b"set-cookie":
            cookie = SimpleCookie()
            cookie.load(value.decode())
            out.append(cookie)
    return out


class TestRefreshCookieScope:
    def test_refresh_cookie_path_covers_logout(self):
        response = Response()
        _set_auth_cookies(_make_request(), response, "access-tok", "refresh-tok")

        refresh = [c for c in _cookies_from(response) if "refresh_token" in c]
        assert refresh, "refresh_token cookie must be set"
        path = refresh[0]["refresh_token"]["path"]
        # /api/v1/auth covers both /refresh and /logout; the old value
        # /api/v1/auth/refresh made logout revocation unreachable.
        assert path == "/api/v1/auth"

    def test_refresh_cookie_stays_httponly_and_scoped(self):
        response = Response()
        _set_auth_cookies(_make_request(), response, "access-tok", "refresh-tok")

        refresh = [c for c in _cookies_from(response) if "refresh_token" in c][0]
        morsel = refresh["refresh_token"]
        assert morsel["httponly"]
        assert morsel["samesite"].lower() == "strict"
        # Must never widen to site root — that would expose the refresh token
        # to every endpoint instead of just the auth router.
        assert morsel["path"] != "/"

    def test_clear_deletes_both_old_and_new_paths(self):
        response = Response()
        _clear_auth_cookies(response)

        refresh_paths = {
            c["refresh_token"]["path"] for c in _cookies_from(response) if "refresh_token" in c
        }
        # Both the current path and the pre-broadening path must be cleared so
        # sessions issued before the change don't keep a stale cookie.
        assert refresh_paths == {"/api/v1/auth", "/api/v1/auth/refresh"}
