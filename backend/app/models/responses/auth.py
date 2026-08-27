"""Auth response models — authentication, sessions, password reset."""

from pydantic import BaseModel


class UserInfo(BaseModel):
    """User details embedded in login and /me responses."""

    id: str
    email: str
    name: str
    roles: list[str]


class LoginResponse(BaseModel):
    """POST /auth/login, /auth/demo/login (dev only), /auth/azure/login — token grant.

    Note: refresh_token is delivered exclusively via httpOnly cookie and is
    intentionally omitted from the response body.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


class TokenRefreshResponse(BaseModel):
    """POST /auth/refresh — new access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SessionsResponse(BaseModel):
    """GET /auth/sessions — active sessions for the current user."""

    sessions: list[dict]


class CurrentUserResponse(BaseModel):
    """GET /auth/me — current authenticated user info."""

    id: str
    email: str
    roles: list[str]
    token_expires: str


class AzureConfigResponse(BaseModel):
    """GET /auth/azure/config — Azure AD frontend configuration."""

    authority: str
    client_id: str
    redirect_uri: str
    scopes: list[str]


class ResetTokenValidationResponse(BaseModel):
    """POST /auth/verify-reset-token — token validity check."""

    valid: bool
