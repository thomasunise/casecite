"""
Password Policy Enforcement

Provides strong password validation for enterprise legal platform.
Requirements: 12+ characters, uppercase, lowercase, digit, special character.
"""

import re


class PasswordPolicyError(Exception):
    """Raised when password does not meet policy requirements."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_password(password: str) -> list[str]:
    """
    Validate password against policy. Returns list of errors (empty = valid).

    Policy:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - No more than 3 consecutive identical characters
    """
    errors = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit")

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        errors.append("Password must contain at least one special character")

    if re.search(r"(.)\1{3,}", password):
        errors.append("Password must not contain more than 3 consecutive identical characters")

    return errors


def check_password_strength(password: str) -> dict:
    """
    Return password strength assessment for frontend display.
    """
    score = 0
    feedback = []

    if len(password) >= 12:
        score += 1
    if len(password) >= 16:
        score += 1
    if re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"[a-z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 1
    if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        score += 1

    if score <= 2:
        strength = "weak"
    elif score <= 4:
        strength = "fair"
    elif score <= 5:
        strength = "strong"
    else:
        strength = "very_strong"

    errors = validate_password(password)
    if errors:
        feedback = errors

    return {
        "strength": strength,
        "score": score,
        "max_score": 6,
        "errors": errors,
        "valid": len(errors) == 0,
        "feedback": feedback,
    }
