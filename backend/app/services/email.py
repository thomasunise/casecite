"""Email delivery service (SendGrid).

Builds and sends transactional email. The SendGrid client performs synchronous
HTTP, so sends are dispatched via ``asyncio.to_thread`` to stay off the event
loop. Nothing in this module ever logs a reset token or a reset URL.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def build_password_reset_html(reset_url: str) -> str:
    """Render the password-reset email body."""
    return f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                            .button {{ display: inline-block; padding: 12px 24px; background: #1a365d; color: white; text-decoration: none; border-radius: 6px; }}
                            .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Password Reset Request</h1>
                            <p>We received a request to reset your password. Click the button below to set a new password:</p>
                            <p><a href="{reset_url}" class="button">Reset Password</a></p>
                            <p>This link expires in 1 hour.</p>
                            <p>If you didn't request this, you can safely ignore this email.</p>
                            <div class="footer">
                                <p>&copy; {settings.app_display_name}. All rights reserved.</p>
                            </div>
                        </div>
                    </body>
                    </html>
                """


def _send_via_sendgrid(sendgrid_key: str, to_email: str, subject: str, html_content: str) -> None:
    """Blocking SendGrid send (call via ``asyncio.to_thread``)."""
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=settings.noreply_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )
    SendGridAPIClient(sendgrid_key).send(message)


async def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Send the password-reset email; returns True once handed to SendGrid.

    Never raises: the /auth/forgot-password response must not vary with
    delivery outcome (email enumeration), so failures are logged and swallowed.
    The token/URL is never logged.
    """
    sendgrid_key = getattr(settings, "sendgrid_api_key", None)
    if not sendgrid_key:
        logger.warning("SendGrid not configured - cannot send password reset email")
        return False

    try:
        await asyncio.to_thread(
            _send_via_sendgrid,
            sendgrid_key,
            to_email,
            f"Reset your {settings.app_display_name} password",
            build_password_reset_html(reset_url),
        )
        logger.info("Password reset email sent")
        return True
    except Exception as e:  # Intentional broad catch - delivery must never raise
        # SendGrid's client raises python_http_client exceptions (and urllib
        # errors) that share no base class narrower than Exception. Log only the
        # type: the message can echo the recipient address or the request body.
        logger.error("Failed to send password reset email: %s", type(e).__name__)
        return False
